import { expect, test, type Page, type Route } from "@playwright/test";

type ReviewItem = {
  id: number;
  message_text: string;
  assigned_role: "quan_ly" | "chu_quan";
  proposed_response: string;
};

const API_PATTERN = /^http:\/\/(localhost|127\.0\.0\.1):8000\/api\/v1\/page\/fb-(inbox|policy)/;
const CHAT_PATTERN = /^http:\/\/(localhost|127\.0\.0\.1):8000\/api\/v1\/chat\//;

/**
 * Mock /api/v1/auth/login để trả token giả + role cụ thể,
 * rồi đăng nhập qua UI bình thường.
 *
 * Lý do không dùng addInitScript + sessionStorage.setItem trực tiếp:
 *   useState("") trong các page React luôn khởi tạo token="",
 *   chỉ sau useEffect(() => setToken(getToken()), []) mới đọc storage.
 *   Nếu có AuthGate hoặc redirect trong khoảng thời gian giữa render
 *   đầu và useEffect, test flake. Flow login thực sự gọi setSession()
 *   bên trong React (sau response từ API), đảm bảo state nhất quán.
 */
async function loginAs(
  page: Page,
  role: "quan_ly" | "chu_quan" | "nhan_vien",
) {
  await page.route(
    /^http:\/\/(localhost|127\.0\.0\.1):8000\/api\/v1\/me/,
    async (route: Route) => {
      await route.fulfill({
        json: {
          role,
          nv_id: `e2e-${role}`,
          display_name: `E2E-${role}`,
        },
      });
    },
  );

  // Mock auth endpoint — không cần DB thật, không cần demo_api trả đúng user
  await page.route(
    /^http:\/\/(localhost|127\.0\.0\.1):8000\/api\/v1\/auth\/login/,
    async (route: Route) => {
      await route.fulfill({
        json: {
          token: "e2e-token",
          role,
          display_name: `E2E-${role}`,
          nv_id: `e2e-${role}`,
        },
      });
    },
  );

  await page.goto("/login");
  await page.getByLabel("Tài khoản").fill("e2e");
  await page.getByLabel("Mật khẩu").fill("e2e");
  await page.getByRole("button", { name: "Vào hệ thống" }).click();
  // Sau login, app navigate đến /hom-nay
  await expect(page).toHaveURL(/\/hom-nay/, { timeout: 15_000 });
}

test.beforeEach(async ({ page }) => {
  // Mock WebSocket chat
  await page.routeWebSocket(/.*\/ws\/chat/, (ws) => {
    ws.onMessage((message) => {
      try {
        const data = JSON.parse(message.toString());
        if (data.event === "auth") {
          ws.send(JSON.stringify({ event: "auth:ack" }));
        }
      } catch {
        // ignore
      }
    });
  });

  // Mock HTTP chat endpoints để FloatingChatHead không gọi API thật
  await page.route(CHAT_PATTERN, async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/online")) {
      await route.fulfill({ json: { online_users: [] } });
    } else {
      await route.fulfill({ json: { items: [], unread_total: 0 } });
    }
  });
});

function fixture(item: ReviewItem) {
  return {
    ...item,
    source: "messenger",
    external_psid: `psid-${item.id}`,
    external_user_name: `Khách ${item.id}`,
    detected_intent: "dat_ban",
    confidence: 0.97,
    policy_action: item.assigned_role === "chu_quan" ? "escalate_owner" : "queue_review",
    flagged_reasons: [],
    status: "pending",
    created_at: "2026-09-04T08:00:00Z",
    expires_at: "2099-09-04T08:15:00Z",
  };
}

async function mockInbox(page: Page, items: ReviewItem[], decisions: unknown[]) {
  await page.route(API_PATTERN, async (route: Route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/fb-policy")) {
      await route.fulfill({
        json: { auto_send_enabled: true, jev_enabled: false },
      });
      return;
    }
    if (url.pathname.endsWith("/stats")) {
      await route.fulfill({
        json: { by_status: { pending: items.length }, total: items.length, auto_sent: 0, auto_rate: 0, escalation_unacked: 0 },
      });
      return;
    }
    if (route.request().method() === "POST") {
      decisions.push(route.request().postDataJSON());
      await route.fulfill({ json: { sent: true } });
      return;
    }
    await route.fulfill({ json: { items: items.map(fixture), role: "quan_ly" } });
  });
}

test("Quản lý duyệt, sửa, từ chối và thấy SLA hợp lệ", async ({ page }) => {
  const decisions: unknown[] = [];
  await loginAs(page, "quan_ly");
  await mockInbox(
    page,
    [
      { id: 1, message_text: "Cho mình đặt bàn", assigned_role: "quan_ly", proposed_response: "Dạ quán đã nhận yêu cầu." },
      { id: 2, message_text: "Đổi giờ đặt bàn", assigned_role: "quan_ly", proposed_response: "Dạ quán hỗ trợ đổi giờ." },
      { id: 3, message_text: "Xin voucher", assigned_role: "quan_ly", proposed_response: "Dạ quán kiểm tra ưu đãi." },
    ],
    decisions,
  );

  await page.goto("/page-quan/fb-inbox");
  await expect(page.getByRole("heading", { name: "Hộp thư Fanpage chờ duyệt" })).toBeVisible();
  await expect(page.getByText(/^SLA /).first()).toBeVisible();

  const first = page.getByRole("article").filter({ hasText: "Cho mình đặt bàn" });
  await first.getByRole("button", { name: "Duyệt & gửi" }).click();
  await expect.poll(() => decisions.length).toBe(1);

  const second = page.getByRole("article").filter({ hasText: "Đổi giờ đặt bàn" });
  await second.getByRole("button", { name: "Sửa rồi gửi" }).click();
  await second.getByLabel("Sửa nội dung trước khi gửi").fill("Dạ quán xác nhận đổi sang 20h ạ.");
  await second.getByRole("button", { name: "Gửi bản đã sửa" }).click();
  await expect.poll(() => decisions.length).toBe(2);

  const third = page.getByRole("article").filter({ hasText: "Xin voucher" });
  await third.getByRole("button", { name: "Từ chối" }).click();
  await expect.poll(() => decisions.length).toBe(3);

  expect(decisions).toEqual([
    { quyet_dinh: "duyet" },
    { quyet_dinh: "sua_gui", noi_dung: "Dạ quán xác nhận đổi sang 20h ạ." },
    { quyet_dinh: "tu_choi", ly_do: "Từ chối khi duyệt" },
  ]);
});

test("Quản lý không thể xử lý escalation dành cho chủ quán", async ({ page }) => {
  await loginAs(page, "quan_ly");
  await mockInbox(
    page,
    [{ id: 4, message_text: "Cần gặp chủ quán", assigned_role: "chu_quan", proposed_response: "Dạ chủ quán sẽ phản hồi." }],
    [],
  );

  await page.goto("/page-quan/fb-inbox");
  await expect(page.getByText("Chỉ chủ quán duyệt")).toBeVisible();
  await expect(page.getByRole("button", { name: "Duyệt & gửi" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Từ chối" })).toBeDisabled();
});

test("Bộ lọc tải đúng trạng thái và khóa mục đã xử lý", async ({ page }) => {
  const requestedStatuses: Array<string | null> = [];
  await loginAs(page, "quan_ly");
  await page.route(API_PATTERN, async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/fb-policy")) {
      await route.fulfill({ json: { auto_send_enabled: true, jev_enabled: false } });
      return;
    }
    if (url.pathname.endsWith("/stats")) {
      await route.fulfill({ json: { by_status: {}, total: 1, auto_sent: 0, auto_rate: 0, escalation_unacked: 0 } });
      return;
    }
    const status = url.searchParams.get("status");
    requestedStatuses.push(status);
    const item = fixture({
      id: 6,
      message_text: status === "approved" ? "Tin đã duyệt" : "Tin đang chờ",
      assigned_role: "quan_ly",
      proposed_response: "Dạ quán đã phản hồi.",
    });
    await route.fulfill({ json: { items: [{ ...item, status: status ?? "pending" }], role: "quan_ly" } });
  });

  await page.goto("/page-quan/fb-inbox");
  await page.getByLabel("Trạng thái").selectOption("approved");
  await expect(page.getByText("Tin đã duyệt")).toBeVisible();
  await expect(page.getByRole("button", { name: "Duyệt & gửi" })).toBeDisabled();
  expect(requestedStatuses).toContain("pending");
  expect(requestedStatuses).toContain("approved");
});

test("Chủ quán có thể xử lý escalation", async ({ page }) => {
  const decisions: unknown[] = [];
  await loginAs(page, "chu_quan");
  await mockInbox(
    page,
    [{ id: 5, message_text: "Cần gặp chủ quán", assigned_role: "chu_quan", proposed_response: "Dạ chủ quán sẽ phản hồi." }],
    decisions,
  );

  await page.goto("/page-quan/fb-inbox");
  await expect(page.getByRole("heading", { name: "Hộp thư Fanpage chờ duyệt" })).toBeVisible();
  await page.getByRole("button", { name: "Duyệt & gửi" }).click();
  await expect.poll(() => decisions).toEqual([{ quyet_dinh: "duyet" }]);
});

test("Nhân viên bị chặn khỏi hộp thư Fanpage @smoke", async ({ page }) => {
  await loginAs(page, "nhan_vien");
  await page.goto("/page-quan/fb-inbox");
  await expect(page.getByRole("heading", { name: /Không đủ quyền|Trang này dành cho vai trò khác/ })).toBeVisible();
});