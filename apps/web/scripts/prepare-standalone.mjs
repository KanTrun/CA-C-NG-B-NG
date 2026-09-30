/**
 * Chuẩn bị `.next/standalone` để chạy được e2e local — CÙNG việc CI đang làm.
 *
 * Vì sao cần script thay vì làm tay trong `ci.yml`:
 *
 * `next.config` đặt `output: "standalone"`, nên Next KHÔNG cho dùng
 * `next start` nữa — phải chạy `node .next/standalone/server.js`. Nhưng bản
 * standalone chỉ chứa server + node_modules: **không** có `static/` và
 * `public/`. Thiếu chúng thì mọi request `/_next/static/**` trả 404, trang HTML
 * vẫn hiện nhưng JS/CSS không tải được → React không hydrate → nút bấm không
 * chạy. Triệu chứng dễ chẩn đoán sai nhất là e2e đỏ ở `loginAs` với
 * `page.waitForURL timeout` — trông như lỗi điều hướng, thực ra là lỗi thiếu
 * asset. Đã vấp thật: cả 10 bài `quanverse.spec.ts` đỏ cùng một lý do.
 *
 * Trước đây bước copy nằm rải trong `ci.yml` nên chỉ CI có; máy dev chạy e2e
 * qua `next start` và không bao giờ thấy vấn đề này. Đưa vào script để hai môi
 * trường chạy GIỐNG NHAU — cùng nguyên tắc đã ghi ở `playwright.config.ts`
 * (`CA_AGENT_MODE`).
 */

import { cp, mkdir, rm, stat } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const webRoot = join(here, "..");
const nextDir = join(webRoot, ".next");
const standalone = join(nextDir, "standalone");

async function exists(path) {
  try {
    await stat(path);
    return true;
  } catch {
    return false;
  }
}

if (!(await exists(standalone))) {
  console.error(
    "[prepare-standalone] thiếu .next/standalone — chạy `npm run build` trước.",
  );
  process.exit(1);
}

/** Copy thư mục, ghi đè đích. `rm` trước để không trộn asset của build cũ. */
async function syncDir(from, to, label) {
  if (!(await exists(from))) {
    console.warn(`[prepare-standalone] bỏ qua ${label}: không có ${from}`);
    return;
  }
  await rm(to, { recursive: true, force: true });
  await mkdir(dirname(to), { recursive: true });
  await cp(from, to, { recursive: true });
  console.log(`[prepare-standalone] đã copy ${label}`);
}

await syncDir(join(nextDir, "static"), join(standalone, ".next", "static"), ".next/static");
await syncDir(join(webRoot, "public"), join(standalone, "public"), "public");

/*
 * Next có hai layout thư mục cho app root, tuỳ `outputFileTracingRoot`:
 *   - server.js ngay trong `.next/standalone/`  → `public` cùng cấp
 *   - server.js trong `.next/standalone/apps/web/` → `public` phải nằm trong đó
 * Ở repo này là layout thứ nhất, nhưng copy thêm khi thư mục thứ hai tồn tại để
 * script không phụ thuộc cấu hình hiện tại (CI cũ phải `|| true` cho nhánh này).
 */
const nestedAppRoot = join(standalone, "apps", "web");
if (await exists(nestedAppRoot)) {
  await syncDir(join(webRoot, "public"), join(nestedAppRoot, "public"), "apps/web/public");
}
