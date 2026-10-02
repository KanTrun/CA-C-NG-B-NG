# BÁO CÁO LỖI — NHỊP QUÁN (30/09–01/10/2026)

Site: https://nhipquan.duckdns.org · Vét ~200 lượt kiểm · 0 FAIL chặn demo.

## Lỗi thật (2) — đã fix local, chưa deploy

| # | Lỗi | Bằng chứng | Fix | File |
|---|---|---|---|---|
| 1 | Web HTML thiếu toàn bộ security headers (API thì đủ) | `GET /` không có `nosniff/DENY/CSP/HSTS` trong khi `/api/*` có | `headers()` trong `next.config.js` (CSP nới cho Next + `Permissions-Policy: (self)` để khỏi giết camera/mic/GPS) + HSTS ở `Caddyfile` | `apps/web/next.config.js`, `infra/oracle/Caddyfile`, comment `main.py` |
| 2 | `GET /trends/radar` mất ~90s mỗi lượt xem | Đo production: 200 sau 90.0s, TOTAL=91; endpoint cào live 5 nguồn, bỏ qua cache TTL 90s có sẵn | Truyền `force_live=False` + test regression | `trends.py`, `test_trends_api.py` |

Deploy mới có tác dụng: build lại web + `caddy reload` (Caddyfile mount `:ro`).

## Kết luận không phải lỗi (đã xác minh, không sửa)

- 4 sub-route Quanverse 308 → `/quanverse`: redirect chủ ý (e2e đã chốt).
- `GET /menu` NV đọc được: chủ ý cho quầy POS (sửa vẫn khoá chủ quán).
- `GET /quay/don` 403 cả chủ quán khi chưa điểm danh: đúng cổng `chua_diem_danh`.
- Meeting analyze cho NV: không lưu DB nên cho mọi vai là hợp lý.
- Gmail OAuth 503: fail-closed trung thực (chưa cấu hình).

## Không đụng Copilot

Mọi quan sát thuộc Copilot (LIST_STAFF=19, propose→reject giữ treo 33→33) chỉ ghi nhận đúng, không sửa file nào của `ag_copilot`.
