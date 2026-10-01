"use client";

/**
 * QUÁNVERSE 2.0 — [2 TOP 3] Việc tiếp theo do JEV RANK trong closed-set A–E.
 *
 * CODE dựng candidates (đủ điều kiện + lý do). JEV chỉ xếp hạng. UI hiện tối
 * đa 3 mục eligible theo thứ tự ranking của JEV.
 */

import Link from "next/link";
import type { QuanverseEvidence, QuanverseJev } from "../quanverse-contract";
import { Card, CardHead, NguonChip } from "./kit";

export default function Top3List({
  evidence,
  jev,
  onAsk,
}: {
  evidence: QuanverseEvidence;
  jev: QuanverseJev | null;
  onAsk: (question: string) => void;
}) {
  const byId = new Map(evidence.candidates.map((c) => [c.id, c]));
  const order = (jev?.ranking ?? []).map((r) => r.id).filter((id) => byId.get(id)?.eligible);
  for (const c of evidence.candidates) {
    if (c.eligible && !order.includes(c.id)) order.push(c.id);
  }
  const top3 = order.slice(0, 3).map((id) => byId.get(id)!).filter(Boolean);
  const rankP = new Map((jev?.ranking ?? []).map((r) => [r.id, r.p]));

  return (
    <Card className="nq-qvtop3" tone={top3.length > 0 ? "warn" : "neutral"} label="Việc tiếp theo" testId="quanverse-actions">
      <CardHead
        title="3 việc tiếp theo"
        icon="bell"
        trailing={
          <span className="nq-qv-card__count" data-testid="actions-count">
            JEV rank · {top3.length} mục
          </span>
        }
      />
      {top3.length === 0 ? (
        <p className="nq-qv-trong" data-testid="actions-empty">
          <span className="nq-qv-trong__text">Không có việc cần xử lý ngay</span>
          <span className="nq-qv-trong__hint">Mọi thứ đang trong ngưỡng.</span>
        </p>
      ) : (
        <ol className="nq-qvact__list">
          {top3.map((c) => (
            <li key={c.id} className="nq-qvact__item" data-muc-do="warn">
              <div className="nq-qvact__head">
                <span className="nq-qv-nguon">JEV {c.id}{rankP.has(c.id) ? ` · p=${rankP.get(c.id)}` : ""}</span>
                <span className="nq-qvact__title">{c.label}</span>
              </div>
              <p className="nq-qvact__reason">{c.reason}</p>
              <div className="nq-qvact__meta">
                <NguonChip>{c.source}</NguonChip>
                {c.href ? (
                  <Link className="nq-qvact__cta" href={c.href}>
                    Mở trang
                  </Link>
                ) : (
                  <span className="nq-qvact__cta nq-qvact__cta--none">Chỉ để biết</span>
                )}
                <button
                  type="button"
                  className="nq-qvact__cta nq-qvact__cta--secondary"
                  data-testid={`action-ask-${c.id}`}
                  onClick={() => onAsk(`Cần làm gì với: ${c.label}? ${c.reason}`)}
                >
                  Hỏi AI
                </button>
              </div>
            </li>
          ))}
        </ol>
      )}
    </Card>
  );
}
