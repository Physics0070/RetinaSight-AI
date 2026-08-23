/** Shared API contract types (mirrors the backend Pydantic schemas). */

export type RoleName = "admin" | "health_worker" | "doctor" | "patient";

export type ScreeningCategory =
  | "no_dr"
  | "mild"
  | "moderate"
  | "severe"
  | "proliferative";

export type RiskLevel = "low" | "moderate" | "high" | "urgent";

export type ReferralPriority = "routine" | "consultation" | "urgent";

export type EyeSide = "left" | "right";

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export interface ApiErrorBody {
  error: { code: string; message: string; details?: Record<string, unknown> };
}

export interface AuthenticatedUser {
  id: string;
  email: string;
  full_name: string;
  status: string;
  roles: RoleName[];
  permissions: string[];
  clinic_id: string | null;
  patient_id: string | null;
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export interface LoginResponse {
  tokens: TokenPair;
  user: AuthenticatedUser;
}

export interface UserDetail {
  id: string;
  email: string;
  full_name: string;
  phone: string | null;
  status: string;
  last_active_at: string | null;
  created_at: string;
  roles: string[];
  permissions: string[];
  clinic_id: string | null;
  clinic_name: string | null;
}

export interface Patient {
  id: string;
  patient_code: string;
  full_name: string;
  date_of_birth: string | null;
  sex: string | null;
  phone: string | null;
  has_diabetes: boolean | null;
  diabetes_duration_years: number | null;
  clinic_id: string | null;
  created_at: string;
}

export interface Consent {
  id: string;
  consent_type: string;
  granted: boolean;
  granted_at: string | null;
  created_at: string;
}

export interface RetinalImage {
  id: string;
  session_id: string;
  patient_id: string;
  eye_side: EyeSide;
  capture_index: number;
  mime_type: string;
  file_size: number;
  checksum: string | null;
  width: number | null;
  height: number | null;
  is_active: boolean;
  created_at: string;
}

export interface RetinalImageWithUrl extends RetinalImage {
  url: string;
  url_expires_in: number;
}

export interface QualityAssessment {
  id: string;
  image_id: string;
  session_id: string;
  is_acceptable: boolean;
  result: string;
  overall_score: number;
  blur_score: number;
  lighting_score: number;
  framing_score: number;
  retinal_visibility_score: number;
  issues: string[];
  recommendations: string[];
  assessed_on_device: boolean;
  created_at: string;
}

export interface InferenceResult {
  id: string;
  session_id: string;
  image_id: string | null;
  status: string;
  eye_side: EyeSide | null;
  category: ScreeningCategory | null;
  confidence: number | null;
  class_probabilities: Record<string, number>;
  model_version: string | null;
  inference_mode: string | null;
  is_development_model: boolean;
  duration_ms: number | null;
  error_message: string | null;
  created_at: string;
}

export interface AffectedRegion {
  region: string;
  intensity: number;
  bounds: { x: number; y: number; width: number; height: number };
}

export interface Explanation {
  id: string;
  inference_result_id: string;
  method: string;
  affected_regions: AffectedRegion[];
  model_version: string | null;
  is_development_model: boolean;
  created_at: string;
  heatmap_url: string | null;
  overlay_url: string | null;
  caveat: string;
}

export interface RiskAssessment {
  id: string;
  session_id: string;
  risk_level: RiskLevel;
  priority: string;
  reason: string;
  recommended_action: string;
  requires_clinician_review: boolean;
  rule_id: string | null;
  created_at: string;
}

export interface Referral {
  id: string;
  session_id: string;
  patient_id: string;
  to_clinic_id: string | null;
  assigned_doctor_id: string | null;
  priority: ReferralPriority;
  status: string;
  reason: string;
  acknowledged_at: string | null;
  created_at: string;
}

export interface ScreeningSession {
  id: string;
  local_id: string | null;
  patient_id: string;
  clinic_id: string | null;
  conducted_by_user_id: string | null;
  state: string;
  started_at: string | null;
  completed_at: string | null;
  cancelled_reason: string | null;
  sync_status: string;
  captured_offline: boolean;
  created_at: string;
}

export interface ScreeningSessionDetail extends ScreeningSession {
  state_label: string;
  available_transitions: string[];
  is_terminal: boolean;
  patient: Patient | null;
  images: RetinalImage[];
  quality: QualityAssessment[];
  results: InferenceResult[];
  risk: RiskAssessment | null;
  referral: Referral | null;
}

export interface CaptureResponse {
  image: RetinalImage;
  quality: QualityAssessment;
  retake_required: boolean;
  session_state: string;
  state_label: string;
}

export interface ModelStatus {
  model_version: string;
  framework: string;
  is_development_model: boolean;
  input_size: number[];
  classes: string[];
  available: boolean;
  supports_gradcam: boolean;
  source: string;
  validation_status: string;
  validation_metrics: Record<string, unknown>;
  clinically_validated: boolean;
}

export interface InferenceRunResponse {
  results: InferenceResult[];
  worst: InferenceResult | null;
  risk: RiskAssessment | null;
  quality_blocked: string[];
  model_status: ModelStatus;
  disclaimer: string;
}

export interface ClinicalReview {
  id: string;
  session_id: string;
  patient_id: string;
  referral_id: string | null;
  reviewer_user_id: string | null;
  status: string;
  decision: string | null;
  clinician_category: ScreeningCategory | null;
  agrees_with_ai: boolean | null;
  notes: string | null;
  reviewed_at: string | null;
  created_at: string;
}

export interface RiskQueueItem {
  review: ClinicalReview;
  session: ScreeningSession;
  patient: Patient;
  risk: RiskAssessment | null;
  worst_result: InferenceResult | null;
  quality_acceptable: boolean;
}

export interface FollowUp {
  id: string;
  patient_id: string;
  session_id: string | null;
  review_id: string | null;
  due_date: string;
  status: string;
  instructions: string | null;
  completed_at: string | null;
  created_at: string;
}

export interface Clinic {
  id: string;
  name: string;
  code: string;
  location: string;
  region: string | null;
  status: string;
  connectivity_status: string;
  created_at: string;
  health_worker_count: number;
  doctor_count: number;
  screening_count: number;
  pending_referrals: number;
}

export interface ModelMetadata {
  id: string;
  name: string;
  version: string;
  framework: string;
  deployment_target: string;
  architecture: string | null;
  input_width: number;
  input_height: number;
  classes: string[];
  model_path: string | null;
  status: string;
  validation_status: string;
  validation_metrics: Record<string, unknown>;
  notes: string | null;
  created_at: string;
}

export interface ConfigurationEntry {
  id: string;
  key: string;
  value: Record<string, unknown>;
  category: string;
  description: string;
  is_editable: boolean;
  version: number;
  updated_at: string;
}

export interface AuditLogEntry {
  id: string;
  actor_user_id: string | null;
  actor_email: string | null;
  actor_role: string | null;
  action: string;
  resource_type: string | null;
  resource_id: string | null;
  result: string;
  ip_address: string | null;
  context: Record<string, unknown>;
  created_at: string;
}

export interface AdminDashboard {
  users: {
    total: number;
    active: number;
    health_workers: number;
    doctors: number;
    patients: number;
  };
  patients: { total: number };
  clinics: { total: number; active: number };
  screenings: {
    total: number;
    completed: number;
    in_progress: number;
    captured_offline: number;
  };
  reviews: { pending: number; in_review: number; completed: number };
  referrals: { total: number; pending: number };
  follow_ups: { total: number; due: number };
  sync: { pending: number; failed: number };
  model: ModelStatus;
}

export interface SystemHealth {
  database: { ok: boolean; engine: string };
  storage: { ok: boolean; provider: string };
  model: {
    ok: boolean;
    version: string;
    development: boolean;
    validation_status: string;
  };
  environment: string;
}

export interface SyncQueueEntry {
  id: string;
  local_id: string;
  server_id: string | null;
  entity_type: string;
  operation: string;
  status: string;
  attempt_count: number;
  last_attempt_at: string | null;
  last_error: string | null;
  device_id: string | null;
  created_at: string;
}
