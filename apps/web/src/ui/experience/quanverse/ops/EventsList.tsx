"use client";

/**
 * QUÁNVERSE — H. SỰ KIỆN VẬN HÀNH.
 *
 * Dòng sự kiện có mốc thời gian, nhãn loại, nguồn và khu vực gắn kết. Bấm vào
 * nhãn khu vực để đánh dấu khu vực đó trên bản đồ (không điều hướng đi đâu).
 */

import { Icon } from "../../../icons";
import { formatLuc } from "../../../../lib/present";
import type { QuanverseEvent } from "../quanverse-contract";
import { Card, CardHead, NguonChip } from "./kit";

export default function EventsList({
  events,
  onFocusZone,
}: {
  events: readonly QuanverseEvent[];
  onFocusZone: (zoneId: string) => void;
}) {
  return (
    <Card className="nq-qvev" label="Sự kiện vận hành" testId="quanverse-events">
      <CardHead
        title="Sự kiện vận hành"
        icon="bell"
        trailing={<span className="nq-qv-card__count">{events.length} mục</span>}
      />

      {events.length === 0 ? (
        <p className="nq-qv-trong" data-testid="events-empty">
          <span className="nq-qv-trong__text">
            Không có sự kiện vận hành cho bản chiếu này
          </span>
          <span className="nq-qv-trong__hint">
            Bản chiếu theo vai trò hiện tại không kèm dòng sự kiện nào.
          </span>
        </p>
      ) : (
        <ul className="nq-qvev__list">
          {events.map((ev) => (
            <li key={ev.id} className="nq-qvev__item">
              <span className="nq-qvev__type">{ev.typeLabel}</span>
              <span className="nq-qvev__sum">{ev.summary}</span>
              <span className="nq-qvev__meta">
                <time className="nq-qvev__time">{formatLuc(ev.occurredAt)}</time>
                {ev.zoneId ? (
                  <button
                    type="button"
                    className="nq-qvev__zone"
                    data-testid={`event-zone-${ev.id}`}
                    onClick={() => onFocusZone(ev.zoneId as string)}
                  >
                    <Icon name="location" size={12} />
                    {ev.zoneLabel}
                  </button>
                ) : (
                  <span className="nq-qvev__zone nq-qvev__zone--none">
                    Toàn quán
                  </span>
                )}
                <NguonChip>{ev.sourceLabel}</NguonChip>
              </span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
