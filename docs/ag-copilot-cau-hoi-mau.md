# Câu hỏi mẫu cho AG-COPILOT

Mỗi chức năng **một câu mẫu**, đã đo bằng `parse_intent()` và chạy đúng với cả
3 vai trò (`nhan_vien`, `quan_ly`, `chu_quan`), ở cả dạng có dấu và không dấu.

Nguồn: `_INTENT_KEYWORDS` trong
`packages/agents/src/ca_agents/ag_copilot/intent_parser.py`.
Cổng chặn tự động: `packages/agents/tests/test_copilot_intent_coverage.py`.

Ghi chú:
- Intent ghi (`PROPOSE_*`) chỉ tạo **đề xuất chờ duyệt**, không tự thực thi.
- Vài chức năng giới hạn quyền (xếp lịch, duyệt đổi ca, kiểm kê) — nhân viên
  gọi sẽ bị chặn `role_blocked` và ghi audit, không phải lỗi.
- Người dùng gõ viết tắt (`hnay`, `t`, `k`, `t2`, `t7`) vẫn ra đúng chức năng.

## Tra cứu ca và lịch

| Chức năng | Câu mẫu |
|---|---|
| `GET_MY_SHIFTS` — ca của chính mình | lịch hôm nay của tôi |
| `GET_SCHEDULE` — lịch toàn quán | xem lịch tuần này |
| `SCHEDULE_SOLVE` — xếp lịch | xếp lịch tuần sau |
| `GET_OPEN_SHIFTS` — chợ ca | chợ ca có gì |
| `GET_HANDOVERS` — xem bàn giao | bàn giao ca gần nhất |
| `PROPOSE_HANDOVER` — ghi bàn giao | ghi bàn giao ca |
| `GET_SHIFT_SWAPS` — yêu cầu đổi ca | có yêu cầu đổi ca nào không |
| `APPROVE_SHIFT_SWAP` — duyệt đổi ca | duyệt đổi ca |
| `PROPOSE_SWAP_CONSENT` — đồng ý nhận ca | đồng ý đổi ca |
| `GET_CONSTRAINT_CANDIDATES` — ràng buộc chờ duyệt | ràng buộc chờ duyệt có gì |
| `PROPOSE_TIME_OFF` — xin nghỉ | tôi xin nghỉ ngày mai |
| `GET_FAIRNESS_SUMMARY` — công bằng ca | báo cáo công bằng |

## Vận hành hằng ngày

| Chức năng | Câu mẫu |
|---|---|
| `GET_TODAY_OPERATIONS` — tình hình hôm nay | tình hình hôm nay |
| `GENERATE_DAILY_BRIEF` — bản tin | bản tin hôm nay |
| `GET_WEATHER` — thời tiết | thời tiết hôm nay |
| `GET_RESERVATIONS` — đặt bàn | đặt bàn hôm nay |
| `GET_PREDICTIVE_INSIGHTS` — gợi ý tối ưu | gợi ý vận hành |
| `GET_MY_CHECKLIST` — phiếu việc của tôi | checklist của tôi |

## Kho và nguyên liệu

| Chức năng | Câu mẫu |
|---|---|
| `GET_INVENTORY` — xem tồn kho | xem tồn kho |
| `INVENTORY_RESTOCK_CHECK` — cần nhập thêm | cần nhập thêm gì |
| `ANALYZE_WASTE` — hao hụt | hao hụt hôm nay |
| `PROPOSE_CONSUMPTION_RECORD` — ghi tiêu thụ | ghi tiêu thụ |

## Menu và đơn

| Chức năng | Câu mẫu |
|---|---|
| `QUERY_MENU` — xem menu | menu có gì |
| `PROPOSE_MENU_UPDATE` — sửa giá món | sửa giá món |
| `PROPOSE_ORDER_TRANSITION` — chuyển đơn | chuyển đơn sang pha |

## Quy trình và tri thức

| Chức năng | Câu mẫu |
|---|---|
| `QUERY_SOP` — quy trình, cẩm nang | quy trình pha chế |
| `CREATE_RULE_PROPOSAL` — đề xuất luật | đề xuất luật mới |
| `SEARCH_TRENDS` — xu hướng | xu hướng f&b |
| `QUERY_QUANVERSE` — Quanverse | quanverse |
| `QUERY_AUDIT` — nhật ký hệ thống | nhật ký hệ thống |

## Nhân sự

| Chức năng | Câu mẫu |
|---|---|
| `LIST_STAFF` — danh sách nhân sự | danh sách nhân sự |
| `GET_MY_PROFILE` — hồ sơ của tôi | hồ sơ của tôi |

## Việc treo

| Chức năng | Câu mẫu |
|---|---|
| `GET_HANGING_TASKS` — xem việc treo | việc treo |
| `PROPOSE_HANGING_TASK` — ghi việc treo | treo việc này |
| `PROPOSE_TASK_COMPLETE` — đánh dấu xong | đánh dấu xong việc treo |

## Khảo sát giá đối thủ

| Chức năng | Câu mẫu |
|---|---|
| `RUN_CATCHMENT_SURVEY` — quét giá | khảo sát giá quanh đây |
| `GET_SURVEY_RESULT` — kết quả khảo sát | kết quả khảo sát giá |
| `GET_SERPAPI_QUOTA` — hạn ngạch SerpAPI | hạn ngạch serpapi |

## Fanpage và liên lạc

| Chức năng | Câu mẫu |
|---|---|
| `PROPOSE_PAGE_DRAFT` — soạn bài đăng | đăng bài lên fb |
| `PROPOSE_PAGE_SYNC` — đồng bộ page | đồng bộ page |
| `GET_PAGE_STATUS` — trạng thái page | trạng thái page |
| `SEND_MAIL` — gửi thư | gửi mail cho nhân viên |

## Cuộc họp và TKB

| Chức năng | Câu mẫu |
|---|---|
| `GET_MEETINGS` — biên bản họp | biên bản họp |
| `PROPOSE_TKB_CONFIRM` — xác nhận lịch bận | xác nhận tkb |
| `PROPOSE_PIN` — ghim ca | ghim ca này |

## Ngoài phạm vi

`OUT_OF_SCOPE` — phải từ chối lịch sự, **không** gọi tool:

| Câu mẫu |
|---|
| chào bạn |
| cảm ơn nhé |
| bạn là ai |

### Ranh giới fail-closed — cố ý KHÔNG nhận

Hệ thống thà từ chối còn hơn đoán sai:

| Câu | Lý do |
|---|---|
| lịch năm nay của tôi | không hỗ trợ khoảng thời gian ngoài tuần/tháng |
| lịch ngày 5 của tôi | không parse ngày tuyệt đối |
| lịch today của tôi | hệ thống tiếng Việt |
| đổi ca hôm nay của tôi | chưa có intent ghi; trả về tra cứu sẽ khiến người dùng tưởng đã đổi được |
| hủy ca hôm nay của tôi | chưa có intent hủy ca |
| hôm nay tôi không có ca | câu phủ định, không phải câu hỏi tra cứu |

## Cách chạy lại kiểm tra

```powershell
# Toàn bộ cổng chặn intent (gồm bộ câu hỏi mẫu, viết tắt, phủ định, mutating)
python -m pytest packages/agents/tests/test_copilot_intent_coverage.py -q

# Thử nhanh một câu
python -X utf8 -c "import sys; sys.path.insert(0,'packages/agents/src'); from ca_agents.ag_copilot.intent_parser import parse_intent; print(parse_intent('lịch hôm nay của tôi', {'user_role':'quan_ly'}).intent)"
```
