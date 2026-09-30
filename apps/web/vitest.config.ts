import path from "node:path";
import { defineConfig } from "vitest/config";

/**
 * Vitest cho `apps/web`.
 *
 * Môi trường `node`: các bài test ở đây kiểm LOGIC THUẦN (hợp đồng dữ liệu,
 * bộ chuẩn hoá, tính nhất quán của fixture mock) — không cần DOM.
 *
 * VÌ SAO TỰ KHAI `resolve.alias` mà không dùng `vite-tsconfig-paths`: gói đó là
 * ESM-only, còn `vitest.config.ts` được nạp qua đường `require` của esbuild →
 * "ESM file cannot be loaded by require". Một alias một dòng là đủ và không
 * kéo thêm phụ thuộc.
 *
 * `tsconfig.json` đã loại `**\/*.test.ts` và chính file này khỏi `tsc --noEmit`,
 * nên `npm run lint` / `typecheck` không bị test file làm nhiễu.
 */
export default defineConfig({
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src"),
    },
  },
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
    exclude: ["node_modules", ".next", "e2e/**"],
  },
});
