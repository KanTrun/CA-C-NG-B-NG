"""Async Job Manager cho khảo sát giá (plan mục 2.4, 5.1).

State machine:
    QUEUED → SCRAPING_ONLINE → SCRAPING_DINEIN → OCR_PROCESSING → AGGREGATING → COMPLETED
    Bất kỳ state nào → FAILED (khi có lỗi)
    OCR_PROCESSING → NEEDS_REVIEW (khi confidence thấp, ADR-008)
    NEEDS_REVIEW → AGGREGATING (sau khi người dùng xác nhận)

ADR-008: NEEDS_REVIEW là ĐIỂM DỪNG THẬT — job không tự chuyển sang aggregating
nếu chưa có người dùng xác nhận qua POST .../{job_id}/review.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from ca_contracts.catchment_survey_v2 import (
    SURVEY_JOB_TRANSITIONS,
    CatchmentSurveyRequest,
    CatchmentSurveyResponse,
    SurveyErrorCode,
    SurveyJobStatus,
)


class InvalidJobTransitionError(Exception):
    """Nỗ lực chuyển state không hợp lệ theo state machine."""

    def __init__(self, job_id: str, current: SurveyJobStatus, target: SurveyJobStatus):
        self.job_id = job_id
        self.current = current
        self.target = target
        super().__init__(
            f"Invalid transition for job {job_id}: {current.value} → {target.value}"
        )


@dataclass
class SurveyJob:
    """Một job khảo sát đang chạy hoặc đã hoàn tất."""

    job_id: str
    request: CatchmentSurveyRequest
    status: SurveyJobStatus = SurveyJobStatus.QUEUED
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    response: CatchmentSurveyResponse | None = None
    error_code: SurveyErrorCode | None = None
    error_message: str | None = None
    stores_flagged_for_review: list[str] = field(default_factory=list)
    #: Trạng thái trung gian giữa các bước (records, snapshot OCR, dòng chờ review)
    #: để `resume_after_review` không phải cào lại nguồn. Không serialize ra API.
    meta: dict[str, Any] = field(default_factory=dict)

    def transition_to(self, new_status: SurveyJobStatus) -> None:
        """Chuyển state theo state machine, raise nếu không hợp lệ."""
        allowed = SURVEY_JOB_TRANSITIONS.get(self.status, frozenset())
        if new_status not in allowed:
            raise InvalidJobTransitionError(self.job_id, self.status, new_status)
        self.status = new_status
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def mark_failed(self, error_code: SurveyErrorCode, message: str) -> None:
        """Đánh dấu job thất bại với mã lỗi cụ thể."""
        # FAILED là terminal state, có thể transition từ bất kỳ state nào
        self.status = SurveyJobStatus.FAILED
        self.error_code = error_code
        self.error_message = message
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def set_response(self, response: CatchmentSurveyResponse) -> None:
        """Gán kết quả khảo sát khi job hoàn tất."""
        self.response = response
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def add_flagged_stores(self, store_ids: list[str]) -> None:
        """Thêm các store_id cần review thủ công (ADR-008)."""
        self.stores_flagged_for_review.extend(store_ids)
        self.updated_at = datetime.now(timezone.utc).isoformat()


class JobStore:
    """In-memory store cho các job khảo sát, có hỗ trợ hook persistence cho đa worker.

    Thread-safe: dùng lock để tránh race condition khi nhiều worker cùng truy cập.
    """

    def __init__(self) -> None:
        self._jobs: dict[str, SurveyJob] = {}
        self._lock = threading.RLock()
        self._on_save_hook: Any = None
        self._on_load_hook: Any = None

    def set_hooks(
        self,
        on_save: Any = None,
        on_load: Any = None,
    ) -> None:
        """Cấu hình hook lưu/đọc xuống storage (KV/DB) để chia sẻ giữa các worker."""
        self._on_save_hook = on_save
        self._on_load_hook = on_load

    def create_job(self, request: CatchmentSurveyRequest) -> SurveyJob:
        """Tạo job mới với job_id duy nhất."""
        job_id = str(uuid.uuid4())
        job = SurveyJob(job_id=job_id, request=request)
        with self._lock:
            self._jobs[job_id] = job
        if self._on_save_hook:
            try:
                self._on_save_hook(job)
            except Exception:
                pass
        return job

    def get_job(self, job_id: str) -> SurveyJob | None:
        """Lấy job theo ID, trả None nếu không tìm thấy."""
        with self._lock:
            job = self._jobs.get(job_id)
        if job is None and self._on_load_hook:
            try:
                job = self._on_load_hook(job_id)
                if job is not None:
                    with self._lock:
                        self._jobs[job_id] = job
            except Exception:
                pass
        return job

    def update_job(self, job: SurveyJob) -> None:
        """Cập nhật job (sau khi transition hoặc set response)."""
        with self._lock:
            self._jobs[job.job_id] = job
        if self._on_save_hook:
            try:
                self._on_save_hook(job)
            except Exception:
                pass

    def list_jobs(
        self,
        *,
        status: SurveyJobStatus | None = None,
        store_id: str | None = None,
        limit: int = 100,
    ) -> list[SurveyJob]:
        """Liệt kê jobs, optionally filter theo status và store_id."""
        with self._lock:
            jobs = list(self._jobs.values())
        if status is not None:
            jobs = [j for j in jobs if j.status == status]
        if store_id is not None:
            jobs = [j for j in jobs if j.meta.get("store_id") == store_id]
        # Sort by created_at descending (mới nhất trước)
        jobs.sort(key=lambda j: j.created_at, reverse=True)
        return jobs[:limit]

    def delete_job(self, job_id: str) -> bool:
        """Xóa job khỏi store (dùng cho cleanup)."""
        with self._lock:
            if job_id in self._jobs:
                del self._jobs[job_id]
                return True
            return False

    def get_latest_completed_job(self, store_id: str = "") -> SurveyJob | None:
        """Lấy job hoàn tất gần nhất của quán (phục vụ Copilot query kết quả)."""
        completed = self.list_jobs(status=SurveyJobStatus.COMPLETED, store_id=store_id if store_id else None, limit=1)
        return completed[0] if completed else None

    def count_today(self, store_id: str = "") -> int:
        """Đếm số job tạo trong ngày hôm nay (theo múi giờ Việt Nam UTC+7) của quán để giới hạn rate limit."""
        from datetime import timedelta
        vn_tz = timezone(timedelta(hours=7))
        today_iso = datetime.now(vn_tz).strftime("%Y-%m-%d")
        with self._lock:
            count = 0
            for j in self._jobs.values():
                # j.created_at is ISO string in UTC (e.g. 2026-09-14T10:00:00Z)
                # Need to convert created_at to VN timezone to check if it's today
                try:
                    # Python 3.11+: fromisoformat handles 'Z'
                    dt_utc = datetime.fromisoformat(j.created_at.replace("Z", "+00:00"))
                    dt_vn = dt_utc.astimezone(vn_tz)
                    if dt_vn.strftime("%Y-%m-%d") == today_iso:
                        if not store_id or j.meta.get("store_id") == store_id:
                            count += 1
                except ValueError:
                    pass
            return count


# Global singleton — production dùng dependency injection
_global_job_store: JobStore | None = None


def get_job_store() -> JobStore:
    """Lấy global JobStore singleton."""
    global _global_job_store
    if _global_job_store is None:
        _global_job_store = JobStore()
    return _global_job_store


def reset_job_store() -> None:
    """Reset global JobStore (dùng cho test)."""
    global _global_job_store
    _global_job_store = None
