# BÁO CÁO VÉT TOÀN DIỆN NHỊP QUÁN — 2026-10-01

> **Site:** https://nhipquan.duckdns.org (production) · **Thời điểm:** 2026-10-01 (giờ VN)
> **Cách test:** không có điều khiển trình duyệt tự động — quan sát bằng WebFetch HTML + probe API (urllib, stdlib) + đọc mã nguồn đối chiếu (`page.tsx`, router, `session.ts`, e2e). Mọi luồng ghi có hoàn tác; luồng gửi ra ngoài (FB/m mail) dừng ở bước duyệt.
> **Chỉ thị vòng này:** phát hiện lỗi thì fix luôn (TRỪ mọi lỗi thuộc chat AI agent đứng đầu Copilot — chỉ ghi nhận, không đụng).

---

## 1. Bản đồ chức năng từng trang (quét từ mã + kiểm live)

40 thư mục trang + `/` + alias `/roster`. Chức năng chính trên màn hình (nút/ô nhập) và API backing:

| Trang | Chức năng trên màn hình | API backing (quét `apiGet/Post…`) | Live |
|---|---|---|---|
| `/` | Quick-login 19 acc, CTA Vào ca/Bản đồ | — (tĩnh) | 200, đủ 19 acc |
| `/login` | Form tài khoản/mật khẩu, link /dang-ky /huong-dan | `POST /auth/login` | 200; sai pass 401 |
| `/dang-ky` | Form tạo tài khoản NV | `POST /auth/register` | 200; body rỗng 422 |
| `/huong-dan` | Bản đồ 4 phòng, 8 bước, lọc theo vai | — (tĩnh) | 200 |
| `/them` | 19 tile lối vào | — | 200 |
| `/hom-nay` | KPI, bản tin sáng, hàng đợi, việc treo, shortcut 10 khối | `GET /hom-nay`, `/viec-treo` | 200 |
| `/toi` | Lịch cá nhân, Nhận/Nhả ca, bind email | `GET /me/profile` | 200 |
| `/lich-tuan`, `/roster` (alias) | Ma trận 7 ngày, Xếp lịch tự động, Ghim, Sau→, lifecycle, mở lại (modal lý do), thông báo | drawer + solver routes | 200 |
| `/qr` | PHÁT MÃ ĐIỂM DANH, ô dán mã, ĐIỂM DANH VÀO CA, link phiếu/lịch | `POST /qr`, `POST /qr/{token}` | 200; body rỗng 422 |
| `/phieu` | Tôi đã có mặt, checklist từng bước, chụp ảnh, Để lại việc khó | `POST /phieu/start…` | 200; start rỗng 422 |
| `/treo` | Tab việc cần xử lý / lần sửa lịch, Đánh dấu xong | `GET /viec-treo`, `/ghi-nhan-sua` | 200 (33 việc) |
| `/doi-ca` | Chợ đổi ca, ca thiếu người, chọn người nhận, hạn nhận | `GET /cho-doi-ca`, `/open-shifts` | 200; POST rỗng 422 |
| `/handover` | Ô dán text 2 ca, Tách thành bàn giao, 4 khung SBAR + cảnh báo lệch số | `POST /handover` | 200; `{}` 422 |
| `/chat` | Hội thoại, tìm kiếm, trợ lý lịch/vận hành, gắn thẻ, sửa/thu hồi tin | `GET /chat/scheduler`, WS `/ws/chat` | 200; WS 4001 auth-timeout |
| `/copilot` | Ô chat, chip gợi ý, thẻ CHỜ DUYỆT (Duyệt/Từ chối/Sửa), voice mic | `POST /copilot/message(/stream)`, `/execute-action` | LIST_STAFF→19; propose→reject OK (chi tiết §4; **không fix gì thuộc Copilot**) |
| `/sop` | Ô hỏi, trích dẫn nguồn, cờ chưa-có | `POST /sop` | 2–8°C có trích dẫn; câu lạ `chua_co=true` |
| `/cam-nang` | Pipeline 8 bước, Chạy 8 bước xét luật, Hỏi quy trình, bật/tắt luật | `GET /cam-nang` | 200 |
| `/cong-bang` | Biểu đồ sổ nợ 4 trục, link hộp thư/xếp lại lịch | `GET /cong-bang(/bao-cao)` | 200 |
| `/tkb` | Chọn ảnh, Thử ảnh mẫu, Xác nhận gắn TKB, xem khung bận | `GET /tkb/mine`, `/ops/pickers`, `POST /tkb/upload` | 200; upload không file 400 `thieu_file` |
| `/nguoi` | 19 tài khoản, cơ cấu đội, dialog nâng/hạ vai, vô hiệu hoá | `GET /nguoi` (+nang-vai/ha-vai/deactivate) | hung 200 =19; lan/minh 403 |
| `/menu` (UI OWNER_ONLY) | Danh mục món, sửa giá/BOM, AI vẽ ảnh | `GET /menu/quan-tri`, `PUT /menu/{id}` | hung 200; lan 403 |
| `/quay` | Giỏ, Gửi sang pha chế, đơn của ca, doanh thu, thanh toán | `GET /menu`, `/quay/don`, `/quay/bao-cao`, `/toi/lich` | 200; `GET /quay/don` 403 cả 3 vai khi chưa điểm danh (đúng cổng `chua_diem_danh`, §5) |
| `/pha` | Cột Chờ pha/Đang pha/Xong, nhận pha, hoàn tất, huỷ (lý do bắt buộc) | `GET /quay/don` | 200 (UI khoá khi chưa điểm danh — đã kiểm 29/09) |
| `/cuoc-hop` | Chọn loại họp, dán transcript/ghi âm Meet/ghi âm quầy, Phân tích, Duyệt & phân công, rollback | `POST /meeting/analyze`, `/apply`, `/meetings/{id}/rollback`, `DELETE /meetings/{id}` | analyze 200 (không lưu bản ghi); minh analyze 200 (đúng STAFF_ACCESS) |
| `/de-xuat-thong-minh` | Chạy phát hiện mẫu, Duyệt luật, mô phỏng Twin | `GET /ops/predict/suggestions` | 200 (3 mẫu, không còn 21) |
| `/giai-thich` | Ô “Tại sao ca tối T6 có 2 pha chế?”, Truy vết nhân quả | `GET /ops/explain/chains` | 200, không lặp node |
| `/thu-nghiem-an-toan` | Kịch bản Bớt/Thêm nhân sự, Tăng/Giảm giá, chạy mô phỏng | `POST /ops/twin/simulate` | 200 `qa_vet_01_10`; minh 403 |
| `/ai-learning` | Trạng thái vận hành AI, rule proposals, đánh giá, gửi mail qua trợ lý | `GET /ai/*` (4 endpoint) | 200 (manager; minh 403) |
| `/inbox` | Hàng đợi AI tự động duyệt, filter trạng thái, panel AI đọc giúp trang | `GET /inbox/rang-buoc`, `/lich/lifecycle` | 200 (23 mục); minh 403 |
| `/quanverse` | Cockpit điều hành duy nhất | experience APIs | 200 |
| 4 sub quanverse | Redirect vĩnh viễn về `/quanverse` (chủ ý) | — | 308 `Location: /quanverse` |
| `/tieu-thu` | Sổ tiêu thụ, ghi dòng (mặt hàng/số lượng/đơn vị), cảnh báo dưới ngưỡng | `GET /tieu-thu` | 200 |
| `/hao-phi` | Bảng hao phí, ghi chú tự do, cụm nguyên nhân | `GET /waste`, `/hao-hut?ky`, `/hao-hut/danh-muc` | 200 |
| `/khao-sat-gia` | Bán kính/kênh/chủ đề, tạo job, theo dõi, xác nhận NEEDS_REVIEW, quota | `/market/catchment-survey*`, `/market/serpapi/quota` | dashboard+metrics+quota 200 (quota còn 240/250); KHÔNG tạo job (tốn quota thật) |
| `/page-quan` | Bài nháp, AI soạn nháp, trends radar, cấu hình trả lời khách | `/page/status|drafts|threads`, `/trends/*`, `/store/*` | 200; xem §3 về radar |
| `/page-quan/fb-inbox` | Hàng đợi duyệt, AI draft, stats | `GET /page/fb-inbox`, `/stats` | 200 (20 mục); KHÔNG bấm Đăng phản hồi |
| `/page-quan/dat-ban` | Sơ đồ bàn, tạo/huỷ đặt bàn (lý do) | `GET /reservations` (+POST) | 200; POST rỗng 422 (không tạo) |
| `/gmail` | Tài khoản/Email/Nhãn+Bộ lọc, kết nối OAuth | `GET /gmail/accounts*` | 200 `{accounts: []}`; oauth 503 `chua_cau_hinh_oauth_gmail` (fail-closed trung thực) |
| `/cau-hinh-quan` | Form hồ sơ quán/AI, live preview, lưu | `GET /store/profile|promotions` | 200; KHÔNG PUT (tránh đổi hồ sơ thật) |
| `/vet` | Bảng 200 vết, lọc người/thời gian, tìm kiếm, panel AI | `GET /audit?limit=500` | hung/lan 200; minh 403 |
| `/contracts` | Explorer hợp đồng ADR-012 | `GET /contracts` | 200, tên rút gọn + cờ mô phỏng |
| `/skills` | Danh mục 14 skill, tìm kiếm, xem SHA, verify smoke | `GET /skills`, `POST /skills/{id}/verify` | 200; verify `barista-waste-audit` VERIFIED |

---

## 2. Ma trận RBAC API (hung/lan/minh/không-token)

47 endpoint GET. Kết quả rút gọn — **đúng thiết kế toàn bộ**:

- Mọi vai đã login 200: `/me`, `/store/profile|promotions`, `/hom-nay`, `/toi/lich`, `/cong-bang*`, `/viec-treo`, `/ghi-nhan-sua`, `/cam-nang`, `/lich/*`, `/menu` (đọc quầy — N3), `/tieu-thu`, `/waste`, `/handover`, `/meetings`, `/cho-doi-ca`, `/open-shifts`, `/tkb/mine`, `/ops/pickers`, `/chat/*`, `/gmail/accounts`, `/market/serpapi/quota`, `/skills` (công khai — cả không-token cũng 200, chủ ý).
- Manager-only (hung/lan 200 · minh 403 · none 401): `/nguoi`, `/audit`, `/inbox/rang-buoc`, `/ops/explain/chains`, `/ops/predict/suggestions`, `/ops/twin/scenarios`, `/experience/rules/candidates`, `/ai/*` (3), `/menu/quan-tri`, `/menu/anh/kha-dung`, `/hao-hut/danh-muc`, `/page/status|drafts|fb-inbox/stats`.
- Cổng điểm danh: `GET /quay/don` 403 cả hung/lan/minh khi chưa điểm danh (`chua_diem_danh`) — đúng thiết kế (UI /quay khoá + Alert).
- Không token → 401 mọi endpoint cần auth (trừ `/skills`, `/contracts` công khai chủ ý).

## 3. Bug thật phát hiện + đã fix: `GET /trends/radar` mất ~90s

- **Hiện tượng:** 3 lần gọi (hung/lan/minh) đều timeout ở 25s; gọi lại timeout 100s → **200 TOTAL=91 sau 90.0s**. Mỗi lượt xem page-quan cào live cả 5 nguồn.
- **Gốc:** endpoint không truyền `force_live` → default `True` → bỏ qua cache tổng hợp TTL 90s đã có sẵn trong `ag_trend.py` (chết code từ phía endpoint). Vòng lặp parallel 5 nguồn, mỗi nguồn nhiều request ngoài 6–9s.
- **Fix (1 dòng hành vi + docstring + test):** `trends.py` truyền `force_live=False`; test mới `test_trends_radar_dung_cache_tong_hop` chốt kwargs. Lượt đầu sau TTL vẫn cào live (UI có loading), các lượt trùng tham số trong 90s trả ngay + đỡ bị nguồn chặn IP.
- **Verify:** pytest `test_trends_api.py` 2 passed; ruff sạch. Production vẫn chạy bản cũ tới khi deploy.

## 4. Luồng ghi đã thực thi có kiểm chứng (hoàn tác/không đổi nghiệp vụ)

| Luồng | Kết quả |
|---|---|
| Copilot propose `PROPOSE_HANGING_TASK` (conf 0.9) → reject `act_5f5dc7e7` | `rejected`; `/viec-treo` **33→33 không đổi** |
| Meeting analyze (transcript máy pha/sữa/đoàn 25 khách) | 200 đủ 20+ trường; **không lưu bản ghi** (DELETE → 404, list 1→1) |
| Draft Page thủ công → `tu_choi` | `trang_thai=tu_choi`, `graph_post_id=None` — **không đăng FB**; minh tạo → 403 |
| Twin simulate `qa_vet_01_10/them_nhan_su` | 200 `{ok, scenario}`; minh 403 |
| Skill verify `barista-waste-audit` | 200 `VERIFIED` (smoke script PASSED) |
| SOP có-nguồn / SOP lạ | 2–8°C + `trich_dan`; câu lạ `chua_co=true` (không bịa) |
| Copilot LIST_STAFF | “Hiện có 19 nhân sự” (đúng, không rác) |
| WS `/ws/chat` không auth | Đóng `4001 auth_timeout`, không rò message |

## 5. Ghi nhận đúng-thiết-kế (không fix, không phải bug)

- `GET /quay/don` 403 cả chủ quán khi chưa điểm danh — cổng `_require_dang_ca` (pos.py:179), khớp UI khoá quầy (bug #27 đã sửa).
- `POST /meeting/analyze` minh 200 — `/cuoc-hop` thuộc STAFF_ACCESS; analyze không lưu DB nên cho mọi vai là hợp lý.
- 4 sub-route Quanverse 308 → `/quanverse` — redirect chủ ý (`next.config.js` + e2e `quanverse-hidden-routes.spec.ts`); docs D9 đã sửa kỳ vọng.
- `GET /menu` NV 200 — chủ ý cho quầy POS (comment + test đã chốt 30/09).
- Gmail OAuth 503 `chua_cau_hinh_oauth_gmail` — fail-closed trung thực.
- `POST /resGET /inbox/rang-buoc/<fake>` 405 — item chỉ thao tác qua POST collection (đúng REST).
- TKB upload không file 400 `thieu_file`; đổi-ca rỗng 422; đặt bàn rỗng 422; menu id xấu 422.

## 6. Validation âm tính (không đột biến, 13 case PASS)

Register rỗng 422 · quay/don rỗng 422 · handover `{}` 422 · meeting `{}` 422 · copilot `{}` 422 · sop `{}` 422 · qr `{}` 422 · phieu/start `{}` 422 · menu `AB!!` 422 · inbox fake-id 422 · TKB người khác 403 · traversal `chat/uploads/../../.env` 404 · traversal `menu/../../etc/anh` 404 · login sai 401 · CORS evil không echo · API headers `nosniff/DENY` đủ.

## 7. Cố ý SKIP (lý do an toàn + bằng chứng cũ)

Solver/ghim/lifecycle/inbox-duyệt (đổi lịch thật — S5 26/09) · QR phát/điểm danh (đổi công — S6 26/09) · phiếu bước/ảnh (S7) · treo đánh dấu xong (S8 29/09) · pha chuyển trạng thái (B4 29/09) · TKB confirm (ghi TKB thật) · tạo khảo sát giá (quota SerpApi) · Đăng bài/Đăng phản hồi FB (đăng thật lên Page công khai — page đang `live`) · gửi mail · đăng ký spam (dò rate-limit) · Copilot Voice (cần mic) · PUT cấu hình quán · predict/run + cam-nang chạy (ghi KV).

## 8. Dấu vết để lại trên production (liệt kê để khỏi nhầm bug)

1 proposal bị reject `act_5f5dc7e7` · 1 draft `tu_choi` (QA vet 01-10) · 1 scenario twin `qa_vet_01_10` (idempotent) · audit/log append-only theo thiết kế · 4–5 session login test (tự hết hạn). **Không** đổi lịch/treo/đơn/menu/đặt bàn/TKB/dữ liệu quán.

## 9. Fix/review/deploy

- **Đã fix local (8 file, chưa commit):** `trends.py` + test (radar cache) · `next.config.js` + `Caddyfile` + comment `main.py` (headers web, 30/09) · docstring `pos.py` + test menu RBAC · docs D9. Tổng diff ~115 dòng.
- **Review (skill code-review-and-quality):** Correctness/Readability/Architecture/Security/Performance đạt — Approve. Tự bắt 1 lỗi Critical trong review: `Permissions-Policy` bản đầu `camera=(),microphone=()` sẽ giết chụp ảnh phiếu + Voice + ghi âm họp + GPS Quánverse → đã sửa thành `(self)` + mở `http:/ws:` cho dev local. CSP giữ `unsafe-inline/eval` (Next bắt buộc), `frame-ancestors 'none'` + DENY.
- **Verify:** ruff sạch; pytest `qa_dot6+http_demo` 40 passed, `menu_style+danh_muc` 55 passed, `trends` 2 passed; `node require(next.config)` OK 5 headers + 4 redirects.
- **Cần deploy mới có tác dụng trên production:** build lại web + `caddy reload` (Caddyfile mount `:ro`, `up -d` không recreate — bài học 26/09). Hiện production vẫn chạy bản cũ (radar vẫn ~90s tới khi deploy).
- **Không đụng Copilot:** mọi quan sát thuộc Copilot chỉ ghi nhận (LIST_STAFF 19 đúng, propose/reject đúng), không sửa file nào của `ag_copilot`.

## 10. Tổng hợp

**~200 lượt kiểm: 0 FAIL chặn demo.** 41/45 route web 200 + 4 redirect chủ ý; 47/47 endpoint GET đúng RBAC; 13/13 validation âm tính; 8/8 luồng ghi an toàn; 1 bug hiệu năng thật đã fix (radar 90s→cache); headers web đã fix local chờ deploy. Quán vận hành bình thường, không phát hiện regression so với QA 29/09.
