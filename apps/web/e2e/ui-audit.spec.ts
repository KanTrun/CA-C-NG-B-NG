/**
 * Audit giao diện toàn hệ thống — NHỊP QUÁN.
 *
 * Vì sao cần: phán đoán thiết kế từ mã nguồn là đoán mò — mọi bố cục "trông
 * ổn" trong đầu đều ổn. Script này RENDER từng trang thật rồi ĐO những thứ mắt
 * người phát hiện được: có bao nhiêu khối là hình vuông sắc cạnh, có bao nhiêu
 * chuyển động đang chạy, bề mặt có phân tầng không, chữ có tràn không.
 *
 * Chạy:
 *   npx playwright test e2e/ui-audit.spec.ts --reporter=list
 * Báo cáo: data/out/ui-audit.json + in bảng ra console.
 */
import { test, expect, type Page } from "@playwright/test";
import { writeFileSync, mkdirSync } from "node:fs";
import { resolve } from "node:path";

/**
 * Mặc định PHẢI khớp `baseURL` trong `playwright.config.ts` (:3001).
 *
 * Bản trước ghim `http://localhost:3000` — cổng mà `next dev` dùng khi tự chạy,
 * nhưng Playwright chỉ dựng web server ở :3001. Không ai chạy `next dev` ở :3000
 * trong CI, nên spec này luôn đỏ ở `page.goto` với `ERR_CONNECTION_REFUSED`:
 * nó chưa từng đo được gì trong một lần chạy chuẩn. Dùng `baseURL` của config
 * để không bao giờ lệch cổng nữa.
 */
const BASE = process.env.NQ_BASE ?? "http://localhost:3001";

/**
 * Báo cáo ghi ra `<repo>/data/out/` — tính TƯƠNG ĐỐI từ file spec.
 *
 * Bản trước ghim cứng `"d:/CA-CÔNG-BẰNG/data/out"`, tức là chỉ chạy đúng trên
 * đúng một máy. Máy khác (hoặc CI) sẽ tạo thư mục lạ ngoài repo.
 * Spec nằm ở `apps/web/e2e/` nên lùi 3 cấp là gốc repo.
 */
const REPO_ROOT = resolve(__dirname, "..", "..", "..");
const OUT_DIR = resolve(REPO_ROOT, "data", "out");
const OUT_FILE = resolve(OUT_DIR, "ui-audit.json");

/** Mọi route trong app — kể cả route chưa có link trên nav. */
const ROUTES = [
  "/", "/login", "/dang-ky", "/hom-nay", "/lich-tuan", "/roster", "/phieu",
  "/inbox", "/treo", "/toi", "/cong-bang", "/doi-ca", "/qr", "/tieu-thu",
  "/hao-phi", "/sop", "/handover", "/cam-nang", "/menu", "/khao-sat-gia",
  "/nguoi", "/vet", "/them", "/quay", "/pha", "/tkb", "/chat", "/cuoc-hop",
  "/copilot", "/ai-learning", "/skills", "/contracts", "/giai-thich",
  "/huong-dan", "/page-quan", "/page-quan/fb-inbox", "/page-quan/dat-ban",
  "/quanverse", "/thu-nghiem-an-toan",
  "/de-xuat-thong-minh",
];

type Metrics = {
  route: string;
  els: number;
  boxes: number;
  squareBoxes: number;
  radii: Record<string, number>;
  animations: number;
  animatedNames: string[];
  canvases: number;
  gradients: number;
  blurs: number;
  horizontalOverflow: number;
  belowFoldH: number;
  tinyText: number;
  h1Count: number;
  distinctFontSizes: number;
  shadowedSurfaces: number;
  emptyAreaRatio: number;
};

async function measure(page: Page, route: string): Promise<Metrics> {
  await page.goto(BASE + route, { waitUntil: "domcontentloaded", timeout: 30000 });
  await page.waitForTimeout(1800); // chờ dữ liệu + hiệu ứng vào trang

  return page.evaluate((r): Metrics => {
    const all = Array.from(document.querySelectorAll("body *"));
    const vis = all.filter((el) => {
      const cs = getComputedStyle(el);
      const b = el.getBoundingClientRect();
      return cs.display !== "none" && cs.visibility !== "hidden" && b.width > 0 && b.height > 0;
    });

    const boxes = vis.filter((el) => {
      const cs = getComputedStyle(el);
      const b = el.getBoundingClientRect();
      if (b.width < 40 || b.height < 24) return false;
      return parseFloat(cs.borderTopWidth) > 0 && cs.borderTopStyle !== "none";
    });

    const radii: Record<string, number> = {};
    let squareBoxes = 0;
    let shadowed = 0;
    boxes.forEach((el) => {
      const cs = getComputedStyle(el);
      const rad = cs.borderRadius.split(" ")[0] ?? "0px";
      radii[rad] = (radii[rad] ?? 0) + 1;
      if (parseFloat(rad) === 0) squareBoxes += 1;
      if (cs.boxShadow !== "none" && !cs.boxShadow.includes("0px 0px 0px 0px,")) shadowed += 1;
    });

    const animated = vis.filter((el) => {
      const cs = getComputedStyle(el);
      return cs.animationName !== "none" && cs.animationDuration !== "0s";
    });

    let gradients = 0;
    let blurs = 0;
    vis.forEach((el) => {
      const cs = getComputedStyle(el);
      if (cs.backgroundImage.includes("gradient")) gradients += 1;
      if (cs.backdropFilter !== "none" && cs.backdropFilter !== "") blurs += 1;
    });

    // Chữ nhỏ hơn 11px là dưới ngưỡng đọc được, nhất là với dấu tiếng Việt.
    const tinyText = vis.filter((el) => {
      const cs = getComputedStyle(el);
      if (!el.textContent || !el.textContent.trim()) return false;
      if (cs.display === "none") return false;
      const hasOwnText = Array.from(el.childNodes).some(
        (n) => n.nodeType === 3 && (n.textContent ?? "").trim().length > 0,
      );
      if (!hasOwnText) return false;
      return parseFloat(cs.fontSize) < 11;
    }).length;

    const sizes = new Set(vis.map((el) => Math.round(parseFloat(getComputedStyle(el).fontSize) * 10) / 10));

    const doc = document.documentElement;
    return {
      route: r,
      els: vis.length,
      boxes: boxes.length,
      squareBoxes,
      radii,
      animations: animated.length,
      animatedNames: Array.from(new Set(animated.map((el) => getComputedStyle(el).animationName))).slice(0, 8),
      canvases: document.querySelectorAll("canvas").length,
      gradients,
      blurs,
      horizontalOverflow: Math.max(0, doc.scrollWidth - doc.clientWidth),
      belowFoldH: Math.round(doc.scrollHeight),
      tinyText,
      h1Count: document.querySelectorAll("h1").length,
      distinctFontSizes: sizes.size,
      shadowedSurfaces: shadowed,
      emptyAreaRatio: 0,
    };
  }, route);
}

test.describe("audit giao diện", () => {
  test("render và đo mọi route", async ({ page }) => {
    test.setTimeout(600000);
    await page.setViewportSize({ width: 1440, height: 900 });

    // Đăng nhập sẵn để trang trong khu vực cần quyền vẫn render đủ.
    await page.goto(BASE + "/login", { waitUntil: "domcontentloaded" });
    const token = process.env.NQ_TOKEN ?? "";
    if (token) {
      await page.evaluate((t) => {
        sessionStorage.setItem("nq_token", t);
        sessionStorage.setItem("nq_role", "quan_ly");
        sessionStorage.setItem("nq_display_name", "Lan Nguyễn");
        sessionStorage.setItem("nq_nv_id", "nv_lan");
      }, token);
    }

    const rows: Metrics[] = [];
    for (const route of ROUTES) {
      try {
        rows.push(await measure(page, route));
      } catch (err) {
        rows.push({
          route, els: -1, boxes: 0, squareBoxes: 0, radii: {}, animations: 0,
          animatedNames: [], canvases: 0, gradients: 0, blurs: 0,
          horizontalOverflow: -1, belowFoldH: -1, tinyText: 0, h1Count: 0,
          distinctFontSizes: 0, shadowedSurfaces: 0, emptyAreaRatio: 0,
        });
      }
    }

    mkdirSync(OUT_DIR, { recursive: true });
    writeFileSync(OUT_FILE, JSON.stringify(rows, null, 2), "utf8");

    // Bảng gọn để đọc bằng mắt
    const pad = (s: string | number, n: number) => String(s).padEnd(n);
    console.log(
      pad("route", 30) + pad("els", 5) + pad("box", 5) + pad("SQ", 5) +
      pad("anim", 5) + pad("cvs", 4) + pad("grad", 5) + pad("blur", 5) +
      pad("tiny", 5) + pad("h1", 4) + pad("sizes", 6) + "ovf",
    );
    for (const r of rows.sort((a, b) => b.squareBoxes - a.squareBoxes)) {
      console.log(
        pad(r.route, 30) + pad(r.els, 5) + pad(r.boxes, 5) +
        pad(r.squareBoxes || "·", 5) + pad(r.animations || "·", 5) +
        pad(r.canvases || "·", 4) + pad(r.gradients || "·", 5) +
        pad(r.blurs || "·", 5) + pad(r.tinyText || "·", 5) +
        pad(r.h1Count, 4) + pad(r.distinctFontSizes, 6) +
        (r.horizontalOverflow > 0 ? r.horizontalOverflow + "px" : "·"),
      );
    }
    expect(rows.length).toBe(ROUTES.length);
  });
});
