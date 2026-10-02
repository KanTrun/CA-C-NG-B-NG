"""Orchestrator v2 — điều phối job khảo sát bất đồng bộ (plan mục 2.3, 2.4).

State machine:
    QUEUED → SCRAPING_ONLINE → SCRAPING_DINEIN → OCR_PROCESSING
           → {AGGREGATING | NEEDS_REVIEW | FAILED}
    NEEDS_REVIEW → {AGGREGATING | FAILED}
    AGGREGATING → {COMPLETED | FAILED}

ADR-002: mọi con số nghiệp vụ đến từ `math_layer` (hàm thuần). Module này chỉ
điều phối I/O và lắp ráp contract.
ADR-008: NEEDS_REVIEW là ĐIỂM DỪNG THẬT — chỉ `resume_after_review` (do người
dùng gọi qua API) mới đưa job sang AGGREGATING. Không có auto-approve.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import urllib.request
from datetime import datetime, timezone
from typing import Any

from ca_contracts.catchment_survey import DishItem, StoreCandidate
from ca_contracts.catchment_survey_v2 import (
    AreaContext,
    CatchmentSurveyRequest,
    CatchmentSurveyResponse,
    ChannelMode,
    MenuItemPrice,
    MenuSnapshotV2,
    PositioningTier,
    StoreRecord,
    SubstituteCategoryStats,
    SubstitutePriceComparison,
    SurveyErrorCode,
    SurveyJobStatus,
    SurveyReviewSubmission,
)

from ca_agents.ag_pricing.dish_name_normalizer import normalize_dish_name
from ca_agents.ag_pricing.job_manager import JobStore, SurveyJob, get_job_store
from ca_agents.ag_pricing.math_layer import (
    check_cost_plus_warning,
    collect_sweet_spot_prices,
    competitive_intensity,
    compute_ambi,
    compute_percentile_stats,
    compute_sweet_spot,
    filter_valid_prices,
    is_low_confidence,
    min_viable_price,
    passes_gates,
    weighted_rating,
)
from ca_agents.ag_pricing.pricing_config import PricingConfig, load_pricing_config
from ca_agents.ag_pricing.substitute_taxonomy import (
    SubstituteTaxonomyError,
    SubstituteTaxonomyIndex,
    normalize_category_name,
    union_core_and_substitutes,
)
from ca_agents.ag_pricing.vision_menu_extractor import extract_menu_from_image
from ca_agents.clients.camoufox_client import CamoufoxUnavailable
from ca_agents.sources.delivery_camoufox_source import scrape_delivery_stores_camoufox
from ca_agents.sources.gmaps_menu_source import scrape_gmaps_menu_images_camoufox

logger = logging.getLogger(__name__)

_IMAGE_TIMEOUT_S = 10.0
_IMAGE_MAX_BYTES = 8 * 1024 * 1024
_UA = "Mozilla/5.0 (compatible; nhipquan-pricing-radar/2.1)"

#: Ngân sách thời gian mặc định cho cả lượt khảo sát (giây). Job PHẢI kết thúc ở
#: một trạng thái cuối trong hạn này; hết hạn thì `FAILED` với mã `SOURCE_BLOCKED`.
#: Trước đây không có hạn nào: cào delivery có thể treo ở `page.goto` mãi mãi, và
#: job nằm im ở `scraping_online` cho tới khi worker bị restart (sự cố 2026-10-02).
_JOB_BUDGET_MAC_DINH_S = 300.0
_JOB_BUDGET_BIEN = "CA_SURVEY_JOB_BUDGET_S"


def _job_budget_s() -> float:
    """Đọc ngân sách tại thời điểm chạy để cấu hình lại (và test) có hiệu lực."""
    try:
        return max(1.0, float(os.getenv(_JOB_BUDGET_BIEN, str(_JOB_BUDGET_MAC_DINH_S))))
    except ValueError:
        return _JOB_BUDGET_MAC_DINH_S


class _JobDeadline:
    """Đồng hồ đếm ngược cho một lượt khảo sát.

    Các nguồn dữ liệu là thư viện đồng bộ (urllib, camoufox) không nhận huỷ giữa
    chừng, nên ngân sách được áp bằng hai lớp: (1) cắt timeout truyền xuống tầng
    I/O theo thời gian còn lại, (2) kiểm tra trước mỗi bước để không bắt đầu một
    bước chắc chắn không kịp.
    """

    def __init__(self, tong_giay: float | None = None) -> None:
        self.tong_giay = _job_budget_s() if tong_giay is None else max(1.0, tong_giay)
        self._ket_thuc = time.monotonic() + self.tong_giay

    @property
    def con_lai_s(self) -> float:
        return self._ket_thuc - time.monotonic()

    def het_han(self, toi_thieu_s: float = 0.0) -> bool:
        return self.con_lai_s <= toi_thieu_s

    def ep_het_han(self) -> None:
        """Đánh dấu ngân sách đã cạn (dùng cho test tất định)."""
        self._ket_thuc = time.monotonic() - 1.0

    def con(self, mac_dinh_s: float) -> float:
        """Thời gian còn lại, hoặc `mac_dinh_s` khi ngân sách đã cạn."""
        con_lai = self.con_lai_s
        return mac_dinh_s if con_lai <= 0 else min(mac_dinh_s, con_lai)


class SurveyExecutionError(Exception):
    """Lỗi điều phối có mã lỗi kèm theo (plan mục 5.3)."""

    def __init__(self, code: SurveyErrorCode, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"{code.value}: {message}")


# ── Observability / cost (plan mục 9) ────────────────────────────────────────

_METRICS_LOCK = threading.RLock()
_METRICS: dict[str, Any] = {
    "jobs_created": 0,
    "jobs_completed": 0,
    "jobs_failed": 0,
    "jobs_needs_review": 0,
    "failures_by_code": {},
    "vision_calls": 0,
    "vision_errors": 0,
    "images_downloaded": 0,
    "images_failed": 0,
    "image_bytes_downloaded": 0,
    # Số lượt mở trình duyệt anti-detect (Camoufox qua proxy). Mỗi lượt là một
    # khoản chi phí biến đổi thật, nên phải đếm riêng với số lượt gọi Vision.
    "proxy_requests": 0,
}


def get_pricing_metrics() -> dict[str, Any]:
    """Snapshot metrics chi phí + độ tin cậy nguồn (plan mục 9)."""
    with _METRICS_LOCK:
        return {
            **{k: v for k, v in _METRICS.items() if k != "failures_by_code"},
            "failures_by_code": dict(_METRICS["failures_by_code"]),
        }


def reset_pricing_metrics() -> None:
    """Xóa metrics (dùng cho test)."""
    with _METRICS_LOCK:
        for key in _METRICS:
            _METRICS[key] = {} if key == "failures_by_code" else 0


def _bump(key: str, amount: int = 1) -> None:
    with _METRICS_LOCK:
        _METRICS[key] = _METRICS.get(key, 0) + amount


def _bump_failure(code: SurveyErrorCode) -> None:
    with _METRICS_LOCK:
        bucket = _METRICS["failures_by_code"]
        bucket[code.value] = bucket.get(code.value, 0) + 1


def _kiem_tra_han(deadline: _JobDeadline, buoc: str) -> None:
    """Dừng job khi đã cạn ngân sách thời gian — không bắt đầu bước chắc chắn trễ."""
    if deadline.het_han():
        raise SurveyExecutionError(
            SurveyErrorCode.SOURCE_BLOCKED,
            f"het_thoi_gian_cho_phep sau bước {buoc} (ngân sách {deadline.tong_giay:.0f}s)",
        )


# ── Log có cấu trúc (plan mục 9) ─────────────────────────────────────────────
#
# Plan yêu cầu "logging có cấu trúc (JSON logs) cho từng bước trong State Machine,
# gắn `job_id` xuyên suốt để truy vết". Ở đây phát JSON trong CHUỖI log chứ không
# thay Formatter toàn cục: đổi Formatter là đổi định dạng log của cả API, nằm ngoài
# phạm vi tính năng này và sẽ phá log parsing của các agent khác.


def _log_job(
    job_id: str,
    su_kien: str,
    *,
    muc: int = logging.INFO,
    **truong: Any,
) -> None:
    """Ghi một dòng log JSON: `{"job_id", "su_kien", ...}`.

    `json.dumps(..., default=str)` để enum/datetime rơi vào đây vẫn serialize được
    thay vì làm nổ ngay chỗ ghi log — log hỏng thì mất khả năng truy vết, tệ hơn
    là log thiếu một trường.
    """
    payload = {"job_id": job_id, "su_kien": su_kien, **truong}
    logger.log(muc, json.dumps(payload, ensure_ascii=False, default=str))


def _download_image(url: str, *, timeout_s: float = _IMAGE_TIMEOUT_S) -> bytes:
    """Tải ảnh menu. Trả b"" khi không tải được — KHÔNG raise: một ảnh hỏng
    không được làm sập cả job khảo sát."""
    if not url or not url.lower().startswith(("http://", "https://")):
        return b""
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:  # noqa: S310
            data: bytes = resp.read(_IMAGE_MAX_BYTES)
    except Exception as exc:  # noqa: BLE001 — nguồn bên thứ ba, mọi lỗi đều bỏ qua được
        logger.info("Tải ảnh menu thất bại (%s): %s", url[:80], exc)
        _bump("images_failed")
        return b""
    if data:
        _bump("images_downloaded")
        _bump("image_bytes_downloaded", len(data))
    return data


def _dish_to_menu_item(dish: DishItem, *, channel: ChannelMode) -> MenuItemPrice:
    """DishItem (v1) → MenuItemPrice (v2).

    Scraper delivery chỉ bắt được MỘT mức giá. Không có tín hiệu khuyến mãi thì
    original = effective và `is_promotional=False` — KHÔNG suy ngược giá gốc
    (plan mục 1.5.2: bịa giá gốc sẽ kéo AMBI sai).
    """
    price = max(0, int(dish.price or 0))
    name = dish.name
    return MenuItemPrice(
        item_name_raw=name,
        item_name_normalized=normalize_dish_name(name),
        original_price_vnd=price or None,
        effective_price_vnd=price,
        is_promotional=False,
        is_combo="combo" in name.lower() or "set" in name.lower(),
        portion_note=None,
        source_channel=channel,
        confidence="medium",
        is_fallback_derived=False,
    )


class SurveyOrchestrator:
    """Điều phối toàn bộ một lượt khảo sát theo state machine."""

    def __init__(
        self,
        job_store: JobStore | None = None,
        config: PricingConfig | None = None,
        taxonomy: SubstituteTaxonomyIndex | None = None,
    ) -> None:
        self.job_store = job_store or get_job_store()
        self.config = config or load_pricing_config()
        self._taxonomy = taxonomy

    @property
    def taxonomy(self) -> SubstituteTaxonomyIndex | None:
        """Lazy-load taxonomy: thiếu file config không được làm sập job."""
        if self._taxonomy is None:
            try:
                self._taxonomy = SubstituteTaxonomyIndex.from_file()
            except SubstituteTaxonomyError as exc:
                logger.warning("Không nạp được substitute taxonomy: %s", exc)
                self._taxonomy = None
        return self._taxonomy

    # ── Vòng đời job ─────────────────────────────────────────────────────────

    def create_job(self, request: CatchmentSurveyRequest) -> SurveyJob:
        job = self.job_store.create_job(request)
        _bump("jobs_created")
        logger.info(
            "Tạo job khảo sát %s (category=%s, channel=%s)",
            job.job_id, request.core_category, request.channel_mode.value,
        )
        return job

    def execute_job(self, job_id: str) -> SurveyJob:
        """Chạy job đến COMPLETED / NEEDS_REVIEW / FAILED (blocking).

        Luôn kết thúc ở một trạng thái cuối trong hạn `_JOB_BUDGET_S`; hết hạn thì
        `FAILED` với `SOURCE_BLOCKED` thay vì để job nằm im ở trạng thái trung gian.
        """
        job = self.job_store.get_job(job_id)
        if job is None:
            raise KeyError(f"job_khong_ton_tai: {job_id}")
        if job.status != SurveyJobStatus.QUEUED:
            raise SurveyExecutionError(
                SurveyErrorCode.INVALID_RADIUS,
                f"job {job_id} đang ở trạng thái {job.status.value}, không thể chạy lại",
            )

        deadline = _JobDeadline()
        _log_job(job_id, "job_started", ngan_sach_giay=round(deadline.tong_giay, 1))

        try:
            self._advance(job, SurveyJobStatus.SCRAPING_ONLINE)
            online_raw = self._scrape_online(job.request, deadline)

            _kiem_tra_han(deadline, "quet_kenh_delivery")
            self._advance(job, SurveyJobStatus.SCRAPING_DINEIN)
            dinein_raw = self._scrape_dinein(job.request, deadline)

            online_records = self._to_records(
                online_raw, job.request, ChannelMode.DELIVERY_PLATFORM
            )
            dinein_records = self._to_records(
                dinein_raw, job.request, ChannelMode.DINE_IN_VISION
            )

            _kiem_tra_han(deadline, "quet_quan_tai_cho")
            self._advance(job, SurveyJobStatus.OCR_PROCESSING)
            snapshots, pending = self._process_ocr(dinein_raw, dinein_records, job.request)
            self._attach_dinein_items(dinein_records, snapshots)

            self._stash(job, online_records, dinein_records, snapshots, pending)

            if pending:
                job.add_flagged_stores(sorted({p["store_id"] for p in pending}))
                self._advance(job, SurveyJobStatus.NEEDS_REVIEW)
                _bump("jobs_needs_review")
                # ADR-008: đây là điểm dừng thật, nên log phải nói rõ đang chờ AI.
                _log_job(
                    job_id,
                    "needs_review",
                    so_dong_cho=len(pending),
                    so_quan=len(job.stores_flagged_for_review),
                    cho_nguoi_xac_nhan=True,
                )
                return job

            self._finish_aggregation(job)

        except SurveyExecutionError as exc:
            self._fail(job, exc.code, exc.message)
        except CamoufoxUnavailable as exc:
            self._fail(job, SurveyErrorCode.SOURCE_BLOCKED, f"camoufox_khong_kha_dung: {exc}")
        except Exception as exc:  # noqa: BLE001 — job phải luôn kết thúc ở một trạng thái
            logger.exception("Job %s lỗi ngoài dự kiến", job_id)
            self._fail(job, SurveyErrorCode.VISION_QUOTA_EXCEEDED, str(exc))

        return job

    def resume_after_review(
        self,
        job_id: str,
        submission: SurveyReviewSubmission | None = None,
    ) -> SurveyJob:
        """Tiếp tục job sau khi chủ quán xác nhận các dòng NEEDS_REVIEW (ADR-008).

        Giá do người dùng nhập được đánh dấu `confidence="high"` — đây là dữ liệu
        đã có người chịu trách nhiệm, không còn là suy đoán của OCR.
        """
        job = self.job_store.get_job(job_id)
        if job is None:
            raise KeyError(f"job_khong_ton_tai: {job_id}")
        if job.status != SurveyJobStatus.NEEDS_REVIEW:
            raise SurveyExecutionError(
                SurveyErrorCode.INVALID_RADIUS,
                f"job {job_id} ở trạng thái {job.status.value}, không phải needs_review",
            )

        submission = submission or SurveyReviewSubmission()
        _log_job(
            job_id,
            "review_received",
            so_dong=len(submission.items),
            approve_all_remaining=submission.approve_all_remaining,
            reviewed_by=submission.reviewed_by,
        )
        records = self._apply_review(job, submission)
        try:
            self._advance(job, SurveyJobStatus.AGGREGATING)
            self._aggregate_and_complete(job, **records)
        except SurveyExecutionError as exc:
            self._fail(job, exc.code, exc.message)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Job %s lỗi khi tổng hợp sau review", job_id)
            self._fail(job, SurveyErrorCode.VISION_QUOTA_EXCEEDED, str(exc))
        return job

    # ── State helpers ────────────────────────────────────────────────────────

    def _advance(self, job: SurveyJob, status: SurveyJobStatus) -> None:
        truoc = job.status.value
        job.transition_to(status)
        self.job_store.update_job(job)
        _log_job(
            job.job_id,
            "state_transition",
            tu=truoc,
            den=status.value,
            updated_at=job.updated_at,
        )

    def _fail(self, job: SurveyJob, code: SurveyErrorCode, message: str) -> None:
        job.mark_failed(code, message)
        _bump("jobs_failed")
        _bump_failure(code)
        self.job_store.update_job(job)
        _log_job(
            job.job_id,
            "job_failed",
            muc=logging.WARNING,
            error_code=code.value,
            error_message=message,
        )

    def _stash(
        self,
        job: SurveyJob,
        online: list[StoreRecord],
        dinein: list[StoreRecord],
        snapshots: list[MenuSnapshotV2],
        pending: list[dict[str, Any]],
    ) -> None:
        """Giữ trạng thái trung gian để `resume_after_review` không phải cào lại."""
        job.meta["online_records"] = online
        job.meta["dinein_records"] = dinein
        job.meta["ocr_snapshots"] = snapshots
        job.meta["pending_review"] = pending
        self.job_store.update_job(job)

    def _finish_aggregation(self, job: SurveyJob) -> None:
        self._advance(job, SurveyJobStatus.AGGREGATING)
        self._aggregate_and_complete(
            job,
            online_records=job.meta.get("online_records", []),
            dinein_records=job.meta.get("dinein_records", []),
            snapshots=job.meta.get("ocr_snapshots", []),
        )

    def _aggregate_and_complete(
        self,
        job: SurveyJob,
        *,
        online_records: list[StoreRecord],
        dinein_records: list[StoreRecord],
        snapshots: list[MenuSnapshotV2],
    ) -> None:
        response = self._aggregate_results(
            job.request, online_records, dinein_records, snapshots, job_id=job.job_id
        )
        job.set_response(response)
        self._advance(job, SurveyJobStatus.COMPLETED)
        _bump("jobs_completed")
        _log_job(
            job.job_id,
            "job_completed",
            created_at=job.created_at,
            updated_at=job.updated_at,
            ambi=getattr(response.substitute_comparison, "ambi", None),
        )

    # ── Scraping ─────────────────────────────────────────────────────────────

    def _scrape_online(
        self,
        request: CatchmentSurveyRequest,
        deadline: _JobDeadline,
    ) -> list[StoreCandidate]:
        if request.channel_mode == ChannelMode.DINE_IN_VISION:
            return []
        _bump("proxy_requests")
        return scrape_delivery_stores_camoufox(
            request.latitude,
            request.longitude,
            request.core_category,
            radius_km=request.radius_profile.delivery_km,
            deadline_s=deadline.con_lai_s,
        )

    def _scrape_dinein(
        self,
        request: CatchmentSurveyRequest,
        deadline: _JobDeadline,
    ) -> list[StoreCandidate]:
        if request.channel_mode == ChannelMode.DELIVERY_PLATFORM:
            return []
        _bump("proxy_requests")
        return scrape_gmaps_menu_images_camoufox(
            request.latitude,
            request.longitude,
            request.core_category,
            radius_km=request.radius_profile.dine_in_km,
            max_images=request.max_menu_images_per_store,
            deadline_s=deadline.con_lai_s,
        )

    def _to_records(
        self,
        raw_stores: list[StoreCandidate],
        request: CatchmentSurveyRequest,
        channel: ChannelMode,
    ) -> list[StoreRecord]:
        """Dual-Gate (plan mục 4.2) + chuyển sang contract v2.

        Quán rớt gate vẫn nằm trong danh sách (cờ `passed_gate*` = False) để UI
        diễn giải lý do; tầng tổng hợp mới là nơi lọc ra tập mẫu.
        """
        records: list[StoreRecord] = []
        for raw in raw_stores:
            if not raw.name.strip():
                continue
            wr = weighted_rating(
                raw.review_count,
                raw.rating,
                m=self.config.dual_gate.bayes_m,
                prior_c=self.config.dual_gate.bayes_prior_c,
            )
            record = StoreRecord(
                store_id=raw.id or raw.place_id or raw.name,
                name=raw.name,
                lat=raw.lat or request.latitude,
                lng=raw.lng or request.longitude,
                review_count=raw.review_count,
                rating=raw.rating,
                weighted_rating=round(min(5.0, max(0.0, wr)), 4),
                passed_gate1=False,
                passed_gate2=False,
                has_favorite_badge=raw.is_favorite,
                low_confidence=False,
                positioning_tier_suggested=request.positioning_tier,
                menu_items=(
                    [_dish_to_menu_item(d, channel=channel) for d in raw.dishes]
                    if channel == ChannelMode.DELIVERY_PLATFORM
                    else []
                ),
            )
            gate1, gate2 = passes_gates(
                record,
                min_v=request.min_review_count,
                min_r=request.min_rating,
                min_wr=self.config.dual_gate.min_weighted_rating,
            )
            record.passed_gate1 = gate1
            record.passed_gate2 = gate2
            record.low_confidence = is_low_confidence(
                record,
                review_threshold=self.config.dual_gate.low_confidence_review_threshold,
            )
            records.append(record)
        return records

    # ── OCR (plan mục 2.2) ───────────────────────────────────────────────────

    def _process_ocr(
        self,
        raw_stores: list[StoreCandidate],
        records: list[StoreRecord],
        request: CatchmentSurveyRequest,
    ) -> tuple[list[MenuSnapshotV2], list[dict[str, Any]]]:
        """Tải ảnh menu + OCR. Trả (snapshots, pending_review)."""
        if request.channel_mode == ChannelMode.DELIVERY_PLATFORM:
            return [], []

        by_id = {r.store_id: r for r in records}
        snapshots: list[MenuSnapshotV2] = []
        pending: list[dict[str, Any]] = []

        for raw in raw_stores:
            record = by_id.get(raw.id or raw.place_id or raw.name)
            if record is None or not record.passes_dual_gate:
                continue
            urls = list(raw.menu_image_urls or [])[: request.max_menu_images_per_store]
            for url in urls:
                image_bytes = _download_image(url)
                if not image_bytes:
                    continue
                _bump("vision_calls")
                result = extract_menu_from_image(
                    image_bytes,
                    store_id=record.store_id,
                    image_url=url,
                    core_keyword=request.core_category,
                    source_channel=ChannelMode.DINE_IN_VISION,
                )
                if result.error:
                    _bump("vision_errors")
                if result.snapshot is not None:
                    snapshots.append(result.snapshot)
                for entry in result.needs_review:
                    pending.append(
                        {
                            "store_id": record.store_id,
                            "store_name": record.name,
                            "image_url": url,
                            "name": entry.get("name", ""),
                            "raw_text": entry.get("raw_text", ""),
                            "reason": entry.get("reason", "price_unreadable"),
                        }
                    )
        return snapshots, pending

    def _attach_dinein_items(
        self,
        records: list[StoreRecord],
        snapshots: list[MenuSnapshotV2],
    ) -> None:
        by_id: dict[str, list[MenuItemPrice]] = {}
        for snap in snapshots:
            by_id.setdefault(snap.store_id, []).extend(snap.extracted_items)
        for record in records:
            items = by_id.get(record.store_id)
            if items:
                record.menu_items = list(items)

    def _apply_review(
        self,
        job: SurveyJob,
        submission: SurveyReviewSubmission,
    ) -> dict[str, Any]:
        """Ghi nhận quyết định của chủ quán vào tập mẫu, trả state để tổng hợp."""
        dinein: list[StoreRecord] = list(job.meta.get("dinein_records", []))
        by_id = {r.store_id: r for r in dinein}

        for item in submission.items:
            record = by_id.get(item.store_id)
            if record is None:
                logger.info("Review bỏ qua store_id lạ: %s", item.store_id)
                continue
            kept = [
                m for m in record.menu_items if m.item_name_raw != item.item_name_raw
            ]
            if not item.rejected:
                original = item.original_price_vnd
                effective = item.effective_price_vnd or (original or 0)
                if original is None and effective:
                    original = effective
                if original or effective:
                    kept.append(
                        MenuItemPrice(
                            item_name_raw=item.item_name_raw,
                            item_name_normalized=normalize_dish_name(item.item_name_raw),
                            original_price_vnd=original,
                            effective_price_vnd=effective,
                            is_promotional=bool(original and original != effective),
                            is_combo=item.is_combo,
                            portion_note=item.portion_note,
                            source_channel=ChannelMode.DINE_IN_VISION,
                            confidence="high",
                            is_fallback_derived=False,
                        )
                    )
            record.menu_items = kept

        job.stores_flagged_for_review = []
        job.meta["pending_review"] = []
        job.meta["reviewed_by"] = submission.reviewed_by
        job.meta["approve_all_remaining"] = submission.approve_all_remaining
        self.job_store.update_job(job)

        return {
            "online_records": list(job.meta.get("online_records", [])),
            "dinein_records": dinein,
            "snapshots": list(job.meta.get("ocr_snapshots", [])),
        }

    # ── Tổng hợp (plan mục 4) ────────────────────────────────────────────────

    def _qualified(self, records: list[StoreRecord]) -> list[StoreRecord]:
        return [r for r in records if r.passes_dual_gate]

    def _basket(self, items: list[MenuItemPrice]) -> list[float]:
        return filter_valid_prices(
            collect_sweet_spot_prices(
                items,
                exclude_combo=self.config.sweet_spot.loai_tru_combo,
                use_original_price=self.config.sweet_spot.dung_gia_goc,
            ),
            min_vnd=self.config.phan_vi.gia_hop_le_toi_thieu_vnd,
            max_vnd=self.config.phan_vi.gia_hop_le_toi_da_vnd,
        )

    def _channel_prices(self, records: list[StoreRecord]) -> list[float]:
        prices: list[float] = []
        for record in self._qualified(records):
            prices.extend(self._basket(record.menu_items))
        return prices

    def _core_categories(self, request: CatchmentSurveyRequest) -> set[str]:
        """Tập category được coi là CORE cho request này.

        Gồm chính `core_category` và MỌI core khác của cùng nhóm JTBD: chủ quán
        hỏi "cơm tấm" thì "cơm sườn"/"cơm gà" vẫn là bữa trưa no bụng cùng phân
        khúc — bỏ chúng ra thì AMBI bị thiếu mẫu một cách âm thầm.
        """
        cats = {normalize_category_name(request.core_category)}
        index = self.taxonomy
        if index is not None:
            for group in index.groups_for_core(request.core_category):
                cats.update(group.core_categories)
        cats.discard("")
        return cats

    def _classify(
        self,
        request: CatchmentSurveyRequest,
        records: list[StoreRecord],
    ) -> tuple[list[MenuItemPrice], dict[str, list[MenuItemPrice]]]:
        """Phân món vào rổ core / từng nhóm thay thế (plan mục 1.2, 3.4).

        GIẢ ĐỊNH NGOÀI PLAN: scraper đã tìm theo đúng `core_category`, nên món
        không khớp alias nào trong taxonomy vẫn được tính vào rổ core. Bỏ chúng
        thì AMBI trống rỗng ở đa số khu vực — mà plan không yêu cầu vậy. Món khớp
        một nhóm thay thế đã khai báo thì KHÔNG tính vào core. Món khớp một core
        của NHÓM JTBD KHÁC (vd "cà phê" khi đang khảo sát "cơm tấm") bị loại —
        không cùng một nhu cầu thay thế.
        """
        index = self.taxonomy
        substitutes: tuple[str, ...] = (
            index.substitute_categories(request.core_category) if index else ()
        )
        core_cats = self._core_categories(request)

        core_items: list[MenuItemPrice] = []
        sub_items: dict[str, list[MenuItemPrice]] = {cat: [] for cat in substitutes}

        for record in self._qualified(records):
            for item in record.menu_items:
                resolved = None
                if index is not None:
                    resolved = index.resolve_category(item.item_name_raw) or (
                        index.resolve_category(item.item_name_normalized)
                    )
                if resolved is not None and resolved in sub_items:
                    sub_items[resolved].append(item)
                elif resolved is None or resolved in core_cats:
                    core_items.append(item)
        return core_items, sub_items

    def _aggregate_results(
        self,
        request: CatchmentSurveyRequest,
        online_records: list[StoreRecord],
        dinein_records: list[StoreRecord],
        snapshots: list[MenuSnapshotV2],
        *,
        job_id: str,
    ) -> CatchmentSurveyResponse:
        online_stats = compute_percentile_stats(
            self._channel_prices(online_records),
            min_sample_size=self.config.phan_vi.min_sample_size,
        )
        dinein_stats = compute_percentile_stats(
            self._channel_prices(dinein_records),
            min_sample_size=self.config.phan_vi.min_sample_size,
        )

        if online_stats.insufficient_data and dinein_stats.insufficient_data:
            raise SurveyExecutionError(
                SurveyErrorCode.INSUFFICIENT_MARKET_DATA,
                f"khong_du_mau_toi_thieu: online={online_stats.sample_size}, "
                f"dinein={dinein_stats.sample_size}, "
                f"nguong={self.config.phan_vi.min_sample_size}",
            )

        core_items, sub_items = self._classify(request, [*online_records, *dinein_records])
        core_prices = self._basket(core_items)
        sub_prices = {
            cat: self._basket(items) for cat, items in sub_items.items() if items
        }

        core_stats = compute_percentile_stats(
            core_prices, min_sample_size=self.config.phan_vi.min_sample_size
        )
        substitute_stats = [
            SubstituteCategoryStats(
                category_name=cat,
                stats=compute_percentile_stats(
                    prices, min_sample_size=self.config.phan_vi.min_sample_size
                ),
            )
            for cat, prices in sorted(sub_prices.items())
        ]
        substitute_medians = [
            s.stats.p50 for s in substitute_stats if not s.stats.insufficient_data
        ]

        comparison: SubstitutePriceComparison | None = None
        if not core_stats.insufficient_data:
            ambi = compute_ambi(
                core_stats.p50,
                substitute_medians,
                w_core=self.config.ambi.trong_so_core,
                w_subs=self.config.ambi.trong_so_substitutes,
            )
            basket = union_core_and_substitutes(core_prices, sub_prices)
            category_group = (
                self.taxonomy.rounding_group(request.core_category)
                if self.taxonomy
                else "mon_chinh"
            )
            zone = compute_sweet_spot(
                basket,
                ambi,
                p_low=self.config.sweet_spot.phan_vi_canh_duoi,
                p_high=self.config.sweet_spot.phan_vi_canh_tren,
                category_group=category_group,
                rounding_steps=self.config.lam_tron_hien_thi,
            )

            viable: float | None = None
            if request.cost_plus_check and request.cost_plus_check.estimated_cogs_vnd:
                viable = min_viable_price(
                    request.cost_plus_check.estimated_cogs_vnd,
                    request.cost_plus_check.target_margin_ratio
                    or self.config.cost_plus.target_margin_ratio_mac_dinh,
                )

            comparison = SubstitutePriceComparison(
                core_category=normalize_category_name(request.core_category)
                or request.core_category,
                positioning_tier=request.positioning_tier or PositioningTier.CASUAL_DINE_IN,
                core_stats=core_stats,
                substitutes=substitute_stats,
                ambi=ambi,
                sweet_spot_low_raw=zone.low_raw,
                sweet_spot_high_raw=zone.high_raw,
                sweet_spot_low_display=float(zone.low_display),
                sweet_spot_high_display=float(zone.high_display),
                min_viable_price=viable,
                cost_plus_warning=check_cost_plus_warning(zone.high_raw, viable),
            )

        qualified_count = len(self._qualified(online_records)) + len(
            self._qualified(dinein_records)
        )
        # `area_type=None`: chưa có nguồn POI thật — KHÔNG được bịa (ADR-002).
        area_ctx = AreaContext(
            area_type=None,
            competitive_intensity=competitive_intensity(
                qualified_count,
                max(
                    request.radius_profile.dine_in_km,
                    request.radius_profile.delivery_km,
                ),
                pi=self.config.pi,
            ),
        )

        captured_at = max(
            (s.captured_at for s in snapshots),
            default=datetime.now(timezone.utc).isoformat(),
        )
        return CatchmentSurveyResponse(
            schema_version=request.schema_version,
            job_id=job_id,
            status=SurveyJobStatus.COMPLETED,
            online_stats=online_stats if not online_stats.insufficient_data else None,
            dinein_stats=dinein_stats if not dinein_stats.insufficient_data else None,
            substitute_comparison=comparison,
            area_context=area_ctx,
            stores_flagged_for_review=[],
            survey_captured_at=captured_at,
            generated_at=datetime.now(timezone.utc).isoformat(),
            error_code=None,
        )


def run_survey_job(
    request: CatchmentSurveyRequest,
    job_store: JobStore | None = None,
) -> SurveyJob:
    """Tiện ích: tạo job và chạy ngay (blocking). Dùng cho script/test."""
    orchestrator = SurveyOrchestrator(job_store=job_store)
    job = orchestrator.create_job(request)
    return orchestrator.execute_job(job.job_id)
