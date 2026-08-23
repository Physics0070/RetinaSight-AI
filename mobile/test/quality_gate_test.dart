/// On-device quality gate.
///
/// Uses synthetic fundus-like images (red-dominant disc on a dark surround),
/// matching the backend's test fixtures so both gates are checked against the
/// same shapes.
library;

import 'dart:math' as math;
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:image/image.dart' as img;
import 'package:retinasight/domain/models.dart';
import 'package:retinasight/services/quality_gate.dart';

img.Image syntheticFundus({
  int size = 320,
  bool blurred = false,
  double brightness = 1.0,
  double coverage = 0.75,
  int offsetX = 0,
  int offsetY = 0,
}) {
  final image = img.Image(width: size, height: size);
  final radius = math.sqrt(coverage / math.pi) * size;
  final centre = size / 2;

  for (var y = 0; y < size; y++) {
    for (var x = 0; x < size; x++) {
      final dx = x - centre - offsetX;
      final dy = y - centre - offsetY;
      final inside = (dx * dx + dy * dy) <= radius * radius;

      if (!inside) {
        image.setPixelRgb(x, y, 0, 0, 0);
        continue;
      }

      // Vessel-like texture so the focus measure has real signal.
      final texture = math.sin(x / 3.0) * math.cos(y / 4.0) * 26.0;
      int channel(double base) =>
          ((base + texture) * brightness).clamp(0, 255).round();

      image.setPixelRgb(x, y, channel(165), channel(70), channel(55));
    }
  }

  return blurred ? img.gaussianBlur(image, radius: 6) : image;
}

Uint8List encode(img.Image image) => Uint8List.fromList(img.encodeJpg(image, quality: 95));

void main() {
  const gate = QualityGate();

  group('acceptance', () {
    test('a reasonable capture passes', () {
      final result = gate.assessImage(syntheticFundus());

      expect(result.isAcceptable, isTrue);
      expect(result.issues, isEmpty);
      expect(result.overallScore, inInclusiveRange(0.0, 1.0));
    });

    test('scores always stay within 0..1', () {
      for (final brightness in [0.05, 1.0, 3.0]) {
        final result = gate.assessImage(syntheticFundus(brightness: brightness));
        for (final score in [
          result.overallScore,
          result.blurScore,
          result.lightingScore,
          result.framingScore,
          result.retinalVisibilityScore,
        ]) {
          expect(score, inInclusiveRange(0.0, 1.0));
        }
      }
    });
  });

  group('rejection with guidance', () {
    test('a blurred capture is rejected and explains why', () {
      final result = gate.assessImage(syntheticFundus(blurred: true));

      expect(result.isAcceptable, isFalse);
      expect(result.issues, contains('blur'));
      expect(result.recommendations, isNotEmpty);
    });

    test('a dark capture is rejected', () {
      final result = gate.assessImage(syntheticFundus(brightness: 0.12));

      expect(result.isAcceptable, isFalse);
      expect(result.issues, contains('low_light'));
    });

    test('a badly framed capture is rejected', () {
      final result = gate.assessImage(
        syntheticFundus(coverage: 0.05, offsetX: 90, offsetY: 90),
      );

      expect(result.isAcceptable, isFalse);
      expect(result.issues, contains('poor_framing'));
    });

    test('a frame with no retina is rejected', () {
      final green = img.Image(width: 320, height: 320);
      img.fill(green, color: img.ColorRgb8(20, 90, 30));

      final result = gate.assessImage(green);

      expect(result.isAcceptable, isFalse);
      expect(result.issues, contains('retina_not_visible'));
    });

    test('a low-resolution capture is flagged', () {
      final result = gate.assessImage(syntheticFundus(size: 64));

      expect(result.issues, contains('low_resolution'));
      expect(result.isAcceptable, isFalse);
    });

    test('unreadable bytes are rejected rather than crashing', () {
      final result = gate.assess(Uint8List.fromList([1, 2, 3, 4, 5]));

      expect(result.isAcceptable, isFalse);
      expect(result.recommendations, isNotEmpty);
    });

    test('every reported issue carries actionable guidance', () {
      final result = gate.assessImage(syntheticFundus(blurred: true, brightness: 0.1));

      for (final issue in result.issues) {
        expect(
          qualityRecommendations.containsKey(issue),
          isTrue,
          reason: 'issue "$issue" has no guidance for the operator',
        );
      }
    });
  });

  group('configuration', () {
    test('thresholds are policy-driven, not hardcoded', () {
      final image = syntheticFundus(blurred: true);
      const permissive = QualityPolicy(
        overallMin: 0,
        blurMin: 0,
        lightingMin: 0,
        framingMin: 0,
        retinalVisibilityMin: 0,
      );

      expect(gate.assessImage(image).isAcceptable, isFalse);
      expect(
        const QualityGate(policy: permissive).assessImage(image).isAcceptable,
        isTrue,
      );
    });

    test('server configuration maps onto the local policy', () {
      final policy = QualityPolicy.fromServer(
        {'overall_min': 0.8, 'blur_min': 0.7, 'min_width': 512},
        {'sharpness_reference': 300.0, 'target_luminance': 100.0},
      );

      expect(policy.overallMin, 0.8);
      expect(policy.blurMin, 0.7);
      expect(policy.minWidth, 512);
      expect(policy.sharpnessReference, 300.0);
      // Unspecified keys fall back to the documented defaults.
      expect(policy.framingMin, 0.40);
    });
  });

  group('serialisation', () {
    test('an assessment round-trips through JSON', () {
      final original = gate.assessImage(syntheticFundus());
      final restored = QualityAssessment.fromJson(original.toJson());

      expect(restored.isAcceptable, original.isAcceptable);
      expect(restored.overallScore, original.overallScore);
      expect(restored.issues, original.issues);
    });
  });
}
