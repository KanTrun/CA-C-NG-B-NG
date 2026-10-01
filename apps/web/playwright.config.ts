import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: "list",
  timeout: 60_000,
  expect: {
    timeout: 10_000,
  },
  use: {
    baseURL: "http://localhost:3001",
    trace: "on-first-retry",
    navigationTimeout: 30_000,
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command:
        process.platform === "win32"
          ? "py -3.12 ../../scripts/demo_api.py"
          : "python ../../scripts/demo_api.py",
      url: "http://127.0.0.1:8000/health",
      cwd: __dirname,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      env: {
        NHIPQUAN_API_HOST: "0.0.0.0",
        NHIPQUAN_API_PORT: "8000",
        NHIPQUAN_DISABLE_RATE_LIMIT: "true",
        NHIPQUAN_SEED_DEMO: "true",
        NHIPQUAN_INBOX_SEED_FIXTURE: "1",
        NHIPQUAN_HAO_HUT_SEED_FIXTURE: "1",
        // BẮT BUỘC cho e2e: các endpoint reset trạng thái (`/experience/rules/reset`,
        // `/experience/quanverse/reset`) trả 403 ngoài chế độ replay (đúng thiết kế
        // fail-closed — production không được xoá luật thật).
        //
        // Trên CI biến này có sẵn vì `.github/workflows/ci.yml` đặt
        // `CA_AGENT_MODE: replay` ở CẤP WORKFLOW, nên mọi job đều thừa hưởng. Ở máy
        // dev thì KHÔNG có, khiến reset im lặng thất bại (403) và trạng thái rò từ
        // bài này sang bài sau — biểu hiện là 3–5 test đỏ NGẪU NHIÊN khi chạy cả bộ
        // mà chạy riêng từng tệp lại xanh. Đặt tường minh ở đây để hai môi trường
        // chạy GIỐNG NHAU, không phụ thuộc việc CI tình cờ có sẵn biến.
        CA_AGENT_MODE: "replay",
      },
    },
    {
      // CẢ HAI môi trường đều chạy `standalone/server.js`, không dùng `next start`.
      //
      // Vì sao: `next.config` đặt `output: "standalone"`, nên `next start` chỉ in
      // cảnh báo và KHÔNG phục vụ đúng `.next/static` — browser nhận 404 cho mọi
      // chunk, React không hydrate, và mọi bài đỏ ở `loginAs` (trông như lỗi điều
      // hướng). Bản standalone cần `static/` + `public/` được copy vào; script
      // `prepare-standalone.mjs` làm việc đó và chạy ngay trước khi start.
      command:
        "node scripts/prepare-standalone.mjs && node .next/standalone/server.js",
      url: "http://localhost:3001",
      cwd: __dirname,
      reuseExistingServer: false,
      timeout: 120_000,
      env: {
        NEXT_PUBLIC_API_URL: "http://127.0.0.1:8000",
        PORT: "3001",
        HOSTNAME: "0.0.0.0",
      },
    },
  ],
});
