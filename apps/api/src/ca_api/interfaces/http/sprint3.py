"""Sprint 3 HTTP — phiếu, orc, AG-MSG, lịch của tôi, ghi nhận sửa."""

from __future__ import annotations

import csv
import io
import json
import os
import uuid
from collections.abc import Callable

try:
    from datetime import UTC, datetime
except ImportError:
    from datetime import datetime, timezone

    UTC = timezone.utc
from pathlib import Path
from typing import Annotated, Any, cast

from ca_agents.ag_msg import classify
from ca_agents.ag_tkb.extract import extract_tkb
from ca_agents.llm import agent_mode
from ca_agents.messaging import get_port
from ca_ops import (
    PhieuRun,
    add_treo,
    complete_buoc,
    dump_run,
    escalate,
    load_phieu_catalog,
    load_run,
    load_template,
    run_to_dict,
    start_phieu,
)
from ca_playbook import list_sua, record_sua
from fastapi import APIRouter, File, Form, Header, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from ca_api.orchestration import Clock, IdempotencyStore, StateMachine, dispatch_parallel
from ca_api.persist import (
    audit_add,
    db_path,
    diem_danh_hom_nay,
    ghi_diem_danh,
    kv_get,
    kv_mutate,
    kv_set,
)
from ca_api.persist import session as auth_session

router = APIRouter()
ROOT = Path(__file__).resolve().parents[6]
SEED = ROOT / "data" / "seed" / "sample.json"


def _lich_out() -> Path:
    """Output solver — đọc MỖI LẦN GỌI, không phải lúc import module.

    Đồng bộ `main._lich_tuan_out()` và `sprint45._lich_out()`, hai nơi đã làm đúng
    từ trước và ghi rõ lý do.

    Vì sao BẮT BUỘC đọc mỗi lần: conftest set `NHIPQUAN_LICH_TUAN_OUT` theo từng
    bài test, SAU khi module đã import. Nếu chốt đường dẫn ở cấp module thì biến
    đó không bao giờ được thấy, và test đọc/ghi thẳng vào `data/out/lich_tuan.json`
    THẬT của quán.

    Hậu quả thật đã xảy ra: `_phan_cong()` ưu tiên file lịch tuần hơn seed, nên một
    file sót lại từ lần chạy demo trước đã che seed vĩnh viễn. `data/out/lich_tuan.json`
    có `w1_c01 = ['nv_03', 'nv_38']` trong khi seed nói `['nv_07', 'nv_19']` — nên
    `test_ghi_nhan_after_nha` nhận `nv_03` đã ở trong ca và trả **409 `da_trong_ca`**,
    đỏ trên mọi máy có file đó, kể cả máy sạch vì nó đã bị theo dõi nhầm.
    """
    env = os.environ.get("NHIPQUAN_LICH_TUAN_OUT")
    if env:
        return Path(env)
    return ROOT / "data" / "out" / "lich_tuan.json"

_clock: Clock = Clock()
_sm_by_phieu: dict[str, StateMachine] = {}
_idem = IdempotencyStore()
_orc_writes: dict[str, int] = {}


def set_clock(clock: Clock) -> None:
    global _clock
    _clock = clock


def _role(authorization: str | None) -> str | None:
    s = auth_session(authorization)
    return None if s is None else s["role"]


def _require_role(authorization: str | None) -> str:
    role = _role(authorization)
    if not role:
        raise HTTPException(status_code=401, detail="thieu_token")
    return role


def _nv_from_token(authorization: str | None) -> str:
    s = auth_session(authorization)
    if not s:
        raise HTTPException(status_code=401, detail="thieu_token")
    return s["nv_id"]


def _store_from_token(authorization: str | None) -> str:
    s = auth_session(authorization)
    if not s:
        raise HTTPException(status_code=401, detail="thieu_token")
    return s.get("store_id", "quan_01")


def _can_touch(run: Any, authorization: str | None) -> str:
    nv = _nv_from_token(authorization)
    role = _require_role(authorization)
    if role in {"quan_ly", "chu_quan"}:
        return nv
    if run.nv_id != nv:
        raise HTTPException(status_code=403, detail="khong_phai_chu_phieu")
    return nv


def _require_chu_quan(authorization: str | None) -> str:
    role = _require_role(authorization)
    if role != "chu_quan":
        raise HTTPException(status_code=403, detail="forbidden — requires chu_quan")
    return role


def _require_manager(authorization: str | None) -> str:
    role = _require_role(authorization)
    if role not in {"quan_ly", "chu_quan"}:
        raise HTTPException(status_code=403, detail="forbidden")
    return role


def _known_ca(ca_id: str) -> bool:
    seed = json.loads(SEED.read_text(encoding="utf-8")) if SEED.exists() else {}
    ids = {c["id"] for c in seed.get("ca_mau_21", [])}
    ids |= set(_phan_cong())
    return ca_id in ids


def _known_nv(nv_id: str) -> bool:
    """NV có tồn tại không — chỉ tính người THẬT trong pool đang xếp lịch.

    Trước đây truyền `include_seed=True` nên chấp nhận cả `nv_20..nv_25` (mã chỉ
    có trong seed fixture) → có thể ghim ca / phát QR cho người không tồn tại
    (bug QA đợt 4). Phải khớp nguồn NV thật để validation đúng.
    """
    from ca_api.nhan_vien import list_nhan_vien_ops

    ids = {n["id"] for n in list_nhan_vien_ops() if n.get("id")}
    if not ids:
        # DB rỗng (demo sạch) → chấp nhận seed để không chặn luồng demo.
        ids = {n["id"] for n in list_nhan_vien_ops(include_seed=True) if n.get("id")}
    return nv_id in ids


def _current_week() -> str:
    """Tuần đang hiệu lực của quán.

    Thứ tự: lifecycle thật → tuần ISO HIỆN TẠI (theo đồng hồ).
    Trước đây fallback cứng `2026-W01` nên khi KV trống (quán mới/demo sạch)
    mọi thao tác gắn vào tuần W01 — sai hẳn so với thực tế (bug QA đợt 4).
    """
    life = kv_get("lich_tuan_lifecycle", {})
    if isinstance(life, dict) and life.get("tuan_iso"):
        return str(life["tuan_iso"])
    return _current_iso_week()


def _phan_cong(tuan_iso: str | None = None) -> dict[str, list[str]]:
    week = (tuan_iso or "").strip()
    if week:
        by_week = kv_get("phan_cong_by_week", {})
        if isinstance(by_week, dict) and week in by_week and isinstance(by_week[week], dict):
            return cast(dict[str, list[str]], by_week[week])
    stored = kv_get("phan_cong", None)
    if stored:
        return cast(dict[str, list[str]], stored)
    phan: dict[str, list[str]] = {}
    lich_out = _lich_out()
    if lich_out.exists():
        phan = json.loads(lich_out.read_text(encoding="utf-8")).get("phan_cong", {})
    elif SEED.exists():
        seed = json.loads(SEED.read_text(encoding="utf-8"))
        hist = (seed.get("lich_su_8_tuan") or [{}])[0].get("phan_cong", {})
        phan = hist
    data = {cid: list(nvs) for cid, nvs in phan.items()}
    kv_set("phan_cong", data)
    return data


def _save_run(run: Any) -> None:
    def mut(bag: dict[str, Any]) -> dict[str, Any]:
        bag[run.id] = dump_run(run)
        return bag

    kv_mutate("phieu", mut, {})


def _get_run(phieu_id: str) -> PhieuRun:
    bag = kv_get("phieu", {})
    raw = bag.get(phieu_id)
    if not raw:
        raise HTTPException(status_code=404, detail="phieu_khong_tim_thay")
    return load_run(raw)


def _signals(run: Any, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = run_to_dict(run)
    esc = escalate(run, _clock.now_ms())
    if esc:
        payload["escalate"] = esc
    if extra:
        payload["signals"] = {**payload.get("signals", {}), **extra}
    return cast(dict[str, Any], payload)


class StartBody(BaseModel):
    mau: str = Field(min_length=1)
    ca_id: str = "w1_c01"


class BuocBody(BaseModel):
    ma: str
    gia_tri: Any = None


class ChungBody(BaseModel):
    buoc_ma: str
    data_url: str = ""


class TreoBody(BaseModel):
    noi_dung: str


class CaBody(BaseModel):
    ca_id: str
    # Chỉ dùng cho đường quản lý gán ca (`/ca/nhan-truc-tiep`); đường của nhân
    # viên bỏ qua trường này và luôn thao tác trên chính mình.
    nv_id: str | None = None


class MsgBody(BaseModel):
    text: str
    backend: str = "console"


class TkbExtractBody(BaseModel):
    image_path_or_id: str


def _current_iso_week() -> str:
    iso = datetime.now(UTC).isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


class TkbConfirmBody(BaseModel):
    nv_id: str | None = None
    tuan_iso: str = Field(
        default_factory=_current_iso_week,
        pattern=r"^\d{4}-W(?:0[1-9]|[1-4]\d|5[0-3])$",
    )
    khoang_ban: list[dict[str, str]]
    source_id: str = ""
    upload_id: str = ""


def _tkb_upload_dir() -> Path:
    base = Path(os.environ.get("NHIPQUAN_TKB_UPLOAD", "")).expanduser()
    if not str(base):
        base = db_path().parent / "tkb_uploads"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _clean_khoang_api(raw: list[dict[str, str]]) -> list[dict[str, str]]:
    thu_ok = {"T2", "T3", "T4", "T5", "T6", "T7", "CN"}
    out: list[dict[str, str]] = []
    for item in raw:
        thu = str(item.get("thu") or "").strip().upper()
        if thu in {"CN", "T8"}:
            thu = "CN"
        start = str(item.get("start") or "").strip()
        end = str(item.get("end") or "").strip()
        # AG-TKB có thể trả "07:30:00" — chuẩn hóa về "HH:MM" 5 ký tự
        # trước khi kiểm, nếu không khung giờ thật bị lọc sạch → khoang_rong.
        if len(start) == 8 and start.count(":") == 2:
            start = start[:5]
        if len(end) == 8 and end.count(":") == 2:
            end = end[:5]
        if thu not in thu_ok or len(start) != 5 or len(end) != 5:
            continue
        try:
            start_time = datetime.strptime(start, "%H:%M").time()
            end_time = datetime.strptime(end, "%H:%M").time()
        except ValueError:
            continue
        if start_time >= end_time:
            continue
        out.append({"thu": thu, "start": start, "end": end})
    return out


def _tuan_trang_thai(week: str, store_id: str = "quan_01") -> str:
    """Trạng thái vòng đời của MỘT tuần, đọc mỗi lần gọi.

    Vì sao không lấy từ kv `lich_tuan_lifecycle` trần: khoá đó là bản legacy có
    `tuan_iso` bên trong, và từng gây lỗi thật — tuần mới (W39) thừa hưởng
    `cho_duyet` của W37 nên bấm duyệt báo `authoritative_schedule_run_required`.
    Nguồn đúng là `lich_tuan_lifecycle_by_week` (khoá theo tuần), chỉ rơi về bản
    legacy khi `legacy["tuan_iso"] == week`.

    Không import từ `sprint45._life` ở cấp module để tránh vòng import
    (sprint45 import từ sprint3). Import trong hàm là chủ đích.
    """
    try:
        from ca_api.interfaces.http.sprint45 import _life

        return str(_life(week, store_id=store_id).get("trang_thai") or "nhap")
    except Exception:
        return "nhap"


def _phut(t: str) -> int:
    """'HH:MM' → số phút từ nửa đêm. Chuỗi hỏng trả -1 để không khớp gì."""
    try:
        hh, mm = t.strip()[:5].split(":")
        return int(hh) * 60 + int(mm)
    except (ValueError, AttributeError):
        return -1


def _giao_nhau(a_start: str, a_end: str, b_start: str, b_end: str) -> bool:
    """Hai khung giờ có giao nhau không (nửa mở: chạm mép KHÔNG tính là trùng)."""
    a1, a2, b1, b2 = _phut(a_start), _phut(a_end), _phut(b_start), _phut(b_end)
    if min(a1, a2, b1, b2) < 0:
        return False
    return a1 < b2 and b1 < a2


class TkbXepLaiBody(BaseModel):
    tuan_iso: str = Field(
        default_factory=_current_iso_week,
        pattern=r"^\d{4}-W(?:0[1-9]|[1-4]\d|5[0-3])$",
    )


def _tkb_khoang_cu(nv_id: str, week: str, store_id: str) -> list[dict[str, str]]:
    """Khung bận đã lưu của một người trong một tuần (rỗng nếu chưa có)."""
    doc = kv_get("tkb_nv_by_week", {})
    week_key = week if store_id == "quan_01" else f"{store_id}:{week}"
    week_doc = doc.get(week_key, {}) if isinstance(doc, dict) else {}
    entry = week_doc.get(nv_id) if isinstance(week_doc, dict) else None
    raw = entry.get("khoang_ban") if isinstance(entry, dict) else None
    if not isinstance(raw, list):
        return []
    return [
        {"thu": str(b["thu"]), "start": str(b["start"]), "end": str(b["end"])}
        for b in raw
        if isinstance(b, dict) and b.get("thu") and b.get("start") and b.get("end")
    ]


def _tac_dong_len_lich(
    *,
    nv_id: str,
    week: str,
    store_id: str,
    khoang_moi: list[dict[str, str]],
) -> dict[str, Any]:
    """Cho biết khung bận MỚI có đụng ca nào đã xếp cho tuần đó không.

    Trả `can_chay_lai` = True khi có ca đang giao với khung bận mới — nghĩa là
    lịch hiện tại SAI ràng buộc và người dùng cần chạy lại solver. Đây là mảnh
    còn thiếu khiến "up TKB xong mà lịch không tự đổi": trước kia `tkb_confirm`
    ghi khung rồi kết thúc, không ai nói cho người dùng biết lịch đã lệch.

    KHÔNG tự chạy solver ở đây (đó là quyết định của người dùng, xem
    `POST /api/v1/tkb/xep-lai`) — hàm này chỉ ĐO và BÁO.
    """
    phan = kv_get("phan_cong_by_week", {})
    week_key = week if store_id == "quan_01" else f"{store_id}:{week}"
    week_phan = phan.get(week_key, {}) if isinstance(phan, dict) else {}
    if not isinstance(week_phan, dict):
        week_phan = {}

    # Bản phân công thật nằm ở `phan_cong_by_week` (khoá tuần); bản phẳng
    # `phan_cong` chỉ là bản cũ/legacy. Đọc thêm để không bỏ sót tuần chưa
    # có bản theo tuần (lần xếp đầu tiên).
    if not week_phan:
        flat = kv_get("phan_cong", {})
        week_phan = flat if isinstance(flat, dict) else {}

    # `ca_meta` KHÔNG phải một khoá kv — nó chỉ tồn tại BÊN TRONG kết quả solver
    # (`solver_adapter` trả `"ca_meta": input_data.ca_meta`). Tra từ seed
    # `ca_mau_21` giống phần còn lại của tệp (xem dòng ~143), đừng bịa khoá kv.
    seed_doc = json.loads(SEED.read_text(encoding="utf-8")) if SEED.exists() else {}
    thu_map = {1: "T2", 2: "T3", 3: "T4", 4: "T5", 5: "T6", 6: "T7", 7: "CN"}
    ca_meta: dict[str, dict[str, Any]] = {
        str(c["id"]): {
            "thu": thu_map.get(int(c.get("ngay_offset", 1)), "T2"),
            "khung": str(c.get("khung") or ""),
            "bat_dau": str(c.get("bat_dau") or "07:00"),
            "ket_thuc": str(c.get("ket_thuc") or "12:00"),
        }
        for c in seed_doc.get("ca_mau_21", [])
        if isinstance(c, dict) and c.get("id")
    }

    trung: list[dict[str, Any]] = []
    for ca_id, ids in week_phan.items():
        if not isinstance(ids, list) or nv_id not in [str(x) for x in ids]:
            continue
        meta = ca_meta.get(ca_id)
        if not isinstance(meta, dict):
            continue
        thu = str(meta.get("thu") or "")
        bat_dau = str(meta.get("bat_dau") or "")
        ket_thuc = str(meta.get("ket_thuc") or "")
        for k in khoang_moi:
            if k["thu"] == thu and _giao_nhau(bat_dau, ket_thuc, k["start"], k["end"]):
                trung.append({
                    "ca_id": str(ca_id),
                    "thu": thu,
                    "khung": str(meta.get("khung") or ""),
                    "gio": f"{bat_dau}-{ket_thuc}" if bat_dau and ket_thuc else "",
                    "khoang_ban": f"{k['start']}-{k['end']}",
                })
                break

    trang_thai = _tuan_trang_thai(week, store_id)
    da_cong_bo = trang_thai in {"da_cong_bo", "da_dong"}
    return {
        "nv_id": nv_id,
        "tuan_iso": week,
        "trang_thai": trang_thai,
        "ca_bi_dung": trung,
        "so_ca_bi_dung": len(trung),
        "can_chay_lai": bool(trung),
        "da_cong_bo": da_cong_bo,
        "ly_do": (
            "Khung bận mới trùng giờ với ca đã xếp. Cần xếp lại để lịch tôn trọng ràng buộc."
            if trung
            else "Khung bận mới không đụng ca nào đã xếp."
        ),
    }


class DispatchBody(BaseModel):
    n: int = Field(default=8, ge=1, le=32)
    key: str = "orc-8"


@router.post("/api/v1/diem-danh")
def diem_danh(
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, str]:
    nv = _nv_from_token(authorization)
    ghi_diem_danh(nv)
    audit_add(
        _clock.now_iso(),
        nv,
        "attendance.check_in",
        {
            "entity_type": "attendance",
            "entity_id": nv,
            "nv_id": nv,
            "source": "manual",
        },
    )
    return {"ok": "true", "nv_id": nv}


@router.get("/api/v1/phieu/mau")
def phieu_mau(authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    """Liệt kê các mẫu được quán bật trong cấu hình, không phải mọi fixture."""
    items: list[dict[str, Any]] = []
    for entry in load_phieu_catalog(_store_from_token(authorization)):
        ma = str(entry["ma"])
        tpl = load_template(ma)
        items.append(
            {
                "ma": ma,
                "ten": tpl["ten"],
                "so_buoc": len(tpl["buoc"]),
                "gan_voi": tpl.get("gan_voi", ""),
                "mo_khi": tpl.get("mo_khi", ""),
                "han_hoan_thanh_phut": tpl.get("han_hoan_thanh_phut"),
                "bat_buoc": entry["bat_buoc"],
                "buoc": tpl["buoc"],
            }
        )
    if not items:
        raise HTTPException(status_code=404, detail="khong_co_mau_phieu")
    # Giữ các khoá phẳng của mẫu đầu để không phá client cũ đang đọc `buoc`.
    dau = items[0]
    return {"items": items, "ma": dau["ma"], "ten": dau["ten"], "buoc": dau["buoc"]}


@router.post("/api/v1/phieu/start")
def phieu_start(
    body: StartBody,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    nv = _nv_from_token(authorization)
    catalog = {entry["ma"] for entry in load_phieu_catalog(_store_from_token(authorization))}
    if body.mau not in catalog:
        raise HTTPException(status_code=404, detail="mau_phieu_khong_bat")
    da_diem_danh = nv in set(diem_danh_hom_nay())

    def next_seq(seq: int) -> int:
        return int(seq) + 1

    seq = kv_mutate("phieu_seq", next_seq, 0)
    run_id = f"ph_{seq}"
    try:
        run = start_phieu(
            run_id=run_id,
            mau=body.mau,
            nv_id=nv,
            ca_id=body.ca_id,
            now_ms=_clock.now_ms(),
            diem_danh=da_diem_danh,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    _save_run(run)
    sm = StateMachine()
    sm.transition("dang_chay")
    _sm_by_phieu[run_id] = sm
    return cast(dict[str, Any], run_to_dict(run))


@router.get("/api/v1/phieu/{phieu_id}")
def phieu_get(
    phieu_id: str,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    run = _get_run(phieu_id)
    _can_touch(run, authorization)
    return _signals(run)


@router.post("/api/v1/phieu/{phieu_id}/buoc")
def phieu_buoc(
    phieu_id: str,
    body: BuocBody,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    run = _get_run(phieu_id)
    _can_touch(run, authorization)
    try:
        complete_buoc(run, body.ma, body.gia_tri, _clock.now_ms())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    _save_run(run)
    if run.closed:
        sm = _sm_by_phieu.get(phieu_id)
        if sm and sm.state == "dang_chay":
            sm.transition("xong")
    return _signals(run)


@router.post("/api/v1/phieu/{phieu_id}/minh-chung")
def phieu_chung(
    phieu_id: str,
    body: ChungBody,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    run = _get_run(phieu_id)
    _can_touch(run, authorization)
    if not body.data_url.strip().startswith("data:image/"):
        raise HTTPException(status_code=400, detail="thieu_minh_chung_anh")
    if len(body.data_url) > 400_000:
        raise HTTPException(status_code=400, detail="anh_qua_lon")
    try:
        complete_buoc(run, body.buoc_ma, body.data_url, _clock.now_ms())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    _save_run(run)
    if run.closed:
        sm = _sm_by_phieu.get(phieu_id)
        if sm and sm.state == "dang_chay":
            sm.transition("xong")
    return _signals(run, extra={"minh_chung": True})


@router.post("/api/v1/phieu/{phieu_id}/treo")
def phieu_treo(
    phieu_id: str,
    body: TreoBody,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    run = _get_run(phieu_id)
    _can_touch(run, authorization)
    try:
        add_treo(run, body.noi_dung)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    _save_run(run)

    def mut(hung: list[dict[str, Any]]) -> list[dict[str, Any]]:
        hung.append(
            {
                "id": f"treo_{uuid.uuid4().hex[:8]}",
                "phieu_id": phieu_id,
                "nv_id": run.nv_id,
                "nhan_vien": run.nv_id,
                "noi_dung": body.noi_dung,
                "trang_thai": "dang_cho",
                "created_at": datetime.now(UTC).isoformat(),
            }
        )
        return hung

    kv_mutate("treo", mut, [])
    out = _signals(run)
    out["ok"] = True
    return out


@router.get("/api/v1/viec-treo")
def viec_treo(authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    _require_role(authorization)
    return {"items": kv_get("treo", [])}


class TreoPatchBody(BaseModel):
    trang_thai: str = "xong"


@router.patch("/api/v1/viec-treo/{treo_id}")
def viec_treo_patch(
    treo_id: str,
    body: TreoPatchBody,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    role = _require_manager(authorization)
    found: dict[str, Any] | None = None

    def mut(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        nonlocal found
        for it in items:
            if isinstance(it, dict) and it.get("id") == treo_id:
                it["trang_thai"] = body.trang_thai
                it["xong_luc"] = datetime.now(UTC).isoformat()
                it["xong_boi"] = role
                found = dict(it)
                return items
        raise HTTPException(status_code=404, detail="treo_khong_tim_thay")

    kv_mutate("treo", mut, [])
    if not found:
        raise HTTPException(status_code=404, detail="treo_khong_tim_thay")
    return found


@router.post("/api/v1/orc/dispatch")
def orc_dispatch(
    body: DispatchBody,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _require_manager(authorization)

    def job() -> dict[str, Any]:
        def write(i: int) -> dict[str, Any]:
            _orc_writes[body.key] = _orc_writes.get(body.key, 0) + 1
            return {"i": i, "ok": True}

        # cast: lambda có tham số mặc định nên mypy không suy được kiểu từ ngữ cảnh
        tasks = [cast("Callable[[], dict[str, Any]]", lambda i=i: write(i)) for i in range(body.n)]
        results = dispatch_parallel(tasks)
        return {"n": len(results), "results": results, "writes": _orc_writes[body.key]}

    val, replayed = _idem.once(body.key, job)
    return {"replayed": replayed, **val}


class InboxMsgBody(BaseModel):
    tom_tat: str
    agent: str = "ag_msg"


@router.get("/api/v1/inbox")
def inbox(authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    _require_manager(authorization)
    return {"items": kv_get("inbox_msg", [])}


@router.post("/api/v1/inbox")
def inbox_add(
    body: InboxMsgBody,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _require_manager(authorization)

    def mut(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        items.append(
            {
                "id": f"msg_{uuid.uuid4().hex[:8]}",
                "tom_tat": body.tom_tat,
                "agent": body.agent,
                "trang_thai": "moi",
            }
        )
        return items

    items = kv_mutate("inbox_msg", mut, [])
    return {"ok": True, "n": len(items)}


@router.post("/api/v1/msg/classify")
def msg_classify(
    body: MsgBody,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _require_role(authorization)
    # Phải truyền tuần THẬT làm mốc; nếu để trống, `classify` mặc định
    # "2026-W01" → "tuần sau" tính thành W02 bất kể hôm nay là tuần nào
    # (bug QA đợt 4: mọi ràng buộc nghỉ/đổi ca rơi vào tuần sai).
    r = classify(body.text, base_iso_week=_current_iso_week())
    port = get_port(body.backend)
    recipient = _nv_from_token(authorization) if authorization else "lan"
    sent = port.send(recipient, f"intent={r.intent}")
    return {
        "intent": r.intent,
        "tier": r.tier,
        "do_tin_cay": r.do_tin_cay,
        "rang_buoc": r.rang_buoc,
        "message": sent.__dict__,
    }


@router.post("/api/v1/tkb/extract")
def tkb_extract(
    body: TkbExtractBody,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _require_role(authorization)
    return extract_tkb(body.image_path_or_id, mode=agent_mode())


@router.post("/api/v1/tkb/upload")
async def tkb_upload(
    authorization: Annotated[str | None, Header()] = None,
    file: UploadFile | None = File(None),
    fixture_id: Annotated[str | None, Form()] = None,
) -> dict[str, Any]:
    """Upload ảnh TKB (hoặc dùng fixture_id để thử) → AG-TKB extract."""
    _require_role(authorization)
    upload_id = ""
    source = ""

    if fixture_id and fixture_id.strip():
        source = fixture_id.strip()
        upload_id = f"fixture:{source}"
    elif file is not None and file.filename:
        raw = await file.read()
        if not raw:
            raise HTTPException(status_code=400, detail="file_trong")
        if len(raw) > 8_000_000:
            raise HTTPException(status_code=400, detail="file_qua_lon")
        suffix = Path(file.filename).suffix.lower() or ".jpg"
        if suffix not in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
            raise HTTPException(status_code=400, detail="dinh_dang")
        upload_id = f"up_{uuid.uuid4().hex[:12]}"
        dest = _tkb_upload_dir() / f"{upload_id}{suffix}"
        dest.write_bytes(raw)
        source = str(dest)
    else:
        raise HTTPException(status_code=400, detail="thieu_file")

    # Replay khi fixture; live khi file thật (theo CA_AGENT_MODE).
    mode = "replay" if upload_id.startswith("fixture:") else agent_mode()
    result = extract_tkb(source, mode=mode)
    result["upload_id"] = upload_id
    result["agent_mode"] = mode
    return result


def _busy_to_availability(busy_intervals: list[dict[str, str]]) -> dict[str, list[str]]:
    shifts = ["Sáng", "Chiều", "Tối"]
    all_days = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"]
    shift_ranges = {
        "Sáng": (6 * 60 + 30, 12 * 60),
        "Chiều": (12 * 60, 17 * 60 + 30),
        "Tối": (17 * 60 + 30, 22 * 60 + 30),
    }
    avail = {d: list(shifts) for d in all_days}
    for b in busy_intervals:
        day = b.get("thu")
        start_str = b.get("start", "00:00")
        end_str = b.get("end", "23:59")
        try:
            sh, sm = map(int, start_str.split(":"))
            eh, em = map(int, end_str.split(":"))
            b_start = sh * 60 + sm
            b_end = eh * 60 + em
        except Exception:
            continue
        if day in avail:
            avail[day] = [
                s for s in avail[day]
                if not (b_start < shift_ranges[s][1] and b_end > shift_ranges[s][0])
            ]
            if not avail[day]:
                avail.pop(day, None)
    return avail


@router.post("/api/v1/tkb/confirm")
def tkb_confirm(
    body: TkbConfirmBody,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Xác nhận khoảng bận và gắn vào nhân viên — dùng khi xếp lịch."""
    s = auth_session(authorization)
    if not s:
        raise HTTPException(status_code=401, detail="thieu_token")
    role = s["role"]
    nv = (body.nv_id or "").strip() or s["nv_id"]
    if role not in {"quan_ly", "chu_quan"} and nv != s["nv_id"]:
        raise HTTPException(status_code=403, detail="chi_gan_tkb_cua_minh")
    store_id = s.get("store_id", "quan_01")
    # Xác thực nhân viên thuộc cửa hàng khi quản lý gán cho người khác
    if role in {"quan_ly", "chu_quan"} and nv != s["nv_id"]:
        from ca_api.persist import list_users
        users = list_users(store_id=store_id)
        if not any(u.get("id") == nv for u in users):
            raise HTTPException(status_code=403, detail="nhan_vien_khong_thuoc_cua_hang")

    khoang = _clean_khoang_api(body.khoang_ban)
    if not khoang:
        raise HTTPException(status_code=400, detail="khoang_rong")

    entry = {
        "tuan_iso": body.tuan_iso,
        "khoang_ban": khoang,
        "source_id": body.source_id,
        "upload_id": body.upload_id,
        "xac_nhan_boi": s["nv_id"],
        "vai": role,
    }

    def mut(doc: dict[str, Any]) -> dict[str, Any]:
        week_key = body.tuan_iso if store_id == "quan_01" else f"{store_id}:{body.tuan_iso}"
        week_doc = doc.setdefault(week_key, {})
        if not isinstance(week_doc, dict):
            week_doc = {}
            doc[week_key] = week_doc
        week_doc[nv] = entry
        return doc

    # Đọc khung CŨ trước khi ghi đè — cần để nói cho người dùng biết lịch tuần có
    # bị ảnh hưởng hay không. Không có bước này thì trang TKB im lặng báo "đã gắn"
    # trong khi lịch tuần đã công bố vẫn giữ ca vi phạm khung bận mới.
    khoang_cu = _tkb_khoang_cu(nv, body.tuan_iso, store_id)
    kv_mutate("tkb_nv_by_week", mut, {})

    avail = _busy_to_availability(khoang)
    from ca_api.persist import availability_confirmation_upsert
    availability_confirmation_upsert(
        item_id=f"tkb_{uuid.uuid4().hex[:8]}",
        store_id=store_id,
        nv_id=nv,
        tuan_iso=body.tuan_iso,
        availability=avail,
        status="da_xac_nhan",
        source="tkb_confirm",
    )

    def add_lbc(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        items = [x for x in items if not (x.get("nv_id") == nv and x.get("tuan_iso") == body.tuan_iso)]
        items.append({
            "id": f"lbc_{uuid.uuid4().hex[:8]}",
            "store_id": store_id,
            "nv_id": nv,
            "tuan_iso": body.tuan_iso,
            "status": "da_xac_nhan",
            "availability": avail,
            "busy_intervals": khoang,
            "source": "tkb_confirm",
        })
        return items[-200:]
    kv_mutate("lich_ban_confirmations", add_lbc, [])

    record_sua(
        loai="tkb_xac_nhan",
        truoc={"khoang_ban": khoang_cu},
        sau={"nv_id": nv, "tuan_iso": body.tuan_iso, "n": len(khoang)},
        ai=s["nv_id"],
        now_iso=datetime.now(UTC).isoformat(),
    )
    return {
        "ok": True,
        "nv_id": nv,
        "tuan_iso": body.tuan_iso,
        "khoang_ban": khoang,
        "n": len(khoang),
        "khoang_cu": khoang_cu,
        "tac_dong": _tac_dong_len_lich(
            nv_id=nv,
            week=body.tuan_iso,
            store_id=store_id,
            khoang_moi=khoang,
        ),
    }


@router.post("/api/v1/tkb/xep-lai")
def tkb_xep_lai(
    body: TkbXepLaiBody,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Chạy lại solver cho một tuần sau khi thời khoá biểu bận đã đổi.

    Vì sao cần đường riêng: `tkb_confirm` chỉ GHI khung bận, nên lịch tuần đang
    có vẫn giữ nguyên các ca đã vi phạm khung mới — đúng lỗi người dùng gặp
    ("up xong mà nó không update cho tôi"). Tự chạy solver ngay trong
    `tkb_confirm` thì phá lịch đã công bố mà không hỏi ai; nên tách thành một
    hành động có ý thức, do người dùng bấm.

    Đi qua ĐÚNG một đường sản xuất `run_authoritative_schedule` (cùng hàm mà
    `patch_lifecycle` nhánh `dang_giai` dùng) để không sinh ra nguồn sự thật
    thứ hai. Kết quả trả về kèm DIFF trước/sau để UI chứng minh ai đổi ca.

    Chỉ `quan_ly`/`chu_quan`. Tuần đã công bố vẫn cho chạy, nhưng kết quả ở
    trạng thái `cho_duyet` — phải duyệt lại mới có hiệu lực, không tự công bố.
    """
    s = auth_session(authorization)
    if not s:
        raise HTTPException(status_code=401, detail="thieu_token")
    role = str(s.get("role") or "")
    if role not in {"quan_ly", "chu_quan"}:
        raise HTTPException(status_code=403, detail="chi_quan_ly_xep_lai")
    store_id = str(s.get("store_id") or "quan_01")
    week = body.tuan_iso

    from ca_api.interfaces.http.sprint45 import _life, _save_life
    from ca_api.services.schedule_diff import so_sanh_phan_cong, tom_tat_thay_doi
    from ca_api.services.scheduling_service import (
        authoritative_input_fingerprint,
        run_authoritative_schedule,
    )

    truoc_phan = kv_get("phan_cong_by_week", {})
    week_key = week if store_id == "quan_01" else f"{store_id}:{week}"
    truoc = truoc_phan.get(week_key, {}) if isinstance(truoc_phan, dict) else {}
    if not isinstance(truoc, dict):
        truoc = {}

    _, fingerprint = authoritative_input_fingerprint(store_id, week)
    authoritative = run_authoritative_schedule(
        store_id=store_id,
        tuan_iso=week,
        actor_id=s["nv_id"],
        idempotency_key=f"tkb-xep-lai:{week}:{fingerprint[:16]}",
    )
    ket_qua = cast(dict[str, Any], authoritative.get("result") or {})

    if not ket_qua.get("ok"):
        # Không đủ người khả dụng → giữ nguyên lịch cũ, trả lý do cụ thể.
        return {
            "ok": False,
            "tuan_iso": week,
            "ly_do": "khong_xep_duoc",
            "danh_sach_xung_dot": ket_qua.get("danh_sach_xung_dot") or [],
            "diff": None,
        }

    sau = cast(dict[str, Any], ket_qua.get("phan_cong") or {})
    diff = so_sanh_phan_cong(
        cast(dict[str, list[str]], truoc),
        sau,
        ca_meta=cast(dict[str, Any], ket_qua.get("ca_meta") or {}),
        nhan_vien=_nhan_vien_map(store_id),
    )

    doc = _life(week, store_id=store_id)
    doc["trang_thai"] = "cho_duyet"
    doc["tuan_iso"] = week
    doc["cap_nhat_luc"] = datetime.now(UTC).isoformat()
    doc["cap_nhat_boi"] = role
    _save_life(doc, store_id=store_id)

    record_sua(
        loai="tkb_xep_lai",
        truoc={"so_o_ca": len(truoc)},
        sau={"tuan_iso": week, "so_o_ca": len(sau), "thay_doi": tom_tat_thay_doi(diff)},
        ai=s["nv_id"],
        now_iso=datetime.now(UTC).isoformat(),
    )

    return {
        "ok": True,
        "tuan_iso": week,
        "trang_thai": "cho_duyet",
        "solver": ket_qua,
        "diff": diff,
        "tom_tat": tom_tat_thay_doi(diff),
    }


def _nhan_vien_map(store_id: str) -> dict[str, Any]:
    """Map nv_id → tên để diff in ra TÊN người, không phải mã `nv_xx`.

    Ưu tiên nguồn THẬT (`list_nhan_vien_ops` = users + seed) để nhân viên tự
    đăng ký (chỉ có trong DB) cũng hiện tên; seed chỉ là fallback khi nguồn
    thật rỗng (bug QA đợt 4: map cũ chỉ đọc seed nên NV mới hiện mã `nv_xx`).
    """
    out: dict[str, Any] = {}
    try:
        from ca_api.nhan_vien import list_nhan_vien_ops

        for n in list_nhan_vien_ops():
            nid = n.get("id") or n.get("nv_id")
            if nid:
                out[str(nid)] = {"ten": str(n.get("ten") or nid)}
    except Exception:
        out = {}
    if not out:
        seed_doc = json.loads(SEED.read_text(encoding="utf-8")) if SEED.exists() else {}
        for n in seed_doc.get("nhan_vien", []):
            if isinstance(n, dict) and n.get("id"):
                out[str(n["id"])] = {"ten": str(n.get("ten") or n.get("ho_ten") or n["id"])}
    return out


@router.get("/api/v1/tkb/mine")
def tkb_mine(
    tuan_iso: str | None = None,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    nv = _nv_from_token(authorization)
    s = auth_session(authorization) or {}
    store_id = s.get("store_id", "quan_01")
    week = tuan_iso or _current_iso_week()
    by_week = kv_get("tkb_nv_by_week", {})
    week_key = week if store_id == "quan_01" else f"{store_id}:{week}"
    week_doc = by_week.get(week_key, {}) if isinstance(by_week, dict) else {}
    item = week_doc.get(nv) if isinstance(week_doc, dict) else None
    if item is None:
        legacy = kv_get("tkb_nv", {})
        candidate = legacy.get(nv) if isinstance(legacy, dict) else None
        if isinstance(candidate, dict) and candidate.get("tuan_iso") == week:
            item = candidate
    return {"nv_id": nv, "tuan_iso": week, "item": item, "nguon": "quan"}


@router.get("/api/v1/tkb/{nv_id}")
def tkb_get(
    nv_id: str,
    tuan_iso: str | None = None,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    s = auth_session(authorization)
    if not s:
        raise HTTPException(status_code=401, detail="thieu_token")
    if s["role"] not in {"quan_ly", "chu_quan"} and s["nv_id"] != nv_id:
        raise HTTPException(status_code=403, detail="cam")
    store_id = s.get("store_id", "quan_01")
    week = tuan_iso or _current_iso_week()
    by_week = kv_get("tkb_nv_by_week", {})
    week_key = week if store_id == "quan_01" else f"{store_id}:{week}"
    week_doc = by_week.get(week_key, {}) if isinstance(by_week, dict) else {}
    item = week_doc.get(nv_id) if isinstance(week_doc, dict) else None
    if item is None:
        legacy = kv_get("tkb_nv", {})
        candidate = legacy.get(nv_id) if isinstance(legacy, dict) else None
        if isinstance(candidate, dict) and candidate.get("tuan_iso") == week:
            item = candidate
    return {"nv_id": nv_id, "tuan_iso": week, "item": item, "nguon": "quan"}


@router.get("/api/v1/toi/lich")
def toi_lich(
    tuan: Annotated[str | None, Query(description="Tuần ISO, vd 2026-W38")] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    nv = _nv_from_token(authorization)
    target_week = (tuan or "").strip() or _current_week()
    phan = _phan_cong(target_week)
    seed = json.loads(SEED.read_text(encoding="utf-8")) if SEED.exists() else {}
    meta = {c["id"]: c for c in seed.get("ca_mau_21", [])}
    thu = {1: "T2", 2: "T3", 3: "T4", 4: "T5", 5: "T6", 6: "T7", 7: "CN"}
    mine_ids = [cid for cid, nvs in phan.items() if nv in nvs]
    # Ca TÔI CÓ THỂ NHẬN: chưa có tôi, và tuần đã công bố (nhận ca là thay đổi
    # phân công nên chỉ có nghĩa khi lịch đã chốt). Trước đây UI tự suy từ
    # `co_the_nhan` của TẤT CẢ ca nên hiện cả ca của người khác ở tuần nháp.
    co_the_nhan_ids = [
        cid
        for cid, nvs in phan.items()
        if nv not in nvs and cid in meta
    ]
    ca = []
    for cid in mine_ids:
        fallback = {
            "id": cid,
            "bat_dau": "07:00",
            "ket_thuc": "12:00",
            "vi_tri": "pha_che",
            "ngay_offset": 1,
        }
        m = meta.get(cid, fallback)
        nguoi_trong_ca = [x for x in phan.get(cid, []) if x != nv]
        ca.append(
            {
                "id": cid,
                "ngay": thu.get(int(m.get("ngay_offset", 1)), "T2"),
                "bat_dau": m.get("bat_dau", "07:00"),
                "ket_thuc": m.get("ket_thuc", "12:00"),
                "vi_tri": m.get("vi_tri", ""),
                "khung": m.get("khung", ""),
                # `trang_thai` là nguồn sự thật cho nhãn "Ca của bạn" ở UI.
                # Trước đây trường này KHÔNG hề được set, nên UI so
                # `trang_thai === "cua_toi"` luôn sai và nhãn đó là code chết.
                "trang_thai": "cua_toi",
                "co_the_nha": nv in phan.get(cid, []),
                "co_the_nhan": False,
                "nguoi_khac_trong_ca": nguoi_trong_ca,
                "so_nguoi_trong_ca": len(phan.get(cid, [])),
            }
        )
    for cid in co_the_nhan_ids:
        fallback = {"id": cid, "bat_dau": "07:00", "ket_thuc": "12:00", "vi_tri": "pha_che", "ngay_offset": 1}
        m = meta.get(cid, fallback)
        ca.append(
            {
                "id": cid,
                "ngay": thu.get(int(m.get("ngay_offset", 1)), "T2"),
                "bat_dau": m.get("bat_dau", "07:00"),
                "ket_thuc": m.get("ket_thuc", "12:00"),
                "vi_tri": m.get("vi_tri", ""),
                "khung": m.get("khung", ""),
                "trang_thai": "co_the_nhan",
                "co_the_nha": False,
                "co_the_nhan": True,
                "nguoi_khac_trong_ca": [x for x in phan.get(cid, []) if x != nv],
                "so_nguoi_trong_ca": len(phan.get(cid, [])),
            }
        )
    # Ràng buộc đã duyệt liên quan tới tôi (xin nghỉ / TKB bận) — để nhân viên
    # thấy hiệu lực sau khi quản lý duyệt ở /inbox, không phải chờ xếp lịch sau.
    inbox_duyet = [
        {
            "id": it.get("id"),
            "y_dinh": it.get("y_dinh"),
            "ghi": (it.get("hieu_luc") or {}).get("ghi", ""),
        }
        for it in kv_get("inbox_rang_buoc", [])
        if isinstance(it, dict)
        and it.get("trang_thai") == "duyet"
        and it.get("nv_id") == nv
    ]
    by_week_life = kv_get("lich_tuan_lifecycle_by_week", {})
    life_doc = by_week_life.get(target_week) if isinstance(by_week_life, dict) else None
    if not life_doc:
        life_doc = kv_get("lich_tuan_lifecycle", {})
    trang_thai = (life_doc.get("trang_thai") if isinstance(life_doc, dict) else None) or "may_sinh"

    from ca_api.persist import list_users
    users = list_users()
    matched_user = next((u for u in users if u.get("id") == nv or u.get("nv_id") == nv), None)
    nv_status = (matched_user.get("status") if matched_user else "active") or "active"

    da_cong_bo = trang_thai in {"da_cong_bo", "da_dong"}
    return {
        "nv_id": nv,
        "tuan_iso": target_week,
        "trang_thai": trang_thai,
        "nv_status": nv_status,
        "da_cong_bo": da_cong_bo,
        "ca": ca,
        "ca_ids": mine_ids,
        "items": ca,
        "rang_buoc_da_duyet": inbox_duyet,
        "tom_tat": _tom_tat_ca_cua_toi(
            nv=nv,
            week=target_week,
            trang_thai=trang_thai,
            da_cong_bo=da_cong_bo,
            ca_cua_toi=[c for c in ca if c["trang_thai"] == "cua_toi"],
            ca_co_the_nhan=[c for c in ca if c["trang_thai"] == "co_the_nhan"],
            rang_buoc=inbox_duyet,
        ),
    }


def _tom_tat_ca_cua_toi(
    *,
    nv: str,
    week: str,
    trang_thai: str,
    da_cong_bo: bool,
    ca_cua_toi: list[dict[str, Any]],
    ca_co_the_nhan: list[dict[str, Any]],
    rang_buoc: list[dict[str, Any]],
) -> dict[str, Any]:
    """Trợ lý tóm tắt trang "Ca của tôi" — NÓI RÕ đang ở đâu và cần làm gì.

    Vì sao trả CẤU TRÚC thay vì một câu văn: cùng dữ liệu này còn phải vẽ được
    thành các dòng có nhãn trên UI. Trả câu văn thì UI phải parse lại, còn trả
    cấu trúc thì cả người đọc lẫn máy đọc đều dùng được.

    Quy tắc quan trọng nhất: khi tuần CHƯA công bố thì nói thẳng là chưa nhận
    ca được, KHÔNG im lặng để người dùng bấm nút rồi nhận lỗi.
    """
    TRANG_THAI_LABEL = {
        "may_sinh": "Máy đang sinh lịch",
        "nhap": "Đang chuẩn bị (nháp)",
        "dang_giai": "Đang xếp lịch",
        "cho_duyet": "Chờ quản lý duyệt",
        "da_duyet": "Đã duyệt",
        "da_cong_bo": "Đã công bố",
        "da_dong": "Đã đóng",
    }

    if not ca_cua_toi and not ca_co_the_nhan:
        tinh_trang = "chua_co_lich"
        can_lam = (
            "Tuần này bạn chưa được xếp ca nào."
            if da_cong_bo
            else "Tuần này chưa có lịch chính thức — chờ quản lý xếp và công bố."
        )
    elif da_cong_bo:
        tinh_trang = "co_the_thao_tac"
        phan = [f"bạn có {len(ca_cua_toi)} ca"]
        if ca_co_the_nhan:
            phan.append(f"{len(ca_co_the_nhan)} ca có thể nhận")
        can_lam = (
            "Lịch đã công bố: " + ", ".join(phan) + ". "
            "Nhả ca thì bấm Nhả (có hiệu lực ngay). Nhận ca cần quản lý xác nhận."
        )
    else:
        tinh_trang = "cho_cong_bo"
        can_lam = (
            f"Tuần {week} đang «{TRANG_THAI_LABEL.get(trang_thai, trang_thai)}» — "
            "chưa thể nhận/nhả ca. Ca của bạn chỉ xem được, chờ công bố."
        )

    return {
        "tuan_iso": week,
        "trang_thai": trang_thai,
        "trang_thai_label": TRANG_THAI_LABEL.get(trang_thai, trang_thai),
        "da_cong_bo": da_cong_bo,
        "tinh_trang": tinh_trang,
        "so_ca_cua_toi": len(ca_cua_toi),
        "so_ca_co_the_nhan": len(ca_co_the_nhan),
        "so_rang_buoc_da_duyet": len(rang_buoc),
        "can_lam": can_lam,
    }


@router.post("/api/v1/ca/nha")
def ca_nha(body: CaBody, authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    """Nhả ca — nhân viên tự nguyện rút khỏi ca của mình.

    Cổng công bố: CHỈ cho nhả khi lịch đã công bố. Lý do là chính dòng mô tả
    trang đang hứa — "nhả/nhận ca khi lịch đã công bố". Tuần còn nháp thì phân
    công chưa chốt, nhả ca ở đó là sửa một bản nháp mà quản lý còn đang xếp.
    """
    nv = _nv_from_token(authorization)
    if not _known_ca(body.ca_id):
        raise HTTPException(status_code=404, detail="ca_khong_tim_thay")

    week = _current_week()
    trang_thai = _tuan_trang_thai(week)
    if trang_thai not in {"da_cong_bo", "da_dong"}:
        # Kèm trạng thái thật để UI nói được ĐANG ở bước nào, thay vì chỉ "không
        # được". Không có nó thì người dùng bấm nút rồi nhận câu từ chối chung
        # chung và không biết chờ ai — đúng phàn nàn "cái nút đó đâu còn ý nghĩa".
        raise HTTPException(
            status_code=409,
            detail=f"lich_chua_cong_bo:{trang_thai}",
        )
    state: dict[str, Any] = {"truoc": [], "sau": []}

    def mut(phan: dict[str, list[str]]) -> dict[str, list[str]]:
        truoc = list(phan.get(body.ca_id, []))
        if nv not in truoc:
            raise HTTPException(status_code=409, detail="khong_trong_ca")
        sau = [x for x in truoc if x != nv]
        phan[body.ca_id] = sau
        state["truoc"] = truoc
        state["sau"] = sau
        return phan

    base = _phan_cong()
    kv_mutate("phan_cong", mut, base)

    def mut_week(all_weeks: dict[str, Any]) -> dict[str, Any]:
        week_pc = all_weeks.setdefault(week, {})
        week_pc[body.ca_id] = list(state["sau"])
        return all_weeks
    kv_mutate("phan_cong_by_week", mut_week, {})

    def mut_results(results: dict[str, Any]) -> dict[str, Any]:
        if week in results and isinstance(results[week], dict):
            pc = results[week].setdefault("phan_cong", {})
            pc[body.ca_id] = list(state["sau"])
        return results
    kv_mutate("lich_tuan_results_by_week", mut_results, {})

    record_sua(
        loai="nha_ca",
        truoc={"ca_id": body.ca_id, "nv": state["truoc"]},
        sau={"ca_id": body.ca_id, "nv": state["sau"]},
        ai=nv,
        now_iso=_clock.now_iso(),
    )
    return {
        "ok": True,
        "ca_id": body.ca_id,
        "hanh_dong": "nha",
        "tuan_iso": week,
        "truoc": state["truoc"],
        "sau": state["sau"],
    }


@router.post("/api/v1/ca/nhan")
def ca_nhan(body: CaBody, authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    """Nhận ca — CHỈ khi lịch đã công bố, và KHÔNG ghi thẳng vào phân công.

    Vì sao không ghi thẳng: nhận một ca ở tuần đã công bố là thay đổi lịch mà
    người khác đang chạy theo — phải qua đồng ý hai bên. Trước đây endpoint này
    ghi thẳng `phan_cong` cho bất kỳ ai đăng nhập, không cần ai duyệt, kể cả ca
    của người khác ở tuần chưa công bố.

    Đường đúng để nhận ca là `Chợ đổi ca` (`/doi-ca`) — ở đó có bước cả hai bên
    đồng ý và quản lý duyệt. Endpoint này trả 409 kèm chỉ dẫn để UI mở đúng chỗ,
    thay vì im lặng ghi rồi để hậu quả hiện ra sau.
    """
    # Vẫn phải xác thực người gọi trước khi nói "không được phép" — nếu không,
    # người chưa đăng nhập cũng đọc ra được thông báo rằng ca này tồn tại.
    _nv_from_token(authorization)
    if not _known_ca(body.ca_id):
        raise HTTPException(status_code=404, detail="ca_khong_tim_thay")

    week = _current_week()
    trang_thai = _tuan_trang_thai(week)
    if trang_thai not in {"da_cong_bo", "da_dong"}:
        raise HTTPException(status_code=409, detail="lich_chua_cong_bo")
    raise HTTPException(status_code=409, detail="nhan_ca_phai_qua_cho_doi_ca")


@router.post("/api/v1/ca/nhan-truc-tiep")
def ca_nhan_truc_tiep(
    body: CaBody, authorization: Annotated[str | None, Header()] = None
) -> dict[str, Any]:
    """Nhận ca trực tiếp — chỉ quản lý/chủ quán, dùng cho ca thiếu người.

    Tách khỏi `ca_nhan` để đường của nhân viên bắt buộc đi qua chợ đổi ca. Nhân
    viên gọi endpoint này sẽ bị 403.
    """
    s = auth_session(authorization)
    if not s:
        raise HTTPException(status_code=401, detail="thieu_token")
    role = str(s.get("role") or "")
    if role not in {"quan_ly", "chu_quan"}:
        raise HTTPException(status_code=403, detail="chi_quan_ly_gan_ca")
    nv = str(body.nv_id or s["nv_id"])
    if not _known_ca(body.ca_id):
        raise HTTPException(status_code=404, detail="ca_khong_tim_thay")
    state: dict[str, Any] = {"truoc": [], "sau": []}

    def mut(phan: dict[str, list[str]]) -> dict[str, list[str]]:
        truoc = list(phan.get(body.ca_id, []))
        if nv in truoc:
            raise HTTPException(status_code=409, detail="da_trong_ca")
        sau = [*truoc, nv]
        phan[body.ca_id] = sau
        state["truoc"] = truoc
        state["sau"] = sau
        return phan

    base = _phan_cong()
    kv_mutate("phan_cong", mut, base)

    week = _current_week()
    def mut_week(all_weeks: dict[str, Any]) -> dict[str, Any]:
        week_pc = all_weeks.setdefault(week, {})
        week_pc[body.ca_id] = list(state["sau"])
        return all_weeks
    kv_mutate("phan_cong_by_week", mut_week, {})

    def mut_results(results: dict[str, Any]) -> dict[str, Any]:
        if week in results and isinstance(results[week], dict):
            pc = results[week].setdefault("phan_cong", {})
            pc[body.ca_id] = list(state["sau"])
        return results
    kv_mutate("lich_tuan_results_by_week", mut_results, {})

    record_sua(
        loai="nhan_ca",
        truoc={"ca_id": body.ca_id, "nv": state["truoc"]},
        sau={"ca_id": body.ca_id, "nv": state["sau"]},
        ai=s["nv_id"],
        now_iso=_clock.now_iso(),
    )
    return {
        "ok": True,
        "ca_id": body.ca_id,
        "hanh_dong": "nhan",
        "nv_id": nv,
        "tuan_iso": week,
        "truoc": state["truoc"],
        "sau": state["sau"],
    }


@router.get("/api/v1/ghi-nhan-sua")
def ghi_nhan(authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    """Sổ lần sửa lịch — kể cả dòng dựng lại, nhưng nói rõ dòng nào là dựng lại.

    Trước đây hàm này lọc `include_synthetic=False`, nên khi quán chưa nhả/nhận
    ca lần nào thì bảng rỗng trắng — người dùng không thấy sổ này để làm gì. Giờ
    trả cả dòng fixture, mỗi dòng kèm `nguon` để không ai nhầm dựng lại là ghi
    thật. Cổng chặn luật (`/cam-nang/chay-8-buoc`) VẪN chỉ đếm dòng ghi trực
    tiếp, nên số #10 "0 luật quán thật" không bị fixture làm sai.
    """
    _require_role(authorization)
    items = []
    for i, row in enumerate(list_sua()):
        la_dung_lai = bool(row.get("synthetic"))
        mac_dinh = "mo_phong_fixture" if la_dung_lai else "ghi_truc_tiep"
        items.append(
            {
                "id": f"sua_{i}",
                "loai": row.get("loai"),
                "truoc": json.dumps(row.get("truoc"), ensure_ascii=False),
                "sau": json.dumps(row.get("sau"), ensure_ascii=False),
                "created_at": row.get("at"),
                "luc": row.get("at"),
                "ai": row.get("ai"),
                "nguon": row.get("nguon") or mac_dinh,
                "dung_lai": la_dung_lai,
            }
        )
    so_that = sum(1 for x in items if not x["dung_lai"])
    return {"items": items, "so_ghi_truc_tiep": so_that, "so_dung_lai": len(items) - so_that}


@router.post("/api/v1/import/nhan-vien")
def import_nv(
    body: dict[str, str],
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """CSV phần 1 — parse text, no live spreadsheet vendor."""
    _require_manager(authorization)
    raw = body.get("csv", "id,ten\nnv_x,Import")
    rows = list(csv.DictReader(io.StringIO(raw)))
    return {"n": len(rows), "preview": rows[:5], "nguon": "csv_p1"}
