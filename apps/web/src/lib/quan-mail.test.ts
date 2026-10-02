import { describe, expect, it } from "vitest";
import { chuanHoaMail, locMailQuan, mailLienQuanQuan } from "./quan-mail";

describe("quan-mail — chỉ hiện mail liên quan quán", () => {
  it("chuẩn hoá không dấu để khớp 'ĐƠN HÀNG' với 'don hang'", () => {
    expect(chuanHoaMail("ĐƠN HÀNG ShopeeFood")).toBe("don hang shopeefood");
  });

  it("mail Google hệ thống (no-reply, không từ khoá quán) ⇒ ẩn", () => {
    expect(
      mailLienQuanQuan({
        from_email: "Google <no-reply@google.com>",
        subject: "Hoàn tất quá trình thiết lập Tài khoản Google mới",
        snippet: "Hãy dành một phút để thiết lập thiết bị của bạn với Google",
      }),
    ).toBe(false);
  });

  it("mail đơn hàng ShopeeFood ⇒ hiện", () => {
    expect(
      mailLienQuanQuan({
        from_email: "ShopeeFood <donhang@shopeefood.vn>",
        subject: "Đơn hàng mới #1234 — 2 Cà phê sữa đá",
        snippet: "Giao tới 12 Nguyễn Huệ",
      }),
    ).toBe(true);
  });

  it("mail nhà cung cấp ⇒ hiện, và đúng nhóm", () => {
    const mail = {
      from_email: "NCC Sữa <baogia@suatuoi.vn>",
      subject: "Báo giá sữa tươi tháng 10",
      snippet: "Nhập hàng nguyên liệu",
    };
    expect(mailLienQuanQuan(mail)).toBe(true);
    expect(mailLienQuanQuan(mail, "nha_cung_cap")).toBe(true);
    expect(mailLienQuanQuan(mail, "don_hang")).toBe(false);
  });

  it("locMailQuan đếm số mail đã ẩn", () => {
    const { hien, an } = locMailQuan(
      [
        { from_email: "Google <no-reply@google.com>", subject: "Thiết lập", snippet: "Google" },
        { from_email: "a@shopeefood.vn", subject: "Đơn hàng mới", snippet: "giao hàng" },
      ],
      { chi_quan: true },
    );
    expect(hien).toHaveLength(1);
    expect(an).toBe(1);
  });

  it("tắt lọc ⇒ giữ nguyên tất cả", () => {
    const msgs = [{ subject: "bất kỳ" }];
    expect(locMailQuan(msgs, { chi_quan: false }).hien).toHaveLength(1);
  });
});
