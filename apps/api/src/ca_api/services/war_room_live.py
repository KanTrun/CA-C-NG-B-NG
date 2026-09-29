"""War Room — baseline THẬT từ lịch tuần đang vận hành (không fixture).

Vì sao: War Room trước đây mô phỏng trên preset + snapshot fixture, nên bấm
"Đề xuất" chỉ ra số của một kịch bản trình diễn — không tính trên quán thật.
Tầng này dựng baseline từ ĐÚNG phân công hiện tại (ca có người, ca thiếu, nhân
sự khả dụng) để mô phỏng ra số THẬT của tuần đang chạy.

Nguyên tắc:
- Chỉ ĐỌC dữ liệu thật (kv `phan_cong_by_week`, seed ca, `list_nhan_vien_ops`).
- Không mutation, không LLM. Số do engine tất định tính.
- Chưa có lịch tuần → trả None để caller rơi về fixture (fail-closed).
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any


def _tuan_hien_tai() -> str:
    """Tuần ISO đang hiệu lực (theo lịch tuần), fallback tuần của hôm nay."""
    try:
        from ca_api.interfaces.http.sprint45 import _life

        tuan = str(_life().get("tuan_iso") or "")
        if tuan:
            return tuan
    except Exception:
        pass
    y, w, _ = datetime.now(UTC).isocalendar()
    return f"{y}-W{w:02d}"


def build_live_baseline(week: str | None = None) -> dict[str, Any] | None:
    """Baseline THẬT của quán cho War Room.

    Trả None khi chưa có phân công thật (để router dùng fixture).
    Khoá trả về:
    - `tuan_iso`, `fingerprint` (hash tất định của baseline),
    - `nhan_vien`: danh sách {nv_id, ten, ky_nang},
    - `ca`: danh sách ca có người/thiếu kèm `co`/`can`,
    - `chi_so`: số ca, số ca đủ, số ca thiếu, tổng giờ xếp.
    """
    import json as _json

    from ca_api.nhan_vien import list_nhan_vien_ops
    from ca_api.persist import kv_get

    tuan = week or _tuan_hien_tai()
    phan_cong = kv_get("phan_cong_by_week", {})
    week_assign = phan_cong.get(tuan, {}) if isinstance(phan_cong, dict) else {}
    if not isinstance(week_assign, dict) or not week_assign:
        try:
            from ca_api.interfaces.http.sprint45 import _lich_out

            out = _lich_out()
            if out.exists():
                doc = _json.loads(out.read_text(encoding="utf-8"))
                if str(doc.get("tuan_iso") or "") == tuan:
                    week_assign = doc.get("phan_cong", {}) or {}
        except Exception:
            week_assign = {}
    if not isinstance(week_assign, dict) or not week_assign:
        return None

    from ca_api.interfaces.http.main import SEED

    try:
        seed = _json.loads(SEED.read_text(encoding="utf-8"))
    except Exception:
        seed = {}
    ca_meta = {str(c.get("id")): c for c in seed.get("ca_mau_21", []) if c.get("id")}

    nv_rows = list_nhan_vien_ops()
    ten_by_id = {str(n["id"]): str(n.get("ten") or n["id"]) for n in nv_rows}
    ky_nang_by_id = {str(n["id"]): list(n.get("ky_nang") or []) for n in nv_rows}

    ca_list: list[dict[str, Any]] = []
    gio_tong = 0.0
    so_ca_du = 0
    for ca_id, nvs in week_assign.items():
        meta = ca_meta.get(str(ca_id), {})
        can = int(meta.get("so_nguoi_toi_thieu") or 1)
        co = len(set(str(x) for x in (nvs or [])))
        du = co >= can
        if du:
            so_ca_du += 1
        gio_tong += _shift_hours(meta) * co
        ca_list.append(
            {
                "ca_id": str(ca_id),
                "thu": str(meta.get("thu") or ""),
                "khung": str(meta.get("khung") or ""),
                "vi_tri": str(meta.get("vi_tri") or ""),
                "bat_dau": str(meta.get("bat_dau") or ""),
                "ket_thuc": str(meta.get("ket_thuc") or ""),
                "can": can,
                "co": co,
                "du": du,
                "nv_ids": [str(x) for x in (nvs or [])],
            }
        )

    if not ca_list:
        return None

    nhan_vien = [
        {"nv_id": nv_id, "ten": ten_by_id.get(nv_id, nv_id), "ky_nang": ky_nang_by_id.get(nv_id, [])}
        for nv_id in {str(x) for c in ca_list for x in c["nv_ids"]}
    ]
    baseline = {
        "tuan_iso": tuan,
        "nhan_vien": nhan_vien,
        "ca": ca_list,
        "chi_so": {
            "so_ca": len(ca_list),
            "so_ca_du": so_ca_du,
            "so_ca_thieu": len(ca_list) - so_ca_du,
            "gio_da_xep": round(gio_tong, 1),
            "nhan_vien_kha_dung": len(nhan_vien),
        },
    }
    baseline["fingerprint"] = hashlib.sha256(
        json.dumps(
            {"tuan": tuan, "ca": [(c["ca_id"], c["nv_ids"]) for c in ca_list]},
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()[:16]
    return baseline


def _shift_hours(meta: dict[str, Any]) -> float:
    """Số giờ một ca từ 'HH:MM' bat_dau/ket_thuc (mặc định 5.0)."""
    try:
        b = str(meta.get("bat_dau") or "")
        e = str(meta.get("ket_thuc") or "")
        bh, bm = (int(x) for x in b.split(":"))
        eh, em = (int(x) for x in e.split(":"))
        return max(0.0, (eh * 60 + em - bh * 60 - bm) / 60.0)
    except Exception:
        return 5.0


def simulate_live_scenarios(
    baseline: dict[str, Any], *, kind: str, ca_id: str = "", khung: str = ""
) -> dict[str, Any]:
    """Chạy 3 phương án TẤT ĐỊNH trên baseline THẬT.

    Ba phương án cố định (đúng nghiệp vụ quán):
    - `giu_nguyen`: không đổi gì (mốc so sánh).
    - `tang_nguoi`: thêm 1 người vào ca đang thiếu (hoặc ca đông khung `khung`).
    - `dieu_chuyen`: rút 1 người từ ca ĐỦ nhất sang ca thiếu (không thêm quỹ giờ).

    Số trả về tính từ chính baseline — không phải preset.
    """
    ca_list = baseline.get("ca", [])
    chi_so = baseline.get("chi_so", {})
    gio_tb_ca = 5.0

    thieu = [c for c in ca_list if not c["du"]]
    du_nhat = max(ca_list, key=lambda c: c["co"] - c["can"]) if ca_list else None

    options: list[dict[str, Any]] = []

    # Phương án 1 — giữ nguyên.
    options.append(
        {
            "option_id": "opt_giu_nguyen",
            "scenario_id": "giu_nguyen",
            "label": "Giữ nguyên",
            "outputs": {
                "so_ca_thieu": chi_so.get("so_ca_thieu", 0),
                "gio_da_xep": chi_so.get("gio_da_xep", 0.0),
            },
            "load": {"thieu_truoc": len(thieu), "thieu_sau": len(thieu)},
            "constraint_violations": [],
            "risk": "Không thay đổi: các ca thiếu vẫn thiếu." if thieu else "Lịch đang đủ người.",
        }
    )

    # Phương án 2 — thêm người vào ca thiếu (hoặc ca theo khung chỉ định).
    target = None
    if ca_id:
        target = next((c for c in ca_list if c["ca_id"] == ca_id), None)
    if target is None and khung:
        target = next((c for c in thieu if c["khung"] == khung), None)
    if target is None and thieu:
        target = thieu[0]
    if target is not None:
        options.append(
            {
                "option_id": "opt_tang_nguoi",
                "scenario_id": "tang_nguoi",
                "label": f"Thêm 1 người vào ca {target['ca_id']}",
                "outputs": {
                    "so_ca_thieu": max(0, chi_so.get("so_ca_thieu", 0) - 1),
                    "gio_tang_them": gio_tb_ca,
                    "gio_da_xep": round(float(chi_so.get("gio_da_xep", 0.0)) + gio_tb_ca, 1),
                },
                "load": {"thieu_truoc": len(thieu), "thieu_sau": max(0, len(thieu) - 1)},
                "constraint_violations": [],
                "risk": "Tăng quỹ giờ tuần; cần người có kỹ năng phù hợp và chưa vượt trần giờ.",
                "chi_tiet": {"ca_id": target["ca_id"], "vi_tri": target["vi_tri"], "can": target["can"], "co": target["co"]},
            }
        )

    # Phương án 3 — điều chuyển người từ ca đủ nhất sang ca thiếu (không thêm giờ).
    if thieu and du_nhat is not None and (du_nhat["co"] - du_nhat["can"]) >= 1:
        options.append(
            {
                "option_id": "opt_dieu_chuyen",
                "scenario_id": "dieu_chuyen",
                "label": f"Chuyển 1 người từ {du_nhat['ca_id']} sang {thieu[0]['ca_id']}",
                "outputs": {
                    "so_ca_thieu": max(0, chi_so.get("so_ca_thieu", 0) - 1),
                    "gio_da_xep": chi_so.get("gio_da_xep", 0.0),
                    "chenh_cong_bang": 1.0,
                },
                "load": {"thieu_truoc": len(thieu), "thieu_sau": max(0, len(thieu) - 1)},
                "constraint_violations": [],
                "risk": "Ca nguồn mỏng đi — kiểm tra không rơi xuống dưới định biên.",
                "chi_tiet": {"tu_ca": du_nhat["ca_id"], "sang_ca": thieu[0]["ca_id"]},
            }
        )

    return {
        "baseline": baseline,
        "baseline_snapshot_hash": baseline.get("fingerprint", ""),
        "options": options,
    }
