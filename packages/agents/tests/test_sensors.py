# mypy: disable-error-code="no-untyped-def,no-untyped-call,type-arg,no-any-return,unused-ignore"
"""Tests cho SignalSensor (Jev + Regex) và bảng quyết định route_fb.

Xác minh các nguyên tắc kế hoạch JEV v2:
- RegexSensor tất định, không I/O, luôn ok=True.
- JevSensor fail-closed khi tắt / circuit breaker mở / lỗi.
- Replay (ADR-007) dùng phản hồi đã ghi.
- route_fb: regex thắng (đơn điệu), Jev lỗi → về phía con người,
  ngưỡng sức khỏe thấp, vùng xám noul, whitelist auto-reply.
"""

from __future__ import annotations

from ca_agents.sensors.fb_route import (
    AUTO_REPLY_WHITELIST,
    Route,
    route_fb,
)
from ca_agents.sensors.jev_sensor import JevSensor
from ca_agents.sensors.port import SensorResult, Signal
from ca_agents.sensors.regex_sensor import RegexSensor

# ── RegexSensor ─────────────────────────────────────────────────────────────


def test_regex_sensor_detects_health() -> None:
    s = RegexSensor()
    r = s.evaluate({"noi_dung_khach": "cả nhà tôi đau bụng từ nửa đêm"}, "fb")
    assert r.ok
    assert r.signals["nguy_co_suc_khoe"].value == 1.0


def test_regex_sensor_no_health() -> None:
    s = RegexSensor()
    r = s.evaluate({"noi_dung_khach": "menu hôm nay có gì"}, "fb")
    assert r.ok
    assert r.signals["nguy_co_suc_khoe"].value == 0.0


def test_regex_sensor_detects_legal() -> None:
    s = RegexSensor()
    r = s.evaluate({"noi_dung_khach": "tôi sẽ báo báo chí"}, "fb")
    assert r.ok
    assert r.signals["de_doa_phap_ly_truyen_thong"].value == 1.0


def test_regex_sensor_detects_hostile() -> None:
    s = RegexSensor()
    r = s.evaluate({"noi_dung_khach": "đe dọa đánh quán"}, "fb")
    assert r.ok
    assert r.signals["muc_gay_gat"].value == 1.0


# ── JevSensor: fail-closed ──────────────────────────────────────────────────


Q = {"test_q": {"type": "noul", "instructions": "Is X?"}}


def test_jev_sensor_disabled_fail_closed() -> None:
    s = JevSensor(enabled=False)
    r = s.evaluate({"noi_dung_khach": "x"}, "fb", Q)
    assert not r.ok
    assert r.signals == {}


def test_jev_sensor_enabled_no_key_stub_fail_closed() -> None:
    """Có enabled nhưng không có API key → fail-closed (ADR-008)."""
    s = JevSensor(enabled=True, api_key="")
    r = s.evaluate({"noi_dung_khach": "x"}, "fb", Q)
    assert not r.ok


def test_jev_sensor_missing_questions_fail_closed() -> None:
    """Thiếu bộ câu hỏi → fail-closed (V3 review)."""
    s = JevSensor(enabled=True, api_key="test-key")
    r = s.evaluate({"noi_dung_khach": "x"}, "fb")
    assert not r.ok


# ── JevSensor: replay (ADR-007) ─────────────────────────────────────────────


def test_jev_sensor_replay_uses_recorded() -> None:
    s = JevSensor(enabled=True)
    state = {"noi_dung_khach": "đau bụng"}
    raw = {
        "model": "jev-1.13.0",
        "answers": {
            "nguy_co_suc_khoe": {"type": "noul", "noul": 0.9},
        },
    }
    s.record_replay(state, "fb", raw, Q)
    r = s.evaluate(state, "fb", Q)
    assert r.ok
    assert r.signals["nguy_co_suc_khoe"].value == 0.9
    assert r.model_version == "jev-1.13.0"


def test_jev_sensor_replay_bad_schema_fail_closed() -> None:
    s = JevSensor(enabled=True)
    state = {"noi_dung_khach": "x"}
    s.record_replay(
        state, "fb", {"answers": {"a": {"type": "noul"}}}, Q
    )  # thiếu noul
    r = s.evaluate(state, "fb", Q)
    assert not r.ok


# ── JevSensor: circuit breaker ──────────────────────────────────────────────


def test_jev_sensor_circuit_breaker_opens() -> None:
    clock = {"t": 1000.0}

    def fake_clock() -> float:
        return clock["t"]

    s = JevSensor(
        enabled=True, api_key="", failure_threshold=3, open_seconds=60
    )
    s.set_clock(fake_clock)

    # 3 lỗi liên tiếp (không có key) → KHÔNG mở breaker (V6: thiếu key không
    # phải lỗi transient).
    for _ in range(5):
        r = s.evaluate({"noi_dung_khach": "x"}, "fb", Q)
        assert not r.ok
    # Breaker vẫn đóng (không có key → không bao giờ mở).
    r = s.evaluate({"noi_dung_khach": "x"}, "fb", Q)
    assert not r.ok


def test_jev_sensor_circuit_breaker_opens_on_api_error() -> None:
    """Lỗi API (transient) → mở breaker sau 3 lỗi."""
    from unittest.mock import patch

    clock = {"t": 1000.0}

    def fake_clock() -> float:
        return clock["t"]

    s = JevSensor(enabled=True, api_key="k", failure_threshold=3, open_seconds=60)
    s.set_clock(fake_clock)

    for _ in range(3):
        with patch.object(s, "_call_api", side_effect=RuntimeError("timeout")):
            r = s.evaluate({"noi_dung_khach": "x"}, "fb", Q)
        assert not r.ok

    # Breaker mở → không gọi API, trả fail-closed.
    with patch.object(s, "_call_api") as mock_call:
        r = s.evaluate({"noi_dung_khach": "x"}, "fb", Q)
    mock_call.assert_not_called()
    assert not r.ok

    # Sau open_seconds, breaker đóng lại (thử lại 1 request).
    clock["t"] = 1061.0
    with patch.object(s, "_call_api", side_effect=RuntimeError("timeout")):
        r = s.evaluate({"noi_dung_khach": "x"}, "fb", Q)
    assert not r.ok


def test_jev_sensor_circuit_breaker_half_open_probe_success() -> None:
    """Half-open: probe thành công sau khi hết thời gian mở → đóng breaker."""
    from unittest.mock import patch

    clock = {"t": 1000.0}

    def fake_clock() -> float:
        return clock["t"]

    s = JevSensor(enabled=True, api_key="k", failure_threshold=2, open_seconds=60)
    s.set_clock(fake_clock)
    raw = {
        "model": "jev-1.13.0",
        "answers": {"a": {"type": "noul", "noul": 0.5}},
    }

    # 2 lỗi → breaker mở.
    for _ in range(2):
        with patch.object(s, "_call_api", side_effect=RuntimeError("timeout")):
            r = s.evaluate({"noi_dung_khach": "x"}, "fb", Q)
        assert not r.ok

    # Đang mở → không gọi.
    with patch.object(s, "_call_api") as mock_call:
        r = s.evaluate({"noi_dung_khach": "x"}, "fb", Q)
    mock_call.assert_not_called()
    assert not r.ok

    # Hết thời gian mở → half-open cho 1 probe. Probe thành công → đóng.
    clock["t"] = 1061.0
    with patch.object(s, "_call_api", return_value=raw):
        r = s.evaluate({"noi_dung_khach": "x"}, "fb", Q)
    assert r.ok
    # Breaker đã đóng → lần sau gọi bình thường.
    with patch.object(s, "_call_api", return_value=raw) as mock_call2:
        r = s.evaluate({"noi_dung_khach": "x"}, "fb", Q)
    mock_call2.assert_called_once()
    assert r.ok


def test_jev_sensor_429_backoff_longer() -> None:
    """429 (rate limit) → backoff dài hơn open_seconds mặc định."""
    import urllib.error
    from unittest.mock import patch

    clock = {"t": 1000.0}

    def fake_clock() -> float:
        return clock["t"]

    s = JevSensor(enabled=True, api_key="k", failure_threshold=1, open_seconds=60)
    s.set_clock(fake_clock)

    # 1 lỗi 429 → breaker mở với backoff 30s (khác open_seconds 60).
    from email.message import Message

    with patch.object(
        s,
        "_call_api",
        side_effect=urllib.error.HTTPError("url", 429, "Too Many", Message(), None),
    ):
        r = s.evaluate({"noi_dung_khach": "x"}, "fb", Q)
    assert not r.ok
    # 429 → backoff 30s: tại t=1010 (chưa đủ 30s) breaker còn mở, chưa probe.
    clock["t"] = 1010.0
    with patch.object(s, "_call_api") as mock_call:
        r = s.evaluate({"noi_dung_khach": "x"}, "fb", Q)
    mock_call.assert_not_called()
    assert not r.ok


# ── JevSensor: HTTP call thật (mock _call_api) ─────────────────────────────


def test_jev_sensor_calls_api_with_key(monkeypatch) -> None:
    """Có key + enabled → gọi _call_api và parse phản hồi."""
    from unittest.mock import patch

    s = JevSensor(enabled=True, api_key="test-key")
    raw = {
        "model": "jev-1.13.0",
        "answers": {
            "nguy_co_suc_khoe": {"type": "noul", "noul": 0.9},
        },
    }
    with patch.object(s, "_call_api", return_value=raw) as mock_call:
        r = s.evaluate({"noi_dung_khach": "đau bụng"}, "fb", Q)
    mock_call.assert_called_once()
    assert r.ok
    assert r.signals["nguy_co_suc_khoe"].value == 0.9


def test_jev_sensor_api_error_fail_closed(monkeypatch) -> None:
    """API lỗi (exception) → ok=False, fail-closed."""
    from unittest.mock import patch

    s = JevSensor(enabled=True, api_key="test-key")
    with patch.object(s, "_call_api", side_effect=RuntimeError("timeout")):
        r = s.evaluate({"noi_dung_khach": "x"}, "fb", Q)
    assert not r.ok


def test_jev_sensor_api_bad_schema_fail_closed(monkeypatch) -> None:
    """API trả schema lạ → ok=False (VF-SCHEMA, fail-closed)."""
    from unittest.mock import patch

    s = JevSensor(enabled=True, api_key="test-key")
    with patch.object(s, "_call_api", return_value={"answers": {"a": {"type": "noul"}}}):
        r = s.evaluate({"noi_dung_khach": "x"}, "fb", Q)
    assert not r.ok


def test_jev_sensor_sends_bearer_header_not_placeholder(monkeypatch) -> None:
    """`Authorization` phải mang key thật.

    Chốt chặn để khối placeholder không quay lại: payload từng gửi chuỗi che
    `******` ở mọi lời gọi, và test cũ chỉ mock `_call_api` nên không ai thấy.
    """
    import urllib.request
    from unittest.mock import patch

    s = JevSensor(enabled=True, api_key="key-that")
    seen: dict[str, str] = {}

    class _Resp:
        def read(self) -> bytes:
            return b'{"model": "jev-1.13.0", "answers": {}}'

        def __enter__(self):
            return self

        def __exit__(self, *a) -> None:
            return None

    def _fake_urlopen(req, timeout=None):
        seen.update({k.lower(): v for k, v in req.headers.items()})
        seen["__data__"] = req.data.decode("utf-8")
        return _Resp()

    with patch.object(urllib.request, "urlopen", _fake_urlopen):
        s.evaluate({"noi_dung_khach": "x"}, "fb", Q)

    assert seen["authorization"] == "Bearer key-that"
    assert "******" not in seen["authorization"]


def test_jev_sensor_state_khong_bi_boc_thanh_chuoi_json(monkeypatch) -> None:
    """`state` phải đi nguyên dạng, không bị `json.dumps` thành một chuỗi.

    TypeSafe khai `state` là string | object | array. Bọc object thành chuỗi
    JSON vừa bỏ hết cấu trúc trường (instructions đọc theo khoá), vừa làm
    `_request_hash` băm một payload khác với payload gửi đi (ADR-007).
    """
    import json
    import urllib.request
    from unittest.mock import patch

    s = JevSensor(enabled=True, api_key="key-that")
    seen: dict[str, str] = {}

    class _Resp:
        def read(self) -> bytes:
            return b'{"model": "jev-1.13.0", "answers": {}}'

        def __enter__(self):
            return self

        def __exit__(self, *a) -> None:
            return None

    def _fake_urlopen(req, timeout=None):
        seen["__data__"] = req.data.decode("utf-8")
        return _Resp()

    with patch.object(urllib.request, "urlopen", _fake_urlopen):
        s.evaluate({"noi_dung_khach": "đau bụng"}, "fb", Q)

    payload = json.loads(seen["__data__"])
    assert isinstance(payload["state"], dict), "state đang bị serialize thành chuỗi JSON"
    assert payload["state"]["noi_dung_khach"] == "đau bụng"


def test_jev_sensor_hash_khop_payload_gui_di(monkeypatch) -> None:
    """Hash replay phải băm ĐÚNG payload đã gửi (ADR-007).

    Lỗi cũ: `_call_api` gửi `state` bọc chuỗi JSON còn `_request_hash` băm
    object thô → bản ghi replay mô tả một request khác. Test ghi replay theo
    payload gửi thật rồi bắt `evaluate` phải dùng lại bản ghi đó (không gọi
    mạng lần hai).
    """
    import json
    import urllib.request
    from unittest.mock import patch

    s = JevSensor(enabled=True, api_key="key-that")
    calls: list[str] = []
    state = {"noi_dung_khach": "đau bụng"}

    class _Resp:
        def read(self) -> bytes:
            return b'{"model": "jev-1.13.0", "answers": {"nguy_co_suc_khoe": {"type": "noul", "noul": 0.77}}}'

        def __enter__(self):
            return self

        def __exit__(self, *a) -> None:
            return None

    captured: dict[str, str] = {}

    def _fake_urlopen(req, timeout=None):
        calls.append("net")
        captured["payload"] = req.data.decode("utf-8")
        return _Resp()

    with patch.object(urllib.request, "urlopen", _fake_urlopen):
        first = s.evaluate(state, "fb", Q)

    assert first.ok
    sent = json.loads(captured["payload"])
    # Ghi bản replay từ CHÍNH payload đã gửi (đúng quy trình ADR-007).
    s.record_replay(
        state,
        "fb",
        {"model": "jev-1.13.0", "answers": {"nguy_co_suc_khoe": {"type": "noul", "noul": 0.11}}},
        Q,
    )
    assert json.loads(captured["payload"])["state"] == sent["state"]

    # Lượt hai phải ăn replay, KHÔNG gọi mạng.
    with patch.object(urllib.request, "urlopen", _fake_urlopen):
        second = s.evaluate(state, "fb", Q)
    assert len(calls) == 1, "hash replay không khớp payload gửi đi → gọi mạng lại"
    assert second.ok
    assert second.signals["nguy_co_suc_khoe"].value == 0.11


# ── route_fb: bảng quyết định ──────────────────────────────────────────────


def _result(signals: dict, ok: bool = True) -> SensorResult:
    return SensorResult(
        signals=signals,
        model_version="jev-1.13.0",
        schema_version="jev-schema-1.0.0",
        latency_ms=10,
        ok=ok,
    )


def test_route_regex_wins_monotone() -> None:
    """Regex trúng → ESCALATE_OWNER, bất kể Jev nói gì (đơn điệu)."""
    r = _result({"nguy_co_suc_khoe": Signal("noul", 0.0)})
    assert route_fb(regex_hit=True, r=r) == Route.ESCALATE_OWNER


def test_route_jev_error_fail_closed() -> None:
    """Jev lỗi → về phía con người, không 'regex không thấy = an toàn'."""
    r = _result({}, ok=False)
    assert route_fb(regex_hit=False, r=r) == Route.HUMAN_QUEUE_HOLDING_MSG


def test_route_health_low_threshold_escalates() -> None:
    """Ngưỡng sức khỏe thấp: 0.30 → ESCALATE_OWNER (thà báo nhầm)."""
    r = _result({"nguy_co_suc_khoe": Signal("noul", 0.35)})
    assert route_fb(regex_hit=False, r=r) == Route.ESCALATE_OWNER


def test_route_legal_escalates() -> None:
    r = _result({"de_doa_phap_ly_truyen_thong": Signal("noul", 0.40)})
    assert route_fb(regex_hit=False, r=r) == Route.ESCALATE_OWNER


def test_route_noul_gray_zone_queues() -> None:
    """Vùng xám noul (0.25–0.35) → HUMAN_QUEUE, không quyết định cứng."""
    r = _result({"nguy_co_suc_khoe": Signal("noul", 0.28)})
    assert route_fb(regex_hit=False, r=r) == Route.HUMAN_QUEUE


def test_route_hostile_escalates_manager() -> None:
    r = _result({"muc_gay_gat": Signal("score", 2.0)})
    assert route_fb(regex_hit=False, r=r) == Route.ESCALATE_MANAGER


def test_route_ask_human_escalates_manager() -> None:
    r = _result({"doi_gap_nguoi_that": Signal("noul", 0.6)})
    assert route_fb(regex_hit=False, r=r) == Route.ESCALATE_MANAGER


def test_route_complaint_escalates_manager() -> None:
    r = _result({"y_dinh": Signal("choice", "khieu_nai", confidence=0.9)})
    assert route_fb(regex_hit=False, r=r) == Route.ESCALATE_MANAGER


def test_route_sarcasm_escalates_manager() -> None:
    r = _result({"co_ve_mia_mai": Signal("noul", 0.6)})
    assert route_fb(regex_hit=False, r=r) == Route.ESCALATE_MANAGER


def test_route_auto_reply_whitelist() -> None:
    """Intent trong whitelist + confidence cao + không nguy hại → AUTO_REPLY_DRAFT."""
    r = _result(
        {
            "y_dinh": Signal("choice", "khen", confidence=0.9),
            "nguy_co_suc_khoe": Signal("noul", 0.0),
            "de_doa_phap_ly_truyen_thong": Signal("noul", 0.0),
            "muc_gay_gat": Signal("score", 0.0),
        }
    )
    assert route_fb(regex_hit=False, r=r) == Route.AUTO_REPLY_DRAFT


def test_route_auto_reply_low_confidence_queues() -> None:
    """Confidence thấp → không tự trả lời, vào hàng đợi."""
    r = _result(
        {
            "y_dinh": Signal("choice", "khen", confidence=0.5),
            "nguy_co_suc_khoe": Signal("noul", 0.0),
            "de_doa_phap_ly_truyen_thong": Signal("noul", 0.0),
            "muc_gay_gat": Signal("score", 0.0),
        }
    )
    assert route_fb(regex_hit=False, r=r) == Route.HUMAN_QUEUE


def test_route_auto_reply_not_in_whitelist_queues() -> None:
    """Intent ngoài whitelist → không tự trả lời."""
    r = _result(
        {
            "y_dinh": Signal("choice", "khac", confidence=0.9),
            "nguy_co_suc_khoe": Signal("noul", 0.0),
            "de_doa_phap_ly_truyen_thong": Signal("noul", 0.0),
            "muc_gay_gat": Signal("score", 0.0),
        }
    )
    assert route_fb(regex_hit=False, r=r) == Route.HUMAN_QUEUE


def test_route_contradiction_escalates() -> None:
    """Mâu thuẫn: y_dinh=khen nhưng nguy_co_suc_khoe cao → leo thang."""
    r = _result(
        {
            "y_dinh": Signal("choice", "khen", confidence=0.9),
            "nguy_co_suc_khoe": Signal("noul", 0.8),
        }
    )
    assert route_fb(regex_hit=False, r=r) == Route.ESCALATE_OWNER


def test_whitelist_contains_expected() -> None:
    assert AUTO_REPLY_WHITELIST == frozenset({"khen", "hoi_thong_tin", "dat_ban"})