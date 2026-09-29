# DEMO BROWSER PLAN — Kế hoạch demo/QA từng chức năng NHỊP QUÁN (thực thi trực tiếp trên trình duyệt)

> ## ⚠️ ĐÃ LỖI THỜI — DÙNG [`docs/KE-HOACH-TEST-TOAN-BO-CHUC-NANG.md`](./docs/KE-HOACH-TEST-TOAN-BO-CHUC-NANG.md) THAY THẾ
>
> Tài liệu này lập ngày **2026-09-25**; từ đó route và nhãn UI đã đổi:
> - Route chính nay là **`/lich-tuan`** (tài liệu cũ nhắc `/roster`), `/giai-thich` (cũ: `/vet`),
>   và sidebar hiện có **42 route chia 5 nhóm** khác cấu trúc cũ.
> - Bảng nhãn nút ở §F dưới **không còn khớp** UI hiện tại (nhiều nút đã đổi tên/gộp lại).
> - Kế hoạch mới có **50 mục test** đã kiểm chứng độ phủ 42/42 route, RBAC đọc trực tiếp từ
>   `session.ts`, và bảng payload đã xác minh để tránh lỗi 422.
>
> **Giữ lại tài liệu này chỉ để tra cứu lịch sử QA** (nhật ký bug #1–#12, các đợt QA 1–4).
> Nếu bạn là AI Agent cần chạy test → mở file kế hoạch mới.

> **Ngày:** 2026-09-25 · **Môi trường:** https://nhipquan.duckdns.org (production — trang đang mở `/vet`, phiên đăng nhập `hung` — Chủ quán)
> **Mục đích:** Kế hoạch cho AI Agent chạy demo/QA **từng chức năng** trên trình duyệt thật, bấm đúng nút như UI hiển thị.
> **Nguồn nhãn nút:** trích trực tiếp từ mã `apps/web/src` (dẫn chứng file:dòng) — **không phịa nhãn**.
>
> **QUY TẮC AN TOÀN BẮT BUỘC KHI CHẠY TRÊN PRODUCTION:**
> 1. KHÔNG bấm các nút gửi nội dung ra BÊN NGOÀI hệ thống: "Đăng bài"/"Đăng phản hồi" Facebook, "Gửi email" (SEND_MAIL execute), "gửi khách". Dừng ở bước duyệt cuối (trạng thái chờ từng thấy là đủ).
> 2. Trước luồng FB (S14–S15): bấm toggle "Tắt tự trả lời" nếu đang bật (fb-inbox :282).
> 3. Mọi bước: chụp screenshot làm bằng chứng; kết quả ghi vào `DEMO_QA_RESULTS.md`.
> 4. Chỉ đăng xuất/đổi tài khoản bằng quick-login tại `/` — không sửa dữ liệu bằng tay qua SQL/DevTools.

**Tài khoản (mật khẩu chung: `nhipquan`):** `lan` (quan_ly) · `hung` (chu_quan) · `minh`, `chi`, `quan`… (nhan_vien).

---

## A. Chạy nhanh (cheat-sheet cho AI Agent)

| Việc | Cách |
|------|------|
| Mở trang | `navigate_page` tới URL |
| Đọc UI | `read_page` → tìm ref theo nhãn nút trong plan này |
| Bấm | `click_element` với ref + element description |
| Gõ | `type_in_page` vào selector theo placeholder |
| Bằng chứng | `screenshot_page` sau mỗi bướcquant trọng |
| Copilot | `Ctrl+K` mở drawer (= `type_in_page` key "Control+k"), gõ lệnh, duyệt bằng gõ "duyệt" hoặc nút trên thẻ |

---

## B. Kịch bản từng chức năng (S1 → S19)

### S1 — Đăng nhập & phân quyền 4 vai (P0)
**Trang:** `/` →.quick-login, `/login`
1. `navigate` → `https://nhipquan.duckdns.org/`
2. **PASS IF** thấy các nút 1-click "Lan Nguyễn", "Hùng Trần", "Minh Phạm"… (page.tsx:42)
3. Thử sai: `/login` → nhập `lan` / `saimatkhau` → **PASS IF** hiện "Tài khoản hoặc mật khẩu chưa đúng…" (login/page.tsx:31)
4. Đăng nhập đúng `lan` → chuyển `/hom-nay`
5. **RBAC âm tính:** đăng nhập `minh` → mở `/vet` → **PASS IF** xem được (🔵 mọi vai) nhưng vào `/inbox` thấy Notice "Quản lý hoặc chủ quán mới bấm duyệt" (inbox:442)

### S2 — NV xin nghỉ qua tin nhắn (AG-MSG) (P0)
**Trang:** `/chat` hoặc copilot drawer với `minh`
1. Quick-login `minh` → drawer (Ctrl+K) → gõ: `Mai em xin nghỉ ca sáng, em có việc gia đình`
2. **PASS IF** phản hồi có intent xin_nghi / thẻ đề xuất (PROPOSE_TIME_OFF) — **KHÔNG** tự ghi
3. **Optional an toàn:** bấm "Từ chối" trên proposal (không duyệt) — hộp thư không đổi
4. **Bằng chứng:** screenshot thẻ proposal + dòng chat

### S3 — Hộp thư ràng buộc + duyệt (P0)
**Trang:** `/inbox` (phải `lan`)
1. Quick-login `lan` → `/inbox`
2. **PASS IF** có mục `cho_duyet` label "Chờ bạn quyết" (inbox:106)
3. Bấm hàng → khung chi tiết "Duyệt ràng buộc — xem chi tiết trước khi chốt" (:662) → bấm **"Duyệt ràng buộc"** (:725)
4. **PASS IF** toast "Đã duyệt…" (:343–346); nếu là đổi ca → hiện gợi ý "Duyệt AI (…)" (:626)
5. **Edge:** bấm **"Từ chối"** (:639) → nhập lý do → **"Xác nhận từ chối"** (:790) → dòng chuyển "Đã từ chối" (:109)

### S4 — Copilot SCHEDULE_SOLVE + 2 pha (P0)
**Trang:** `/copilot` hoặc drawer (với `lan`)
1. Gõ: `Xếp lịch tuần 2026-W39` (hoặc tuần hiện hành hiển thị trên /roster)
2. **PASS IF** SSE meta hiện intent + confidence; thẻ proposal "CHỜ DUYỆT" (ActionProposalCard:227) có diff + snapshot hash
3. Duyệt bằng gõ `duyệt` (useCopilotChat APPROVAL_KEYWORDS) → **PASS IF** thẻ "✓ ĐÃ DUYỆT" (:214)
4. **Idempotent test:** bấm nút Duyệt lần 2 → hệ thống không nhân bản (receipts chặn) — PASS IF không có vết "executed" lặp trong /vet
5. **Amend:** đề xuất khác → bấm "✏️ Sửa trước khi duyệt" (:270) → sửa → gửi đính chính → "CHỜ DUYỆT ĐÍNH CHÍNH" (:226)

### S5 — Roster: lifecycle lịch tuần (P0)
**Trang:** `/roster` (với `lan`/`hung`)
1. **PASS IF** lưới hiển thị + header trạng thái (Nháp/Chờ duyệt/Đã công bố)
2. Theo trạng thái hiện tại bấm đúng nút (roster:115–121): `nhap` → **"Xếp lịch tự động"**; `cho_duyet` → **"Duyệt và công bố"**; `da_duyet/da_cong_bo` → **"Mở lại để điều chỉnh"** (modal hỏi lý do :1498 — nhập lý do, bấm xác nhận)
3. **PASS IF:** solver chạy xong (dang_giai → cho_duyet), lưới có phân công; công bố thành công → toast "Đã duyệt, công bố lịch và gửi thông báo cho nhân viên." (:484)
4. Bấm ô ca → panel "Đủ 2/2" → nút **"Ghim"**/:**"Bỏ ghim"** (:1373) — **PASS IF** toast "Đã ghim và xếp lại phần lịch còn lại." (:367)
5. **Conflict message test:** bấm lifecycle khi chưa đủ điều kiện → đọc conflict text (:125–127) — PASS IF hiển thị đúng thông điệp vi-Việt

### S6 — QR điểm danh (P0)
**Trang:** `/qr`
1. `lan`: chọn nhân viên + ca → **"Phát mã điểm danh"** (:111) → **PASS IF** "Đã phát mã một lần…" + mã che
2. Copy mã → `minh`: dán vào ô "Dán mã quản lý gửi…" → **"Điểm danh vào ca"** (:133) → **PASS IF** "Đã điểm danh xong. Mã vừa dùng không dùng lại được nữa." (:75)
3. **Replay-protection:** dán lại mã cũ → **PASS IF** lỗi "Mã này đã dùng rồi…" (:81–82)

### S7 — Phiếu checklist trong ca (P0)
**Trang:** `/phieu` (với đã điểm danh)
1. Nếu chưa có mặt: bấm **"Tôi đã có mặt"** (:367)
2. Chọn phiếu "Mở quán" → **PASS IF** danh sách bước hiện, mỗi lần 1 bước
3. Hoàn thành 1–2 bước (nhập giá trị مثل 4.5) → bấm bước tiếp
4. Bước cần ảnh: **"Chụp ảnh minh chứng"** (:494) → preview "Xem trước ảnh minh chứng" (:475) → gửi
5. Bấm **"Để lại việc khó"** (:563) → nhập "Hết ống hút cỡ lớn" → **PASS IF** xác nhận + hint nối sang /treo
6. **Anti-fake (nói + thử nhẹ):** hoàn thành bước < ngưỡng thời gian → bị chặn (ADR-008) — không cần cố ý fail

### S8 — Việc treo + "Đánh dấu xong" (P1)
**Trang:** `/treo` (với `lan`)
1. **PASS IF** tab "Việc cần xử lý (n)" (:176) có ≥1 việc
2. Bấm **"Đánh dấu xong"** (:234) → **PASS IF** msg "Đã đánh dấu việc treo là xong." (:141) + việc chuyển nhóm "Xong"
3. **RBAC âm tính:** `minh` bấm → **PASS IF** lỗi "Chỉ quản lý mới đánh dấu xong việc treo." (:144)

### S9 — Họp giao ca AG-MEETING (P0)
**Trang:** `/cuoc-hop` (với `lan`)
1. Field "Nội dung ghi chép cuộc họp" (:1118) → dán transcript mẫu (máy rỉ nước, khách quên áo, sữa sắp hết, đoàn 25 người)
2. Bấm **"Phân tích biên bản"** (:1127) → **"Đang phân tích Action Items & Đề xuất Cẩm nang quán..."** (:598)
3. **PASS IF** biên bản: tiêu đề + tóm tắt + action items + đề xuất SOP
4. Bấm **"Duyệt & phân công vào ca"** (MeetingResults:938) → **"Đã áp dụng…"** → xem link **"Sang Lịch tuần xếp ca (Solver)"** (:926)
5. **PASS IF** action items xuất hiện ở /treo

### S10 — Bàn giao ca + mâu thuẫn (P1)
**Trang:** `/handover`
1. Dán 2 claim tiền khác nhau (ca A: két 2.350.000đ / ca B: 2.300.000đ)
2. Bấm **"Tách thành bàn giao"** (:94) → **PASS IF** "Bốn phần đã tách" + phát hiện lệch số (VF-NUM)

### S11 — Cẩm nang 8 bước + SOP trích dẫn (P1)
**Trang:** `/cam-nang` (`lan`/`hung`), `/sop` (bất kỳ ai)
1. `/cam-nang` → **PASS IF** thẻ "Pipeline 8 bước" + chỉ số (Lần sửa thật/Mẫu sẵn sàng/Đang hiệu lực/Chờ chốt :191–194)
2. Bấm **"Chạy 8 bước xét luật"** (:213) → **PASS IF** hoặc đề xuất luật, hoặc thông báo "Chưa đủ lần sửa có bằng chứng…" (:135) — cả hai đều đúng nghiệp vụ
3. Nếu có luật chờ chốt → bấm chốt (msg :148 "Chủ quán đã chốt luật có hiệu lực…")
4. `/sop` gõ `Nhiệt độ tủ lạnh bao nhiêu là được?` → **PASS IF** trả lời kèm trích dẫn; thử câu lạ → **PASS IF** cờ "chưa có trong cẩm nang" (không bịa)

### S12 — Tự giải thích AG-EXPLAIN (P1)
**Trang:** `/giai-thich`
1. Câu hỏi mặc định "Tại sao ca tối T6 có 2 pha chế?" (:35) → bấm nút chạy (:96)
2. **PASS IF** chuỗi nhân quả có căn cứ trả về (không bịa)

### S13 — Công bằng + Đề xuất thông minh (P1/P2)
1. `/cong-bang` → **PASS IF** biểu đồ số dư 4 trục (Empty nếu chưa công bố :100)
2. `/de-xuat-thong-minh` → xem gợi ý luật tích cực (AG-PREDICT) + mô phỏng (AG-TWIN)

### S14 — Duyệt phản hồi Fanpage (⚠️ AN TOÀN) (P1)
**Trang:** `/page-quan/fb-inbox` (`lan`/`hung`)
1. Trước hết: nếu policy "auto_send_enabled" → bấm **"Tắt tự trả lời"** (:282) — PASS IF "Đã tắt tự gửi."
2. Xem hàng đợi → chọn 1 item trung tính → AI draft hiển thị
3. **CHỈ BẤM** "sửa_gui" hoặc mở chi tiết — **KHÔNG bấm nút cuối "Đăng"/"duyet" (:498)** trên production trừ khi chủ quán cho phép. **ĐỀ XUẤT AN TOÀN:** dừng ở preview, screenshot, ghi chú "nút Đăng phản hồi được xác nhận tồn tại".

### S15 — Soạn bài Page bằng AI (⚠️ AN TOÀN) (P2)
**Trang:** `/page-quan` → mục "AI Tự Động Soạn Thảo Bài Đăng" (:2035)
1. Nhập chủ đề → bấm **"AI Soạn & Thêm Nháp"** (:2091) → **PASS IF** "AI đã soạn xong bài viết và lưu vào danh sách nháp!" (:516)
2. **KHÔNG bấm "Đăng bài"** — dừng ở nháp.

### S16 — Khảo sát giá AG-PRICING (P2)
**Trang:** `/khao-sat-gia`
1. Bước 1: bấm lấy vị trí → Bước 2 chọn preset bán kính (:736) → chọn kênh (:815)
2. Submit (busy "Đang tạo khảo sát…" :872) → poll job → **PASS IF** trạng thái job + kết quả
3. Giá NEEDS_REVIEW → bấm **"Gửi xác nhận"** (:653) → **PASS IF** cập nhật
4. Quota: kiểm tra "Kiểm tra số dư" nếu có (metrics)

### S17 — POS quầy + menu (P2)
**Trang:** `/quay`, `/menu`
1. `/quay` chọn món theo menu → tạo đơn → chuyển `cho_pha → dang_pha → xong` (nút chuyển trạng thái tại /quay + /pha)
2. `/menu` xem + (nếu có quyền) sửa giá → save → **PASS IF** toast; kiểm ảnh món

### S18 — Vết hệ thống /vet (P0 — màn đang mở)
**Trang:** `/vet`
1. **PASS IF** "200 vết" + filter "Người thực hiện" (combobox :276) + "Thời gian" (:279)
2. Chọn combobox "Chủ quán" → **PASS IF** danh sách lọc đúng
3. Search từ khóa (vd "Đăng nhập") → PASS IF lọc được
4. Mở rộng 1 vết → đọc 3 câu: actor (nv_01/nv_02), loại "Thao tác hệ thống", "Loại đối tượng"…

### S19 — Skills + AI Learning (P2)
1. `/skills` → **PASS IF** danh sách 14 kỹ năng + bấm verify 1 skill (smoke offline) → "…trạng thái verification"
2. `/ai-learning` → xem "Tổng hợp đánh giá", "Trạng thái vận hành AI", rule proposals; bấm feedback nếu form có sẵn

---

## C. Tình trạng đã phát hiện trên production (2026-09-25 17:0x)

| Hiện tượng | Bằng chứng | Mức độ | Trạng thái |
|------------|------------|--------|-----------|
| WS 502 trên 3 WebSocket (`/ws/chat`, `/api/v1/copilot/voice`, `/api/v1/meeting/stream`) — Caddyfile chỉ khai mỗi `/ws/chat*` | console error lặp | 🟡 | ✅ **ĐÃ SỬA** — `infra/oracle/Caddyfile` thêm `handle` + `flush_interval -1` cho cả 3 (cần reload Caddy trên VM) |
| 1 resource 404 | console error | 🟢 | ⏳ cần xác định URL cụ thể (không chặn demo) |
| `/skills` và `/gmail` chặn MỌI vai (kể cả chủ quán) | test bằng `lan` + `hung` đều BLOCKED | 🔴 P1 | ✅ **ĐÃ SỬA** — `session.ts` thêm `/skills` → STAFF_ACCESS, `/gmail` → MANAGER_ONLY |
| `/giai-thich` chuỗi bằng chứng lặp ~13 lần · `/de-xuat-thong-minh` "21 mẫu" nhưng chỉ 3 thật | snapshot DOM | 🟡 P2 | ✅ **ĐÃ SỬA** — dedupe ở `causal_memory.py` + `ops_predict.py` + id luật ổn định |
| `/handover` không cảnh báo lệch số két | "Đánh giá: (trống)" | 🟡 P2 | ✅ **ĐÃ SỬA** — thêm `detect_number_conflicts` + Alert UI |
| Phần còn lại hoạt động: /vet render, 200 vết, login hung/lan | snapshot | ✅ | — |

> Chi tiết đầy đủ + bằng chứng + cách fix: [`DEMO_QA_RESULTS.md`](./DEMO_QA_RESULTS.md) §6.

## D. Thứ tự khuyến nghị chạy (cho agent)

`S1 → S18 (đã ở trang) → S3 → S2 → S4 → S5 → S6 → S7 → S8 → S10 → S9 → S11 → S12 → S13 → S17 → S19 → S16 → S14 → S15`
(Ly do: trước tiên kiểm tra các màn không ghi DB; FB/soạn bài/đặt bàn để cuối vì chạm ra ngoài.)

## E. Kết quả ghi vào `DEMO_QA_RESULTS.md`
Mỗi bước: `Sx | PASS/FAIL/BLOCKED | thời điểm | screenshot | vướng mắc`.

---

## F. TRẠNG THÁI THỰC THI (2026-09-26) — Đã chạy QA

> Chi tiết đầy đủ + bằng chứng: [`DEMO_QA_RESULTS.md`](./DEMO_QA_RESULTS.md)
> **Tóm tắt: 20 PASS · 2 PARTIAL · 1 FAIL · 1 BLOCKED · 3 chưa chạy · 2 bỏ qua (an toàn).**

### F.1 Nhãn nút THỰC TẾ trên production (khác mã cũ — dùng cái này)

| Vị trí | Nhãn thực tế đã xác nhận |
|--------|---------------------------|
| `/inbox` | **ĐÃ ĐỔI GIAO DIỆN**: "AI tự động duyệt · chỉ xem"; filter Trạng thái có option "AI đang xử lý / Mới vào hộp thư / AI đã duyệt / AI đã từ chối"; KHÔNG còn nút "Duyệt ràng buộc" thủ công |
| `/inbox` panel phải | "Trợ lý đọc giúp trang này" + "Hỏi AI về trang này" |
| `/roster` | "Xếp lịch tự động" · "MỞ LẠI ĐỂ ĐIỀU CHỈNH" · modal "Mở lại lịch" (nút đích) / "Huỷ" · "Chỉnh khung giờ" · "Xuất lịch"; workflow hiển thị "1. Chuẩn bị lịch / 2. Rà soát và xử lý ca thiếu / 3. Đã duyệt và công bố" |
| `/copilot` | Nút gửi là **"Gửi"**; chip gợi ý gồm "Xếp lịch tuần sau…", "Xem xét duyệt đổi ca ngày mai", "Tóm tắt bản tin sáng hôm nay", "Kiểm tra tồn kho…", "Đề xuất quy định mới…"; thẻ proposal có nút **"✓ Duyệt & Áp dụng"** / **"✕ Từ chối"** |
| `/giai-thich` | Nút là **"Truy vết nhân quả"** (KHÔNG phải "Giải thích") |
| `/qr` | "PHÁT MÃ ĐIỂM DANH" / "ĐIỂM DANH VÀO CA" (chữ hoa); mã che `•••• •••• XXXX` |
| `/treo` | "Đánh dấu xong" · tab "Việc cần xử lý (n)" / "Lần sửa lịch (n)" |
| `/cam-nang` | "CHẠY 8 BƯỚC XÉT LUẬT" · "HỎI QUY TRÌNH" |
| `/sop` | "Hỏi" · badge "Có trong cẩm nang · AI · <provider> · Tin cậy N%" + mục "Nguồn dẫn" |
| `/handover` | "Tách thành bàn giao" |
| `/de-xuat-thong-minh` | "Chạy phát hiện mẫu thành công" · "Duyệt luật" |

### F.2 Trang có panel AI dùng chung (đã xác nhận)
`/inbox`, `/giai-thich`, `/de-xuat-thong-minh`… đều có panel phải: **"Trợ lý đọc giúp trang này"** (nút "Phân tích lại") + **"Hỏi AI về trang này"** (ô "Nhập câu hỏi…" + nút "Hỏi").

### F.3 Danh sách route bị chặn theo vai (đọc từ `apps/web/src/lib/session.ts`)
- `OWNER_ONLY` (chỉ `chu_quan`): `/menu`, `/nguoi`
- `MANAGER_ONLY` (`quan_ly` + `chu_quan`): `/lich-tuan`, `/roster`, `/inbox`, `/page-quan*`, `/ai-learning`, `/cau-hinh-quan`, `/khao-sat-gia`, `/vet`, `/giai-thich`, `/de-xuat-thong-minh`, `/thu-nghiem-an-toan`, `/quanverse/{war-room,shift-rescue,rules}`
- ⚠️ `/skills` và `/gmail` **không thuộc tập nào** → bị chặn với mọi vai (**Bug #4**, xem QA results)

