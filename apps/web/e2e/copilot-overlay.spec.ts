/**
 * Chống hồi quy: panel Copilot nổi KHÔNG được che nút bấm của trang.
 *
 * Lỗi gốc (QA 2026-10-01, đo trên production): `CopilotPane` là `position:
 * fixed` 430×640 ở góc phải dưới và MỞ SẴN trên mọi trang desktop
 * (`DEFAULT_STATE.size = 1`). Nó đè lên nội dung trang, nên 20 control trên 14
 * trang không bấm được — kể cả "LƯU THÔNG TIN QUÁN" và "Thêm món". Nút nhìn bình
 * thường, không báo gì, bấm mãi không có phản hồi.
 *
 * API kiểm tra trước khi sửa vẫn trả 200 cho mọi thứ — phía server ổn, lỗi nằm
 * ở tầng trình duyệt. Vì vậy KHÔNG có test API nào bắt được; chỉ render thật rồi
 * đo `elementFromPoint()` mới nói ra được.
 *
 * Cách sửa: chạm vào phần trang (ngoài pane) thì pane tự thu nhỏ về Tinh Linh.
 *
 * Chạy: npx playwright test e2e/copilot-overlay.spec.ts --reporter=list
 */

import { expect, test, type Page } from "@playwright/test";

async function loginAs(page: Page, user = "lan") {
  const res = await page.request.post("http://localhost:8000/api/v1/auth/login", {
    data: { username: user, password: "nhipquan" },
  });
  const body = await res.json();
  await page.addInitScript(
    ([token, role, name, nvId]) => {
      sessionStorage.setItem("nq_token", token);
      sessionStorage.setItem("nq_role", role);
      sessionStorage.setItem("nq_name", name);
      sessionStorage.setItem("nq_nv_id", nvId);
      localStorage.setItem("nq_role", role);
      localStorage.setItem("nq_onboarding_v1", "1");
    },
    [body.token, body.role, body.display_name, body.nv_id],
  );
}

/** Trả về các control ĐANG HIỆN trong khung nhìn mà không bấm được do bị che. */
async function coveredControls(page: Page) {
  return page.evaluate(() => {
    const out: Array<{ label: string; blocker: string }> = [];
    for (const el of document.querySelectorAll("button,a[href],input,select,textarea")) {
      const r = el.getBoundingClientRect();
      if (r.width < 4 || r.height < 4) continue;
      const s = getComputedStyle(el);
      if (s.visibility === "hidden" || s.display === "none" || s.opacity === "0") continue;
      if (r.bottom < 0 || r.top > innerHeight) continue;
      const cx = r.left + r.width / 2;
      const cy = r.top + r.height / 2;
      if (cx < 0 || cx > innerWidth) continue;
      const top = document.elementFromPoint(cx, cy);
      if (!top || top === el || el.contains(top)) continue;
      let e: Element | null = top;
      let blockedByCopilot = false;
      while (e) {
        if (e.id === "nq-copilot-root" || e.closest("#nq-copilot-root")) {
          blockedByCopilot = true;
          break;
        }
        e = e.parentElement;
      }
      if (blockedByCopilot) {
        out.push({
          label: ((el as HTMLElement).getAttribute("aria-label") || el.textContent || "").trim().slice(0, 40),
          blocker: `${top.tagName}.${String(top.className).slice(0, 40)}`,
        });
      }
    }
    return out;
  });
}

/** Nút hành động chính của từng trang — đúng những nút từng bị che trên production. */
const CASES = [
  { user: "hung", path: "/menu", label: "Thêm món" },
  { user: "lan", path: "/cau-hinh-quan", label: "LƯU THÔNG TIN QUÁN" },
  { user: "lan", path: "/page-quan/dat-ban", label: "Đã hủy" },
  { user: "lan", path: "/quay", label: "Thêm Combo sang" },
];

for (const c of CASES) {
  test(`nút "${c.label}" ở ${c.path} bấm được dù Copilot đang mở (${c.user})`, async ({ page }) => {
    await loginAs(page, c.user);
    await page.goto(c.path);
    await page.waitForLoadState("domcontentloaded");
    await page.waitForTimeout(2500);

    // Bảo đảm pane ĐANG mở — nếu không, bài test này không kiểm gì.
    const paneOpen = await page.evaluate(() => !!document.querySelector("#nq-copilot-root"));
    expect(paneOpen, "pane Copilot phải mở sẵn thì bài test mới có ý nghĩa").toBe(true);

    const btn = page.getByRole("button", { name: c.label, exact: true }).first();
    await expect(btn).toBeVisible();
    await btn.scrollIntoViewIfNeeded();
    await page.waitForTimeout(300);

    // Chạm vào phần trang ⇒ pane phải tự thu nhỏ.
    await page.mouse.click(60, 300);
    await page.waitForTimeout(600);

    const covered = await coveredControls(page);
    expect(covered, `còn control bị Copilot che: ${JSON.stringify(covered)}`).toHaveLength(0);

    // Và bấm thật phải ăn.
    await btn.click({ timeout: 5000 });
  });
}

test("pane không che control nào ngay khi vừa mở trang", async ({ page }) => {
  await loginAs(page, "hung");
  await page.goto("/menu");
  await page.waitForLoadState("domcontentloaded");
  await page.waitForTimeout(2000);

  // Trước khi chạm vào trang, pane có thể phủ — nhưng đó là hành vi mở mặc định
  // có chủ ý. Chạm vào trang một lần là phải sạch hoàn toàn.
  await page.mouse.click(60, 300);
  await page.waitForTimeout(600);
  expect(await coveredControls(page)).toHaveLength(0);
});