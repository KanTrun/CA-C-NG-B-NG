"""HTTP router for AI Meeting OS — Transcription, Extraction, and Operational Application."""

from __future__ import annotations

import asyncio
import base64
import json
import re

try:
    from datetime import UTC, datetime
except ImportError:
    from datetime import datetime, timezone
    UTC = timezone.utc
import os
import uuid
from pathlib import Path
from typing import Annotated, Any, cast

from ca_agents.ag_meeting import (
    clarify_meeting_actions,
    create_meeting_stream_session,
    extract_meeting,
    transcribe_audio_live,
    transcribe_audio_live_async,
)
from ca_contracts import CuocHop
from fastapi import (
    APIRouter,
    File,
    Form,
    Header,
    HTTPException,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from pydantic import BaseModel, Field

from ca_api.interfaces.http.sprint3 import _nv_from_token, _require_manager, _require_role
from ca_api.persist import audit_add, kv_get, kv_mutate, list_users
from ca_api.persist import session as auth_session

router = APIRouter(tags=["meeting"])
ROOT = Path(__file__).resolve().parents[6]
SEED = ROOT / "data" / "seed" / "sample.json"

# Giới hạn file âm thanh cuộc họp — Gemini nhận tối đa ~20MB inline, chặn 25MB
# ở cổng để không đọc cả payload vào RAM rồi mới phát hiện file 500MB.
AUDIO_TOI_DA_BYTES = 25_000_000
_AUDIO_MIME_CHO_PHEP = {
    "audio/webm",
    "audio/mp3",
    "audio/wav",
    "audio/ogg",
    "audio/aac",
    "audio/m4a",
    "audio/flac",
}


def _clean_audio_mime(mime: str | None) -> str:
    """Chuẩn hóa MIME: bỏ tham số `;codecs=opus`, chỉ nhận whitelist của STT."""
    clean = (mime or "audio/webm").split(";")[0].strip().lower()
    return clean if clean in _AUDIO_MIME_CHO_PHEP else "audio/webm"


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _get_staff_list() -> list[dict[str, Any]]:
    """Danh sách NV để AG-MEETING gán người phụ trách.

    Chỉ dùng NV CÓ THẬT (pool đang xếp lịch). Trước đây truyền
    `include_seed=True` nên agent có thể gán việc cho `nv_20..nv_25` — mã chỉ
    có trong seed fixture, không tồn tại trong DB (bug QA đợt 4).
    """
    try:
        from ca_api.nhan_vien import list_nhan_vien_ops

        staff = [n for n in list_nhan_vien_ops() if n.get("id")]
        if staff:
            return staff
    except Exception:
        pass
    users = list_users()
    if users:
        return [
            {
                "id": u.get("nv_id") or u.get("username"),
                "ten": u.get("display_name") or u.get("username"),
            }
            for u in users
        ]
    return []


def _get_roster_data() -> tuple[dict[str, list[str]], list[dict[str, Any]]]:
    """Retrieve active schedule assignments and shift definitions."""
    import json

    seed_data: dict[str, Any] = {}
    if SEED.exists():
        try:
            seed_data = json.loads(SEED.read_text(encoding="utf-8"))
        except Exception:
            pass

    ca_raw = seed_data.get("ca_mau_21", [])
    ca_list: list[dict[str, Any]] = []
    thu_map = {1: "T2", 2: "T3", 3: "T4", 4: "T5", 5: "T6", 6: "T7", 7: "CN"}
    for c in ca_raw:
        c_copy = dict(c)
        if "thu" not in c_copy or not c_copy["thu"]:
            c_copy["thu"] = thu_map.get(int(c_copy.get("ngay_offset", 1)), "T2")
        ca_list.append(c_copy)

    phan_cong: dict[str, list[str]] = dict(kv_get("phan_cong", {}) or {})
    if not phan_cong:
        _env_out = os.environ.get("NHIPQUAN_LICH_TUAN_OUT")
        lich_tuan_out = Path(_env_out) if _env_out else ROOT / "data" / "out" / "lich_tuan.json"
        if lich_tuan_out.exists():
            try:
                sol_data = json.loads(lich_tuan_out.read_text(encoding="utf-8"))
                phan_cong = sol_data.get("phan_cong", {}) or {}
            except Exception:
                pass
    if not phan_cong:
        lich_su = seed_data.get("lich_su_phan_cong", {})
        if isinstance(lich_su, dict):
            for _w, asg in lich_su.items():
                if isinstance(asg, dict) and asg:
                    phan_cong = asg
                    break

    return phan_cong, ca_list


class AnalyzeMeetingBody(BaseModel):
    text: str
    segments: list[dict[str, Any]] = Field(default_factory=list)
    meeting_type: str = "giao_ca"
    audio_source: str = "google_meet_tab"
    meeting_id: str | None = None
    thoi_gian: str | None = None


class TranscribeAudioBody(BaseModel):
    audio_base64: str
    mime_type: str = "audio/webm"


@router.post("/api/v1/meeting/transcribe")
def transcribe_audio_endpoint(
    body: TranscribeAudioBody,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Convert audio bytes to transcript with speaker diarization."""
    _require_role(authorization)
    try:
        audio_bytes = base64.b64decode(body.audio_base64)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid base64: {exc}") from exc
    if len(audio_bytes) > AUDIO_TOI_DA_BYTES:
        raise HTTPException(status_code=413, detail="audio_qua_lon_toi_da_25mb")

    res = transcribe_audio_live(audio_bytes=audio_bytes, mime_type=_clean_audio_mime(body.mime_type))
    return {
        "ok": res.ok,
        "raw_text": res.raw_text,
        "segments": [
            {
                "nguoi_noi": s.nguoi_noi,
                "noi_dung": s.noi_dung,
                "bat_dau_s": s.bat_dau_s,
                "ket_thuc_s": s.ket_thuc_s,
            }
            for s in res.segments
        ],
        "provider": res.provider,
        "reason": res.reason,
    }


@router.post("/api/v1/meeting/analyze")
def analyze_meeting_endpoint(
    body: AnalyzeMeetingBody,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Analyze meeting transcript into structured CuocHop contract."""
    _require_role(authorization)
    staff = _get_staff_list()
    res = extract_meeting(
        text=body.text,
        segments=body.segments,
        staff_list=staff,
        meeting_type=body.meeting_type,
        meeting_id=body.meeting_id,
        audio_source=body.audio_source,
        thoi_gian=body.thoi_gian,
    )
    if "action_items" in res and res["action_items"]:
        phan_cong, ca_list = _get_roster_data()
        res["action_items"] = clarify_meeting_actions(
            actions=res["action_items"],
            staff_list=staff,
            phan_cong=phan_cong,
            ca_list=ca_list,
        )
    return res


@router.post("/api/v1/meeting/process-audio")
async def process_audio_upload(
    file: UploadFile = File(...),
    meeting_type: str = Form("giao_ca"),
    audio_source: str = Form("google_meet_tab"),
    live_transcript: str = Form(""),
    thoi_gian: str = Form(""),
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """1-step pipeline: Upload audio file -> STT with Diarization -> Extract CuocHop."""
    _require_role(authorization)
    audio_bytes = await file.read()
    if len(audio_bytes) > AUDIO_TOI_DA_BYTES:
        raise HTTPException(status_code=413, detail="audio_qua_lon_toi_da_25mb")
    # TC-33: Detect disguised video (.mov/.mp4 renamed as .mp3) or corrupt stream
    is_disguised_video = len(audio_bytes) >= 8 and (
        b"ftypqt" in audio_bytes[:32]
        or b"ftypisom" in audio_bytes[:32]
        or b"corrupted" in audio_bytes[:32]
    )
    if is_disguised_video:
        raise HTTPException(
            status_code=400,
            detail="Không thể đọc file âm thanh, vui lòng kiểm tra lại định dạng.",
        )

    trans_res = await transcribe_audio_live_async(
        audio_bytes=audio_bytes, mime_type=_clean_audio_mime(file.content_type)
    )
    if not trans_res.ok and not live_transcript.strip():
        raise HTTPException(
            status_code=400,
            detail="Không thể đọc file âm thanh, vui lòng kiểm tra lại định dạng.",
        )

    staff = _get_staff_list()

    raw_text = trans_res.raw_text.strip()
    segments = [
        {
            "nguoi_noi": s.nguoi_noi,
            "noi_dung": s.noi_dung,
            "bat_dau_s": s.bat_dau_s,
            "ket_thuc_s": s.ket_thuc_s,
        }
        for s in trans_res.segments
    ]

    # If backend STT was empty or fallback, use live_transcript captured directly from user speech
    if (not raw_text or trans_res.provider == "replay_fixture") and live_transcript.strip():
        raw_text = live_transcript.strip()
        segments = [{"nguoi_noi": "Người nói", "noi_dung": live_transcript.strip()}]

    meeting_data = extract_meeting(
        text=raw_text,
        segments=segments,
        staff_list=staff,
        meeting_type=meeting_type,
        audio_source=audio_source,
        thoi_gian=thoi_gian or None,
    )
    if "action_items" in meeting_data and meeting_data["action_items"]:
        phan_cong, ca_list = _get_roster_data()
        meeting_data["action_items"] = clarify_meeting_actions(
            actions=meeting_data["action_items"],
            staff_list=staff,
            phan_cong=phan_cong,
            ca_list=ca_list,
        )
    return meeting_data


class ClarifyActionsBody(BaseModel):
    action_items: list[dict[str, Any]]
    transcript: str = ""


@router.post("/api/v1/meeting/clarify-actions")
def clarify_actions_endpoint(
    body: ClarifyActionsBody,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Re-clarify action items with active schedule and staff assignments."""
    _require_role(authorization)
    staff = _get_staff_list()
    phan_cong, ca_list = _get_roster_data()
    clarified = clarify_meeting_actions(
        actions=body.action_items,
        staff_list=staff,
        phan_cong=phan_cong,
        ca_list=ca_list,
    )
    return {"ok": True, "action_items": clarified}


@router.post("/api/v1/meeting/apply")
def apply_meeting_decisions(
    body: CuocHop,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Human-in-the-loop: Apply approved action items to opsengine and playbook."""
    try:
        user = _require_manager(authorization)
    except HTTPException as exc:
        if exc.status_code == 403:
            raise HTTPException(
                status_code=403,
                detail="Chỉ Quản lý hoặc Chủ quán mới có quyền duyệt phân công.",
            ) from exc
        raise
    now_iso = _now()

    # 1. Add selected action items to opsengine (treo) or route gop_y
    selected_actions = [a for a in body.action_items if a.da_chon]
    created_tasks = 0
    gop_y_converted: list[dict[str, Any]] = []

    if selected_actions:

        def mut_treo(cur: list[Any]) -> list[Any]:
            nonlocal created_tasks
            res = list(cur)
            da_co_treo = {
                (x.get("meeting_id"), x.get("noi_dung"))
                for x in res
                if isinstance(x, dict)
            }
            # TC-30 / R09: Active open tasks (dang_cho) across all meetings to prevent cross-meeting duplication
            open_tasks = {
                (
                    str(x.get("nv_id") or x.get("nhan_vien") or "").strip().lower(),
                    re.sub(r"^\[.*?\]\s*", "", str(x.get("noi_dung") or "")).split(" [Ca:")[0].split(" (Hạn:")[0].strip().lower(),
                )
                for x in res
                if isinstance(x, dict) and x.get("trang_thai") == "dang_cho"
            }
            for act in selected_actions:
                if getattr(act, "loai_cong_viec", "1_ca") == "gop_y":
                    gop_y_converted.append(
                        {
                            "id": f"fb_act_{act.id}",
                            "nguoi_gop_y": act.ten_nguoi_giao or str(user),
                            "nguoi_nhan": act.ten_nguoi_nhan or "Tất cả",
                            "chu_de": "luu_y_chung",
                            "tinh_chat": "gop_y",
                            "noi_dung": act.tieu_de,
                            "ghi_chu": act.noi_dung_chi_tiet or f"Góp ý từ cuộc họp: {body.tieu_de}",
                        }
                    )
                    continue

                task_noi_dung = f"[{body.tieu_de}] {act.tieu_de}"
                if getattr(act, "ca_thuc_hien", None):
                    task_noi_dung += f" [Ca: {act.ca_thuc_hien}]"
                if act.han_chot:
                    task_noi_dung += f" (Hạn: {act.han_chot})"
                if (body.id, task_noi_dung) in da_co_treo:
                    continue

                act_nv = str(act.nhan_vien_id or act.ten_nguoi_nhan or "").strip().lower()
                act_core = str(act.tieu_de or "").strip().lower()
                if (act_nv, act_core) in open_tasks:
                    continue

                treo_item = {
                    "id": f"treo_{uuid.uuid4().hex[:8]}",
                    "nv_id": act.nhan_vien_id or act.ten_nguoi_nhan,
                    "nhan_vien": act.ten_nguoi_nhan,
                    "noi_dung": task_noi_dung,
                    "trang_thai": "dang_cho",
                    "created_at": now_iso,
                    "nguon": "cuoc_hop",
                    "meeting_id": body.id,
                    "loai_cong_viec": getattr(act, "loai_cong_viec", "1_ca"),
                    "ca_thuc_hien": getattr(act, "ca_thuc_hien", ""),
                }
                res.insert(0, treo_item)
                da_co_treo.add((body.id, task_noi_dung))
                open_tasks.add((act_nv, act_core))
                created_tasks += 1
            return res

        kv_mutate("treo", mut_treo, [])

    # 2. Persist approved SOP proposals — key kv riêng, KHÔNG ghi vào bảng
    # sửa ca: đề xuất từ cuộc họp chưa phải là lần sửa đã xảy ra trong ca.
    new_proposals: list[dict[str, Any]] = []
    for prop in body.de_xuat_phe_duyet:
        if prop.trang_thai == "da_duyet" and prop.loai_de_xuat == "quy_trinh_sop":
            new_proposals.append(
                {
                    "loai": "de_xuat_phe_duyet",
                    "id": prop.id,
                    "meeting_id": body.id,
                    "meeting_tieu_de": body.tieu_de,
                    "quy_trinh": prop.quy_trinh_lien_quan or prop.tieu_de,
                    "buoc_so": prop.buoc_so,
                    "noi_dung": prop.noi_dung,
                    "ly_do": prop.ly_do or f"Từ cuộc họp: {body.tieu_de}",
                    "nguoi_de_xuat": prop.nguoi_de_xuat,
                    "nguoi_phe_duyet": prop.nguoi_phe_duyet or str(user),
                    "ghi_luc": now_iso,
                }
            )
    for sop in body.de_xuat_sop:
        new_proposals.append(
            {
                "loai": "de_xuat_sop",
                "id": "",
                "meeting_id": body.id,
                "meeting_tieu_de": body.tieu_de,
                "quy_trinh": sop.quy_trinh_lien_quan,
                "buoc_so": sop.buoc_so,
                "noi_dung": sop.noi_dung_thay_doi,
                "ly_do": sop.ly_do or f"Từ cuộc họp: {body.tieu_de}",
                "nguoi_de_xuat": "",
                "nguoi_phe_duyet": str(user),
                "ghi_luc": now_iso,
            }
        )
    sop_count = 0
    if new_proposals:

        def mut_sop(cur: list[dict[str, Any]]) -> list[dict[str, Any]]:
            nonlocal sop_count
            da_co = {(x.get("meeting_id"), x.get("noi_dung")) for x in cur}
            for p in new_proposals:
                if (p["meeting_id"], p["noi_dung"]) in da_co:
                    continue
                cur.append(p)
                da_co.add((p["meeting_id"], p["noi_dung"]))
                sop_count += 1
            return cur

        kv_mutate("sop_de_xuat", mut_sop, [])

    # 2b. Persist approved schedule adjustments (dieu_chinh_lich) to inbox_rang_buoc & pins
    sched_items: list[dict[str, Any]] = []
    for prop in body.de_xuat_phe_duyet:
        if prop.trang_thai in ("da_duyet", "cho_duyet") and prop.loai_de_xuat == "dieu_chinh_lich":
            if prop.chi_tiet_lich:
                sched_items.append(prop.chi_tiet_lich.model_dump())
            else:
                sched_items.append({
                    "id": prop.id,
                    "nhan_vien_id": None,
                    "ten_nhan_vien": prop.nguoi_de_xuat,
                    "loai": "xin_nghi" if any(k in prop.noi_dung.lower() for k in ["nghỉ", "bận"]) else "ghim_ca",
                    "thu": "",
                    "khung": "",
                    "ca_id": "",
                    "ly_do": prop.noi_dung,
                    "trang_thai": "da_duyet",
                })
    for d in body.dieu_chinh_lich:
        d_dict = d.model_dump()
        if d_dict.get("id") not in [x.get("id") for x in sched_items]:
            sched_items.append(d_dict)

    sched_applied_count = 0
    inbox_leave_count = 0
    pins_count = 0

    if sched_items:
        life = kv_get("lich_tuan_lifecycle", {}) or kv_get("lifecycle", {}) or {}
        current_week = life.get("tuan_iso") or datetime.now(UTC).strftime("%G-W%V")

        # Apply leaves to inbox_rang_buoc
        leaves_to_apply = [s for s in sched_items if s.get("loai") == "xin_nghi"]
        if leaves_to_apply:
            def mut_inbox(cur: list[Any]) -> list[Any]:
                nonlocal inbox_leave_count
                res = list(cur)
                da_co = {
                    (x.get("meeting_id"), x.get("nv_id"), (x.get("rang_buoc") or {}).get("thu"))
                    for x in res
                    if isinstance(x, dict)
                }
                for it in leaves_to_apply:
                    nv_id = str(it.get("nhan_vien_id") or it.get("ten_nhan_vien") or "unknown")
                    thu = str(it.get("thu") or "")
                    tuan = str(it.get("tuan_iso") or current_week)
                    if (body.id, nv_id, thu) in da_co:
                        continue
                    inbox_item = {
                        "id": f"rb_meet_{uuid.uuid4().hex[:8]}",
                        "nv_id": nv_id,
                        "nhan_vien": it.get("ten_nhan_vien") or nv_id,
                        "y_dinh": "xin_nghi",
                        "trang_thai": "duyet",
                        "ly_do": f"Từ cuộc họp [{body.tieu_de}]: {it.get('ly_do') or 'Xin nghỉ phép'}",
                        "hieu_luc": {
                            "loai": "rang_buoc_cho_solver",
                            "nv_id": nv_id,
                            "thu": thu,
                            "tuan_id": tuan,
                        },
                        "rang_buoc": {
                            "thu": thu,
                            "tuan_id": tuan,
                        },
                        "created_at": now_iso,
                        "nguon": "cuoc_hop",
                        "meeting_id": body.id,
                    }
                    res.insert(0, inbox_item)
                    da_co.add((body.id, nv_id, thu))
                    inbox_leave_count += 1
                return res

            kv_mutate("inbox_rang_buoc", mut_inbox, [])

        # Apply pins to KV "pins"
        pins_to_apply = [s for s in sched_items if s.get("loai") == "ghim_ca"]
        if pins_to_apply:
            def mut_pins(cur: dict[str, Any]) -> dict[str, Any]:
                nonlocal pins_count
                res = dict(cur)
                for it in pins_to_apply:
                    nv_id = it.get("nhan_vien_id") or it.get("ten_nhan_vien")
                    ca_id = it.get("ca_id")
                    if not ca_id and it.get("thu"):
                        thu_ord = {"T2": 1, "T3": 2, "T4": 3, "T5": 4, "T6": 5, "T7": 6, "CN": 7}.get(it["thu"], 1)
                        khung_idx = {"sang": 1, "chieu": 2, "toi": 3}.get(it.get("khung", "sang"), 1)
                        ca_id = f"w1_c{(thu_ord - 1) * 3 + khung_idx:02d}"
                    if ca_id and nv_id:
                        res[f"{ca_id}|{nv_id}"] = True
                        pins_count += 1
                return res

            kv_mutate("pins", mut_pins, {})

        sched_applied_count = inbox_leave_count + pins_count

    # 3. Persist meeting to store
    meeting_dict = body.model_dump()
    meeting_dict["trang_thai"] = "da_duyet"
    meeting_dict["duyet_boi"] = str(user)
    meeting_dict["duyet_luc"] = now_iso

    if gop_y_converted:
        current_fbs = list(meeting_dict.get("gop_y_luu_y") or [])
        existing_ids = {f.get("id") for f in current_fbs if isinstance(f, dict)}
        for g in gop_y_converted:
            if g["id"] not in existing_ids:
                current_fbs.append(g)
                existing_ids.add(g["id"])
        meeting_dict["gop_y_luu_y"] = current_fbs

    def mut_meetings(cur: list[dict[str, Any]]) -> list[dict[str, Any]]:
        res = [m for m in cur if m.get("id") != body.id]
        res.insert(0, meeting_dict)
        return res

    kv_mutate("meetings", mut_meetings, [])

    # 4. Audit Trail
    actor = _nv_from_token(authorization) if authorization else str(user)
    audit_add(
        now_iso,
        actor,
        "meeting.approve",
        {
            "entity_type": "meeting",
            "entity_id": body.id,
            "meeting_id": body.id,
            "tieu_de": body.tieu_de,
            "tasks_created": created_tasks,
            "sop_proposals": sop_count,
            "schedule_adjustments": sched_applied_count,
            "inbox_leaves": inbox_leave_count,
            "pins_created": pins_count,
        },
    )

    return {
        "ok": True,
        "meeting_id": body.id,
        "tasks_created": created_tasks,
        "sop_proposals": sop_count,
        "schedule_adjustments": sched_applied_count,
        "inbox_leaves": inbox_leave_count,
        "pins_created": pins_count,
        "applied_at": now_iso,
    }


@router.get("/api/v1/meetings")
def list_meetings(
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """List all recorded and analyzed meetings."""
    _require_role(authorization)
    items = kv_get("meetings", [])
    return {"items": items}


@router.get("/api/v1/meetings/{meeting_id}")
def get_meeting(
    meeting_id: str,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Get single meeting detail by ID."""
    _require_role(authorization)
    items = kv_get("meetings", [])
    for m in items:
        if m.get("id") == meeting_id:
            return cast(dict[str, Any], m)
    raise HTTPException(status_code=404, detail="Meeting not found")


@router.delete("/api/v1/meetings/{meeting_id}")
def delete_meeting(
    meeting_id: str,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Delete a recorded meeting by ID. Manager/owner only."""
    _require_manager(authorization)

    items = kv_get("meetings", [])
    if not any(m.get("id") == meeting_id for m in items):
        raise HTTPException(status_code=404, detail="Meeting not found")

    def mut(cur: list[dict[str, Any]]) -> list[dict[str, Any]]:
        # KHÔNG gọi audit_add bên trong (tránh SQLite lock do ghi chéo trong transaction).
        return [m for m in cur if m.get("id") != meeting_id]

    kv_mutate("meetings", mut, [])

    # Ghi audit SAU khi transaction đã commit (tránh deadlock).
    actor = _nv_from_token(authorization) if authorization else "quan_ly"
    audit_add(_now(), actor, "meeting.delete", {"entity_type": "meeting", "entity_id": meeting_id, "meeting_id": meeting_id})
    return {"ok": True, "meeting_id": meeting_id, "deleted": True}


@router.get("/api/v1/sop/de-xuat")
def list_sop_de_xuat(
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Đề xuất sửa quy trình đã được duyệt từ cuộc họp — nguồn thật, không bịa."""
    _require_role(authorization)
    items = kv_get("sop_de_xuat", [])
    return {"items": list(reversed(items))}


@router.post("/api/v1/meetings/{meeting_id}/rollback")
def rollback_meeting_endpoint(
    meeting_id: str,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Rollback / Recall applied meeting tasks and proposals (TC-42)."""
    user = _require_manager(authorization)
    now_iso = _now()

    meetings = kv_get("meetings", [])
    target = next((m for m in meetings if m.get("id") == meeting_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="Meeting not found")

    recalled_tasks = 0

    def mut_treo(cur: list[Any]) -> list[Any]:
        nonlocal recalled_tasks
        res = []
        for t in cur:
            if isinstance(t, dict) and t.get("meeting_id") == meeting_id:
                if t.get("trang_thai") == "da_xong":
                    t["ghi_chu"] = f"{t.get('ghi_chu', '')} (Biên bản cuộc họp đã rollback)"
                    res.append(t)
                else:
                    recalled_tasks += 1
            else:
                res.append(t)
        return res

    kv_mutate("treo", mut_treo, [])

    recalled_sop = 0

    def mut_sop(cur: list[dict[str, Any]]) -> list[dict[str, Any]]:
        nonlocal recalled_sop
        res = []
        for p in cur:
            if p.get("meeting_id") == meeting_id:
                recalled_sop += 1
            else:
                res.append(p)
        return res

    kv_mutate("sop_de_xuat", mut_sop, [])

    recalled_leaves = 0

    def mut_inbox(cur: list[Any]) -> list[Any]:
        nonlocal recalled_leaves
        res = []
        for x in cur:
            if isinstance(x, dict) and x.get("meeting_id") == meeting_id:
                recalled_leaves += 1
            else:
                res.append(x)
        return res

    kv_mutate("inbox_rang_buoc", mut_inbox, [])

    def mut_meet(cur: list[dict[str, Any]]) -> list[dict[str, Any]]:
        res = []
        for m in cur:
            if m.get("id") == meeting_id:
                m["trang_thai"] = "cho_duyet"
                m["phien_ban"] = int(m.get("phien_ban") or 1) + 1
                m["last_modified_at"] = now_iso
            res.append(m)
        return res

    kv_mutate("meetings", mut_meet, [])

    actor = _nv_from_token(authorization) if authorization else str(user)
    audit_add(
        now_iso,
        actor,
        "meeting.rollback",
        {
            "entity_type": "meeting",
            "entity_id": meeting_id,
            "meeting_id": meeting_id,
            "recalled_tasks": recalled_tasks,
            "recalled_sop": recalled_sop,
            "recalled_leaves": recalled_leaves,
        },
    )

    return {
        "ok": True,
        "meeting_id": meeting_id,
        "recalled_tasks": recalled_tasks,
        "recalled_sop": recalled_sop,
        "recalled_leaves": recalled_leaves,
        "trang_thai": "cho_duyet",
    }


@router.put("/api/v1/meetings/{meeting_id}/draft")
def update_meeting_draft_endpoint(
    meeting_id: str,
    body: CuocHop,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Save meeting draft with optimistic concurrency control (TC-44)."""
    _require_manager(authorization)
    now_iso = _now()
    new_ver = 1

    def mut_meet(cur: list[dict[str, Any]]) -> list[dict[str, Any]]:
        nonlocal new_ver
        current = next((m for m in cur if m.get("id") == meeting_id), None)
        if current:
            cur_ver = int(current.get("phien_ban") or 1)
            req_ver = int(body.phien_ban or 1)
            if req_ver < cur_ver:
                raise HTTPException(
                    status_code=409,
                    detail=f"Xung đột phiên bản: Biên bản đã được sửa đổi lên v{cur_ver} bởi người khác. Vui lòng tải lại trang.",
                )
            new_ver = cur_ver + 1
        else:
            new_ver = int(body.phien_ban or 1)

        save_dict = body.model_dump()
        save_dict["id"] = meeting_id
        save_dict["phien_ban"] = new_ver
        save_dict["last_modified_at"] = now_iso

        res = [m for m in cur if m.get("id") != meeting_id]
        res.insert(0, save_dict)
        return res

    kv_mutate("meetings", mut_meet, [])
    return {"ok": True, "meeting_id": meeting_id, "phien_ban": new_ver, "last_modified_at": now_iso}


# ── Streaming realtime (Google Meet / micro trực tiếp) ────────────────────────
# Không giới hạn thời gian: audio gửi theo tốc độ thực, không dồn token.
# Client gửi: {"event": "auth", "token": "..."} → {"event": "audio", "data": "<base64 pcm16 16khz>"}
# Server trả: {"event": "transcript", "data": {"text": "...", "is_final": bool}}
# Client kết thúc: {"event": "stop"}

MAX_AUDIO_CHUNK_BYTES = 65536  # 64 KB per PCM chunk


def _stream_verified_context(token: str) -> dict[str, str] | None:
    session = auth_session(f"Bearer {token}") or auth_session(token)
    if not session:
        return None
    user_id = str(session.get("nv_id") or "").strip()
    role = str(session.get("role") or "")
    if not user_id or role not in {"chu_quan", "quan_ly", "nhan_vien"}:
        return None
    return {
        "user_id": user_id,
        "role": role,
        "store_id": str(session.get("store_id") or "quan_01"),
    }


@router.websocket("/api/v1/meeting/stream")
async def meeting_stream_websocket(websocket: WebSocket) -> None:
    """Streaming realtime: nhận audio chunk, trả transcript liên tục."""
    await websocket.accept()

    # Auth
    try:
        raw = await websocket.receive_text()
        message = json.loads(raw)
    except Exception:
        await websocket.close(code=4001, reason="auth_invalid")
        return
    if not isinstance(message, dict) or message.get("event") != "auth":
        await websocket.close(code=4001, reason="auth_invalid")
        return
    context = _stream_verified_context(str(message.get("token") or "").strip())
    if context is None:
        await websocket.close(code=4001, reason="auth_invalid")
        return

    # Tạo session streaming
    session = create_meeting_stream_session()
    if session is None:
        await websocket.send_json(
            {"event": "error", "data": {"code": "stream_unavailable", "fallback": "batch"}}
        )
        await websocket.close(code=4003, reason="stream_unavailable")
        return

    try:
        await session.open()
    except Exception as exc:
        await websocket.send_json(
            {"event": "error", "data": {"code": "setup_failed", "detail": str(exc)}}
        )
        await websocket.close(code=4003, reason="setup_failed")
        return

    await websocket.send_json(
        {"event": "ready", "data": {"input_format": "pcm_s16le_16000_mono"}}
    )

    async def _receive_client() -> None:
        """Nhận audio chunk từ client, chuyển tiếp lên Gemini."""
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                return
            audio = message.get("bytes")
            if audio is not None:
                if audio and len(audio) <= MAX_AUDIO_CHUNK_BYTES:
                    await session.send_audio(audio)
                continue
            raw = message.get("text")
            if not raw:
                continue
            try:
                payload = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                continue
            if not isinstance(payload, dict):
                continue
            event = payload.get("event")
            if event == "stop":
                await session.end_audio()
                return

    async def _receive_upstream() -> None:
        """Nhận transcript realtime từ Gemini, gửi về client."""
        while True:
            transcript = await session.receive()
            if transcript is None:
                break
            await websocket.send_json(
                {
                    "event": "transcript",
                    "data": {"text": transcript.text, "is_final": transcript.is_final},
                }
            )

    try:
        client_task = asyncio.create_task(_receive_client())
        upstream_task = asyncio.create_task(_receive_upstream())
        done, _ = await asyncio.wait(
            {client_task, upstream_task}, return_when=asyncio.FIRST_COMPLETED
        )
        for task in done:
            if not task.cancelled():
                task.result()
    except WebSocketDisconnect:
        pass
    finally:
        for task in (client_task, upstream_task):
            task.cancel()
        await asyncio.gather(client_task, upstream_task, return_exceptions=True)
        await session.close()
