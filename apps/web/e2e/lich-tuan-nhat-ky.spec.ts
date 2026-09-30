import { expect, test } from "@playwright/test";

/**
 * Panel nhật ký mở sẵn + khối trạng thái tuần trên /lich-tuan.
 * Không phụ thuộc solver thật — mock API thay-doi + lich-tuan.
 */
test("lịch tuần: nhật ký mở sẵn, filter, khối trạng thái chốt/bận gấp", async ({ page }) => {
  const week = "2026-W41";

  await page.route("**/api/v1/lich-tuan/thay-doi**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        tuan_iso: week,
        so_ban_ghi: 1,
        items: [
          {
            luc: "2026-10-06T08:00:00Z",
            nguon: "doi_ca",
            tuan_iso: week,
            tom_tat: "1 ca đổi người.",
            diff: {
              them: [],
              bot: [],
              hoan_doi: [
                {
                  ca: {
                    ca_id: "w1_c01",
                    thu: "T2",
                    khung: "sang",
                    gio: "07:00-12:00",
                  },
                  ra: [{ nv_id: "nv_01", ten: "Lan" }],
                  vao: [{ nv_id: "nv_03", ten: "Minh" }],
                },
              ],
              doi_giua_hai_ca: [],
              giu_nguyen: 0,
              khong_so_sanh_duoc: false,
            },
          },
        ],
      }),
    });
  });

  await page.route("**/api/v1/lich-tuan?**", async (route) => {
    const url = new URL(route.request().url());
    if (url.searchParams.get("tuan") === week || !url.searchParams.get("tuan")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          tuan_iso: week,
          danh_sach_tuan: [week],
          trang_thai: "da_cong_bo",
          phan_cong: { w1_c01: ["nv_03", "nv_02"] },
          ca: [
            {
              id: "w1_c01",
              thu: "T2",
              khung: "sang",
              bat_dau: "07:00",
              ket_thuc: "12:00",
              so_nguoi_toi_thieu: 2,
            },
          ],
          nhan_vien: [
            { id: "nv_01", ten: "Lan" },
            { id: "nv_02", ten: "Hùng" },
            { id: "nv_03", ten: "Minh" },
          ],
          open_shifts: [
            {
              id: "os1",
              ca_id: "w1_c02",
              tuan_iso: week,
              status: "open",
            },
          ],
          schedule_run: {
            id: "run-w41",
            status: "computed",
            fingerprint: "fp",
          },
          pins: [],
          kiem_tra: { coverage: { filled: 1, total: 21 } },
        }),
      });
    } else {
      await route.continue();
    }
  });

  await page.goto("/login");
  await page.getByLabel("Tài khoản").fill("lan");
  await page.getByLabel("Mật khẩu").fill("nhipquan");
  await page.getByRole("button", { name: "Vào hệ thống" }).click();
  await expect(page).toHaveURL(/\/hom-nay/, { timeout: 15_000 });

  await page.goto(`/lich-tuan?tuan=${week}`);
  await expect(page.getByText("1. Chuẩn bị lịch", { exact: true })).toBeVisible({
    timeout: 10_000,
  });

  // Khối trạng thái — không chôn trong details.
  await expect(page.getByText(`Tuần ${week} đang ở đâu`)).toBeVisible();
  await expect(page.getByText(/Đã chốt/)).toBeVisible();
  await expect(page.getByText(/ca mở/)).toBeVisible();

  // Nhật ký mở sẵn (không cần bấm summary).
  const journal = page.locator('[data-panel="nhat-ky-doi-ca"]');
  await expect(journal).toBeVisible();
  await expect(journal.getByText(/Ai đổi ca với ai/)).toBeVisible();
  // Scope vào article — panel còn khối "Hôm nay nhanh" cũng có .nq-shiftdiff__out
  // (Lan xuất hiện 2 lần → strict mode nếu query cả journal).
  const entry = journal.getByRole("article").first();
  await expect(entry.locator(".nq-shiftdiff__out").filter({ hasText: "Lan" })).toBeVisible();
  await expect(entry.locator(".nq-shiftdiff__in").filter({ hasText: "Minh" })).toBeVisible();
  await expect(journal.getByLabel("Lọc theo loại thay đổi")).toBeVisible();
});
