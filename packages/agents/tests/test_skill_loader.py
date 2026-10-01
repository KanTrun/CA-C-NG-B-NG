# mypy: disable-error-code="no-untyped-def,no-untyped-call,type-arg,no-any-return,unused-ignore"
from ca_agents.runtime import AgentRuntime, SkillLoader


def test_skill_loader_list_skills() -> None:
    loader = SkillLoader()
    skills = loader.list_skills()
    # Số kỹ năng do `scripts/distill_project_skills.py` sinh ra. Thêm skill mới
    # phải chạy lại script đó để `skills_index.jsonl` có đủ dòng + content_sha256,
    # và sửa con số ở đây.
    assert len(skills) == 14
    skill_ids = [s["skill_id"] for s in skills]
    assert "solver-scheduling" in skill_ids
    assert "smart-swap-recommender" in skill_ids
    assert "vf-gates-audit" in skill_ids
    assert "sop-execution" in skill_ids
    assert "rule-mining-lifecycle" in skill_ids
    assert "barista-waste-audit" in skill_ids
    assert "inventory-restock-check" in skill_ids
    assert "handover-reconciliation" in skill_ids
    assert "daily-brief-generator" in skill_ids
    assert "meeting-memo-extractor" in skill_ids
    assert "customer-memory-voc" in skill_ids
    assert "fbpage-concierge" in skill_ids
    assert "mailwriter-notification" in skill_ids
    assert "genz-texting-agent" in skill_ids


def test_skill_loader_genz_skill_khong_cướp_từ_khoa_rong() -> None:
    """Từ khoá skill nhắn tin phải hẹp và không cướp intent vận hành.

    `match_intent_to_skill` trả khớp ĐẦU TIÊN theo thứ tự bảng, nên skill
    nhắn tin phải đứng CUỐI và không chứa từ khoa chung như "fanpage"/"inbox"
    (đã thuộc `fbpage-concierge`) — nếu không, câu hỏi vận hành sẽ bị gắn nhãn
    nhầm vào skill sai.
    """
    loader = SkillLoader()
    # Câu vận hành phải vẫn về đúng skill chuyên dụng.
    assert loader.match_intent_to_skill("Khách hỏi menu và đặt bàn trên fanpage") == "fbpage-concierge"
    assert loader.match_intent_to_skill("Anh xem lịch xếp ca tuần tới giúp em") == "solver-scheduling"
    # Câu nói về gộp tin nhắn thuộc skill nhắn tin.
    assert loader.match_intent_to_skill("Gộp tin nhắn của khách lại thành 1 câu trả lời") == "genz-texting-agent"
    # Skill nhắn tin đứng cuối bảng.
    assert list(loader.TRIGGER_MAP)[-1] == "genz-texting-agent"


def test_skill_loader_match_intent() -> None:
    loader = SkillLoader()
    assert loader.match_intent_to_skill("Cho anh xem lịch xếp ca tuần tới") == "solver-scheduling"
    assert loader.match_intent_to_skill("Tìm người đổi ca gấp cho Lan") == "smart-swap-recommender"
    assert loader.match_intent_to_skill("Thẩm định kiểm duyệt cổng an toàn fail-closed") == "vf-gates-audit"
    assert loader.match_intent_to_skill("Quy trình mở ca và checklist vệ sinh máy") == "sop-execution"
    assert loader.match_intent_to_skill("Kiểm tra hao hụt nguyên liệu pha chế hôm nay") == "barista-waste-audit"
    assert loader.match_intent_to_skill("Bàn giao ca và đối soát tiền két thu ngân") == "handover-reconciliation"
    assert loader.match_intent_to_skill("Kiểm tra tồn kho xem cần nhập hàng gì không") == "inventory-restock-check"
    assert loader.match_intent_to_skill("Gửi bản tin giao ban ca sáng cho anh em") == "daily-brief-generator"
    assert loader.match_intent_to_skill("Soạn email gửi nhà cung cấp sữa") == "mailwriter-notification"
    assert loader.match_intent_to_skill("Khách quen thích uống ít ngọt") == "customer-memory-voc"
    assert loader.match_intent_to_skill("Khách hỏi menu và đặt bàn trên fanpage") == "fbpage-concierge"
    assert loader.match_intent_to_skill("Biên bản họp ca và việc cần làm") == "meeting-memo-extractor"
    assert loader.match_intent_to_skill("Phát hiện lỗi lặp lại cần đề xuất luật mới") == "rule-mining-lifecycle"
    assert loader.match_intent_to_skill("Một câu hỏi vu vơ không liên quan") is None


def test_skill_loader_load_skill() -> None:
    loader = SkillLoader()
    ref = loader.load_skill("solver-scheduling")
    assert ref.skill_id == "solver-scheduling"
    assert "validate_solver_payload.py" in ref.scripts
    assert "constraints_c01_c06.md" in ref.references

    ctx = loader.get_skill_prompt_context("solver-scheduling")
    assert "KỸ NĂNG VẬN HÀNH: solver-scheduling" in ctx
    # Kiểm tra ngữ cảnh luôn gọn gàng (dưới 1500 tokens ~ 6000 ký tự)
    assert len(ctx) < 4000


def test_agent_runtime_load_skill_for_task() -> None:
    runtime = AgentRuntime()
    ref = runtime.load_skill_for_task("Gợi ý phân công ca sáng T2")
    assert ref is not None
    assert ref.skill_id == "solver-scheduling"

    ref_swap = runtime.load_skill_for_task("Đổi ca cho nhân viên Hùng")
    assert ref_swap is not None
    assert ref_swap.skill_id == "smart-swap-recommender"
