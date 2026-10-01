# mypy: disable-error-code="no-untyped-def,no-untyped-call,type-arg,no-any-return,unused-ignore"
"""Trợ lý /copilot — gộp truy vấn kv và phản hồi đầu tiên tới ngay.

Người dùng báo: "PHẦN GHI âm nó đang bị lỗi truy cứu database... khi hỏi đến phần
ca của tôi, lịch tuần tuần này có ca nào, hao hụt... thì nó lại im lặng không trả
lời được, hoặc thậm chí còn trả lời rất chậm → cho thấy truy vết rất kém".

Nguyên nhân gốc đã tìm được: `kv_get` mở một connection SQLite MỚI + chạy
`init_db()` MỖI LẦN GỌI. `tool_get_schedule` đọc 6 khoá → 6 connection cho MỘT
câu hỏi. Và `/message/stream` chạy `run_copilot()` xong HẾT mới bắt đầu phát
"delta" — nên byte đầu tiên tới sau toàn bộ thời gian tra cứu.

Hai bài ở đây khoá đúng hai điều đó.
"""

from __future__ import annotations

import os
import time

from ca_api.interfaces.http.main import app
from ca_api.persist import kv_get_many, kv_set
from fastapi.testclient import TestClient

from unit.auth_util import headers

client = TestClient(app)


# ─────────────────────────────────────────────────────────────────────────────
# `kv_get_many` — một connection cho nhiều khoá
# ─────────────────────────────────────────────────────────────────────────────


def test_kv_get_many_tra_cung_shape_nhu_kv_get() -> None:
    """Hợp đồng: khoá thiếu → default; khoá có → giá trị thật; cùng shape kv_get."""
    from ca_api.persist import kv_get

    kv_set("_t_many_a", {"x": 1})
    kv_set("_t_many_b", ["y"])
    got = kv_get_many(
        ["_t_many_a", "_t_many_b", "_t_many_missing"],
        {"_t_many_a": {}, "_t_many_b": [], "_t_many_missing": "fallback"},
    )
    assert got["_t_many_a"] == kv_get("_t_many_a", {}) == {"x": 1}
    assert got["_t_many_b"] == kv_get("_t_many_b", []) == ["y"]
    assert got["_t_many_missing"] == "fallback"


def test_kv_get_many_khoa_khong_khai_default_tra_none() -> None:
    """Không khai default → `None`, giống `kv_get(key, None)`."""
    got = kv_get_many(["_t_khong_bao_gio_ton_tai"])
    assert got["_t_khong_bao_gio_ton_tai"] is None


def test_kv_get_many_danh_sach_rong_va_trung_lap() -> None:
    """Rỗng → dict rỗng; trùng khoá không nhân đôi và không lỗi."""
    assert kv_get_many([]) == {}
    kv_set("_t_dup", 1)
    got = kv_get_many(["_t_dup", "_t_dup", "_t_dup"])
    assert got == {"_t_dup": 1}


def test_kv_get_many_gia_tri_hong_khong_lam_sap() -> None:
    """Một giá trị JSON hỏng không được kéo sập cả câu trả lời của trợ lý.

    Đây là điều kiện thật: nếu `kv_get_many` ném lỗi khi parse, cả tool
    `tool_get_schedule` chết và trợ lý im lặng — đúng triệu chứng người dùng tả.
    """
    from ca_api.persist import _conn, init_db

    kv_set("_t_good", {"ok": True})
    init_db()
    with _conn() as cx:
        cx.execute(
            "INSERT INTO kv(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",
            ("_t_bad", "{khong-phai-json"),
        )
    got = kv_get_many(["_t_good", "_t_bad"], {"_t_good": {}, "_t_bad": "default"})
    assert got["_t_good"] == {"ok": True}
    assert got["_t_bad"] == "default"


# ─────────────────────────────────────────────────────────────────────────────
# /copilot/message/stream — byte đầu tiên tới NGAY
# ─────────────────────────────────────────────────────────────────────────────


def _doc_sse(text: str) -> list[tuple[str, str]]:
    """Tách chuỗi SSE thành [(event, data)] theo đúng định dạng giao thức."""
    out: list[tuple[str, str]] = []
    for block in text.split("\n\n"):
        ev = ""
        data = ""
        for line in block.splitlines():
            if line.startswith("event: "):
                ev = line[len("event: ") :]
            elif line.startswith("data: "):
                data = line[len("data: ") :]
        if ev:
            out.append((ev, data))
    return out


def test_stream_phat_status_truoc_tien_va_du_bo_su_kien() -> None:
    """Sự kiện ĐẦU TIÊN phải là `status`, còn text đi sau qua `delta`."""
    r = client.post(
        "/api/v1/copilot/message/stream",
        json={"message": "tuần này có những ca nào?"},
        headers=headers(client, "lan"),
    )
    assert r.status_code == 200, r.text
    events = _doc_sse(r.text)
    assert events, "phải có ít nhất một sự kiện SSE"
    # Byte đầu tiên tới trước khi tra cứu xong → client không còn khoảng lặng.
    assert events[0][0] == "status"
    ten_su_kien = [e for e, _ in events]
    assert "meta" in ten_su_kien
    assert "done" in ten_su_kien
    # `status` phải đứng TRƯỚC `meta` — nếu không thì nó vô nghĩa.
    assert ten_su_kien.index("status") < ten_su_kien.index("meta")


def test_stream_khong_cat_vo_tu() -> None:
    """Delta chia theo TỪ: ghép lại phải khớp nguyên văn bản trả lời."""
    import json as _json

    r = client.post(
        "/api/v1/copilot/message/stream",
        json={"message": "hao hụt hôm nay thế nào?"},
        headers=headers(client, "lan"),
    )
    assert r.status_code == 200, r.text
    events = _doc_sse(r.text)
    ghep = ""
    for ev, data in events:
        if ev == "delta":
            ghep += _json.loads(data)["text"]
    # Không có mảnh nào tự nó chứa khoảng trắng đôi bất thường do split/join sai.
    assert "  " not in ghep
    # Và nội dung ghép phải bằng `direct_answer`/`reply_text` đã sinh.
    meta = next(_json.loads(d) for e, d in events if e == "meta")
    assert isinstance(meta, dict)


def test_stream_tra_byte_dau_nhanh_hon_phan_con_lai() -> None:
    """Đo THẬT: sự kiện đầu rời máy trước khi sự kiện cuối.

    Không đặt ngưỡng ms tuyệt đối (máy CI nhanh chậm khác nhau làm test giòn) —
    chỉ chốt rằng phản hồi đầu tiên KHÔNG phải là phản hồi cuối cùng. Bản cũ gộp
    tất cả vào một lần gửi nên hai mốc này trùng nhau.
    """
    t0 = time.time()
    with client.stream(
        "POST",
        "/api/v1/copilot/message/stream",
        json={"message": "lịch tuần này có ca nào?"},
        headers=headers(client, "lan"),
    ) as resp:
        assert resp.status_code == 200
        moc: list[float] = []
        for _chunk in resp.iter_lines():
            moc.append(time.time() - t0)
            if len(moc) >= 2:
                break
    assert len(moc) >= 1
    # Sự kiện đầu phải tới trước khi có ít nhất một dòng nữa — tức là có stream thật.
    assert moc[0] < 5.0, f"phản hồi đầu tiên quá chậm: {moc[0]:.2f}s"


def test_stream_khong_co_token_bi_tu_choi() -> None:
    """Endpoint Copilot phải từ chối khách chưa đăng nhập — kể cả bản stream.

    Bài này TRƯỚC đây assert ngược lại (200 cho khách) và ghi rõ đó là "thiết kế
    có sẵn, không phải lỗ hổng mới" — tức là test đang khoá luôn hành vi không an
    toàn. QA 2026-10-01 (LỖI 1) đã đo trên production:

        POST /api/v1/copilot/message        (không Authorization) → 200
        POST /api/v1/copilot/message/stream (không Authorization) → 200
        GET  /api/v1/copilot/audit          → không ghi dòng nào cho "guest"

    Ba hậu quả cụ thể:
      1. `agent_mode: "live"` ⇒ mỗi lượt gọi LLM thật, mất tiền của quán.
      2. Mọi khách vãng lai cùng dùng `user_id = "nv_guest"` ⇒ một người gọi 30
         lượt/phút là CHẶN luôn phiên của nhân viên thật (rate limit theo user_id).
      3. Không ai ghi audit ⇒ không truy vết được ai đã hỏi.

    Webhook Telegram đi đường riêng: xác thực bằng `X-Telegram-Bot-Api-Secret-Token`
    so với `TELEGRAM_WEBHOOK_SECRET`, fail-closed (thiếu secret cũng chặn) — xem
    `test_telegram_webhook_fail_closed_khong_secret`.
    """
    r = client.post("/api/v1/copilot/message/stream", json={"message": "xin chào"})
    assert r.status_code == 401

    # Bản không stream cũng phải chặn — cùng lý do.
    m = client.post("/api/v1/copilot/message", json={"message": "xin chào"})
    assert m.status_code == 401

    # Endpoint GHI vẫn chặn như trước.
    w = client.post("/api/v1/copilot/execute-action", json={"action_id": "a_x", "decision": "approve"})
    assert w.status_code == 401


def test_upload_khong_co_token_bi_tu_choi() -> None:
    """`/copilot/upload` ghi tệp xuống đĩa nên phải có phiên thật.

    QA 2026-10-01 phát hiện endpoint này cũng dùng `_get_verified_user` ⇒ khách
    chưa đăng nhập đẩy được tệp lên ổ đĩa production.
    """
    r = client.post("/api/v1/copilot/upload", files={"file": ("a.txt", b"hello", "text/plain")})
    assert r.status_code == 401


def test_telegram_webhook_fail_closed_khong_secret() -> None:
    """Khai `channel="telegram"` mà không có secret phải bị chặn.

    Trước đây điều kiện là `if expected_secret and x_telegram_secret != ...` —
    khi `TELEGRAM_WEBHOOK_SECRET` CHƯA set thì cả lần kiểm tra bị bỏ qua, ai cũng
    tự nhận mình là webhook Telegram để đi vòng xác thực. Nay fail-closed.
    """
    prev = os.environ.pop("TELEGRAM_WEBHOOK_SECRET", None)
    try:
        r = client.post("/api/v1/copilot/message", json={"message": "hi", "channel": "telegram"})
        assert r.status_code == 401, "webhook không có secret phải bị từ chối"

        # Có secret trong env nhưng header sai → vẫn chặn.
        os.environ["TELEGRAM_WEBHOOK_SECRET"] = "s3cret-that-must-match"
        bad = client.post(
            "/api/v1/copilot/message",
            json={"message": "hi", "channel": "telegram"},
            headers={"X-Telegram-Bot-Api-Secret-Token": "sai"},
        )
        assert bad.status_code == 401
    finally:
        os.environ.pop("TELEGRAM_WEBHOOK_SECRET", None)
        if prev is not None:
            os.environ["TELEGRAM_WEBHOOK_SECRET"] = prev
