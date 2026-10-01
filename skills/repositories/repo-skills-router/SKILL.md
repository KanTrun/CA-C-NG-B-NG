---
name: repo-skills-router
description: "Bộ điều hướng tăng dần (Progressive Disclosure Router) cho toàn bộ hệ sinh thái NHỊP QUÁN. Ánh xạ nhu cầu người dùng hoặc intent của Agent sang đúng Skill cụ thể, ngăn ngừa tràn context window."
metadata:
  role: router
  system: nhip-quan
---

# NHỊP QUÁN Repository Skills Router (14 Kỹ Năng Hoàn Chỉnh)

Bộ điều hướng này sử dụng mô hình **Progressive Disclosure** theo chuẩn DisCo / AREX-Skill: Agent trước tiên đọc router này để xác định nhánh kỹ năng cần dùng, sau đó **chỉ nạp duy nhất** file `SKILL.md` của nhánh đó vào context.

## 1. Bảng Phân loại & Ánh xạ Kỹ năng (Taxonomy & Routing)

| Nhóm chức năng (Family) | Ý định / Từ khóa kích hoạt (Triggers) | Kỹ năng phụ trách | Đường dẫn tương đối |
|---|---|---|---|
| **Lập lịch & Xếp ca** | Xếp ca, phân công nhân sự, trùng giờ học TKB, nghỉ phép, trần giờ tuần | `solver-scheduling` | `../repo-skills/solver-scheduling/SKILL.md` |
| **Đổi ca thông minh** | Đổi ca, tìm người thế ca, nhân viên vắng mặt, bù ca đột xuất | `smart-swap-recommender` | `../repo-skills/smart-swap-recommender/SKILL.md` |
| **Kiểm duyệt An toàn** | Thẩm định đề xuất, kiểm tra fail-closed, kiểm tra schema, truy xuất nguồn bằng chứng | `vf-gates-audit` | `../repo-skills/vf-gates-audit/SKILL.md` |
| **Quy trình & Cẩm nang** | Mở ca, đóng ca, vệ sinh máy pha, cẩm nang 8 bước, checklist ca làm việc, xử lý sự cố | `sop-execution` | `../repo-skills/sop-execution/SKILL.md` |
| **Tự sinh luật cẩm nang** | Khai phá lỗi lặp lại, đề xuất luật mới, tập sự luật, sửa ca nhiều lần | `rule-mining-lifecycle` | `../repo-skills/rule-mining-lifecycle/SKILL.md` |
| **Pha chế & Hao hụt** | Công thức pha chế, định lượng sữa/cà phê, tính hao hụt, lãng phí nguyên vật liệu | `barista-waste-audit` | `../repo-skills/barista-waste-audit/SKILL.md` |
| **Kho & Nhập hàng** | Tồn kho cạn, cảnh báo nhập hàng, điểm đặt hàng lại ROP, thiếu cà phê hạt/sữa | `inventory-restock-check` | `../repo-skills/inventory-restock-check/SKILL.md` |
| **Bàn giao ca & Quỹ két** | Giao ca, bàn giao việc, đối soát tiền két, thừa thiếu tiền mặt, chốt ca | `handover-reconciliation` | `../repo-skills/handover-reconciliation/SKILL.md` |
| **Bản tin giao ban** | Bản tin đầu ca, giao ban ca sáng/chiều, mục tiêu doanh thu, lưu ý ca | `daily-brief-generator` | `../repo-skills/daily-brief-generator/SKILL.md` |
| **Biên bản họp ca** | Ghi biên bản họp, trích xuất đầu việc, phân công người phụ trách, hạn chót | `meeting-memo-extractor` | `../repo-skills/meeting-memo-extractor/SKILL.md` |
| **Khách quen & VOC** | Đánh giá khách hàng, khen chê, khách quen, dị ứng, sở thích ít ngọt/không đá | `customer-memory-voc` | `../repo-skills/customer-memory-voc/SKILL.md` |
| **Fanpage & Đặt bàn** | Trực fanpage, trả lời menu, giá đồ uống, giờ mở cửa, đặt bàn trước | `fbpage-concierge` | `../repo-skills/fbpage-concierge/SKILL.md` |
| **Nhắn tin tự nhiên (Gen Z)** | Thiết kế chatbot/AI agent nhắn tin giống người, debounce gộp tin dồn dập, chia nhỏ phản hồi thành nhiều bubble, giọng văn/tone Gen Z, teencode, dùng emoji/sticker đúng liều | `genz-texting-agent` | `../repo-skills/genz-texting-agent/SKILL.md` |
| **Soạn thảo Email** | Soạn email gửi nhà cung cấp, đặt hàng qua mail, thông báo nội bộ nhân viên | `mailwriter-notification` | `../repo-skills/mailwriter-notification/SKILL.md` |

## 2. Quy trình Thực thi cho Agent (AG-COPILOT & Workers)

1. **Nhận diện ý định (Intent Recognition):** So khớp yêu cầu với cột *Triggers*.
2. **Nạp Skill nhánh (Branch Loading):** Đọc file `SKILL.md` tương ứng từ bảng trên.
3. **Thực thi script kiểm tra (Execution Gate):** Trước khi đưa ra quyết định hoặc phản hồi, luôn chạy script validator trong thư mục `scripts/` của skill tương ứng.
4. **Báo cáo kết quả (Deterministic Output):** Trả về kết quả kèm mã lý do hoặc bằng chứng minh bạch (tuân thủ nguyên tắc deterministic của NHỊP QUÁN).
