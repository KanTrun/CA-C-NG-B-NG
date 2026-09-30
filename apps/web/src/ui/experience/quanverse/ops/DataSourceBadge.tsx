"use client";

/**
 * QUÁNVERSE — nguồn dữ liệu: NHÃN + BỘ CHỌN.
 *
 * Trả lời câu hỏi bắt buộc của trang: "dữ liệu này là thật hay mô phỏng?"
 *
 * Nhãn LUÔN hiện. Bộ chọn CHỈ hiện ở môi trường phát triển/demo — trên
 * production, người dùng không được phép bật số bịa lên màn vận hành.
 *
 * KHÔNG dùng chữ "live": backend đọc dữ liệu theo yêu cầu, không đẩy realtime.
 */

import { formatLuc } from "../../../../lib/present";
import type { QuanverseProvenance } from "../quanverse-contract";
import {
  QUANVERSE_SCENARIOS,
  QUANVERSE_SCENARIO_LABEL,
  type QuanverseScenario,
} from "../repository";

export default function DataSourceBadge({
  dataSource,
  scenario,
  updatedAt,
  provenance,
  scenarioOptions,
  canChooseSource,
  onChangeScenario,
}: {
  dataSource: "real" | "mock";
  scenario: QuanverseScenario | null;
  updatedAt: string | null;
  provenance: readonly QuanverseProvenance[];
  scenarioOptions: readonly QuanverseScenario[];
  canChooseSource: boolean;
  onChangeScenario: (s: QuanverseScenario) => void;
}) {
  const loi = provenance.filter((p) => !p.ok);
  const laMock = dataSource === "mock";
  const luaChon = scenarioOptions.length > 0 ? scenarioOptions : QUANVERSE_SCENARIOS;

  return (
    <div className="nq-qvsrc" data-testid="quanverse-source" data-nguon={dataSource}>
      <span
        className={`nq-qvsrc__badge nq-qvsrc__badge--${laMock ? "mock" : "real"}`}
        data-testid="source-badge"
      >
        <span className="nq-qvsrc__dot" aria-hidden="true" />
        {laMock ? "Mô phỏng" : "Dữ liệu thật"}
      </span>

      {laMock ? (
        <span className="nq-qvsrc__detail" data-testid="source-scenario">
          Kịch bản: “{scenario ? QUANVERSE_SCENARIO_LABEL[scenario] : "—"}”
        </span>
      ) : (
        <span className="nq-qvsrc__detail">
          Cập nhật {updatedAt ? formatLuc(updatedAt) : "—"}
        </span>
      )}

      {loi.length > 0 ? (
        <span className="nq-qvsrc__warn" data-testid="source-degraded">
          {loi.length} nguồn không đọc được
        </span>
      ) : null}

      {canChooseSource ? (
        <div className="nq-qvsrc__choose" role="group" aria-label="Chọn nguồn dữ liệu">
          <span className="nq-qvsrc__choose-label">Nguồn:</span>
          {luaChon.map((s) => (
            <button
              key={s}
              type="button"
              className={`nq-qvsrc__btn${scenario === s ? " is-on" : ""}`}
              aria-pressed={scenario === s}
              data-testid={`scenario-${s}`}
              onClick={() => onChangeScenario(s)}
            >
              {QUANVERSE_SCENARIO_LABEL[s]}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}

export function ProvenancePanel({
  provenance,
}: {
  provenance: readonly QuanverseProvenance[];
}) {
  const loi = provenance.filter((p) => !p.ok);
  if (loi.length === 0) return null;
  return (
    <div className="nq-qvprov" data-testid="quanverse-provenance">
      <strong className="nq-qvprov__title">Nguồn dữ liệu đang lỗi</strong>
      <ul className="nq-qvprov__list">
        {loi.map((p) => (
          <li key={p.endpoint}>
            <code>{p.endpoint}</code>
            <span>
              {p.label}
              {p.status ? ` · HTTP ${p.status}` : " · lỗi mạng"}
              {p.missingFields?.length ? ` · thiếu: ${p.missingFields.join(", ")}` : ""}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
