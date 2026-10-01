"use client";

/**
 * QUÁNVERSE 2.0 — [S3] Trống hoàn toàn: KHÔNG gọi JEV, không đoán.
 *
 * Đây là behavior demo, không phải lỗi: checklist 3 nguồn + CTA tới nghiệp vụ
 * thật + Demo Setup ẩn cho manager.
 */

import Link from "next/link";
import type { QuanverseEvidence } from "../quanverse-contract";
import { nhanCoverage } from "../quanverse-contract";
import { Card, CardHead } from "./kit";

const NGUON_HREF: Record<string, string> = {
  don: "/quay",
  lich: "/lich-tuan",
  kho: "/tieu-thu",
};

const NGUON_CTA: Record<string, string> = {
  don: "Ghi đơn đầu",
  lich: "Mở Lịch tuần",
  kho: "Nhập kho",
};

export default function InsufficientCard({
  evidence,
  isManager,
  demoBusy,
  onDemoSetup,
}: {
  evidence: QuanverseEvidence | null;
  isManager: boolean;
  demoBusy: boolean;
  onDemoSetup: () => void;
}) {
  const keys = ["don", "lich", "kho"] as const;
  return (
    <Card className="nq-qvempty" tone="warn" label="Chưa đủ dữ liệu" testId="quanverse-insufficient">
      <CardHead title="Chưa đủ dữ liệu" icon="warn" />
      <p className="nq-qv-trong__text" data-testid="insufficient-headline">
        🟡 CHƯA ĐỦ DỮ LIỆU — Quanverse chưa thể đánh giá vì chưa có dữ liệu vận hành.
      </p>
      <p className="nq-qv-trong__hint">
        Quanverse không đoán khi không có căn cứ. Cần tối thiểu 1 trong 3 nguồn dưới đây.
      </p>
      <ul className="nq-qvempty__list" data-testid="insufficient-checklist">
        {keys.map((k) => {
          const ok = evidence?.coverage[k] === "ok";
          return (
            <li key={k} className="nq-qvempty__item" data-co={ok ? "ok" : "thieu"}>
              <span>{ok ? "✓" : "❌"} {nhanCoverage(k)}</span>
              <span className="nq-qvempty__st">{ok ? "Đã có" : "Chưa có"}</span>
              <Link className="nq-qvact__cta" href={NGUON_HREF[k]}>
                {NGUON_CTA[k]}
              </Link>
            </li>
          );
        })}
      </ul>
      {isManager ? (
        <div className="nq-qvempty__demo">
          <p className="nq-qv-trong__hint">
            Dành cho chủ quán/admin: nạp dữ liệu demo BẰNG bản ghi nghiệp vụ thật (không phải mock
            của Quanverse).
          </p>
          <button
            type="button"
            className="nq-qvfocus__btn"
            data-testid="demo-setup-btn"
            disabled={demoBusy}
            onClick={onDemoSetup}
          >
            {demoBusy ? "Đang chuẩn bị…" : "⚙ Chuẩn bị dữ liệu demo"}
          </button>
        </div>
      ) : null}
    </Card>
  );
}
