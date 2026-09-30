import { expect, test } from "@playwright/test";
import { disableWebgl, loginAs } from "./_helpers";

/**
 * QUÁNVERSE — dữ liệu VẮNG MẶT.
 *
 * Yêu cầu gốc: "Không hiển thị '0' nếu thực tế chưa biết dữ liệu. Nếu chưa có
 * dữ liệu: '—' / 'Chưa có dữ liệu'. Không được biến thành số 0 giả."
 *
 * Bài này chặn MỌI nguồn dữ liệu của trang (kể cả nguồn mock/API) rồi khẳng
 * định không ô KPI nào hiện "0". Đây là bài chống hồi quy cho đúng lỗi mà bản
 * cũ mắc: `snap.zones?.length ?? 0` in ra "0" khi chưa tải xong.
 */

test.describe("QUÁNVERSE — không có dữ liệu", () => {
  test.beforeEach(async ({ page }) => {
    await disableWebgl(page);
    await loginAs(page);
  });

  test("API lỗi hết thì KPI hiện — chứ KHÔNG hiện 0", async ({ page }) => {
    // Chặn mọi lời gọi API của trang.
    await page.route("**/api/v1/**", (route) =>
      route.fulfill({ status: 503, contentType: "application/json", body: "{}" }),
    );

    await page.goto("/quanverse");
    await expect(page.getByTestId("quanverse-root")).toBeVisible({ timeout: 15_000 });

    // Trang phải render được, không sập.
    await expect(page.getByTestId("quanverse-kpis")).toBeVisible();

    const soO = page.locator('[data-co-du-lieu="0"]');
    await expect(soO.first()).toBeVisible();

    // MỌI ô KPI khi vắng dữ liệu phải là "—", tuyệt đối không "0".
    for (const key of ["staff", "zones", "orders", "queue", "alerts", "upcoming"]) {
      const cell = page.getByTestId(`kpi-${key}`);
      const text = (await cell.innerText()).trim();
      expect(text, `KPI ${key} lộ số 0 giả`).not.toBe("0");
      expect(text).toBe("—");
    }
  });

  test("mọi khối đều có trạng thái trống nói rõ, không để trống im lặng", async ({
    page,
  }) => {
    await page.route("**/api/v1/**", (route) =>
      route.fulfill({ status: 503, contentType: "application/json", body: "{}" }),
    );

    await page.goto("/quanverse");
    await expect(page.getByTestId("quanverse-root")).toBeVisible({ timeout: 15_000 });

    // Khối rỗng phải nói ra lý do.
    await expect(page.getByTestId("actions-empty")).toBeVisible();
    await expect(page.getByTestId("events-empty")).toBeVisible();
    // Chuỗi dự báo có HAI trạng thái trống hợp lệ, tuỳ nguồn:
    //  · "capacity-empty"     — không đọc được chuỗi nào (API lỗi hẳn)
    //  · "capacity-no-history"— đọc được chuỗi nhưng chưa đủ ngày dữ liệu
    // Cả hai đều phải nói rõ chưa có dữ liệu; TUYỆT ĐỐI không vẽ đường.
    const capEmpty = page.getByTestId("capacity-empty");
    const capNoHistory = page.getByTestId("capacity-no-history");
    const coMot = (await capEmpty.count()) + (await capNoHistory.count());
    expect(coMot, "khối dự báo phải có trạng thái trống").toBeGreaterThan(0);
    if (await capNoHistory.count()) {
      await expect(capNoHistory).toContainText("Chưa đủ dữ liệu lịch sử để dự báo");
    } else {
      await expect(capEmpty).toContainText("Chưa có dữ liệu");
    }
    await expect(page.getByTestId("copilot-empty")).toBeVisible();
  });

  test("nguồn lỗi được khai báo minh bạch", async ({ page }) => {
    await page.route("**/api/v1/**", (route) =>
      route.fulfill({ status: 503, contentType: "application/json", body: "{}" }),
    );

    await page.goto("/quanverse");
    await expect(page.getByTestId("quanverse-root")).toBeVisible({ timeout: 15_000 });

    await expect(page.getByTestId("source-degraded")).toBeVisible();
    await expect(page.getByTestId("quanverse-provenance")).toBeVisible();
  });

  test("dự báo không vẽ đường khi chưa đủ lịch sử", async ({ page }) => {
    await page.route("**/api/v1/**", (route) =>
      route.fulfill({ status: 503, contentType: "application/json", body: "{}" }),
    );

    await page.goto("/quanverse");
    await expect(page.getByTestId("quanverse-capacity")).toBeVisible({ timeout: 15_000 });
    // Có trạng thái trống (một trong hai biến thể) và KHÔNG vẽ svg dự báo.
    const capEmpty = page.getByTestId("capacity-empty");
    const capNoHistory = page.getByTestId("capacity-no-history");
    const coMot = (await capEmpty.count()) + (await capNoHistory.count());
    expect(coMot, "phải có trạng thái trống cho khối dự báo").toBeGreaterThan(0);
    // Không có SVG nào vẽ đường dự báo.
    await expect(page.locator(".nq-qvcap__chart")).toHaveCount(0);
  });

  test("chuỗi dự báo rỗng có lịch sử nhưng thiếu ngày ⇒ nói thẳng chưa đủ lịch sử", async ({
    page,
  }) => {
    // Hình dạng THẬT khi quán chưa có đơn: `co_du_lieu=false` nhưng `series`
    // vẫn đủ 16 giờ với nhu_cau = 0. Đây là ca nguy hiểm nhất — nếu UI vẽ đường
    // thì ra một đường phẳng 0 trông y như dữ liệu thật.
    //
    // THỨ TỰ ROUTE QUAN TRỌNG: Playwright khớp route ĐĂNG KÝ SAU CÙNG trước, nên
    // route CỤ THỂ phải đăng ký SAU route tổng `**/api/v1/**` — nếu không, route
    // tổng nuốt mất và bài test lại rơi vào nhánh "không đọc được chuỗi nào".
    await page.route("**/api/v1/**", (route) =>
      route.fulfill({ status: 503, contentType: "application/json", body: "{}" }),
    );
    await page.route("**/api/v1/experience/quanverse/forecast**", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          co_du_lieu: false,
          so_ngay_du_lieu: 0,
          series: Array.from({ length: 16 }, (_, i) => ({
            gio: i + 7,
            nhu_cau: 0,
            hang_doi_du_bao: 0,
          })),
          giao_dich_nhat: [],
          nguon: "chua_co_du_lieu",
        }),
      }),
    );

    await page.goto("/quanverse");
    await expect(page.getByTestId("capacity-no-history")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId("capacity-no-history")).toContainText(
      "Chưa đủ dữ liệu lịch sử để dự báo",
    );
    await expect(page.locator(".nq-qvcap__chart")).toHaveCount(0);
  });
});
