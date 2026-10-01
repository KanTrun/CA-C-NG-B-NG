/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",

  /**
   * Quánverse đã thu về MỘT màn điều hành duy nhất (`/quanverse`).
   *
   * Bốn route phụ cũ (War Room · Cứu ca · Quán tự viết luật · Hồn quán) bị bỏ
   * khỏi điều hướng và khỏi UX. Chuyển hướng vĩnh viễn thay vì 404 để link cũ
   * trong tài liệu, bookmark của người dùng và lịch sử trình duyệt vẫn vào được
   * chỗ có nghĩa — demo không bị đứt quãng.
   *
   * Backend của bốn tính năng này VẪN SỐNG (`/api/v1/experience/war-room/...`
   * v.v.); chỉ bề mặt UI bị rút khỏi Quánverse.
   */
  async redirects() {
    return [
      { source: "/quanverse/war-room", destination: "/quanverse", permanent: true },
      { source: "/quanverse/shift-rescue", destination: "/quanverse", permanent: true },
      { source: "/quanverse/rules", destination: "/quanverse", permanent: true },
      { source: "/quanverse/spatial-memory", destination: "/quanverse", permanent: true },
    ];
  },

  /**
   * Header bảo mật cho mọi trang HTML (QA 2026-09-30 phát hiện N1: middleware
   * `add_security_headers` của FastAPI chỉ phủ `/api/*`, còn HTML do Next.js
   * phục vụ thì không có header nào).
   *
   * Giữ cùng giá trị với API ở `apps/api/src/ca_api/interfaces/http/main.py`
   * (`nosniff` · `DENY` · `no-referrer`), riêng hai chỗ PHẢI khác API:
   *
   * - CSP phải nới hơn API (`default-src 'none'` sẽ giết Next.js vì framework
   *   cần inline script/style): cho phép `'self'` + inline/eval cho
   *   script/style do Next Generics, ảnh `data:/blob:/https:` (ảnh món + tile
   *   bản đồ), font `data:/https:`, kết nối `http:/https:/ws:/wss:` (`http/ws`
   *   cho dev local `localhost:3000 → localhost:8000`, prod dùng https/wss).
   *   `frame-ancestors 'none'` đi cùng `X-Frame-Options: DENY` chống clickjacking.
   * - Permissions-Policy PHẢI mở `(self)` cho camera/microphone/geolocation:
   *   `/phieu` chụp ảnh minh chứng, Copilot Voice + `/cuoc-hop` ghi âm cần
   *   mic, Quánverse thời tiết cần GPS. `(self)` vẫn chặn trang thứ ba nhúng
   *   vào (kết hợp `frame-ancestors 'none'`), không mở toang như `*`.
   *
   * HSTS do Caddy thêm ở tầng TLS (`infra/oracle/Caddyfile`), không đặt ở đây
   * để tránh gửi nhầm trên HTTP nội bộ web:3000.
   */
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "no-referrer" },
          {
            key: "Permissions-Policy",
            value: "camera=(self), microphone=(self), geolocation=(self)",
          },
          {
            key: "Content-Security-Policy",
            value:
              "default-src 'self'; img-src 'self' data: blob: https:; " +
              "script-src 'self' 'unsafe-inline' 'unsafe-eval'; " +
              "style-src 'self' 'unsafe-inline' https:; " +
              "font-src 'self' data: https:; " +
              "connect-src 'self' http: https: ws: wss:; " +
              "frame-ancestors 'none'; base-uri 'self'; form-action 'self'",
          },
        ],
      },
    ];
  },
};

module.exports = nextConfig;
