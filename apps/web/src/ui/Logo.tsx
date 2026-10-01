"use client";

import Link from "next/link";
import { motion, useReducedMotion } from "framer-motion";
import { LINEAR, LOOP_PERIOD_S, beat, beatSeconds } from "../lib/motion";
import { LOGO_PATH_D } from "./logo-path";

/**
 * Bước so le của dấu quán: mỗi nét vào sau nét trước đúng một nhịp `settle`.
 *
 * Dùng lại `beat-settle` làm bước thay vì đặt một số mới — dấu quán chỉ có ba
 * nét, không đáng có thang riêng, và mượn nhịp có sẵn thì khi `--nq-beat-settle`
 * đổi, dấu quán đổi theo.
 */
const LOGO_STEP_S = beatSeconds("settle");

/**
 * Dấu quán: khung tròn nét gạch, hình ly cà phê có đường nhịp tim, và một chấm đỏ.
 *
 * ── Vì sao hình bên trong đổi (2026-09-27) ──
 * Bản trước vẽ tay một đường zigzag (`M 30 70 L 30 30 L 50 70 L 70 30 L 70 70`)
 * đọc ra chữ N/M trừu tượng — **không** phải logo của quán. Trong khi tab trình
 * duyệt lại hiện ảnh `docs/hinh/logo.png` (ly cà phê có đường nhịp tim). Hai
 * thương hiệu khác nhau trên cùng một sản phẩm, và người dùng thấy cả hai cùng lúc.
 *
 * Nay hình lấy từ `LOGO_PATH_D` — **cùng một nguồn** với `public/icon.svg` và bộ
 * favicon, đều sinh từ `docs/hinh/logo.png` bởi `scripts/gen_app_icons.py`. Không
 * chép tay path vào đây: hai bản chép tay thì sớm muộn lệch nhau, đúng thứ vừa
 * phải đi sửa. Sửa hình = sửa ảnh gốc rồi chạy lại script ấy.
 *
 * Vì sao là **một** `<path>` gồm nhiều vòng con thay vì nhiều `<path>`: `fill-rule`
 * mặc định (`nonzero`) cần thấy hết các vòng trong CÙNG một path mới khoét được lỗ
 * bên trong nét vẽ (lỗ của tay cầm, khe giữa các nét). Tách ra nhiều `<path>` thì
 * mỗi vòng thành một hình đặc và các khe biến mất.
 *
 * ── Chuyển động ──
 * Chỉ **mở một lần khi tải trang** rồi đứng yên. Bản trước để hai vòng lặp
 * `repeat: Infinity` chạy mãi: chấm đỏ phồng lên xẹp xuống liên tục, và vòng gạch
 * quay không ngừng khi trỏ vào. Logo nằm trong thanh trên cùng của **mọi trang**,
 * nên đó là hai chuyển động không bao giờ dừng mà người dùng không tài nào tắt —
 * và cả hai đều không mang thông tin gì. Nay chúng chạy **theo yêu cầu** (trỏ vào
 * mới quay) và **tôn trọng ý muốn giảm chuyển động** của hệ điều hành.
 */
export function Logo({ href = "/", className = "" }: { href?: string; className?: string }) {
  const reduced = useReducedMotion() ?? false;
  return (
    <Link
      href={href}
      className={`group inline-flex shrink-0 items-center transition-colors ${className}`}
      aria-label="NHỊP QUÁN — về trang chủ"
    >
      <motion.svg
        width="36"
        height="36"
        viewBox="0 0 100 100"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className="shrink-0 overflow-hidden"
        initial="hidden"
        animate="visible"
        whileHover="hover"
        aria-hidden
      >
        <motion.circle
          cx="50"
          cy="50"
          r="45"
          stroke="var(--nq-accent)"
          strokeWidth="2"
          strokeDasharray="4 8"
          variants={{
            hidden: reduced ? { pathLength: 1, rotate: 0, opacity: 1 } : { pathLength: 0, rotate: -90, opacity: 0 },
            visible: {
              pathLength: 1,
              rotate: 0,
              opacity: 1,
              transition: beat("chapter"),
            },
            hover:
              reduced
                ? {}
                : {
                  rotate: 180,
                  strokeWidth: 4,
                  transition: { duration: LOOP_PERIOD_S, ease: LINEAR, repeat: Infinity },
                },
          }}
        />
        {/* Hình ly + nhịp tim.
            `fillRule="evenodd"` là BẮT BUỘC, không phải mặc định.
            Path này do `scripts/gen_app_icons.py` trace từ ảnh gốc: mỗi vòng là
            một đường bao tách riêng, gần như tất cả cùng chiều (13/15 vòng quay
            cùng hướng). Với `nonzero` — luật mặc định — các vòng cùng chiều cộng
            dồn winding number nên phần nét TRONG bị tô đặc, mất hết khe hở, và
            ở cạnh ly hình đọc ra thành một vệt dính. `evenodd` mới khoét đúng lỗ
            theo số lần cắt.
            Đo được (IoU với mask gốc, cùng bbox): evenodd 0.87–0.90 so với
            nonzero 0.82 ở mọi cỡ từ 16px tới 256px. */}
        <motion.path
          d={LOGO_PATH_D}
          fill="var(--nq-fg)"
          fillRule="evenodd"
          variants={{
            hidden: reduced ? { opacity: 1 } : { opacity: 0 },
            visible: {
              opacity: 1,
              transition: beat("chapter", LOGO_STEP_S),
            },
            hover: {
              fill: "var(--nq-accent)",
              transition: beat("settle"),
            },
          }}
        />
        <motion.circle
          cx="50"
          cy="50"
          r="6"
          fill="var(--nq-red)"
          variants={{
            hidden: { scale: 0, opacity: 0 },
            visible: {
              scale: reduced ? 1 : [0, 1.35, 1],
              opacity: 1,
              transition: beat("focus", LOGO_STEP_S * 2),
            },
            hover: {
              scale: 2,
              fill: "var(--nq-accent)",
              transition: beat("settle"),
            },
          }}
        />
      </motion.svg>
      <div className="ml-2.5 hidden min-w-0 flex-col justify-center sm:flex nq-side__brand-text">
        {/* Tên quán ở đây là NHÃN THƯƠNG HIỆU, không phải tiêu đề trang — nhưng
            vẫn bỏ `tracking-tighter`: với "NHỊP QUÁN" viết hoa, khoảng chữ bị siết
            làm dấu mũ của Ị và dấu sắc của Á chồng vào ký tự bên cạnh. Giãn nhẹ
            theo mật độ chữ hoa của hệ (xem `--nq-t-micro` / nhãn eyebrow). */}
        <span className="text-base font-semibold uppercase leading-none tracking-tight text-[var(--nq-fg)] md:text-lg">
          NHỊP QUÁN
        </span>
        <span className="mt-0.5 font-mono text-2xs uppercase leading-none tracking-[0.28em] text-[var(--nq-accent)]">
          Digital System
        </span>
      </div>
    </Link>
  );
}
