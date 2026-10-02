"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { apiGet, apiSend } from "../../lib/api";
import { matchSearch, matchTime, TIME_FILTER_OPTIONS, uniqueSorted, type TimeFilter } from "../../lib/list-filters";
import { formatLuc, NHOM_MON_THU_TU, nhomMonLabel } from "../../lib/present";
import { getToken, isManager } from "../../lib/session";
import {
  Alert,
  AuthGate,
  Btn,
  Empty,
  Field,
  FixtureChip,
  inputClassName,
  Loading,
  NextSteps,
  Notice,
  OpsCard,
  PageHeader,
  StatusChip,
} from "../../ui/kit";
import { FilteredEmpty, ListToolbar } from "../../ui/list-filters";

/** Chặn trang kéo dài vô tận: mỗi trang 50 dòng, bấm thêm mới hiện tiếp. */
const SO_DONG_DAU = 50;

type MonLienQuan = { id: string; ten: string; nhom?: string };

/** Một dòng `tong_hop` từ máy chủ: một nguyên liệu sau khi đã gộp. */
type Tong = {
  ma: string;
  hang: string;
  nhom: string;
  don_vi: string;
  mon_lien_quan: MonLienQuan[];
  so_mon?: number;
};

/** Một lần ghi — máy chủ đã bỏ dòng hỏng và chuẩn hoá tên / đơn vị. */
type Row = {
  id?: string;
  ma: string;
  hang: string;
  nhom?: string;
  so_luong: number;
  don_vi: string;
  duoi_nguong?: boolean;
  luc?: string;
  created_at?: string;
};

type PhanHoi = {
  tong_hop?: Tong[];
  items?: Row[];
  da_bo_qua?: number;
  co_du_lieu_mau?: boolean;
  ghi?: string;
};

/** Một dòng hiển thị sau khi lọc: số liệu tính lại từ `items` đã lọc. */
type Dong = {
  ma: string;
  hang: string;
  nhom: string;
  don_vi: string;
  so_luong: number;
  so_dong: number;
  so_duoi_nguong: number;
  moi_nhat: string;
  mon_lien_quan: MonLienQuan[];
};

const LOC_NHOM_ALL = "all";
const LOC_NHOM_KHAC = "khac";

/**
 * Link món nằm trong `<td>` / `<span>` — hai chỗ này không qua được rule
 * `p a, li a` nên phải tự gắn màu + gạch chân, nếu không nó trùng màu chữ
 * thường và người dùng không biết là bấm được.
 */
const LOP_MON = "text-[var(--nq-accent)] underline decoration-dotted underline-offset-2 hover:text-[var(--nq-accent-hover)]";

function khopNhom(nhom: string, loc: string): boolean {
  if (loc === LOC_NHOM_ALL) return true;
  if (loc === LOC_NHOM_KHAC) return nhom === "";
  return nhom === loc;
}

/** Số nguyên ghi nguyên, số lẻ giữ 1 chữ số — tránh "18.000000000000004". */
function soNgon(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}

export default function TieuThuPage() {
  const [token, setToken] = useState("");
  const [tongHop, setTongHop] = useState<Tong[]>([]);
  const [items, setItems] = useState<Row[]>([]);
  const [daBoQua, setDaBoQua] = useState(0);
  const [ghi, setGhi] = useState("");
  const [coMau, setCoMau] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const [hang, setHang] = useState("");
  const [so, setSo] = useState("");
  const [donVi, setDonVi] = useState("khay");

  const [search, setSearch] = useState("");
  const [nhomF, setNhomF] = useState(LOC_NHOM_ALL);
  const [statusF, setStatusF] = useState("all");
  const [timeF, setTimeF] = useState<TimeFilter>("all");
  const [soDong, setSoDong] = useState(SO_DONG_DAU);

  useEffect(() => {
    setToken(getToken());
    if (!getToken()) setLoading(false);
  }, []);

  const load = useCallback(() => {
    if (!getToken()) return;
    apiGet<PhanHoi>("/api/v1/tieu-thu")
      .then((d) => {
        setTongHop(d.tong_hop ?? []);
        setItems(d.items ?? []);
        setDaBoQua(Number(d.da_bo_qua ?? 0));
        setGhi(String(d.ghi ?? ""));
        setCoMau(d.co_du_lieu_mau === true);
        setError(null);
      })
      .catch(() => setError("Không đọc được sổ tiêu thụ."))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (token) load();
  }, [token, load]);

  /** Đổi bộ lọc thì về 50 dòng đầu — nếu không, nút "xem thêm" của bộ lọc cũ còn đó. */
  useEffect(() => {
    setSoDong(SO_DONG_DAU);
  }, [search, nhomF, statusF, timeF]);

  /** `ma` → thông tin máy chủ đã tra sẵn (tên có dấu, nhóm, món đang bán). */
  const thongTin = useMemo(() => {
    const m = new Map<string, Tong>();
    for (const d of tongHop) m.set(d.ma, d);
    return m;
  }, [tongHop]);

  const nhomChips = useMemo(() => {
    const co = new Set(tongHop.map((d) => d.nhom).filter(Boolean));
    const nhomTrong = tongHop.some((d) => !d.nhom);
    const list = NHOM_MON_THU_TU.filter((k) => k !== "nguyen_lieu" && co.has(k)).map((k) => ({
      value: k,
      label: nhomMonLabel(k),
    }));
    return [
      { value: LOC_NHOM_ALL, label: "Tất cả" },
      ...list,
      ...(nhomTrong ? [{ value: LOC_NHOM_KHAC, label: "Chưa nhóm" }] : []),
    ];
  }, [tongHop]);

  const statusOptions = useMemo(
    () => [
      { value: "all", label: "Mọi trạng thái" },
      { value: "ok", label: "Đủ ngưỡng" },
      { value: "low", label: "Dưới ngưỡng" },
    ],
    [],
  );

  const hangGoiY = useMemo(() => uniqueSorted(items.map((i) => i.hang)), [items]);
  const duoiNguongHang = useMemo(() => uniqueSorted(items.filter((i) => i.duoi_nguong).map((i) => i.hang)), [items]);

  /** Lọc TỪNG LẦN GHI, rồi mới gộp — số trong bảng luôn là số của bộ lọc đang chọn. */
  const dong = useMemo(() => {
    const gom = new Map<string, Dong>();
    for (const it of items) {
      const info = thongTin.get(it.ma);
      const nhom = info?.nhom ?? it.nhom ?? "";
      if (!khopNhom(nhom, nhomF)) continue;
      if (!matchTime(it.luc ?? it.created_at, timeF)) continue;
      if (statusF === "low" && !it.duoi_nguong) continue;
      if (statusF === "ok" && it.duoi_nguong) continue;
      const tenMon = (info?.mon_lien_quan ?? []).map((m) => m.ten).join(" ");
      const hay = [it.hang, info?.hang ?? "", tenMon, soNgon(it.so_luong), it.don_vi, it.duoi_nguong ? "dưới ngưỡng" : ""]
        .join(" ")
        .trim();
      if (search && !matchSearch(hay, search)) continue;

      let day = gom.get(it.ma);
      if (!day) {
        day = {
          ma: it.ma,
          hang: info?.hang ?? it.hang,
          nhom,
          don_vi: info?.don_vi ?? it.don_vi,
          so_luong: 0,
          so_dong: 0,
          so_duoi_nguong: 0,
          moi_nhat: "",
          mon_lien_quan: info?.mon_lien_quan ?? [],
        };
        gom.set(it.ma, day);
      }
      day.so_luong += it.so_luong;
      day.so_dong += 1;
      if (it.duoi_nguong) day.so_duoi_nguong += 1;
      const luc = it.luc ?? it.created_at ?? "";
      if (luc > day.moi_nhat) day.moi_nhat = luc;
    }
    return [...gom.values()].sort((a, b) => b.so_luong - a.so_luong || a.hang.localeCompare(b.hang, "vi"));
  }, [items, thongTin, nhomF, statusF, timeF, search]);

  const filterActive =
    search.length > 0 || nhomF !== LOC_NHOM_ALL || statusF !== "all" || timeF !== "all";
  const hien = dong.slice(0, soDong);

  function clearFilters() {
    setSearch("");
    setNhomF(LOC_NHOM_ALL);
    setStatusF("all");
    setTimeF("all");
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!hang.trim() || !so.trim()) {
      setError("Nhập tên hàng và số lượng trước khi ghi.");
      return;
    }
    try {
      await apiSend("/api/v1/tieu-thu", { hang: hang.trim(), so_luong: Number(so), don_vi: donVi });
      setHang("");
      setSo("");
      setError(null);
      load();
    } catch {
      setError("Cần quyền quản lý để ghi số lượng.");
    }
  }

  if (!token) return <AuthGate />;

  return (
    <div className="nq-page">
      <PageHeader
        kicker="Số lượng · không kế toán"
        title="Tiêu thụ trong ca"
        meta="Đếm hàng đầu ca và cuối ca — hệ thống tự suy ra tiêu thụ trong ca. Một dòng cho mỗi nguyên liệu, chọn nhóm để lọc nhanh."
      />
      {error ? <Alert>{error}</Alert> : null}
      {daBoQua > 0 ? (
        <Alert kind="info">
          Đã bỏ qua {daBoQua} dòng dữ liệu cũ không đọc được (thiếu tên hoặc số lượng). Bỏ chứ không hiển thị ô trống.
        </Alert>
      ) : null}
      {duoiNguongHang.length > 0 ? (
        <Alert kind="info">
          Đang dưới ngưỡng: {duoiNguongHang.join(", ")}. Cảnh báo cũng hiện trên Hôm nay.
        </Alert>
      ) : null}

      {isManager() ? (
        <OpsCard eyebrow="Khu vực 1" title="Ghi kiểm kê mới">
          <p className="mb-3 text-sm text-[var(--nq-dim)]">
            Đếm số lượng nguyên liệu đang có rồi ghi vào đây — đầu ca và cuối ca mỗi ngày.
          </p>
          <form onSubmit={onSubmit}>
            <Field label="Hàng">
              <input
                className={inputClassName}
                value={hang}
                onChange={(e) => setHang(e.target.value)}
                list="hang-goi-y"
                placeholder="Ví dụ: Sữa tươi"
              />
              <datalist id="hang-goi-y">
                {hangGoiY.map((h) => (
                  <option key={h} value={h} />
                ))}
              </datalist>
            </Field>
            <Field label="Số lượng còn lại">
              <input
                className={inputClassName}
                value={so}
                onChange={(e) => setSo(e.target.value)}
                inputMode="decimal"
                placeholder="Ví dụ: 8"
              />
            </Field>
            <Field label="Đơn vị">
              <select className={inputClassName} value={donVi} onChange={(e) => setDonVi(e.target.value)}>
                <option value="khay">Khay</option>
                <option value="hop">Hộp</option>
                <option value="kg">Kg</option>
              </select>
            </Field>
            <Btn type="submit" variant="primary">
              Ghi kiểm kê
            </Btn>
          </form>
        </OpsCard>
      ) : (
        <Notice>Chỉ quản lý mới ghi số lượng. Bạn vẫn xem được lịch sử kiểm kê bên dưới.</Notice>
      )}

      <div className="flex flex-wrap gap-2 mb-6" role="group" aria-label="Lọc theo nhóm nguyên liệu">
        {nhomChips.map((o) => (
          <button
            key={o.value}
            type="button"
            onClick={() => setNhomF(o.value)}
            aria-pressed={nhomF === o.value}
            className={`nq-modebtn${nhomF === o.value ? " nq-modebtn--on" : ""}`}
          >
            {o.label}
          </button>
        ))}
      </div>

      <OpsCard eyebrow="Khu vực 2" title="Theo từng nguyên liệu" count={dong.length} countLabel="nguyên liệu">
        {coMau ? (
          <p className="mb-4">
            <FixtureChip />
          </p>
        ) : null}
        {ghi ? <p className="mb-4 text-xs text-[var(--nq-dim)]">{ghi}</p> : null}

        <ListToolbar
          idPrefix="nq-tt"
          search={search}
          onSearchChange={setSearch}
          searchPlaceholder="Tìm tên nguyên liệu hoặc món…"
          status={statusF}
          onStatusChange={setStatusF}
          statusOptions={statusOptions}
          statusLabel="Ngưỡng"
          time={timeF}
          onTimeChange={(v) => setTimeF(v as TimeFilter)}
          timeOptions={TIME_FILTER_OPTIONS}
          shown={dong.length}
          total={tongHop.length}
          filtered={filterActive}
        />

        {loading ? <Loading skeleton="table" rows={4}>Đang tải sổ tiêu thụ…</Loading> : null}

        {!loading && items.length === 0 ? <Empty title="Chưa có lần ghi">Chưa có lần kiểm kê nào.</Empty> : null}
        {!loading && items.length > 0 && dong.length === 0 ? <FilteredEmpty onClear={clearFilters} /> : null}

        {!loading && hien.length > 0 ? (
          <>
            <div className="nq-table-wrap hidden md:block">
              <table className="nq-table w-full">
                <caption className="sr-only">
                  Tiêu thụ gộp theo từng nguyên liệu: tổng đã dùng, số lần ghi, món đang dùng và ngưỡng.
                </caption>
                <thead>
                  <tr>
                    <th scope="col">Nguyên liệu</th>
                    <th scope="col" className="text-right">
                      Tổng dùng
                    </th>
                    <th scope="col" className="text-right">
                      Số lần
                    </th>
                    <th scope="col">Món liên quan</th>
                    <th scope="col">Ngưỡng</th>
                  </tr>
                </thead>
                <tbody>
                  {hien.map((d) => (
                    <tr key={d.ma} data-ma={d.ma} data-nhom={d.nhom}>
                      <th scope="row" className="font-bold">
                        {d.hang}
                        <span className="block text-xs font-normal text-[var(--nq-dim)]">{d.don_vi}</span>
                      </th>
                      <td className="text-right font-mono">{soNgon(d.so_luong)}</td>
                      <td className="text-right">
                        <span className="font-mono">{d.so_dong}</span>
                        {d.moi_nhat ? (
                          <span className="block text-xs font-normal text-[var(--nq-dim)]">
                            gần nhất {formatLuc(d.moi_nhat)}
                          </span>
                        ) : null}
                      </td>
                      <td>
                        {d.mon_lien_quan.length === 0 ? (
                          <span className="text-[var(--nq-dim)]">—</span>
                        ) : (
                          <span className="flex flex-wrap gap-x-2 gap-y-1">
                            {d.mon_lien_quan.map((m) => (
                              <Link key={m.id} href={`/menu#${m.id}`} className={LOP_MON}>
                                {m.ten}
                              </Link>
                            ))}
                          </span>
                        )}
                      </td>
                      <td>
                        {d.so_duoi_nguong > 0 ? (
                          <StatusChip tone="warn">{d.so_duoi_nguong} lần dưới ngưỡng</StatusChip>
                        ) : (
                          <span className="text-[var(--nq-dim)]">—</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="nq-list md:hidden">
              {hien.map((d) => (
                <article key={d.ma} className="nq-item" data-ma={d.ma} data-nhom={d.nhom}>
                  <div className="flex items-start justify-between gap-2">
                    <p className="nq-item-title">{d.hang}</p>
                    <p className="nq-item-sub font-mono whitespace-nowrap">
                      {soNgon(d.so_luong)} {d.don_vi}
                    </p>
                  </div>
                  <p className="nq-item-sub">
                    {d.so_dong} lần ghi
                    {d.moi_nhat ? ` · gần nhất ${formatLuc(d.moi_nhat)}` : ""}
                    {d.so_duoi_nguong > 0 ? ` · ${d.so_duoi_nguong} lần dưới ngưỡng` : ""}
                  </p>
                  {d.mon_lien_quan.length > 0 ? (
                    <p className="nq-item-sub">
                      Dùng cho:{" "}
                      {d.mon_lien_quan.map((m, i) => (
                        <span key={m.id}>
                          {i > 0 ? ", " : ""}
                          <Link href={`/menu#${m.id}`} className={LOP_MON}>
                            {m.ten}
                          </Link>
                        </span>
                      ))}
                    </p>
                  ) : null}
                </article>
              ))}
            </div>

            {dong.length > hien.length ? (
              <p className="mt-4">
                <button type="button" className="nq-btn nq-btn-ghost" onClick={() => setSoDong((n) => n + SO_DONG_DAU)}>
                  Xem thêm {Math.min(SO_DONG_DAU, dong.length - hien.length)} dòng
                </button>
              </p>
            ) : null}
          </>
        ) : null}
      </OpsCard>

      <NextSteps title="Làm gì tiếp" note="Đếm xong thì xem chỗ lệch">
        <Link href="/hao-phi" className="nq-btn nq-btn-ghost">
          Xem hao hụt theo nguyên liệu
        </Link>
        <Link href="/menu" className="nq-btn nq-btn-ghost">
          Xem công thức món
        </Link>
      </NextSteps>
    </div>
  );
}
