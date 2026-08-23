/// Screening workflow controller.
///
/// Owns the state machine on the device, mirroring the server's transition
/// table. Everything is written locally first and queued for sync, so the whole
/// workflow completes with no connectivity at all.
library;

// Uint8List comes through foundation.dart; importing dart:typed_data as well
// would be redundant.
import 'package:flutter/foundation.dart';

import '../data/local_store.dart';
import '../domain/models.dart';
import 'quality_gate.dart';

/// Legal transitions — kept in step with
/// backend/app/services/screening_state_machine.py.
const Map<ScreeningState, Set<ScreeningState>> kTransitions = {
  ScreeningState.idle: {ScreeningState.patientSelected, ScreeningState.cancelled},
  ScreeningState.patientSelected: {
    ScreeningState.captureLeftEye,
    ScreeningState.captureRightEye,
    ScreeningState.cancelled,
  },
  ScreeningState.captureLeftEye: {
    ScreeningState.qualityCheck,
    ScreeningState.captureRightEye,
    ScreeningState.readyForInference,
    ScreeningState.cancelled,
    ScreeningState.error,
  },
  ScreeningState.captureRightEye: {
    ScreeningState.qualityCheck,
    ScreeningState.captureLeftEye,
    ScreeningState.readyForInference,
    ScreeningState.cancelled,
    ScreeningState.error,
  },
  ScreeningState.qualityCheck: {
    ScreeningState.retakeRequired,
    ScreeningState.readyForInference,
    ScreeningState.captureLeftEye,
    ScreeningState.captureRightEye,
    ScreeningState.cancelled,
    ScreeningState.error,
  },
  ScreeningState.retakeRequired: {
    ScreeningState.captureLeftEye,
    ScreeningState.captureRightEye,
    ScreeningState.cancelled,
  },
  ScreeningState.readyForInference: {
    ScreeningState.inferenceRunning,
    ScreeningState.captureLeftEye,
    ScreeningState.captureRightEye,
    ScreeningState.cancelled,
  },
  ScreeningState.inferenceRunning: {
    ScreeningState.resultAvailable,
    ScreeningState.error,
    ScreeningState.cancelled,
  },
  ScreeningState.resultAvailable: {
    ScreeningState.explanationAvailable,
    ScreeningState.referralPending,
    ScreeningState.syncPending,
    ScreeningState.completed,
    ScreeningState.cancelled,
  },
  ScreeningState.explanationAvailable: {
    ScreeningState.referralPending,
    ScreeningState.syncPending,
    ScreeningState.completed,
    ScreeningState.cancelled,
  },
  ScreeningState.referralPending: {
    ScreeningState.referralCreated,
    ScreeningState.completed,
    ScreeningState.cancelled,
  },
  ScreeningState.referralCreated: {
    ScreeningState.syncPending,
    ScreeningState.doctorReview,
    ScreeningState.completed,
    ScreeningState.cancelled,
  },
  ScreeningState.syncPending: {
    ScreeningState.synced,
    ScreeningState.error,
    ScreeningState.cancelled,
  },
  ScreeningState.synced: {ScreeningState.doctorReview, ScreeningState.completed},
  ScreeningState.doctorReview: {ScreeningState.followUp, ScreeningState.completed},
  ScreeningState.followUp: {ScreeningState.completed},
  ScreeningState.error: {
    ScreeningState.captureLeftEye,
    ScreeningState.captureRightEye,
    ScreeningState.syncPending,
    ScreeningState.cancelled,
  },
  ScreeningState.completed: {},
  ScreeningState.cancelled: {},
};

bool canTransition(ScreeningState from, ScreeningState to) =>
    kTransitions[from]?.contains(to) ?? false;

class WorkflowException implements Exception {
  const WorkflowException(this.message);
  final String message;

  @override
  String toString() => message;
}

class CaptureOutcome {
  const CaptureOutcome({
    required this.quality,
    required this.retakeRequired,
    required this.state,
  });

  final QualityAssessment quality;
  final bool retakeRequired;
  final ScreeningState state;
}

class ScreeningController extends ChangeNotifier {
  ScreeningController({
    required LocalStore store,
    QualityGate? qualityGate,
    String Function()? idGenerator,
  })  : _store = store,
        _qualityGate = qualityGate ?? const QualityGate(),
        _newId = idGenerator ?? _defaultId;

  final LocalStore _store;
  final QualityGate _qualityGate;
  final String Function() _newId;

  ScreeningSession? _session;
  final Map<EyeSide, QualityAssessment> _quality = {};

  ScreeningSession? get session => _session;
  ScreeningState get state => _session?.state ?? ScreeningState.idle;
  QualityAssessment? qualityFor(EyeSide eye) => _quality[eye];

  bool get canRunScreening =>
      _quality.values.any((assessment) => assessment.isAcceptable);

  bool get bothEyesAccepted =>
      (_quality[EyeSide.left]?.isAcceptable ?? false) &&
      (_quality[EyeSide.right]?.isAcceptable ?? false);

  // ------------------------------------------------------------------ //
  Future<ScreeningSession> startScreening(Patient patient) async {
    if (!patient.screeningConsent) {
      throw const WorkflowException(
        'Screening consent has not been recorded for this patient.',
      );
    }

    final session = ScreeningSession(
      localId: _newId(),
      patientLocalId: patient.localId,
      patientServerId: patient.serverId,
      state: ScreeningState.patientSelected,
      createdAt: DateTime.now().toUtc(),
    );

    await _store.saveSession(session);
    await _store.enqueue(
      localId: session.localId,
      entityType: SyncEntityType.screeningSession,
      payload: {
        'patient_id': patient.serverId,
        'patient_local_id': patient.localId,
      },
    );

    _session = session;
    _quality.clear();
    notifyListeners();
    return session;
  }

  Future<void> _moveTo(ScreeningState target) async {
    final current = _session;
    if (current == null) throw const WorkflowException('No screening is open.');
    if (!canTransition(current.state, target)) {
      throw WorkflowException(
        'That action is not available at this step (${current.state.value}).',
      );
    }
    _session = current.copyWith(state: target);
    await _store.updateSessionState(current.localId, target);
    notifyListeners();
  }

  // ------------------------------------------------------------------ //
  /// Capture one eye: quality-gate locally, store, then queue for upload.
  Future<CaptureOutcome> captureEye({
    required EyeSide eyeSide,
    required Uint8List bytes,
  }) async {
    final current = _session;
    if (current == null) throw const WorkflowException('No screening is open.');
    if (current.state.isTerminal) {
      throw const WorkflowException('This screening is closed and cannot be changed.');
    }

    final captureState =
        eyeSide == EyeSide.left ? ScreeningState.captureLeftEye : ScreeningState.captureRightEye;
    if (current.state != captureState) await _moveTo(captureState);

    await _moveTo(ScreeningState.qualityCheck);

    final assessment = _qualityGate.assess(bytes);
    _quality[eyeSide] = assessment;

    final captureId = _newId();
    await _store.saveCapture(
      localId: captureId,
      sessionLocalId: current.localId,
      eyeSide: eyeSide,
      bytes: bytes,
      quality: assessment,
    );

    if (assessment.isAcceptable) {
      // Only images that pass the gate are worth uploading.
      await _store.enqueue(
        localId: captureId,
        entityType: SyncEntityType.retinalImage,
        payload: {
          'session_local_id': current.localId,
          'session_id': current.serverId,
          'eye_side': eyeSide.value,
          'file_path': '',
          'quality': assessment.toJson(),
        },
      );

      await _moveTo(
        bothEyesAccepted
            ? ScreeningState.readyForInference
            : (eyeSide == EyeSide.left
                ? ScreeningState.captureRightEye
                : ScreeningState.captureLeftEye),
      );
    } else {
      await _moveTo(ScreeningState.retakeRequired);
    }

    return CaptureOutcome(
      quality: assessment,
      retakeRequired: !assessment.isAcceptable,
      state: state,
    );
  }

  Future<void> requestRetake(EyeSide eyeSide) async {
    _quality.remove(eyeSide);
    await _moveTo(
      eyeSide == EyeSide.left
          ? ScreeningState.captureLeftEye
          : ScreeningState.captureRightEye,
    );
  }

  /// Proceed with the acceptable captures obtained so far (single-eye path).
  Future<void> markReadyForInference() async {
    if (!canRunScreening) {
      throw const WorkflowException('No image has passed the quality gate yet.');
    }
    if (state != ScreeningState.readyForInference) {
      await _moveTo(ScreeningState.readyForInference);
    }
  }

  /// On-device inference is not performed unless a validated exported model is
  /// present. The device queues the screening and the server produces the
  /// result — no placeholder output is ever shown as a screening result.
  Future<void> submitForScreening() async {
    await markReadyForInference();
    await _moveTo(ScreeningState.inferenceRunning);
    await _moveTo(ScreeningState.resultAvailable);
    await _moveTo(ScreeningState.syncPending);
  }

  // ---- exit points: always available while the screening is open ---- //
  Future<void> cancel({String? reason}) async {
    await _moveTo(ScreeningState.cancelled);
  }

  Future<void> complete() async {
    await _moveTo(ScreeningState.completed);
  }

  /// Leave the screening resumable — nothing is discarded.
  void saveAndExit() {
    notifyListeners();
  }

  static String _defaultId() =>
      '${DateTime.now().microsecondsSinceEpoch}-${identityHashCode(Object())}';
}
