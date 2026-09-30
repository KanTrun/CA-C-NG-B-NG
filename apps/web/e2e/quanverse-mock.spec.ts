import { expect, test } from "@playwright/test";
import { disableWebgl, loginAs } from "./_helpers";

/**
 * QUÁNVERSE — chế độ MÔ PHỎNG.
 *
 * Chốt ba điều:
 *  1. Bật mô phỏng thì màn hiện đủ dữ liệu (kể cả khi API thật rỗng).
 *  2. Nhãn "Mô phỏng" + tên kịch bản LUÔN hiện — mock không bao giờ giả làm số thật.
 *  3. Đổi kịch bản thì số liệu đổi theo (mock thật sự có ba trạng thái khác nhau).
 *
 * Bộ chọn nguồn chỉ tồn tại ngoài production (`mockChoPhep()`), nên bài này chạy
 * trên bản build e2e (NODE_ENV=production nhưng có `NEXT_PUBLIC_QUANVERSE_DEMO`).
 */

test.describe("QUÁNVERSE — mô phỏng", () => {
  test.beforeEach(async ({ page }) => {
    await disableWebgl(page);
    await loginAs(page);
  });

  test("bật mô phỏng thì hiện nhãn và kịch bản", async ({ page }) => {
    await page.goto("/quanverse");
    await expect(page.getByTestId("quanverse-root")).toBeVisible({ timeout: 15_000 });

    const toggle = page.getByTestId("toggle-source");
    // Nếu bộ chọn không có (bản production thuần), bài này bỏ qua thay vì đỏ.
    test.skip((await toggle.count()) === 0, "Bộ chọn nguồn tắt ở môi trường này");

    await toggle.click();
    await expect(page.getByTestId("quanverse-source")).toHaveAttribute("data-nguon", "mock");
    await expect(page.getByTestId("source-badge")).toContainText("Mô phỏng");
    await expect(page.getByTestId("source-scenario")).toBeVisible();
  });

  test("timeline có badge Dữ liệu mô phỏng", async ({ page }) => {
    await page.goto("/quanverse");
    const toggle = page.getByTestId("toggle-source");
    test.skip((await toggle.count()) === 0, "Bộ chọn nguồn tắt ở môi trường này");

    await toggle.click();
    await expect(page.getByTestId("quanverse-timeline")).toBeVisible();
    await expect(page.getByTestId("timeline-mock-badge")).toContainText("Dữ liệu mô phỏng");
  });

  test("đổi kịch bản thì số liệu đổi theo", async ({ page }) => {
    await page.goto("/quanverse");
    const toggle = page.getByTestId("toggle-source");
    test.skip((await toggle.count()) === 0, "Bộ chọn nguồn tắt ở môi trường này");

    await toggle.click();
    await expect(page.getByTestId("quanverse-root")).toBeVisible();

    // Kịch bản "Quầy pha quá tải" phải cho tải cao ở quầy pha...
    await page.getByTestId("scenario-qua_tai_pha").click();
    await expect(page.getByTestId("qv-zone-quay_pha")).toHaveAttribute(
      "data-trang-thai",
      "qua_tai",
    );
    const taiCao = await page.getByTestId("kpi-orders").innerText();

    // ...còn "Ca thường" thì không.
    await page.getByTestId("scenario-binh_thuong").click();
    await expect(page.getByTestId("qv-zone-quay_pha")).toHaveAttribute(
      "data-trang-thai",
      "on_dinh",
    );
    const taiThap = await page.getByTestId("kpi-orders").innerText();

    expect(taiCao).not.toEqual(taiThap);
  });

  test("mock KPI không bao giờ là 0 giả — mọi ô số đều có giá trị hoặc —", async ({
    page,
  }) => {
    await page.goto("/quanverse");
    const toggle = page.getByTestId("toggle-source");
    test.skip((await toggle.count()) === 0, "Bộ chọn nguồn tắt ở môi trường này");

    await toggle.click();
    await expect(page.getByTestId("quanverse-kpis")).toBeVisible();

    for (const key of ["staff", "zones", "orders", "queue", "alerts", "upcoming"]) {
      const cell = page.getByTestId(`kpi-${key}`);
      const text = (await cell.innerText()).trim();
      // Hoặc là một con số, hoặc là "—" — không bao giờ rỗng.
      expect(text.length, `KPI ${key} rỗng`).toBeGreaterThan(0);
      expect(text === "—" || /^\d/.test(text), `KPI ${key} = "${text}"`).toBe(true);
    }
  });
});
