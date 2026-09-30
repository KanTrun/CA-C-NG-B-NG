"use client";

/**
 * QUÁNVERSE — bảng năng lực trang: chức năng nào có, nguồn nào thật/mô phỏng,
 * tương tác được tới đâu. Không để người xem đoán "chỉ là demo tĩnh".
 */

import type {
  QuanverseDataSource,
  QuanverseProvenance,
  QuanverseViewModel,
} from "../quanverse-contract";
import { Card, CardHead } from "./kit";

type Hang = {
  id: string;
  chucNang: string;
  tuongTac: string;
  that: "ok" | "partial" | "mock_only" | "need_data";
  ghiChu: string;
};

function trangThaiNguon(
  provenance: readonly QuanverseProvenance[],
  label: string,
): boolean {
  const p = provenance.find((x) => x.label === label);
  return p?.ok === true;
}

export default function CapabilityBoard({
  vm,
  dataSource,
  canMock,
  onEnableMock,
}: {
  vm: QuanverseViewModel;
  dataSource: QuanverseDataSource;
  canMock: boolean;
  onEnableMock: () => void;
}) {
  const coDonThat =
    dataSource === "real" &&
    vm.kpis.find((k) => k.key === "orders")?.value !== null;
  const coDuBao = vm.capacity.hasHistory;
  const snapshotOk = trangThaiNguon(vm.provenance, "Bản chiếu vận hành");
  const stationsOk = trangThaiNguon(vm.provenance, "Tải theo khu vực");
  const askOk = dataSource === "mock" || trangThaiNguon(vm.provenance, "Tóm tắt cho AI");

  const hang: Hang[] = [
    {
      id: "map",
      chucNang: "Bản đồ khu vực + chọn zone",
      tuongTac: "Bấm zone → lọc việc / sự kiện / ZoneFocus",
      that: stationsOk || snapshotOk ? (coDonThat ? "ok" : "partial") : "need_data",
      ghiChu: coDonThat
        ? "Tải/hàng chờ từ đơn quầy thật"
        : "Chưa có đơn quầy → tải hiện \"—\", vẫn chọn zone được",
    },
    {
      id: "kpi",
      chucNang: "6 KPI điều hành",
      tuongTac: "Bấm Cảnh báo / Chờ / Việc tới → nhảy panel",
      that: dataSource === "mock" ? "ok" : coDonThat ? "ok" : "partial",
      ghiChu: "null → \"—\" (không bịa 0)",
    },
    {
      id: "actions",
      chucNang: "Cần xử lý ngay",
      tuongTac: "CTA mở lịch/kho/treo hoặc hỏi AI",
      that: dataSource === "mock" || snapshotOk ? "ok" : "partial",
      ghiChu: "Ghép tải khu vực + lịch tuần + kho + việc treo",
    },
    {
      id: "timeline",
      chucNang: "Timeline 15 phút",
      tuongTac: "Đọc horizon; lọc theo zone nếu có",
      that: snapshotOk || dataSource === "mock" ? "ok" : "need_data",
      ghiChu: "Nguồn: snapshot / fixture horizon (role-projected)",
    },
    {
      id: "capacity",
      chucNang: "Biểu đồ năng lực",
      tuongTac: "Hover/click giờ · chọn peak · prefill AI",
      that: coDuBao ? "ok" : "need_data",
      ghiChu: coDuBao
        ? "Từ lịch sử đơn quầy thật"
        : "Cần ≥1 ngày có đơn → mới vẽ đường",
    },
    {
      id: "ask",
      chucNang: "AI Copilot + hỏi grounded",
      tuongTac: "Gõ câu hỏi · chip gợi ý · citations",
      that: askOk ? "ok" : "need_data",
      ghiChu: "POST /ask — không ghi DB; không suy đoán số",
    },
    {
      id: "modes",
      chucNang: "Chế độ quán (Modes)",
      tuongTac: "Đề xuất → Xác nhận → Tắt (QL/Chủ)",
      that: "ok",
      ghiChu: "API thật ghi kv đề xuất; không tự đổi lịch/nhân sự",
    },
    {
      id: "events",
      chucNang: "Sự kiện vận hành",
      tuongTac: "Bấm nhãn zone → focus bản đồ",
      that: snapshotOk || dataSource === "mock" ? "ok" : "need_data",
      ghiChu: "Snapshot role-strip phía máy chủ",
    },
    {
      id: "staff",
      chucNang: "Nhân sự trong ca",
      tuongTac: "Chỉ đọc (header + KPI)",
      that: trangThaiNguon(vm.provenance, "Nhân sự trong ca") ||
        trangThaiNguon(vm.provenance, "Phân công tuần")
        ? "ok"
        : "need_data",
      ghiChu: "GET /staff-on-shift (+ fallback lịch tuần)",
    },
  ];

  const nhan: Record<Hang["that"], string> = {
    ok: "Chạy được",
    partial: "Chạy một phần",
    mock_only: "Chỉ mô phỏng",
    need_data: "Cần dữ liệu",
  };

  return (
    <Card className="nq-qvcapab" label="Năng lực trang" testId="quanverse-capability">
      <CardHead
        title="Trang này làm được gì"
        icon="info"
        trailing={
          <span className="nq-qvcapab__badge" data-testid="capability-source">
            {dataSource === "mock" ? "Đang xem: Mô phỏng" : "Đang xem: Dữ liệu thật"}
          </span>
        }
      />

      <p className="nq-qvcapab__lead">
        Quánverse là cockpit vận hành: cảm nhận → chọn khu vực → hỏi AI có căn cứ →
        đề xuất chế độ do người xác nhận. Không phải trang marketing và không tự
        ghi lịch.
      </p>

      <ul className="nq-qvcapab__list">
        {hang.map((h) => (
          <li
            key={h.id}
            className={`nq-qvcapab__item nq-qvcapab__item--${h.that}`}
            data-testid={`capability-${h.id}`}
            data-status={h.that}
          >
            <div className="nq-qvcapab__row">
              <strong>{h.chucNang}</strong>
              <span className={`nq-qvcapab__st nq-qvcapab__st--${h.that}`}>
                {nhan[h.that]}
              </span>
            </div>
            <p className="nq-qvcapab__tuongtac">{h.tuongTac}</p>
            <p className="nq-qvcapab__note">{h.ghiChu}</p>
          </li>
        ))}
      </ul>

      {!coDonThat && dataSource === "real" && canMock ? (
        <div className="nq-qvcapab__cta" data-testid="capability-mock-cta">
          <p>
            Quán hiện chưa có đơn quầy trong hệ thống — KPI đơn/hàng chờ và biểu đồ
            dự báo hiện &quot;—&quot; là đúng (không bịa số). Muốn pitch đủ tải cao
            điểm / quá tải, bật mô phỏng.
          </p>
          <button
            type="button"
            className="nq-qvfocus__btn"
            data-testid="capability-enable-mock"
            onClick={onEnableMock}
          >
            Bật mô phỏng để xem đủ tương tác
          </button>
        </div>
      ) : null}

      {dataSource === "mock" ? (
        <p className="nq-qvcapab__foot">
          Mô phỏng dùng cùng hợp đồng ViewModel với dữ liệu thật — tắt mô phỏng là
          quay lại API thật, không phải giao diện khác.
        </p>
      ) : (
        <p className="nq-qvcapab__foot">
          Khi có đơn quầy / phân công / kho thật: stations, forecast, KPI đơn, biểu
          đồ và cảnh báo tồn tự đầy — không cần đổi UI.
        </p>
      )}
    </Card>
  );
}
