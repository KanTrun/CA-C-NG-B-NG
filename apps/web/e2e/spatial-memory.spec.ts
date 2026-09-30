import { expect, test } from "@playwright/test";
import { disableWebgl, loginAs, resetExperienceState } from "./_helpers";

/** HỒN QUÁN Spatial Memory e2e — replay fixture, WebGL-off, no mạng LLM. */

test.describe("Hon Quan Spatial Memory", () => {
  test.beforeEach(async ({ page }) => {
    // Tắt WebGL để test 2D fallback.
    await disableWebgl(page);
    await loginAs(page);
    // Tệp này trước đây KHÔNG dọn gì cả. Đo được hệ quả: bài "memory consent
    // grant and remove" cấp consent rồi xoá một ký ức, và bài "voice turn
    // grounded answer" tạo thêm một draft; cả hai thay đổi nằm trong kho ký ức
    // TOÀN CỤC sống suốt phiên server. Chạy cả bộ thì bài "anchor select shows
    // details" ở chính tệp này đỏ (sơ đồ vẽ ra cao hơn khung), chạy riêng tệp
    // thì xanh — thứ tự chạy quyết định kết quả.
    await resetExperienceState(page);
    await page.goto("/quanverse/spatial-memory");
  });

  test("anchor select shows details and confirmed memories", async ({ page }) => {
    await expect(page.locator(".nq-map2d")).toBeVisible({ timeout: 15_000 });

    // Mọi neo phải nằm TRONG khung vẽ — bản trước chiếu sai nên neo rơi ra ngoài
    // viewBox và bản đồ trông rỗng dù API trả đủ dữ liệu.
    const svgBox = await page.locator(".nq-map2d__svg").boundingBox();
    expect(svgBox).not.toBeNull();
    const anchorCount = await page.locator(".nq-map2d__anchor").count();
    expect(anchorCount).toBeGreaterThan(0);
    for (let i = 0; i < anchorCount; i++) {
      const box = await page.locator(".nq-map2d__anchor").nth(i).boundingBox();
      expect(box).not.toBeNull();
      if (!box || !svgBox) continue;
      expect(box.y).toBeGreaterThanOrEqual(svgBox.y - 2);
      expect(box.y + box.height).toBeLessThanOrEqual(svgBox.y + svgBox.height + 2);
    }

    // Anchor đầu auto-select → chi tiết hiện.
    await expect(page.locator(".nq-anchor")).toBeVisible({ timeout: 10_000 });

    // Anchor thứ 2: Enter phải đổi được lựa chọn (SVG g có onKeyDown).
    const second = page.locator(".nq-map2d__anchor").nth(1);
    const secondId = await second.getAttribute("data-anchor");
    await second.focus().catch(() => undefined);
    await page.keyboard.press("Enter");
    await expect(page.locator(".nq-anchor")).toBeVisible({ timeout: 10_000 });
    await expect(page.locator(".nq-map2d__anchor.is-selected")).toHaveAttribute(
      "data-anchor",
      secondId ?? "",
    );
  });

  test("3D toggle available when the machine can run WebGL", async ({ page }) => {
    // Fallback 2D luôn có; nút chuyển chỉ hiện khi máy thật sự chạy được WebGL.
    const toggle = page.getByTestId("spatial-map-toggle");
    const has3d = await toggle.isVisible().catch(() => false);
    if (!has3d) {
      // Không có WebGL (đúng với cấu hình test này) → phải là sơ đồ 2D, không trắng.
      await expect(page.locator(".nq-map2d")).toBeVisible();
      return;
    }
    await toggle.click();
    await expect(page.getByTestId("spatial-3d")).toBeVisible({ timeout: 15_000 });
  });

  test("voice turn grounded answer and remember proposal", async ({ page }) => {
    await expect(page.locator(".nq-map2d")).toBeVisible({ timeout: 15_000 });

    // Hỏi grounded về bar (default selected là anchor đầu).
    await page.getByTestId("voice-input").fill("khách thích gì ở quầy pha chế?");
    await page.getByTestId("voice-ask").click();
    const resp = page.getByTestId("voice-response");
    await expect(resp).toBeVisible({ timeout: 10_000 });
    await expect(resp).toContainText("ký ức đã xác nhận");

    // Nhớ điều này → đề xuất memory (không lộ mã nội bộ trên UI).
    await page.getByTestId("voice-input").fill("nhớ điều này: khách đoàn thích ngồi gần cửa sổ");
    await page.getByTestId("voice-ask").click({ force: true });
    await expect(page.locator(".nq-voicedock__proposal")).toBeVisible({ timeout: 10_000 });
    await expect(resp).not.toContainText("vp_");
  });

  test("memory consent grant and remove are reachable", async ({ page }) => {
    // Trước đây ký ức chờ duyệt treo vĩnh viễn: API có consent + delete nhưng
    // không UI nào gọi.
    await expect(page.locator(".nq-anchor")).toBeVisible({ timeout: 15_000 });
    await expect(page.locator(".nq-anchor__subhead").first()).toBeVisible();

    const grant = page.getByTestId(/^mem-grant-/).first();
    if (await grant.isVisible().catch(() => false)) {
      await grant.click();
      await expect(page.locator(".nq-pref__notice").first()).toBeVisible({ timeout: 10_000 });
    }
    // Không có ký ức chờ thì nhánh empty state phải nói thẳng, không để trống.
    // ExpEmpty dùng kit Empty → class `.nq-empty`.
    const emptyOrList = page.locator("[data-testid='pending-memories'], .nq-empty");
    await expect(emptyOrList.first()).toBeVisible();
  });

  test("propose form creates a reviewable draft at the anchor", async ({ page }) => {
    // Luồng trước đây gãy: endpoint /memories/propose có từ Phase 05 nhưng
    // không UI nào gọi — muốn ghi nhớ chỉ có đường gõ "nhớ điều này…" vào
    // hộp voice. Form ở khung chi tiết neo nối đủ đường còn lại.
    await expect(page.locator(".nq-anchor")).toBeVisible({ timeout: 15_000 });

    const input = page.getByTestId("memory-propose-input");
    await input.fill("khách quen hay nhờ giữ hộ bình giữ nhiệt");
    await page.getByTestId("memory-propose-send").click();

    // Draft mới phải hiện ngay trong "Chờ quyết định" — không cần F5.
    await expect(page.getByTestId("pending-memories")).toBeVisible({ timeout: 10_000 });
    await expect(page.getByTestId("pending-memories")).toContainText(
      "khách quen hay nhờ giữ hộ bình giữ nhiệt",
    );

    // Duyệt luôn cho trọn chuỗi: đề xuất → đồng ý → nằm ở "Ký ức đã xác nhận".
    //
    // Phải nhắm ĐÚNG bản nháp vừa tạo, không dùng `.first()`: fixture đã có sẵn
    // một draft khác ở cùng neo (`mem_bar_draft_01`), và `.first()` duyệt nó thay
    // vì bản mới — timeline khi đó chứa ký ức của fixture, bài đỏ dù luồng thật
    // vẫn đúng. Lỗi này đã làm đỏ CI thật.
    const row = page
      .getByTestId("pending-memories")
      .locator(".nq-memlist__item")
      .filter({ hasText: "bình giữ nhiệt" });
    const newGrant = row.getByTestId(/^mem-grant-/);
    await expect(newGrant).toBeVisible({ timeout: 10_000 });
    await newGrant.click();
    await expect(page.locator(".nq-pref__notice").first()).toBeVisible({ timeout: 10_000 });
    await expect(page.locator(".nq-timeline").first()).toContainText(
      "khách quen hay nhờ giữ hộ bình giữ nhiệt",
      { timeout: 10_000 },
    );
  });

  test("voice remember refreshes pending list without reload", async ({ page }) => {
    // Voice nói "nhớ điều này…" tạo draft ở NEO ĐANG CHỌN — bản trước UI không
    // để draft xuất hiện cho tới khi người dùng tự F5.
    await expect(page.locator(".nq-map2d")).toBeVisible({ timeout: 15_000 });

    await page.getByTestId("voice-input").fill("nhớ điều này: khách hay hỏi wifi ở bàn cửa sổ");
    await page.getByTestId("voice-ask").click({ force: true });
    await expect(page.locator(".nq-voicedock__proposal")).toBeVisible({ timeout: 10_000 });

    // Cùng một draft phải có mặt trong "Chờ quyết định" của neo tương ứng.
    await expect(page.locator(".nq-anchor")).toContainText(
      "khách hay hỏi wifi ở bàn cửa sổ",
      { timeout: 10_000 },
    );
  });

  test("tour guide renders deterministic steps", async ({ page }) => {
    await expect(page.locator(".nq-map2d")).toBeVisible({ timeout: 15_000 });
    await expect(page.locator(".nq-tour__step").first()).toBeVisible({ timeout: 10_000 });
    const steps = await page.locator(".nq-tour__step").count();
    expect(steps).toBeGreaterThanOrEqual(2);
  });
});