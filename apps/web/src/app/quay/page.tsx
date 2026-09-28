"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiError, apiGet, apiSend } from "../../lib/api";
import { menuImageUrl } from "../../lib/menu-image";
import {
  donThanhToanLabel,
  donTrangThaiLabel,
  donTrangThaiTone,
  khungLabel,
  NHOM_MON_THU_TU,
  nhomMonLabel,
  viError,
} from "../../lib/present";
import { getRole, getToken, isManager } from "../../lib/session";
import { ActionRow, Alert, Btn, Empty, Loading, OpsCard, PageHeader, StatusChip } from "../../ui/kit";

type Mon = { id: string; ten: string; gia: number; nhom?: string; hinh_url?: string };
type Dong = { mon_id: string; ten: string; so_luong: number; gia: number };
type Don = {
  id: string;
  trang_thai: "cho_pha" | "dang_pha" | "xong" | "huy";
  thanh_toan: "tien_mat" | "da_ck" | "chua_thu";
  dong: Dong[];
  ly_do_huy?: string | null;
};
type BaoCao = { so_don: number; tong_ly: number; tong_tien: number; chua_thu: number };
type Ca = {
  id: string;
  ngay: string;
  bat_dau: string;
  ket_thuc: string;
  vi_tri?: string;
  khung?: string;
  co_the_nha?: boolean;
  co_the_nhan?: boolean;
};
type LichToi = { nv_id: string; tuan_iso: string; ca: Ca[]; items?: Ca[] };

const MONEY = new Intl.NumberFormat("vi-VN", { style: "currency", currency: "VND", maximumFractionDigits: 0 });
const THU = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"] as const;

function PosThumb({ mon }: { mon: Mon }) {
  const [err, setErr] = useState(false);
  return (
    <div className="h-14 w-14 shrink-0 overflow-hidden rounded-md border border-[var(--nq-line)] bg-[var(--nq-surface-hi)]">
      {!err ? (
        <img
          src={menuImageUrl(mon.id, mon.hinh_url)}
          alt=""
          className="h-full w-full object-cover"
          onError={() => setErr(true)}
        />
      ) : (
        <div className="flex h-full items-center justify-center text-lg font-semibold text-[var(--nq-accent)]">
          {mon.ten.slice(0, 1)}
        </div>
      )}
    </div>
  );
}

function QtyStepper({
  qty,
  onMinus,
  onPlus,
  label,
}: {
  qty: number;
  onMinus: () => void;
  onPlus: () => void;
  label: string;
}) {
  return (
    <div className="nq-stepper" aria-label={label}>
      <button type="button" className="nq-stepper__btn" onClick={onMinus} disabled={qty < 1} aria-label={`Bớt ${label}`}>
        −
      </button>
      <span className="nq-stepper__qty" aria-live="polite">
        {qty}
      </span>
      <button type="button" className="nq-stepper__btn nq-stepper__btn--add" onClick={onPlus} aria-label={`Thêm ${label}`}>
        +
      </button>
    </div>
  );
}

/**
 * Ghi chú thiết kế: trang này KHÔNG có nút Nhận/Nhả ca, có chủ đích.
 *
 * Trang này là "Ghi đơn tại quầy". Việc nhận/nhả ca thuộc `/toi` (ca của tôi) và
 * `/doi-ca` (chợ đổi ca — nơi có đồng thuận hai bên và quản lý duyệt). Bản trước
 * liệt kê MỌI ca trong tuần mà người dùng chưa nằm trong đó kèm nút nhận, nên
 * trang ghi đơn hiện ra hàng chục thẻ ca không liên quan — và vì `co_the_nhan`
 * đúng với mọi ca trống, con số đó bằng số ca của cả tuần.
 *
 * Khối ca ở đây chỉ để trả lời một câu: "hôm nay mình trực ca nào".
 */
export default function QuayPage() {
  const [token, setToken] = useState("");
  const [role, setRole] = useState("");
  const [menu, setMenu] = useState<Mon[]>([]);
  const [orders, setOrders] = useState<Don[]>([]);
  const [cart, setCart] = useState<Record<string, number>>({});
  const [payment, setPayment] = useState<Don["thanh_toan"]>("chua_thu");
  const [report, setReport] = useState<BaoCao | null>(null);
  const [checkedIn, setCheckedIn] = useState(false);
  const [caMine, setCaMine] = useState<Ca[]>([]);
  // Tách khỏi `checkedIn`: "hôm nay có ca" KHÁC "đã điểm danh". Cổng mở quầy ở
  // API (`_require_dang_ca`) chỉ chấp nhận `da_diem_danh`, nên có ca mà chưa
  // điểm danh vẫn bị 403 — gộp hai thứ làm một sẽ khiến UI báo "Ca đang mở"
  // trong khi nút gửi đơn chết. Xem bug QA đợt 5.
  const [coCaHomNay, setCoCaHomNay] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  /*
    Lịch của chính tôi (`GET /api/v1/toi/lich`) — CHỈ để hiển thị khối ca hôm nay.
    KHÔNG dùng để suy ra quầy đã mở: cổng mở quầy ở API (`_require_dang_ca`) đòi
    `da_diem_danh`, không phải "hôm nay có ca". Trả về `true` khi hôm nay có ca
    của mình, để hàm gọi không phải tự so ngày.
  */
  const loadCa = useCallback(async (): Promise<{ list: Ca[]; homNay: boolean }> => {
    try {
      const out = await apiGet<LichToi>("/api/v1/toi/lich");
      const list = out.ca ?? out.items ?? [];
      // `ngay` là nhãn thứ (T2..CN), không phải ngày tháng → quy về chỉ số hôm nay.
      const jsDay = new Date().getDay();
      const chiSo = jsDay === 0 ? 6 : jsDay - 1;
      return { list, homNay: list.some((c) => c.ngay === THU[chiSo]) };
    } catch {
      return { list: [], homNay: false };
    }
  }, []);

  const load = useCallback(async () => {
    if (!getToken()) return;
    setLoading(true);
    try {
      const [menuOut, orderOut] = await Promise.all([
        apiGet<{ items: Mon[] }>("/api/v1/menu"),
        apiGet<{ items: Don[] }>("/api/v1/quay/don"),
      ]);
      setMenu(menuOut.items ?? []);
      setOrders(orderOut.items ?? []);
      setCheckedIn(true);
      if (isManager(getRole())) {
        apiGet<BaoCao>("/api/v1/quay/bao-cao").then(setReport).catch(() => setReport(null));
      }
      setError(null);
    } catch (e) {
      if (e instanceof ApiError && e.status === 403) {
        // Quầy khóa: vẫn nạp menu + lịch để nhân viên thấy mình có ca nào.
        const { list, homNay } = await loadCa();
        setCaMine(list);
        setCoCaHomNay(homNay);
        // 403 ở đây CHỈ có một nghĩa: `chua_diem_danh` (`_require_dang_ca`).
        // Không được suy ra "đã mở quầy" từ việc hôm nay có ca.
        setCheckedIn(false);
        try {
          const menuOut = await apiGet<{ items: Mon[] }>("/api/v1/menu");
          setMenu(menuOut.items ?? []);
        } catch {
          setError(viError(e, { doing: "mở quầy" }));
        }
      } else {
        setError(viError(e, { doing: "mở quầy" }));
      }
    } finally {
      setLoading(false);
    }
  }, [loadCa]);

  useEffect(() => {
    setToken(getToken());
    setRole(getRole());
  }, []);
  useEffect(() => {
    if (token) void load();
  }, [token, load]);

  const lines = useMemo(
    () => menu.filter((m) => cart[m.id]).map((m) => ({ ...m, so_luong: cart[m.id] })),
    [cart, menu],
  );
  const total = lines.reduce((sum, line) => sum + line.gia * line.so_luong, 0);

  /** Menu gom theo nhóm món, giữ thứ tự chuẩn của quán; nhóm rỗng bị bỏ. */
  const nhomMenu = useMemo(() => {
    const buckets = new Map<string, Mon[]>();
    for (const mon of menu) {
      const key = mon.nhom && mon.nhom.trim() ? mon.nhom : "khac";
      const arr = buckets.get(key);
      if (arr) arr.push(mon);
      else buckets.set(key, [mon]);
    }
    return [...NHOM_MON_THU_TU, "khac"]
      .filter((key) => buckets.has(key))
      .map((key) => ({ key, ten: nhomMonLabel(key), items: buckets.get(key) ?? [] }));
  }, [menu]);

  const caHomNay = caMine.filter((c) => c.co_the_nha ?? false);

  function changeQty(id: string, delta: number) {
    setCart((old) => {
      const next = Math.max(0, (old[id] ?? 0) + delta);
      const copy = { ...old };
      if (next) copy[id] = next;
      else delete copy[id];
      return copy;
    });
  }

  async function checkIn() {
    setBusy(true);
    setError(null);
    try {
      await apiSend("/api/v1/diem-danh");
      setMsg("Đã điểm danh ca. Bạn có thể ghi đơn tại quầy.");
      await load();
    } catch (e) {
      setError(viError(e, { doing: "điểm danh ca" }));
    } finally {
      setBusy(false);
    }
  }

  async function createOrder() {
    if (!lines.length) return;
    setBusy(true);
    setError(null);
    try {
      await apiSend("/api/v1/quay/don", {
        dong: lines.map((line) => ({ mon_id: line.id, so_luong: line.so_luong })),
        thanh_toan: payment,
      });
      setCart({});
      setMsg("Đơn đã vào hàng chờ pha.");
      await load();
    } catch (e) {
      setError(viError(e, { doing: "ghi đơn quầy", forbidden: "Cần điểm danh ca trước khi ghi đơn." }));
    } finally {
      setBusy(false);
    }
  }

  if (!token) return null;
  return (
    <section className="nq-page nq-page--wide">
      <PageHeader
        kicker="Quầy nội bộ"
        title="Ghi đơn tại quầy"
        meta="Chạm món để thêm — giỏ cố định bên phải. Đơn do nhân viên đang ca ghi."
      />
      {error ? <Alert>{error}</Alert> : null}
      {msg ? <Alert kind="ok">{msg}</Alert> : null}
      {!checkedIn ? (
        <Alert kind="info">
          {coCaHomNay
            ? "Quầy đang khóa: bạn có ca hôm nay nhưng chưa điểm danh."
            : "Quầy đang khóa: bạn chưa điểm danh và hôm nay chưa có ca nào trong lịch."}{" "}
          <Btn onClick={() => void checkIn()} busy={busy}>
            Điểm danh để mở quầy
          </Btn>
        </Alert>
      ) : null}

      {/* Đếm theo SỐ CA HIỆN RA, không theo cả tuần: thẻ chỉ vẽ ca hôm nay. */}
      <OpsCard
        eyebrow="Ca làm việc"
        title={checkedIn ? "Ca đang mở" : "Chưa mở ca"}
        count={caHomNay.length}
        countLabel="ca hôm nay"
      >
        {caHomNay.length === 0 ? (
          <Empty title="Hôm nay bạn không có ca">
            Lịch của bạn cho hôm nay đang trống. Muốn đổi hoặc nhận thêm ca, mở «Ca của tôi»
            hoặc «Chợ đổi ca».
          </Empty>
        ) : null}
        {caHomNay.length ? (
          <>
            <p className="mb-2 font-mono text-xs uppercase tracking-widest text-[var(--nq-dim)]">Ca hôm nay của bạn</p>
            <ul className="nq-ca-strip" aria-label="Ca hôm nay của bạn">
              {caHomNay.map((ca) => (
                <li key={ca.id} className="nq-ca-strip__item nq-ca-strip__item--hom-nay">
                  <span className="nq-ca-strip__khung">{khungLabel(ca.khung) || "Ca hôm nay"}</span>
                  <p className="nq-ca-strip__gio">
                    {ca.bat_dau} – {ca.ket_thuc}
                  </p>
                  <p className="nq-ca-strip__meta">
                    {checkedIn ? "Hôm nay · đã điểm danh" : "Hôm nay · chưa điểm danh"}
                  </p>
                </li>
              ))}
            </ul>
          </>
        ) : null}
      </OpsCard>

      {loading ? <Loading skeleton="bento">Đang tải menu quầy…</Loading> : null}
      {!loading && menu.length === 0 ? <Empty>Chủ quán chưa mở món nào trong menu.</Empty> : null}
      {!loading ? (
        <div className="mt-8">
          {nhomMenu.map((nhom) => (
            <section key={nhom.key} className="nq-pos-nhom" aria-label={nhom.ten}>
              <div className="nq-pos-nhom__head">
                <h3 className="nq-pos-nhom__ten">{nhom.ten}</h3>
                <span className="nq-pos-nhom__dem">{nhom.items.length} món</span>
              </div>
              <div className="nq-pos-menu">
                {nhom.items.map((mon) => {
                  const qty = cart[mon.id] ?? 0;
                  return (
                    <article key={mon.id} className={`nq-pos-row ${qty ? "nq-pos-row--on" : ""}`}>
                      {/* Tầng trên: ảnh + tên + giá. Tầng dưới: stepper. Tách hai
                          tầng để ô hẹp trong lưới không làm stepper đè lên giá. */}
                      <div className="nq-pos-row__top">
                        <PosThumb mon={mon} />
                        <div className="nq-pos-row__info">
                          <strong className="nq-pos-row__name">{mon.ten}</strong>
                          <p className="nq-pos-row__price">{MONEY.format(mon.gia)}</p>
                        </div>
                      </div>
                      <QtyStepper
                        qty={qty}
                        label={mon.ten}
                        onMinus={() => changeQty(mon.id, -1)}
                        onPlus={() => changeQty(mon.id, 1)}
                      />
                    </article>
                  );
                })}
              </div>
            </section>
          ))}
        </div>
      ) : null}

      <div className="nq-pos-shell mt-8">
        <aside className="nq-pos-cart">
          <h2 className="text-sm font-mono uppercase tracking-widest">Đơn mới</h2>
          {lines.length === 0 ? <p className="nq-muted mt-3 text-sm">Chọn món từ menu bên trên.</p> : null}
          <ul className="mt-3 space-y-2 text-sm">
            {lines.map((line) => (
              <li key={line.id} className="flex justify-between gap-2 border-b border-[var(--nq-line)] pb-2">
                <span>
                  {line.ten} × {line.so_luong}
                </span>
                <span className="font-mono">{MONEY.format(line.gia * line.so_luong)}</span>
              </li>
            ))}
          </ul>
          <p className="mt-4 text-lg font-semibold">
            Tổng: <span className="text-[var(--nq-accent)]">{MONEY.format(total)}</span>
          </p>
          <label className="mt-4 block text-sm">
            <span className="mb-1 block font-mono text-xs uppercase tracking-widest text-[var(--nq-dim)]">Thanh toán</span>
            <select className="nq-select w-full" value={payment} onChange={(e) => setPayment(e.target.value as Don["thanh_toan"])}>
              <option value="chua_thu">{donThanhToanLabel("chua_thu")}</option>
              <option value="tien_mat">{donThanhToanLabel("tien_mat")}</option>
              <option value="da_ck">{donThanhToanLabel("da_ck")}</option>
            </select>
          </label>
          <div className="mt-4">
            <Btn
              type="button"
              onClick={() => void createOrder()}
              busy={busy}
              disabled={!checkedIn || !lines.length}
              block
            >
              Gửi sang pha chế
            </Btn>
          </div>
        </aside>

        {report && role !== "nhan_vien" ? (
          <aside className="nq-pos-cart" aria-label="Tổng quầy">
            <h2 className="text-sm font-mono uppercase tracking-widest">
              Tổng ca · {report.so_don} đơn
            </h2>
            <ul className="mt-3 space-y-2 text-sm">
              <li className="flex justify-between gap-2">
                <span className="nq-muted">Số ly đã bán</span>
                <span className="font-mono">{report.tong_ly}</span>
              </li>
              <li className="flex justify-between gap-2">
                <span className="nq-muted">Doanh thu</span>
                <span className="font-mono">{MONEY.format(report.tong_tien)}</span>
              </li>
              <li className="flex justify-between gap-2">
                <span className="nq-muted">Còn chưa thu</span>
                <span className="font-mono text-[var(--nq-st-warn)]">{MONEY.format(report.chua_thu)}</span>
              </li>
            </ul>
          </aside>
        ) : null}
      </div>

      <h2 className="mb-3 mt-10 text-sm font-mono uppercase tracking-widest text-[var(--nq-dim)]">Đơn của ca</h2>
      {!loading && orders.length === 0 ? <Empty>Chưa có đơn nào trong ca của bạn.</Empty> : null}
      <div className="nq-card-grid">
        {orders.map((order) => (
          <article key={order.id} className="nq-item">
            <ul className="space-y-1">
              {order.dong.map((line, i) => (
                <li key={`${order.id}-${i}`} className="flex justify-between gap-3 text-sm font-semibold">
                  <span className="min-w-0">{line.ten}</span>
                  <span className="shrink-0 font-mono text-[var(--nq-accent)]">× {line.so_luong}</span>
                </li>
              ))}
            </ul>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <StatusChip tone={donTrangThaiTone(order.trang_thai)}>{donTrangThaiLabel(order.trang_thai)}</StatusChip>
              <span className="nq-muted text-xs">{donThanhToanLabel(order.thanh_toan)}</span>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
