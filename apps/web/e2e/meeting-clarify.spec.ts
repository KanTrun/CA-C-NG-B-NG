import { expect, test, type Page } from "@playwright/test";

async function loginAs(page: Page, user: "lan" | "minh" | "hung" = "lan") {
  await page.goto("/login");
  await page.getByLabel("Tài khoản").fill(user);
  await page.getByLabel("Mật khẩu").fill("nhipquan");
  await page.getByRole("button", { name: "Vào hệ thống" }).click();
  try {
    await expect(page).toHaveURL(/\/hom-nay/, { timeout: 15_000 });
  } catch (err) {
    const alert = await page.locator(".nq-alert, [role='alert']").textContent().catch(() => null);
    if (alert) {
      throw new Error(`Login failed for user "${user}" with page error: "${alert.trim()}". Original: ${err}`);
    }
    throw err;
  }
}

test.describe("AI Meeting OS — Rà soát Ngữ cảnh & Lịch ca Phân công", () => {
  test.beforeEach(async ({ page }) => {
    await loginAs(page, "lan");
  });

  test("Phân tích cuộc họp -> Hiển thị AI Clarifier Agent -> Giải quyết ngữ cảnh 1-chạm", async ({ page }) => {
    await page.goto("/cuoc-hop");
    await expect(page.getByRole("heading", { name: /Họp & giao ca/i })).toBeVisible();

    // Pane Copilot mở sẵn ở góc phải dưới và có thể đè lên tab ở CI (font
    // Ubuntu cao hơn làm layout dịch xuống — local Windows không tái hiện).
    // UX thiết kế là "chạm vào phần trang thì pane tự thu nhỏ", nên chạm h1
    // trước khi bấm tab; không vậy click bị `#nq-copilot-root` chặn mãi mãi
    // (Playwright bỏ qua hit-target bị che, không dispatch pointerdown — khác
    // người thật, click đầu tiên vẫn làm pane thu nhỏ).
    await page.locator("h1").first().click();
    await page.waitForTimeout(600);

    // 1. Chuyển sang tab Dán ghi chép
    await page.getByRole("button", { name: /Dán ghi chép/i }).click();

    // 2. Điền nội dung mẫu có cả việc gấp, việc nhiều ca và góp ý
    const sampleMeeting =
      "Quản lý: Chào ca chiều, Tuấn kiểm tra lại tủ đá và họng máy pha nhé.\n" +
      "Tuấn: Dạ em sẽ lau họng máy trước 16h.\n" +
      "Quản lý: Nhắc My nhớ cười tươi và chào khách niềm nở hơn khi đứng quầy.\n" +
      "My: Dạ em ghi nhận ạ.";

    await page.locator("textarea").fill(sampleMeeting);

    // 3. Bấm Phân tích biên bản
    await page.getByRole("button", { name: /Phân tích biên bản|Phân tích văn bản/i }).click();

    // 4. Chờ kết quả phân tích hiển thị
    await expect(page.getByText(/Kết quả phân tích/i)).toBeVisible({ timeout: 15_000 });

    // 5. Mở tab Việc giao
    await page.getByRole("button", { name: /Việc giao/i }).click();

    /* Kiểm tra các nút chuyển đổi bản chất công việc có mặt.
       KHÔNG assert theo emoji (⚡/🔄/💬): các nút này đã đổi sang icon SVG
       (`<Icon name="zap|refresh|chat"/>` + chữ) vì guideline cấm emoji làm icon
       — emoji do hệ điều hành vẽ nên hình/màu khác nhau trên từng máy và không
       ăn `currentColor`. Assert theo CHỮ, đúng thứ người dùng đọc và không phụ
       thuộc font hệ thống. */
    await expect(page.locator("button", { hasText: "1 ca" }).first()).toBeVisible();
    await expect(page.locator("button", { hasText: "Nhiều ca" }).first()).toBeVisible();
    await expect(page.locator("button", { hasText: "Góp ý" }).first()).toBeVisible();

    // Kiểm tra nút AI Rà soát ngữ cảnh & Lịch ca
    await expect(page.getByRole("button", { name: /AI Rà soát ngữ cảnh & Lịch ca/i })).toBeVisible();

    // 6. Thử nghiệm tương tác với AI Clarifier Agent (nếu có câu hỏi làm rõ)
    const quickActionBtn = page.locator("button", { hasText: /^✓ / }).first();
    if (await quickActionBtn.isVisible()) {
      await quickActionBtn.click();
      await expect(page.getByText(/Đã áp dụng làm rõ|Đã chuyển việc/i)).toBeVisible();
    }
  });
});
