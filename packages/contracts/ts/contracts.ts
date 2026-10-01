// Sinh tự động từ JSON Schema của pydantic — chạy `make contracts`.
// KHÔNG sửa tay: nguồn sự thật là packages/contracts/src/ca_contracts.

export type JsonValue = string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue };

export interface NhanVien {
  id: string;
  ten: string;
  ky_nang?: string[];
  la_sinh_vien?: boolean;
  so_dien_thoai_hash?: string | null;
}

export interface Ca {
  id: string;
  ngay: string;
  bat_dau: string;
  ket_thuc: string;
  vi_tri: string;
  so_nguoi_toi_thieu?: number;
}

export interface LichTuan {
  tuan_iso: string;
  trang_thai?: "may_sinh" | "nhap" | "dang_giai" | "cho_duyet" | "da_duyet" | "da_cong_bo" | "da_dong";
  phan_cong?: Record<string, string[]>;
}

export type MinhChungLoai = "khong" | "so" | "anh" | "kiem_ke" | "van_ban" | "danh_sach" | "xac_nhan" | "xac_nhan_doc";

export interface PhieuBuoc {
  ma: string;
  ten: string;
  minh_chung?: MinhChungLoai;
}

export interface PhieuMau {
  ma: string;
  ten: string;
  gan_voi?: string | null;
  buoc: PhieuBuoc[];
}

export interface RangBuocTrichXuat {
  id: string;
  nguon: "tkb" | "tin_nhan" | "ban_giao" | "khac";
  nhan_vien_id?: string | null;
  noi_dung: string;
  do_tin_cay: number;
  trang_thai?: "cho_duyet" | "da_duyet" | "tu_choi";
  khung_gio?: string[];
}

export interface MonNuoc {
  id: string;
  ten: string;
  gia: number;
  an?: boolean;
  hinh_url?: string;
  nhom?: string;
  bom?: Record<string, number>;
}

export interface DongDon {
  mon_id: string;
  ten: string;
  so_luong: number;
  gia: number;
}

export interface DonQuay {
  id: string;
  nv_id: string;
  trang_thai?: "cho_pha" | "dang_pha" | "xong" | "huy";
  thanh_toan?: "tien_mat" | "da_ck" | "chua_thu";
  dong: DongDon[];
  ly_do_huy?: string | null;
  nguon?: string;
  luc?: string;
}

export interface ActionItem {
  id: string;
  tieu_de: string;
  noi_dung_chi_tiet?: string;
  tinh_chat?: "bat_buoc" | "tuy_chon" | "khuyen_khich";
  ten_nguoi_giao?: string;
  nhan_vien_id?: string | null;
  ten_nguoi_nhan: string;
  pham_vi?: "ca_nhan" | "nhom";
  thoi_gian_bat_dau?: string;
  han_chot?: string;
  muc_do_uu_tien?: "cao" | "trung_binh" | "thap";
  do_tin_cay?: number;
  da_chon?: boolean;
  loai_cong_viec?: "1_ca" | "nhieu_ca" | "gop_y";
  ca_thuc_hien?: string;
  ca_du_kien?: string[];
  can_lam_ro?: boolean;
  van_de_ngu_canh?: string;
  cau_hoi_lam_ro?: string;
  goi_y_xu_ly?: string[];
  stt_near_miss?: boolean;
  khong_co_can_cu?: boolean;
  nguon_cau_noi?: string;
}

export interface AuditTuanThuSop {
  diem_tuan_thu?: number;
  xep_hang?: "A" | "B" | "C" | "D";
  tieu_chi?: TieuChiAudit[];
  canh_bao_do?: string[];
  nhan_xet_chung?: string;
}

export interface BanTinCaKhan {
  ban_vip?: string[];
  luu_y_di_ung_khach?: string[];
  su_co_thiet_bi_khan?: string[];
  danh_sach_mon_86?: string[];
  noi_dung_tin_nhan_gui_nhom?: string;
}

export interface DeXuatPheDuyet {
  id: string;
  loai_de_xuat?: "quy_trinh_sop" | "mua_sam_vat_tu" | "chinh_sach_nhan_su" | "dieu_chinh_lich" | "khac";
  tieu_de: string;
  nguoi_de_xuat?: string;
  nguoi_phe_duyet?: string;
  noi_dung: string;
  ly_do?: string;
  trang_thai?: "da_duyet" | "cho_duyet" | "tu_choi";
  quy_trinh_lien_quan?: string | null;
  buoc_so?: number | null;
  chi_tiet_lich?: DieuChinhLichHop | null;
}

export interface DeXuatSop {
  quy_trinh_lien_quan: string;
  buoc_so?: number | null;
  noi_dung_thay_doi: string;
  ly_do?: string;
}

export interface DieuChinhLichHop {
  id?: string;
  nhan_vien_id?: string | null;
  ten_nhan_vien?: string;
  loai?: "xin_nghi" | "ghim_ca" | "doi_ca" | "uu_tien";
  thu?: string;
  khung?: string;
  ca_id?: string;
  tuan_iso?: string;
  ly_do?: string;
  trang_thai?: "cho_duyet" | "da_duyet" | "tu_choi";
}

export interface DoanThoaiTranscript {
  nguoi_noi: string;
  bat_dau_s?: number | null;
  ket_thuc_s?: number | null;
  noi_dung: string;
}

export interface GopYLuuY {
  id: string;
  nguoi_gop_y?: string;
  nguoi_nhan?: string;
  chu_de?: "thai_do_phuc_vu" | "ky_nang_pha_che" | "ve_sinh_an_toan" | "dong_vien_khen_ngoi" | "luu_y_chung";
  tinh_chat?: "nhac_nho" | "khen_ngoi" | "kinh_nghiem" | "gop_y";
  noi_dung: string;
  ghi_chu?: string;
}

export interface HuanLuyenQuanLy {
  ty_le_noi_quan_ly_pct?: number;
  ty_le_noi_nhan_vien_pct?: number;
  diem_tuong_tac_2_chieu?: number;
  diem_truyen_cam_hung?: number;
  phong_cach_dieu_hanh?: string;
  loi_khuyen_ai_coaching?: string[];
}

export interface TieuChiAudit {
  ma: string;
  ten_tieu_chi: string;
  dat?: boolean;
  chi_tiet?: string;
}

export interface CuocHop {
  id: string;
  tieu_de: string;
  loai_hop?: "giao_ca" | "hop_tuan" | "dao_tao" | "khac";
  thoi_gian?: string;
  nguon_am_thanh?: "google_meet_tab" | "microphone" | "file_upload" | "ghi_chep_tay";
  transcript_thoai?: DoanThoaiTranscript[];
  tom_tat: string;
  quyet_dinh?: string[];
  de_xuat_phe_duyet?: DeXuatPheDuyet[];
  action_items?: ActionItem[];
  gop_y_luu_y?: GopYLuuY[];
  dieu_chinh_lich?: DieuChinhLichHop[];
  audit_sop?: AuditTuanThuSop | null;
  ban_tin_ca?: BanTinCaKhan | null;
  huan_luyen_quan_ly?: HuanLuyenQuanLy | null;
  de_xuat_sop?: DeXuatSop[];
  do_tin_cay_tong_the?: number;
  trang_thai?: "cho_duyet" | "da_duyet" | "tu_choi";
  phien_ban?: number;
  last_modified_at?: string;
  ngay_ghi_am?: string;
}

export interface CopilotContext {
  store_id?: string;
  user_id: string;
  user_role: "chu_quan" | "quan_ly" | "nhan_vien";
  active_date: string;
  channel?: "web" | "telegram" | "zalo";
  recent_messages?: string[];
}

export interface CopilotMessage {
  message: string;
  context: CopilotContext;
}

export type ActionProposalStatus = "draft" | "ready_for_approval" | "amendment_ready" | "executing" | "executed" | "execution_failed" | "rejected" | "expired" | "stale_rejected";

export type CopilotIntent = "SCHEDULE_SOLVE" | "APPROVE_SHIFT_SWAP" | "GENERATE_DAILY_BRIEF" | "QUERY_SOP" | "ANALYZE_WASTE" | "CREATE_RULE_PROPOSAL" | "INVENTORY_RESTOCK_CHECK" | "SEND_MAIL" | "GET_MY_PROFILE" | "LIST_STAFF" | "QUERY_MENU" | "GET_INVENTORY" | "GET_SHIFT_SWAPS" | "GET_HANGING_TASKS" | "GET_HANDOVERS" | "PROPOSE_HANGING_TASK" | "PROPOSE_TASK_COMPLETE" | "PROPOSE_CONSUMPTION_RECORD" | "PROPOSE_TIME_OFF" | "PROPOSE_MENU_UPDATE" | "PROPOSE_ORDER_TRANSITION" | "PROPOSE_PIN" | "GET_PAGE_STATUS" | "PROPOSE_PAGE_SYNC" | "PROPOSE_PAGE_DRAFT" | "PROPOSE_TKB_CONFIRM" | "PROPOSE_SWAP_CONSENT" | "PROPOSE_HANDOVER" | "GET_SCHEDULE" | "GET_MY_SHIFTS" | "GET_CONSTRAINT_CANDIDATES" | "RUN_CATCHMENT_SURVEY" | "GET_SERPAPI_QUOTA" | "GET_SURVEY_RESULT" | "QUERY_AUDIT" | "QUERY_QUANVERSE" | "OUT_OF_SCOPE";

export interface ActionProposal {
  action_id: string;
  intent: CopilotIntent;
  status?: ActionProposalStatus;
  summary: string;
  explanation?: string;
  payload_diff?: Record<string, JsonValue>;
  requires_confirmation?: boolean;
  store_id?: string;
  created_by: string;
  confidence?: number;
  data_snapshot_hash?: string;
  expires_at: string;
  created_at?: string;
  executed_at?: string | null;
  amended_from?: string | null;
}

export type FbPolicyAction = "auto_send" | "queue_review" | "priority_review" | "escalate_owner" | "block_polite" | "block_silent";

export interface PolicyDecision {
  action: FbPolicyAction;
  reason: string;
  intent: string;
  confidence: number;
  assigned_role?: "quan_ly" | "chu_quan" | null;
  sla_minutes?: number | null;
  flagged_reasons?: string[];
}

export interface AIGenerationDraft {
  subject?: string | null;
  body: string;
}

export interface AIModelVersion {
  provider: string;
  model_id: string;
  model_revision?: string | null;
  temperature: number;
  tool_context_hash: string;
}

export interface AIGenerationRecord {
  id: string;
  store_id: string;
  channel: "gmail" | "facebook";
  conversation_id?: string | null;
  request_kind: "gmail_request" | "facebook_message" | "facebook_comment";
  external_event_hash?: string | null;
  draft: AIGenerationDraft;
  context_snapshot_hash: string;
  verified_fact_refs?: string[];
  missing_context?: boolean;
  agent_version: string;
  prompt_version: string;
  rule_version: string;
  rollout_bucket: "control" | "canary_10" | "canary_50" | "active_100";
  model: AIModelVersion;
  policy_action: FbPolicyAction;
  idempotency_key: string;
  created_at: string;
}

export interface AIFeedbackContent {
  subject?: string | null;
  body?: string | null;
}

export interface AIFeedbackEvent {
  id: string;
  store_id: string;
  generation_id: string;
  channel: "gmail" | "facebook";
  type: "manager_approve" | "manager_edit" | "manager_reject" | "customer_positive" | "customer_negative" | "customer_followup" | "send_success" | "send_failure" | "manual_rating";
  original?: AIFeedbackContent | null;
  final?: AIFeedbackContent | null;
  edited_fields?: Array<"subject" | "body">;
  materially_edited?: boolean;
  actor_user_id?: string | null;
  actor_role: "chu_quan" | "quan_ly" | "system" | "customer";
  send_status?: "not_applicable" | "sent" | "failed";
  failure_code?: string | null;
  idempotency_key: string;
  created_at: string;
}

export interface AIEvaluationScores {
  accuracy: number;
  safety: number;
  completeness?: number | null;
  tone?: number | null;
  naturalness?: number | null;
  personalization?: number | null;
  actionability?: number | null;
  policy_compliance?: number | null;
  intent_fit?: number | null;
  emotional_fit?: number | null;
  resolution_likelihood?: number | null;
}

export interface AIEvaluation {
  id: string;
  store_id: string;
  generation_id: string;
  channel: "gmail" | "facebook";
  scores: AIEvaluationScores;
  aggregate_score: number;
  passed: boolean;
  action: FbPolicyAction;
  hard_fail_flags?: string[];
  flags?: string[];
  threshold_version: string;
  calibration_version: string;
  sample_count: number;
  evaluation_window: string;
  evaluator: string;
  idempotency_key: string;
  created_at: string;
}

export interface AIRuleDefinition {
  text: string;
  intent_scope: string[];
  audience_scope: string[];
  priority: number;
}

export interface AIRuleRollout {
  mode?: "none" | "canary" | "full";
  percentage?: number;
  min_sample?: number;
  start_at?: string | null;
  end_at?: string | null;
}

export interface AIRuleProposal {
  id: string;
  store_id: string;
  channel: "gmail" | "facebook";
  rule_type: "style" | "prompt" | "playbook" | "safety";
  rule: AIRuleDefinition;
  evidence_count: number;
  evidence_ids: string[];
  confidence: number;
  status?: "pending" | "conflict_pending" | "approved" | "active" | "paused" | "rolled_back" | "rejected";
  version: number;
  rollback_target_version?: number | null;
  rollout?: AIRuleRollout;
  approved_by?: string | null;
  approved_at?: string | null;
  rejection_reason?: string | null;
  idempotency_key: string;
  created_at: string;
  updated_at: string;
}

export interface TableReservation {
  id: string;
  store_id?: string;
  psid?: string;
  customer_name: string;
  phone: string;
  booking_time: string;
  party_size: number;
  duration_minutes?: number;
  table_ids?: string[];
  status?: "held" | "confirmed" | "seated" | "completed" | "cancelled" | "no_show" | "needs_review";
  source?: "ai_auto" | "staff_manual";
  notes?: string;
  idempotency_key?: string;
  notified_nv_id?: string | null;
  notification_acked_at?: string | null;
  cancelled_by?: string | null;
  cancelled_reason?: string | null;
  created_at?: string;
  updated_at?: string;
}

export interface SpatialAnchor {
  anchor_id: string;
  khu_vuc: string;
  label: string;
  x: number;
  y: number;
  z?: number;
  kind: string;
  active?: boolean;
}

export type ExperienceRole = "khach" | "nhan_vien" | "quan_ly" | "chu_quan";

export interface ExperienceEvent {
  event_id: string;
  event_type: string;
  occurred_at: string;
  actor_id?: string | null;
  role?: ExperienceRole | null;
  anchor_id?: string | null;
  payload?: Record<string, JsonValue>;
  evidence_refs?: string[];
  source: "replay" | "user" | "system" | "agent";
}

export interface VoiceTurn {
  turn_id: string;
  conversation_id: string;
  transcript: string;
  response_text?: string;
  audio_ref?: string | null;
  intent?: string | null;
  confidence?: number;
  proposal_id?: string | null;
}

export type MemoryConsentStatus = "required" | "granted" | "revoked" | "expired";

export type MemoryStatus = "draft" | "confirmed" | "superseded" | "deleted";

export type MemoryVisibility = "private" | "staff" | "manager" | "public";

export interface ExperienceMemory {
  memory_id: string;
  anchor_id?: string | null;
  owner_scope: string;
  content: string;
  source_event_ids?: string[];
  consent_status?: MemoryConsentStatus;
  visibility?: MemoryVisibility;
  status?: MemoryStatus;
  retention_until?: string | null;
  created_by?: string;
}

export type ExperienceProposalStatus = "draft" | "ready" | "confirmed" | "rejected" | "expired";

export interface ExperienceActionProposal {
  proposal_id: string;
  action_type: string;
  status?: ExperienceProposalStatus;
  snapshot_hash: string;
  evidence_refs?: string[];
  deterministic_result?: Record<string, JsonValue>;
  explanation?: string;
  requested_by: string;
  store_id?: string;
  created_at?: string;
  expires_at?: string | null;
}

export type WarRoomScenarioType = "demand_surge" | "add_staff_to_shift" | "remove_staff_from_shift" | "equipment_outage" | "heavy_rain" | "large_group_arrival";

export interface WarRoomScenario {
  scenario_id: string;
  loai: WarRoomScenarioType;
  tham_so?: Record<string, string | number | boolean>;
}

export interface WarRoomOption {
  option_id: string;
  scenario_id: string;
  input_assumptions?: Record<string, string | number | boolean>;
  outputs?: Record<string, number>;
  staffing?: Record<string, number>;
  load?: Record<string, number>;
  fairness_impact?: Record<string, number>;
  estimated_cost?: number | null;
  estimated_revenue?: number | null;
  risk?: string;
  evidence_refs?: string[];
  stale_data?: boolean;
  constraint_violations?: string[];
  labels?: Array<"mo_phong" | "uoc_tinh">;
}

export interface WarRoomComparison {
  simulation_id: string;
  baseline_snapshot_hash: string;
  baseline?: Record<string, JsonValue>;
  options?: WarRoomOption[];
}

export type PositiveRuleStatus = "de_xuat" | "qua_vf_rule" | "du_tap_su" | "hieu_luc" | "tu_choi" | "da_go";

export interface ShadowTestResult {
  before?: Record<string, number>;
  after?: Record<string, number>;
  diffs?: Record<string, number>;
  hard_constraints_ok?: boolean;
  fairness_delta?: number;
  workload_delta?: number;
  operational_delta?: number;
  notes?: string[];
}

export interface RuleCandidate {
  candidate_id: string;
  condition: Record<string, string | number | boolean>;
  effect: Record<string, string | number | boolean>;
  sentence: string;
  evidence_refs?: string[];
  counterexample_refs?: string[];
  confidence?: number;
  source_kind: "decision" | "rescue" | "twin" | "episode";
  playbook_status?: PositiveRuleStatus;
  shadow_result?: ShadowTestResult | null;
  rule_version?: string;
  created_from_snapshot_hash: string;
}

export interface RescueCandidate {
  candidate_id: string;
  nv_id: string;
  nv_ten?: string;
  safe?: boolean;
  reason_passes?: string[];
  reason_blocks?: string[];
  fairness_delta?: number;
  added_hours?: number;
  skill_coverage?: Record<string, boolean>;
}

export type RescueCaseStatus = "reported" | "resolving" | "candidates_ready" | "proposed" | "invited" | "responded" | "confirmed" | "expired" | "cancelled";

export interface RescueCase {
  case_id: string;
  store_id?: string;
  status?: RescueCaseStatus;
  absence_nv_id: string;
  shift_id: string;
  reported_by: string;
  schedule_snapshot_hash: string;
  candidates?: RescueCandidate[];
  selected_candidate_id?: string | null;
}

export interface ZoneProjection {
  zone_id: string;
  label: string;
  kind: string;
  active?: boolean;
  load_signal?: number;
}

export interface PublicEventProjection {
  event_id: string;
  event_type: string;
  status: string;
  occurred_at: string;
  source: "replay" | "user" | "system" | "agent";
  summary?: string;
  zone_id?: string | null;
}

export type ExperienceMode = "troi_mua" | "gio_cao_diem" | "khach_doan" | "thieu_nhan_su" | "quan_yen_tinh" | "dem_nhac";

export interface ModeProjection {
  mode: ExperienceMode;
  active?: boolean;
  proposed_by?: string | null;
  proposal_status?: ExperienceProposalStatus | null;
}

export interface HorizonItem {
  item_id: string;
  kind?: "event" | "signal" | "handover" | "mode_proposal";
  title: string;
  starts_at: string;
  source: "replay" | "user" | "system" | "agent";
}

export interface DataQualityNotice {
  code: string;
  level?: "info" | "warning" | "error";
  message: string;
}

export interface LivingCafeSnapshot {
  snapshot_id: string;
  store_id?: string;
  generated_at?: string;
  role: ExperienceRole;
  zones?: ZoneProjection[];
  events?: PublicEventProjection[];
  modes?: ModeProjection[];
  next_horizon?: HorizonItem[];
  data_quality?: DataQualityNotice[];
}

export interface QuanverseMetric {
  key: string;
  label: string;
  value?: number | null;
  unit?: string;
  tone?: "default" | "ok" | "warn" | "danger";
}

export type QuanversePage = "living_map" | "war_room" | "shift_rescue" | "rules" | "spatial_memory";

export interface QuanverseBrief {
  page: QuanversePage;
  headline: string;
  facts?: string[];
  metrics?: QuanverseMetric[];
  risks?: string[];
  next_actions?: string[];
  grounded_refs?: string[];
  data_quality?: DataQualityNotice[];
}

export interface QuanverseAskRequest {
  page: QuanversePage;
  question: string;
}

export interface QuanverseAskResponse {
  page: QuanversePage;
  question: string;
  answer: string;
  brief: QuanverseBrief;
  citations?: string[];
  unsupported_claims?: string[];
  grounded?: boolean;
  provider?: string;
}

export type LossBasis = "ke_hoach_kiem_ke" | "don_quay_thuc_te" | "hon_hop";

export type LossLevel = "dat" | "canh_bao" | "nghiem_trong" | "thieu_du_lieu";

export interface LossLine {
  mat_hang: string;
  ten?: string;
  don_vi?: string;
  ly_thuyet?: number | null;
  thuc_te?: number | null;
  lech?: number | null;
  ty_le_phan_tram?: number | null;
  muc_do?: LossLevel;
  nguong_phan_tram?: number;
  co_so?: LossBasis;
  thieu_ve?: string[];
  ghi_chu?: string;
}

export type LossCauseSource = "ghi_chu_ca" | "nguyen_nhan_ghi" | "hon_hop";

export interface LossCauseRank {
  nguyen_nhan: string;
  ten?: string;
  so_lan: number;
  mat_hang_lien_quan?: string[];
  ty_le_tong?: number;
  nguon?: LossCauseSource;
}

export interface LossSummary {
  ky?: string;
  tong_dong?: number;
  so_nghiem_trong?: number;
  so_canh_bao?: number;
  so_thieu_du_lieu?: number;
  ty_le_trung_binh?: number | null;
  dong?: LossLine[];
  nguyen_nhan_hang_dau?: LossCauseRank[];
  nguon?: string;
  co_du_lieu_mau?: boolean;
  ghi?: string;
}

export interface LossThreshold {
  mac_dinh_phan_tram?: number;
  nghiem_trong_phan_tram?: number;
  theo_mat_hang?: Record<string, number>;
  phien_ban?: string;
  ngay_kiem?: string;
}

export interface MemoryQuery {
  store_id?: string;
  anchor_id?: string | null;
  from_time?: string | null;
  to_time?: string | null;
  status?: MemoryStatus | null;
  consent_status?: MemoryConsentStatus | null;
  role?: ExperienceRole;
  requester_id: string;
  keyword?: string | null;
}

export interface MemoryProposal {
  proposal_id: string;
  anchor_id: string;
  store_id?: string;
  content: string;
  owner_scope: string;
  visibility?: "private" | "staff" | "manager" | "public";
  proposed_by: string;
  source_event_ids?: string[];
  snapshot_hash: string;
}

export interface MemoryConsentRequest {
  memory_id: string;
  consent: MemoryConsentStatus;
  actor_id: string;
  actor_role?: ExperienceRole;
  reason?: string;
}

export interface MemoryAuditEntry {
  audit_id: string;
  memory_id: string;
  action: "propose" | "consent_grant" | "consent_revoke" | "confirm" | "expire" | "delete" | "supersede";
  actor_id: string;
  reason?: string;
  occurred_at?: string;
}

export interface GroundedAnswer {
  answer_id: string;
  answer_text: string;
  citations?: string[];
  memory_ids?: string[];
  proposal_id?: string | null;
  unsupported_claims?: string[];
  grounded?: boolean;
}

export interface TourStep {
  step_id: string;
  anchor_id: string;
  narrative: string;
  citation_memory_ids?: string[];
}

export interface TourPlan {
  tour_id: string;
  steps: TourStep[];
  grounded?: boolean;
}

export interface VoiceTurnRequest {
  conversation_id: string;
  transcript: string;
  store_id?: string;
  anchor_id?: string | null;
  role?: ExperienceRole;
  requester_id: string;
}

export interface VoiceTurnResponse {
  turn_id: string;
  transcript: string;
  response_text: string;
  citations?: string[];
  audio_ref?: string | null;
  proposal?: MemoryProposal | null;
  grounded?: boolean;
}

export interface GmailAccount {
  id: string;
  store_id?: string;
  nv_id: string;
  email: string;
  display_name?: string;
  is_primary?: boolean;
  is_active?: boolean;
  created_at: string;
  updated_at: string;
}

export interface GmailOAuthTokens {
  account_id: string;
  access_token: string;
  refresh_token?: string | null;
  expires_at: string;
  scope?: string;
  token_type?: string;
  updated_at: string;
}

export interface GmailSyncState {
  account_id: string;
  last_history_id?: string | null;
  last_sync_at?: string | null;
  sync_cursor?: string | null;
  total_messages?: number;
  unread_count?: number;
  updated_at: string;
}

export interface GmailMessage {
  id: string;
  account_id: string;
  thread_id: string;
  label_ids?: string[];
  snippet?: string;
  from_email?: string;
  to_emails?: string[];
  cc_emails?: string[];
  subject?: string;
  body_text?: string | null;
  body_html?: string | null;
  internal_date: string;
  is_read?: boolean;
  is_starred?: boolean;
  has_attachment?: boolean;
  raw_headers?: string | null;
  created_at: string;
}

export interface GmailLabel {
  id: string;
  account_id: string;
  name: string;
  label_type?: "system" | "user";
  message_list_visibility?: "show" | "hide";
  label_list_visibility?: "labelShow" | "labelHide";
  color_background?: string | null;
  color_text?: string | null;
  total_messages?: number;
  unread_messages?: number;
  updated_at: string;
}

export interface GmailFilter {
  id: string;
  account_id: string;
  criteria?: Record<string, JsonValue>;
  action?: Record<string, JsonValue>;
  created_at: string;
  updated_at: string;
}

export interface GmailThread {
  id: string;
  account_id: string;
  message_ids?: string[];
  subject?: string;
  participants?: string[];
  last_message_date?: string;
  is_unread?: boolean;
  label_ids?: string[];
}

export interface GmailOAuthAuthorizeRequest {
  state?: string | null;
}

export interface GmailOAuthAuthorizeResponse {
  authorization_url: string;
  state: string;
}

export interface GmailOAuthCallbackRequest {
  code: string;
  state: string;
}

export interface GmailOAuthCallbackResponse {
  ok: boolean;
  account_id: string;
  email: string;
  message: string;
}

export interface GmailAccountCreateRequest {
  email: string;
  display_name?: string;
  is_primary?: boolean;
}

export interface GmailAccountUpdateRequest {
  display_name?: string | null;
  is_primary?: boolean | null;
  is_active?: boolean | null;
}

export interface GmailMessageListParams {
  label_ids?: string[] | null;
  query?: string | null;
  is_read?: boolean | null;
  limit?: number;
  offset?: number;
}

export interface GmailLabelCreateRequest {
  name: string;
  label_list_visibility?: "labelShow" | "labelHide";
  message_list_visibility?: "show" | "hide";
  color_background?: string | null;
  color_text?: string | null;
}

export interface GmailLabelUpdateRequest {
  name?: string | null;
  label_list_visibility?: "labelShow" | "labelHide" | null;
  message_list_visibility?: "show" | "hide" | null;
  color_background?: string | null;
  color_text?: string | null;
}

export interface GmailFilterCreateRequest {
  criteria?: Record<string, JsonValue>;
  action?: Record<string, JsonValue>;
}

export interface GmailSyncRequest {
  account_id?: string | null;
  full_sync?: boolean;
}

export interface GmailSendMessageRequest {
  to: string[];
  subject: string;
  body_text: string;
  body_html?: string | null;
  cc?: string[] | null;
  bcc?: string[] | null;
  thread_id?: string | null;
  in_reply_to?: string | null;
  references?: string | null;
}

