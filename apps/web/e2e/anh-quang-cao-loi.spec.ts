import { expect, test, type Page } from "@playwright/test";

/**
 * Lỗi tạo ảnh quảng cáo phải hiện bằng TIẾNG VIỆT dễ hiểu.
 *
 * Mã lỗi của provider (`http_429:{...json...}`) là chuỗi kỹ thuật — đẩy thẳng ra
 * UI thì người vận hành không biết làm gì tiếp. Test này chặn API trả đúng các
 * mã đó rồi khẳng định UI hiện câu tiếng Việt có hành động kế tiếp.
 */

const MON = "mon_sua";
const ANH_1PX =
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==";

/** Bước 1 qua được để vào được bước tạo ảnh (test này tập trung vào lỗi khi sinh ảnh). */
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

/** Chặn endpoint prompt quảng cáo để trả kết quả nhanh, không phụ thuộc backend. */
async function chan_prompt_quang_cao(page: Page): Promise<void> {
    await page.route(`**/api/v1/menu/${MON}/anh/prompt-quang-cao`, async (route) => {
        await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify({
                ok: true,
                provider: "local-template",
                mon_id: MON,
                prompt_en: "A refreshing cup of iced milk coffee on a wooden table, professional photography",
                prompt_vi: "Cà phê sữa đá trên bàn gỗ",
                bao_bi: "glass",
                bo_qua: [],
            }),
        });
    });
}

/** Đăng nhập và mở món có sẵn, rồi mở khu tạo ảnh. */
async function mo_khu_tao_anh(page: Page): Promise<void> {
    await chan_kiem_anh_dat(page);
    await chan_prompt_quang_cao(page);
    await page.goto("/login");
    await page.getByLabel("Tài khoản").fill("hung");
    await page.getByLabel("Mật khẩu").fill("nhipquan");
    await page.getByRole("button", { name: "Vào hệ thống" }).click();
    await expect(page).toHaveURL(/\/hom-nay/, { timeout: 15_000 });

    await page.goto("/menu");
    await page.getByRole("button", { name: /Cà phê sữa/ }).click();
    await page.getByRole("button", { name: "Tạo ảnh quảng cáo (AI)" }).click();
    // Khu tạo ảnh sẵn sàng (nút tạo ảnh hiện, đang khoá vì chưa có ảnh).
    await expect(page.getByRole("button", { name: "Tạo ảnh (AI)" })).toBeVisible({ timeout: 15_000 });
}

/** Chọn ảnh sản phẩm thật — bắt buộc trước khi bấm tạo ảnh. */
async function chon_anh_san_pham(page: Page): Promise<void> {
    await page.locator("#aigen-photo").setInputFiles({
        name: "nuoc.png",
        mimeType: "image/png",
        buffer: Buffer.from(ANH_1PX, "base64"),
    });
    await expect(page.getByRole("button", { name: "Tạo ảnh (AI)" })).toBeEnabled({ timeout: 15_000 });
}

/** Chặn endpoint generate để trả lỗi provider với mã cho trước. */
async function chan_loi_provider(page: Page, error: string, provider = "cloudflare"): Promise<void> {
    await page.route(`**/api/v1/menu/${MON}/anh/generate`, async (route) => {
        await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify({ ok: false, error, provider, mon_id: MON }),
        });
    });
}

test("hết hạn mức → câu tiếng Việt có gợi ý chờ và tạo lại", async ({ page }) => {
    await chan_loi_provider(
        page,
        'http_429:{"error":{"code":429,"message":"You exceeded your current quota"}}',
    );
    await mo_khu_tao_anh(page);
    await chon_anh_san_pham(page);
    await page.getByRole("button", { name: "Tạo ảnh (AI)" }).click();

    const canhBao = page.getByRole("alert").filter({ hasText: /hạn mức|quota/i });
    await expect(canhBao).toBeVisible({ timeout: 10_000 });
    // Không được lộ mã kỹ thuật hay JSON thô ra màn hình.
    await expect(page.locator("body")).not.toContainText("http_429");
    await expect(page.locator("body")).not.toContainText("exceeded your current quota");
    await expect(canhBao).toContainText(/chờ|tạo lại|báo quản lý/i);
});

test("thiếu khoá sửa ảnh → chỉ đúng việc cần làm", async ({ page }) => {
    await chan_loi_provider(page, "thieu_key_sua_anh", "pollinations-edit");
    await mo_khu_tao_anh(page);
    await chon_anh_san_pham(page);
    await page.getByRole("button", { name: "Tạo ảnh (AI)" }).click();

    const canhBao = page.getByRole("alert").filter({ hasText: /khoá|AI sửa ảnh/i });
    await expect(canhBao).toBeVisible({ timeout: 10_000 });
    await expect(canhBao).toContainText(/dán|dùng chế độ|thử lại/i);
    await expect(page.locator("body")).not.toContainText("thieu_key_sua_anh");
});

test("máy chủ vẽ ảnh lỗi 5xx → câu tiếng Việt, không stack trace", async ({ page }) => {
    await chan_loi_provider(page, 'http_503:{"detail":"upstream unavailable"}');
    await mo_khu_tao_anh(page);
    await chon_anh_san_pham(page);
    await page.getByRole("button", { name: "Tạo ảnh (AI)" }).click();

    const canhBao = page.getByRole("alert").filter({ hasText: /lỗi|thử lại/i });
    await expect(canhBao).toBeVisible({ timeout: 10_000 });
    await expect(page.locator("body")).not.toContainText("http_503");
    await expect(page.locator("body")).not.toContainText("upstream unavailable");
});

test("API chưa chạy (mất mạng) → nhắc kiểm tra kết nối", async ({ page }) => {
    await page.route(`**/api/v1/menu/${MON}/anh/generate`, (route) => route.abort("failed"));
    await mo_khu_tao_anh(page);
    await chon_anh_san_pham(page);
    await page.getByRole("button", { name: "Tạo ảnh (AI)" }).click();

    const canhBao = page.getByRole("alert").filter({ hasText: /máy chủ|mạng|nối/i });
    await expect(canhBao).toBeVisible({ timeout: 10_000 });
});

test("tạo ảnh thành công → hiện ảnh kèm nguồn", async ({ page }) => {
    // PNG 1×1 hợp lệ để <img> hiển thị được.
    const anh1px =
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==";
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
                image_base64: anh1px,
            }),
        });
    });
    await mo_khu_tao_anh(page);
    await chon_anh_san_pham(page);
    await page.getByRole("button", { name: "Tạo ảnh (AI)" }).click();

    await expect(page.getByAltText("Ảnh quảng cáo AI")).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText(/cloudflare/i)).toBeVisible();
    await expect(page.getByRole("button", { name: "Lưu làm ảnh đại diện món" })).toBeVisible();
});
