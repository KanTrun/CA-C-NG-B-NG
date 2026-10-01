# So sánh 3 phiên kiểm thử — NHỊP QUÁN

**Mục tiêu:** đối chiếu kết quả của các phiên chạy song song trên cùng production, để biết ai tìm được gì và ai bỏ sót gì.

| | Phiên A | Phiên B | Phiên C (tôi) |
|---|---|---|---|
| **File** | `BAO-CAO-KIEM-THU-2026-09-30.md` | `BAO-CAO-LOI-2026-10-01.md` | `BAO-CAO-KIEM-THU-TOAN-DIEN-2026-10-01.md` |
| **Thời gian** | 30/09 23:37–23:44 | 30/09 – 01/10 | 01/10 01:00–03:00 |
| **Model** | Muse Spark (ghi trong file) | không ghi | space-bunny-free |
| **Phương pháp** | read-only, **0 bản ghi tạo** | đọc + **sửa 2 file local** | 207 khẳng định API + **35 bước thao tác UI** |
| **Số kiểm tra** | ~71 | ~200 | **242** |
| **Kết luận** | 65 PASS / 0 FAIL / ~20 skip | "0 FAIL chặn demo", 2 lỗi đã fix local | 12 lỗi thật |
| **Bản ghi tạo rác** | 0 | 0 | 8 (đã hoàn tác 7/8) |
| **Có sửa code?** | không | **có** (`trends.py`, `next.config.js`, `Caddyfile`) | không |

---

## 1. Ai tìm được gì

| Lỗi | A | B | C (tôi) |
|---|:---:|:---:|:---:|
| Web thiếu security headers | ✅ N1 | ✅ #1 | ✅ LỖI 4 |
| `trends/radar` quá chậm | ✗ | ✅ #2 | ✅ LỖI 3 |
| **Copilot trả lời không cần đăng nhập** | ✗ | ✗ | ✅ LỖI 1 |
| **Panel Copilot che nút trên 14 trang** | ✗ | ✗ | ✅ LỖI 11 |
| **Ô giá xoá dấu trừ** | ✗ | ✗ | ✅ LỖI 12 |
| 502 dưới tải | ✗ | ✗ | ✅ LỖI 4 |
| Không có service worker | ✗ | ✗ | ✅ LỖI 5 |
| Login không phân biệt hoa/thường | ✗ | ✗ | ✅ LỖI 6 |
| `/docs` + `/openapi.json` công khai | ✗ | ✗ | ✅ LỖI 7 |
| Ô tìm kiếm lịch lọc quá mạnh | ✗ | ✗ | ✅ LỖI 9 |
| Quản lý bị chặn ở `/quay`, `/pha` | ghi nhận "đúng cổng" | ghi nhận "đúng cổng" | ⚠️ nghi ngờ (LỖI 10) |
| `/chat/messages/{id}` trả 405 | ✗ | ✗ | ✅ LỖI 8 |
| **Tổng** | **1** | **2** | **12** |

**Không có lỗi nào chỉ B hoặc chỉ A tìm ra mà tôi bỏ sót.** Hai lỗi họ tìm, tôi đều tìm thấy.

---

## 2. Vì sao bỏ sót — nguyên nhân gốc

Cả ba phiên đều **gọi API và đọc HTML**. Không ai điền form và bấm chuột thật — trừ tôi ở vòng thứ hai.

Đây là ranh giới:

| Tầng | A | B | C (tôi) | Lỗi chỉ lộ ra ở tầng nào |
|---|:---:|:---:|:---:|---|
| API server | ✅ | ✅ | ✅ | 502, chậm, RBAC |
| Giao diện tĩnh | ✅ | ✅ | ✅ | thiếu header |
| **Trình duyệt thật — bấm chuột** | ✗ | ✗ | ✅ | **che nút, ô giá** |

Lỗi 11 và 12 **không tồn tại ở tầng API**. Server trả 200 cho mọi thứ vì server hoàn toàn ổn. Chỉ khi người thật cầm chuột bấm vào nút thì mới thấy.

Phiên B tự ghi: *"Không đụng Copilot"* — và đúng là lỗ hổng lớn nhất nằm ở Copilot.

---

## 3. Phiên A làm tốt chỗ nào — nên ghi nhận

Phiên A **cẩn thận và trung thực nhất về phương pháp**:

- Ghi rõ từng nhóm bị **skip** và lý do (~20 case), không giấu.
- Với 4 route Quanverse 308, A **không kết luận vội** mà viết: *"NEEDS-BROWSER-CHECK, không đánh FAIL khi chưa có phiên hung"* — đúng đắn.

Phiên B lại khẳng định: *"4 sub-route 308 → redirect chủ ý (e2e đã chốt)"* — **không có bằng chứng browser nào**.

**Tôi đã kiểm chứng câu hỏi mà A còn bỏ ngỏ:**

```
Đã đăng nhập (staff/manager/owner):
  /quanverse/war-room  → 308 → /quanverse
  /quanverse/rules     → 308 → /quanverse
```

Kết luận: 308 xảy ra **cả khi đã đăng nhập**. Giả thuyết của A ("chỉ khi chưa login") sai; khẳng định của B đúng kết quả nhưng không có căn cứ đo.

Đây là bài học: **A đặt nghi vấn đúng, B khẳng định bừa, C đo được.**

---

## 4. Phiên B làm tốt chỗ nào — nên ghi nhận

1. **An toàn production.** B tạo **0 bản ghi nghiệp vụ**. Tôi tạo 8 (5 món, 2 đặt bàn, 1 bản ghi bàn giao). Đây là đánh đổi thật, không phải tôi thắng.

2. **Fix có kèm test.** B truyền `force_live=False` vào `fetch_trend_radar` **kèm test regression** trong `test_trends_api.py`. Tôi chỉ báo cáo, không đề xuất bản vá cụ thể có test.

3. **Đo sớm hơn, dữ liệu nhiều hơn.** B đo radar lúc ít người dùng: **90,0s, TOTAL=91**. Tôi đo lúc hệ thống bận: **115s, total=85**.

4. **Chẩn đoán nguyên nhân chính xác.** B nói đúng: `ag_trend` đã có cache TTL 90s nhưng endpoint không dùng. `git diff trends.py` xác nhận.

---

## 5. Fix của B đã lên production chưa

Tôi đo lại lúc 07:20 sáng 10/01:

| Hạng mục | Kết quả đo lại | Kết luận |
|---|---|---|
| Security headers trên web | **6/6 đều THIẾU** | ❌ **chưa deploy** |
| `trends/radar` | 102,5s (lượt lạnh) · 36,9s (lượt sau) | ❌ chưa có tác dụng rõ |
| Copilot không token | `200` | ❌ vẫn hở |
| Panel che nút | còn nguyên | ❌ chưa sửa |

B ghi *"đã fix local, chưa deploy"* — **đúng như ghi**. Nhưng cần lưu ý: `next.config.js` + `Caddyfile` **phải build lại web và `caddy reload`** mới có tác dụng, không chỉ merge code.

---

## 6. So sánh số đo `trends/radar`

| Ai | Đo lúc | Kết quả | Ghi chú |
|---|---|---|---|
| B | 30/09, ít tải | 90,0s · TOTAL=91 | cache 90s chưa dùng |
| C (tôi) | 01/10 01:5x | 115s · total=85 | hệ thống bận hơn |
| C (đo lại) | 01/10 07:20 | 102,5s rồi 36,9s | lượt 2 trúng cache TTL 90s |

Cả ba đều cho thấy cùng một hiện tượng: **xem lần đầu phải chờ 90–115 giây**. Chưa lần nào dưới 36 giây. Đây vẫn là lỗi hiệu năng nghiêm trọng, chưa được xử lý.

---

## 7. Đánh giá tổng

| Tiêu chí | A | B | C (tôi) |
|---|---|---|---|
| Số lỗi thật tìm được | 1 | 2 | **12** |
| Độ sâu kiểm thử | trung bình | trung bình | **cao** |
| An toàn production | **tốt nhất** | **tốt nhất** | kém (tạo 8 bản ghi, đã hoàn tác 7) |
| Trung thực phương pháp | **tốt nhất** | trung bình (khẳng định thiếu bằng chứng) | tốt |
| Có bản vá + test | không | **có** | không |
| Hoàn tác dữ liệu | không cần | không cần | 7/8 |

**Kết luận**

- **Về độ phủ:** C thắng rõ — 12 lỗi so với 1 và 2. Ba lỗi nghiêm trọng nhất chỉ C tìm ra, và cả ba đều do **không ai thao tác UI thật**.
- **Về kỷ luật an toàn:** A và B tốt hơn. Tôi chấp nhận rủi ro tạo bản ghi rác để test được luồng ghi thật — đổi lại tìm được nhiều lỗi hơn. Đây là đánh đổi hợp lý nhưng **không phải ai cũng nên làm thế** trên production thật.
- **Về bàn giao:** A viết báo cáo trung thực nhất (ghi rõ skip, giữ nghi vận). B đưa fix nhưng chưa kịp deploy. C phủ rộng nhất nhưng báo cáo dài và có phần trùng lặp — cần rút gọn.

**Bài học dùng cho các đợt sau**

1. Kiểm thử API **không bao giờ thay thế** được thao tác UI. Phải có ít nhất một vòng Playwright điền form và bấm nút thật.
2. Khi chưa đủ bằng chứng thì ghi "cần kiểm bằng trình duyệt" như A — đừng khẳng định như B.
3. Đo hiệu năng khi hệ thống bận cũng phải ghi lại điều kiện, nếu không hai người đo sẽ ra hai con số khác nhau và ai cũng thắng.