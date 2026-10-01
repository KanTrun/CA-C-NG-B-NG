import { describe, expect, it } from "vitest";
import { ApiError } from "./api";
import { loiKetNoiGmail, viError } from "./present";

/**
 * Hồi quy: 503 thiếu OAuth config từng bị báo thành "Máy chủ quán đang lỗi…
 * thử lại sau" — người dùng thử lại mãi không được vì thực chất API chạy tốt,
 * chỉ là tiến trình API chưa có Client ID/Secret.
 */
describe("loiKetNoiGmail — 503 thiếu cấu hình không được báo thành 'máy chủ lỗi'", () => {
  it("503 chua_cau_hinh_oauth_gmail ⇒ câu hành động (điền .env + restart API)", () => {
    const msg = loiKetNoiGmail(new ApiError(503, "chua_cau_hinh_oauth_gmail"));
    expect(msg, "phải có câu riêng, không rơi vào viError 5xx").not.toBeNull();
    expect(msg).toContain(".env");
    expect(msg).not.toContain("đang lỗi");
  });

  it("500 thật ⇒ null để viError báo 'máy chủ đang lỗi' như cũ", () => {
    expect(loiKetNoiGmail(new ApiError(500, "boom"))).toBeNull();
    expect(
      viError(new ApiError(500, "boom"), { doing: "khởi tạo kết nối Gmail" }),
    ).toContain("Máy chủ quán đang lỗi");
  });

  it("mất mạng / lỗi lạ ⇒ null", () => {
    expect(loiKetNoiGmail(new ApiError(0))).toBeNull();
    expect(loiKetNoiGmail(new Error("fetch failed"))).toBeNull();
    expect(loiKetNoiGmail(new ApiError(503, "ma_la_nao_do"))).toBeNull();
  });
});
