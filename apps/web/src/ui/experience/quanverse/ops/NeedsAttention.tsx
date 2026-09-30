"use client";

/**
 * QUÁNVERSE — D. CẦN XỬ LÝ NGAY.
 *
 * Danh sách việc có thể hành động, sắp theo mức độ. Mỗi mục nói RÕ:
 * mức độ · chuyện gì · vì sao · nguồn dữ liệu · CTA.
 *
 * RANH GIỚI AI: khối này KHÔNG tự quyết định thay đổi gì. CTA chỉ mở một trang
 * để người dùng tự làm — không có "áp dụng", không có ghi dữ liệu.
 */

import Link from "next/link";
import { Icon } from "../../../icons";
import type { QuanverseActionItem } from "../quanverse-contract";
import { Card, CardHead, MucDoChip, NguonChip } from "./kit";

export default function NeedsAttention({
  actions,
  onFocusZone,
}: {
  actions: readonly QuanverseActionItem[];
  onFocusZone: (zoneId: string) => void;
}) {
  const canXuLy = actions.length > 0;

  return (
    <Card
      className="nq-qvact"
      tone={canXuLy ? "warn" : "neutral"}
      label="Cần xử lý ngay"
      testId="quanverse-actions"
    >
      <CardHead
        title="Cần xử lý ngay"
        icon="bell"
        trailing={
          <span className="nq-qv-card__count">{actions.length} mục</span>
        }
      />

      {!canXuLy ? (
        <p className="nq-qv-trong" data-testid="actions-empty">
          <span className="nq-qv-trong__text">Không có việc cần xử lý ngay</span>
          <span className="nq-qv-trong__hint">
            Tải, hàng chờ và định biên đều đang trong ngưỡng.
          </span>
        </p>
      ) : (
        <ol className="nq-qvact__list">
          {actions.map((a) => {
            // Việc gắn khu vực: nếu có `ctaHref` thì đi trang khác, ngược lại
            // cuộn/đánh dấu khu vực trên bản đồ (không có mutation nào cả).
            const laZone = a.id.startsWith("zone_");
            const zoneId = laZone ? a.id.slice("zone_".length) : null;
            return (
              <li key={a.id} className="nq-qvact__item" data-muc-do={a.severity}>
                <div className="nq-qvact__head">
                  <MucDoChip severity={a.severity} />
                  <span className="nq-qvact__title">{a.title}</span>
                </div>
                <p className="nq-qvact__reason">{a.reason}</p>
                <div className="nq-qvact__meta">
                  <NguonChip>{a.source}</NguonChip>
                  {a.ctaHref && a.ctaLabel ? (
                    <Link className="nq-qvact__cta" href={a.ctaHref}>
                      {a.ctaLabel}
                      <Icon name="arrow-right" size={13} />
                    </Link>
                  ) : zoneId ? (
                    <button
                      type="button"
                      className="nq-qvact__cta"
                      onClick={() => onFocusZone(zoneId)}
                    >
                      Xem trên bản đồ
                      <Icon name="arrow-right" size={13} />
                    </button>
                  ) : (
                    <span className="nq-qvact__cta nq-qvact__cta--none">
                      Chỉ để biết
                    </span>
                  )}
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </Card>
  );
}
