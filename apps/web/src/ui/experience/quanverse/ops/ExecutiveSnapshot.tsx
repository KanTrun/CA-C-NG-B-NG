"use client";

/**
 * QUÁNVERSE — B. EXECUTIVE SNAPSHOT: sáu KPI đọc trong một lần liếc.
 *
 * KPI alerts/queue/upcoming bấm được → focus zone nóng hoặc panel tương ứng.
 * `value === null` ⇒ "—" — không bao giờ hiện "0" giả.
 */

import {
  CHUA_CO_DU_LIEU,
  type QuanverseKpi,
  formatSo,
} from "../quanverse-contract";

export default function ExecutiveSnapshot({
  kpis,
  onKpiClick,
}: {
  kpis: readonly QuanverseKpi[];
  onKpiClick?: (key: QuanverseKpi["key"]) => void;
}) {
  return (
    <ul className="nq-qvk" data-testid="quanverse-kpis">
      {kpis.map((k) => {
        const clickable =
          !!onKpiClick &&
          (k.key === "alerts" || k.key === "queue" || k.key === "upcoming");
        return (
          <li
            key={k.key}
            className={`nq-qvk__item nq-qvk__item--${k.tone}${
              clickable ? " is-clickable" : ""
            }`}
            data-kpi={k.key}
            data-co-du-lieu={k.value === null ? "0" : "1"}
          >
            {clickable ? (
              <button
                type="button"
                className="nq-qvk__btn"
                data-testid={`kpi-btn-${k.key}`}
                onClick={() => onKpiClick?.(k.key)}
              >
                <span className="nq-qvk__num" data-testid={`kpi-${k.key}`}>
                  {formatSo(k.value, { unit: k.unit })}
                </span>
                <span className="nq-qvk__label">{k.label}</span>
                <span className="nq-qvk__source">
                  {k.value === null ? CHUA_CO_DU_LIEU : k.source}
                </span>
              </button>
            ) : (
              <div className="nq-qvk__btn">
                <span className="nq-qvk__num" data-testid={`kpi-${k.key}`}>
                  {formatSo(k.value, { unit: k.unit })}
                </span>
                <span className="nq-qvk__label">{k.label}</span>
                <span className="nq-qvk__source">
                  {k.value === null ? CHUA_CO_DU_LIEU : k.source}
                </span>
              </div>
            )}
          </li>
        );
      })}
    </ul>
  );
}
