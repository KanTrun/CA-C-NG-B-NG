import type { Metadata } from "next";
import { ConditionalShell } from "./ConditionalShell";
import { SmoothScroll } from "../ui/SmoothScroll";
import { MotionProvider } from "../ui/motion/MotionProvider";
import { fontClass } from "../ui/fonts";
import "./globals.css";
import "./experience.css";
import "./quanverse.css";
import "./pos.css";

export const metadata: Metadata = {
  title: "NHỊP QUÁN",
  description: "Ca làm việc · cẩm nang sống",
  manifest: "/manifest.webmanifest",
  // Favicon dùng `favicon.png` theo yêu cầu — chỉ đổi favicon, không đụng logo.
  // `apple`: giữ nguyên cho iOS.
  icons: {
    icon: [{ url: "/favicon.png", type: "image/png" }],
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
      <body>
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
