/// Guided capture overlay and instrument readouts.
///
/// The camera preview is framed as a screening instrument, not a photo app:
/// a fixed alignment reticle, live align/light/focus readouts, and a scanning
/// sweep while the quality gate runs.
library;

import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../../domain/models.dart';
import '../theme.dart';

/// Fixed alignment target the operator lines the pupil up with.
class CaptureReticle extends StatelessWidget {
  const CaptureReticle({super.key, this.hasFailed = false});

  final bool hasFailed;

  @override
  Widget build(BuildContext context) {
    return IgnorePointer(
      child: CustomPaint(
        painter: _ReticlePainter(
          color: hasFailed ? RsColors.danger : RsColors.accent,
        ),
        child: const SizedBox.expand(),
      ),
    );
  }
}

class _ReticlePainter extends CustomPainter {
  const _ReticlePainter({required this.color});

  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    final centre = Offset(size.width / 2, size.height / 2);
    final radius = math.min(size.width, size.height) * 0.36;

    final outline = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.6
      ..color = color.withValues(alpha: 0.85);

    // Dashed outer ring — the framing target.
    const segments = 48;
    for (var i = 0; i < segments; i++) {
      if (i.isOdd) continue;
      final start = (i / segments) * 2 * math.pi;
      const sweep = (1 / segments) * 2 * math.pi;
      canvas.drawArc(
        Rect.fromCircle(center: centre, radius: radius),
        start,
        sweep,
        false,
        outline,
      );
    }

    // Inner ring marks the macula target zone.
    canvas.drawCircle(
      centre,
      radius * 0.42,
      Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1.0
        ..color = color.withValues(alpha: 0.45),
    );

    // Cardinal tick marks.
    final tick = Paint()
      ..strokeWidth = 2.0
      ..color = color.withValues(alpha: 0.8);
    const tickLength = 14.0;
    for (final angle in [0, math.pi / 2, math.pi, 3 * math.pi / 2]) {
      final outer = Offset(
        centre.dx + math.cos(angle) * (radius + 18),
        centre.dy + math.sin(angle) * (radius + 18),
      );
      final inner = Offset(
        centre.dx + math.cos(angle) * (radius + 18 - tickLength),
        centre.dy + math.sin(angle) * (radius + 18 - tickLength),
      );
      canvas.drawLine(inner, outer, tick);
    }
  }

  @override
  bool shouldRepaint(covariant _ReticlePainter oldDelegate) =>
      oldDelegate.color != color;
}

/// Sweeping scan line shown while the quality gate is evaluating.
class ScanningIndicator extends StatefulWidget {
  const ScanningIndicator({super.key});

  @override
  State<ScanningIndicator> createState() => _ScanningIndicatorState();
}

class _ScanningIndicatorState extends State<ScanningIndicator>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 1400),
  )..repeat();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    // Respect the platform's reduced-motion preference.
    final reduceMotion = MediaQuery.maybeOf(context)?.disableAnimations ?? false;
    if (reduceMotion) {
      return const Center(
        child: Text(
          'Checking image quality…',
          style: TextStyle(color: Colors.white70, fontWeight: FontWeight.w600),
        ),
      );
    }

    return AnimatedBuilder(
      animation: _controller,
      builder: (context, _) => LayoutBuilder(
        builder: (context, constraints) {
          final travel = constraints.maxHeight;
          return Stack(
            children: [
              Positioned(
                top: (_controller.value * travel * 1.4) - travel * 0.2,
                left: 0,
                right: 0,
                child: Container(
                  height: travel * 0.28,
                  decoration: BoxDecoration(
                    gradient: LinearGradient(
                      begin: Alignment.topCenter,
                      end: Alignment.bottomCenter,
                      colors: [
                        Colors.transparent,
                        RsColors.accent.withValues(alpha: 0.45),
                        Colors.transparent,
                      ],
                    ),
                  ),
                ),
              ),
            ],
          );
        },
      ),
    );
  }
}

/// One instrument readout: bar, percentage and label.
class QualityReadout extends StatelessWidget {
  const QualityReadout({
    super.key,
    required this.label,
    this.score,
    this.analysing = false,
  });

  final String label;
  final double? score;
  final bool analysing;

  Color get _tone {
    final value = score;
    if (value == null) return RsColors.inkSubtle;
    if (value >= 0.70) return RsColors.ok;
    if (value >= 0.45) return RsColors.warn;
    return RsColors.danger;
  }

  @override
  Widget build(BuildContext context) {
    final percent = score == null ? null : (score! * 100).round();

    return Expanded(
      child: NeumorphicPanel(
        sunken: true,
        padding: const EdgeInsets.symmetric(
          horizontal: RsSpacing.sm,
          vertical: RsSpacing.sm + 2,
        ),
        child: Column(
          children: [
            Text(
              label.toUpperCase(),
              style: const TextStyle(
                fontSize: 10,
                letterSpacing: 1.2,
                fontWeight: FontWeight.w700,
                color: RsColors.inkSubtle,
              ),
            ),
            const SizedBox(height: RsSpacing.sm),
            ClipRRect(
              borderRadius: BorderRadius.circular(4),
              child: LinearProgressIndicator(
                value: analysing && score == null ? null : (score ?? 0),
                minHeight: 6,
                backgroundColor: RsColors.line,
                valueColor: AlwaysStoppedAnimation(_tone),
              ),
            ),
            const SizedBox(height: RsSpacing.xs + 2),
            Text(
              percent == null ? (analysing ? '···' : '—') : '$percent%',
              style: TextStyle(
                fontSize: 13,
                fontWeight: FontWeight.w700,
                color: _tone,
                fontFeatures: const [FontFeature.tabularFigures()],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Risk chip. Glyph + label + colour — three redundant cues, never colour alone.
class RiskChip extends StatelessWidget {
  const RiskChip({super.key, required this.level});

  final RiskLevel level;

  Color get _color => switch (level) {
        RiskLevel.low => RsColors.riskLow,
        RiskLevel.moderate => RsColors.riskModerate,
        RiskLevel.high => RsColors.riskHigh,
        RiskLevel.urgent => RsColors.riskUrgent,
      };

  @override
  Widget build(BuildContext context) {
    return Semantics(
      label: '${level.label} risk',
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
        decoration: BoxDecoration(
          color: _color.withValues(alpha: 0.14),
          borderRadius: BorderRadius.circular(8),
          border: Border.all(color: _color.withValues(alpha: 0.45)),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(level.glyph, style: TextStyle(color: _color, fontSize: 13)),
            const SizedBox(width: 6),
            Text(
              '${level.label} risk'.toUpperCase(),
              style: TextStyle(
                color: _color,
                fontSize: 11,
                letterSpacing: 0.9,
                fontWeight: FontWeight.w800,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Standing notice wherever AI output is shown.
class AiAssistanceNotice extends StatelessWidget {
  const AiAssistanceNotice({super.key});

  @override
  Widget build(BuildContext context) {
    return const NeumorphicPanel(
      sunken: true,
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(Icons.info_outline, size: 18, color: RsColors.inkMuted),
          SizedBox(width: RsSpacing.sm),
          Expanded(
            child: Text(
              'AI-assisted screening support. This is not a diagnosis. '
              'A qualified clinician reviews every screening.',
              style: TextStyle(fontSize: 13, color: RsColors.inkMuted, height: 1.4),
            ),
          ),
        ],
      ),
    );
  }
}
