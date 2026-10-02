import { expect, test, type Page } from "@playwright/test";
import { ensureDemoData, loginAs } from "./_helpers";

/**
 * Hồi quy cho chuẩn hoá `/tieu-thu` + menu (kế hoạch
 * `plans/261002-tieu-thu-va-menu-chuan-hoa.md` §5).
 *
 * Bốn điều người dùng từng thấy và nay phải đúng:
 *  1. Sổ tiêu thụ một dòng / một nguyên liệu, tên tiếng Việt có dấu, đơn vị
 *     thật — không còn ô trống, không còn "ca phe hat", không còn "42 đơn vị".
 *  2. Lọc theo nhóm hoạt động, và bấm món liên quan mở `/menu` đúng món đó.
 *  3. Quầy không còn bán 8 món bao bì nhóm `nguyen_lieu`.
 *  4. Sửa công thức liệt kê đủ mã nguyên liệu có dấu.
 *
 * Chưa thêm `@smoke` nên CI (`npx playwright test --grep @smoke`) không chạy —
 * chạy tay khi sửa khu vực này: `npx playwright test e2e/tieu-thu-chuan-hoa.spec.ts`.
 */

const API = process.env.NQ_API ?? "http://127.0.0.1:8000";

/** Nạp dữ liệu demo (có `tieu_thu` thật) rồi đăng nhập vai trò cần kiểm. */
async function taoDuLieu(page: Page, user: "lan" | "minh" | "hung") {
  await loginAs(page, user);
  await ensureDemoData(page);
}

test.describe("/tieu-thu sau chuẩn hoá", () => {
  test("tên có dấu, không ô trống, một dòng / nguyên liệu", async ({ page }) => {
    await taoDuLieu(page, "lan");
    await page.goto("/tieu-thu");

    await expect(page.getByRole("heading", { name: "Tiêu thụ trong ca", exact: true })).toBeVisible();

    const rows = page.locator(".nq-table tbody tr[data-ma]");
    const soDong = await rows.count();
    expect(soDong, "demo-setup phải ghi được dòng tieu_thu để có cái mà kiểm").toBeGreaterThan(0);

    const ma: string[] = [];
    const ten: string[] = [];
    for (let i = 0; i < soDong; i += 1) {
      ma.push((await rows.nth(i).getAttribute("data-ma")) ?? "");
      ten.push(((await rows.nth(i).locator("th[scope='row']").first().textContent()) ?? "").trim());
    }

    // Gộp theo nguyên liệu: không còn 6 dòng của cùng "Cà phê hạt".
    expect(new Set(ma).size, `trùng mã: ${ma.join(", ")}`).toBe(soDong);

    for (let i = 0; i < ten.length; i += 1) {
      expect(ten[i], `ô trống ở dòng ${i}`).not.toBe("");
      // Tên còn là MÃ BOM ("ca_phe_hat") = dữ liệu chưa dịch sang tiếng Việt.
      expect(ten[i], `dòng ${i} vẫn là mã: ${ten[i]}`).not.toMatch(/^[a-z]+_[a-z_]+$/);
      // Ba từ latin liên tiếp không dấu ⇒ nhiều khả năng là tên mất dấu.
      expect(ten[i], `dòng ${i} mất dấu: ${ten[i]}`).not.toMatch(/[a-z] [a-z] [a-z]/);
    }

    const donVi = await page.locator(".nq-table tbody tr[data-ma] th[scope='row'] span").allTextContents();
    expect(donVi.join(" | "), "đơn vị mặc định 'đơn vị' là lỗi đã sửa").not.toContain("đơn vị");
  });

  test("lọc nhóm và bấm món liên quan ra /menu", async ({ page }) => {
    // `hung` (chủ quán) vì `/menu` bị chặn với `lan` — link từ `/tieu-thu` sang
    // cũng phải chịu đúng luật phân quyền đó.
    await taoDuLieu(page, "hung");
    await page.goto("/tieu-thu");
    await expect(page.locator(".nq-table tbody tr[data-ma]").first()).toBeVisible();

    const chip = page.getByRole("button", { name: "Cà phê", exact: true });
    await expect(chip).toBeVisible();
    await chip.click();
    await expect(chip).toHaveAttribute("aria-pressed", "true");

    const nhom = await page.locator(".nq-table tbody tr[data-ma]").evaluateAll((els) =>
      els.map((e) => e.getAttribute("data-nhom")),
    );
    expect(nhom.length).toBeGreaterThan(0);
    expect(nhom.every((n) => n === "ca_phe"), `lọc nhóm sai: ${JSON.stringify(nhom)}`).toBe(true);

    // Về "Tất cả" rồi bấm một món → sang `/menu` và mở đúng món đó.
    await page.getByRole("button", { name: "Tất cả", exact: true }).click();
    const link = page.locator(".nq-table tbody a[href^='/menu#']").first();
    const href = (await link.getAttribute("href")) ?? "";
    expect(href.startsWith("/menu#"), `link sai: ${href}`).toBe(true);
    await link.click();

    await expect(page).toHaveURL(/\/menu#/);
    const id = href.split("#")[1];
    await expect(page.locator(`#${id}`)).toBeVisible();
    await expect(page.getByText("Sửa món", { exact: true })).toBeVisible();
  });
});

test.describe("/quay và /menu sau chuẩn hoá", () => {
  test("quay không còn bán món bao bì", async ({ page }) => {
    // Kiểm ở API trước: đây là luật thật (`GET /api/v1/menu` chỉ trả `an=1`),
    // còn khối menu trên UI chỉ render được khi quầy mở (điểm danh + có ca).
    const login = await page.request.post(`${API}/api/v1/auth/login`, {
      data: { username: "minh", password: "nhipquan" },
    });
    expect(login.ok()).toBe(true);
    const { token } = (await login.json()) as { token: string };
    const res = await page.request.get(`${API}/api/v1/menu`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(res.ok()).toBe(true);
    const { items } = (await res.json()) as { items: Array<{ id: string; nhom?: string }> };
    const nhomBan = [...new Set(items.map((m) => m.nhom ?? ""))];
    expect(nhomBan, "nhóm bán sỉ không được lọt vào menu quầy").not.toContain("nguyen_lieu");
    for (const id of ["goi_ca_phe_250", "bi_da_2kg", "bich_ly_50"]) {
      expect(items.map((m) => m.id), `${id} vẫn đang bán trên quầy`).not.toContain(id);
    }

    // Xác nhận thêm ở UI khi quầy mở được.
    await loginAs(page, "minh");
    await page.goto("/quay");
    const diemDanh = page.getByRole("button", { name: /Điểm danh để mở quầy/ });
    if (await diemDanh.count()) await diemDanh.click();
    const nhomUi = await page.locator("h3.nq-pos-nhom__ten").allTextContents();
    expect(nhomUi).not.toContain("Nguyên liệu pha chế");
  });

  test("menu sửa công thức có đủ mã nguyên liệu có dấu", async ({ page }) => {
    await loginAs(page, "hung");
    await page.goto("/menu");
    await expect(page.locator("button.nq-menu-card").first()).toBeVisible();
    await page.locator("button.nq-menu-card").first().click();

    const select = page.locator("select#bom-ing-0");
    await expect(select).toBeVisible();
    const opts = await select.locator("option").allTextContents();

    // 16 mã trong `data/seed/danh-muc.json` + ô trống + "Nguyên liệu khác…".
    expect(opts.length).toBeGreaterThanOrEqual(17);
    expect(opts).toContain("Cà phê hạt");
    expect(opts).toContain("Đường");
    expect(opts).toContain("Sữa đặc");
    // Mã legacy (`cafe_g`) và mã thô không còn trong danh sách chọn.
    expect(opts.join("|")).not.toContain("cafe_g");
    expect(opts.some((o) => /^[a-z]+_[a-z_]+$/.test(o))).toBe(false);
  });
});
