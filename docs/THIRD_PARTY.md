# Third-party & free-tier — ngày kiểm 2026-08-21

| Thành phần | Giấy phép / hạng | Hạn mức (theo trang công bố lúc kiểm) | Ngày kiểm | Ghi chú vận hành |
|------------|-----------------|----------------------------------------|-----------|------------------|
| FastAPI | MIT | n/a | 2026-08-21 | API |
| Next.js | MIT | n/a | 2026-08-21 | Web |
| Pydantic | MIT | n/a | 2026-08-21 | Contracts |
| PostgreSQL image | PostgreSQL License | n/a | 2026-08-21 | Docker |
| Redis image | RSALv2 / SSPLv1 (image) / client BSD | n/a | 2026-08-21 | Chỉ dùng local/dev |
| OR-Tools | Apache-2.0 | n/a | 2026-08-21 | Xác nhận lại file LICENSE trong release dùng |
| Google AI Studio / Gemini free | ToS Google | Có hạn mức ngày/phút — **không** cam kết “vĩnh viễn” | 2026-08-21 | Router phải có fallback Ollama |
| NVIDIA NIM / genai (`ai.api.nvidia.com/v1/genai`) | NVIDIA API Trial ToS | Có hạn mức theo tài khoản | 2026-09-26 | **ĐÃ GỠ BỎ khỏi hệ thống** — không còn dùng ở `ca_agents/image_gen.py`. Lý do: **KHÔNG nhận ảnh người dùng** (cả `flux.1-kontext-dev` i2i lẫn ControlNet `canny`/`depth` đều đòi `example_id` nội bộ của NVIDIA; tự upload asset lên NVCF thì S3 trả `403 SignatureDoesNotMatch`), nên không làm được tính năng "AI sửa ảnh thật" — việc mà Cloudflare Workers AI làm được MIỄN PHÍ. Giữ dòng này để ghi lại quyết định, không phải để dùng. |
| Pollinations Gen — image editing (`gen.pollinations.ai/v1/images/edits`) | ToS Pollinations | **Có Pollen miễn phí qua Quests**; cần API key (đăng nhập GitHub) | 2026-09-25 | Provider image-to-image dự phòng — `ca_agents/image_gen.py::edit_image`. 19 model nhận ảnh vào (đã dò từ `/image/models`), mặc định `black-forest-labs/flux.1-kontext-pro`. Nhận `multipart/form-data` với file nhị phân trực tiếp (không cần upload trung gian). |
| Cloudflare Workers AI (`api.cloudflare.com/client/v4/accounts/{id}/ai/run/{model}`) | Cloudflare Workers AI ToS | **Miễn phí 10.000 neurons/NGÀY** (reset 00:00 UTC, không cần thẻ); ảnh 1024×1024 tốn ~105 neurons → ≈80–95 ảnh/ngày | 2026-09-26 | Provider **CHÍNH** cho cả sinh ảnh mới lẫn sửa ảnh thật (image-to-image) — `ca_agents/image_gen.py`. Đã kiểm chứng thật: `@cf/black-forest-labs/flux-2-klein-4b` (mặc định) và `flux-2-dev` đều nhận ảnh người dùng; nhận thẳng `width`/`height` (thử 896×1120 và 768×1344 đều trả ĐÚNG kích thước). Cần **cả hai** biến `CLOUDFLARE_ACCOUNT_ID` + `CLOUDFLARE_API_TOKEN`; input là `multipart/form-data`, trường ảnh `input_image_0` (fallback `image` nếu 400). Ảnh trả về ở `result.image` (base64). |
| Gemini image (flash-image / pro-image) | ToS Google | Free tier hiện **limit=0** cho model ảnh → luôn fallback | 2026-09-21 | Dự phòng cho cả sinh ảnh và sửa ảnh thật (nhận `inline_data` base64); xem `ca_agents/image_gen.py` |
| Pollinations image API (cũ) | ToS Pollinations (miễn phí, no-key) | Community model hay 429/500 — có retry, nhưng TỔNG thời gian bị chặn bởi ngân sách `timeout_s`; model "turbo" làm fallback tốc độ | 2026-09-22 | Dự phòng cuối cho text-to-image + nguồn sinh **nền** trong `bg_redesign` — `ca_agents/image_gen.py` |
| Pillow | MIT-CMU | n/a | 2026-09-22 | Composite local trong `ca_agents/bg_redesign.py` + đọc/ghi ảnh trong test; khai báo ở `packages/agents/pyproject.toml` |
| SciPy | BSD-3-Clause | n/a | 2026-09-21 | `ndimage` tách chủ thể (label/fill holes) trong `bg_redesign.py`; thuần CPU, không gọi mạng |
| Groq free tier | ToS Groq | Rate limit thay đổi theo thời điểm | 2026-08-21 | Không phụ thuộc một nhà cung cấp |
| OpenRouter free models | ToS OpenRouter | Hạn mức credit free thay đổi | 2026-08-21 | Ghi `make budget` tuần |
| Ollama local | MIT (phần mềm) | Phụ thuộc máy đội | 2026-08-21 | Phương án B khi hết hạn mức cloud |
| Zalo OA | Zalo OA ToS / bảng giá | **Gói miễn phí có thể không đủ / đổi** | 2026-08-27 | **Kênh tin ưu tiên (VN)** — runbook `docs/runbooks/zalo-oa-connect.md`; cần OA + token do quán tạo |
| Telegram Bot API | Telegram ToS | Free cho bot thông thường | 2026-08-27 | Kênh phụ cùng MessagePort; runbook `telegram-bot-connect.md` |
| Facebook Page / Graph | Meta Platform ToS | App Review + quyền Page | 2026-08-27 | Surface `/page-quan` riêng; trống tới khi có token — `facebook-page-connect.md` |
| Thu thập Google Maps / ShopeeFood / Grab | ToS từng nền tảng | Thu thập tự động **không** giả định được phép | 2026-08-21 | AG-VOC chỉ nhận phản hồi quán tự chuyển |
| Camoufox (Firefox chống-detect) | MPL-2.0 | Binary ~300MB sau `camoufox fetch`; không có API hạn mức | 2026-09-10 | Optional — tier cào browser-thật AG-TREND; Linux cần system deps (libgtk-3-0, libasound2, libdbus-glib-1-2, libx11-xcb1, fonts) — runbook `docs/runbooks/camoufox-scraping.md` |
| Pillow | MIT-CMU (HPND) | n/a | 2026-09-23 | Ảnh sản phẩm sinh **tại máy** — ADR-019. Đã có sẵn trong venv/CI qua `reportlab`; không gọi mạng nên không có hạn mức nào bị thu hồi |
| google-api-python-client | Apache-2.0 | Gmail API free tier: 1 tỷ quota units/ngày/project; 250 quota units/user/giây | 2026-09-19 | Quản lý Gmail (`ag_gmail`): đọc/gửi/labels/filters; cần OAuth client `NHIPQUAN_GMAIL_CLIENT_ID` |
| google-auth / google-auth-oauthlib | Apache-2.0 | n/a | 2026-09-19 | OAuth 2.0 flow cho Gmail; refresh token tự động |
| cryptography (Fernet) | Apache-2.0 / BSD-3-Clause | n/a | 2026-09-19 | Mã hoá OAuth token trong DB; key qua `NHIPQUAN_ENCRYPTION_KEY` |
| Space Grotesk (font) | SIL OFL 1.1 | n/a — file **commit trong repo** | 2026-09-25 | Tiêu đề. `apps/web/src/fonts/`; xem `README.md` cùng thư mục |
| IBM Plex Sans (font) | SIL OFL 1.1 | n/a — file **commit trong repo** | 2026-09-25 | Chữ đọc chính |
| IBM Plex Mono (font) | SIL OFL 1.1 | n/a — file **commit trong repo** | 2026-09-25 | Số liệu / mã / mono |
| Open-Meteo Forecast + Geocoding | CC-BY 4.0 (data) / open API không cần khoá | Non-commercial free, rate hạn chế theo IP — cache 20 phút phía server | 2026-09-30 | AI FORECAST `/api/v1/thoi-tiet/hom-nay` — `ca_api/services/thoi_tiet.py` |

**Vì sao font được commit vào repo (khác các mục trên):** ba họ này tải từ Google
Fonts một lần rồi commit dưới dạng `.woff2`. Lý do: `next/font/google` tải font
**lúc build**, và trong Docker build của CI lời gọi đó vỡ
(`TypeError: Cannot read properties of null` ở `loader.js`) trong khi build ở máy
local vẫn xanh — lỗi ẩn tới tận bước deploy. Guideline
(`docs/design-guidelines.md` §Typography) cũng đã yêu cầu self-host để cổng §14.9
(demo chạy khi rút mạng) không vỡ. OFL 1.1 cho phép phân phối kèm sản phẩm, chỉ
cấm bán font riêng lẻ. Kích thước: 27 file, ~324 KB.

## Kết luận vận hành (không phải lời hứa marketing)

- Ngân sách **0 đồng** = không trả phí cloud bắt buộc; phụ thuộc free tier **dễ thu hồi** → thiết kế router đa nhà cung cấp + Ollama.
- Trước bảo vệ: C chụp lại trang giá/ToS và cập nhật cột Ngày kiểm.
