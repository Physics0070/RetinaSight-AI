/// Domain vocabulary, mirroring the backend enums so both sides agree on the
/// meaning of every state and grade.
library;

enum EyeSide { left, right }

extension EyeSideX on EyeSide {
  String get value => name;

  String get label => this == EyeSide.left ? 'Left eye (OS)' : 'Right eye (OD)';

  static EyeSide parse(String raw) =>
      EyeSide.values.firstWhere((e) => e.name == raw, orElse: () => EyeSide.left);
}

/// The five-class diabetic retinopathy grading scale.
enum ScreeningCategory { noDr, mild, moderate, severe, proliferative }

extension ScreeningCategoryX on ScreeningCategory {
  String get value => switch (this) {
        ScreeningCategory.noDr => 'no_dr',
        ScreeningCategory.mild => 'mild',
        ScreeningCategory.moderate => 'moderate',
        ScreeningCategory.severe => 'severe',
        ScreeningCategory.proliferative => 'proliferative',
      };

  String get clinicalLabel => switch (this) {
        ScreeningCategory.noDr => 'No DR detected',
        ScreeningCategory.mild => 'Mild NPDR',
        ScreeningCategory.moderate => 'Moderate NPDR',
        ScreeningCategory.severe => 'Severe NPDR',
        ScreeningCategory.proliferative => 'Proliferative DR',
      };
}

enum RiskLevel { low, moderate, high, urgent }

extension RiskLevelX on RiskLevel {
  String get value => name;

  /// Distinct glyph per level so severity never depends on colour alone.
  String get glyph => switch (this) {
        RiskLevel.low => '○',
        RiskLevel.moderate => '◐',
        RiskLevel.high => '◕',
        RiskLevel.urgent => '●',
      };

  String get label => switch (this) {
        RiskLevel.low => 'Low',
        RiskLevel.moderate => 'Moderate',
        RiskLevel.high => 'High',
        RiskLevel.urgent => 'Urgent',
      };

  static RiskLevel parse(String raw) =>
      RiskLevel.values.firstWhere((r) => r.name == raw, orElse: () => RiskLevel.moderate);
}

/// Mirrors the backend screening state machine.
enum ScreeningState {
  idle,
  patientSelected,
  captureLeftEye,
  captureRightEye,
  qualityCheck,
  retakeRequired,
  readyForInference,
  inferenceRunning,
  resultAvailable,
  explanationAvailable,
  referralPending,
  referralCreated,
  doctorReview,
  followUp,
  completed,
  cancelled,
  syncPending,
  synced,
  error,
}

extension ScreeningStateX on ScreeningState {
  String get value => switch (this) {
        ScreeningState.idle => 'idle',
        ScreeningState.patientSelected => 'patient_selected',
        ScreeningState.captureLeftEye => 'capture_left_eye',
        ScreeningState.captureRightEye => 'capture_right_eye',
        ScreeningState.qualityCheck => 'quality_check',
        ScreeningState.retakeRequired => 'retake_required',
        ScreeningState.readyForInference => 'ready_for_inference',
        ScreeningState.inferenceRunning => 'inference_running',
        ScreeningState.resultAvailable => 'result_available',
        ScreeningState.explanationAvailable => 'explanation_available',
        ScreeningState.referralPending => 'referral_pending',
        ScreeningState.referralCreated => 'referral_created',
        ScreeningState.doctorReview => 'doctor_review',
        ScreeningState.followUp => 'follow_up',
        ScreeningState.completed => 'completed',
        ScreeningState.cancelled => 'cancelled',
        ScreeningState.syncPending => 'sync_pending',
        ScreeningState.synced => 'synced',
        ScreeningState.error => 'error',
      };

  bool get isTerminal =>
      this == ScreeningState.completed || this == ScreeningState.cancelled;

  static ScreeningState parse(String raw) => ScreeningState.values.firstWhere(
        (s) => s.value == raw,
        orElse: () => ScreeningState.idle,
      );
}

enum SyncStatus { pending, uploading, synced, failed, retrying }

extension SyncStatusX on SyncStatus {
  String get value => name;

  static SyncStatus parse(String raw) =>
      SyncStatus.values.firstWhere((s) => s.name == raw, orElse: () => SyncStatus.pending);
}

enum SyncEntityType { patient, screeningSession, retinalImage }

extension SyncEntityTypeX on SyncEntityType {
  String get value => switch (this) {
        SyncEntityType.patient => 'patient',
        SyncEntityType.screeningSession => 'screening_session',
        SyncEntityType.retinalImage => 'retinal_image',
      };
}

/// Outcome of the on-device quality gate.
class QualityAssessment {
  const QualityAssessment({
    required this.isAcceptable,
    required this.overallScore,
    required this.blurScore,
    required this.lightingScore,
    required this.framingScore,
    required this.retinalVisibilityScore,
    this.issues = const [],
    this.recommendations = const [],
  });

  final bool isAcceptable;
  final double overallScore;
  final double blurScore;
  final double lightingScore;
  final double framingScore;
  final double retinalVisibilityScore;
  final List<String> issues;
  final List<String> recommendations;

  factory QualityAssessment.fromJson(Map<String, dynamic> json) => QualityAssessment(
        isAcceptable: json['is_acceptable'] as bool? ?? false,
        overallScore: (json['overall_score'] as num?)?.toDouble() ?? 0,
        blurScore: (json['blur_score'] as num?)?.toDouble() ?? 0,
        lightingScore: (json['lighting_score'] as num?)?.toDouble() ?? 0,
        framingScore: (json['framing_score'] as num?)?.toDouble() ?? 0,
        retinalVisibilityScore:
            (json['retinal_visibility_score'] as num?)?.toDouble() ?? 0,
        issues: (json['issues'] as List?)?.cast<String>() ?? const [],
        recommendations: (json['recommendations'] as List?)?.cast<String>() ?? const [],
      );

  Map<String, dynamic> toJson() => {
        'is_acceptable': isAcceptable,
        'overall_score': overallScore,
        'blur_score': blurScore,
        'lighting_score': lightingScore,
        'framing_score': framingScore,
        'retinal_visibility_score': retinalVisibilityScore,
        'issues': issues,
        'recommendations': recommendations,
      };
}

class Patient {
  const Patient({
    required this.localId,
    required this.fullName,
    this.serverId,
    this.patientCode,
    this.phone,
    this.hasDiabetes,
    this.screeningConsent = false,
  });

  final String localId;
  final String? serverId;
  final String fullName;
  final String? patientCode;
  final String? phone;
  final bool? hasDiabetes;
  final bool screeningConsent;

  Map<String, dynamic> toSyncPayload() => {
        'full_name': fullName,
        'patient_code': patientCode,
        'phone': phone,
        'has_diabetes': hasDiabetes,
        'consents': {'screening': screeningConsent},
      };
}

class ScreeningSession {
  const ScreeningSession({
    required this.localId,
    required this.patientLocalId,
    required this.state,
    this.serverId,
    this.patientServerId,
    this.syncStatus = SyncStatus.pending,
    this.createdAt,
  });

  final String localId;
  final String? serverId;
  final String patientLocalId;
  final String? patientServerId;
  final ScreeningState state;
  final SyncStatus syncStatus;
  final DateTime? createdAt;

  ScreeningSession copyWith({
    String? serverId,
    ScreeningState? state,
    SyncStatus? syncStatus,
    String? patientServerId,
  }) =>
      ScreeningSession(
        localId: localId,
        serverId: serverId ?? this.serverId,
        patientLocalId: patientLocalId,
        patientServerId: patientServerId ?? this.patientServerId,
        state: state ?? this.state,
        syncStatus: syncStatus ?? this.syncStatus,
        createdAt: createdAt,
      );
}

class SyncQueueItem {
  const SyncQueueItem({
    required this.localId,
    required this.entityType,
    required this.payload,
    this.serverId,
    this.status = SyncStatus.pending,
    this.attemptCount = 0,
    this.lastError,
  });

  final String localId;
  final SyncEntityType entityType;
  final Map<String, dynamic> payload;
  final String? serverId;
  final SyncStatus status;
  final int attemptCount;
  final String? lastError;
}
