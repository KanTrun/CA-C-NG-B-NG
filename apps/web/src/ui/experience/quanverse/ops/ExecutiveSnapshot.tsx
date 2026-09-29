"use client";

/**
 * QUÁNVERSE — B. EXECUTIVE SNAPSHOT: sáu KPI đọc trong một lần liếc.
 *
 * QUY ƯỚC SỐ: `value === null` ⇒ "—" + "Chưa có dữ liệu". KHÔNG bao giờ hiện
 * "0" cho dữ liệu vắng mặt — đó là điểm khác biệt giữa "quán rảnh" và "chưa
 * biết gì". Mọi con số đi qua `formatSo` nên không chỗ nào tự nối chuỗi số.
 */

import {
  CHUA_CO_DU_LIEU,
  type QuanverseKpi,
  formatSo,
} from "../quanverse-contract";
import { Card } from "./kit";

export default function ExecutiveSnapshot({
  kpis,
}: {
  kpis: readonly QuanverseKpi[];
}) {
  return (
    <ul className="nq-qvk" data-testid="quanverse-kpis">
      {kpis.map((k) => (
        <li
          key={k.key}
          className={`nq-qvk__item nq-qvk__item--${k.tone}`}
          data-kpi={k.key}
          data-co-du-lieu={k.value === null ? "0" : "1"}
        >
          <span className="nq-qvk__num" data-testid={`kpi-${k.key}`}>
            {formatSo(k.value, { unit: k.unit })}
          </span>
          <span className="nq-qvk__label">{k.label}</span>
          <span className="nq-qvk__source">
            {k.value === null ? CHUA_CO_DU_LIEU : k.source}
          </span>
        </li>
      ))}
    </ul>
  );
}

/** Bọc KPI trong một thẻ có tiêu đề — dùng khi cần nhấn KPI là khối riêng. */
export function ExecutiveSnapshotCard({
  kpis,
}: {
  kpis: readonly QuanverseKpi[];
}) {
  return (
    <Card label="Tình hình chung">
      <ExecutiveSnapshot kpis={kpis} />
    </Card>
  );
}
