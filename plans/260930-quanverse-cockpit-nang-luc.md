# Quánverse Cockpit — Năng lực trang (trước merge)

## Đây là trang gì?

**Cockpit vận hành AI** tại `/quanverse`: một màn trả lời quán đang thế nào → điểm nào cần xử lý → 15 phút tới → hỏi AI có căn cứ → đề xuất chế độ do người xác nhận.

Không phải app khách, không 3D, không tự ghi lịch/nhân sự/rule.

## Chức năng (làm được)

| # | Chức năng | Tương tác | Nguồn |
|---|-----------|-----------|--------|
| 1 | Toolbar nguồn + vai trò xem | Đổi real/mock, scenario, role | UI |
| 2 | Pulse: header + 6 KPI | Click KPI alerts/queue/upcoming | stations, lich-tuan, staff-on-shift, hom-nay |
| 3 | Bản đồ 2D khu vực | Click zone → ZoneFocus + lọc panel | stations (+ snapshot fallback) |
| 4 | ZoneFocus | Hỏi AI / xem việc / chọn nhanh zone | selection bus |
| 5 | Cần xử lý ngay | CTA lịch/kho/treo + hỏi AI | zones + lich-tuan + hom-nay |
| 6 | Timeline 15' | Đọc horizon, lọc theo zone nếu có | snapshot.next_horizon |
| 7 | Biểu đồ năng lực | Click giờ/peak, dual series | forecast (cần lịch sử đơn) |
| 8 | AI Copilot + Ask | Gõ hỏi, chip gợi ý, citations | brief + POST /ask |
| 9 | Modes | Đề xuất → Xác nhận → Tắt | GET/POST /modes/* (kv thật) |
| 10 | Sự kiện | Click zone trên event | snapshot.events |
| 11 | Bảng năng lực trang | CTA bật mock khi thiếu đơn | tự chẩn đoán provenance |

## Hay ở chỗ nào?

1. **Selection-driven** — một zone điều khiển nhiều panel, không phải dashboard rời.
2. **AI grounded** — citations / unsupported_claims / grounded; không chatbot bịa số.
3. **Human-in-the-loop** — modes chỉ đề xuất; người xác nhận; không auto-write.
4. **Honest null** — chưa có dữ liệu hiện "—", không `?? 0`.
5. **Cùng hợp đồng** — mock và real trả cùng `QuanverseViewModel`; đổi nguồn không đổi UI.

## Tận dụng gì sẵn có?

- API experience: snapshot, stations, forecast, brief, ask, modes, staff-on-shift
- `/lich-tuan`, `/hom-nay` (kho, việc treo, việc tới)
- Design tokens `--nq-*`, motion presets, TechnicalDrawer
- Role projection phía máy chủ

## Mock thôi thì sau dùng dữ liệu thật có chạy không?

**Có.** Không phải giao diện giả tách biệt.

| Nhóm | Real hôm nay (môi trường hiện tại) | Khi quán có dữ liệu |
|------|-------------------------------------|---------------------|
| Ask / Modes / Events / Timeline / Brief | **Chạy API thật** | Giữ nguyên |
| Stations / KPI đơn / Capacity | `co_du_lieu=false` → hiện "—" (đúng) | Tự đầy khi có đơn quầy |
| Staff-on-shift | Endpoint thật (có thể count=0 nếu ca trống) | Đầy theo phân công |
| Mock 3 scenario | Chỉ demo/non-prod | Tắt → về real, cùng UI |

Đã đo: `POST /ask` grounded=true; `GET /modes` 6 chế độ + can_activate; stations/forecast báo `chua_co_du_lieu` khi chưa có đơn.

## Không để khoảng trống UI

- ZoneFocus **luôn** hiện (idle hướng dẫn chọn zone, hoặc chi tiết khi chọn)
- Cột cockpit `align-items: stretch`
- Capacity empty có khối hướng dẫn bước tiếp (không stub thấp)
- CapabilityBoard lấp đáy trang: nói rõ chức năng + trạng thái + CTA mock khi thiếu đơn

## Pitch 90 giây (mock)

1. Bật Mô phỏng → Quầy pha quá tải  
2. Click Quầy pha → ZoneFocus + lọc việc  
3. Hỏi AI “Khu vực nào đang quá tải?” → citations  
4. Modes: Đề xuất Trời mưa → Xác nhận  
5. Click peak capacity → prefill hỏi AI  
