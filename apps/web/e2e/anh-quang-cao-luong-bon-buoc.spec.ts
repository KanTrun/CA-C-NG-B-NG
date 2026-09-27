import { expect, test, type Page } from "@playwright/test";

/**
 * Luồng ẢNH QUẢNG CÁO 4 BƯỚC — chạy trong trình duyệt thật.
 *
 * Điều quan trọng nhất được kiểm: người dùng gõ ý kiến bằng lời thường, thấy nó
 * nằm trong "lịch sử ý kiến", và **mọi yêu cầu phá ràng buộc bảo toàn sản phẩm
 * đều được báo lại rõ ràng** thay vì âm thầm bỏ.
 *
 * API được chặn (route) nên test không phụ thuộc provider ảnh thật và không mở
 * mạng ra ngoài — đúng cổng CI "No live LLM".
 */

const MON = "mon_sua";
const ANH_1PX =
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==";

/** Đăng nhập, mở món có sẵn, mở khu tạo ảnh (chưa chọn ảnh). */
async function mo_khu_tao_anh(page: Page): Promise<void> {
    await page.goto("/login");
    await page.getByLabel("Tài khoản").fill("hung");
    await page.getByLabel("Mật khẩu").fill("nhipquan");
    await page.getByRole("button", { name: "Vào hệ thống" }).click();
    await expect(page).toHaveURL(/\/hom-nay/, { timeout: 15_000 });

    await page.goto("/menu");
    await page.getByRole("button", { name: /Cà phê sữa/ }).click();
    await page.getByRole("button", { name: "Tạo ảnh quảng cáo (AI)" }).click();
    await expect(page.getByRole("button", { name: "Tạo ảnh (AI)" })).toBeVisible({ timeout: 15_000 });
}

/** Bước 1 qua được, kèm ghi chú "chưa kiểm được nội dung". */
async function chan_kiem_anh_dat(page: Page, ghi = ""): Promise<void> {
    await page.route(`**/api/v1/menu/${MON}/anh/kiem-tra`, async (route) => {
        await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify({
                ok: true,
                mon_id: MON,
                da_kiem: !ghi,
                bao_bi: "glass",
                ghi,
            }),
        });
    });
}

/** Chặn Bước 3/4 và trả prompt cố định để khỏi phụ thuộc từ điển. */
async function chan_prompt_quang_cao(
    page: Page,
    handler: (history: string[]) => { prompt_en: string; bo_qua: string[] },
): Promise<void> {
    await page.route(`**/api/v1/menu/${MON}/anh/prompt-quang-cao`, async (route) => {
        const body = JSON.parse(route.request().postData() ?? "{}") as {
            feedback_history?: string[];
        };
        const out = handler(body.feedback_history ?? []);
        await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify({
                ok: true,
                provider: "local-template",
                mon_id: MON,
                prompt_en: out.prompt_en,
                prompt_vi: "Ảnh quảng cáo",
                bao_bi: "glass",
                bo_qua: out.bo_qua,
            }),
        });
    });
}

/** Chọn ảnh sản phẩm qua input file (ảnh 1×1 hợp lệ). */
async function chon_anh_san_pham(page: Page): Promise<void> {
    await page.locator("#aigen-photo").setInputFiles({
        name: "nuoc.png",
        mimeType: "image/png",
        buffer: Buffer.from(ANH_1PX, "base64"),
    });
}

test("chọn ảnh → Bước 1 chạy và báo thiếu kiểm nội dung khi chưa có khoá", async ({ page }) => {
    await chan_kiem_anh_dat(page, "Chưa kiểm được nội dung ảnh (chưa có khoá AI thị giác). Vẫn dùng được.");
    await mo_khu_tao_anh(page);
    await chon_anh_san_pham(page);

    // Nói thật với người dùng: chưa kiểm được nội dung, KHÔNG phải "đã kiểm và đạt".
    await expect(page.getByText(/Chưa kiểm được nội dung ảnh/)).toBeVisible({ timeout: 10_000 });
    // Ô ý kiến Bước 2 xuất hiện vì đã có ảnh sản phẩm.
    await expect(page.getByLabel(/Bước 2/)).toBeVisible();
});

test("ảnh không phải sản phẩm nước → hiện đúng câu hướng dẫn gửi lại", async ({ page }) => {
    await page.route(`**/api/v1/menu/${MON}/anh/kiem-tra`, async (route) => {
        await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify({
                ok: false,
                mon_id: MON,
                da_kiem: true,
                bao_bi: "",
                ly_do: "đây là đĩa thức ăn",
                thong_diep:
                    "Ảnh bạn gửi không phải là ảnh sản phẩm dạng nước (chai/lọ/bình chứa chất lỏng). Vui lòng gửi lại ảnh sản phẩm rõ nét để mình xử lý.",
            }),
        });
    });
    await mo_khu_tao_anh(page);
    await chon_anh_san_pham(page);

    const canhBao = page.getByRole("alert").filter({ hasText: /không phải là ảnh sản phẩm/ });
    await expect(canhBao).toBeVisible({ timeout: 10_000 });
    await expect(canhBao).toContainText(/Vui lòng gửi lại ảnh sản phẩm rõ nét/);
    // Ảnh không đạt thì KHÔNG cho tạo ảnh.
    await expect(page.getByRole("button", { name: "Tạo ảnh (AI)" })).toBeDisabled();
});

test("gõ ý kiến → vào lịch sử và prompt được lắp lại", async ({ page }) => {
    const daNhan: string[][] = [];
    await chan_kiem_anh_dat(page);
    await chan_prompt_quang_cao(page, (history) => {
        daNhan.push(history);
        return { prompt_en: `PROMPT ${history.length}`, bo_qua: [] };
    });
    await mo_khu_tao_anh(page);
    await chon_anh_san_pham(page);

    await page.getByLabel(/Bước 2/).fill("nền xanh, làm sáng hơn");
    await page.getByRole("button", { name: "Ghi nhận ý kiến" }).click();

    // Ý kiến hiện trong lịch sử (đánh số) để người dùng thấy nó đã được ghi nhận.
    await expect(page.getByText(/Ý kiến đã ghi nhận/)).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText("1. nền xanh, làm sáng hơn")).toBeVisible();
    expect(daNhan.at(-1)).toEqual(["nền xanh, làm sáng hơn"]);
});

test("ý kiến vi phạm ràng buộc được báo lại, phần hợp lệ vẫn vào prompt", async ({ page }) => {
    await chan_kiem_anh_dat(page);
    await chan_prompt_quang_cao(page, (history) => ({
        prompt_en: `PROMPT: ${history.join(" | ")}`,
        // Máy chủ là nơi lọc; UI phải HIỆN lại danh sách này cho người dùng.
        bo_qua: ["thêm người cầm chai"],
    }));
    await mo_khu_tao_anh(page);
    await chon_anh_san_pham(page);

    await page.getByLabel(/Bước 2/).fill("nền xanh, thêm người cầm chai");
    await page.getByRole("button", { name: "Ghi nhận ý kiến" }).click();

    const baoLoc = page.getByText(/Không áp dụng được:/);
    await expect(baoLoc).toBeVisible({ timeout: 10_000 });
    await expect(baoLoc).toContainText("thêm người cầm chai");
    await expect(baoLoc).toContainText(/giữ nguyên sản phẩm/);
});

test("tạo ảnh xong → Bước 4 hỏi chỉnh thêm và cho chốt ảnh", async ({ page }) => {
    await chan_kiem_anh_dat(page);
    await chan_prompt_quang_cao(page, () => ({ prompt_en: "PROMPT", bo_qua: [] }));
    await page.route(`**/api/v1/menu/${MON}/anh/generate`, async (route) => {
        await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify({
                ok: true,
                provider: "cloudflare",
                model: "@cf/black-forest-labs/flux-2-klein-4b",
                mon_id: MON,
                seed: 42,
                image_mime: "image/png",
                image_base64: ANH_1PX,
            }),
        });
    });
    await mo_khu_tao_anh(page);
    await chon_anh_san_pham(page);

    await page.getByRole("button", { name: "Tạo ảnh (AI)" }).click();
    await expect(page.getByAltText("Ảnh quảng cáo AI")).toBeVisible({ timeout: 10_000 });

    // Bước 4: hỏi có muốn chỉnh thêm không, kèm nút chốt.
    await expect(page.getByText(/Bạn có muốn chỉnh sửa thêm gì cho ảnh này không/)).toBeVisible();
    const nutChot = page.getByRole("button", { name: /chốt ảnh/ });
    await nutChot.click();
    await expect(page.getByText(/Đã chốt ảnh/).first()).toBeVisible();
});

test("chưa chọn ảnh thì ô ý kiến Bước 2 KHÔNG hiện", async ({ page }) => {
    await mo_khu_tao_anh(page);
    // Không chọn ảnh → vẫn ở chế độ "AI vẽ mới", ô ý kiến quảng cáo không áp dụng.
    await expect(page.getByLabel(/Bước 2/)).toHaveCount(0);
});
