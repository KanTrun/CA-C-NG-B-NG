"""JevSensor — cảm biến xác suất gọi Jev (TypeSafe System One).

Thiết kế theo kế hoạch JEV v2:
- **Stub sau cổng cấu hình:** HTTP client thật nằm sau flag `jev.enabled`.
  Mặc định `enabled=False` (chưa có API key Jev) → `evaluate()` trả `ok=False`
  để code tất định thoái lui về phía con người (fail-closed, ADR-008).
- **Circuit breaker:** timeout 1.5s; 3 lỗi liên tiếp → mở 60s → thử 1 request thăm dò.
- **Replay (ADR-007):** ở chế độ replay, dùng phản hồi đã ghi thay vì gọi lại.
- **Kill-switch:** `jev.enabled=false` tắt nhanh mà không cần deploy.
- **Ghim phiên bản:** `jev-1.13.0`, không dùng `jev-latest` ở sản xuất.

Lưu ý: payload HTTP dưới đây đã đối chiếu `https://api.typesafe.ai/openapi.json`
(2026-10-02): `state` gửi dạng object, `questions` là map name →
{type, instructions, criteria}. Payload và hash replay dùng CHUNG
`_build_payload` nên không thể lệch nhau (ADR-007).

**Chưa kiểm chứng bằng lời gọi thật:** mọi môi trường đều thiếu `JEV_API_KEY`,
nên chưa có bằng chứng TypeSafe chấp nhận payload này. Bật Jev lần đầu thì phải
gọi thử một lần và đọc vết `fb_jev_sensor` trước khi tin.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from ca_agents.sensors.port import SensorResult, Signal

# Ghim phiên bản mô hình (kế hoạch §3.5). Không dùng "jev-latest" ở sản xuất.
JEV_MODEL_VERSION = "jev-1.13.0"
JEV_SCHEMA_VERSION = "jev-schema-1.0.0"

# Cấu hình môi trường (pattern nhất quán với llm.py / serpapi_client.py).
# Đặt JEV_API_KEY trong .env / env để bật Jev thật.
JEV_API_KEY_ENV = "JEV_API_KEY"
JEV_BASE_URL_ENV = "JEV_BASE_URL"
JEV_ENDPOINT_ENV = "JEV_ENDPOINT"
JEV_ENABLED_ENV = "JEV_ENABLED"

# Endpoint mặc định (xác minh từ docs.typesafe.ai/api — POST /v1/systemone).
_DEFAULT_BASE_URL = "https://api.typesafe.ai"
_DEFAULT_ENDPOINT = "/v1/systemone"

# Circuit breaker (kế hoạch §5, giá trị khởi điểm).
DEFAULT_TIMEOUT_MS = 1500
DEFAULT_FAILURE_THRESHOLD = 3
DEFAULT_OPEN_SECONDS = 60


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class CircuitBreakerState:
    """Trạng thái circuit breaker (bất biến, để test dễ).

    - `consecutive_failures`: số lỗi liên tiếp (chỉ lỗi transient).
    - `open_until`: thời điểm mở lại (epoch seconds); 0 = đóng.
    - `half_open_at`: thời điểm chuyển half-open (cho 1 request thăm dò);
      0 = không half-open.
    """

    consecutive_failures: int = 0
    open_until: float = 0.0  # epoch seconds; 0 = đóng
    half_open_at: float = 0.0  # epoch seconds; 0 = không half-open


@dataclass
class JevSensor:
    """Cảm biến gọi Jev. `enabled=False` → luôn `ok=False` (fail-closed).

    Bật Jev thật bằng cách đặt env:
      JEV_API_KEY=<key>   (bắt buộc — thiếu key thì fail-closed, không gọi mạng)
      JEV_ENABLED=true    (mặc định BẬT khi không đặt; đặt =0/false để tắt hẳn)
      JEV_BASE_URL=...    (tùy chọn, mặc định https://api.typesafe.ai)
      JEV_ENDPOINT=...    (tùy chọn, mặc định /v1/systemone)
    """

    enabled: bool | None = None
    api_key: str | None = None
    base_url: str = _DEFAULT_BASE_URL
    endpoint: str = _DEFAULT_ENDPOINT
    timeout_ms: int = DEFAULT_TIMEOUT_MS
    failure_threshold: int = DEFAULT_FAILURE_THRESHOLD
    open_seconds: int = DEFAULT_OPEN_SECONDS
    model_version: str = JEV_MODEL_VERSION
    schema_version: str = JEV_SCHEMA_VERSION
    # Replay store: request_hash -> phản hồi đã ghi (ADR-007).
    replay_store: dict[str, Mapping[str, Any]] = field(default_factory=dict)
    # Circuit breaker trạng thái (mutable).
    _breaker: CircuitBreakerState = field(default_factory=CircuitBreakerState, init=False)
    _clock: Any = field(default_factory=lambda: time.time, init=False)
    _half_open_probe_used: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        # `enabled=None` → đọc từ env (JEV_ENABLED, mặc định BẬT khi không đặt).
        # Truyền True/False tường minh để ÉP trạng thái, không bị env override
        # (quan trọng cho test).
        if self.enabled is None:
            self.enabled = _env_flag(JEV_ENABLED_ENV, default=True)
        # `api_key=None` → đọc từ env. Truyền "" (rỗng) để ép tắt (fail-closed).
        if self.api_key is None:
            self.api_key = os.getenv(JEV_API_KEY_ENV, "").strip() or None
        self.base_url = os.getenv(JEV_BASE_URL_ENV, self.base_url).rstrip("/")
        self.endpoint = os.getenv(JEV_ENDPOINT_ENV, self.endpoint)

    # ── Cấu hình clock cho test ─────────────────────────────────────────────
    def set_clock(self, clock: Any) -> None:
        """Gắn clock giả (FrozenClock) để test circuit breaker tất định."""
        self._clock = clock

    def _now(self) -> float:
        return float(self._clock())

    # ── Circuit breaker ─────────────────────────────────────────────────────
    def _is_open(self) -> bool:
        return self._now() < self._breaker.open_until

    @property
    def breaker_state(self) -> CircuitBreakerState:
        """Trạng thái hiện tại (cho test/giám sát)."""
        return self._breaker

    def _is_half_open(self) -> bool:
        """Half-open: đã hết thời gian mở, đang chờ 1 request thăm dò.

        Trả True nếu breaker đang ở half-open và CHƯA có request thăm dò nào
        được phép chạy (đếm qua `_half_open_probe_used`)."""
        return (
            self._breaker.half_open_at > 0
            and self._now() >= self._breaker.open_until
            and not self._half_open_probe_used
        )

    def _record_success(self) -> None:
        self._breaker = CircuitBreakerState(
            consecutive_failures=0, open_until=0.0, half_open_at=0.0
        )
        self._half_open_probe_used = False

    def _record_failure(self, backoff_seconds: float = 0.0) -> None:
        """Ghi 1 lỗi; nếu `backoff_seconds>0` (429) thời gian mở dài hơn.

        Khi breaker đang half-open mà thăm dò thất bại → mở lại ngay.
        """
        if self._breaker.half_open_at > 0 and self._half_open_probe_used:
            # Probe thất bại → mở lại ngay, đếm lại từ đầu.
            self._breaker = CircuitBreakerState(
                consecutive_failures=1,
                open_until=self._now() + (backoff_seconds or self.open_seconds),
                half_open_at=0.0,
            )
            self._half_open_probe_used = False
            return

        n = self._breaker.consecutive_failures + 1
        if n >= self.failure_threshold:
            # Ngưỡng đạt → mở breaker, sau open_seconds sẽ half-open.
            self._breaker = CircuitBreakerState(
                consecutive_failures=0,
                open_until=self._now() + (backoff_seconds or self.open_seconds),
                half_open_at=self._now() + (backoff_seconds or self.open_seconds),
            )
            self._half_open_probe_used = False
        else:
            self._breaker = CircuitBreakerState(
                consecutive_failures=n, open_until=0.0, half_open_at=0.0
            )

    # ── Payload ─────────────────────────────────────────────────────────────
    @staticmethod
    def _build_payload(
        model: str,
        state: Mapping[str, object],
        questions: Mapping[str, object],
    ) -> dict[str, Any]:
        """Payload gửi TypeSafe — dạng DUY NHẤT dùng cho cả hash lẫn HTTP.

        `state` đi nguyên object (openapi khai string | object | array). Trước
        đây `_call_api` bọc `json.dumps(state)` còn `_request_hash` băm object
        thô — hai payload khác nhau, nên hash replay không mô tả thứ đã gửi
        (ADR-007). Gộp về một hàm để không thể lệch lần nữa.
        """
        return {"model": model, "state": dict(state), "questions": dict(questions)}

    @staticmethod
    def _hash_payload(payload: Mapping[str, object]) -> str:
        """Băm CANONICAL của payload thật (sort key, không khoảng trắng thừa)."""
        canonical = json.dumps(
            payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    # ── Replay (ADR-007) ────────────────────────────────────────────────────
    def _request_hash(
        self,
        state: Mapping[str, object],
        schema_id: str,
        questions: Mapping[str, object] | None = None,
    ) -> str:
        """Hash của phản hồi đã ghi cho cặp (state, schema, questions).

        `schema_id` GẮN vào hash vì cùng một state có thể được hỏi bằng hai bộ
        câu hỏi khác nhau (`fb_page` vs `injection_scan`) — không gắn thì hai
        lượt ghi đè nhau và replay trả sai bộ đáp án.
        """
        payload = self._build_payload(
            self.model_version, state, questions or {}
        )
        payload["schema_id"] = schema_id
        return self._hash_payload(payload)

    def _hash_for_request(
        self,
        state: Mapping[str, object],
        schema_id: str,
        questions: Mapping[str, object],
    ) -> str:
        """Hash của ĐÚNG payload sắp gửi — `_call_api` và `evaluate` dùng chung."""
        payload = self._build_payload(self.model_version, state, questions)
        payload["schema_id"] = schema_id
        return self._hash_payload(payload)

    def record_replay(
        self,
        state: Mapping[str, object],
        schema_id: str,
        response: Mapping[str, Any],
        questions: Mapping[str, object] | None = None,
    ) -> None:
        """Ghi phản hồi Jev để replay (ADR-007)."""
        self.replay_store[
            self._request_hash(state, schema_id, questions)
        ] = response

    # ── Evaluate ────────────────────────────────────────────────────────────
    def evaluate(
        self,
        state: Mapping[str, object],
        schema_id: str,
        questions: Mapping[str, object] | None = None,
    ) -> SensorResult:
        """Đánh giá state với bộ câu hỏi.

        Bắt buộc truyền `questions` (map câu hỏi atom có type/instructions).
        Nếu thiếu → fail-closed (không gọi mạng, không bịa) — câu hỏi chung
        "Evaluate the state" không có ý nghĩa thực tế (V3 review).
        """
        # Kill-switch / chưa bật → fail-closed (ADR-008).
        if not self.enabled:
            return SensorResult(
                signals={},
                model_version=self.model_version,
                schema_version=self.schema_version,
                latency_ms=0,
                ok=False,
            )

        # Thiếu bộ câu hỏi → fail-closed (V3).
        if not questions:
            return SensorResult(
                signals={},
                model_version=self.model_version,
                schema_version=self.schema_version,
                latency_ms=0,
                ok=False,
            )

        # Circuit breaker mở → không gọi, thoái lui về phía con người.
        # Trừ khi đã tới half-open (hết thời gian mở) → cho 1 request thăm dò.
        if self._is_open() and not self._is_half_open():
            return SensorResult(
                signals={},
                model_version=self.model_version,
                schema_version=self.schema_version,
                latency_ms=0,
                ok=False,
            )
        if self._is_half_open():
            self._half_open_probe_used = True

        req_hash = self._hash_for_request(state, schema_id, questions)

        # Replay: dùng phản hồi đã ghi (ADR-007).
        if req_hash in self.replay_store:
            raw = self.replay_store[req_hash]
            return self._parse_response(raw, latency_ms=0)

        # Thiếu API key → fail-closed. KHÔNG đếm vào circuit breaker: đây là
        # lỗi cấu hình cố định, không phải lỗi transient (V6 review).
        if not self.api_key:
            return SensorResult(
                signals={},
                model_version=self.model_version,
                schema_version=self.schema_version,
                latency_ms=0,
                ok=False,
            )

        # Gọi API Jev thật.
        start = self._now()
        try:
            raw = self._call_api(state, schema_id, questions)
            latency_ms = int((self._now() - start) * 1000)
            return self._parse_response(raw, latency_ms=latency_ms)
        except Exception as exc:
            # 429 (rate limit) → backoff dài hơn (kế hoạch §5).
            backoff = _http_error_code(exc)
            self._record_failure(backoff_seconds=backoff)
            return SensorResult(
                signals={},
                model_version=self.model_version,
                schema_version=self.schema_version,
                latency_ms=int((self._now() - start) * 1000),
                ok=False,
            )

    def _call_api(
        self,
        state: Mapping[str, object],
        schema_id: str,
        questions: Mapping[str, object] | None = None,
    ) -> Mapping[str, Any]:
        """Gọi HTTP tới Jev (TypeSafe System One).

        Schema đã đối chiếu `api.typesafe.ai/openapi.json`:
        - Endpoint: POST {base}/v1/systemone
        - Request:  {"state": string|object|array, "model": str,
                     "questions": {name: {type, instructions, criteria}}}
          `state` gửi dạng OBJECT (không bọc chuỗi JSON) — xem `_build_payload`.
        `questions` được truyền (map câu hỏi atom) → gửi thẳng lên API.
        Thiếu questions → lỗi (evaluate() đã chặn trước, đây là lưới an toàn).
        """
        import urllib.request

        if not questions:
            raise ValueError("questions is required for JevSensor._call_api")
        url = f"{self.base_url}{self.endpoint}"
        payload = self._build_payload(self.model_version, state, questions)
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
        )
        with urllib.request.urlopen(req, timeout=self.timeout_ms / 1000.0) as resp:
            body = resp.read().decode("utf-8")
        parsed = json.loads(body)
        if not isinstance(parsed, dict):
            raise ValueError("Jev response must be a JSON object")
        return parsed

    # ── Parse phản hồi Jev ──────────────────────────────────────────────────
    def _parse_response(
        self, raw: Mapping[str, Any], latency_ms: int
    ) -> SensorResult:
        """Chuyển phản hồi Jev thô (theo docs.typesafe.ai/api) thành SensorResult.

        `raw` dạng:
        {
          "model": "jev-1.13.0",
          "answers": {
            "nguy_co_suc_khoe": {"type": "noul", "noul": 0.9},
            "muc_gay_gat": {"type": "score", "score": 1.2, "confidence": 0.8},
            "y_dinh": {"type": "choice", "choice": "khieu_nai",
                         "probabilities": {...}, "confidence": 0.9}
          },
          "usage": {...}
        }
        Nếu thiếu trường bắt buộc → coi như lỗi (VF-SCHEMA, fail-closed).
        """
        try:
            answers_raw = raw["answers"]
            signals: dict[str, Signal] = {}
            for name, a in answers_raw.items():
                kind = a["type"]
                if kind == "noul":
                    signals[name] = Signal(kind="noul", value=float(a["noul"]))
                elif kind == "score":
                    signals[name] = Signal(
                        kind="score",
                        value=float(a["score"]),
                        confidence=a.get("confidence"),
                        probabilities=a.get("probabilities"),
                    )
                elif kind == "choice":
                    signals[name] = Signal(
                        kind="choice",
                        value=str(a["choice"]),
                        confidence=a.get("confidence"),
                        probabilities=a.get("probabilities"),
                    )
                else:
                    raise ValueError(f"Unknown answer type: {kind}")
            model_version = str(raw.get("model", self.model_version))
            self._record_success()
            return SensorResult(
                signals=signals,
                model_version=model_version,
                schema_version=self.schema_version,
                latency_ms=latency_ms,
                ok=True,
            )
        except (KeyError, TypeError, ValueError):
            self._record_failure()
            return SensorResult(
                signals={},
                model_version=self.model_version,
                schema_version=self.schema_version,
                latency_ms=latency_ms,
                ok=False,
            )


def _http_error_code(exc: Exception) -> float:
    """Trả thời gian backoff (giây) cho lỗi HTTP — 429/529 → backoff dài.

    Kế hoạch §5: xử lý 429 bằng backoff, không thử lại vô hạn.
    Lỗi khác (5xx/mạng/timeout) → 0 (dùng open_seconds mặc định).
    """
    import urllib.error

    if isinstance(exc, urllib.error.HTTPError):
        if exc.code in (429, 529):
            # Rate limit / overloaded: nhà cung cấp khuyến nghị backoff.
            return 30.0
    return 0.0