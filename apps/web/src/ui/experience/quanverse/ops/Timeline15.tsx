"use client";

/**
 * QUÁNVERSE — E. 15 PHÚT TỚI: timeline vận hành.
 *
 * Mỗi mốc: giờ · tiêu đề · loại · nguồn · trạng thái. Khi dữ liệu là mô phỏng,
 * badge "Dữ liệu mô phỏng" hiện ngay trên đầu khối — không giả làm số thật.
 */

import { formatLuc, safeText } from "../../../../lib/present";
import type { QuanverseTimelineItem, QuanverseTimelineStatus } from "../quanverse-contract";
import { Card, CardHead, NguonChip } from "./kit";

function hienGio(at: string): string {
  const raw = safeText(at, "—");
  if (raw === "—") return raw;
  if (/^\d{1,2}:\d{2}$/.test(raw.trim())) return raw.trim();
  // ISO datetime → "DD/MM HH:MM", chuỗi rác → "—" (không Invalid Date).
  const fm = formatLuc(raw);
  if (fm !== "—") {
    const parts = fm.split(" ");
    return parts.length > 1 ? parts[1] : fm;
  }
  return raw;
}

const NHAN_TT: Record<QuanverseTimelineStatus, string> = {
  sap_toi: "Sắp tới",
  dang_chay: "Đang chạy",
  xong: "Đã xong",
  qua_han: "Quá hạn",
};

export default function Timeline15({
  items,
  isMock,
}: {
  items: readonly QuanverseTimelineItem[];
  isMock: boolean;
}) {
  return (
    <Card className="nq-qvtl" label="15 phút tới" testId="quanverse-timeline">
      <CardHead
        title="15 phút tới"
        icon="clock"
        trailing={
          isMock ? (
            <span className="nq-qv-badge-mock" data-testid="timeline-mock-badge">
              Dữ liệu mô phỏng
            </span>
          ) : null
        }
      />

      {items.length === 0 ? (
        <p className="nq-qv-trong">
          <span className="nq-qv-trong__text">Chưa có mốc nào trong 15 phút tới</span>
          <span className="nq-qv-trong__hint">
            Không có bàn giao, kiểm kê hay đổi ca nào được lên lịch.
          </span>
        </p>
      ) : (
        <ol className="nq-qvtl__list">
          {items.map((it) => (
            <li
              key={it.id}
              className={`nq-qvtl__item nq-qvtl__item--${it.status}`}
              data-trang-thai={it.status}
            >
              <time className="nq-qvtl__gio">{hienGio(it.at)}</time>
              <span className="nq-qvtl__dot" aria-hidden="true" />
              <span className="nq-qvtl__body">
                <span className="nq-qvtl__title">{it.title}</span>
                <span className="nq-qvtl__meta">
                  {it.kind ? <span className="nq-qvtl__kind">{it.kind}</span> : null}
                  <NguonChip>{it.source}</NguonChip>
                  <span className="nq-qvtl__status">{NHAN_TT[it.status]}</span>
                </span>
              </span>
            </li>
          ))}
        </ol>
      )}
    </Card>
  );
}
