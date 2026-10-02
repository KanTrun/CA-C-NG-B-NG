"""Shared data contracts — Sprint-1 schemas plus quầy nội bộ (ADR-013)."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field

# Import ở đầu file chứ không để cuối: hai module con chỉ phụ thuộc stdlib + pydantic
# nên không có vòng lặp import, và để cuối file thì ruff báo E402 (lint gate đỏ).
from ca_contracts.catchment_survey import StoreCandidate
from ca_contracts.causal_memory import (
    CausalChain,
    CausalLink,
    CausalNode,
    CausalNodeType,
)
from ca_contracts.episodic_memory import (
    Episode,
    EpisodeType,
    Reflection,
    ReflectionResult,
)
from ca_contracts.grand_experience import (
    DataQualityNotice,
    ExperienceActionProposal,
    ExperienceCapability,
    ExperienceEvent,
    ExperienceEventType,
    ExperienceMemory,
    ExperienceMode,
    ExperienceProposalStatus,
    ExperienceRole,
    HorizonItem,
    LivingCafeSnapshot,
    MemoryConsentStatus,
    MemoryStatus,
    MemoryVisibility,
    ModeProjection,
    PublicEventProjection,
    QuanverseAskRequest,
    QuanverseAskResponse,
    QuanverseBrief,
    QuanverseMetric,
    QuanversePage,
    RescueCandidate,
    RescueCase,
    RescueCaseStatus,
    RuleCandidate,
    ShadowTestResult,
    SpatialAnchor,
    VoiceTurn,
    WarRoomComparison,
    WarRoomOption,
    WarRoomScenario,
    WarRoomScenarioType,
    ZoneProjection,
    experience_capabilities_for_role,
    experience_role_can,
)
from ca_contracts.loss import (
    LossBasis,
    LossCauseRank,
    LossCauseSource,
    LossLevel,
    LossLine,
    LossSummary,
    LossThreshold,
)
from ca_contracts.ops_predict import (
    PositiveRule,
    PositiveRuleStatus,
    PredictResponse,
    SuccessPattern,
    SuccessPatternSource,
    SuccessPatternType,
    TwinScenario,
    TwinScenarioType,
)
from ca_contracts.spatial_memory import (
    AnchorQuery,
    GroundedAnswer,
    MemoryAuditEntry,
    MemoryConsentRequest,
    MemoryProposal,
    MemoryQuery,
    TourPlan,
    TourStep,
    VoiceTurnRequest,
    VoiceTurnResponse,
)
from ca_contracts.trend_item import TrendItem
from ca_contracts.virtual_staff import (
    VirtualSimulation,
    VirtualStaff,
    VirtualStaffType,
)


class NhanVien(BaseModel):
    id: str
    ten: str
    ky_nang: list[str] = Field(default_factory=list)
    la_sinh_vien: bool = True
    so_dien_thoai_hash: str | None = None


class Ca(BaseModel):
    id: str
    ngay: str
    bat_dau: str
    ket_thuc: str
    vi_tri: str
    so_nguoi_toi_thieu: int = 1


class LichTuan(BaseModel):
    tuan_iso: str
    trang_thai: Literal[
        "may_sinh", "nhap", "dang_giai", "cho_duyet", "da_duyet", "da_cong_bo", "da_dong"
    ] = "nhap"
    phan_cong: dict[str, list[str]] = Field(
        default_factory=dict,
        description="ca_id -> danh sách nhan_vien_id",
    )


class MinhChungLoai(StrEnum):
    khong = "khong"
    so = "so"
    anh = "anh"
    kiem_ke = "kiem_ke"
    van_ban = "van_ban"
    danh_sach = "danh_sach"
    xac_nhan = "xac_nhan"
    xac_nhan_doc = "xac_nhan_doc"


class PhieuBuoc(BaseModel):
    ma: str
    ten: str
    minh_chung: MinhChungLoai = MinhChungLoai.khong


class PhieuMau(BaseModel):
    ma: str
    ten: str
    gan_voi: str | None = None
    buoc: list[PhieuBuoc]


class RangBuocTrichXuat(BaseModel):
    id: str
    nguon: Literal["tkb", "tin_nhan", "ban_giao", "khac"]
    nhan_vien_id: str | None = None
    noi_dung: str
    do_tin_cay: float = Field(ge=0.0, le=1.0)
    trang_thai: Literal["cho_duyet", "da_duyet", "tu_choi"] = "cho_duyet"
    khung_gio: list[str] = Field(default_factory=list)


class DongDon(BaseModel):
    mon_id: str
    ten: str
    so_luong: int = Field(ge=1)
    gia: int = Field(ge=0)


class MonNuoc(BaseModel):
    id: str
    ten: str
    gia: int = Field(ge=0, description="Đồng, số nguyên")
    an: bool = False
    hinh_url: str = Field(default="", max_length=500, description="URL ảnh món (hoặc /api/v1/menu/{id}/anh)")
    nhom: str = Field(
        default="",
        description="Nhóm sản phẩm (ca_phe/tra/sinh_to/banh/nuoc_dong_chai/nguyen_lieu), dùng phân mục menu quầy",
    )
    bom: dict[str, float] = Field(
        default_factory=dict,
        description="Nguyên liệu ước lượng khi hoàn thành đơn, vd cafe_g, sua_ml, ly",
    )


class DonQuay(BaseModel):
    id: str
    nv_id: str
    trang_thai: Literal["cho_pha", "dang_pha", "xong", "huy"] = "cho_pha"
    thanh_toan: Literal["tien_mat", "da_ck", "chua_thu"] = "chua_thu"
    dong: list[DongDon]
    ly_do_huy: str | None = None
    nguon: Literal["quay_noi_bo"] = "quay_noi_bo"
    luc: str = ""


class DoanThoaiTranscript(BaseModel):
    nguoi_noi: str
    bat_dau_s: float | None = None
    ket_thuc_s: float | None = None
    noi_dung: str


class ActionItem(BaseModel):
    id: str
    tieu_de: str
    noi_dung_chi_tiet: str = ""
    tinh_chat: Literal["bat_buoc", "tuy_chon", "khuyen_khich"] = "bat_buoc"
    ten_nguoi_giao: str = ""
    nhan_vien_id: str | None = None
    ten_nguoi_nhan: str
    pham_vi: Literal["ca_nhan", "nhom"] = "ca_nhan"
    thoi_gian_bat_dau: str = ""
    han_chot: str = ""
    muc_do_uu_tien: Literal["cao", "trung_binh", "thap"] = "trung_binh"
    do_tin_cay: float = Field(ge=0.0, le=1.0, default=0.9)
    da_chon: bool = True
    loai_cong_viec: Literal["1_ca", "nhieu_ca", "gop_y"] = "1_ca"
    ca_thuc_hien: str = ""
    ca_du_kien: list[str] = Field(default_factory=list)
    can_lam_ro: bool = False
    van_de_ngu_canh: str = ""
    cau_hoi_lam_ro: str = ""
    goi_y_xu_ly: list[str] = Field(default_factory=list)
    stt_near_miss: bool = False
    khong_co_can_cu: bool = False
    nguon_cau_noi: str = ""


class DieuChinhLichHop(BaseModel):
    id: str = ""
    nhan_vien_id: str | None = None
    ten_nhan_vien: str = ""
    loai: Literal["xin_nghi", "ghim_ca", "doi_ca", "uu_tien"] = "xin_nghi"
    thu: str = ""  # T2, T3, T4, T5, T6, T7, CN
    khung: str = ""  # sang, chieu, toi
    ca_id: str = ""  # e.g. w1_c01, ca_01
    tuan_iso: str = ""
    ly_do: str = ""
    trang_thai: Literal["cho_duyet", "da_duyet", "tu_choi"] = "cho_duyet"


class DeXuatPheDuyet(BaseModel):
    id: str
    loai_de_xuat: Literal["quy_trinh_sop", "mua_sam_vat_tu", "chinh_sach_nhan_su", "dieu_chinh_lich", "khac"] = (
        "quy_trinh_sop"
    )
    tieu_de: str
    nguoi_de_xuat: str = ""
    nguoi_phe_duyet: str = ""
    noi_dung: str
    ly_do: str = ""
    trang_thai: Literal["da_duyet", "cho_duyet", "tu_choi"] = "cho_duyet"
    quy_trinh_lien_quan: str | None = None
    buoc_so: int | None = None
    chi_tiet_lich: DieuChinhLichHop | None = None


class GopYLuuY(BaseModel):
    id: str
    nguoi_gop_y: str = ""
    nguoi_nhan: str = ""
    chu_de: Literal[
        "thai_do_phuc_vu",
        "ky_nang_pha_che",
        "ve_sinh_an_toan",
        "dong_vien_khen_ngoi",
        "luu_y_chung",
    ] = "luu_y_chung"
    tinh_chat: Literal["nhac_nho", "khen_ngoi", "kinh_nghiem", "gop_y"] = "gop_y"
    noi_dung: str
    ghi_chu: str = ""


class DeXuatSop(BaseModel):
    quy_trinh_lien_quan: str
    buoc_so: int | None = None
    noi_dung_thay_doi: str
    ly_do: str = ""


class TieuChiAudit(BaseModel):
    ma: str
    ten_tieu_chi: str
    dat: bool = False
    chi_tiet: str = ""


class AuditTuanThuSop(BaseModel):
    diem_tuan_thu: int = Field(ge=0, le=100, default=100)
    xep_hang: Literal["A", "B", "C", "D"] = "A"
    tieu_chi: list[TieuChiAudit] = Field(default_factory=list)
    canh_bao_do: list[str] = Field(default_factory=list)
    nhan_xet_chung: str = ""


class BanTinCaKhan(BaseModel):
    ban_vip: list[str] = Field(default_factory=list)
    luu_y_di_ung_khach: list[str] = Field(default_factory=list)
    su_co_thiet_bi_khan: list[str] = Field(default_factory=list)
    danh_sach_mon_86: list[str] = Field(default_factory=list)
    noi_dung_tin_nhan_gui_nhom: str = ""


class HuanLuyenQuanLy(BaseModel):
    ty_le_noi_quan_ly_pct: int = Field(ge=0, le=100, default=70)
    ty_le_noi_nhan_vien_pct: int = Field(ge=0, le=100, default=30)
    diem_tuong_tac_2_chieu: int = Field(ge=0, le=10, default=8)
    diem_truyen_cam_hung: int = Field(ge=0, le=10, default=8)
    phong_cach_dieu_hanh: str = "Chuẩn mực & Tương tác"
    loi_khuyen_ai_coaching: list[str] = Field(default_factory=list)


class CuocHop(BaseModel):
    id: str
    tieu_de: str
    loai_hop: Literal["giao_ca", "hop_tuan", "dao_tao", "khac"] = "giao_ca"
    thoi_gian: str = ""
    nguon_am_thanh: Literal["google_meet_tab", "microphone", "file_upload", "ghi_chep_tay"] = (
        "microphone"
    )
    transcript_thoai: list[DoanThoaiTranscript] = Field(default_factory=list)
    tom_tat: str
    quyet_dinh: list[str] = Field(default_factory=list)
    de_xuat_phe_duyet: list[DeXuatPheDuyet] = Field(default_factory=list)
    action_items: list[ActionItem] = Field(default_factory=list)
    gop_y_luu_y: list[GopYLuuY] = Field(default_factory=list)
    dieu_chinh_lich: list[DieuChinhLichHop] = Field(default_factory=list)
    audit_sop: AuditTuanThuSop | None = None
    ban_tin_ca: BanTinCaKhan | None = None
    huan_luyen_quan_ly: HuanLuyenQuanLy | None = None
    de_xuat_sop: list[DeXuatSop] = Field(default_factory=list)
    do_tin_cay_tong_the: float = Field(ge=0.0, le=1.0, default=0.9)
    trang_thai: Literal["cho_duyet", "da_duyet", "tu_choi"] = "cho_duyet"
    phien_ban: int = 1
    last_modified_at: str = ""
    ngay_ghi_am: str = ""


class CatchmentSurveyParams(BaseModel):
    """Tham số khảo sát giá thị trường được schema hoá tất định (plan v2.0 mục 4.1)."""

    contract_version: Literal["v1"] = "v1"
    store_id: str = Field(min_length=1)
    category_keyword: str = Field(min_length=1, max_length=64)
    radius_km: float = Field(ge=0.5, le=10.0, default=3.0)
    channel_mode: Literal["dine_in_vision", "delivery_platform", "hybrid"] = "hybrid"
    include_substitutes: bool = True
    quota_cost: int = Field(default=1, ge=1)


class CopilotIntent(StrEnum):
    SCHEDULE_SOLVE = "SCHEDULE_SOLVE"
    APPROVE_SHIFT_SWAP = "APPROVE_SHIFT_SWAP"
    GENERATE_DAILY_BRIEF = "GENERATE_DAILY_BRIEF"
    QUERY_SOP = "QUERY_SOP"
    ANALYZE_WASTE = "ANALYZE_WASTE"
    CREATE_RULE_PROPOSAL = "CREATE_RULE_PROPOSAL"
    INVENTORY_RESTOCK_CHECK = "INVENTORY_RESTOCK_CHECK"
    SEND_MAIL = "SEND_MAIL"
    # PR9 read intents — chỉ đọc, không side effect
    GET_MY_PROFILE = "GET_MY_PROFILE"
    LIST_STAFF = "LIST_STAFF"
    QUERY_MENU = "QUERY_MENU"
    GET_INVENTORY = "GET_INVENTORY"
    GET_SHIFT_SWAPS = "GET_SHIFT_SWAPS"
    GET_HANGING_TASKS = "GET_HANGING_TASKS"
    GET_HANDOVERS = "GET_HANDOVERS"
    # PR10 self-service mutating intents
    PROPOSE_HANGING_TASK = "PROPOSE_HANGING_TASK"
    PROPOSE_TASK_COMPLETE = "PROPOSE_TASK_COMPLETE"
    PROPOSE_CONSUMPTION_RECORD = "PROPOSE_CONSUMPTION_RECORD"
    # NV báo bận/xin nghỉ cho chính mình — đề xuất vào inbox chờ duyệt
    PROPOSE_TIME_OFF = "PROPOSE_TIME_OFF"
    # PR11 admin mutating intents
    PROPOSE_MENU_UPDATE = "PROPOSE_MENU_UPDATE"
    PROPOSE_ORDER_TRANSITION = "PROPOSE_ORDER_TRANSITION"
    PROPOSE_PIN = "PROPOSE_PIN"
    # PR12 external channel intents
    GET_PAGE_STATUS = "GET_PAGE_STATUS"
    PROPOSE_PAGE_SYNC = "PROPOSE_PAGE_SYNC"
    PROPOSE_PAGE_DRAFT = "PROPOSE_PAGE_DRAFT"
    # PR10 còn lại (R2_CONFIRM): xác nhận TKB, đồng ý đổi ca, ghi bàn giao ca
    PROPOSE_TKB_CONFIRM = "PROPOSE_TKB_CONFIRM"
    PROPOSE_SWAP_CONSENT = "PROPOSE_SWAP_CONSENT"
    PROPOSE_HANDOVER = "PROPOSE_HANDOVER"
    # PR13 read intents bổ sung — lịch tuần / ca cá nhân / ràng buộc chờ duyệt
    GET_SCHEDULE = "GET_SCHEDULE"
    GET_MY_SHIFTS = "GET_MY_SHIFTS"
    GET_CONSTRAINT_CANDIDATES = "GET_CONSTRAINT_CANDIDATES"
    # Khảo sát thị trường & SerpApi
    RUN_CATCHMENT_SURVEY = "RUN_CATCHMENT_SURVEY"
    GET_SERPAPI_QUOTA = "GET_SERPAPI_QUOTA"
    GET_SURVEY_RESULT = "GET_SURVEY_RESULT"
    # Audit / vết hệ thống — chỉ quản lý & chủ quán (R0_READ, tenant-scoped)
    QUERY_AUDIT = "QUERY_AUDIT"
    # Hỏi về 4 mặt Trải nghiệm AI: Living Map, War Room, Cứu ca, Hồn quán (R0_READ)
    QUERY_QUANVERSE = "QUERY_QUANVERSE"
    # Mở rộng năng lực vận hành (R0_READ)
    GET_WEATHER = "GET_WEATHER"
    GET_TODAY_OPERATIONS = "GET_TODAY_OPERATIONS"
    GET_FAIRNESS_SUMMARY = "GET_FAIRNESS_SUMMARY"
    GET_MY_CHECKLIST = "GET_MY_CHECKLIST"
    SEARCH_TRENDS = "SEARCH_TRENDS"
    GET_RESERVATIONS = "GET_RESERVATIONS"
    GET_OPEN_SHIFTS = "GET_OPEN_SHIFTS"
    GET_MEETINGS = "GET_MEETINGS"
    GET_PREDICTIVE_INSIGHTS = "GET_PREDICTIVE_INSIGHTS"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"


# ── Ma trận quyền Role → Intent (single source of truth) ─────────────────────
# Nguyên tắc: fail-closed — intent không liệt kê = không ai được gọi.
# - nhan_vien: đọc (R0) + draft (R1): brief, SOP, hao hụt, menu, việc treo...
# - quan_ly: + xếp lịch, duyệt đổi ca, đề xuất luật, kiểm kê tồn kho, gửi mail.
# - chu_quan: toàn bộ quyền quan_ly (không có intent riêng vượt quan_ly).
_READ_INTENTS = frozenset(
    {
        "GET_MY_PROFILE",
        "LIST_STAFF",
        "QUERY_MENU",
        "GET_INVENTORY",
        "GET_SHIFT_SWAPS",
        "GET_HANGING_TASKS",
        "GET_HANDOVERS",
        # PR13: lịch tuần, ca cá nhân, ràng buộc chờ duyệt — R0_READ mọi role
        "GET_SCHEDULE",
        "GET_MY_SHIFTS",
        "GET_CONSTRAINT_CANDIDATES",
        # Thị trường & SerpApi — R0_READ
        "GET_SERPAPI_QUOTA",
        "GET_SURVEY_RESULT",
        # Trải nghiệm AI (Living Map / War Room / Cứu ca / Hồn quán) — R0_READ mọi role
        "QUERY_QUANVERSE",
        # Mở rộng năng lực vận hành — R0_READ mọi role
        "GET_WEATHER",
        "GET_TODAY_OPERATIONS",
        "GET_FAIRNESS_SUMMARY",
        "GET_MY_CHECKLIST",
        "SEARCH_TRENDS",
        "GET_RESERVATIONS",
        "GET_OPEN_SHIFTS",
        "GET_MEETINGS",
    }
)
_QUAN_LY_INTENTS: frozenset[str] = frozenset(
    {
        "GENERATE_DAILY_BRIEF",
        "QUERY_SOP",
        "ANALYZE_WASTE",
        "OUT_OF_SCOPE",
        *_READ_INTENTS,
        "SCHEDULE_SOLVE",
        "APPROVE_SHIFT_SWAP",
        "CREATE_RULE_PROPOSAL",
        "INVENTORY_RESTOCK_CHECK",
        "SEND_MAIL",
        # PR10 self-service (R2_CONFIRM)
        "PROPOSE_HANGING_TASK",
        "PROPOSE_TASK_COMPLETE",
        "PROPOSE_CONSUMPTION_RECORD",
        "PROPOSE_TIME_OFF",
        # PR11 admin (R2_CONFIRM)
        "PROPOSE_MENU_UPDATE",
        "PROPOSE_ORDER_TRANSITION",
        "PROPOSE_PIN",
        # PR12 external channels (R0/R2)
        "GET_PAGE_STATUS",
        "PROPOSE_PAGE_SYNC",
        "PROPOSE_PAGE_DRAFT",
        # PR10 còn lại (R2_CONFIRM)
        "PROPOSE_TKB_CONFIRM",
        "PROPOSE_SWAP_CONSENT",
        "PROPOSE_HANDOVER",
        # Khảo sát giá thị trường — R2_CONFIRM (chỉ quản lý/chủ quán)
        "RUN_CATCHMENT_SURVEY",
        # Audit / vết hệ thống — R0_READ nhưng chỉ quản lý & chủ quán (tenant-scoped)
        "QUERY_AUDIT",
        # Gợi ý tối ưu vận hành / Playbook — R0_READ chỉ quản lý & chủ quán
        "GET_PREDICTIVE_INSIGHTS",
    }
)
COPILOT_ROLE_INTENT_MATRIX: dict[str, frozenset[str]] = {
    "nhan_vien": frozenset(
        {
            "GENERATE_DAILY_BRIEF",
            "QUERY_SOP",
            "ANALYZE_WASTE",
            "OUT_OF_SCOPE",
            *_READ_INTENTS,
            # PR10 self-service: nhân viên tạo việc treo/đánh dấu xong của mình
            "PROPOSE_HANGING_TASK",
            "PROPOSE_TASK_COMPLETE",
            # PR10 còn lại (R2_CONFIRM): tự xác nhận TKB, đồng ý đổi ca, bàn giao ca
            "PROPOSE_TKB_CONFIRM",
            "PROPOSE_SWAP_CONSENT",
            "PROPOSE_HANDOVER",
            # NV báo bận/xin nghỉ cho mình — cơ bản như phiếu
            "PROPOSE_TIME_OFF",
        }
    ),
    "quan_ly": _QUAN_LY_INTENTS,
    # Chủ quán có đầy đủ toàn bộ quyền quản trị của Quản lý
    "chu_quan": _QUAN_LY_INTENTS,
}


def copilot_intents_allowed_for_role(role: str) -> frozenset[str]:
    """Trả về tập intent được phép cho role. Fail-closed: role lạ → rỗng."""
    return COPILOT_ROLE_INTENT_MATRIX.get(role, frozenset())


def copilot_role_can_use_intent(role: str, intent: str) -> bool:
    """Kiểm tra role có được dùng intent không. Fail-closed."""
    return intent in copilot_intents_allowed_for_role(role)


class ActionProposalStatus(StrEnum):
    draft = "draft"
    ready_for_approval = "ready_for_approval"
    amendment_ready = "amendment_ready"
    executing = "executing"
    executed = "executed"
    execution_failed = "execution_failed"
    rejected = "rejected"
    expired = "expired"
    stale_rejected = "stale_rejected"


class CopilotContext(BaseModel):
    store_id: str = "quan_01"
    user_id: str
    user_role: Literal["chu_quan", "quan_ly", "nhan_vien"]
    active_date: str
    channel: Literal["web", "telegram", "zalo"] = "web"
    recent_messages: list[str] = Field(default_factory=list, max_length=3)


class CopilotMessage(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    context: CopilotContext


class ActionProposal(BaseModel):
    action_id: str
    intent: CopilotIntent
    status: ActionProposalStatus = ActionProposalStatus.draft
    summary: str
    explanation: str = ""
    payload_diff: dict[str, Any] = Field(default_factory=dict)
    requires_confirmation: bool = True
    store_id: str = "quan_01"
    created_by: str
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    data_snapshot_hash: str = ""
    expires_at: str
    created_at: str = ""
    executed_at: str | None = None
    amended_from: str | None = None


class CopilotResponse(BaseModel):
    reply_text: str
    intent: CopilotIntent
    confidence: float = Field(ge=0.0, le=1.0)
    action_proposal: ActionProposal | None = None
    direct_answer: str | None = None
    citations: list[str] = Field(default_factory=list)
    agent_mode: str = "replay"
    # Lượt này chỉ là CÂU HỎI LÀM RÕ, chưa phải hành động. Client nhắn dùng
    # cờ này để biết lượt sau câu của người dùng là câu TRẢ LỜI — trước đây
    # phải so chuỗi trong `reply_text`, nên đổi câu chữ là hỏng ngay, và không
    # phân biệt được "hỏi lý do" với các câu hỏi làm rõ khác.
    clarification_kind: str | None = None


# ── Universal Orchestration (PR9): Capability Registry ───────────────────────

CapabilityRiskTier = Literal["R0_READ", "R1_DRAFT", "R2_CONFIRM", "R3_DUAL_APPROVAL", "R4_MANUAL_ONLY"]


class CapabilityDefinition(BaseModel):
    """Một capability trong catalog điều phối toàn dự án (kế hoạch §1.2/§1.3).

    - `intent`: tên intent duy nhất (GET_*, QUERY_*, PROPOSE_*, NAVIGATE_*...).
    - `risk_tier`: mức quyền theo mô hình 5 cấp R0-R4.
    - `deep_link`: màn hình web tương ứng (R4 hoặc dữ liệu trực quan).
    - `manual_only_reason`: bắt buộc khi risk_tier = R4_MANUAL_ONLY.
    """

    intent: str
    label: str
    domain: str
    risk_tier: CapabilityRiskTier
    deep_link: str = ""
    manual_only_reason: str = ""


def _cap(
    intent: str, label: str, domain: str, risk_tier: CapabilityRiskTier,
    deep_link: str = "", manual_only_reason: str = "",
) -> CapabilityDefinition:
    return CapabilityDefinition(
        intent=intent, label=label, domain=domain, risk_tier=risk_tier,
        deep_link=deep_link, manual_only_reason=manual_only_reason,
    )


CAPABILITY_REGISTRY: tuple[CapabilityDefinition, ...] = (
    # ── Tài khoản / cá nhân ──
    _cap("GET_MY_PROFILE", "Xem hồ sơ của tôi", "account", "R0_READ", "/toi"),
    _cap("PROPOSE_MY_EMAIL_UPDATE", "Cập nhật email cá nhân", "account", "R2_CONFIRM", "/toi"),
    _cap("LOGIN", "Đăng nhập", "account", "R4_MANUAL_ONLY", "/login", "Thao tác bảo mật bắt buộc — agent không nhận mật khẩu/token"),
    _cap("REGISTER", "Đăng ký tài khoản", "account", "R4_MANUAL_ONLY", "/dang-ky", "Thao tác bảo mật bắt buộc"),
    # ── Nhân sự & vai trò ──
    _cap("LIST_STAFF", "Danh sách nhân sự", "staff", "R0_READ", "/nguoi"),
    _cap("CHANGE_ROLE", "Nâng/hạ vai trò", "staff", "R4_MANUAL_ONLY", "/nguoi", "Chỉ chủ quán thao tác trực tiếp — không qua chat"),
    # ── Lịch tuần ──
    _cap("GET_SCHEDULE", "Xem lịch tuần", "schedule", "R0_READ", "/roster"),
    _cap("DRAFT_SCHEDULE", "Xếp lịch nháp", "schedule", "R1_DRAFT"),
    _cap("SCHEDULE_SOLVE", "Xếp lịch tuần", "schedule", "R2_CONFIRM"),
    _cap("CONFIRM_SCHEDULE_AVAILABILITY", "Xác nhận khả dụng theo tuần", "schedule", "R2_CONFIRM", "/chat"),
    _cap("RESOLVE_SCHEDULE_GAPS", "Xử lý ca trống", "schedule", "R3_DUAL_APPROVAL", "/lich"),
    _cap("GET_SCHEDULE_NOTIFICATIONS", "Xem thông báo lịch", "schedule", "R0_READ", "/lich"),
    _cap("PROPOSE_SHIFT_FRAME_CHANGE", "Đổi khung giờ ca", "schedule", "R3_DUAL_APPROVAL"),
    _cap("PROPOSE_PIN", "Ghim ca", "schedule", "R2_CONFIRM"),
    _cap("PROPOSE_SCHEDULE_TRANSITION", "Công bố/đóng lịch", "schedule", "R3_DUAL_APPROVAL"),
    _cap("EXPORT_SCHEDULE", "Xuất lịch ICS", "schedule", "R0_READ", "/roster"),
    # ── Hôm nay / công bằng ──
    _cap("GET_WEATHER", "Thời tiết & Khuyến nghị vận hành", "today", "R0_READ", "/hom-nay"),
    _cap("GET_TODAY_OPERATIONS", "Dashboard hôm nay", "today", "R0_READ", "/hom-nay"),
    _cap("GENERATE_DAILY_BRIEF", "Bản tin sáng", "today", "R0_READ"),
    _cap("GET_FAIRNESS_SUMMARY", "Báo cáo công bằng", "today", "R0_READ", "/cong-bang"),
    _cap("EXPLAIN_ASSIGNMENT", "Giải thích phân công", "today", "R0_READ"),
    # ── Điểm danh / QR ──
    _cap("GET_ATTENDANCE_STATUS", "Trạng thái điểm danh", "attendance", "R0_READ", "/qr"),
    _cap("ISSUE_QR", "Phát mã QR", "attendance", "R4_MANUAL_ONLY", "/qr", "Mã QR là thông tin xác thực vật lý — không qua chat"),
    _cap("CHECK_IN", "Check-in tại quán", "attendance", "R4_MANUAL_ONLY", "/qr", "Check-in phải xác thực vật lý tại quán"),
    # ── Phiếu / checklist ──
    _cap("GET_MY_CHECKLIST", "Checklist của tôi", "checklist", "R0_READ", "/phieu"),
    _cap("DRAFT_CHECKLIST_UPDATE", "Cập nhật phiếu nháp", "checklist", "R1_DRAFT"),
    _cap("PROPOSE_EVIDENCE", "Đính kèm minh chứng", "checklist", "R2_CONFIRM", "/phieu"),
    _cap("PROPOSE_HANGING_TASK", "Tạo việc treo", "checklist", "R2_CONFIRM", "/treo"),
    # ── Việc treo ──
    _cap("GET_HANGING_TASKS", "Xem việc treo", "hanging", "R0_READ", "/treo"),
    _cap("PROPOSE_TASK_DISPATCH", "Giao việc treo", "hanging", "R2_CONFIRM", "/treo"),
    _cap("PROPOSE_TASK_COMPLETE", "Đánh dấu việc treo xong", "hanging", "R2_CONFIRM", "/treo"),
    # ── TKB & ràng buộc ──
    _cap("EXTRACT_TKB", "Trích TKB từ ảnh", "tkb", "R1_DRAFT"),
    _cap("CONFIRM_TKB", "Xác nhận TKB", "tkb", "R2_CONFIRM", "/inbox"),
    _cap("PROPOSE_TKB_CONFIRM", "Xác nhận TKB qua chat", "tkb", "R2_CONFIRM", "/inbox"),
    _cap("CLASSIFY_CONSTRAINT", "Phân loại ràng buộc", "tkb", "R1_DRAFT"),
    _cap("GET_CONSTRAINT_CANDIDATES", "Xem ràng buộc chờ duyệt", "tkb", "R0_READ", "/inbox"),
    _cap("PROPOSE_CONSTRAINT_DECISION", "Duyệt ràng buộc", "tkb", "R2_CONFIRM", "/inbox"),
    # ── Ca cá nhân & đổi ca ──
    _cap("GET_MY_SHIFTS", "Lịch của tôi", "shift", "R0_READ", "/toi"),
    _cap("PROPOSE_RELEASE_SHIFT", "Nhả ca", "shift", "R2_CONFIRM", "/doi-ca"),
    _cap("PROPOSE_TAKE_SHIFT", "Nhận ca", "shift", "R2_CONFIRM", "/doi-ca"),
    _cap("GET_SHIFT_SWAPS", "Xem chợ đổi ca", "shift", "R0_READ", "/doi-ca"),
    _cap("GET_OPEN_SHIFTS", "Xem ca đang cần người", "shift", "R0_READ", "/open-shifts"),
    _cap("CLAIM_OPEN_SHIFT", "Đăng ký nhận ca trống", "shift", "R2_CONFIRM", "/open-shifts"),
    _cap("APPROVE_SHIFT_SWAP", "Duyệt đổi ca", "shift", "R2_CONFIRM"),
    _cap("CONSENT_SHIFT_SWAP", "Đồng ý đổi ca", "shift", "R2_CONFIRM", "/doi-ca"),
    _cap("PROPOSE_SWAP_CONSENT", "Đồng ý đổi ca qua chat", "shift", "R2_CONFIRM", "/doi-ca"),
    _cap("REJECT_SHIFT_SWAP", "Từ chối đổi ca", "shift", "R2_CONFIRM", "/doi-ca"),
    _cap("FINALIZE_SHIFT_SWAP", "Chốt đổi ca", "shift", "R3_DUAL_APPROVAL", "/doi-ca"),
    # ── Menu ──
    _cap("QUERY_MENU", "Tra cứu menu", "menu", "R0_READ", "/menu"),
    _cap("DRAFT_MENU_ITEM", "Soạn món nháp", "menu", "R1_DRAFT"),
    _cap("PROPOSE_MENU_UPDATE", "Cập nhật món/giá", "menu", "R2_CONFIRM", "/menu"),
    _cap("PROPOSE_MENU_IMAGE", "Cập nhật ảnh món", "menu", "R2_CONFIRM", "/menu"),
    # ── Quầy / POS ──
    _cap("GET_COUNTER_STATUS", "Trạng thái quầy", "pos", "R0_READ", "/quay"),
    _cap("GET_RESERVATIONS", "Tra cứu đặt bàn & sơ đồ bàn", "pos", "R0_READ", "/page-quan/dat-ban"),
    _cap("DRAFT_COUNTER_ORDER", "Soạn đơn quầy nháp", "pos", "R1_DRAFT"),
    _cap("PROPOSE_ORDER_TRANSITION", "Đổi trạng thái đơn", "pos", "R2_CONFIRM", "/quay"),
    _cap("PAYMENT", "Thanh toán đơn", "pos", "R4_MANUAL_ONLY", "/quay", "Thanh toán cần policy riêng — giữ manual"),
    _cap("CANCEL_ORDER", "Hủy đơn", "pos", "R4_MANUAL_ONLY", "/quay", "Hủy đơn là thao tác phá hủy — giữ manual"),
    # ── Tiêu thụ / tồn kho ──
    _cap("GET_INVENTORY", "Xem tồn kho", "inventory", "R0_READ", "/tieu-thu"),
    _cap("INVENTORY_RESTOCK_CHECK", "Kiểm kê & cảnh báo", "inventory", "R2_CONFIRM"),
    _cap("PROPOSE_CONSUMPTION_RECORD", "Ghi tiêu thụ", "inventory", "R2_CONFIRM", "/tieu-thu"),
    _cap("PROPOSE_STOCK_ADJUSTMENT", "Chỉnh tồn kho", "inventory", "R2_CONFIRM", "/tieu-thu"),
    # ── Hao hụt ──
    _cap("ANALYZE_WASTE", "Phân tích hao hụt", "waste", "R0_READ", "/hao-phi"),
    _cap("PROPOSE_WASTE_RECORD", "Ghi hao hụt", "waste", "R2_CONFIRM", "/hao-phi"),
    # Hao hụt định lượng (plan 260923-1736): đọc tổng hợp và ghi có nguyên nhân.
    _cap("GET_LOSS_SUMMARY", "Hao hụt theo nguyên liệu", "waste", "R0_READ", "/hao-phi"),
    _cap("GET_LOSS_THRESHOLD", "Ngưỡng hao hụt đang áp dụng", "waste", "R0_READ", "/hao-phi"),
    _cap("PROPOSE_LOSS_RECORD", "Ghi hao hụt kèm nguyên nhân", "waste", "R2_CONFIRM", "/hao-phi"),
    # ── Bàn giao ──
    _cap("GET_HANDOVERS", "Xem bàn giao", "handover", "R0_READ", "/handover"),
    _cap("DRAFT_HANDOVER", "Soạn bàn giao nháp", "handover", "R1_DRAFT"),
    _cap("APPLY_HANDOVER", "Áp dụng bàn giao", "handover", "R2_CONFIRM", "/handover"),
    _cap("PROPOSE_HANDOVER", "Ghi bàn giao ca qua chat", "handover", "R2_CONFIRM", "/handover"),
    # ── SOP / cẩm nang ──
    _cap("QUERY_SOP", "Hỏi quy trình", "sop", "R0_READ", "/sop"),
    _cap("GET_PLAYBOOK", "Xem cẩm nang", "sop", "R0_READ", "/cam-nang"),
    _cap("GET_PREDICTIVE_INSIGHTS", "Gợi ý tối ưu vận hành & Playbook", "sop", "R0_READ", "/de-xuat-thong-minh"),
    _cap("CREATE_RULE_PROPOSAL", "Đề xuất luật mới", "sop", "R2_CONFIRM"),
    _cap("RUN_RULE_PIPELINE", "Chạy pipeline 8 bước", "sop", "R1_DRAFT", "/cam-nang"),
    _cap("ACTIVATE_PAUSE_ROLLBACK_RULE", "Kích hoạt/tạm dừng luật", "sop", "R3_DUAL_APPROVAL", "/cam-nang"),
    # ── Cuộc họp ──
    _cap("GET_MEETINGS", "Xem biên bản họp & quyết định", "meeting", "R0_READ", "/cuoc-hop"),
    _cap("TRANSCRIBE_MEETING", "Phiên âm cuộc họp", "meeting", "R1_DRAFT", "/cuoc-hop"),
    _cap("DRAFT_MEETING_MINUTES", "Soạn biên bản nháp", "meeting", "R1_DRAFT", "/cuoc-hop"),
    _cap("APPLY_MEETING_ACTIONS", "Áp dụng action họp", "meeting", "R2_CONFIRM", "/cuoc-hop"),
    _cap("DELETE_MEETING", "Xóa cuộc họp", "meeting", "R4_MANUAL_ONLY", "/cuoc-hop", "Xóa là thao tác phá hủy — giữ manual"),
    # ── Email ──
    _cap("DRAFT_EMAIL", "Soạn email nháp", "email", "R1_DRAFT"),
    _cap("SEND_MAIL", "Gửi email đã duyệt", "email", "R2_CONFIRM"),
    _cap("GET_MAIL_DELIVERY_STATUS", "Trạng thái gửi mail", "email", "R0_READ"),
    # ── Liên kết kênh ──
    _cap("GET_CHANNEL_STATUS", "Trạng thái kênh liên kết", "channel", "R0_READ"),
    _cap("ISSUE_MY_BIND_CODE", "Cấp mã liên kết kênh", "channel", "R2_CONFIRM"),
    _cap("BIND_OTHER_CHANNEL", "Liên kết kênh giúp người khác", "channel", "R4_MANUAL_ONLY", "/nguoi", "Chỉ chủ quán cấu hình mapping người khác"),
    # ── Facebook inbox / Page ──
    _cap("GET_FB_INBOX", "Xem hộp thư Fanpage", "fbpage", "R0_READ", "/page-quan/fb-inbox"),
    _cap("DRAFT_FB_REPLY", "Soạn trả lời Fanpage", "fbpage", "R1_DRAFT"),
    _cap("SEND_APPROVED_FB_REPLY", "Gửi trả lời đã duyệt", "fbpage", "R2_CONFIRM", "/page-quan/fb-inbox"),
    _cap("DECIDE_FB_MODERATION", "Duyệt kiểm duyệt FB", "fbpage", "R3_DUAL_APPROVAL", "/page-quan/fb-inbox"),
    _cap("GET_PAGE_STATUS", "Trạng thái Page", "fbpage", "R0_READ", "/page-quan"),
    _cap("SYNC_PAGE", "Đồng bộ Page", "fbpage", "R2_CONFIRM", "/page-quan"),
    _cap("PROPOSE_STORE_PROFILE", "Cập nhật hồ sơ quán", "fbpage", "R3_DUAL_APPROVAL", "/page-quan"),
    _cap("PROPOSE_PROMOTION_UPDATE", "Cập nhật khuyến mãi", "fbpage", "R3_DUAL_APPROVAL", "/page-quan"),
    _cap("DRAFT_FB_POST", "Soạn bài đăng nháp", "fbpage", "R1_DRAFT"),
    _cap("PUBLISH_APPROVED_FB_POST", "Đăng bài đã duyệt", "fbpage", "R3_DUAL_APPROVAL", "/page-quan"),
    # ── Xu hướng ──
    _cap("SEARCH_TRENDS", "Tra cứu xu hướng", "trend", "R0_READ"),
    _cap("GET_TREND_DETAIL", "Chi tiết xu hướng", "trend", "R0_READ"),
    _cap("GET_SCRAPER_USAGE", "Mức dùng Apify", "trend", "R0_READ"),
    # ── Khảo sát giá thị trường (plan 260913-1455) ──
    _cap("RUN_CATCHMENT_SURVEY", "Khảo sát giá bán kính", "market", "R2_CONFIRM", "/khao-sat-gia"),
    _cap("GET_SURVEY_STATUS", "Tiến trình khảo sát giá", "market", "R0_READ", "/khao-sat-gia"),
    _cap("GET_SURVEY_RESULT", "Kết quả khảo sát giá", "market", "R0_READ", "/khao-sat-gia"),
    _cap("REVIEW_SURVEY_ITEMS", "Xác nhận giá OCR", "market", "R2_CONFIRM", "/khao-sat-gia"),
    _cap("GET_SURVEY_METRICS", "Chi phí Vision & nguồn", "market", "R0_READ", "/khao-sat-gia"),
    _cap("GET_SERPAPI_QUOTA", "Xem hạn ngạch SerpApi", "market", "R0_READ", "/khao-sat-gia"),
    # ── AI learning / governance ──
    _cap("GET_AI_QUALITY", "Chất lượng AI", "ai", "R0_READ", "/ai-learning"),
    _cap("SUBMIT_AI_FEEDBACK", "Gửi phản hồi AI", "ai", "R2_CONFIRM", "/ai-learning"),
    _cap("RUN_REFLECTION", "Chạy reflection", "ai", "R1_DRAFT", "/ai-learning"),
    _cap("REVIEW_LEARNED_RULE", "Xem luật AI học được", "ai", "R0_READ", "/ai-learning"),
    _cap("PROPOSE_AI_CIRCUIT_CHANGE", "Thay đổi circuit breaker", "ai", "R3_DUAL_APPROVAL"),
    _cap("PROPOSE_LEARNED_RULE_TRANSITION", "Duyệt luật AI học được", "ai", "R3_DUAL_APPROVAL", "/ai-learning"),
    # ── Audit / chẩn đoán ──
    _cap("QUERY_AUDIT", "Tra cứu audit", "audit", "R0_READ", "/vet"),
    _cap("GET_ACTION_STATUS", "Trạng thái action", "audit", "R0_READ"),
    _cap("GET_MY_PERMISSIONS", "Quyền của tôi", "audit", "R0_READ"),
    _cap("EXPLAIN_CONFLICT", "Giải thích xung đột", "audit", "R0_READ"),
    # ── Điều hướng ──
    _cap("NAVIGATE_TO_FEATURE", "Mở màn hình chức năng", "nav", "R0_READ"),
    # ── Webhook / ingestion (không bao giờ qua chat) ──
    _cap("CONFIGURE_WEBHOOK", "Cấu hình webhook", "channel", "R4_MANUAL_ONLY", "/page-quan", "Webhook là cấu hình bảo mật — chỉ chủ quán thao tác trực tiếp"),
    _cap("REPLAY_INGESTION", "Replay dữ liệu kênh", "channel", "R4_MANUAL_ONLY", "", "Replay ingestion chỉ chạy từ công cụ vận hành, không qua chat"),
)


def capabilities_for_role(role: str) -> list[CapabilityDefinition]:
    """Trả về danh sách capability user với role này được dùng.

    Quy tắc fail-closed (kế hoạch §1.1):
    - R0_READ: mọi role đã xác thực đều được (đọc có tenant scope).
    - R1_DRAFT: mọi role đã xác thực (draft chưa ghi domain).
    - R2_CONFIRM: chỉ quan_ly/chu_quan (khớp ma trận intent ghi hiện có).
    - R3_DUAL_APPROVAL: chỉ quan_ly/chu_quan.
    - R4_MANUAL_ONLY: không role nào được agent thực thi — chỉ deep-link.
    """
    if role not in COPILOT_ROLE_INTENT_MATRIX:
        return []
    privileged = role in ("quan_ly", "chu_quan")
    out: list[CapabilityDefinition] = []
    for cap in CAPABILITY_REGISTRY:
        if cap.risk_tier in ("R0_READ", "R1_DRAFT"):
            out.append(cap)
        elif cap.risk_tier in ("R2_CONFIRM", "R3_DUAL_APPROVAL") and privileged:
            out.append(cap)
    return out


class FbPolicyAction(StrEnum):
    """Hành động kiểm duyệt FB — ma trận §3.2 của kế hoạch chatbot moderation."""

    auto_send = "auto_send"
    queue_review = "queue_review"
    priority_review = "priority_review"
    escalate_owner = "escalate_owner"
    block_polite = "block_polite"
    block_silent = "block_silent"

    # Uppercase aliases
    AUTO_SEND = "auto_send"
    QUEUE_REVIEW = "queue_review"
    PRIORITY_REVIEW = "priority_review"
    ESCALATE_OWNER = "escalate_owner"
    BLOCK_POLITE = "block_polite"
    BLOCK_SILENT = "block_silent"


class PolicyDecision(BaseModel):
    """Kết quả của fb_policy.decide() — tất định, không LLM, không I/O (ADR-002).

    Mang đủ reason + flagged_reasons để tầng API ghi audit (ADR-008: người quyết,
    có dấu vết).
    """

    action: FbPolicyAction
    reason: str
    intent: str
    confidence: float = Field(ge=0.0, le=1.0)
    assigned_role: Literal["quan_ly", "chu_quan"] | None = None
    sla_minutes: int | None = None
    flagged_reasons: list[str] = Field(default_factory=list)


class AIGenerationDraft(BaseModel):
    subject: str | None = None
    body: str = Field(min_length=1)


class AIModelVersion(BaseModel):
    provider: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    model_revision: str | None = None
    temperature: float = Field(ge=0.0, le=2.0)
    tool_context_hash: str = Field(min_length=1)


class AIGenerationRecord(BaseModel):
    id: str = Field(min_length=1)
    store_id: str = Field(min_length=1)
    channel: Literal["gmail", "facebook"]
    conversation_id: str | None = None
    request_kind: Literal["gmail_request", "facebook_message", "facebook_comment"]
    external_event_hash: str | None = None
    draft: AIGenerationDraft
    context_snapshot_hash: str = Field(min_length=1)
    verified_fact_refs: list[str] = Field(default_factory=list)
    missing_context: bool = False
    agent_version: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)
    rule_version: str = Field(min_length=1)
    rollout_bucket: Literal["control", "canary_10", "canary_50", "active_100"]
    model: AIModelVersion
    policy_action: FbPolicyAction
    idempotency_key: str = Field(min_length=1)
    created_at: str = Field(min_length=1)


class AIFeedbackContent(BaseModel):
    subject: str | None = None
    body: str | None = None


class AIFeedbackEvent(BaseModel):
    id: str = Field(min_length=1)
    store_id: str = Field(min_length=1)
    generation_id: str = Field(min_length=1)
    channel: Literal["gmail", "facebook"]
    type: Literal[
        "manager_approve",
        "manager_edit",
        "manager_reject",
        "customer_positive",
        "customer_negative",
        "customer_followup",
        "send_success",
        "send_failure",
        "manual_rating",
    ]
    original: AIFeedbackContent | None = None
    final: AIFeedbackContent | None = None
    edited_fields: list[Literal["subject", "body"]] = Field(default_factory=list)
    materially_edited: bool = False
    actor_user_id: str | None = None
    actor_role: Literal["chu_quan", "quan_ly", "system", "customer"]
    send_status: Literal["not_applicable", "sent", "failed"] = "not_applicable"
    failure_code: str | None = None
    idempotency_key: str = Field(min_length=1)
    created_at: str = Field(min_length=1)


class AIEvaluationScores(BaseModel):
    accuracy: float = Field(ge=0.0, le=1.0)
    safety: float = Field(ge=0.0, le=1.0)
    completeness: float | None = Field(default=None, ge=0.0, le=1.0)
    tone: float | None = Field(default=None, ge=0.0, le=1.0)
    naturalness: float | None = Field(default=None, ge=0.0, le=1.0)
    personalization: float | None = Field(default=None, ge=0.0, le=1.0)
    actionability: float | None = Field(default=None, ge=0.0, le=1.0)
    policy_compliance: float | None = Field(default=None, ge=0.0, le=1.0)
    intent_fit: float | None = Field(default=None, ge=0.0, le=1.0)
    emotional_fit: float | None = Field(default=None, ge=0.0, le=1.0)
    resolution_likelihood: float | None = Field(default=None, ge=0.0, le=1.0)


class AIEvaluation(BaseModel):
    id: str = Field(min_length=1)
    store_id: str = Field(min_length=1)
    generation_id: str = Field(min_length=1)
    channel: Literal["gmail", "facebook"]
    scores: AIEvaluationScores
    aggregate_score: float = Field(ge=0.0, le=1.0)
    passed: bool
    action: FbPolicyAction
    hard_fail_flags: list[str] = Field(default_factory=list)
    flags: list[str] = Field(default_factory=list)
    threshold_version: str = Field(min_length=1)
    calibration_version: str = Field(min_length=1)
    sample_count: int = Field(ge=0)
    evaluation_window: str = Field(min_length=1)
    evaluator: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=1)
    created_at: str = Field(min_length=1)


class AIRuleDefinition(BaseModel):
    text: str = Field(min_length=1)
    intent_scope: list[str] = Field(min_length=1)
    audience_scope: list[str] = Field(min_length=1)
    priority: int = Field(ge=0)


class AIRuleRollout(BaseModel):
    mode: Literal["none", "canary", "full"] = "none"
    percentage: int = Field(default=0, ge=0, le=100)
    min_sample: int = Field(default=20, ge=1)
    start_at: str | None = None
    end_at: str | None = None


class AIRuleProposal(BaseModel):
    id: str = Field(min_length=1)
    store_id: str = Field(min_length=1)
    channel: Literal["gmail", "facebook"]
    rule_type: Literal["style", "prompt", "playbook", "safety"]
    rule: AIRuleDefinition
    evidence_count: int = Field(ge=1)
    evidence_ids: list[str] = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    status: Literal[
        "pending",
        "conflict_pending",
        "approved",
        "active",
        "paused",
        "rolled_back",
        "rejected",
    ] = "pending"
    version: int = Field(ge=1)
    rollback_target_version: int | None = Field(default=None, ge=1)
    rollout: AIRuleRollout = Field(default_factory=AIRuleRollout)
    approved_by: str | None = None
    approved_at: str | None = None
    rejection_reason: str | None = None
    idempotency_key: str = Field(min_length=1)
    created_at: str = Field(min_length=1)
    updated_at: str = Field(min_length=1)


class TableReservation(BaseModel):
    id: str
    store_id: str = "quan_01"
    psid: str = ""
    customer_name: str
    phone: str
    booking_time: str
    party_size: int = Field(ge=1)
    duration_minutes: int = 120
    table_ids: list[str] = Field(default_factory=list)
    status: Literal[
        "held", "confirmed", "seated", "completed", "cancelled", "no_show", "needs_review"
    ] = "confirmed"
    source: Literal["ai_auto", "staff_manual"] = "ai_auto"
    notes: str = ""
    idempotency_key: str = ""
    notified_nv_id: str | None = None
    notification_acked_at: str | None = None
    cancelled_by: str | None = None
    cancelled_reason: str | None = None
    created_at: str = ""
    updated_at: str = ""


# ── Gmail Management Contracts ──────────────────────────────────────────

class GmailAccount(BaseModel):
    id: str
    store_id: str = "quan_01"
    nv_id: str
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    display_name: str = ""
    is_primary: bool = False
    is_active: bool = True
    created_at: str
    updated_at: str


class GmailOAuthTokens(BaseModel):
    account_id: str
    access_token: str
    refresh_token: str | None = None
    expires_at: str
    scope: str = ""
    token_type: str = "Bearer"
    updated_at: str


class GmailSyncState(BaseModel):
    account_id: str
    last_history_id: str | None = None
    last_sync_at: str | None = None
    sync_cursor: str | None = None
    total_messages: int = 0
    unread_count: int = 0
    updated_at: str


class GmailMessage(BaseModel):
    id: str
    account_id: str
    thread_id: str
    label_ids: list[str] = Field(default_factory=list)
    snippet: str = ""
    from_email: str = ""
    to_emails: list[str] = Field(default_factory=list)
    cc_emails: list[str] = Field(default_factory=list)
    subject: str = ""
    body_text: str | None = None
    body_html: str | None = None
    internal_date: str
    is_read: bool = False
    is_starred: bool = False
    has_attachment: bool = False
    raw_headers: str | None = None
    created_at: str


class GmailLabel(BaseModel):
    id: str
    account_id: str
    name: str
    label_type: Literal["system", "user"] = "user"
    message_list_visibility: Literal["show", "hide"] = "show"
    label_list_visibility: Literal["labelShow", "labelHide"] = "labelShow"
    color_background: str | None = None
    color_text: str | None = None
    total_messages: int = 0
    unread_messages: int = 0
    updated_at: str


class GmailFilter(BaseModel):
    id: str
    account_id: str
    criteria: dict[str, Any] = Field(default_factory=dict)
    action: dict[str, Any] = Field(default_factory=dict)
    created_at: str
    updated_at: str


class GmailThread(BaseModel):
    id: str
    account_id: str
    message_ids: list[str] = Field(default_factory=list)
    subject: str = ""
    participants: list[str] = Field(default_factory=list)
    last_message_date: str = ""
    is_unread: bool = False
    label_ids: list[str] = Field(default_factory=list)


class GmailOAuthAuthorizeRequest(BaseModel):
    state: str | None = None


class GmailOAuthAuthorizeResponse(BaseModel):
    authorization_url: str
    state: str


class GmailOAuthCallbackRequest(BaseModel):
    code: str
    state: str


class GmailOAuthCallbackResponse(BaseModel):
    ok: bool
    account_id: str
    email: str
    message: str


class GmailAccountCreateRequest(BaseModel):
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    display_name: str = Field(default="", max_length=100)
    is_primary: bool = False


class GmailAccountUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, max_length=100)
    is_primary: bool | None = None
    is_active: bool | None = None


class GmailMessageListParams(BaseModel):
    label_ids: list[str] | None = None
    query: str | None = None
    is_read: bool | None = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class GmailLabelCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    label_list_visibility: Literal["labelShow", "labelHide"] = "labelShow"
    message_list_visibility: Literal["show", "hide"] = "show"
    color_background: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    color_text: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")


class GmailLabelUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    label_list_visibility: Literal["labelShow", "labelHide"] | None = None
    message_list_visibility: Literal["show", "hide"] | None = None
    color_background: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    color_text: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")


class GmailFilterCreateRequest(BaseModel):
    criteria: dict[str, Any] = Field(default_factory=dict)
    action: dict[str, Any] = Field(default_factory=dict)


class GmailSyncRequest(BaseModel):
    account_id: str | None = None
    full_sync: bool = False


class GmailSendMessageRequest(BaseModel):
    to: list[str] = Field(min_length=1)
    subject: str = Field(min_length=1, max_length=200)
    body_text: str = Field(min_length=1, max_length=50000)
    body_html: str | None = None
    cc: list[str] | None = None
    bcc: list[str] | None = None
    thread_id: str | None = None
    in_reply_to: str | None = None
    references: str | None = None


CONTRACTS = {
    "NhanVien": NhanVien,
    "Ca": Ca,
    "LichTuan": LichTuan,
    "PhieuMau": PhieuMau,
    "RangBuocTrichXuat": RangBuocTrichXuat,
    "MonNuoc": MonNuoc,
    "DonQuay": DonQuay,
    "DongDon": DongDon,
    "CuocHop": CuocHop,
    "ActionItem": ActionItem,
    "DeXuatSop": DeXuatSop,
    "DeXuatPheDuyet": DeXuatPheDuyet,
    "GopYLuuY": GopYLuuY,
    "AuditTuanThuSop": AuditTuanThuSop,
    "BanTinCaKhan": BanTinCaKhan,
    "HuanLuyenQuanLy": HuanLuyenQuanLy,
    "CopilotMessage": CopilotMessage,
    "ActionProposal": ActionProposal,
    "PolicyDecision": PolicyDecision,
    "AIGenerationRecord": AIGenerationRecord,
    "AIFeedbackEvent": AIFeedbackEvent,
    "AIEvaluation": AIEvaluation,
    "AIRuleProposal": AIRuleProposal,
    "TableReservation": TableReservation,
    # ── Grand AI Experience Portfolio (plan 260920-1442) ──
    # Lưu ý: chỉ BaseModel mới vào CONTRACTS (để sinh schema/TS). StrEnum
    # (ExperienceRole, ExperienceProposalStatus...) export qua __all__.
    "SpatialAnchor": SpatialAnchor,
    "ExperienceEvent": ExperienceEvent,
    "VoiceTurn": VoiceTurn,
    "ExperienceMemory": ExperienceMemory,
    "ExperienceActionProposal": ExperienceActionProposal,
    "WarRoomScenario": WarRoomScenario,
    "WarRoomOption": WarRoomOption,
    "WarRoomComparison": WarRoomComparison,
    "RuleCandidate": RuleCandidate,
    "ShadowTestResult": ShadowTestResult,
    "RescueCandidate": RescueCandidate,
    "RescueCase": RescueCase,
    "ZoneProjection": ZoneProjection,
    "PublicEventProjection": PublicEventProjection,
    "ModeProjection": ModeProjection,
    "HorizonItem": HorizonItem,
    "DataQualityNotice": DataQualityNotice,
    "LivingCafeSnapshot": LivingCafeSnapshot,
    # Trợ lý Quánverse — lớp tường thuật tất định trên dữ liệu hệ thống
    "QuanverseMetric": QuanverseMetric,
    "QuanverseBrief": QuanverseBrief,
    "QuanverseAskRequest": QuanverseAskRequest,
    "QuanverseAskResponse": QuanverseAskResponse,
    # ── Hao hụt tiêu thụ theo nguyên liệu (plan 260923-1736) ──
    # Chỉ BaseModel vào CONTRACTS; LossLevel/LossBasis/LossCauseSource export qua __all__.
    "LossLine": LossLine,
    "LossCauseRank": LossCauseRank,
    "LossSummary": LossSummary,
    "LossThreshold": LossThreshold,
    # ── HỒN QUÁN Spatial Memory (Phase 05) ──
    "MemoryQuery": MemoryQuery,
    "MemoryProposal": MemoryProposal,
    "MemoryConsentRequest": MemoryConsentRequest,
    "MemoryAuditEntry": MemoryAuditEntry,
    "GroundedAnswer": GroundedAnswer,
    "TourStep": TourStep,
    "TourPlan": TourPlan,
    "VoiceTurnRequest": VoiceTurnRequest,
    "VoiceTurnResponse": VoiceTurnResponse,
    # ── Gmail Management ──
    "GmailAccount": GmailAccount,
    "GmailOAuthTokens": GmailOAuthTokens,
    "GmailSyncState": GmailSyncState,
    "GmailMessage": GmailMessage,
    "GmailLabel": GmailLabel,
    "GmailFilter": GmailFilter,
    "GmailThread": GmailThread,
    "GmailOAuthAuthorizeRequest": GmailOAuthAuthorizeRequest,
    "GmailOAuthAuthorizeResponse": GmailOAuthAuthorizeResponse,
    "GmailOAuthCallbackRequest": GmailOAuthCallbackRequest,
    "GmailOAuthCallbackResponse": GmailOAuthCallbackResponse,
    "GmailAccountCreateRequest": GmailAccountCreateRequest,
    "GmailAccountUpdateRequest": GmailAccountUpdateRequest,
    "GmailMessageListParams": GmailMessageListParams,
    "GmailLabelCreateRequest": GmailLabelCreateRequest,
    "GmailLabelUpdateRequest": GmailLabelUpdateRequest,
    "GmailFilterCreateRequest": GmailFilterCreateRequest,
    "GmailSyncRequest": GmailSyncRequest,
    "GmailSendMessageRequest": GmailSendMessageRequest,
}

__all__ = [
    "CONTRACTS",
    "CatchmentSurveyParams",
    "StoreCandidate",
    "TrendItem",
    # Re-export từ module con (public API) — giữ để không bị ruff F401
    "CausalChain",
    "CausalLink",
    "CausalNode",
    "CausalNodeType",
    "Episode",
    "EpisodeType",
    "Reflection",
    "ReflectionResult",
    "PositiveRule",
    "PositiveRuleStatus",
    "PredictResponse",
    "SuccessPattern",
    "SuccessPatternSource",
    "SuccessPatternType",
    "TwinScenario",
    "TwinScenarioType",
    "VirtualSimulation",
    "VirtualStaff",
    "VirtualStaffType",
    "ExperienceRole",
    "ExperienceProposalStatus",
    "SpatialAnchor",
    "ExperienceEvent",
    "ExperienceEventType",
    "VoiceTurn",
    "ExperienceMemory",
    "MemoryConsentStatus",
    "MemoryVisibility",
    "MemoryStatus",
    "ExperienceActionProposal",
    "ExperienceCapability",
    "WarRoomScenarioType",
    "WarRoomScenario",
    "WarRoomOption",
    "WarRoomComparison",
    "ExperienceMode",
    "RuleCandidate",
    "ShadowTestResult",
    "RescueCaseStatus",
    "RescueCandidate",
    "RescueCase",
    "ZoneProjection",
    "PublicEventProjection",
    "ModeProjection",
    "HorizonItem",
    "DataQualityNotice",
    "LivingCafeSnapshot",
    # Trợ lý Quánverse — enum export qua __all__ (không vào CONTRACTS)
    "QuanversePage",
    "QuanverseMetric",
    "QuanverseBrief",
    "QuanverseAskRequest",
    "QuanverseAskResponse",
    "experience_capabilities_for_role",
    "experience_role_can",
    "AnchorQuery",
    "MemoryQuery",
    "MemoryProposal",
    "MemoryConsentRequest",
    "MemoryAuditEntry",
    "GroundedAnswer",
    "TourStep",
    "TourPlan",
    "VoiceTurnRequest",
    "VoiceTurnResponse",
    # Hao hụt tiêu thụ theo nguyên liệu — enum export qua __all__ (không vào CONTRACTS)
    "LossLevel",
    "LossBasis",
    "LossCauseSource",
    # Bốn kiểu dữ liệu hao hụt dưới đây được import ở đầu file và dùng bởi
    # `ca_api.interfaces.http.hao_hut`, nhưng trước đây thiếu trong __all__ nên
    # mypy strict báo `attr-defined` ("không export tường minh"). Bổ sung để
    # API hao hụt import được qua `from ca_contracts import ...`.
    "LossLine",
    "LossSummary",
    "LossCauseRank",
    "LossThreshold",
    # ── Gmail Management ──
    "GmailAccount",
    "GmailOAuthTokens",
    "GmailSyncState",
    "GmailMessage",
    "GmailLabel",
    "GmailFilter",
    "GmailThread",
    "GmailOAuthAuthorizeRequest",
    "GmailOAuthAuthorizeResponse",
    "GmailOAuthCallbackRequest",
    "GmailOAuthCallbackResponse",
    "GmailAccountCreateRequest",
    "GmailAccountUpdateRequest",
    "GmailMessageListParams",
    "GmailLabelCreateRequest",
    "GmailLabelUpdateRequest",
    "GmailFilterCreateRequest",
    "GmailSyncRequest",
    "GmailSendMessageRequest",
]

