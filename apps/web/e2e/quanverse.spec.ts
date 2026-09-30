import { expect, test, type Page } from "@playwright/test";
import { disableWebgl, loginAs, resetExperienceState } from "./_helpers";

/** QUANVERSE e2e — role projection, mode confirm, flavor, AR fallback. */

test.describe("QUANVERSE", () => {
  test.beforeEach(async ({ page }) => {
    await disableWebgl(page);
    await loginAs(page);
    // Dọn ở ĐẦU mỗi bài, không phải cuối: dọn ở cuối không bảo vệ được chính bài
    // đó, và nếu bài trước rơi giữa chừng thì bước dọn không bao giờ chạy. Bài
    // "manager walks mode propose -> confirm -> deactivate" kết thúc bằng cách
    // BẬT mode `dem_nhac`; bài đó chạy lại sẽ không thấy nút propose (đã active)
    // nên khẳng định `is-active` rơi vào trạng thái phụ thuộc thứ tự chạy.
    await resetExperienceState(page);
    await page.goto("/quanverse");
  });

  test("living map renders zones and events", async ({ page }) => {
    await expect(page.locator(".nq-living-map")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId("zone-bar")).toBeVisible();
    await expect(page.locator(".nq-quanverse__events")).toBeVisible();
    // Chú giải mức tải nằm NGAY TRÊN mặt bằng — `nq-loadbar__key` (ô màu Nhẹ/Vừa/
    // Tải cao) mới là thứ luôn hiện khi mở trang.
    //
    // KHÔNG assert `nq-loadbar__fill` ở đây: cột fill nằm trong `ZoneDetail`, chỉ
    // mount SAU khi người dùng bấm một khu vực. Assert nó ngay sau khi mở trang
    // là đòi một phần tử chưa tồn tại — và đã làm đỏ CI thật.
    await expect(page.locator(".nq-loadbar__key").first()).toBeVisible();
  });

  test("events link to zones and store-wide events say so", async ({ page }) => {
    await expect(page.getByTestId("quanverse-events")).toBeVisible({ timeout: 15_000 });
    // Sự kiện gắn khu vực: bấm chip phải mở đúng bảng chi tiết khu vực đó.
    const zoneChip = page.locator(".nq-zonechip").first();
    await expect(zoneChip).toBeVisible();
    await zoneChip.click();
    await expect(page.locator(".nq-zone-detail")).toBeVisible({ timeout: 10_000 });
    // Sự kiện không thuộc khu vực nào phải nói thẳng là toàn quán.
    await expect(page.locator(".nq-zonechip--none").first()).toBeVisible();
    await expect(page.locator(".nq-zonechip--none").first()).toContainText("Toàn quán");
  });

  test("role switch (replay) changes projection", async ({ page }) => {
    await expect(page.locator(".nq-living-map")).toBeVisible({ timeout: 15_000 });
    // Switch sang khách → không còn sự kiện staff.
    await page.getByTestId("role-khach").click();
    await expect(page.getByText(/Không có sự kiện vận hành cho bản chiếu này/)).toBeVisible({ timeout: 10_000 });
  });

  test("bỏ đề xuất thì không hiện lại nút Duyệt", async ({ page }) => {
    // Lỗi thật đã vấp: fixture khai `khach_doan` là `draft`. Sau khi bỏ đề xuất,
    // kv không còn `proposal_status`, và bản cũ rơi về giá trị của FIXTURE nên
    // UI vẫn hiện "Chờ duyệt" kèm nút Duyệt cho đề xuất vừa bị bỏ.
    await expect(page.locator(".nq-moderail")).toBeVisible({ timeout: 15_000 });
    const mode = "khach_doan";
    const item = page.getByTestId(`mode-item-${mode}`);
    await expect(item).toBeVisible();

    // Fixture khai sẵn draft → nút Duyệt phải đang hiện.
    await expect(page.getByTestId(`mode-confirm-${mode}`)).toBeVisible();

    await page.getByTestId(`mode-drop-${mode}`).click();

    // Bỏ rồi: KHÔNG còn nút Duyệt, và trạng thái phải là "Đang tắt".
    await expect(page.getByTestId(`mode-confirm-${mode}`)).toHaveCount(0, { timeout: 10_000 });
    await expect(item).not.toHaveClass(/is-waiting/);
    await expect(page.getByTestId(`mode-propose-${mode}`)).toBeVisible();
  });

  test("mode removed from kv does not reset to fixture state", async ({ page }) => {
    // Trạng thái mode đọc từ kv khi CÓ bản ghi, kể cả khi `proposal_status` rỗng
    // (rỗng = đã bỏ, khác hẳn chưa từng đề xuất). Đây là bất biến chống hồi sinh.
    await expect(page.locator(".nq-moderail")).toBeVisible({ timeout: 15_000 });
    const mode = "khach_doan";
    await page.getByTestId(`mode-drop-${mode}`).click();
    await expect(page.getByTestId(`mode-confirm-${mode}`)).toHaveCount(0, { timeout: 10_000 });

    // Tải lại trang: máy chủ phải trả CÙNG trạng thái (đã bỏ), không phải fixture.
    await page.reload();
    await expect(page.locator(".nq-moderail")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId(`mode-confirm-${mode}`)).toHaveCount(0, { timeout: 10_000 });
  });

  test("chọn khu vực mở bảng chi tiết", async ({ page }) => {
    await expect(page.locator(".nq-living-map")).toBeVisible({ timeout: 15_000 });
    await page.getByTestId("zone-bar").click();
    const detail = page.locator(".nq-zone-detail");
    await expect(detail).toBeVisible({ timeout: 10_000 });
    await expect(page.getByTestId("zone-bar")).toHaveAttribute("aria-pressed", "true");
    // Bấm lại khu vực khác thì bảng chi tiết đổi theo, không chồng hai bảng.
    await page.getByTestId("zone-cashier").click();
    await expect(page.locator(".nq-zone-detail")).toHaveCount(1);
    await expect(page.getByTestId("zone-cashier")).toHaveAttribute("aria-pressed", "true");
    // Nút đóng trả về trạng thái gợi ý chọn khu vực.
    await page.locator(".nq-zdetail__close").click();
    await expect(page.locator(".nq-zone-detail")).toHaveCount(0);
  });

  test("manager walks mode propose -> confirm -> deactivate", async ({ page }) => {
    await expect(page.locator(".nq-moderail")).toBeVisible({ timeout: 15_000 });

    // Bật một chế độ rồi phải TẮT được — trước đây vòng đời một chiều.
    const mode = "dem_nhac";
    const item = page.getByTestId(`mode-item-${mode}`);
    await expect(item).toBeVisible();

    const propose = page.getByTestId(`mode-propose-${mode}`);
    if (await propose.isVisible().catch(() => false)) {
      await propose.click();
      await expect(page.getByTestId(`mode-confirm-${mode}`)).toBeVisible({ timeout: 10_000 });
    }

    const confirm = page.getByTestId(`mode-confirm-${mode}`);
    if (await confirm.isVisible().catch(() => false)) {
      await confirm.click();
    }
    await expect(item).toHaveClass(/is-active/, { timeout: 10_000 });
    await expect(page.locator(".nq-switch.is-on").first()).toBeVisible();

    await page.getByTestId(`mode-deactivate-${mode}`).click();
    await expect(item).not.toHaveClass(/is-active/, { timeout: 10_000 });
  });

  test("flavor recommendation with reasons", async ({ page }) => {
    await expect(page.locator(".nq-flavor")).toBeVisible({ timeout: 15_000 });
    await page.getByTestId("flavor-ngot-it").click();
    await page.getByTestId("flavor-sua").uncheck();
    await page.getByTestId("flavor-go").click();
    await expect(page.getByTestId("flavor-results").first()).toBeVisible({ timeout: 10_000 });
    // Mỗi gợi ý có điểm số trực quan + lý do, không chỉ tên món.
    await expect(page.locator(".nq-flavor__meter-fill").first()).toBeVisible();
    await expect(page.locator(".nq-flavor__reasons li").first()).toBeVisible();
  });

  test("preference reaches stored via consent", async ({ page }) => {
    // Bản trước chỉ có nhánh xoá — không có đường đồng ý, nên không lưu được.
    await expect(page.locator(".nq-pref")).toBeVisible({ timeout: 15_000 });
    await page.getByTestId("pref-input").fill("thích bàn cạnh cửa sổ yên tĩnh");
    await page.getByTestId("pref-propose").click();

    const grant = page.getByTestId("pref-grant");
    await expect(grant).toBeVisible({ timeout: 10_000 });
    await grant.click();

    await expect(page.getByTestId("pref-stored")).toBeVisible({ timeout: 10_000 });
    await expect(page.getByTestId("pref-stored")).toContainText("thích bàn cạnh cửa sổ yên tĩnh");

    // Không cần dọn ở đây: `beforeEach` gọi `resetExperienceState` ở ĐẦU mỗi bài,
    // nên bài sau luôn bắt đầu từ trạng thái fixture dù bài này có rơi giữa chừng.
    // Bản trước dọn ở cuối — cách đó không bảo vệ được bài đang chạy, và đã để lại
    // 8 bản sở thích trùng trong kv qua nhiều lần chạy.
  });

  test("ar-lite fallback path", async ({ page }) => {
    await expect(page.locator(".nq-ar")).toBeVisible({ timeout: 15_000 });
    await page.getByTestId("ar-qr").fill("blender-02");
    await page.getByTestId("ar-start").click();
    const result = page.getByTestId("ar-result");
    await expect(result).toBeVisible({ timeout: 10_000 });
    // Mã nội bộ không được in lên UI — vẫn truy vết được qua data-attribute.
    await expect(result).toHaveAttribute("data-fallback", "map_or_qr_text");
    await expect(result).not.toContainText("map_or_qr_text");
    await expect(page.locator(".nq-ar__anchorbox")).toBeVisible();
  });
});