"use client";

/**
 * QUÁNVERSE — A. HEADER: tình trạng quán trong một dòng.
 *
 * Trả lời ngay: quán nào · hôm nay · ca nào · ai đang trực · hệ thống thế nào ·
 * số liệu cập nhật lúc nào.
 *
 * Không hard-code ngày giờ: mọi mốc lấy từ `ViewModel.header` (máy chủ sinh)
 * hoặc từ đồng hồ hiện tại.
 */

import { formatLuc } from "../../../../lib/present";
import { CHUA_CO_DU_LIEU, KHONG_CO_DU_LIEU, type QuanverseStoreHeader } from "../quanverse-contract";
import { NguonChip } from "./kit";

const THU_VN = ["Chủ nhật", "Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7"];

function nhanNgay(dateISO: string): string {
  const d = new Date(`${dateISO}T00:00:00`);
  if (Number.isNaN(d.getTime())) return dateISO;
  const p2 = (n: number) => String(n).padStart(2, "0");
  return `${THU_VN[d.getDay()]} · ${p2(d.getDate())}/${p2(d.getMonth() + 1)}`;
}

export default function QuanverseHeaderBlock({
  header,
  dataSource,
  scenarioLabel,
}: {
  header: QuanverseStoreHeader;
  dataSource: "real" | "mock";
  scenarioLabel: string | null;
}) {
  const soNguoi =
    header.onShiftCount !== null
      ? `${header.onShiftCount} nhân sự đang trực`
      : CHUA_CO_DU_LIEU;

  return (
    <header className="nq-qvh" data-testid="quanverse-header">
      <div className="nq-qvh__title">
        <h1>QUÁNVERSE</h1>
        <p>Trung tâm điều hành quán</p>
      </div>

      <dl className="nq-qvh__facts">
        <div className="nq-qvh__fact">
          <dt>Quán</dt>
          <dd>{header.storeName}</dd>
        </div>
        <div className="nq-qvh__fact">
          <dt>Ngày</dt>
          <dd>{nhanNgay(header.dateISO)}</dd>
        </div>
        <div className="nq-qvh__fact">
          <dt>Ca hiện tại</dt>
          <dd>{header.shiftLabel ?? CHUA_CO_DU_LIEU}</dd>
        </div>
        <div className="nq-qvh__fact">
          <dt>Đang trực</dt>
          <dd data-testid="header-onshift">
            {soNguoi}
            {header.onShiftNames.length > 0 ? (
              <span className="nq-qvh__names">
                {" · "}
                {header.onShiftNames.join(", ")}
              </span>
            ) : null}
          </dd>
        </div>
        <div className="nq-qvh__fact">
          <dt>Hệ thống</dt>
          <dd>{header.systemStatus}</dd>
        </div>
        <div className="nq-qvh__fact">
          <dt>Cập nhật</dt>
          <dd data-testid="header-updated">
            {header.updatedAt ? formatLuc(header.updatedAt) : KHONG_CO_DU_LIEU}
          </dd>
        </div>
      </dl>

      {dataSource === "mock" ? (
        <NguonChip>
          {scenarioLabel ? `Mô phỏng · ${scenarioLabel}` : "Mô phỏng"}
        </NguonChip>
      ) : null}
    </header>
  );
}
