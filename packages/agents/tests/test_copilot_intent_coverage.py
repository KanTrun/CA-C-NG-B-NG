# mypy: disable-error-code="no-untyped-def,no-untyped-call,type-arg,no-any-return,unused-ignore"
"""Cổng chặn: mọi intent copilot khai báo phải có ít nhất một từ khóa.

Bài học (2026-10-01): `GET_INVENTORY` có enum, có tool (`tool_get_inventory`),
được cấp cho cả 3 vai trò — nhưng không có dòng nào trong `_INTENT_KEYWORDS`.
Nên `parse_intent()` không bao giờ sinh ra nó từ câu nói, và nhân viên hỏi
"tồn kho còn gì" thì nhận OUT_OF_SCOPE dù dữ liệu nằm ngay trong KV.

Lỗi đó lọt qua nhiều PR không ai thấy vì không có gì kiểm tra. Test này là cổng
đó: thêm intent mà quên khai từ khóa thì CI fail ngay.

Cùng bộ test này còn canh 2 thứ liên quan:
- Intent phải có tool thật trong registry (không có tool thì khai báo cũng rác).
- Từ khóa phải viết cả bản CÓ DẤU và KHÔNG DẤU, vì parser khớp thẳng
  `kw in text.lower()` và KHÔNG bỏ dấu (đã đo: cụm không dấu không khớp câu có dấu).
"""

from __future__ import annotations

import pytest
from ca_agents.ag_copilot import intent_parser as ip
from ca_agents.ag_copilot.tool_registry import _READ_TOOLS, _TOOLS
from ca_contracts import CopilotIntent

# OUT_OF_SCOPE là trạng thái rơi, không phải hành động → không cần từ khóa.
_KO_CAN_TU_KHOA = {"OUT_OF_SCOPE"}


def _ten_intent() -> set[str]:
    return {i.value for i in CopilotIntent} - _KO_CAN_TU_KHOA


def _intent_co_tu_khoa() -> set[str]:
    return {name for name, _, _ in ip._INTENT_KEYWORDS}


def test_moi_intent_deu_co_tu_khoa() -> None:
    """Intent nào khai báo trong enum mà không có từ khóa thì fail.

    Đây chính là lỗi GET_INVENTORY. Test phải bắt được, nên chạy lúc này SẼ FAIL —
    sau khi sửa intent_parser.py thì xanh.
    """
    thieu = sorted(_ten_intent() - _intent_co_tu_khoa())
    assert not thieu, (
        "Intent có trong CopilotIntent nhưng KHÔNG có _INTENT_KEYWORDS → "
        "parse_intent() không bao giờ sinh ra được, người dùng hỏi là OUT_OF_SCOPE: "
        + ", ".join(thieu)
    )


def test_moi_intent_deu_co_tool() -> None:
    """Intent có từ khóa mà không có tool thì người dùng được câu trả lời rỗng."""
    co_tool = set(_READ_TOOLS) | set(_TOOLS)
    thieu = sorted(_ten_intent() - co_tool)
    assert not thieu, (
        "Intent không có tool trong registry: " + ", ".join(thieu)
    )


def _bo_dau(s: str) -> str:
    import unicodedata

    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return unicodedata.normalize("NFC", s).replace("đ", "d").replace("Đ", "D").lower()


def _co_ban_khong_dau(chuoi: str) -> bool:
    """True nếu chuỗi còn nguyên dấu tiếng Việt."""
    return chuoi != _bo_dau(chuoi)


@pytest.mark.parametrize("ten", sorted(_intent_co_tu_khoa()))
def test_tu_khoa_co_ban_khong_dau(ten: str) -> None:
    """Mỗi từ khóa có dấu phải có bản không dấu đi kèm.

    Parser khớp thẳng `kw in text.lower()`. Người dùng đánh máy không dấu vẫn
    phải ra đúng intent, nếu không thì lỗi "nói lệch một từ là rơi OUT_OF_SCOPE"
    quay lại y hệt lúc đầu.
    """
    cum = next(kw for kw in ip._INTENT_KEYWORDS if kw[0] == ten)[1]
    khong_dau = {_bo_dau(c) for c in cum}
    thieu = [kw for kw in cum if _co_ban_khong_dau(kw) and _bo_dau(kw) not in khong_dau]
    assert not thieu, (
        f"Intent {ten}: từ khóa có dấu mà thiếu bản không dấu: "
        + ", ".join(thieu)
    )