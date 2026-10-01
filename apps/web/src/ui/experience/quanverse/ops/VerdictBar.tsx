"use client";

/**
 * QUÁNVERSE 2.0 — [1 VERDICT] Một câu duy nhất cho chủ quán/giám khảo.
 *
 * JEV judge (không bịa): verdict + p + provider + latency. Thiếu 1 phần thì
 * liệt kê đúng phần thiếu — cấm nhắc số kho khi kho chưa có.
 */

import type { QuanverseEvidence, QuanverseJev } from "../quanverse-contract";
import { formatSo, nhanCoverage } from "../quanverse-contract";
import { Card, CardHead, MucDoChip, NguonChip } from "./kit";

const TONE: Record<string, "danger" | "warn" | "ok" | "neutral"> = {
  khan_cap: "danger",
  can_xu_ly: "danger",
  theo_doi: "warn",
  binh_thuong: "ok",
};

export default function VerdictBar({
  evidence,
  jev,
}: {
  evidence: QuanverseEvidence;
  jev: QuanverseJev | null;
}) {
  const st = evidence.state;
  const tone = jev?.verdict ? (TONE[jev.verdict] ?? "neutral") : "neutral";
  const thua = (jev?.thieu ?? []).map(nhanCoverage).join(" · ");
  const canCu: string[] = [];
  if (evidence.coverage.don === "ok") canCu.push(`${formatSo(st.donDangXuLy)} đơn đang xử lý`);
  if (evidence.coverage.lich === "ok")
    canCu.push(st.nhanVienTruc !== null ? `${formatSo(st.nhanVienTruc)} người trực` : "có lịch ca");
  if (evidence.coverage.kho === "ok" && st.tonDuoiNguong.length > 0)
    canCu.push(`${st.tonDuoiNguong.length} món dưới ngưỡng`);
  if (evidence.coverage.kho === "ok" && st.tonDuoiNguong.length === 0) canCu.push("kho trong ngưỡng");

  return (
    <Card className="nq-qvverdict" tone={tone} label="Kết luận AI" testId="quanverse-verdict">
      <CardHead
        title="Quán lúc này"
        icon="info"
        trailing={
          jev?.verdict ? (
            <span className="nq-qvai__grounded is-grounded" data-testid="verdict-grounded">
              JEV {jev.provider === "jev" ? "thật" : "nền"} · p={formatSo(jev.p, { decimals: 2 })}
            </span>
          ) : (
            <span className="nq-qvai__grounded" data-testid="verdict-grounded">
              Chưa gọi JEV
            </span>
          )
        }
      />
      <div className="nq-qvverdict__row">
        {jev?.verdict ? <MucDoChip severity={tone} /> : null}
        <p className="nq-qvai__headline" data-testid="verdict-headline">
          {jev?.verdictLabel ?? "Chưa đánh giá"}
          {jev?.p !== null && jev?.p !== undefined ? ` — p=${formatSo(jev.p, { decimals: 2 })}` : ""}
        </p>
      </div>
      {canCu.length > 0 ? (
        <p className="nq-qvverdict__cancu" data-testid="verdict-evidence">
          Căn cứ: {canCu.join(" · ")}
          {st.soNgayDuLieu !== null ? ` · ${formatSo(st.soNgayDuLieu)} ngày dữ liệu` : ""}.
        </p>
      ) : null}
      {thua ? (
        <p className="nq-qvai__weak" data-testid="verdict-missing">
          Chưa đánh giá được {thua} vì chưa có dữ liệu — AI không suy đoán phần này.
        </p>
      ) : null}
      <p className="nq-qvai__provider" data-testid="verdict-provider">
        Nguồn sinh: {jev?.provider === "jev" ? `JEV thật${jev.latencyMs !== null ? ` · ${jev.latencyMs}ms` : ""}` : jev?.provider === "fallback" ? "Luật nền tất định (không JEV)" : "—"}
        {" · "}
        <NguonChip>database thật</NguonChip>
      </p>
    </Card>
  );
}
