"""Agent runtime — versioned prompts + content-hash cache + SkillLoader. No DB writes."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast


@dataclass(frozen=True)
class PromptRef:
    agent: str
    version: str
    path: Path


@dataclass(frozen=True)
class SkillRef:
    skill_id: str
    name: str
    path: Path
    content: str
    scripts: list[str] = field(default_factory=list)
    references: list[str] = field(default_factory=list)
    sha256: str = ""


class ContentCache:
    def __init__(self) -> None:
        self._store: dict[str, Any] = {}

    @staticmethod
    def key(payload: bytes) -> str:
        return hashlib.sha256(payload).hexdigest()

    def get(self, digest: str) -> Any | None:
        return self._store.get(digest)

    def put(self, digest: str, value: Any) -> None:
        self._store[digest] = value


class SkillLoader:
    """Bộ nạp Kỹ năng (SkillLoader) theo cơ chế Progressive Disclosure."""

    TRIGGER_MAP: dict[str, list[str]] = {
        "smart-swap-recommender": ["đổi ca", "doi ca", "thế ca", "the ca", "bù ca", "bu ca", "vắng mặt", "vang mat"],
        "solver-scheduling": ["xếp ca", "xep ca", "lịch", "lich", "tkb", "phân công", "phan cong", "c01", "c02"],
        "vf-gates-audit": ["kiểm duyệt", "kiem duyet", "cổng", "cong", "fail-closed", "vf", "schema", "trace", "conf", "thẩm định", "tham dinh"],
        "sop-execution": ["mở ca", "mo ca", "đóng ca", "dong ca", "vệ sinh", "ve sinh", "cẩm nang", "cam nang", "sop", "checklist", "quy trình", "quy trinh"],
        "rule-mining-lifecycle": ["luật mới", "luat moi", "đề xuất luật", "de xuat luat", "lỗi lặp lại", "loi lap lai", "tập sự luật"],
        "barista-waste-audit": ["hao hụt", "hao hut", "lãng phí", "lang phi", "pha chế", "pha che", "công thức", "cong thuc", "định lượng", "dinh luong"],
        "inventory-restock-check": ["nhập hàng", "nhap hang", "hết hàng", "het hang", "tồn kho", "ton kho", "đặt hàng", "dat hang", "rop"],
        "handover-reconciliation": ["bàn giao", "ban giao", "giao ca", "tiền két", "tien ket", "đối soát", "doi soat", "lệch tiền", "lech tien"],
        "daily-brief-generator": ["bản tin", "ban tin", "giao ban", "mục tiêu ca", "muc tieu ca"],
        "meeting-memo-extractor": ["biên bản", "bien ban", "họp ca", "hop ca", "cuộc họp", "cuoc hop", "việc cần làm", "viec can lam"],
        "customer-memory-voc": ["khách quen", "khach quen", "khen chê", "khen che", "đánh giá khách", "danh gia khach", "ít ngọt", "it ngot"],
        "fbpage-concierge": ["fanpage", "inbox", "menu", "giá", "gia", "đặt bàn", "dat ban", "giờ mở cửa", "gio mo cua"],
        "mailwriter-notification": ["soạn mail", "soan mail", "email", "thư", "thu", "nhà cung cấp", "nha cung cap"],
        # Đặt CUỐI bảng: `match_intent_to_skill` trả về khớp ĐẦU TIÊN, nên thêm
        # ở cuối bảo đảm từ khóa rộng của skill khác (vd "fanpage", "inbox") vẫn
        # thắng. Từ khóa cố tình hẹp và không trùng ngữ cảnh vận hành: skill này
        # viết system prompt cho agent nhắn tin khách hàng, dùng cho FB Messenger
        # — không liên quan câu lệnh nội bộ của copilot.
        "genz-texting-agent": ["gộp tin nhắn", "gop tin nhan", "nhiều tin nhắn", "nhieu tin nhan", "tin nhắn dài", "tin nhan dai", "giọng gen z", "giong gen z", "teencode", "debounce"],
    }



    def __init__(self, skills_root: Path | None = None) -> None:
        if skills_root is not None:
            self.skills_root = skills_root
        else:
            # Tự động dò tìm thư mục skills/ ở root của monorepo
            curr = Path(__file__).resolve()
            root = None
            for p in curr.parents:
                if (p / "skills").exists() and (p / "pyproject.toml").exists():
                    root = p / "skills"
                    break
            self.skills_root = root or (Path(__file__).resolve().parents[4] / "skills")

        self.repo_skills_dir = self.skills_root / "repositories" / "repo-skills"
        self._cache = ContentCache()

    def list_skills(self) -> list[dict[str, Any]]:
        """Đọc danh sách skill từ skills_index.jsonl."""
        index_file = self.skills_root / "skills_index.jsonl"
        if not index_file.exists():
            return []
        skills = []
        for line in index_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                skills.append(json.loads(line))
        return skills

    def match_intent_to_skill(self, query_or_intent: str) -> str | None:
        """Nhận diện intent và trả về skill_id phù hợp qua Progressive Router."""
        q_lower = query_or_intent.lower()
        for skill_id, keywords in self.TRIGGER_MAP.items():
            for kw in keywords:
                if kw in q_lower:
                    return skill_id
        return None

    def load_skill(self, skill_id: str) -> SkillRef:
        """Nạp một Skill cụ thể mà không làm phình context window."""
        if not re.match(r"^[a-z0-9][a-z0-9_-]{1,63}$", skill_id):
            raise FileNotFoundError(f"Mã kỹ năng không hợp lệ: {skill_id}")
        skill_dir = (self.repo_skills_dir / skill_id).resolve()
        if not skill_dir.is_relative_to(self.repo_skills_dir.resolve()):
            raise FileNotFoundError(f"Mã kỹ năng ngoài phạm vi: {skill_id}")
        skill_file = skill_dir / "SKILL.md"
        if not skill_file.exists():
            raise FileNotFoundError(f"Không tìm thấy file skill tại: {skill_file}")

        content = skill_file.read_text(encoding="utf-8")
        scripts_dir = skill_dir / "scripts"
        refs_dir = skill_dir / "references"

        scripts = [p.name for p in scripts_dir.glob("*.py")] if scripts_dir.exists() else []
        refs = [p.name for p in refs_dir.glob("*.md")] if refs_dir.exists() else []
        sha = hashlib.sha256(content.encode("utf-8")).hexdigest()

        return SkillRef(
            skill_id=skill_id,
            name=skill_id,
            path=skill_dir,
            content=content,
            scripts=scripts,
            references=refs,
            sha256=sha,
        )

    def get_skill_prompt_context(self, skill_id: str) -> str:
        """Sinh chuỗi hướng dẫn cô đọng cho Agent (luôn < 1.500 token)."""
        ref = self.load_skill(skill_id)
        # Chỉ trích xuất phần thân sau frontmatter
        body = ref.content
        if body.startswith("---"):
            parts = body.split("---", 2)
            if len(parts) >= 3:
                body = parts[2].strip()

        scripts_info = ", ".join(ref.scripts) if ref.scripts else "không có"
        refs_info = ", ".join(ref.references) if ref.references else "không có"

        return (
            f"=== KỸ NĂNG VẬN HÀNH: {ref.name} ===\n"
            f"{body}\n\n"
            f"[Scripts thực thi sẵn có: {scripts_info}]\n"
            f"[Tài liệu tham chiếu: {refs_info}]\n"
            f"======================================"
        )


class AgentRuntime:
    """Sprint 1 frame: load prompt file, cache by content, replay-safe + skill integration."""

    def __init__(self, prompts_root: Path | None = None, skills_root: Path | None = None) -> None:
        root = prompts_root or Path(__file__).resolve().parent / "prompts"
        self.prompts_root = root
        self.cache = ContentCache()
        self.skill_loader = SkillLoader(skills_root)

    def load_prompt(self, agent: str, version: str) -> PromptRef:
        path = self.prompts_root / agent / f"{version}.md"
        if not path.exists():
            raise FileNotFoundError(path)
        return PromptRef(agent=agent, version=version, path=path)

    def load_skill_for_task(self, task_description: str) -> SkillRef | None:
        """Tự động phát hiện và nạp skill liên quan cho tác vụ."""
        matched_id = self.skill_loader.match_intent_to_skill(task_description)
        if matched_id:
            return self.skill_loader.load_skill(matched_id)
        return None

    def run_replay(self, agent: str, version: str, inp: dict[str, Any]) -> dict[str, Any]:
        ref = self.load_prompt(agent, version)
        blob = json.dumps({"agent": agent, "v": version, "in": inp}, sort_keys=True).encode()
        digest = self.cache.key(blob)
        hit = self.cache.get(digest)
        if hit is not None:
            return cast(dict[str, Any], hit)
        text = ref.path.read_text(encoding="utf-8")
        out = {
            "agent": agent,
            "prompt_version": version,
            "mode": "replay",
            "prompt_chars": len(text),
            "result": None,
            "note": "Sprint 1 runtime frame — no live LLM",
        }
        self.cache.put(digest, out)
        return out
