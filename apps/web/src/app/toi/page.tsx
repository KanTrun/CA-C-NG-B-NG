"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiError, apiGet, apiSend } from "../../lib/api";
import { khungLabel, viTriLabel } from "../../lib/present";
import { getToken } from "../../lib/session";
import {
  Alert,
  AuthGate,
  Btn,
  BtnLink,
  ConfirmDialog,
  Empty,
  Input,
  Loading,
  OpsCard,
  PageHeader,
  StatusChip,
} from "../../ui/kit";

type Ca = {
  id: string;
  ngay: string;
  bat_dau: string;
  ket_thuc: string;
  vi_tri: string;
  khung?: string;
  trang_thai?: string;
  co_the_nha?: boolean;
  co_the_nhan?: boolean;
  nguoi_khac_trong_ca?: string[];
  so_nguoi_trong_ca?: number;
};

/** Tóm tắt do server sinh — nói rõ tuần đang ở đâu và tôi cần làm gì. */
type TomTat = {
  tuan_iso: string;
  trang_thai: string;
  trang_thai_label: string;
  da_cong_bo: boolean;
  tinh_trang: string;
  so_ca_cua_toi: number;
  so_ca_co_the_nhan: number;
  so_rang_buoc_da_duyet: number;
  can_lam: string;
};

type RangBuoc = { id?: string; y_dinh?: string; ghi?: string };

type ToiLichOut = {
  ca?: Ca[];
  tuan_iso?: string;
  trang_thai?: string;
  da_cong_bo?: boolean;
  tom_tat?: TomTat;
  rang_buoc_da_duyet?: RangBuoc[];
};

const THU: Record<number, string> = {
  0: "CN",
  1: "T2",
  2: "T3",
  3: "T4",
  4: "T5",
  5: "T6",
  6: "T7",
};

const Y_DINH_LABEL: Record<string, string> = {
  xin_nghi: "Xin nghỉ",
  cap_nhat_tkb: "Cập nhật lịch bận",
  bao_tre: "Báo trễ",
  doi_ca: "Đổi ca",
  nhan_ca: "Nhận ca",
};

/** Nhãn bước vòng đời tuần — khớp giá trị server gửi trong `detail` lỗi 409. */
const TRANG_THAI_BUOC: Record<string, string> = {
  may_sinh: "máy đang sinh lịch",
  nhap: "còn nháp",
  dang_giai: "đang xếp lịch",
  cho_duyet: "chờ quản lý duyệt",
  da_duyet: "đã duyệt",
  da_cong_bo: "đã công bố",
  da_dong: "đã đóng",
};

function dayLabel(isoDate: string): string {
  const d = new Date(`${isoDate}T12:00:00`);
  if (Number.isNaN(d.getTime())) return isoDate;
  const thu = THU[d.getDay()] ?? "";
  return `${thu} · ${isoDate}`;
}

/**
 * Trang "Ca của tôi".
 *
 * Ba thay đổi so với bản cũ, theo đúng phàn nàn của người dùng:
 *  1. Tách hẳn hai mục "Ca của tôi" và "Ca có thể nhận", mỗi mục có số đếm —
 *     bản cũ trộn lẫn nên không biết ca nào là của mình.
 *  2. Nói rõ TRẠNG THÁI TUẦN và LÝ DO nút bị chặn. Bản cũ chỉ ghi trong dòng
 *     meta rằng "nhả/nhận ca khi lịch đã công bố" mà không hề kiểm tra — bấm
 *     vào thì bị từ chối ở server mà không hiểu vì sao.
 *  3. Nút "Nhả" hỏi lại trước khi làm — đây là hành động không hoàn tác được.
 */
export default function ToiPage() {
  const [token, setToken] = useState("");
  const [ca, setCa] = useState<Ca[]>([]);
  const [week, setWeek] = useState("");
  const [tomTat, setTomTat] = useState<TomTat | null>(null);
  const [rangBuoc, setRangBuoc] = useState<RangBuoc[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [xacNhanNha, setXacNhanNha] = useState<Ca | null>(null);

  const [profileEmail, setProfileEmail] = useState("");
  const [emailInput, setEmailInput] = useState("");
  const [emailMsg, setEmailMsg] = useState<string | null>(null);
  const [emailError, setEmailError] = useState<string | null>(null);
  const [emailBusy, setEmailBusy] = useState(false);

  useEffect(() => {
    setToken(getToken());
    if (!getToken()) setLoading(false);
    const requestedWeek =
      typeof window !== "undefined" ? new URLSearchParams(window.location.search).get("tuan") ?? "" : "";
    if (/^\d{4}-W\d{2}$/.test(requestedWeek)) setWeek(requestedWeek);
  }, []);

  const load = useCallback(
    (targetWeek?: string) => {
      if (!getToken()) return;
      const w = targetWeek !== undefined ? targetWeek : week;
      const url = w ? `/api/v1/toi/lich?tuan=${encodeURIComponent(w)}` : "/api/v1/toi/lich";
      apiGet<ToiLichOut | Ca[]>(url)
        .then((d) => {
          const list = Array.isArray(d) ? d : d.ca ?? [];
          setCa(list);
          if (!Array.isArray(d)) {
            if (d.tuan_iso) setWeek(d.tuan_iso);
            setTomTat(d.tom_tat ?? null);
            setRangBuoc(d.rang_buoc_da_duyet ?? []);
          }
        })
        .catch(() => setError("Không tải được lịch của bạn."))
        .finally(() => setLoading(false));

      apiGet<{ email?: string; username?: string }>("/api/v1/me/profile")
        .then((p) => {
          const em = p.email || "";
          setProfileEmail(em);
          setEmailInput(em);
        })
        .catch(() => {});
    },
    [week],
  );

  async function saveEmail(e: React.FormEvent) {
    e.preventDefault();
    setEmailBusy(true);
    setEmailMsg(null);
    setEmailError(null);
    try {
      await apiSend("/api/v1/me/profile/email", { email: emailInput.trim() }, "PATCH");
      setProfileEmail(emailInput.trim());
      setEmailMsg("Đã lưu email nhận thông báo.");
    } catch {
      setEmailError("Không cập nhật được email. Vui lòng kiểm tra lại định dạng.");
    } finally {
      setEmailBusy(false);
    }
  }

  useEffect(() => {
    if (token) load();
  }, [token, load]);

  /**
   * Nhả ca. Chỉ còn MỘT hành động ghi ở trang này.
   *
   * Nhận ca ở đây đã bỏ có chủ đích: nhận ca ở tuần đã công bố cần đồng thuận hai
   * bên nên đường duy nhất là Chợ đổi ca (`/doi-ca`). Giữ một nút "Nhận" gọi
   * endpoint sẽ trả 409 chỉ tạo cảm giác bấm được mà không làm gì.
   */
  async function nhaCa(id: string) {
    setBusy(id);
    setError(null);
    setMsg(null);
    try {
      await apiSend("/api/v1/ca/nha", { ca_id: id });
      setMsg("Đã nhả ca.");
      load();
    } catch (e) {
      // Server kèm trạng thái tuần trong `detail` (`lich_chua_cong_bo:nhap`) để
      // câu báo lỗi nói được ĐANG ở bước nào, không chỉ "không được".
      const detail =
        e instanceof ApiError && typeof e.detail === "string" ? e.detail : "";
      if (detail.startsWith("lich_chua_cong_bo")) {
        const buoc = detail.split(":")[1] ?? "";
        setError(
          `Chưa nhả ca được: tuần này đang «${buoc
            ? TRANG_THAI_BUOC[buoc] ?? buoc
            : "chưa công bố"}». Cần quản lý công bố lịch trước.`,
        );
      } else {
        setError("Không nhả được ca.");
      }
    } finally {
      setBusy(null);
    }
  }

  const caCuaToi = useMemo(() => ca.filter((c) => c.trang_thai === "cua_toi"), [ca]);
  const caCoTheNhan = useMemo(() => ca.filter((c) => c.trang_thai === "co_the_nhan"), [ca]);

  const grouped = useMemo(() => {
    const g: Record<string, Ca[]> = {};
    for (const c of caCuaToi) (g[c.ngay] ??= []).push(c);
    return g;
  }, [caCuaToi]);
  const days = useMemo(() => Object.keys(grouped).sort(), [grouped]);

  if (!token) return <AuthGate />;

  const daCongBo = tomTat?.da_cong_bo ?? false;

  return (
    <div className="nq-page">
      <PageHeader
        kicker="Ca của tôi"
        title="Lịch của tôi"
        meta={week ? `Tuần ${week} — nhả/nhận ca khi lịch đã công bố.` : "Đang đọc tuần hiện tại…"}
      />
      {error ? <Alert>{error}</Alert> : null}
      {msg ? <Alert kind="ok">{msg}</Alert> : null}

      {/* Trợ lý tóm tắt: đang ở tuần nào, có mấy ca, cần làm gì. */}
      {tomTat ? (
        <OpsCard eyebrow="Trợ lý tóm tắt" title={`Tuần ${tomTat.tuan_iso}`} density="compact">
          <div className="flex flex-wrap items-center gap-2">
            <StatusChip tone={daCongBo ? "ok" : "warn"}>{tomTat.trang_thai_label}</StatusChip>
            <StatusChip tone="info">{tomTat.so_ca_cua_toi} ca của bạn</StatusChip>
            {tomTat.so_ca_co_the_nhan > 0 ? (
              <StatusChip tone="info">{tomTat.so_ca_co_the_nhan} ca có thể nhận</StatusChip>
            ) : null}
            {tomTat.so_rang_buoc_da_duyet > 0 ? (
              <StatusChip tone="warn">{tomTat.so_rang_buoc_da_duyet} ràng buộc đã duyệt</StatusChip>
            ) : null}
          </div>
          <p className="mt-3 text-sm text-[var(--nq-fg)]" data-role="tom-tat-can-lam">
            {tomTat.can_lam}
          </p>
        </OpsCard>
      ) : null}

      {rangBuoc.length > 0 ? (
        <OpsCard eyebrow="Đã được duyệt" title="Ràng buộc ảnh hưởng tới bạn" density="compact">
          <ul className="nq-tkb-list">
            {rangBuoc.map((r, i) => (
              <li key={r.id ?? i}>
                {Y_DINH_LABEL[r.y_dinh ?? ""] ?? r.y_dinh ?? "Ràng buộc"}
                {r.ghi ? ` — ${r.ghi}` : ""}
              </li>
            ))}
          </ul>
        </OpsCard>
      ) : null}

      {loading ? <Loading skeleton="list">Đang tải lịch của bạn…</Loading> : null}
      {!loading && ca.length === 0 && !error ? (
        <Empty title="Chưa có ca">Chưa có ca trong tuần này, hoặc lịch chưa công bố.</Empty>
      ) : null}

      {!loading && caCuaToi.length > 0 ? (
        <OpsCard
          density="compact"
          eyebrow="Tuần này"
          title="Ca của tôi"
          count={caCuaToi.length}
          countLabel="ca"
        >
          {!daCongBo ? (
            <Alert kind="info">
              Tuần này {tomTat ? `đang «${tomTat.trang_thai_label}»` : "chưa công bố"} — nút
              Nhả ca tạm khóa. Chờ quản lý công bố lịch rồi mới nhả/đổi được.
            </Alert>
          ) : null}
          <div className="space-y-4">
            {days.map((ngay) => (
              <section key={ngay} className="min-w-0">
                <header className="mb-2 flex items-baseline justify-between gap-2 border-b border-[var(--nq-line)] pb-1.5">
                  <h3 className="text-sm font-semibold text-[var(--nq-fg)]">{dayLabel(ngay)}</h3>
                  <span className="font-mono text-2xs text-[var(--nq-dim)]">
                    {(grouped[ngay] ?? []).length} ca
                  </span>
                </header>
                <ul className="space-y-2">
                  {(grouped[ngay] ?? []).map((c) => (
                    <li
                      key={c.id}
                      className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-[var(--nq-line)] bg-[var(--nq-surface)] px-3 py-2.5"
                    >
                      <div className="min-w-0">
                        <p className="font-semibold text-[var(--nq-fg)]">{viTriLabel(c.vi_tri)}</p>
                        <p className="font-mono text-xs text-[var(--nq-dim)]">
                          {c.bat_dau} – {c.ket_thuc}
                          {c.khung ? ` · ${khungLabel(c.khung)}` : ""}
                        </p>
                        {c.nguoi_khac_trong_ca && c.nguoi_khac_trong_ca.length > 0 ? (
                          <p className="mt-0.5 text-2xs text-[var(--nq-ink-muted)]">
                            Cùng ca với {c.nguoi_khac_trong_ca.length} người khác
                          </p>
                        ) : null}
                      </div>
                      <div className="flex shrink-0 flex-wrap items-center gap-2">
                        <Btn
                          size="sm"
                          variant="danger"
                          disabled={busy === c.id || !daCongBo}
                          title={daCongBo ? "Nhả ca này" : "Lịch chưa công bố — chưa thể nhả ca"}
                          onClick={() => setXacNhanNha(c)}
                        >
                          Nhả ca
                        </Btn>
                      </div>
                    </li>
                  ))}
                </ul>
              </section>
            ))}
          </div>
        </OpsCard>
      ) : null}

      {!loading && caCoTheNhan.length > 0 ? (
        <OpsCard
          density="compact"
          eyebrow="Chưa có ai nhận"
          title="Ca có thể nhận"
          count={caCoTheNhan.length}
          countLabel="ca"
        >
          <Alert kind="info">
            Nhận ca ở tuần đã công bố cần <strong>quản lý xác nhận</strong> — hãy mở Chợ đổi ca
            để gửi đề nghị và theo dõi ai đồng ý.
          </Alert>
          <ul className="mt-3 space-y-2">
            {caCoTheNhan.map((c) => (
              <li
                key={c.id}
                className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-[var(--nq-line)] bg-[var(--nq-surface)] px-3 py-2.5"
              >
                <div className="min-w-0">
                  <p className="font-semibold text-[var(--nq-fg)]">
                    {dayLabel(c.ngay)} · {viTriLabel(c.vi_tri)}
                  </p>
                  <p className="font-mono text-xs text-[var(--nq-dim)]">
                    {c.bat_dau} – {c.ket_thuc}
                    {typeof c.so_nguoi_trong_ca === "number"
                      ? ` · ${c.so_nguoi_trong_ca} người đang trực`
                      : ""}
                  </p>
                </div>
                <BtnLink
                  href={`/doi-ca?tuan=${encodeURIComponent(week)}`}
                  size="sm"
                  variant="primary"
                >
                  Mở Chợ đổi ca
                </BtnLink>
              </li>
            ))}
          </ul>
        </OpsCard>
      ) : null}

      <OpsCard density="compact" eyebrow="Hồ sơ" title="Email nhận thông báo ca">
        <form onSubmit={saveEmail} className="nq-list">
          <p className="text-sm text-[var(--nq-ink-muted)]">
            Gmail để nhận thông báo phân ca, đổi ca và nhắc việc từ quán.
          </p>
          {emailMsg ? <Alert kind="ok">{emailMsg}</Alert> : null}
          {emailError ? <Alert>{emailError}</Alert> : null}
          <div className="mt-2 flex flex-col gap-2 sm:flex-row">
            <Input
              type="email"
              placeholder="nhan_vien@gmail.com"
              value={emailInput}
              onChange={(e) => setEmailInput(e.target.value)}
              required
              className="flex-1"
            />
            <Btn
              variant="primary"
              type="submit"
              disabled={emailBusy || !emailInput.trim() || emailInput.trim() === profileEmail}
            >
              {emailBusy ? "Đang lưu…" : "Lưu Gmail"}
            </Btn>
          </div>
        </form>
      </OpsCard>

      <ConfirmDialog
        open={xacNhanNha !== null}
        title="Nhả ca này?"
        confirmLabel="Nhả ca"
        cancelLabel="Giữ lại"
        variant="danger"
        busy={busy !== null}
        onCancel={() => setXacNhanNha(null)}
        onConfirm={() => {
          const target = xacNhanNha;
          setXacNhanNha(null);
          if (target) void nhaCa(target.id);
        }}
        body={
          <p>
            Bạn sẽ được rút khỏi ca {xacNhanNha ? dayLabel(xacNhanNha.ngay) : ""} (
            {xacNhanNha?.bat_dau}–{xacNhanNha?.ket_thuc}). Ca này sẽ trống người cho tới khi quản
            lý xếp người khác hoặc có người nhận qua Chợ đổi ca.
          </p>
        }
      />
    </div>
  );
}

