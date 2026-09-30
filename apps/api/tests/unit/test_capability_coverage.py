# mypy: disable-error-code="no-untyped-def,no-untyped-call,type-arg,no-any-return,unused-ignore"
"""PR13 coverage gate — mọi route user-facing phải có capability hoặc exclusion.

Kế hoạch §PR13: "CI fail khi thêm chức năng user-facing mà không khai báo
capability hoặc explicit exclusion". Gate này quét các router FastAPI, trích
route path, và đối chiếu với CAPABILITY_REGISTRY + EXCLUDED_ROUTES.
"""

from __future__ import annotations

import re
from pathlib import Path

from ca_contracts import CAPABILITY_REGISTRY

API_SRC = Path(__file__).resolve().parents[2] / "src" / "ca_api" / "interfaces" / "http"

# Route không điều phối qua chat theo thiết kế (kế hoạch §1.2 — R4_MANUAL_ONLY
# hoặc hạ tầng kỹ thuật). Mỗi exclusion phải có lý do.
EXCLUDED_ROUTES: dict[str, str] = {
    # Auth — thao tác bảo mật bắt buộc
    "/api/v1/auth/login": "R4: đăng nhập là thao tác bảo mật",
    "/api/v1/auth/register": "R4: đăng ký là thao tác bảo mật",
    # Webhook / ingestion — hạ tầng kỹ thuật, không phải chức năng user-facing
    "/api/v1/channels/telegram/webhook": "webhook hạ tầng Meta/Telegram",
    "/api/v1/channels/zalo/webhook": "webhook hạ tầng Zalo",
    "/api/v1/channels/facebook/webhook": "webhook hạ tầng Meta",
    "/api/v1/channels/replay": "R4: replay ingestion chỉ chạy từ công cụ vận hành",
    # Copilot tự tham chiếu — chính là lớp điều phối
    "/message": "copilot core",
    "/message/stream": "copilot core",
    "/execute-action": "copilot core",
    "/action/{action_id}/amend": "copilot core",
    "/action/{action_id}": "copilot core",
    "/audit": "copilot core",
    "/permissions": "copilot core",
    "/capabilities": "copilot core",
    "/navigate": "copilot core",
    # Upload tệp nhị phân — trình duyệt xử lý trực tiếp
    "/api/v1/chat/upload": "upload tệp qua trình duyệt",
    "/api/v1/chat/uploads/{filename}": "tệp tĩnh",
    "/upload": "upload tệp đính kèm copilot qua trình duyệt",
    "/uploads/{filename}": "tệp tĩnh đính kèm copilot",
    "/api/v1/menu/{mon_id}/anh": "upload ảnh qua trình duyệt",
    # Health/metrics nội bộ
    "/api/v1/ops/pickers": "chẩn đoán nội bộ",
    "/api/v1/ab": "báo cáo A/B nội bộ",
    "/api/v1/vf/conflict": "chẩn đoán VF nội bộ",
    "/api/v1/vf/conflict-demo": "demo VF nội bộ",
    "/api/v1/ai/retention/dry-run": "chẩn đoán retention nội bộ",
    # Narration phụ trợ cho một trang cụ thể — dùng route tất định đã có
    # capability riêng (predict/explain/twin/cam-nang/...), không phải một hành
    # động điều phối mới của copilot.
    "/api/v1/ai/insight": "narration phụ trợ, không phải hành động điều phối",
    "/api/v1/ai/insight/ask": "narration phụ trợ, không phải hành động điều phối",
    "/api/v1/reservations-metrics": "metrics nội bộ",
    "/catchment-survey": "khảo sát giá thị trường bán kính catchment (pricing radar)",
    "/catchment-survey/{job_id}": "tiến trình job khảo sát giá — poll qua UI /khao-sat-gia",
    "/catchment-survey/{job_id}/result": "kết quả job khảo sát giá — đọc qua UI /khao-sat-gia",
    "/catchment-survey/{job_id}/review": "R2: chủ quán xác nhận giá OCR qua UI /khao-sat-gia (ADR-008)",
    "/catchment-survey-dashboard": "dashboard tổng quan chi phí & kết quả khảo sát — đọc qua UI /khao-sat-gia",
    "/catchment-survey-metrics": "metrics chi phí Vision & độ tin cậy nguồn (nội bộ)",
    "/serpapi/quota": "hạn ngạch SerpApi trong tháng (pricing radar)",
    # ── AI-learning / governance (PR13 scope, deep-link /ai-learning) ──
    "/api/v1/ai/rules/proposals": "AI governance — duyệt qua UI /ai-learning",
    "/api/v1/ai/generations": "AI governance — đọc qua UI /ai-learning",
    "/api/v1/ai/feedback": "AI governance — feedback qua UI /ai-learning",
    "/api/v1/ai/evaluations/summary": "AI governance — đọc qua UI /ai-learning",
    "/api/v1/ai/operations/status": "AI governance — trạng thái qua UI",
    "/api/v1/ai/operations/circuit-breaker": "R3: circuit breaker qua UI dual approval",
    "/api/v1/ai/reflection/gmail/run": "AI governance — reflection qua UI",
    "/api/v1/ai/reflection/facebook/run": "AI governance — reflection qua UI",
    "/api/v1/ai/rules/proposals/{proposal_id}/approve": "R3: dual approval qua UI",
    "/api/v1/ai/rules/proposals/{proposal_id}/activate": "R3: dual approval qua UI",
    "/api/v1/ai/rules/proposals/{proposal_id}/reject": "R3: dual approval qua UI",
    "/api/v1/ai/rules/{proposal_id}/pause": "R3: dual approval qua UI",
    "/api/v1/ai/rules/{proposal_id}/rollback": "R3: dual approval qua UI",
    # ── Chat nội bộ — realtime channel, không phải tác vụ điều phối ──
    "/api/v1/chat/conversations": "chat realtime — kênh giao tiếp",
    "/api/v1/chat/conversations/{conv_id}": "chat realtime — kênh giao tiếp",
    "/api/v1/chat/conversations/{conv_id}/messages": "chat realtime — kênh giao tiếp",
    "/api/v1/chat/conversations/{conv_id}/mute": "chat realtime — kênh giao tiếp",
    "/api/v1/chat/conversations/{conv_id}/read": "chat realtime — kênh giao tiếp",
    "/api/v1/chat/messages/{message_id}": "chat realtime — kênh giao tiếp",
    "/api/v1/chat/messages/{message_id}/pin": "chat realtime — kênh giao tiếp",
    "/api/v1/chat/messages/{message_id}/reactions": "chat realtime — kênh giao tiếp",
    "/api/v1/chat/online": "chat realtime — kênh giao tiếp",
    "/api/v1/chat/search": "chat realtime — kênh giao tiếp",
    # ── Facebook Page chi tiết — deep-link /page-quan đã phủ miền ──
    "/api/v1/page/threads": "FB Page — deep-link /page-quan/fb-inbox",
    "/api/v1/page/threads/{thread_id}/reply": "FB Page — deep-link /page-quan/fb-inbox",
    "/api/v1/page/threads/{thread_id}/approve": "FB Page — deep-link /page-quan/fb-inbox",
    "/api/v1/page/fb-inbox": "FB Page — deep-link /page-quan/fb-inbox",
    "/api/v1/page/fb-inbox/stats": "FB Page — deep-link /page-quan/fb-inbox",
    "/api/v1/page/fb-inbox/{item_id}": "FB Page — deep-link /page-quan/fb-inbox",
    "/api/v1/page/fb-inbox/{item_id}/decide": "R3: moderation qua UI /page-quan/fb-inbox",
    "/api/v1/page/fb-policy": "R3: policy qua UI /page-quan",
    "/api/v1/page/audit/reflection": "AI governance — reflection qua UI",
    "/api/v1/page/audit/reflection/latest": "AI governance — reflection qua UI",
    "/api/v1/page/audit/reflection/apply-proposal": "R3: apply qua UI dual approval",
    "/api/v1/page/drafts": "FB Page — deep-link /page-quan",
    "/api/v1/page/drafts/ai-generate": "FB Page — deep-link /page-quan",
    "/api/v1/page/drafts/{draft_id}": "FB Page — deep-link /page-quan",
    "/api/v1/page/treo": "FB Page — deep-link /page-quan",
    "/api/v1/store/profile": "R3: store profile qua UI /page-quan",
    "/api/v1/store/promotions": "R3: promotions qua UI /page-quan",
    "/api/v1/page/status": "PR12: GET_PAGE_STATUS đã phủ qua chat",
    "/api/v1/page/sync": "PR12: PROPOSE_PAGE_SYNC đã phủ qua chat",
    "/api/v1/page/sync-multi": "multi-page sync qua trang quan ly",
    # ── Việc treo / hao hụt — PR10 intents đã phủ qua chat ──
    "/api/v1/viec-treo": "PR10: GET_HANGING_TASKS đã phủ qua chat",
    "/api/v1/viec-treo/{treo_id}": "PR10: PROPOSE_TASK_COMPLETE đã phủ qua chat",
    "/api/v1/waste": "PR10: PROPOSE_WASTE_RECORD scope — ghi qua UI /hao-phi",
    # ── Hao hụt định lượng (plan 260923-1736) — đọc/ghi qua UI /hao-phi ──
    # Path API là `/hao-hut` còn deep_link capability là `/hao-phi` (route web), nên
    # phép khớp tiền tố của cổng không tự nối được; khai exclusion kèm capability
    # tương ứng thay vì nới cổng.
    "/api/v1/hao-hut": "GET_LOSS_SUMMARY + PROPOSE_LOSS_RECORD — đọc/ghi qua UI /hao-phi",
    "/api/v1/hao-hut/nguong": "GET_LOSS_THRESHOLD — ngưỡng hiển thị qua UI /hao-phi",
    "/api/v1/hao-hut/danh-muc": "chẩn đoán nội bộ — gợi ý mã mặt hàng cho ô nhập hao hụt",
    # ── Cuộc họp — deep-link /cuoc-hop ──
    "/api/v1/meetings": "meeting — deep-link /cuoc-hop",
    "/api/v1/meetings/{meeting_id}": "meeting — deep-link /cuoc-hop",
    "/api/v1/meetings/{meeting_id}/draft": "meeting — deep-link /cuoc-hop",
    "/api/v1/meetings/{meeting_id}/rollback": "meeting — deep-link /cuoc-hop",
    "/api/v1/meeting/clarify-actions": "meeting — deep-link /cuoc-hop",
    "/api/v1/meeting/transcribe": "meeting — deep-link /cuoc-hop",
    "/api/v1/meeting/analyze": "meeting — deep-link /cuoc-hop",
    "/api/v1/meeting/process-audio": "meeting — deep-link /cuoc-hop",
    "/api/v1/meeting/apply": "meeting — deep-link /cuoc-hop",
    "/api/v1/sop/de-xuat": "SOP — deep-link /cam-nang",
    # ── Kênh liên kết — self-service bind ──
    "/api/v1/channels/bind": "R2: self-service bind qua UI /toi",
    "/api/v1/channels/bind/issue": "R2: self-service issue code qua UI /toi",
    "/api/v1/channels/status": "R0: trạng thái kênh qua UI",
    # ── Ca cá nhân / TKB / điểm danh — deep-link /toi, /qr ──
    # `ca/nha` chỉ chạy khi tuần đã công bố (server chặn 409 `lich_chua_cong_bo`
    # nếu chưa) — nhả ca là quyền tự nguyện của chính nhân viên.
    "/api/v1/ca/nha": "R2: nhả ca qua UI /toi (chỉ khi tuần đã công bố)",
    # `ca/nhan` KHÔNG ghi phân công nữa: nhận ca ở tuần đã công bố phải qua đồng
    # thuận hai bên nên đường duy nhất là Chợ đổi ca — server trả 409 kèm chỉ dẫn.
    "/api/v1/ca/nhan": "R2: nhận ca bắt buộc qua UI /doi-ca (consent 2 bên)",
    "/api/v1/ca/nhan-truc-tiep": "R3: quản lý gán ca để lấp ca thiếu người",
    "/api/v1/lich-tuan/thay-doi": "R1: nhật ký đổi ca qua UI /lich-tuan",
    "/api/v1/tkb/xep-lai": "R3: xếp lại lịch sau khi đổi TKB là thao tác quản lý",
    "/api/v1/cho-doi-ca/{swap_id}/duyet": "R3: quản lý duyệt phiếu đổi ca qua UI /doi-ca",
    "/api/v1/toi/lich": "R0: lịch của tôi qua UI /toi",
    "/api/v1/tkb/mine": "R0: TKB của tôi qua UI",
    "/api/v1/tkb/{nv_id}": "R0: TKB theo nhân viên qua UI",
    "/api/v1/tkb/extract": "R1: trích TKB qua UI /inbox",
    "/api/v1/tkb/upload": "R1: upload TKB qua UI /inbox",
    "/api/v1/tkb/confirm": "PR10: PROPOSE_TKB_CONFIRM đã phủ qua chat",
    "/api/v1/diem-danh": "R4: check-in vật lý tại quán",
    "/api/v1/qr": "R4: phát QR là thao tác bảo mật",
    "/api/v1/qr/{token}": "R4: dùng QR là thao tác bảo mật",
    "/api/v1/ghi-nhan-sua": "R0: ghi nhận sửa qua UI /cam-nang",
    "/api/v1/import/nhan-vien": "R4: import nhân sự là thao tác quản trị",
    "/api/v1/orc/dispatch": "chẩn đoán orchestration nội bộ",
    "/api/v1/inbox": "inbox nội bộ qua UI",
    "/api/v1/msg/classify": "AG-MSG nội bộ qua UI /inbox",
    # ── Lịch lifecycle / ICS — deep-link /roster ──
    "/api/v1/lich/lifecycle": "R3: lifecycle lịch qua UI /roster",
    "/api/v1/lich/ics": "R0: xuất ICS qua UI /roster",
    "/api/v1/lich/xlsx": "R0: xuất Excel qua UI /lich-tuan",
    "/api/v1/lich/pdf": "R0: xuất PDF qua UI /lich-tuan",
    "/api/v1/hom-nay": "R0: bảng hôm nay qua UI /hom-nay",
    "/api/v1/thoi-tiet/hom-nay": "AI FORECAST thời tiết hôm nay qua UI /hom-nay + brief Quánverse",
    "/api/v1/audit": "R0: audit qua UI /vet",
    # ── Mail / profile — deep-link /toi ──
    "/api/v1/mail/send": "R2: gửi mail qua UI (Copilot SEND_MAIL đã phủ chat)",
    "/api/v1/me/profile": "R0: hồ sơ qua UI /toi",
    "/api/v1/me/profile/email": "R2: cập nhật email qua UI /toi",
    "/api/v1/users/emails": "R0: danh sách email qua UI /nguoi",
    # ── Quản lý Gmail — deep-link /gmail ──
    "/api/v1/gmail/accounts": "Gmail — deep-link /gmail (tab Tài khoản)",
    "/api/v1/gmail/accounts/{account_id}": "Gmail — deep-link /gmail (tab Tài khoản)",
    "/api/v1/gmail/accounts/{account_id}/messages": "Gmail — deep-link /gmail (tab Hộp thư)",
    "/api/v1/gmail/accounts/{account_id}/messages/{message_id}": "Gmail — deep-link /gmail (tab Hộp thư)",
    "/api/v1/gmail/accounts/{account_id}/messages/{message_id}/read": "Gmail — deep-link /gmail (tab Hộp thư)",
    "/api/v1/gmail/accounts/{account_id}/messages/{message_id}/star": "Gmail — deep-link /gmail (tab Hộp thư)",
    "/api/v1/gmail/accounts/{account_id}/labels": "Gmail — deep-link /gmail (tab Nhãn)",
    "/api/v1/gmail/accounts/{account_id}/labels/{label_id}": "Gmail — deep-link /gmail (tab Nhãn)",
    "/api/v1/gmail/accounts/{account_id}/filters": "Gmail — deep-link /gmail (tab Bộ lọc)",
    "/api/v1/gmail/accounts/{account_id}/filters/{filter_id}": "Gmail — deep-link /gmail (tab Bộ lọc)",
    "/api/v1/gmail/accounts/{account_id}/sync-state": "Gmail — deep-link /gmail (tab Đồng bộ)",
    "/api/v1/gmail/accounts/{account_id}/send": "Gmail — deep-link /gmail (gửi qua Gmail API)",
    "/api/v1/gmail/sync": "Gmail — deep-link /gmail (tab Đồng bộ)",
    "/api/v1/gmail/oauth/authorize": "Gmail OAuth — luồng cấp quyền qua UI /gmail",
    "/api/v1/gmail/oauth/callback": "Gmail OAuth — Google redirect về (GET, hạ tầng)",
    "/api/v1/gmail/oauth/revoke": "Gmail OAuth — thu hồi qua UI /gmail",
    # ── Đổi ca chi tiết — deep-link /doi-ca ──
    "/api/v1/cho-doi-ca": "R2: chợ đổi ca qua UI /doi-ca",
    "/api/v1/cho-doi-ca/{swap_id}/dong-y": "PR10: PROPOSE_SWAP_CONSENT đã phủ qua chat",
    "/api/v1/cho-doi-ca/{swap_id}/tu-choi": "R2: consent qua UI /doi-ca",
    "/api/v1/doi-ca/{swap_id}/xac-nhan": "PR10: PROPOSE_SWAP_CONSENT đã phủ qua chat",
    "/api/v1/doi-ca/{swap_id}/tu-choi": "R2: consent qua UI /doi-ca",
    # ── Đặt bàn — deep-link /page-quan/dat-ban ──
    "/api/v1/reservations": "reservation — deep-link /page-quan/dat-ban",
    "/api/v1/reservations/tables": "reservation — deep-link /page-quan/dat-ban",
    "/api/v1/reservations/{res_id}": "reservation — deep-link /page-quan/dat-ban",
    "/api/v1/reservations/{res_id}/check-in": "R4: check-in vật lý tại quán",
    "/api/v1/reservations/{res_id}/no-show": "R2: no-show qua UI /page-quan/dat-ban",
    "/api/v1/reservations/{res_id}/complete": "R2: complete qua UI /page-quan/dat-ban",
    "/api/v1/reservations/{res_id}/cancel": "R2: cancel qua UI /page-quan/dat-ban",
    "/api/v1/reservations/notifications/me": "R0: thông báo qua UI",
    "/api/v1/reservations/notifications/{thong_bao_id}/ack": "R0: ack qua UI",
    # ── Kỹ năng (skills) — deep-link /cam-nang ──
    # Lưu ý: `_collect_route_paths` đọc path THÔ trong decorator (chưa gồm
    # prefix router), nên key ở đây phải khớp path thô, không phải URL đầy đủ.
    "": "skills — danh mục 13 kỹ năng (deep-link /cam-nang)",
    "/{skill_id}": "skills — deep-link /cam-nang",
    "/{skill_id}/verify": "skills — deep-link /cam-nang",
    "/distill-sop": "skills — deep-link /cam-nang",
    # ── Xu hướng — deep-link qua SEARCH_TRENDS ──
    "/apify-usage": "trend — GET_SCRAPER_USAGE",
    "/radar": "trend — SEARCH_TRENDS",
    "/{trend_id}": "trend — GET_TREND_DETAIL",
    # ── Hệ sinh thái AI agent (Self-Explaining / Predictive / Digital Twin) ──
    "/api/v1/ops/episodes": "ops — deep-link /giai-thich (episodic memory)",
    "/api/v1/ops/explain": "ops — deep-link /giai-thich (causal chain)",
    "/api/v1/ops/explain/chains": "ops — deep-link /giai-thich (danh sách chain)",
    "/api/v1/ops/reflect": "ops — deep-link /giai-thich (suy ngẫm)",
    "/api/v1/ops/predict/run": "ops — deep-link /de-xuat-thong-minh",
    "/api/v1/ops/predict/suggestions": "ops — deep-link /de-xuat-thong-minh",
    "/api/v1/ops/predict/{rule_id}/approve": "R3: dual approval qua UI /de-xuat-thong-minh",
    "/api/v1/ops/twin/scenarios": "ops — deep-link /thu-nghiem-an-toan",
    "/api/v1/ops/twin/simulate": "ops — deep-link /thu-nghiem-an-toan",
    "/api/v1/ops/twin/virtual-staff": "ops — deep-link /thu-nghiem-an-toan (virtual staff)",
    # ── Grand AI Experience Portfolio — deep-link /quanverse (ADR-016) ──
    # Bề mặt trải nghiệm là sản phẩm RIÊNG, không điều phối qua chat: ranh giới
    # sản phẩm ở ADR-016 tách nó khỏi luồng copilot. Vai trò trên bề mặt này do
    # `experience_role_can` kiểm ở máy chủ (xem docs/architecture-grand-ai-experience.md),
    # và mọi mutation vẫn qua proposal + người xác nhận (ADR-008).
    "/api/v1/experience/capabilities": "experience — deep-link /quanverse (capability theo vai trò)",
    "/api/v1/experience/map": "experience — deep-link /quanverse/spatial-memory (bản đồ neo)",
    "/api/v1/experience/events": "experience — deep-link /quanverse/spatial-memory (sự kiện theo neo)",
    "/api/v1/experience/snapshot-hash": "experience — dấu vân tay fixture cho replay tất định",
    "/api/v1/experience/anchors/{anchor_id}": "experience — deep-link /quanverse/spatial-memory (chi tiết neo)",
    "/api/v1/experience/memories": "experience — deep-link /quanverse/spatial-memory (ký ức theo bộ lọc)",
    "/api/v1/experience/memories/propose": "R2: đề xuất ký ức qua UI (đồng thuận bắt buộc ngoài chat)",
    "/api/v1/experience/memories/{memory_id}": "R2: xoá ký ức qua UI (thao tác trên dữ liệu cá nhân)",
    "/api/v1/experience/memories/{memory_id}/consent": "R2: đồng thuận ký ức qua UI (quyết định của chủ dữ liệu)",
    "/api/v1/experience/tour/start": "experience — deep-link /quanverse/spatial-memory (tour mở quán)",
    "/api/v1/experience/voice/turn": "experience — deep-link /quanverse/spatial-memory (hỏi đáp có căn cứ)",
    "/api/v1/experience/quanverse/snapshot": "experience — deep-link /quanverse (bản chiếu theo vai trò)",
    "/api/v1/experience/quanverse/stations": "experience — deep-link /quanverse (tải/hàng chờ theo khu vực, đọc đơn thật)",
    "/api/v1/experience/quanverse/forecast": "experience — deep-link /quanverse (dự báo nhu cầu theo giờ, đọc lịch sử đơn)",
    "/api/v1/experience/quanverse/staff-on-shift": "experience — deep-link /quanverse (nhân sự đang trong ca theo phân công tuần)",
    "/api/v1/experience/quanverse/modes": "experience — deep-link /quanverse (danh sách chế độ)",
    "/api/v1/experience/quanverse/modes/{mode}/propose": "R2: đề xuất chế độ qua UI /quanverse",
    "/api/v1/experience/quanverse/modes/{mode}/confirm": "R3: duyệt chế độ qua UI /quanverse (quản lý/chủ quán)",
    "/api/v1/experience/quanverse/modes/{mode}/deactivate": "R3: tắt chế độ qua UI /quanverse (quản lý/chủ quán)",
    "/api/v1/experience/quanverse/flavor/recommend": "experience — deep-link /quanverse (gợi ý theo khẩu vị khách khai)",
    "/api/v1/experience/quanverse/preferences": "experience — deep-link /quanverse (sở thích của chính người gọi)",
    "/api/v1/experience/quanverse/preferences/propose": "R2: đề xuất sở thích qua UI (đồng thuận bắt buộc ngoài chat)",
    "/api/v1/experience/quanverse/preferences/{pref_id}": "R2: xoá sở thích qua UI (dữ liệu cá nhân)",
    "/api/v1/experience/quanverse/preferences/{pref_id}/consent": "R2: đồng thuận sở thích qua UI (quyết định của khách)",
    "/api/v1/experience/quanverse/tour/{tour_id}": "experience — deep-link /quanverse (tour theo mã)",
    "/api/v1/experience/quanverse/ar-session": "experience — AR-lite qua UI /quanverse (không cấp camera qua chat)",
    # Trợ lý Quánverse: lớp TƯỜNG THUẬT đọc lại dữ liệu của chính các route tất
    # định ở trên (snapshot/modes/war-room/shift-rescue/rules/memories). Nó không
    # tính số và không điều phối hành động nào — ADR-002: LLM chỉ diễn đạt lại
    # brief, số do tầng toán thuần sinh. Vì vậy không phải một capability mới;
    # đây đúng khuôn "narration phụ trợ" như /api/v1/ai/insight.
    "/api/v1/experience/quanverse/brief/{page}": "narration phụ trợ — tóm tắt tất định của dữ liệu đã có capability riêng",
    "/api/v1/experience/quanverse/ask": "narration phụ trợ — LLM chỉ diễn đạt brief, không thêm số/kết luận",
    "/api/v1/experience/war-room/simulate": "R2: mô phỏng qua UI /quanverse/war-room (số do math layer, không qua chat)",
    "/api/v1/experience/war-room/simulate-live": "R2: mô phỏng trên LỊCH TUẦN THẬT qua UI /quanverse/war-room (số tự tính, không preset)",
    "/api/v1/experience/war-room/scenarios/{simulation_id}": "experience — deep-link /quanverse/war-room",
    "/api/v1/experience/war-room/{simulation_id}/propose": "R2: đề xuất phương án qua UI /quanverse/war-room",
    "/api/v1/experience/war-room/{simulation_id}/confirm": "R3: chốt phương án qua UI /quanverse/war-room",
    "/api/v1/experience/shift-rescue/options": "experience — deep-link /quanverse/shift-rescue (ca đang phân người)",
    "/api/v1/experience/shift-rescue/intake": "R2: báo vắng qua UI /quanverse/shift-rescue",
    "/api/v1/experience/shift-rescue/{case_id}": "experience — deep-link /quanverse/shift-rescue",
    "/api/v1/experience/shift-rescue/{case_id}/candidates": "experience — tìm người bù qua UI /quanverse/shift-rescue",
    "/api/v1/experience/shift-rescue/{case_id}/propose": "R2: đề xuất người bù qua UI /quanverse/shift-rescue",
    "/api/v1/experience/shift-rescue/{case_id}/invite": "R3: gửi lời mời qua UI /quanverse/shift-rescue",
    "/api/v1/experience/shift-rescue/{case_id}/respond": "R2: phản hồi lời mời qua UI (người được mời tự quyết)",
    "/api/v1/experience/shift-rescue/{case_id}/confirm": "R3: chốt người bù qua UI /quanverse/shift-rescue",
    "/api/v1/experience/rules/candidates": "experience — deep-link /quanverse/rules (ứng viên luật)",
    "/api/v1/experience/rules/discover": "R2: phát hiện quyết định lặp qua UI /quanverse/rules",
    "/api/v1/experience/rules/{candidate_id}/evidence": "experience — deep-link /quanverse/rules (bằng chứng)",
    "/api/v1/experience/rules/{candidate_id}/shadow-test": "experience — chạy thử cô lập qua UI /quanverse/rules",
    "/api/v1/experience/rules/{candidate_id}/confirm": "R3: ban hành luật qua UI /quanverse/rules (vong_doi sole writer)",
    "/api/v1/experience/rules/{candidate_id}/reject": "R2: từ chối luật qua UI /quanverse/rules",
    "/api/v1/experience/rules/{candidate_id}/revoke": "R3: thu hồi luật qua UI /quanverse/rules",
    # Endpoint CHỈ dùng để cách ly trạng thái test, không phải bề mặt người dùng:
    # `_CANDIDATES` là store trong bộ nhớ sống suốt phiên server nên trạng thái rò
    # giữa các bài e2e. Endpoint tự chặn 403 khi không ở chế độ replay.
    "/api/v1/experience/rules/reset": "test-isolation only — 403 ngoài chế độ replay",
    "/api/v1/experience/quanverse/reset": "test-isolation only — 403 ngoài chế độ replay",
    # ── Bề mặt MOCK của Quánverse (plan quanverse-ops-cockpit) ──
    # Ba route này trả fixture biên soạn tay ĐÚNG hình dạng của snapshot/stations/
    # forecast thật, để `/quanverse` demo được khi quán chưa có đơn thật mà UI
    # không phải bịa số. Chúng KHÔNG phải chức năng điều phối: chỉ đọc, không gọi
    # LLM, không ghi DB, và ẩn khỏi `/openapi.json` (`include_in_schema=False`).
    # Xoá cùng `interfaces/http/quanverse_fixtures.py` khi hết nhu cầu demo.
    "/api/v1/test/quanverse/snapshot": "mock fixture cho UI /quanverse — chỉ đọc, ẩn khỏi OpenAPI",
    "/api/v1/test/quanverse/stations": "mock fixture cho UI /quanverse — chỉ đọc, ẩn khỏi OpenAPI",
    "/api/v1/test/quanverse/forecast": "mock fixture cho UI /quanverse — chỉ đọc, ẩn khỏi OpenAPI",
}

_ROUTE_RE = re.compile(r'@router\.(?:get|post|patch|put|delete)\("([^"]+)"')


def _collect_route_paths() -> list[str]:
    paths: set[str] = set()
    for py in API_SRC.glob("*.py"):
        for match in _ROUTE_RE.finditer(py.read_text(encoding="utf-8")):
            paths.add(match.group(1))
    return sorted(paths)


def _registry_covers(path: str) -> bool:
    """Một route được coi là 'có capability' khi deep_link của capability nào
    đó trùng tiền tố nghiệp vụ của path (vd /menu -> /api/v1/menu)."""
    registry_links = {c.deep_link for c in CAPABILITY_REGISTRY if c.deep_link}
    for link in registry_links:
        segment = link.strip("/")
        if segment and f"/{segment}" in path:
            return True
    return False


def test_every_user_facing_route_has_capability_or_exclusion() -> None:
    """PR13 coverage gate: route nào không có capability và không nằm trong
    danh sách exclusion có lý do sẽ làm test này fail."""
    uncovered: list[str] = []
    for path in _collect_route_paths():
        if path in EXCLUDED_ROUTES:
            continue
        if _registry_covers(path):
            continue
        uncovered.append(path)
    assert not uncovered, (
        "Các route sau chưa có capability hoặc explicit exclusion: "
        + ", ".join(uncovered)
    )


def test_exclusions_all_have_reasons() -> None:
    """Mọi exclusion phải có lý do không rỗng — không được exclude âm thầm."""
    for path, reason in EXCLUDED_ROUTES.items():
        assert reason.strip(), f"Exclusion {path} thiếu lý do"


def test_registry_covers_core_domains() -> None:
    """Các miền nghiệp vụ chính phải có ít nhất một capability deep-link."""
    links = {c.deep_link for c in CAPABILITY_REGISTRY}
    for required in ("/hom-nay", "/roster", "/menu", "/quay", "/treo", "/doi-ca", "/sop", "/page-quan", "/ai-learning"):
        assert required in links, f"Thiếu capability deep-link cho {required}"


def test_privilege_escalation_intents_are_not_executable() -> None:
    """Eval chống privilege escalation: các intent nhạy cảm nhất phải là
    R4_MANUAL_ONLY (agent không thực thi) hoặc R3 (dual approval)."""
    sensitive = {"CHANGE_ROLE", "PAYMENT", "CANCEL_ORDER", "DELETE_MEETING", "CONFIGURE_WEBHOOK", "REPLAY_INGESTION", "BIND_OTHER_CHANNEL"}
    by_intent = {c.intent: c for c in CAPABILITY_REGISTRY}
    for intent in sensitive:
        cap = by_intent.get(intent)
        assert cap is not None, f"Thiếu capability cho {intent}"
        assert cap.risk_tier in ("R4_MANUAL_ONLY", "R3_DUAL_APPROVAL"), (
            f"{intent} phải là R4/R3, đang là {cap.risk_tier}"
        )
