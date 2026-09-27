import type { Metadata } from "next";
import { ConditionalShell } from "./ConditionalShell";
import { SmoothScroll } from "../ui/SmoothScroll";
import { MotionProvider } from "../ui/motion/MotionProvider";
import { fontClass } from "../ui/fonts";
import "./globals.css";
import "./experience.css";
import "./pos.css";

export const metadata: Metadata = {
  title: "NHỊP QUÁN",
  description: "Ca làm việc · cẩm nang sống",
  manifest: "/manifest.webmanifest",
  // Khai ĐỦ size thay vì một tệp .ico chung chung.
  //
  // Vì sao phải liệt kê từng tệp: `favicon.ico` cũ chỉ có **1 entry 256×233**
  // (không vuông — xem `scripts/gen_app_icons.py`), nên mỗi trình duyệt tự nghĩ
  // cách thu nhỏ và tab hiện ra một vệt nhoè. Nay bộ icon sinh từ
  // `docs/hinh/logo.png` có đủ 16/32/48 vuông, và khai tường minh ở đây để
  // trình duyệt chọn đúng bản cho từng ngữ cảnh (tab, bookmark, màn hình chính)
  // thay vì đoán.
  //
  // `apple`: iOS bỏ qua `sizes` và lấy tệp cuối cùng khớp `rel="apple-touch-icon"`
  //   — trỏ thẳng `apple-touch-icon.png` (180×180, nền đặc, vì iOS tô đen alpha).
  // `other`: `icon.svg` cho trình duyệt ưu tiên vector — nét sắc ở mọi tỉ lệ
  //   phóng, và **cùng dữ liệu path** với `Logo.tsx` nên hai nơi không thể lệch.
  icons: {
    icon: [
      { url: "/favicon.ico", sizes: "any" },
      { url: "/icon.svg", type: "image/svg+xml", sizes: "any" },
      { url: "/favicon-16x16.png", type: "image/png", sizes: "16x16" },
      { url: "/favicon-32x32.png", type: "image/png", sizes: "32x32" },
      { url: "/favicon-48x48.png", type: "image/png", sizes: "48x48" },
    ],
    apple: [{ url: "/apple-touch-icon.png", type: "image/png", sizes: "180x180" }],
  },
  // iOS chỉ đọc được vài khoá này qua thẻ meta riêng, không qua manifest.
  appleWebApp: {
    capable: true,
    title: "NHỊP QUÁN",
    statusBarStyle: "black-translucent",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="vi" className={fontClass}>
      {/* suppressHydrationWarning: tiện ích trình duyệt (dịch trang, chặn quảng
          cáo) chèn class/thuộc tính vào <body> TRƯỚC khi React hydrate, làm
          React báo lỗi hydration dù HTML của mình đúng. Chỉ bỏ qua cảnh báo ở
          riêng <body>; mọi phần khác vẫn được kiểm tra nghiêm. */}
      <body suppressHydrationWarning>
        <MotionProvider>
          <SmoothScroll>
            <a href="#nq-content" className="nq-skip">
              Bỏ qua thanh điều hướng
            </a>
            <ConditionalShell>{children}</ConditionalShell>
          </SmoothScroll>
        </MotionProvider>
      </body>
    </html>
  );
}
