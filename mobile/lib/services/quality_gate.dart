/// On-device image quality gate.
///
/// Runs before anything is stored or queued so the health worker gets an
/// immediate retake prompt while the patient is still in front of them —
/// waiting for a round trip would defeat the purpose in a low-connectivity
/// setting.
///
/// It mirrors the server-side measurements (variance of the Laplacian for
/// focus, luminance for exposure, disc coverage and centring for framing,
/// red-channel dominance for retinal visibility). The server re-runs the same
/// gate on upload and remains the authority; this is a fast local pre-check,
/// never a clinical assessment.
library;

import 'dart:math' as math;
import 'dart:typed_data';

import 'package:image/image.dart' as img;

import '../domain/models.dart';

/// Thresholds and normalisation references.
///
/// Defaults match the server's seeded configuration. They are fetched from
/// `/config` when online and cached, so tuning happens in one place.
class QualityPolicy {
  const QualityPolicy({
    this.overallMin = 0.55,
    this.blurMin = 0.45,
    this.lightingMin = 0.40,
    this.framingMin = 0.40,
    this.retinalVisibilityMin = 0.50,
    this.minWidth = 224,
    this.minHeight = 224,
    // Calibrated against 250 real APTOS fundus photographs. These MUST stay in
    // step with backend/app/domain/config_defaults.py — if the device and the
    // server disagree, a capture accepted here is rejected on upload and the
    // health worker is sent round a loop they cannot win.
    this.analysisLongEdge = 512,
    this.sharpnessReference = 30.0,
    this.targetLuminance = 90.5,
    this.luminanceTolerance = 65.0,
    this.maxClippedFraction = 0.02,
    this.targetCoverage = 0.789,
    this.coverageTolerance = 0.692,
    this.maxCentreOffset = 0.136,
    this.redRatioFloor = 0.36,
    this.redRatioSpan = 0.14,
  });

  final double overallMin;
  final double blurMin;
  final double lightingMin;
  final double framingMin;
  final double retinalVisibilityMin;
  final int minWidth;
  final int minHeight;
  final int analysisLongEdge;
  final double sharpnessReference;
  final double targetLuminance;
  final double luminanceTolerance;
  final double maxClippedFraction;
  final double targetCoverage;
  final double coverageTolerance;
  final double maxCentreOffset;
  final double redRatioFloor;
  final double redRatioSpan;

  /// Build from the server's `quality.thresholds` + `quality.normalisation`.
  factory QualityPolicy.fromServer(
    Map<String, dynamic> thresholds,
    Map<String, dynamic> normalisation,
  ) {
    double read(Map<String, dynamic> src, String key, double fallback) =>
        (src[key] as num?)?.toDouble() ?? fallback;

    return QualityPolicy(
      overallMin: read(thresholds, 'overall_min', 0.55),
      blurMin: read(thresholds, 'blur_min', 0.45),
      lightingMin: read(thresholds, 'lighting_min', 0.40),
      framingMin: read(thresholds, 'framing_min', 0.40),
      retinalVisibilityMin: read(thresholds, 'retinal_visibility_min', 0.50),
      minWidth: (thresholds['min_width'] as num?)?.toInt() ?? 224,
      minHeight: (thresholds['min_height'] as num?)?.toInt() ?? 224,
      analysisLongEdge:
          (normalisation['analysis_long_edge'] as num?)?.toInt() ?? 512,
      sharpnessReference: read(normalisation, 'sharpness_reference', 30.0),
      targetLuminance: read(normalisation, 'target_luminance', 90.5),
      luminanceTolerance: read(normalisation, 'luminance_tolerance', 65.0),
      maxClippedFraction: read(normalisation, 'max_clipped_fraction', 0.02),
      targetCoverage: read(normalisation, 'target_coverage', 0.789),
      coverageTolerance: read(normalisation, 'coverage_tolerance', 0.692),
      maxCentreOffset: read(normalisation, 'max_centre_offset', 0.136),
      redRatioFloor: read(normalisation, 'red_ratio_floor', 0.36),
      redRatioSpan: read(normalisation, 'red_ratio_span', 0.14),
    );
  }
}

/// Guidance shown to the person holding the camera.
const Map<String, String> qualityRecommendations = {
  'blur': 'Hold the phone steady and let the camera focus before capturing.',
  'low_light': 'Increase illumination slightly, or move to a darker room to widen the pupil.',
  'overexposed': 'Reduce the light intensity or move the lens slightly further away.',
  'poor_framing': 'Centre the retina in the frame and move slightly closer.',
  'retina_not_visible': 'Align the lens with the pupil until the retina fills the circle.',
  'low_resolution': 'Use a higher capture resolution.',
};

class QualityGate {
  const QualityGate({this.policy = const QualityPolicy()});

  final QualityPolicy policy;

  /// Assess raw encoded image bytes (JPEG/PNG).
  QualityAssessment assess(Uint8List bytes) {
    // decodeImage does not merely return null on bad input — its format
    // sniffers can throw (a truncated frame can reach the PSD decoder and
    // overrun its header read). A corrupt camera frame must produce a retake
    // prompt, never crash the screening in the field.
    img.Image? decoded;
    try {
      decoded = img.decodeImage(bytes);
    } catch (_) {
      decoded = null;
    }

    if (decoded == null) {
      return const QualityAssessment(
        isAcceptable: false,
        overallScore: 0,
        blurScore: 0,
        lightingScore: 0,
        framingScore: 0,
        retinalVisibilityScore: 0,
        issues: ['retina_not_visible'],
        recommendations: ['That file could not be read as an image. Capture again.'],
      );
    }
    return assessImage(decoded);
  }

  /// Resize so measurements do not depend on the phone's sensor resolution.
  ///
  /// Variance of the Laplacian is scale-dependent: the same photograph measured
  /// at 3000px and at 512px gives very different values. Without this the gate's
  /// verdict would vary by handset rather than by image quality.
  img.Image _toAnalysisScale(img.Image source) {
    final longEdge = math.max(source.width, source.height);
    if (longEdge <= policy.analysisLongEdge) return source;

    final scale = policy.analysisLongEdge / longEdge;
    return img.copyResize(
      source,
      width: math.max(1, (source.width * scale).round()),
      height: math.max(1, (source.height * scale).round()),
      interpolation: img.Interpolation.average,
    );
  }

  QualityAssessment assessImage(img.Image original) {
    final issues = <String>[];

    // Resolution is judged on the original capture; everything else on a
    // fixed analysis scale so the result is comparable across devices.
    if (original.width < policy.minWidth || original.height < policy.minHeight) {
      issues.add('low_resolution');
    }

    final source = _toAnalysisScale(original);
    final width = source.width;
    final height = source.height;

    final luma = _luminance(source);
    final mask = _retinaMask(luma, width, height);

    final blurScore = _clamp(_laplacianVariance(luma, width, height) / policy.sharpnessReference);

    // -- lighting --
    var retinaSum = 0.0;
    var retinaCount = 0;
    var clippedBright = 0;
    for (var i = 0; i < luma.length; i++) {
      if (mask[i]) {
        retinaSum += luma[i];
        retinaCount++;
      }
      if (luma[i] >= 253) clippedBright++;
    }
    final meanLuminance = retinaCount > 0 ? retinaSum / retinaCount : 0.0;
    final luminanceScore = _clamp(
      1.0 - (meanLuminance - policy.targetLuminance).abs() / policy.luminanceTolerance,
    );
    final clippedFraction = clippedBright / luma.length;
    final clippingScore = _clamp(1.0 - clippedFraction / policy.maxClippedFraction);
    final lightingScore = _clamp(math.min(luminanceScore, clippingScore));

    // -- framing --
    final coverage = retinaCount / luma.length;
    final coverageScore = _clamp(
      1.0 - (coverage - policy.targetCoverage).abs() / policy.coverageTolerance,
    );

    var sumX = 0.0;
    var sumY = 0.0;
    if (retinaCount > 0) {
      for (var y = 0; y < height; y++) {
        for (var x = 0; x < width; x++) {
          if (mask[y * width + x]) {
            sumX += x;
            sumY += y;
          }
        }
      }
    }
    final centreOffset = retinaCount > 0
        ? _distance(sumX / retinaCount - width / 2, sumY / retinaCount - height / 2) /
            math.max(1.0, _distance(width.toDouble(), height.toDouble()) / 2)
        : 1.0;
    final centringScore = _clamp(1.0 - centreOffset / policy.maxCentreOffset);
    final framingScore = _clamp(math.min(coverageScore, centringScore));

    // -- retinal visibility (fundus imagery is red-dominant) --
    var red = 0.0;
    var green = 0.0;
    var blue = 0.0;
    if (retinaCount > 0) {
      for (var y = 0; y < height; y++) {
        for (var x = 0; x < width; x++) {
          if (!mask[y * width + x]) continue;
          final pixel = source.getPixel(x, y);
          red += pixel.r.toDouble();
          green += pixel.g.toDouble();
          blue += pixel.b.toDouble();
        }
      }
    }
    final total = red + green + blue;
    final redRatio = total > 0 ? red / total : 0.0;
    // Floor and span are policy, not constants baked into the algorithm.
    final rednessScore =
        _clamp((redRatio - policy.redRatioFloor) / policy.redRatioSpan);
    final visibilityScore = _clamp(math.min(coverageScore, rednessScore));

    final overall = (blurScore + lightingScore + framingScore + visibilityScore) / 4;

    if (blurScore < policy.blurMin) issues.add('blur');
    if (lightingScore < policy.lightingMin) {
      issues.add(meanLuminance > policy.targetLuminance ? 'overexposed' : 'low_light');
    }
    if (framingScore < policy.framingMin) issues.add('poor_framing');
    if (visibilityScore < policy.retinalVisibilityMin) issues.add('retina_not_visible');

    final acceptable = issues.isEmpty && overall >= policy.overallMin;
    if (issues.isEmpty && !acceptable) issues.add('blur');

    return QualityAssessment(
      isAcceptable: acceptable,
      overallScore: _round(overall),
      blurScore: _round(blurScore),
      lightingScore: _round(lightingScore),
      framingScore: _round(framingScore),
      retinalVisibilityScore: _round(visibilityScore),
      issues: issues,
      recommendations: issues
          .map((issue) => qualityRecommendations[issue])
          .whereType<String>()
          .toList(growable: false),
    );
  }

  // ---- helpers ----

  Float32List _luminance(img.Image source) {
    final out = Float32List(source.width * source.height);
    var index = 0;
    for (var y = 0; y < source.height; y++) {
      for (var x = 0; x < source.width; x++) {
        final pixel = source.getPixel(x, y);
        out[index++] =
            0.299 * pixel.r.toDouble() + 0.587 * pixel.g.toDouble() + 0.114 * pixel.b.toDouble();
      }
    }
    return out;
  }

  /// Fundus photographs sit on a dark surround, so a low threshold separates
  /// the illuminated disc from the background.
  List<bool> _retinaMask(Float32List luma, int width, int height) =>
      List<bool>.generate(luma.length, (i) => luma[i] > 18, growable: false);

  /// Variance of the 3x3 Laplacian response — a standard focus measure.
  double _laplacianVariance(Float32List luma, int width, int height) {
    if (width < 3 || height < 3) return 0;
    final responses = <double>[];
    for (var y = 1; y < height - 1; y++) {
      for (var x = 1; x < width - 1; x++) {
        final centre = luma[y * width + x];
        final response = luma[(y - 1) * width + x] +
            luma[(y + 1) * width + x] +
            luma[y * width + (x - 1)] +
            luma[y * width + (x + 1)] -
            4 * centre;
        responses.add(response);
      }
    }
    if (responses.isEmpty) return 0;
    final mean = responses.reduce((a, b) => a + b) / responses.length;
    var variance = 0.0;
    for (final value in responses) {
      variance += (value - mean) * (value - mean);
    }
    return variance / responses.length;
  }

  double _distance(double dx, double dy) => math.sqrt(dx * dx + dy * dy);

  double _clamp(double value) => value.isNaN ? 0 : math.min(1.0, math.max(0.0, value));

  double _round(double value) => (value * 10000).round() / 10000;
}
