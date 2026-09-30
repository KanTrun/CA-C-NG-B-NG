"use client";

/**
 * QUÁNVERSE — D. CẦN XỬ LÝ NGAY.
 *
 * Danh sách việc có thể hành động. Khi có zone filter, hiện chip lọc.
 * CTA nội bộ: focus zone / hỏi AI; CTA ngoài: link trang nghiệp vụ.
 */

import Link from "next/link";
import { Icon } from "../../../icons";
import {
  type QuanverseActionItem,
  zoneIdTuAction,
} from "../quanverse-contract";
import { Card, CardHead, MucDoChip, NguonChip } from "./kit";

export default function NeedsAttention({
  actions,
  filterZoneLabel,
  onClearFilter,
  onFocusZone,
  onAsk,
}: {
  actions: readonly QuanverseActionItem[];
  filterZoneLabel: string | null;
  onClearFilter: () => void;
  onFocusZone: (zoneId: string) => void;
  onAsk: (question: string) => void;
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
          <span className="nq-qv-card__count" data-testid="actions-count">
            {actions.length} mục
          </span>
        }
      />

      {filterZoneLabel ? (
        <div className="nq-qvact__filter" data-testid="actions-filter">
          <span>Đang lọc · {filterZoneLabel}</span>
          <button type="button" className="nq-linkbtn" onClick={onClearFilter}>
            Xem tất cả
          </button>
        </div>
      ) : null}

      {!canXuLy ? (
        <p className="nq-qv-trong" data-testid="actions-empty">
          <span className="nq-qv-trong__text">
            {filterZoneLabel
              ? `Không có việc gắn ${filterZoneLabel}`
              : "Không có việc cần xử lý ngay"}
          </span>
          <span className="nq-qv-trong__hint">
            {filterZoneLabel
              ? "Bỏ lọc để xem việc toàn quán."
              : "Tải, hàng chờ và định biên đều đang trong ngưỡng."}
          </span>
        </p>
      ) : (
        <ol className="nq-qvact__list">
          {actions.map((a) => {
            const zoneId = zoneIdTuAction(a);
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
                    <>
                      <button
                        type="button"
                        className="nq-qvact__cta"
                        onClick={() => onFocusZone(zoneId)}
                      >
                        Xem trên bản đồ
                        <Icon name="arrow-right" size={13} />
                      </button>
                      <button
                        type="button"
                        className="nq-qvact__cta nq-qvact__cta--secondary"
                        data-testid={`action-ask-${a.id}`}
                        onClick={() => onAsk(`Cần làm gì với: ${a.title}?`)}
                      >
                        Hỏi AI
                      </button>
                    </>
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
