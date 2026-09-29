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
};

module.exports = nextConfig;
