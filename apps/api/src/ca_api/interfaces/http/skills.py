"""HTTP endpoints for Skills Management (Repo-To-Skill & Playbook-To-Skill).

Exposes skills catalog, verification gates, and live distillation API.
"""

from __future__ import annotations

import subprocess
import sys
from typing import Annotated, Any

from ca_agents.runtime import SkillLoader
from ca_playbook.distiller import distill_sop_to_dir
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from ca_api.interfaces.http.sprint3 import _require_manager, _require_role

router = APIRouter(prefix="/api/v1/skills", tags=["skills"])
loader = SkillLoader()


class DistillSopRequest(BaseModel):
    sop_id: str = Field(..., pattern=r"^[a-z0-9][a-z0-9_-]{1,63}$", description="Mã định danh kỹ năng (vd: sop-ve-sinh-may)")
    title: str = Field(..., min_length=1, max_length=200, description="Tiêu đề cẩm nang quy trình")
    markdown_content: str = Field(..., min_length=1, max_length=100_000, description="Nội dung markdown của SOP")


@router.get("", summary="Lấy danh mục các Kỹ năng đã kiểm định")
def list_skills() -> list[dict[str, Any]]:
    """Trả về danh sách kỹ năng cùng trạng thái kiểm định và mã SHA256."""
    return loader.list_skills()


@router.get("/{skill_id}", summary="Xem chi tiết một Kỹ năng")
def get_skill_detail(skill_id: str) -> dict[str, Any]:
    """Trả về nội dung SKILL.md, danh sách scripts và references."""
    try:
        ref = loader.load_skill(skill_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy kỹ năng '{skill_id}'") from None

    return {
        "skill_id": ref.skill_id,
        "name": ref.name,
        "content": ref.content,
        "scripts": ref.scripts,
        "references": ref.references,
        "content_sha256": ref.sha256,
        "prompt_context_sample": loader.get_skill_prompt_context(skill_id),
    }


@router.post("/{skill_id}/verify", summary="Chạy kiểm định trực tiếp một Kỹ năng")
def verify_skill_live(
    skill_id: str,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Chạy smoke test của kỹ năng đó ngay lập tức để xác nhận tính khả dụng."""
    _require_role(authorization)
    try:
        ref = loader.load_skill(skill_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy kỹ năng '{skill_id}'") from None

    scripts_dir = ref.path / "scripts"
    script_results: dict[str, Any] = {}
    all_passed = True

    for script_name in ref.scripts:
        script_path = scripts_dir / script_name
        try:
            proc = subprocess.run(
                [sys.executable, str(script_path)],
                capture_output=True,
                text=True,
                timeout=10,
                encoding="utf-8",
                errors="replace",
            )
            passed = proc.returncode == 0
            script_results[script_name] = {
                "passed": passed,
                "return_code": proc.returncode,
                "output": proc.stdout.strip()[:300] if passed else proc.stderr.strip()[:300],
            }
            if not passed:
                all_passed = False
        except Exception as e:
            script_results[script_name] = {"passed": False, "error": str(e)}
            all_passed = False

    return {
        "skill_id": skill_id,
        "verified": all_passed,
        "status": "VERIFIED" if all_passed else "FAILED",
        "script_results": script_results,
    }


@router.post("/distill-sop", summary="Chưng cất SOP mới thành Kỹ năng (Chế độ Hybrid)")
def distill_new_sop(
    req: DistillSopRequest,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Chuyển đổi văn bản cẩm nang SOP thành một Kỹ năng có thể thực thi."""
    _require_manager(authorization)
    target_dir = (loader.repo_skills_dir / req.sop_id).resolve()
    if not target_dir.is_relative_to(loader.repo_skills_dir.resolve()):
        raise HTTPException(status_code=400, detail="sop_id_khong_hop_le")
    res = distill_sop_to_dir(req.sop_id, req.markdown_content, target_dir)
    return {
        "success": True,
        "message": f"Đã chưng cất thành công cẩm nang '{req.title}' thành Kỹ năng '{req.sop_id}'",
        "details": res,
    }
