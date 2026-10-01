"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiError, apiGet, apiSend } from "../../lib/api";
import { matchSearch } from "../../lib/list-filters";
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
import { FilteredEmpty, ListToolbar } from "../../ui/list-filters";
import { useStaffNameMap } from "../../ui/ops-pickers";
import { Alert, Btn, Empty, Loading, OpsCard, PageHeader, PagedList, StatusChip } from "../../ui/kit";

type Mon = { id: string; ten: string; gia: number; nhom?: string; hinh_url?: string };
type Dong = { mon_id: string; ten: string; so_luong: number; gia: number };
type Don = {
  id: string;
  nv_id?: string;
  trang_thai: "cho_pha" | "dang_pha" | "xong" | "huy";
  thanh_toan: "tien_mat" | "da_ck" | "chua_thu";
  dong: Dong[];
  ly_do_huy?: string | null;
  luc?: string;
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
type Nhom = { key: string; ten: string; items: Mon[] };

const MONEY = new Intl.NumberFormat("vi-VN", { style: "currency", currency: "VND", maximumFractionDigits: 0 });
const THU = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"] as const;

/** Trần số lượng một dòng = `DongDatBody.so_luong` (`le=99`) ở API. */
const MAX_SL = 99;

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
    <div className="nq-stepper">
      <button type="button" className="nq-stepper__btn" onClick={onMinus} disabled={qty < 1} aria-label={`Bớt ${label}`}>
        −
      </button>
      <span className="nq-stepper__qty" aria-live="polite" aria-label={`Số lượng ${label}`}>
        {qty}
      </span>
      <button
        type="button"
        className="nq-stepper__btn nq-stepper__btn--add"
        onClick={onPlus}
        disabled={qty >= MAX_SL}
        aria-label={`Thêm ${label}`}
      >
        +
      </button>
    </div>
  );
}

/** Giờ vào đơn rút gọn HH:MM — dùng để phân biệt hai phiếu giống nhau. */
function gioVao(luc?: string): string {
  if (!luc) return "";
  const d = new Date(luc);
  if (Number.isNaN(d.getTime())) return "";
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

/** Mã đơn rút gọn, không lộ UUID dài. */
function maDon(id: string): string {
  return id.replace(/^dq_|^demo_qv_don_/, "").slice(-4).toUpperCase();
}

/** Mốc đầu ngày theo giờ địa phương, ISO-8601 — dùng làm `?tu=` cho báo cáo. */
function dauNgay(): string {
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  return d.toISOString();
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
  // Bộ lọc menu. `nhom` rỗng = xem tất cả (đây là trạng thái mặc định, không
  // phải "lọc rỗng" — phân biệt để `FilteredEmpty` không bắt người dùng xoá lọc
  // khi thực ra chưa bật lọc nào).
  const [tim, setTim] = useState("");
  const [locNhom, setLocNhom] = useState("");
  // Bộ lọc danh sách đơn, tách riêng khỏi bộ lọc menu: lọc món không nên xoá
  // lịch sử đơn và ngược lại.
  const [timDon, setTimDon] = useState("");
  const [locTrangThai, setLocTrangThai] = useState("all");

  const tenNv = useStaffNameMap();

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
      return { list, homNay: list.some((c) => c.ngay === THU[chiSo] && (c.co_the_nha ?? false)) };
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
      // Lịch phải nạp ở ĐÂY NỮA, không chỉ trong nhánh 403. Bản trước chỉ gọi
      // `loadCa()` khi quầy khóa, nên người đã điểm danh (đa số) luôn thấy khối
      // "Hôm nay bạn không có ca" trong khi tiêu đề lại ghi "Ca đang mở" —
      // hai câu trái nhau ở cùng một thẻ.
      const { list, homNay } = await loadCa();
      setCaMine(list);
      setCoCaHomNay(homNay);
      if (isManager(getRole())) {
        // `?tu=` mốc đầu ngày: bản trước cộng TOÀN BỘ đơn từ lúc bảng còn trống
        // rồi gọi đó là "Tổng ca" — sai tên lẫn sai số.
        apiGet<BaoCao>(`/api/v1/quay/bao-cao?tu=${encodeURIComponent(dauNgay())}`)
          .then(setReport)
          .catch(() => setReport(null));
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

  /**
   * Menu gom theo nhóm món, giữ thứ tự chuẩn của quán; nhóm rỗng bị bỏ.
   *
   * Mã nhóm lạ (không có trong `NHOM_MON_THU_TU`) nay gom vào "khac" thay vì
   * bị `.filter()` loại mất. Bản trước vứt mọi món có `nhom` lạ đi im lặng —
   * chủ quán gõ tay một mã sai là món biến mất khỏi quầy, không một dòng cảnh
   * báo. API nay chặn `nhom` ngoài danh mục (`nhom_khong_hop_le`) nhưng dữ liệu
   * cũ trong DB vẫn có thể còn.
   */
  const nhomMenu = useMemo<Nhom[]>(() => {
    const buckets = new Map<string, Mon[]>();
    for (const mon of menu) {
      const raw = (mon.nhom ?? "").trim();
      const key = NHOM_MON_THU_TU.includes(raw) ? raw : "khac";
      const arr = buckets.get(key);
      if (arr) arr.push(mon);
      else buckets.set(key, [mon]);
    }
    return [...NHOM_MON_THU_TU, "khac"]
      .filter((key) => buckets.has(key))
      .map((key) => ({ key, ten: nhomMonLabel(key), items: buckets.get(key) ?? [] }));
  }, [menu]);

  /** Áp tìm kiếm + lọc nhóm. Không lọc thì giữ nguyên nhóm gốc. */
  const nhomHienThi = useMemo(() => {
    const khop = (mon: Mon) => matchSearch(mon.ten, tim);
    return nhomMenu
      .map((n) => ({ ...n, items: n.items.filter(khop) }))
      .filter((n) => n.items.length > 0 && (!locNhom || n.key === locNhom));
  }, [nhomMenu, tim, locNhom]);

  const coLocMenu = tim.trim() !== "" || locNhom !== "";
  const soMonHienThi = nhomHienThi.reduce((sum, n) => sum + n.items.length, 0);
  const xoaLocMenu = useCallback(() => {
    setTim("");
    setLocNhom("");
  }, []);

  /** Ca HÔM NAY thật sự: đúng thứ trong tuần + mở được bằng điểm danh.
      Bản trước chỉ lọc `co_the_nha` nên hiện MỌI ca trong tuần kèm nhãn cứng
      "Hôm nay · đã điểm danh" — sai cả số lượng lẫn nhãn. */
  const caHomNay = useMemo(() => {
    const jsDay = new Date().getDay();
    const chiSo = jsDay === 0 ? 6 : jsDay - 1;
    return caMine.filter((c) => c.ngay === THU[chiSo] && (c.co_the_nha ?? false));
  }, [caMine]);

  const donLoc = useMemo(() => {
    const khop = (d: Don) =>
      (locTrangThai === "all" || d.trang_thai === locTrangThai) &&
      (timDon.trim() === "" || d.dong.some((l) => matchSearch(l.ten, timDon)));
    return orders.filter(khop);
  }, [orders, locTrangThai, timDon]);

  const coLocDon = timDon.trim() !== "" || locTrangThai !== "all";
  const xoaLocDon = useCallback(() => {
    setTimDon("");
    setLocTrangThai("all");
  }, []);

  function changeQty(id: string, delta: number) {
    setCart((old) => {
      const next = Math.min(MAX_SL, Math.max(0, (old[id] ?? 0) + delta));
      const copy = { ...old };
      if (next) copy[id] = next;
      else delete copy[id];
      return copy;
    });
  }

  async function checkIn() {
    setBusy(true);
    setError(null);
    setMsg(null);
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
    setMsg(null);
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
        meta="Chạm món để thêm vào giỏ — giỏ dính bên phải. Đơn do nhân viên đang ca ghi."
      />
      {error ? <Alert>{error}</Alert> : null}
      {msg && !error ? <Alert kind="ok">{msg}</Alert> : null}
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
        ) : (
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
        )}
      </OpsCard>

      {loading ? <Loading skeleton="bento">Đang tải menu quầy…</Loading> : null}
      {!loading && menu.length === 0 ? <Empty>Chủ quán chưa mở món nào trong menu.</Empty> : null}

      {!loading && menu.length > 0 ? (
        <div className="nq-pos-layout mt-8">
          {/* ── Cột trái: menu ── */}
          <div className="min-w-0">
            <ListToolbar
              search={tim}
              onSearchChange={setTim}
              searchPlaceholder="Tìm món — có dấu hay không dấu đều ra…"
              idPrefix="nq-mon"
              status={locNhom}
              onStatusChange={setLocNhom}
              statusLabel="Nhóm món"
              statusOptions={nhomMenu.map((n) => ({
                value: n.key,
                label: `${n.ten} (${n.items.length})`,
              }))}
              shown={soMonHienThi}
              total={menu.length}
              filtered={coLocMenu}
            />

            {nhomMenu.length > 1 ? (
              <ul className="nq-pos-chips mt-3" aria-label="Lọc nhanh theo nhóm món">
                <li>
                  <button
                    type="button"
                    className={`nq-pos-chip ${locNhom === "" ? "nq-pos-chip--on" : ""}`}
                    onClick={() => setLocNhom("")}
                    aria-pressed={locNhom === ""}
                  >
                    Tất cả <span className="nq-pos-chip__dem">{menu.length}</span>
                  </button>
                </li>
                {nhomMenu.map((n) => {
                  // Chip đếm số món KHỚP TỪ KHOÁ đang gõ, không phải tổng nhóm:
                  // gõ "đá" thì chip "Cà phê" phải hiện 1 chứ không phải 10.
                  const khop = n.items.filter((m) => matchSearch(m.ten, tim)).length;
                  return (
                    <li key={n.key}>
                      <button
                        type="button"
                        className={`nq-pos-chip ${locNhom === n.key ? "nq-pos-chip--on" : ""}`}
                        onClick={() => setLocNhom((c) => (c === n.key ? "" : n.key))}
                        aria-pressed={locNhom === n.key}
                        disabled={khop === 0}
                      >
                        {n.ten} <span className="nq-pos-chip__dem">{khop}</span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            ) : null}

            {soMonHienThi === 0 ? (
              <FilteredEmpty onClear={xoaLocMenu} />
            ) : (
              nhomHienThi.map((nhom) => (
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
                          {/* Tầng trên: ảnh + tên + giá. Tách hai tầng để ô hẹp
                              trong lưới không làm stepper đè lên giá. Tầng trên
                              là NÚT THẬT nên chạm chuột lẫn bàn phím đều thêm
                              được món — bản trước gắn onClick lên <article> nên
                              chỉ nút "+" hoạt động, cả menu không tab tới được. */}
                          <button
                            type="button"
                            className="nq-pos-row__top"
                            onClick={() => changeQty(mon.id, 1)}
                            aria-label={`Thêm ${mon.ten} vào đơn`}
                          >
                            <PosThumb mon={mon} />
                            <span className="nq-pos-row__info">
                              <strong className="nq-pos-row__name">{mon.ten}</strong>
                              <span className="nq-pos-row__price">{MONEY.format(mon.gia)}</span>
                            </span>
                          </button>
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
              ))
            )}
          </div>

          {/* ── Cột phải: giỏ dính + tổng ngày ── */}
          <div className="nq-pos-side">
            <aside className="nq-pos-cart">
              <h2 className="text-sm font-mono uppercase tracking-widest">Đơn mới</h2>
              {lines.length === 0 ? (
                <p className="nq-muted mt-3 text-sm">Chạm một món bên trái để thêm vào đơn.</p>
              ) : (
                <ul className="mt-3 space-y-2 text-sm">
                  {lines.map((line) => (
                    <li
                      key={line.id}
                      className="flex items-center justify-between gap-2 border-b border-[var(--nq-line)] pb-2"
                    >
                      <span className="min-w-0">
                        {line.ten} <span className="font-mono">× {line.so_luong}</span>
                      </span>
                      <span className="shrink-0 font-mono">{MONEY.format(line.gia * line.so_luong)}</span>
                    </li>
                  ))}
                </ul>
              )}
              <p className="mt-4 text-lg font-semibold">
                Tổng: <span className="text-[var(--nq-accent)]">{MONEY.format(total)}</span>
              </p>
              <label className="mt-4 block text-sm">
                <span className="mb-1 block font-mono text-xs uppercase tracking-widest text-[var(--nq-dim)]">
                  Thanh toán
                </span>
                <select
                  className="nq-select w-full"
                  value={payment}
                  onChange={(e) => setPayment(e.target.value as Don["thanh_toan"])}
                >
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
              <aside className="nq-pos-cart" aria-label="Tổng quầy hôm nay">
                <h2 className="text-sm font-mono uppercase tracking-widest">
                  Hôm nay · {report.so_don} đơn
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
        </div>
      ) : null}

      {/* Tên khối này CỐ Ý không chứa chữ "quầy": `flows.spec.ts` dò heading
          bằng /Ghi đơn tại quầy|Quầy/i, mà tiêu đề trang đã khớp "quầy" rồi.
          Đặt tên là "Đơn ghi tại quầy" thì một trang có hai heading cùng khớp
          regex và Playwright báo strict-mode violation. */}
      <h2 className="mb-3 mt-10 text-sm font-mono uppercase tracking-widest text-[var(--nq-dim)]">
        Đơn trong ca
      </h2>
      <ListToolbar
        search={timDon}
        onSearchChange={setTimDon}
        searchPlaceholder="Tìm trong đơn — theo tên món…"
        idPrefix="nq-don"
        status={locTrangThai}
        onStatusChange={setLocTrangThai}
        statusLabel="Trạng thái"
        statusOptions={[
          { value: "all", label: "Mọi trạng thái" },
          { value: "cho_pha", label: "Chờ pha" },
          { value: "dang_pha", label: "Đang pha" },
          { value: "xong", label: "Đã xong" },
          { value: "huy", label: "Đã hủy" },
        ]}
        shown={donLoc.length}
        total={orders.length}
        filtered={coLocDon}
      />
      {!loading && orders.length === 0 ? <Empty>Chưa có đơn nào ở quầy.</Empty> : null}
      {orders.length > 0 && donLoc.length === 0 ? <FilteredEmpty onClear={xoaLocDon} /> : null}
      <PagedList
        items={donLoc}
        pageSize={12}
        renderItem={(order) => (
          <article className="nq-item">
            {/* Mã đơn + giờ vào: bản trước không có, nên hai phiếu cùng món,
                cùng số lượng là không phân biệt được với nhau. */}
            <header className="mb-2 flex items-baseline justify-between gap-2">
              <span className="font-mono text-xs uppercase tracking-widest text-[var(--nq-dim)]">
                Đơn {maDon(order.id)}
              </span>
              {gioVao(order.luc) ? (
                <span className="font-mono text-xs text-[var(--nq-dim)]">{gioVao(order.luc)}</span>
              ) : null}
            </header>
            <ul className="space-y-1">
              {order.dong.map((line, i) => (
                <li key={`${order.id}-${i}`} className="flex justify-between gap-3 text-sm font-semibold">
                  <span className="min-w-0">{line.ten}</span>
                  <span className="shrink-0 font-mono text-[var(--nq-accent)]">× {line.so_luong}</span>
                </li>
              ))}
              {order.dong.length === 0 ? (
                <li className="text-sm text-[var(--nq-dim)]">Đơn không còn dòng món nào.</li>
              ) : null}
            </ul>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <StatusChip tone={donTrangThaiTone(order.trang_thai)}>{donTrangThaiLabel(order.trang_thai)}</StatusChip>
              <span className="nq-muted text-xs">{donThanhToanLabel(order.thanh_toan)}</span>
              {order.nv_id ? <span className="nq-muted text-xs">· {tenNv(order.nv_id)}</span> : null}
            </div>
            {order.ly_do_huy ? <p className="nq-phieu__lydo mt-2">Lý do hủy: {order.ly_do_huy}</p> : null}
          </article>
        )}
        className="nq-card-grid mt-4"
      />
    </section>
  );
}
