# mypy: disable-error-code="no-untyped-def,no-untyped-call,type-arg,no-any-return,unused-ignore"
"""Ô trực sau đổi ca còn thiếu người không (`_o_truc_con_thieu`).

Hồi quy từ production 2026-10-01: Bảo đổi ca cho Yến ở ô T2 chiều, ô gồm
3 ca vị trí (pha chế 2 + thu ngân 1 + phục vụ 1 = 4 suất). Yến gánh 2 vị trí
nên chi tiết từng vị trí đều Đủ nhưng lưới vẫn phải nói rõ tình trạng cả ô —
không được im lặng, cũng không được báo Thiếu oan khi suất đã đủ.
"""

from __future__ import annotations

from ca_api.interfaces.http.sprint45 import _o_truc_con_thieu
from ca_api.persist import kv_set

WEEK = "2026-W40"


def _dat_phan_cong(phan: dict[str, list[str]]) -> None:
    kv_set("phan_cong_by_week", {WEEK: phan})


def test_o_du_suat_tra_none() -> None:
    """Đủ 4/4 suất (kể cả 1 người gánh 2 vị trí) → không cảnh báo."""
    _dat_phan_cong({
        "w1_c04": ["nv_01", "nv_02"],
        "w1_c05": ["nv_03"],
        "w1_c06": ["nv_03"],
    })
    assert _o_truc_con_thieu("w1_c04", WEEK) is None


def test_o_thieu_bao_dung_so() -> None:
    """3/4 suất → báo thiếu 1, đúng ô T2 chiều."""
    _dat_phan_cong({
        "w1_c04": ["nv_01"],
        "w1_c05": ["nv_03"],
        "w1_c06": ["nv_04"],
    })
    out = _o_truc_con_thieu("w1_c04", WEEK)
    assert out is not None
    assert out["thu"] == "T2"
    assert out["khung"] == "chieu"
    assert out["da_xep"] == 3
    assert out["can"] == 4
    assert out["thieu"] == 1


def test_ca_la_tra_none() -> None:
    """ca_id không có trong seed → không đoán mò."""
    _dat_phan_cong({"w1_c04": ["nv_01"]})
    assert _o_truc_con_thieu("khong_ton_tai", WEEK) is None
