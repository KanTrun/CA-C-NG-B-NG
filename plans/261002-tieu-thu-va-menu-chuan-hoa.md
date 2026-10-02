# Kế hoạch: sạch dữ liệu `/tieu-thu` + chuẩn hoá menu quầy

Ngày: 2026-10-02 · Trạng thái: chờ duyệt

## 0. Chẩn đoán (đã kiểm chứng bằng dữ liệu thật)

Đọc `data/quan.db` + đọc code, được 5 nguyên nhân:

| # | Triệu chứng người dùng thấy | Nguyên nhân | Nơi đứng |
|---|---|---|---|
| 1 | Dòng trống / "dữ liệu JSON" | `kv.tieu_thu` lẫn 3 hình dạng khác nhau. Dòng legacy `{"order_id","status","items":{"ca_phe_hat":18}}` không có `hang`/`so_luong` → React render ô trống. Dòng demo `{"hang":"Ca phe hat"}` không dấu. Dòng thật `{"hang":"ca_phe_hat"}` là MÃ BOM. | `sprint45.py:1641` trả nguyên `kv_get("tieu_thu")` |
| 2 | Mất dấu | `MAT_HANG` (present.ts:461) chỉ có 9 mã; `BOM_INGREDIENTS` (bom-editor) chỉ có 10 mã, thiếu `duong/sua_dac/kem/trai_cay/syrup/ong_hut` → fallback `key.replace(/_/g," ")` ra "ca phe hat". | `present.ts:461`, `bom-editor.tsx:8` |
| 3 | Đơn vị "42 đơn vị" | `_DON_VI_BOM` (pos.py) chỉ có 4 mã LEGACY (`cafe_g/sua_ml/dao_lat/ly`) — 4 mã này **không còn món nào dùng**; 15 mã thật (`ca_phe_hat`, `da`, `duong`…) rơi vào mặc định `"đơn vị"`. | `pos.py` `_DON_VI_BOM` |
| 4 | Trùng lặp | `cafe_g` ≡ `ca_phe_hat`, `sua_ml` ≡ `sua_tuoi` là 2 hệ mã cùng nghĩa (nguồn: `_MENU_MAC_DINH` persist.py — seed menu mặc định viết "Ca phe den" + BOM `cafe_g`). Kèm dòng ghi hai lần. | `persist.py` `_MENU_MAC_DINH` |
| 5 | Trang kéo dài, không lọc nhóm | Mỗi đơn × mỗi nguyên liệu = 1 dòng; không có bộ lọc nhóm. | `tieu-thu/page.tsx` |

Song song, `/quay` bán cả 8 món bao bì nhóm `nguyen_lieu` ("Gói cà phê hạt 250g", "Bịch ly nhựa 50 cái"…) vì `GET /api/v1/menu` (`pos.py:282`) chỉ lọc `an=1`, không lọc nhóm.

**Đã chốt với người dùng:**
1. Xoá món vô nghĩa → **tự động theo quy tắc** (ẩn `an=1`).
2. 5-6 món mới → **tôi chọn món bán chạy**.
3. `/tieu-thu` → **gộp theo nguyên liệu + bộ lọc nhóm**.

---

## 1. Bảng nguyên liệu chuẩn — MỘT NGUỒN DUY NHẤT

`data/seed/danh-muc.json` thêm mảng top-level `"nguyen_lieu"` (hiện JSON **chưa** có bảng này; 3 bản sao lệch nhau đang tồn tại ở `bom-editor.tsx`, `present.ts`, `_DON_VI_BOM`):

```json
"nguyen_lieu": [
  {"ma":"ca_phe_hat","ten":"Cà phê hạt","don_vi":"g","nhom":"ca_phe"},
  {"ma":"sua_tuoi","ten":"Sữa tươi","don_vi":"ml","nhom":"ca_phe"},
  ...
]
```

16 mã: `ca_phe_hat, sua_tuoi, sua_dac, kem, duong, tra, matcha, dao, da, banh, ly, ong_hut, trai_cay, syrup, nuoc_dong_chai` + `cafe_g`/`sua_ml`/`dao_lat` **không đặt trong danh sách** — chúng là mã cũ, xử lý qua bảng alias.

### 1.1 Python — `apps/api/src/ca_api/nguyen_lieu.py` (mới)

Đọc `data/seed/danh-muc.json` lúc import (`Dockerfile.api:37` đã `COPY data ./data` → có trong ảnh).

- `chuan_hoa_ma(key) -> str` — qua `ALIAS = {"cafe_g":"ca_phe_hat", "sua_ml":"sua_tuoi", "dao_lat":"dao", "ly_nhua":"ly"}`
- `ten_nguyen_lieu(key) -> str` — có dấu; không khớp thì trả `key.replace("_"," ")` (không bịa)
- `don_vi(key) -> str`, `nhom(key) -> str`
- `DOANH_MUC: dict[ma, ...]`

### 1.2 Web — `apps/web/src/lib/nguyen-lieu.ts` (mới)

Bảng mirror + `ingredientLabel/ingredientUnit/nhomNguyenLieu`. `bom-editor.tsx` và `present.ts` import từ đây → 2 file hiện có chỉ còn import, hết bản sao.

**Chốt bằng test (không để lệch lại):**
- Python: `test_bang_nguyen_lieu_khop_danh_muc` — mỗi mã BOM của mọi món ∈ bảng, mọi mã bảng có `ten` đủ dấu.
- Vitest `src/lib/nguyen-lieu.test.ts` — đọc `data/seed/danh-muc.json` bằng `fs`, so bảng TS == bảng JSON, `ten` đủ dấu (mẫu của `present-gmail.test.ts`).

---

## 2. Backend `/tieu-thu` trả dữ liệu sạch

### 2.1 `sprint45.py:tieu_thu_list`

Không đổi shape khách quan — thêm trường, bỏ dòng hỏng:

```jsonc
{
  "id": "ttq_…",
  "ma": "ca_phe_hat",          // đã chuẩn hoá
  "hang": "Cà phê hạt",         // tiếng Việt CÓ DẤU
  "nhom": "ca_phe",             // cho bộ lọc nhóm
  "so_luong": 42, "don_vi": "g",// đơn vị ĐÚNG, không còn "đơn vị"
  "duoi_nguong": false,
  "luc": "2026-10-02T…", "nguon": "uoc_luong_tu_quay",
  "mon_id": "ca_phe_den", "mon_ten": "Cà phê đen", "mon_so_luong": 2,
  "don_quay_id": "…"
}
```

- **Bỏ dòng không đọc được**: thiếu `hang` HOẶC thiếu `so_luong` (đúng dòng legacy `order_id/status/items`) → không trả về, có đếm `da_bo_qua`.
- **Chuẩn hoá**: `ma = chuan_hoa_ma(hang)`; `hang = ten_nguyen_lieu(ma)`; `don_vi` lấy từ bảng khi mã có trong bảng (sửa "42 đơn vị" → "42 g"); dòng ghi tay tên tự do giữ nguyên tên người ghi.
- **Trùng**: bỏ dòng có `ma`+`luc`+`so_luong`+`don_quay_id` giống hệt (double-write), giữ dòng đầu.

### 2.2 Chặn sinh thêm dữ liệu bẩn

- `pos.py:_ghi_tieu_thu_uoc_luong` → ghi `ma`/`ten`/`don_vi` đã chuẩn, xoá hẳn `_DON_VI_BOM`.
- `sprint45.tieu_thu_ghi` (POST) → chuẩn hoá `hang` qua `chuan_hoa_ma` trước khi lưu.

### 2.3 Migration `0019_tieu_thu_va_menu_chuan_hoa`

Lập theo khuôn `0018` (sửa tại chỗ, có bảng backup `menu_mon_bak_0019` + `kv_tieu_thu_bak_0019`, `downgrade()` khôi phục, chạy lại vô hại):

1. **`menu_mon.bom`**: mọi khoá qua `ALIAS` → mã chuẩn (`cafe_g→ca_phe_hat`, `sua_ml→sua_tuoi`, `dao_lat→dao`). Gộp khoá trùng sau khi đổi (ví dụ `{cafe_g:18, ca_phe_hat:10}` → `{ca_phe_hat:28}`).
2. **`menu_mon.ten`**: tra `danh-muc.json` theo `id`, không khớp thì tra theo tên đã bỏ dấu; khớp được thì ghi lại tên có dấu.
3. **Ẩn món thừa** (`an=1`): id **không** nằm trong `danh-muc.json` **VÀ** (id khớp `^(fx_)?mon_` **HOẶC** tên mất dấu). *Tôi siết thêm 1 điều kiện so với phương án đã chốt:* chủ quán tự thêm món mới qua UI sẽ có id tuỳ ý + tên đủ dấu → **không bị ẩn nhầm**. Danh sách bị ẩn được ghi vào bảng backup để đối chiếu.
4. **Ẩn 8 món bao bì** `nhom='nguyen_lieu'` khỏi menu bán (`an=1`). Vẫn hiện ở `/menu` (chế độ `gom_an=True`) để chủ quán quản lý.
5. **Nạp 6 món bán chạy** nếu thiếu: `ca_phe_muoi` (Cà phê muối 35k), `tra_sua_tran_chau` (Trà sữa trân châu 42k), `sinh_to_bo` (Sinh tố bơ 48k), `banh_mi_chao` (Bánh mì chảo 45k), `nuoc_khoang` (Nước khoáng chai 15k), `da_xay_matcha` (Đá xay matcha 52k) — cả 6 **đã có** trong `danh-muc.json` với BOM + giá, chỉ cần chèn.
6. **`kv.tieu_thu`**: đọc JSON, bỏ dòng hỏng, chuẩn hoá mã/tên/đơn vị, khử trùng — cùng thuật toán với §2.1 (dùng chung 1 hàm để test được cả hai đầu).

> `persist._MENU_MAC_DINH` (6 món "Ca phe den" + BOM `cafe_g`) cũng phải viết lại theo danh mục chuẩn — nó là nguồn gốc tạo dữ liệu bẩn ở DB trống.

---

## 3. Web `/tieu-thu` — gộp theo nguyên liệu, có bộ lọc nhóm

Viết lại `apps/web/src/app/tieu-thu/page.tsx`, mượn khung của `/hao-phi` (đã có sẵn `nq-table` + `nq-list` responsive):

1. **Gộp** `items` → `Map<ma>`: `tong_so_luong`, `so_lan`, `don_vi`, `nhom`, danh sách `mon` đã dùng (unique theo `mon_id`).
2. **Bộ lọc nhóm** — chip `.nq-modebtn` như `/hao-phi`: `Tất cả · Cà phê · Trà & trà sữa · Sinh tố & đá xay · Bánh & ăn kèm · Nước đóng chai` (`NHOM_MON_THU_TU`, bỏ `nguyen_lieu`). Dùng `nhomMonLabel` có sẵn.
3. **`ListToolbar`** (đã có): tìm theo tên có dấu + `idPrefix="nq-tt"` (tránh trùng id với trang khác), lọc ngưỡng, lọc thời gian.
4. **Bảng md+ / danh sách mobile**: cột *Nguyên liệu · Tổng dùng · Số lần · Món liên quan · Ngưỡng*. Tên cột `font-bold` thường, **bỏ `font-mono` khỏi tên**; số giữ `font-mono`.
5. **Liên kết món**: `<Link href={"/menu#" + mon_id}>` cho từng món → đúng yêu cầu "liên kết với món ăn hiện tại".
6. **Chặn trang dài**: `SO_DONG_DAU = 50`, nút "Xem thêm 50 dòng"; `FilteredEmpty` khi lọc rỗng.
7. **Giữ nguyên** khu ghi kiểm kê (POST) và liên kết sang `/hao-phi`, `/menu`.
8. Đổi `PageHeader.title` → **"Tiêu thụ trong ca"** (e2e `flows.spec.ts:129` match `/Sổ kiểm kê|Tiêu thụ/i` nên **vẫn pass** — không cần sửa test).

---

## 4. Menu `/quay` + `/menu`

- `/quay`: nhờ §2.3-4, 8 món bao bì tự biến mất khỏi `GET /api/v1/menu`. Không sửa code `/quay` (nhóm `nguyen_lieu` vẫn là nhóm hợp lệ nên không cần đụng).
- `/menu` (sửa công thức): `BOM_INGREDIENTS` đủ 16 mã có dấu + đúng đơn vị (§1.2) → chủ quán sửa công thức không còn thấy "ca phe hat" hay thiếu `đường/sữa đặc/kem`.
- `tsc --noEmit` phải sạch, `next build` OK.

---

## 5. Kiểm chứng

| Lớp | Lệnh |
|---|---|
| Python unit | `python -m pytest apps/api/tests/unit/test_danh_muc_va_anh.py apps/api/tests/unit/test_pos_roles.py -q` + file mới `test_tieu_thu_sach.py` |
| Migration | Test idempotent + `downgrade()` khôi phục trên SQLite replica (mẫu 0018) |
| Web unit | `cd apps/web && npm test` (vitest, thêm `nguyen-lieu.test.ts`) |
| Kiểu | `python -m ruff check <file đã sửa>` · `mypy apps/api/src` (giữ 20 lỗi pre-existing) · `npx tsc --noEmit` |
| Build | `npm run build` + `prepare-standalone.mjs` |
| E2E | `npx playwright test e2e/flows.spec.ts e2e/hao-hut.spec.ts` |
| Tương tác | Script Playwright tự viết: `/tieu-thu` hiện tên có dấu, không còn ô trống, lọc nhóm hoạt động, gộp 1 dòng/nguyên liệu, bấm món ra `/menu`; `/quay` không còn nhóm "Nguyên liệu pha chế"; `/menu` đủ 16 mã |

---

## 6. Commit + push

- `fix(api): chuan hoa tieu-thu va menu, an mon khong co trong danh muc`
- `fix(web): gop tieu-thu theo nguyen lieu, loc nhom, day du tieng viet co dau`
- Rà `git status` chỉ chứa file đã định (48 file WIP cũ vẫn nằm trong `stash@{0}`, **không động tới**).
- `git fetch` → merge `origin/main` nếu cần → push (sẽ **kích hoạt deploy production**; migration 0019 chạy trên Postgres thật).

## 7. Rủi ro & giới hạn

- **Migration 0019 chưa từng chạy trên Postgres thật** — sẽ test kỹ trên SQLite replica + bảng backup có `downgrade()`.
- Ẩn món theo quy tắc có thể trúng món chủ quán tự đặt tên lạ — đã siết điều kiện (§2.3-3) và có backup để đối chiếu.
- Dữ liệu `kv.tieu_thu` trên production tôi **chưa nhìn thấy**; thuật toán dọn phải chịu được mọi hình dạng lạ (bỏ dòng hỏng thay vì đoán).
