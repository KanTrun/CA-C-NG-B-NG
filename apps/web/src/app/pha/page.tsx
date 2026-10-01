"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { apiGet, apiSend } from "../../lib/api";
import { matchSearch } from "../../lib/list-filters";
import { donThanhToanLabel, donTrangThaiLabel, donTrangThaiTone, viError } from "../../lib/present";
import { getToken } from "../../lib/session";
import { FilteredEmpty, ListToolbar } from "../../ui/list-filters";
import { useStaffNameMap } from "../../ui/ops-pickers";
import {
    ActionRow,
    Alert,
    Btn,
    Empty,
    Field,
    Input,
    Loading,
    PageHeader,
    StatusChip,
} from "../../ui/kit";

type Dong = { mon_id?: string; ten?: string; so_luong?: number; gia?: number };
type Don = {
  id: string;
  nv_id?: string;
  trang_thai: "cho_pha" | "dang_pha" | "xong" | "huy";
  dong: Dong[];
  thanh_toan: string;
  ly_do_huy?: string | null;
  luc?: string;
};

type Cot = {
  key: string;
  buoc: string;
  ten: string;
  trang_thai: Don["trang_thai"];
  rong: string;
  chinh: "dang_pha" | "xong" | null;
  /** Đơn còn làm không giới hạn ngày: hôm qua còn dở thì hôm nay vẫn phải pha. */
  moi_truoc: boolean;
};

const COT: readonly Cot[] = [
  {
    key: "cho_pha",
    buoc: "Bước 1",
    ten: "Chờ pha",
    trang_thai: "cho_pha",
    rong: "Chưa có đơn nào chờ pha.",
    chinh: "dang_pha",
    moi_truoc: true,
  },
  {
    key: "dang_pha",
    buoc: "Bước 2",
    ten: "Đang pha",
    trang_thai: "dang_pha",
    rong: "Chưa có đơn nào đang pha.",
    chinh: "xong",
    moi_truoc: true,
  },
  {
    key: "xong",
    buoc: "Bước 3",
    ten: "Đã xong hôm nay",
    trang_thai: "xong",
    rong: "Hôm nay chưa có đơn nào hoàn tất.",
    chinh: null,
    moi_truoc: false,
  },
  {
    key: "huy",
    buoc: "",
    ten: "Đã hủy hôm nay",
    trang_thai: "huy",
    rong: "Hôm nay không có đơn nào bị hủy.",
    chinh: null,
    moi_truoc: false,
  },
];

/** Giờ vào đơn, rút gọn HH:MM — nhân viên pha nhìn mốc để biết đơn nào tới trước. */
function gioVao(luc?: string): string {
  if (!luc) return "";
  const d = new Date(luc);
  if (Number.isNaN(d.getTime())) return "";
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

/** Mã đơn rút gọn để gọi tên phiếu trên bàn pha, không lộ UUID dài. */
function maDon(id: string): string {
  return id.replace(/^dq_|^demo_qv_don_/, "").slice(-4).toUpperCase();
}

/** Mốc đầu ngày theo giờ địa phương, ISO-8601 — dùng làm `?tu=`. */
function dauNgay(): string {
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  return d.toISOString();
}

function PhieuCard({
  item,
  primary,
  busy,
  tenNv,
  onTransition,
}: {
  item: Don;
  primary: "dang_pha" | "xong";
  busy: boolean;
  tenNv: (nv: string | null | undefined) => string;
  onTransition: (trang_thai: "dang_pha" | "xong" | "huy", ly_do: string) => void;
}) {
  const [cancelling, setCancelling] = useState(false);
  const [lyDo, setLyDo] = useState("");
  const gio = gioVao(item.luc);
  const lines = item.dong ?? [];

  return (
    <article className={`nq-phieu ${item.trang_thai === "dang_pha" ? "nq-phieu--dang_pha" : ""}`}>
      <header className="nq-phieu__head">
        <span className="nq-phieu__ma">Đơn {maDon(item.id)}</span>
        <span className="nq-phieu__gio">{gio ? `${gio} · ${tenNv(item.nv_id)}` : tenNv(item.nv_id)}</span>
      </header>

      <div className="nq-phieu__body">
        {lines.length === 0 ? (
          // Đơn không còn dòng món nào. Bản trước render `× ` trống và im lặng —
          // nhân viên thấy phiếu rỗng mà không hiểu đã hỏng hay là đơn rỗng.
          // Nói thẳng ra, kèm mã đơn, để còn hủy được cho khỏi tắc.
          <p className="nq-phieu__lydo">Đơn này không còn dòng món nào — có thể do dữ liệu cũ. Hãy hủy đơn.</p>
        ) : (
          lines.map((line, i) => (
            <div key={`${item.id}-${i}`} className="nq-phieu__dong">
              <span className="nq-phieu__ten">{line.ten || "Món không rõ tên"}</span>
              <span className="nq-phieu__so">× {line.so_luong ?? 1}</span>
            </div>
          ))
        )}
        {cancelling ? (
          <div className="nq-phieu__ly-do">
            <Field label="Lý do hủy">
              <Input
                value={lyDo}
                onChange={(e) => setLyDo(e.target.value)}
                placeholder="Bắt buộc ghi lý do trước khi hủy…"
              />
            </Field>
            <ActionRow align="end">
              <Btn variant="ghost" disabled={busy} onClick={() => setCancelling(false)}>
                Bỏ qua
              </Btn>
              <Btn variant="danger" busy={busy} onClick={() => onTransition("huy", lyDo)}>
                Xác nhận hủy
              </Btn>
            </ActionRow>
          </div>
        ) : null}
      </div>

      <footer className="nq-phieu__foot">
        <StatusChip tone={donTrangThaiTone(item.trang_thai)}>{donTrangThaiLabel(item.trang_thai)}</StatusChip>
        <span className="nq-muted text-xs">{donThanhToanLabel(item.thanh_toan)}</span>
        {!cancelling ? (
          <div className="ml-auto flex flex-wrap gap-2">
            <Btn variant="ghost" disabled={busy} onClick={() => setCancelling(true)}>
              Hủy đơn
            </Btn>
            <Btn busy={busy} onClick={() => onTransition(primary, "")}>
              {primary === "dang_pha" ? "Nhận pha" : "Hoàn tất"}
            </Btn>
          </div>
        ) : null}
      </footer>
    </article>
  );
}

function PhieuDaXong({ item }: { item: Don }) {
  const lines = item.dong ?? [];
  return (
    <article className="nq-phieu">
      <header className="nq-phieu__head">
        <span className="nq-phieu__ma">Đơn {maDon(item.id)}</span>
        {gioVao(item.luc) ? <span className="nq-phieu__gio">{gioVao(item.luc)}</span> : null}
      </header>
      <div className="nq-phieu__body">
        {lines.map((line, i) => (
          <div key={`${item.id}-${i}`} className="nq-phieu__dong">
            <span className="nq-phieu__ten">{line.ten || "Món không rõ tên"}</span>
            <span className="nq-phieu__so">× {line.so_luong ?? 1}</span>
          </div>
        ))}
      </div>
      <footer className="nq-phieu__foot">
        <StatusChip tone={donTrangThaiTone(item.trang_thai)}>{donTrangThaiLabel(item.trang_thai)}</StatusChip>
        <span className="nq-muted text-xs">{donThanhToanLabel(item.thanh_toan)}</span>
      </footer>
    </article>
  );
}

function PhieuDaHuy({ item }: { item: Don }) {
  const lines = item.dong ?? [];
  return (
    <article className="nq-phieu nq-phieu--huy">
      <header className="nq-phieu__head">
        <span className="nq-phieu__ma">Đơn {maDon(item.id)}</span>
        {gioVao(item.luc) ? <span className="nq-phieu__gio">{gioVao(item.luc)}</span> : null}
      </header>
      <div className="nq-phieu__body">
        {lines.map((line, i) => (
          <div key={`${item.id}-${i}`} className="nq-phieu__dong">
            <span className="nq-phieu__ten">{line.ten || "Món không rõ tên"}</span>
            <span className="nq-phieu__so">× {line.so_luong ?? 1}</span>
          </div>
        ))}
        {item.ly_do_huy ? <p className="nq-phieu__lydo">Lý do hủy: {item.ly_do_huy}</p> : null}
      </div>
      <footer className="nq-phieu__foot">
        <StatusChip tone={donTrangThaiTone(item.trang_thai)}>{donTrangThaiLabel(item.trang_thai)}</StatusChip>
      </footer>
    </article>
  );
}

export default function PhaPage() {
  const [token, setToken] = useState("");
  const [items, setItems] = useState<Don[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [checkInBusy, setCheckInBusy] = useState(false);
  const [tim, setTim] = useState("");
  // Mặc định mở hai cột việc đang chạy; hai cột lịch sử thu gọn để không chiếm
  // chỗ của hàng đợi. Người dùng tự thay đổi được sau đó.
  const [mo, setMo] = useState<Record<string, boolean>>({ cho_pha: true, dang_pha: true, xong: false, huy: false });
  const tenNv = useStaffNameMap();

  const load = useCallback(async () => {
    if (!getToken()) return;
    setLoading(true);
    try {
      const out = await apiGet<{ items: Don[] }>("/api/v1/quay/don");
      setItems(out.items ?? []);
      setError(null);
    } catch (e) {
      setError(
        viError(e, { doing: "mở màn hình pha", forbidden: "Cần điểm danh ca trước khi mở màn hình pha." }),
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => setToken(getToken()), []);
  useEffect(() => {
    if (token) void load();
  }, [load, token]);

  async function checkIn() {
    setCheckInBusy(true);
    setError(null);
    try {
      await apiSend("/api/v1/diem-danh");
      await load();
    } catch (e) {
      setError(viError(e, { doing: "điểm danh ca" }));
    } finally {
      setCheckInBusy(false);
    }
  }

  async function transition(id: string, trang_thai: "dang_pha" | "xong" | "huy", ly_do: string) {
    if (trang_thai === "huy" && !ly_do.trim()) {
      setError("Cần ghi lý do trước khi hủy đơn.");
      return;
    }
    setBusyId(id);
    try {
      await apiSend(`/api/v1/quay/don/${id}/chuyen`, { trang_thai, ly_do_huy: ly_do });
      // Xoá lỗi cũ sau khi chuyển thành công — bản trước chỉ xoá trong `load()`
      // nên thông báo lỗi của lần bấm trước treo nguyên trên bảng tới lần
      // nạp kế tiếp, nhân viên tưởng lệnh vừa thao tác bị lỗi.
      setError(null);
      await load();
    } catch (e) {
      setError(viError(e, { doing: "chuyển trạng thái đơn" }));
    } finally {
      setBusyId("");
    }
  }

  const donLoc = useMemo(
    () => (tim.trim() === "" ? items : items.filter((d) => (d.dong ?? []).some((l) => matchSearch(l.ten ?? "", tim)))),
    [items, tim],
  );

  // Cột chờ pha / đang pha: CŨ TRƯỚC (đơn nào tới trước thì pha trước, không bỏ
  // sót đơn nằm dưới đáy). Cột đã xong / đã hủy: MỚI TRƯỚC.
  const theoCot = useMemo(() => {
    const moc = (d: Don) => Date.parse(d.luc ?? "") || 0;
    const bang = new Map<string, Don[]>();
    for (const cot of COT) {
      const nhom = donLoc.filter((d) => d.trang_thai === cot.trang_thai);
      nhom.sort((a, b) => (cot.moi_truoc ? moc(a) - moc(b) : moc(b) - moc(a)));
      bang.set(cot.key, nhom);
    }
    return bang;
  }, [donLoc]);

  const coLoc = tim.trim() !== "";
  const xoaLoc = useCallback(() => setTim(""), []);
  const tatCaDong = COT.every((c) => mo[c.key]);
  const doiTatCa = () => setMo(Object.fromEntries(COT.map((c) => [c.key, !tatCaDong])));

  if (!token) return null;

  return (
    <section className="nq-page nq-page--wide">
      <PageHeader
        kicker="KDS nội bộ"
        title="Màn hình pha chế"
        meta="Hàng đợi chung của cả ca: chờ pha → đang pha → đã xong. Đơn cũ nhất nằm trên cùng."
      />
      {error ? (
        <Alert>
          {error}{" "}
          {/* 403 ở đây chỉ có một nghĩa: chưa điểm danh. Bản trước chỉ hiện một
              dòng cảnh báo rồi bỏ mặc ba cột trống — nhân viên pha không có cách
              sửa ngay tại chỗ, phải đi tìm trang khác. */}
          <Btn onClick={() => void checkIn()} busy={checkInBusy}>
            Điểm danh để mở bàn pha
          </Btn>
        </Alert>
      ) : null}
      {loading ? <Loading skeleton="rows">Đang tải hàng chờ pha…</Loading> : null}

      {!loading ? (
        <>
          <div className="mt-4 flex flex-wrap items-end gap-3">
            <div className="min-w-[16rem] flex-1">
              <ListToolbar
                search={tim}
                onSearchChange={setTim}
                searchPlaceholder="Tìm đơn — theo tên món…"
                idPrefix="nq-pha"
                shown={donLoc.length}
                total={items.length}
                filtered={coLoc}
              />
            </div>
            <Btn variant="ghost" onClick={doiTatCa}>
              {tatCaDong ? "Thu gọn tất cả" : "Mở tất cả"}
            </Btn>
          </div>

          {coLoc && donLoc.length === 0 ? (
            <div className="mt-4">
              <FilteredEmpty onClear={xoaLoc} />
            </div>
          ) : (
            <div className="nq-columns nq-columns--kds mt-4">
              {COT.map((cot) => {
                const ds = theoCot.get(cot.key) ?? [];
                const dangMo = mo[cot.key] ?? true;
                return (
                  /* `OpsCard` không khai `className` nên phần khuôn của cột đặt
                     bằng lớp riêng ở `nq-kds-col-wrap` (xem pos.css). Không truyền
                     `title`/`count` vào `OpsCard` vì nó tự vẽ một tiêu đề nữa —
                     đó chính là lý do bản trước đọc như hai tiêu đề chồng lên
                     nhau ("Bước 2" / "Đang pha" tách rời, không ra một nhãn). */
                  <div key={cot.key} className="nq-kds-col-wrap">
                    <div className="nq-kds-col-head">
                      {cot.buoc ? <p className="nq-eyebrow text-[var(--nq-dim)]">{cot.buoc}</p> : null}
                      <button
                        type="button"
                        className="nq-kds-toggle"
                        aria-expanded={dangMo}
                        onClick={() => setMo((m) => ({ ...m, [cot.key]: !dangMo }))}
                      >
                        <span className="nq-kds-toggle__muc" aria-hidden="true">
                          ▾
                        </span>
                        <span className="nq-kds-toggle__ten">{cot.ten}</span>
                        <span className="nq-kds-toggle__dem">{ds.length} đơn</span>
                      </button>
                    </div>
                    <div className={`nq-kds-col ${dangMo ? "" : "nq-kds-col--collapsed"}`}>
                      {dangMo ? (
                        <div className="nq-kds-col__body">
                          {ds.length === 0 ? (
                            <Empty title="Cột trống">{cot.rong}</Empty>
                          ) : (
                            <div className="space-y-3">
                              {ds.map((item) =>
                                cot.key === "xong" ? (
                                  <PhieuDaXong key={item.id} item={item} />
                                ) : cot.key === "huy" ? (
                                  <PhieuDaHuy key={item.id} item={item} />
                                ) : (
                                  <PhieuCard
                                    key={item.id}
                                    item={item}
                                    primary={cot.chinh ?? "xong"}
                                    busy={busyId === item.id}
                                    tenNv={tenNv}
                                    onTransition={(tt, lyDo) => void transition(item.id, tt, lyDo)}
                                  />
                                ),
                              )}
                            </div>
                          )}
                        </div>
                      ) : null}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </>
      ) : null}
    </section>
  );
}
