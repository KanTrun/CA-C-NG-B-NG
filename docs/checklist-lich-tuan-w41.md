# Checklist tự kiểm lịch tuần W41 (< 5 phút)

Bộ fixture **4 NV + tuần `2026-W41`** — không cần 19 người.

## Chuẩn bị

```bash
python3 scripts/seed_mini_w41_roster.py
# hoặc POST /api/v1/lich-tuan/demo-mini-w41 (đăng nhập lan)
```

## Bước

1. Mở `/lich-tuan?tuan=2026-W41`
2. Khối **«Tuần 2026-W41 đang ở đâu»** hiện trạng thái + việc kế tiếp
3. Bấm **«Xếp lịch tự động»**
   - Thành công → thông báo + panel nhật ký cập nhật
   - Thất bại → lý do tiếng Việt (thiếu người / TKB), không im
4. Panel **«Ai đổi ca với ai»** mở sẵn (không cần mở `<details>`)
5. Công bố lịch → `/doi-ca` tạo phiếu `nv_01` nhường `w1_c01` cho `nv_03` → QL duyệt
6. Quay lại `/lich-tuan?tuan=2026-W41` → nhật ký có dòng **A → B · nguồn Chợ đổi ca**

## Tự động

```bash
CA_AGENT_MODE=replay python3 -m pytest apps/api/tests/unit/test_mini_w41_fixture.py -q
# e2e (cần web + API):
npx playwright test apps/web/e2e/lich-tuan-nhat-ky.spec.ts
```
