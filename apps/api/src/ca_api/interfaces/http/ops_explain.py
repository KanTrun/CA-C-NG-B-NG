"""HTTP router — Self-Explaining System (Causal Memory).

Nguồn: `plans/260918-y-tuong-dot-pha-nho.md` mục 3.

Endpoints:
- POST /api/v1/ops/explain — trả chuỗi nhân quả cho câu hỏi "tại sao"
- GET  /api/v1/ops/explain/chains — danh sách chuỗi nhân quả đã tạo
"""

from __future__ import annotations

from typing import Annotated, Any

from ca_agents.ag_explain import answer_reflection, build_causal_chain
from fastapi import APIRouter, Header
from pydantic import BaseModel, Field

from ca_api.interfaces.http.sprint3 import _require_manager, _require_role
from ca_api.persist import kv_get, kv_mutate

router = APIRouter(tags=["ops_explain"])


class ExplainBody(BaseModel):
    cau_hoi: str = Field(min_length=1, max_length=500)


class ReflectBody(BaseModel):
    cau_hoi: str = Field(min_length=1, max_length=500)


@router.post("/api/v1/ops/explain")
def explain_endpoint(
    body: ExplainBody,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Trả chuỗi nhân quả cho câu hỏi "tại sao" (tất định, có bằng chứng)."""
    _require_role(authorization)

    # Đọc dữ liệu thật từ KV store (đảm bảo luôn là list — cam_nang có thể là dict)
    cam_nang = kv_get("cam_nang", [])
    luat_list = cam_nang if isinstance(cam_nang, list) else cam_nang.get("items", [])
    if not luat_list:
        luat_list = kv_get("ops_predict_rules", [])
    audit_raw = kv_get("audit", [])
    audit_list = audit_raw if isinstance(audit_raw, list) else []
    ket_qua_raw = kv_get("ops_twin_scenarios", [])
    ket_qua_list = ket_qua_raw if isinstance(ket_qua_raw, list) else []

    chain = build_causal_chain(
        cau_hoi=body.cau_hoi,
        luat_list=luat_list,
        audit_list=audit_list,
        ket_qua_list=ket_qua_list,
    )
    chain_dict = chain.model_dump(mode="json")

    def mut_chains(cur: list[dict[str, Any]]) -> list[dict[str, Any]]:
        res = [c for c in cur if c.get("chain_id") != chain.chain_id]
        res.insert(0, chain_dict)
        return res

    kv_mutate("ops_explain_chains", mut_chains, [])
    return {"ok": True, "chain": chain_dict}


@router.get("/api/v1/ops/explain/chains")
def list_chains(
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Lấy danh sách chuỗi nhân quả đã tạo.

    Lọc trùng theo câu hỏi (đã chuẩn hoá) trước khi trả — an toàn cho các bản
    ghi cũ được tạo trước khi `chain_id` đổi sang băm ổn định (`sha1`); mỗi
    lần gọi `explain` mới vẫn tiếp tục ghi đè đúng theo `chain_id`.

    Bug QA đợt 6 (#39): đổi `_require_role` → `_require_manager` cho khớp
    `MANAGER_ONLY` của giao diện (`session.ts`: `/giai-thich` chỉ quản lý/chủ
    quán). Trước đây nhân viên gọi thẳng API vẫn đọc được toàn bộ chuỗi nhân
    quả kèm bằng chứng nội bộ (doanh thu, hao hụt) dù UI đã ẩn trang.
    """
    _require_manager(authorization)
    chains = kv_get("ops_explain_chains", [])
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for c in chains:
        if not isinstance(c, dict):
            continue
        key = str(c.get("cau_hoi") or "").strip().lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(c)
    return {"items": deduped}


class EpisodeBody(BaseModel):
    loai: str
    thoi_gian: str = ""
    mo_ta: str
    nhan_vien: str = ""
    ca: str = ""
    chi_tiet: dict[str, object] = Field(default_factory=dict)


@router.post("/api/v1/ops/episodes")
def add_episode(
    body: EpisodeBody,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Ghi một episode (tình huống cụ thể) vào episodic memory."""
    _require_role(authorization)

    def mut_episodes(cur: list[dict[str, Any]]) -> list[dict[str, Any]]:
        res = list(cur)
        res.insert(
            0,
            {
                "id": f"ep_{len(res) + 1}",
                "loai": body.loai,
                "thoi_gian": body.thoi_gian,
                "mo_ta": body.mo_ta,
                "nhan_vien": body.nhan_vien,
                "ca": body.ca,
                "chi_tiet": body.chi_tiet,
            },
        )
        return res

    kv_mutate("ops_episodes", mut_episodes, [])
    return {"ok": True}


@router.post("/api/v1/ops/reflect")
def reflect_endpoint(
    body: ReflectBody,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Suy ngẫm nguyên nhân gốc từ episodic memory (tất định, không LLM)."""
    _require_role(authorization)

    # Đọc episodes từ KV store (phàn nàn, doanh thu, sự cố...)
    rows = kv_get("ops_episodes", []) or []
    result = answer_reflection(cau_hoi=body.cau_hoi, rows=rows)
    return {"ok": True, "result": result.model_dump(mode="json")}