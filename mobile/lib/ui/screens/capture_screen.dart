/// Guided retinal capture screen.
///
/// Presents as a dedicated screening instrument: live preview inside a fixed
/// alignment reticle, per-eye progress, immediate quality feedback with a
/// retake loop, and explicit exits at every point.
library;

import 'dart:typed_data';

import 'package:camera/camera.dart';
import 'package:flutter/material.dart';

import '../../domain/models.dart';
import '../../services/screening_controller.dart';
import '../theme.dart';
import '../widgets/capture_reticle.dart';

class CaptureScreen extends StatefulWidget {
  const CaptureScreen({
    super.key,
    required this.controller,
    required this.patientName,
    this.cameras = const [],
  });

  final ScreeningController controller;
  final String patientName;
  final List<CameraDescription> cameras;

  @override
  State<CaptureScreen> createState() => _CaptureScreenState();
}

class _CaptureScreenState extends State<CaptureScreen> {
  CameraController? _camera;
  EyeSide _activeEye = EyeSide.left;
  bool _analysing = false;
  bool _cameraReady = false;
  String? _cameraError;

  @override
  void initState() {
    super.initState();
    _initCamera();
  }

  Future<void> _initCamera() async {
    if (widget.cameras.isEmpty) {
      setState(() => _cameraError = 'No camera is available on this device.');
      return;
    }
    try {
      final controller = CameraController(
        widget.cameras.first,
        ResolutionPreset.veryHigh,
        enableAudio: false,
      );
      await controller.initialize();
      if (!mounted) return;
      setState(() {
        _camera = controller;
        _cameraReady = true;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() => _cameraError =
          'The camera could not be started. Check camera permissions and try again.');
    }
  }

  @override
  void dispose() {
    _camera?.dispose();
    super.dispose();
  }

  Future<void> _capture() async {
    final camera = _camera;
    if (camera == null || !camera.value.isInitialized) return;

    setState(() => _analysing = true);
    try {
      final file = await camera.takePicture();
      final bytes = Uint8List.fromList(await file.readAsBytes());
      await widget.controller.captureEye(eyeSide: _activeEye, bytes: bytes);
    } on WorkflowException catch (error) {
      _showMessage(error.message);
    } catch (_) {
      _showMessage(
        'We could not complete the capture. Your previous work is safely stored '
        'on this device.',
      );
    } finally {
      if (mounted) setState(() => _analysing = false);
    }
  }

  void _showMessage(String message) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(message)));
  }

  Future<void> _confirmCancel() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Cancel this screening?'),
        content: const Text(
          'Images already captured stay on this device. You can start a new '
          'screening for this patient at any time.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('Keep screening'),
          ),
          TextButton(
            onPressed: () => Navigator.of(context).pop(true),
            child: const Text('Cancel screening'),
          ),
        ],
      ),
    );

    if (confirmed ?? false) {
      await widget.controller.cancel();
      if (mounted) Navigator.of(context).pop();
    }
  }

  @override
  Widget build(BuildContext context) {
    final controller = widget.controller;
    final quality = controller.qualityFor(_activeEye);
    final failed = quality != null && !quality.isAcceptable;

    return Scaffold(
      appBar: AppBar(
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('Screening', style: TextStyle(fontSize: 16)),
            Text(
              widget.patientName,
              style: const TextStyle(fontSize: 12, color: RsColors.inkSubtle),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () {
              controller.saveAndExit();
              Navigator.of(context).pop();
            },
            child: const Text('Save & exit'),
          ),
        ],
      ),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.all(RsSpacing.md),
          children: [
            _EyeSelector(
              active: _activeEye,
              leftDone: controller.qualityFor(EyeSide.left)?.isAcceptable ?? false,
              rightDone: controller.qualityFor(EyeSide.right)?.isAcceptable ?? false,
              onChanged: (eye) => setState(() => _activeEye = eye),
            ),
            const SizedBox(height: RsSpacing.md),

            // ---- viewfinder ----
            ClipRRect(
              borderRadius: BorderRadius.circular(18),
              child: AspectRatio(
                aspectRatio: 1,
                child: Stack(
                  fit: StackFit.expand,
                  children: [
                    Container(color: RsColors.vitreous),
                    if (_cameraReady && _camera != null)
                      FittedBox(
                        fit: BoxFit.cover,
                        child: SizedBox(
                          width: _camera!.value.previewSize?.height ?? 1,
                          height: _camera!.value.previewSize?.width ?? 1,
                          child: CameraPreview(_camera!),
                        ),
                      )
                    else
                      Center(
                        child: Padding(
                          padding: const EdgeInsets.all(RsSpacing.lg),
                          child: Text(
                            _cameraError ?? 'Starting camera…',
                            textAlign: TextAlign.center,
                            style: const TextStyle(color: Colors.white70),
                          ),
                        ),
                      ),
                    CaptureReticle(hasFailed: failed),
                    if (_analysing) const ScanningIndicator(),
                    Positioned(
                      left: 12,
                      top: 12,
                      child: Container(
                        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                        decoration: BoxDecoration(
                          color: Colors.black54,
                          borderRadius: BorderRadius.circular(6),
                        ),
                        child: Text(
                          _activeEye.label.toUpperCase(),
                          style: const TextStyle(
                            color: Colors.white,
                            fontSize: 10,
                            letterSpacing: 1.1,
                            fontWeight: FontWeight.w800,
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),

            const SizedBox(height: RsSpacing.md),

            // ---- instrument readouts ----
            Row(
              children: [
                QualityReadout(
                  label: 'Align',
                  score: quality?.framingScore,
                  analysing: _analysing,
                ),
                const SizedBox(width: RsSpacing.sm),
                QualityReadout(
                  label: 'Light',
                  score: quality?.lightingScore,
                  analysing: _analysing,
                ),
                const SizedBox(width: RsSpacing.sm),
                QualityReadout(
                  label: 'Focus',
                  score: quality?.blurScore,
                  analysing: _analysing,
                ),
              ],
            ),

            const SizedBox(height: RsSpacing.md),

            if (failed) _RetakeGuidance(quality: quality),
            if (quality != null && quality.isAcceptable)
              _AcceptedBanner(score: quality.overallScore),

            const SizedBox(height: RsSpacing.md),

            ElevatedButton(
              onPressed: _analysing || !_cameraReady ? null : _capture,
              child: Text(_analysing ? 'Checking quality…' : 'Capture'),
            ),
            const SizedBox(height: RsSpacing.sm),

            if (controller.canRunScreening)
              ElevatedButton(
                onPressed: _analysing
                    ? null
                    : () async {
                        await controller.submitForScreening();
                        if (context.mounted) Navigator.of(context).pop();
                      },
                child: const Text('Finish and queue for screening'),
              ),

            const SizedBox(height: RsSpacing.sm),
            OutlinedButton(
              onPressed: _confirmCancel,
              child: const Text('Cancel screening'),
            ),
          ],
        ),
      ),
    );
  }
}

class _EyeSelector extends StatelessWidget {
  const _EyeSelector({
    required this.active,
    required this.leftDone,
    required this.rightDone,
    required this.onChanged,
  });

  final EyeSide active;
  final bool leftDone;
  final bool rightDone;
  final ValueChanged<EyeSide> onChanged;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        for (final eye in EyeSide.values) ...[
          Expanded(
            child: GestureDetector(
              onTap: () => onChanged(eye),
              child: NeumorphicPanel(
                sunken: active != eye,
                padding: const EdgeInsets.symmetric(vertical: 14),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    if (eye == EyeSide.left ? leftDone : rightDone) ...[
                      const Icon(Icons.check, size: 16, color: RsColors.ok),
                      const SizedBox(width: 6),
                    ],
                    Text(
                      eye == EyeSide.left ? 'Left eye' : 'Right eye',
                      style: TextStyle(
                        fontWeight: FontWeight.w700,
                        color: active == eye ? RsColors.accent : RsColors.inkMuted,
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
          if (eye == EyeSide.left) const SizedBox(width: RsSpacing.sm),
        ],
      ],
    );
  }
}

class _RetakeGuidance extends StatelessWidget {
  const _RetakeGuidance({required this.quality});

  final QualityAssessment? quality;

  @override
  Widget build(BuildContext context) {
    final recommendations = quality?.recommendations ?? const <String>[];

    return Container(
      padding: const EdgeInsets.all(RsSpacing.md),
      decoration: BoxDecoration(
        color: RsColors.danger.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: RsColors.danger.withValues(alpha: 0.45)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'IMAGE NOT SUITABLE FOR ANALYSIS',
            style: TextStyle(
              color: RsColors.danger,
              fontWeight: FontWeight.w800,
              fontSize: 12,
              letterSpacing: 0.9,
            ),
          ),
          const SizedBox(height: RsSpacing.sm),
          for (final tip in recommendations)
            Padding(
              padding: const EdgeInsets.only(bottom: 4),
              child: Text('• $tip', style: const TextStyle(fontSize: 14, height: 1.35)),
            ),
        ],
      ),
    );
  }
}

class _AcceptedBanner extends StatelessWidget {
  const _AcceptedBanner({required this.score});

  final double score;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        const Icon(Icons.check_circle_outline, color: RsColors.ok, size: 18),
        const SizedBox(width: RsSpacing.sm),
        Text(
          'Image quality accepted (${(score * 100).round()}%).',
          style: const TextStyle(color: RsColors.ok, fontWeight: FontWeight.w600),
        ),
      ],
    );
  }
}
