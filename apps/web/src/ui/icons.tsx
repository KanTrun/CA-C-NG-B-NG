/**
 * Bộ icon SVG inline.
 *
 * Vì sao không dùng thư viện icon: thêm một dependency runtime cho 9 hình là
 * không đáng, và §10.3 giữ mọi thứ ở mức 0 đồng, không phụ thuộc CDN.
 * Vì sao không dùng emoji: `docs/design-guidelines.md` cấm emoji-as-icon.
 *
 * Mọi icon dùng `currentColor` nên tự đổi màu theo trạng thái active/hover,
 * và mang `aria-hidden` vì nhãn chữ luôn đi kèm.
 */
import type { ReactNode } from "react";

export type IconName =
  | "hom-nay"
  | "phieu"
  | "toi"
  | "treo"
  | "roster"
  | "inbox"
  | "cam-nang"
  | "them"
  | "cong-bang"
  | "copilot"
  | "doi-ca"
  | "chat"
  | "attachment"
  | "microphone"
  | "send"
  | "close"
  | "arrow-left"
  | "arrow-right"
  | "chevron-down"
  | "menu"
  | "bell"
  | "bell-off"
  | "info"
  | "pin"
  | "reply"
  | "edit"
  | "trash"
  | "image"
  | "users"
  | "coffee"
  | "bot"
  | "calendar"
  | "zap"
  | "download"
  | "play"
  | "pause"
  | "table-map"
  | "location"
  | "link"
  | "clipboard"
  | "refresh"
  | "phone"
  | "clock"
  | "check"
  | "x-mark"
  | "plus"
  | "warn"
  | "call"
  | "export"
  // Bộ icon Trải nghiệm (QUÁNVERSE): khu vực quán, chế độ quán, lớp hình ảnh
  | "cloud-rain"
  | "volume-off"
  | "music"
  | "qr"
  | "cube"
  | "map"
  | "door"
  | "gauge"
  | "user"
  | "mail"
  | "tag"
  | "filter"
  | "refresh-cw"
  | "rotate-ccw"
  | "external-link"
  | "star"
  | "mail-open"
  | "paperclip";

const PATHS: Record<IconName, ReactNode> = {
  attachment: <path d="m20.5 11.5-8.9 8.9a6 6 0 0 1-8.5-8.5l9.4-9.4a4 4 0 0 1 5.7 5.7l-9.4 9.4a2 2 0 0 1-2.8-2.8l8.8-8.8" />,
  microphone: <><rect x="9" y="3" width="6" height="11" rx="3" /><path d="M5 11a7 7 0 0 0 14 0M12 18v3M8 21h8" /></>,
  send: <path d="m22 2-7 20-4-9-9-4Z M22 2 11 13" />,
  close: <path d="m6 6 12 12M18 6 6 18" />,
  "arrow-left": <path d="m15 18-6-6 6-6M9 12h10" />,
  "arrow-right": <path d="m9 18 6-6-6-6M15 12H5" />,
  // Mũi nhọn xuống — chỉ nhóm đang mở trong sidebar.
  "chevron-down": <path d="m6 9 6 6 6-6" />,
  // Ba vạch — mở điều hướng ở màn hẹp.
  menu: <path d="M4 7h16M4 12h16M4 17h16" />,
  bell: <path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4" />,
  "bell-off": <><path d="M13.7 5.1A6 6 0 0 0 6 8c0 7-3 7-3 9h12M18 8c0 3.2.7 5 1.7 6.2M10 21h4M3 3l18 18" /></>,
  info: <><circle cx="12" cy="12" r="9" /><path d="M12 11v5M12 8h.01" /></>,
  pin: <path d="m15 4 5 5-3 1-3 5 1 3-2 2-2-4-5-5-4-2 2-2 3 1 5-3 1-3Z" />,
  reply: <path d="M9 14 4 9l5-5M4 9h9a7 7 0 0 1 7 7v2" />,
  edit: <path d="m4 20 4.5-1 10-10a2.1 2.1 0 0 0-3-3l-10 10Z M13.5 7.5l3 3" />,
  trash: <><path d="M4 7h16M10 11v5M14 11v5M6 7l1 14h10l1-14M9 7V4h6v3" /></>,
  image: <><rect x="3" y="4" width="18" height="16" rx="2" /><circle cx="8.5" cy="9" r="1.5" /><path d="m21 15-5-5L5 20" /></>,
  users: <><circle cx="9" cy="8" r="3" /><path d="M3 20a6 6 0 0 1 12 0M16 11a3 3 0 1 0 0-6M18 14a5 5 0 0 1 3 6" /></>,
  coffee: <><path d="M5 8h12v6a5 5 0 0 1-5 5H10a5 5 0 0 1-5-5Z M17 10h2a3 3 0 0 1 0 6h-2M8 4v2M12 3v3" /></>,
  bot: <><rect x="4" y="7" width="16" height="12" rx="3" /><path d="M12 3v4M8 12h.01M16 12h.01M8 16h8" /></>,
  calendar: <><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M16 3v4M8 3v4M3 10h18" /></>,
  zap: <path d="m13 2-9 12h7l-1 8 9-12h-7Z" />,
  download: <path d="M12 3v12m0 0 4-4m-4 4-4-4M5 21h14" />,
  play: <path d="m8 5 11 7-11 7Z" />,
  pause: <path d="M8 5v14M16 5v14" />,
  "table-map": <><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M3 10h18M9 4v16M15 4v16" /></>,
  location: <><path d="M20 10c0 5-8 11-8 11S4 15 4 10a8 8 0 1 1 16 0Z" /><circle cx="12" cy="10" r="2.5" /></>,
  link: <path d="M10 13a5 5 0 0 0 7.1.1l2-2a5 5 0 0 0-7.1-7.1l-1.1 1.1M14 11a5 5 0 0 0-7.1-.1l-2 2A5 5 0 0 0 12 20l1.1-1.1" />,
  clipboard: <><rect x="5" y="4" width="14" height="17" rx="2" /><path d="M9 4.5V3h6v1.5M9 10h6M9 14h6M9 18h3" /></>,
  refresh: <path d="M20 11a8 8 0 0 0-14.8-3.8L4 9M4 5v4h4M4 13a8 8 0 0 0 14.8 3.8L20 15M20 19v-4h-4" />,
  phone: <path d="M6.5 3.5h3l1.5 4-2 1.5a14 14 0 0 0 6 6l1.5-2 4 1.5v3a2 2 0 0 1-2 2C11.6 19.5 4.5 12.4 4.5 5.5a2 2 0 0 1 2-2Z" />,
  clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
  // Dấu tích — xác nhận / giữ ca
  check: <path d="m4.5 12.5 5 5 10-11" />,
  // Dấu × đậm — bỏ ca / gỡ người
  "x-mark": <path d="m6 6 12 12M18 6 6 18" />,
  // Dấu + — thêm người vào ca
  plus: <path d="M12 5v14M5 12h14" />,
  // Tam giác chấm than — cảnh báo / chưa chốt
  warn: <><path d="M12 4 2.5 20h19L12 4Z" /><path d="M12 10v4M12 17.5h.01" /></>,
  // Máy nghe đeo đầu — trực dự bị On-call
  call: <><path d="M4 13a8 8 0 0 1 16 0" /><path d="M4 13v3a2 2 0 0 0 2 2h1v-5H6a2 2 0 0 0-2 2ZM20 13v3a2 2 0 0 1-2 2h-1v-5h1a2 2 0 0 1 2 2Z" /></>,
  // Lịch + mũi tên ra — xuất file .ics
  export: <><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M16 3v4M8 3v4M3 10h18M12 13v5m0 0 2.5-2.5M12 18l-2.5-2.5" /></>,
  // User icon
  user: <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2M12 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z" />,
  // Mail icon
  mail: <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2zm0 2v.51l7 4.2 7-4.2V6H4zm8 8.5-5-3 5-3 5 3-5 3z" />,
  // Tag icon
  tag: <path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82zM7 7a3 3 0 1 1 6 0 3 3 0 0 1-6 0z" />,
  // Filter icon
  filter: <path d="M3 3h18v2H3zm0 16h18v2H3zm0-8h18v2H3z" />,
  // Refresh CW
  "refresh-cw": <path d="M20 11a8 8 0 0 0-14.8-3.8L4 9M4 5v4h4M4 13a8 8 0 0 0 14.8 3.8L20 15M20 19v-4h-4" />,
  // Rotate CCW
  "rotate-ccw": <path d="M4 13a8 8 0 0 1 14.8-3.8L20 15M20 19v-4h-4M4 11a8 8 0 0 0-14.8 3.8L4 15M4 5v4h4" />,
  // External link
  "external-link": <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6M15 3h6v6M10 14 21 3" />,
  // Star
  star: <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z" />,
  // Mail open
  "mail-open": <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2zm0 2v.51l7 4.2 7-4.2V6H4zm8 8.5-5-3 5-3 5 3-5 3z" />,
  // Paperclip
  paperclip: <path d="M20.5 11.5l-8.9 8.9a6 6 0 0 1-8.5-8.5l9.4-9.4a4 4 0 0 1 5.7 5.7l-9.4 9.4a2 2 0 0 1-2.8-2.8l8.8-8.8" />,
  // Bong bóng hội thoại — chat nội bộ
  chat: (
    <>
      <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5Z" />
    </>
  ),
  // Mặt trời trên đường chân trời — bảng "hôm nay"
  "hom-nay": (
    <>
      <circle cx="12" cy="11" r="3.4" />
      <path d="M12 3.5v2M12 16.5v1M4.6 11h2M17.4 11h2M6.8 5.8l1.4 1.4M15.8 7.2l1.4-1.4" />
      <path d="M3 20.5h18" />
    </>
  ),
  // Kẹp giấy có dấu tích — phiếu vận hành
  phieu: (
    <>
      <path d="M9 4.5h6a1 1 0 0 1 1 1v1H8v-1a1 1 0 0 1 1-1Z" />
      <path d="M8 6.5H6.5a1 1 0 0 0-1 1v11a1 1 0 0 0 1 1h11a1 1 0 0 0 1-1v-11a1 1 0 0 0-1-1H16" />
      <path d="M8.8 12.6l1.8 1.8 3.8-3.8" />
    </>
  ),
  // Người kèm đồng hồ — ca của tôi
  toi: (
    <>
      <circle cx="10" cy="8" r="3.2" />
      <path d="M4.5 19.5c0-3 2.5-5.2 5.5-5.2 1 0 1.9.2 2.7.6" />
      <circle cx="16.8" cy="16.8" r="3.7" />
      <path d="M16.8 15.2v1.8l1.4.9" />
    </>
  ),
  // Cờ — việc treo lại
  treo: (
    <>
      <path d="M6 20.5V4.2" />
      <path d="M6 4.8h9.6l-1.7 3.4 1.7 3.4H6" />
    </>
  ),
  // Lưới tuần — lịch tuần
  roster: (
    <>
      <rect x="3.5" y="5.5" width="17" height="14" rx="1.4" />
      <path d="M3.5 10h17M9 5.5v14M14.8 5.5v14" />
      <path d="M7.5 3.5v3M16.5 3.5v3" />
    </>
  ),
  // Khay thư — hộp thư ràng buộc
  inbox: (
    <>
      <path d="M3.6 13.2 6 6.2a1 1 0 0 1 .95-.7h10.1a1 1 0 0 1 .95.7l2.4 7" />
      <path d="M3.6 13.2h4.2l1 2.3h6.4l1-2.3h4.2v4.6a1 1 0 0 1-1 1H4.6a1 1 0 0 1-1-1Z" />
    </>
  ),
  // Sách mở — cẩm nang sống
  "cam-nang": (
    <>
      <path d="M12 6.6C10.4 5.4 8.3 5 5.4 5.2a.9.9 0 0 0-.9.9v10.5a.9.9 0 0 0 1 .9c2.6-.2 4.6.2 6.5 1.3" />
      <path d="M12 6.6c1.6-1.2 3.7-1.6 6.6-1.4a.9.9 0 0 1 .9.9v10.5a.9.9 0 0 1-1 .9c-2.6-.2-4.6.2-6.5 1.3" />
      <path d="M12 6.6v12.2" />
    </>
  ),
  // Cân — bảng công bằng
  "cong-bang": (
    <>
      <path d="M12 4.5v14.8M7.5 19.3h9" />
      <path d="M12 6.6 5 8.2M12 6.6l7 1.6" />
      <path d="M2.8 12.4a2.2 2.2 0 0 0 4.4 0L5 8.2Z" />
      <path d="M16.8 12.4a2.2 2.2 0 0 0 4.4 0L19 8.2Z" />
    </>
  ),
  // Ba chấm — thêm
  them: (
    <>
      <circle cx="6" cy="12" r="1.4" />
      <circle cx="12" cy="12" r="1.4" />
      <circle cx="18" cy="12" r="1.4" />
    </>
  ),
  // Tia lọc trong bong bóng — trợ lý AI
  copilot: (
    <>
      <path d="M4 5h16v10H13l-4 4v-4H4z" />
      <path d="M12 8l1 2 2 1-2 1-1 2-1-2-2-1 2-1z" />
    </>
  ),
  // Hai mũi tên đổi chiều — đổi ca
  "doi-ca": (
    <>
      <path d="M7 8h10l-3-3" />
      <path d="M17 16H7l3 3" />
    </>
  ),
  // Mây kèm mưa — chế độ "trời mưa"
  "cloud-rain": (
    <>
      <path d="M17.5 9.5a4 4 0 0 0-7.6-1.6A3.2 3.2 0 0 0 6 14.8h11a2.8 2.8 0 0 0 .5-5.3Z" />
      <path d="M8 17.5l-.9 2.2M12 17.5l-.9 2.2M16 17.5l-.9 2.2" />
    </>
  ),
  // Loa gạch chéo — chế độ "quán yên tĩnh"
  "volume-off": (
    <>
      <path d="M11 5.5 6.8 9H4v6h2.8L11 18.5Z" />
      <path d="m15.5 9.5 4 5M19.5 9.5l-4 5" />
    </>
  ),
  // Nốt nhạc đôi — chế độ "đêm nhạc"
  music: (
    <>
      <circle cx="7" cy="17.5" r="2.5" />
      <circle cx="18" cy="15.5" r="2.5" />
      <path d="M9.5 17.5V7l11-2v10.5" />
    </>
  ),
  // Bốn góc định vị kèm ô vuông — mã QR / anchor AR
  qr: (
    <>
      <path d="M4 9V5.5A1.5 1.5 0 0 1 5.5 4H9M15 4h3.5A1.5 1.5 0 0 1 20 5.5V9M20 15v3.5a1.5 1.5 0 0 1-1.5 1.5H15M9 20H5.5A1.5 1.5 0 0 1 4 18.5V15" />
      <path d="M10 10h4v4h-4Z" />
    </>
  ),
  // Khối lập phương — lớp hình ảnh 3D
  cube: (
    <>
      <path d="m12 3.2 7.5 4.3v8.6L12 20.4l-7.5-4.3V7.5Z" />
      <path d="m12 12 7.5-4.5M12 12v8.4M12 12 4.5 7.5" />
    </>
  ),
  // Bản đồ gấp — lớp hình ảnh 2D
  map: (
    <>
      <path d="M9 4.5 3.5 6.8v12.7L9 17.2l6 2.3 5.5-2.3V4.5L15 6.8Z" />
      <path d="M9 4.5v12.7M15 6.8v12.7" />
    </>
  ),
  // Cửa mở — khu vực lối vào
  door: (
    <>
      <path d="M5 20.5h14" />
      <path d="M6.5 20.5V4.5a1 1 0 0 1 1-1h7a1 1 0 0 1 1 1v16" />
      <path d="M13.5 12.2h.01" />
      <path d="M17.5 9.5v3" />
    </>
  ),
  // Đồng hồ đo — mức tải
  gauge: (
    <>
      <path d="M4 17a8 8 0 1 1 16 0" />
      <path d="m12 14.5 4-3.5" />
      <circle cx="12" cy="15.5" r="1.4" />
    </>
  ),
};

export function Icon({ name, size = 20, className = "" }: { name: IconName; size?: number; className?: string }) {
  return (
    <svg
      className={className ? `nq-icon ${className}` : "nq-icon"}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {PATHS[name]}
    </svg>
  );
}

/** Suy icon từ href, để bảng điều hướng chỉ cần khai href + label. */
export function iconForHref(href: string): IconName {
  const key = href.replace(/^\//, "") as IconName;
  return key in PATHS ? key : "them";
}
