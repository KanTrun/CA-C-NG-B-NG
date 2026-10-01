import { type Page } from "@playwright/test";

/**
 * Dọn trạng thái Trải nghiệm AI (Quánverse + luật + ký ức) giữa các bài e2e.
 *
 * Vì sao cần tệp dùng chung: bốn spec trước đây mỗi nơi tự chép một đoạn reset,
 * với hai khác biệt nguy hiểm.
 *
 *  1. **Thời điểm chạy.** `quanverse.spec.ts` dọn ở CUỐI mỗi bài, còn
 *     `grand-experience-replay.spec.ts` dọn ở ĐẦU. Dọn ở cuối không bảo vệ được
 *     chính bài đó, và nếu bài trước rơi giữa chừng thì bước dọn không bao giờ
 *     chạy. Dọn ở đầu là cách duy nhất mỗi bài tự lo cho mình.
 *  2. **Phạm vi.** Có nơi chỉ gọi `/rules/reset`, có nơi chỉ `/quanverse/reset`,
 *     có nơi cả hai. `/quanverse/reset` nay cũng dựng lại kho ký ức và xoá mode
 *     state (kv), nhưng một spec gọi thiếu endpoint thì vẫn rò trạng thái.
 *
 * Hệ quả thật đã đo được: chạy cả bộ thì `quanverse.spec.ts` để lại mode `dem_nhac`
 * đang bật, và `spatial-memory.spec.ts` tích thêm ký ức — hai bài ở hai tệp KHÁC
 * đỏ, trong khi chạy riêng từng tệp thì xanh. Thứ tự chạy quyết định kết quả, tức
 * bộ test không còn nói được điều gì chắc chắn.
 *
 * Endpoint reset chỉ mở khi `CA_AGENT_MODE=replay` (ngoài ra 403), nên hàm này an
 * toàn: gọi nhầm môi trường thì nó im lặng bỏ qua chứ không xoá dữ liệu thật.
 */
export async function resetExperienceState(page: Page): Promise<void> {
  const api = process.env.NQ_API ?? "http://127.0.0.1:8000";
  const res = await page.request
    .post(`${api}/api/v1/auth/login`, {
      data: { username: "lan", password: "nhipquan" },
    })
    .catch(() => null);
  if (!res || !res.ok()) return;
  const { token } = (await res.json()) as { token: string };

  for (const path of [
    "/api/v1/experience/rules/reset",
    "/api/v1/experience/quanverse/reset",
  ]) {
    await page.request
      .post(`${api}${path}`, { headers: { Authorization: `Bearer ${token}` } })
      .catch(() => undefined);
  }
}

/**
 * Đăng nhập bằng tài khoản quản lý của fixture.
 *
 * WebGL bị tắt trước khi trang nạp: máy chạy CI và Playwright headless chỉ có
 * SwiftShader/llvmpipe, và `useCapability3d.hasRealWebGL()` từ chối những bộ dựng
 * đó — nên nhánh 3D sẽ không bao giờ chạy. Tắt hẳn cho tường minh thay vì để kết
 * quả phụ thuộc máy, nhưng cũng đừng vì thế mà tưởng đã kiểm được nhánh 3D.
 */
export async function loginAs(page: Page, user = "lan", pass = "nhipquan"): Promise<void> {
  await page.goto("/login");
  await page.getByLabel("Tài khoản").fill(user);
  await page.getByLabel("Mật khẩu").fill(pass);
  await page.getByRole("button", { name: "Vào hệ thống" }).click();
  await page.waitForURL((u) => !u.pathname.includes("/login"), { timeout: 15_000 });
}

/** Tắt WebGL để ép mọi bề mặt 3D rơi về nhánh 2D (xem `loginAs`). */
export async function disableWebgl(page: Page): Promise<void> {
  await page.addInitScript(() => {
    Object.defineProperty(HTMLCanvasElement.prototype, "getContext", { value: () => null });
  });
}

/**
 * QUÁNVERSE 2.0 — bảo đảm có dữ liệu nghiệp vụ thật cho demo/thi.
 *
 * Gọi `POST /quanverse/demo-setup` (manager only, idempotent): ghi don_quay +
 * phan_cong_by_week + tieu_thu thật để Evidence đủ (S1). Im lặng bỏ qua khi
 * môi trường không cho phép — bài test phải tự rẽ nhánh S3 khi đó.
 */
export async function ensureDemoData(page: Page): Promise<void> {
  const api = process.env.NQ_API ?? "http://127.0.0.1:8000";
  const res = await page.request
    .post(`${api}/api/v1/auth/login`, {
      data: { username: "lan", password: "nhipquan" },
    })
    .catch(() => null);
  if (!res || !res.ok()) return;
  const { token } = (await res.json()) as { token: string };
  await page.request
    .post(`${api}/api/v1/experience/quanverse/demo-setup`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    .catch(() => undefined);
}
