"use client";

/**
 * Thời khoá biểu từ ảnh — upload → AI đọc → sửa → xác nhận gắn NV.
 */

import { useCallback, useEffect, useState } from "react";
import { apiGet, apiSend, apiUpload } from "../../lib/api";
import { nvTenHienThi, safeText, viError } from "../../lib/present";
import { getToken, isManager } from "../../lib/session";
import {
  Alert,
  AuthGate,
  Btn,
  BtnLink,
  Empty,
  Field,
  inputClassName,
  Loading,
  Notice,
  OpsCard,
  PageActions,
  PageHeader,
  StatusChip,
  TimeField,
  Toasts,
  useToasts,
} from "../../ui/kit";
import { CopilotPane } from "../../ui/copilot/CopilotPane";

type Khoang = { thu: string; start: string; end: string };

type ExtractOut = {
  rows: Khoang[];
  spans: Array<{ day: string; start: string; end: string }>;
  confidence: number;
  blur: boolean;
  escalate: boolean;
  reason?: string;
  provider?: string;
  mode?: string;
  source_id?: string;
  upload_id?: string;
  agent_mode?: string;
};

type Nv = { id: string; ten: string };

/**
 * Tác động của khung bận vừa gắn lên lịch tuần đang có.
 *
 * Có mặt để trả lời câu "up TKB xong sao lịch không tự đổi": server không tự
 * chạy lại xếp lịch (làm vậy sẽ đè lịch đã công bố mà không hỏi ai), mà TRẢ VỀ
 * đây để người dùng quyết định. `can_chay_lai` là True khi có ca đang giao với
 * khung bận mới — tức lịch hiện tại đang SAI ràng buộc.
 */
type CaBiDung = {
  ca_id: string;
  thu: string;
  khung: string;
  gio: string;
  khoang_ban: string;
};

type TacDong = {
  nv_id: string;
  tuan_iso: string;
  trang_thai: string;
  ca_bi_dung: CaBiDung[];
  so_ca_bi_dung: number;
  can_chay_lai: boolean;
  da_cong_bo: boolean;
  ly_do: string;
};

type ConfirmOut = {
  ok: boolean;
  nv_id: string;
  tuan_iso: string;
  khoang_ban: Khoang[];
  n: number;
  khoang_cu: Khoang[];
  tac_dong: TacDong;
};

/** Diff trả về từ `POST /api/v1/tkb/xep-lai` — bằng chứng ai đổi ca với ai. */
type DongThayDoi = {
  ca: { ca_id: string; thu: string; khung: string; gio: string; vi_tri: string };
  nv_id: string;
  ten: string;
  chieu: string;
};

type HoanDoi = {
  ca: { ca_id: string; thu: string; khung: string; gio: string; vi_tri: string };
  ra: Array<{ nv_id: string; ten: string }>;
  vao: Array<{ nv_id: string; ten: string }>;
};

type ChuyenCa = {
  nv_id: string;
  ten: string;
  tu_ca: Array<{ ca_id: string; thu: string; khung: string; gio: string }>;
  den_ca: Array<{ ca_id: string; thu: string; khung: string; gio: string }>;
};

type Diff = {
  them: DongThayDoi[];
  bot: DongThayDoi[];
  hoan_doi: HoanDoi[];
  doi_giua_hai_ca: ChuyenCa[];
  giu_nguyen: number;
  khong_so_sanh_duoc: boolean;
};

type XepLaiOut = {
  ok: boolean;
  tuan_iso: string;
  trang_thai?: string;
  diff?: Diff | null;
  tom_tat?: string;
  ly_do?: string;
  danh_sach_xung_dot?: string[];
};


const THU = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"] as const;
const THU_TEN: Record<string, string> = {
  T2: "Thứ Hai",
  T3: "Thứ Ba",
  T4: "Thứ Tư",
  T5: "Thứ Năm",
  T6: "Thứ Sáu",
  T7: "Thứ Bảy",
  CN: "Chủ Nhật",
};

const TIME_PATTERN = /^([01]\d|2[0-3]):[0-5]\d$/;

function isoWeekDates(tuanIso: string): Record<string, string> {
  const match = /^(\d{4})-W(\d{2})$/.exec(tuanIso);
  if (!match) return {};

  const year = Number(match[1]);
  const week = Number(match[2]);
  const januaryFourth = new Date(Date.UTC(year, 0, 4));
  const monday = new Date(januaryFourth);
  monday.setUTCDate(
    januaryFourth.getUTCDate() - ((januaryFourth.getUTCDay() + 6) % 7) + (week - 1) * 7,
  );

  return Object.fromEntries(
    THU.map((thu, index) => {
      const date = new Date(monday);
      date.setUTCDate(monday.getUTCDate() + index);
      return [
        thu,
        new Intl.DateTimeFormat("vi-VN", {
          day: "2-digit",
          month: "2-digit",
          year: "numeric",
          timeZone: "UTC",
        }).format(date),
      ];
    }),
  );
}

function validateRows(rows: Khoang[]): string[][] {
  const errors = rows.map(() => [] as string[]);
  const hasValidTimeRange = rows.map(
    (row) => TIME_PATTERN.test(row.start) && TIME_PATTERN.test(row.end) && row.start < row.end,
  );

  rows.forEach((row, index) => {
    if (!THU.includes(row.thu as (typeof THU)[number])) {
      errors[index].push("Ngày không hợp lệ.");
    }
    if (!TIME_PATTERN.test(row.start) || !TIME_PATTERN.test(row.end)) {
      errors[index].push("Nhập đủ giờ bắt đầu và kết thúc theo định dạng HH:mm.");
    } else if (row.start >= row.end) {
      errors[index].push("Giờ kết thúc phải sau giờ bắt đầu.");
    }
  });

  rows.forEach((row, index) => {
    if (!hasValidTimeRange[index]) return;
    rows.slice(index + 1).forEach((other, offset) => {
      const otherIndex = index + offset + 1;
      if (
        hasValidTimeRange[otherIndex] &&
        row.thu === other.thu &&
        row.start < other.end &&
        other.start < row.end
      ) {
        errors[index].push("Khung giờ bị trùng trong cùng ngày.");
        errors[otherIndex].push("Khung giờ bị trùng trong cùng ngày.");
      }
    });
  });

  return errors;
}

function nextISOWeek(): string {
  const now = new Date();
  now.setDate(now.getDate() + 7);
  now.setHours(0, 0, 0, 0);
  now.setDate(now.getDate() + 3 - ((now.getDay() + 6) % 7));
  const week1 = new Date(now.getFullYear(), 0, 4);
  const week =
    1 +
    Math.round(
      ((now.getTime() - week1.getTime()) / 86400000 -
        3 +
        ((week1.getDay() + 6) % 7)) /
        7,
    );
  return `${now.getFullYear()}-W${String(week).padStart(2, "0")}`;
}

export default function TkbPage() {
  const [token, setToken] = useState("");
  const [manager, setManager] = useState(false);
  const [myNv, setMyNv] = useState("");
  const [staff, setStaff] = useState<Nv[]>([]);
  const [nvId, setNvId] = useState("");
  const [tuanIso, setTuanIso] = useState(nextISOWeek);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [result, setResult] = useState<ExtractOut | null>(null);
  const [rows, setRows] = useState<Khoang[]>([]);
  const [saved, setSaved] = useState<Khoang[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [hint, setHint] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [copilotOpen, setCopilotOpen] = useState(false);
  const [tacDong, setTacDong] = useState<TacDong | null>(null);
  const [diff, setDiff] = useState<Diff | null>(null);
  const [xepLaiMsg, setXepLaiMsg] = useState<string | null>(null);
  const [xepLaiBusy, setXepLaiBusy] = useState(false);
  const { toasts, push, dismiss } = useToasts();
  const datesByDay = isoWeekDates(tuanIso);
  const rowErrors = validateRows(rows);
  const hasInvalidRows = rowErrors.some((messages) => messages.length > 0);
  const unrecognizedDayRows = rows
    .map((row, index) => ({ ...row, _i: index }))
    .filter((row) => !THU.includes(row.thu as (typeof THU)[number]));

  useEffect(() => {
    setToken(getToken());
    setManager(isManager());
    setMyNv(sessionStorage.getItem("nq_nv") || "");
    if (!getToken()) setLoading(false);
  }, []);

  const loadMine = useCallback(() => {
    if (!getToken()) return;
    setLoading(true);
    // Danh sách nhân viên lấy từ /ops/pickers (mọi role) — không dùng
    // /lich-tuan (chỉ quản lý) kèm tuần hardcode cũ đã gây lỗi tải → nút
    // duyệt TKB không chạy sau khi lọc.
    Promise.all([
      apiGet<{ nv_id: string; item: { tuan_iso?: string; khoang_ban?: Khoang[] } | null }>(
        `/api/v1/tkb/mine?tuan_iso=${encodeURIComponent(tuanIso)}`,
      ),
      apiGet<{ nhan_vien?: Nv[] }>("/api/v1/ops/pickers").catch(() => ({ nhan_vien: [] })),
    ])
      .then(([mine, lich]) => {
        setMyNv(mine.nv_id || sessionStorage.getItem("nq_nv") || "");
        setNvId((prev) => prev || mine.nv_id || "");
        setSaved(mine.item?.khoang_ban ?? null);
        setStaff(lich.nhan_vien ?? []);
        setError(null);
      })
      .catch((e) => setError(viError(e, { doing: "mở được trang thời khoá biểu" })))
      .finally(() => setLoading(false));
  }, [tuanIso]);

  useEffect(() => {
    if (token) loadMine();
  }, [token, loadMine]);

  useEffect(() => {
    if (!file) {
      setPreview(null);
      return;
    }
    const url = URL.createObjectURL(file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  async function chayExtract(fixture?: string) {
    setBusy(true);
    setError(null);
    setHint(null);
    try {
      const form = new FormData();
      if (fixture) {
        form.append("fixture_id", fixture);
      } else if (file) {
        form.append("file", file);
      } else {
        setError("Chọn ảnh thời khoá biểu, hoặc thử ảnh mẫu.");
        return;
      }
      const out = await apiUpload<ExtractOut>("/api/v1/tkb/upload", form);
      setResult(out);
      const khoang =
        out.rows?.length > 0
          ? out.rows
          : (out.spans ?? []).map((s) => ({ thu: s.day, start: s.start, end: s.end }));
      setRows(khoang);
      if (out.escalate || !khoang.length) {
        // Inline — không dùng toast đáy màn (đè nút Xác nhận).
        setHint(
          khoang.length
            ? "Máy đọc chưa chắc. Kiểm tra và sửa các khung giờ bên dưới trước khi xác nhận."
            : "Không nhận diện được khung giờ bận nào. Ảnh có thể chưa đủ rõ; hãy thêm khung thủ công theo từng ngày.",
        );
      } else {
        setHint(null);
        push(`Đã đọc ${khoang.length} khung · độ tin ${(out.confidence * 100).toFixed(0)}%.`);
      }
    } catch (e) {
      setError(viError(e, { doing: "đọc được ảnh thời khoá biểu" }));
    } finally {
      setBusy(false);
    }
  }

  async function xacNhan() {
    if (rows.length === 0 || hasInvalidRows) {
      setError("Kiểm tra và sửa các khung giờ chưa hợp lệ trước khi xác nhận.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const target = manager ? nvId || myNv : myNv;
      const out = await apiSend<ConfirmOut>("/api/v1/tkb/confirm", {
        nv_id: target,
        tuan_iso: tuanIso,
        khoang_ban: rows,
        source_id: result?.source_id || "",
        upload_id: result?.upload_id || "",
      });
      setSaved(rows);
      setHint(null);
      setDiff(null);
      setXepLaiMsg(null);

      const tacDong = out?.tac_dong;
      if (tacDong?.can_chay_lai) {
        // Lịch tuần đang có ca vi phạm khung bận mới — PHẢI nói ra, không im lặng.
        setTacDong(tacDong);
        push(`Đã gắn TKB · ${tacDong.so_ca_bi_dung} ca đang trùng khung bận.`);
      } else {
        setTacDong(null);
        push("Đã gắn thời khoá biểu. Lượt xếp lịch tới sẽ tránh các khung này.");
      }
      loadMine();
    } catch (e) {
      setError(viError(e, { doing: "xác nhận được thời khoá biểu" }));
    } finally {
      setBusy(false);
    }
  }

  /** Chạy lại xếp lịch cho tuần này — chỉ quản lý. Trả về diff để CHỨNG MINH. */
  async function chayXepLai() {
    setXepLaiBusy(true);
    setError(null);
    try {
      const out = await apiSend<XepLaiOut>("/api/v1/tkb/xep-lai", { tuan_iso: tuanIso }, "POST");
      if (out.ok) {
        setDiff(out.diff ?? null);
        setXepLaiMsg(
          `Đã xếp lại tuần ${tuanIso} — trạng thái "Chờ duyệt". ${out.tom_tat ?? ""} Mở trang Lịch tuần để xem và công bố.`.trim(),
        );
        setTacDong(null);
      } else {
        setXepLaiMsg(
          `Chưa xếp được: ${out.ly_do ?? "không rõ"} — ${
            (out.danh_sach_xung_dot ?? []).slice(0, 3).join(" ") || "thiếu người khả dụng."
          }`,
        );
      }
    } catch (e) {
      setError(viError(e, { doing: "xếp lại lịch tuần" }));
    } finally {
      setXepLaiBusy(false);
    }
  }

  function updateRow(i: number, patch: Partial<Khoang>) {
    setRows((prev) => prev.map((r, idx) => (idx === i ? { ...r, ...patch } : r)));
  }

  if (!token) return <AuthGate />;

  return (
    <div className="nq-page nq-page--tkb">
      <PageHeader
        kicker="Lịch cá nhân · tránh xếp trùng ca"
        title="Tải ảnh lịch bận"
        meta="Chụp hoặc chọn ảnh lịch học, kiểm tra các khung giờ được đọc rồi xác nhận. Lần xếp ca tiếp theo sẽ tránh các giờ này."
      />
      <PageActions>
        <Btn variant="ghost" onClick={() => setCopilotOpen(true)}>
          Hỏi trợ lý vận hành
        </Btn>
      </PageActions>
      <Toasts toasts={toasts} onDismiss={dismiss} />
      {error ? <Alert kind="err">{error}</Alert> : null}
      {loading ? <Loading skeleton="list">Đang tải…</Loading> : null}

      <Notice>
        Khai báo <strong className="text-[var(--nq-fg)]">theo đúng ca</strong> bạn bận (ca sáng /
        chiều / tối) — hệ thống chỉ tránh xếp ca đó, không xoá cả ngày.
      </Notice>

      <Notice>
        Ảnh thật cần <span className="font-mono text-[var(--nq-fg)]">CA_AGENT_MODE=live</span> và key
        Gemini. Có thể bấm <strong className="text-[var(--nq-fg)]">Thử ảnh mẫu</strong> ngay không cần
        Gemini.
      </Notice>

      {saved && saved.length > 0 ? (
        <OpsCard
          eyebrow="Đã lưu"
          title="Lưới lịch bận đã gắn"
          count={saved.length}
          countLabel="khung bận"
        >
          <p className="mb-3 text-sm text-[var(--nq-fg)]">
            Các khung bên dưới sẽ được AvoidConflict khi xếp lịch lần tới — bấm «Xóa khung» để bỏ.
          </p>
          <div className="nq-tkb-day-grid">
            {THU.map((t) => {
              const khungTrongNgay = saved.filter((k) => k.thu === t);
              if (khungTrongNgay.length === 0) {
                return (
                  <div
                    key={t}
                    className="rounded-lg border border-[var(--nq-line)] bg-[var(--nq-bg)] p-3 opacity-70"
                  >
                    <p className="text-xs font-bold uppercase tracking-wide text-[var(--nq-ink)]">
                      {THU_TEN[t]}
                    </p>
                    <p className="mt-1 text-xs text-[var(--nq-ink-muted)]">Rảnh cả ngày</p>
                  </div>
                );
              }
              return (
                <div key={t} className="rounded-lg border border-[color-mix(in_srgb,var(--nq-st-warn)_46%,var(--nq-line))] bg-[var(--nq-st-warn-soft)] p-3">
                  <p className="text-xs font-bold uppercase tracking-wide text-[var(--nq-st-warn-ink)]">
                    {THU_TEN[t]}
                  </p>
                  <ul className="mt-1.5 space-y-1">
                    {khungTrongNgay.map((k, i) => (
                      <li
                        key={`${k.thu}-${k.start}-${i}`}
                        className="rounded bg-[var(--nq-bg-elevated)] px-2 py-1 font-mono text-xs text-[var(--nq-ink)]"
                      >
                        {k.start} – {k.end}
                      </li>
                    ))}
                  </ul>
                </div>
              );
            })}
          </div>
        </OpsCard>
      ) : null}

      <OpsCard eyebrow="Bước 1" title="Tải ảnh & đọc">
        <Field label="Tuần áp dụng">
          <input
            className={inputClassName}
            type="week"
            value={tuanIso}
            onChange={(e) => setTuanIso(e.target.value)}
          />
        </Field>
        <div className="mb-4">
          <span className="mb-2 block text-sm font-bold uppercase tracking-widest text-[var(--nq-dim)]">
            Ảnh thời khoá biểu
          </span>
          <label className="nq-tkb-file">
            <span className="nq-tkb-file-btn">Chọn ảnh</span>
            <span className="nq-tkb-file-name">
              {file ? file.name : "Chưa chọn — PNG, JPG hoặc chụp màn hình"}
            </span>
            <input
              type="file"
              accept="image/*,.svg"
              className="sr-only"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
          </label>
        </div>
        {preview ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={preview} alt="Xem trước TKB" className="nq-tkb-preview" />
        ) : null}
        {manager ? (
          <Field label="Gắn cho nhân viên">
            <select className={inputClassName} value={nvId} onChange={(e) => setNvId(e.target.value)}>
              <option value={myNv}>Tôi ({myNv || "—"})</option>
              {staff.map((nv) => (
                <option key={nv.id} value={nv.id}>
                  {nvTenHienThi(nv.ten, nv.id)}
                </option>
              ))}
            </select>
          </Field>
        ) : (
          <p className="text-sm text-[var(--nq-fg)]">
            Gắn vào tài khoản của bạn ({safeText(myNv, "…")})
          </p>
        )}
        <div className="mt-4 flex flex-wrap gap-2">
          <Btn variant="primary" disabled={busy || !file} onClick={() => chayExtract()}>
            {busy ? "Đang đọc…" : "Đọc ảnh"}
          </Btn>
          <Btn variant="ghost" disabled={busy} onClick={() => chayExtract("tkb_01")}>
            Thử ảnh mẫu
          </Btn>
        </div>
      </OpsCard>

      {result ? (
        <OpsCard eyebrow="Bước 2" title="Sửa & xác nhận" count={rows.length} countLabel="khung">
          <div className="mb-3 flex flex-wrap gap-2">
            <StatusChip tone={result.escalate || rows.length === 0 ? "warn" : "ok"}>
              {rows.length === 0
                ? "Không nhận diện được khung"
                : result.escalate
                  ? "Kết quả chưa chắc chắn"
                  : "Đã nhận diện"}
            </StatusChip>
            <StatusChip>
              {(result.confidence * 100).toFixed(0)}% · {safeText(result.provider, "—")} ·{" "}
              {safeText(result.mode, "")}
            </StatusChip>
          </div>
          {hint ? <Alert kind="info">{hint}</Alert> : null}
          <p className="mb-3 text-sm text-[var(--nq-fg)]">
            Kết quả nhận diện cho tuần <strong>{tuanIso}</strong>. Mỗi khung bên dưới hiển thị rõ
            ngày và giờ bận; bạn có thể thêm, sửa hoặc xóa trước khi xác nhận.
          </p>
          {hasInvalidRows ? (
            <Alert kind="err">Có khung giờ chưa hợp lệ hoặc bị trùng. Hãy sửa các mục được đánh dấu.</Alert>
          ) : null}

          {unrecognizedDayRows.map((row) => (
            <div
              key={row._i}
              className="mb-3 flex flex-wrap items-center gap-2 rounded-lg border border-[color-mix(in_srgb,var(--nq-st-danger)_46%,var(--nq-line))] bg-[var(--nq-st-danger-soft)] p-3"
            >
              <span className="text-sm text-[var(--nq-st-danger-ink)]">
                Không nhận diện được ngày “{safeText(row.thu, "trống")}” cho khung {safeText(row.start, "—")}–
                {safeText(row.end, "—")}.
              </span>
              <select
                className={`${inputClassName} w-auto text-xs`}
                value=""
                aria-label={`Chọn lại ngày cho khung ${row.start}–${row.end}`}
                onChange={(event) => updateRow(row._i, { thu: event.target.value })}
              >
                <option value="">Chọn ngày</option>
                {THU.map((thu) => (
                  <option key={thu} value={thu}>
                    {THU_TEN[thu]} · {datesByDay[thu]}
                  </option>
                ))}
              </select>
              <Btn
                variant="ghost"
                title="Xóa khung không nhận diện được ngày"
                onClick={() => setRows((prev) => prev.filter((_, index) => index !== row._i))}
              >
                Xóa
              </Btn>
            </div>
          ))}

          {/* Lưới chi tiết theo ngày — mỗi khung hiện đầy đủ thứ, giờ, nút xóa.
              `auto-fill minmax(260px,1fr)` tự co số cột theo bề ngang thật của
              trang (không còn cố định 4 cột rồi ép ô giờ tràn ra ngoài thẻ). */}
          <div className="nq-tkb-day-grid">
            {THU.map((t) => {
              const khungTrongNgay = rows.map((r, i) => ({ ...r, _i: i })).filter((r) => r.thu === t);
              return (
                <div
                  key={t}
                  className={`rounded-lg border p-3 space-y-2 ${
                    khungTrongNgay.length > 0
                      ? "border-[color-mix(in_srgb,var(--nq-st-warn)_46%,var(--nq-line))] bg-[var(--nq-st-warn-soft)]"
                      : "border-[var(--nq-line)] bg-[var(--nq-bg)]"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-xs font-bold uppercase tracking-wide text-[var(--nq-fg)]">
                        {THU_TEN[t]}
                      </p>
                      <p className="mt-0.5 text-xs text-[var(--nq-dim)]">{datesByDay[t]}</p>
                    </div>
                    <button
                      type="button"
                      className="rounded px-1.5 py-0.5 text-2xs font-bold text-[var(--nq-st-warn-ink)] hover:bg-[var(--nq-st-warn)]"
                      title={`Thêm khung bận cho ${THU_TEN[t]}`}
                      onClick={() => setRows((prev) => [...prev, { thu: t, start: "", end: "" }])}
                    >
                      + Thêm khung
                    </button>
                  </div>
                  {khungTrongNgay.length === 0 ? (
                    <p className="text-xs text-[var(--nq-ink-muted)]">Không có khung bận</p>
                  ) : (
                    khungTrongNgay.map((r) => (
                      <div key={r._i} className="nq-tkb-row">
                        <div className="nq-tkb-row__times">
                          <TimeField
                            value={r.start}
                            onChange={(v) => updateRow(r._i, { start: v })}
                            invalid={rowErrors[r._i].length > 0}
                            ariaLabel={`Giờ bắt đầu bận ${THU_TEN[t]} ${datesByDay[t]}`}
                          />
                          <span className="text-[var(--nq-fg)] text-xs">đến</span>
                          <TimeField
                            value={r.end}
                            onChange={(v) => updateRow(r._i, { end: v })}
                            invalid={rowErrors[r._i].length > 0}
                            ariaLabel={`Giờ kết thúc bận ${THU_TEN[t]} ${datesByDay[t]}`}
                          />
                        </div>
                        <Btn
                          variant="ghost"
                          size="sm"
                          title={`Xóa khung bận ${THU_TEN[t]} ${r.start}–${r.end}`}
                          onClick={() => setRows((prev) => prev.filter((_, j) => j !== r._i))}
                        >
                          Xóa
                        </Btn>
                        {rowErrors[r._i].map((message) => (
                          <p key={message} className="mt-1 w-full text-xs text-[var(--nq-st-danger-ink)]" role="alert">
                            {message}
                          </p>
                        ))}
                      </div>
                    ))
                  )}
                </div>
              );
            })}
          </div>

          <div className="mt-6 pb-24 md:pb-8">
            <Btn
              variant="primary"
              disabled={busy || rows.length === 0 || hasInvalidRows}
              onClick={xacNhan}
            >
              Xác nhận gắn TKB
            </Btn>
          </div>
        </OpsCard>
      ) : (
        !loading && (
          <Empty>Chưa có kết quả đọc. Chọn ảnh rồi bấm Đọc ảnh, hoặc thử ảnh mẫu.</Empty>
        )
      )}

      {/* Tác động lên lịch tuần — trả lời "up TKB xong sao lịch không tự đổi". */}
      {tacDong && tacDong.can_chay_lai ? (
        <OpsCard
          eyebrow="Lịch tuần bị ảnh hưởng"
          title="Khung bận mới trùng ca đã xếp"
          count={tacDong.so_ca_bi_dung}
          countLabel="ca"
        >
          <Alert kind="info">
            Lịch tuần <strong>{tacDong.tuan_iso}</strong> đang có {tacDong.so_ca_bi_dung} ca
            giao với khung bận vừa gắn, nên lịch hiện tại <strong>chưa tôn trọng</strong> ràng buộc.
            {tacDong.da_cong_bo
              ? " Tuần này đã công bố — xếp lại sẽ đưa về trạng thái Chờ duyệt, cần duyệt lại mới có hiệu lực."
              : " Xếp lại sẽ đưa tuần về trạng thái Chờ duyệt để bạn rà trước khi công bố."}
          </Alert>
          <ul className="nq-tkb-list mt-3">
            {tacDong.ca_bi_dung.map((c) => (
              <li key={c.ca_id}>
                {THU_TEN[c.thu] ?? c.thu} · {c.gio} — trùng khung bận {c.khoang_ban}
              </li>
            ))}
          </ul>
          {manager ? (
            <div className="mt-4 flex flex-wrap gap-3">
              <Btn variant="primary" disabled={xepLaiBusy} onClick={chayXepLai}>
                {xepLaiBusy ? "Đang xếp lại…" : "Xếp lại lịch tuần này"}
              </Btn>
              <Btn variant="ghost" onClick={() => setTacDong(null)}>
                Chỉ lưu, xếp sau
              </Btn>
            </div>
          ) : (
            <Notice>
              Đã báo cho quản lý. Bạn có thể bấm «Hỏi trợ lý vận hành» để hỏi vì sao ca này bị ảnh hưởng.
            </Notice>
          )}
        </OpsCard>
      ) : null}

      {xepLaiMsg ? (
        <OpsCard eyebrow="Kết quả xếp lại" title="Lịch tuần đã được xếp lại">
          <p className="text-sm text-[var(--nq-fg)]">{xepLaiMsg}</p>
          {diff ? <ShiftChangeDiff diff={diff} /> : null}
          <div className="mt-4">
            <BtnLink href={`/lich-tuan?tuan=${encodeURIComponent(tuanIso)}`} variant="primary">
              Mở Lịch tuần để duyệt
            </BtnLink>
          </div>
        </OpsCard>
      ) : null}

      <CopilotPane open={copilotOpen} onClose={() => setCopilotOpen(false)} />
    </div>
  );
}

/**
 * Bảng chứng minh đổi ca: ai ra, ai vào, ai chuyển ca.
 *
 * Vì sao không chỉ hiện con số: người dùng nói thẳng "cần một hệ thống dễ hiểu
 * chứ không phải tự động ngầm". Con số "3 ca đổi người" không cho biết ai bị
 * ảnh hưởng; ở đây in TÊN người, không in mã `nv_xx`.
 */
function ShiftChangeDiff({ diff }: { diff: Diff }) {
  if (diff.khong_so_sanh_duoc) {
    return (
      <p className="mt-3 text-sm text-[var(--nq-ink-muted)]">
        Chưa đủ dữ liệu để so sánh hai bản phân công (một bên chưa có lịch).
      </p>
    );
  }
  const rong =
    diff.hoan_doi.length === 0 &&
    diff.doi_giua_hai_ca.length === 0 &&
    diff.them.length === 0 &&
    diff.bot.length === 0;

  if (rong) {
    return (
      <p className="mt-3 text-sm text-[var(--nq-ink-muted)]">
        Không có ca nào thay đổi — lịch cũ đã tôn trọng ràng buộc mới.
      </p>
    );
  }

  return (
    <div className="mt-4 space-y-4">
      {diff.hoan_doi.length > 0 ? (
        <div>
          <p className="mb-2 text-xs font-bold uppercase tracking-widest text-[var(--nq-dim)]">
            Ca đổi người
          </p>
          <ul className="space-y-2">
            {diff.hoan_doi.map((h) => (
              <li key={h.ca.ca_id} className="nq-surface-row">
                <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
                  <span className="font-mono text-xs text-[var(--nq-dim)]">
                    {h.ca.thu} · {h.ca.gio}
                  </span>
                  <span className="text-sm">
                    <span className="text-[var(--nq-st-danger-ink)]">
                      {h.ra.map((r) => r.ten).join(", ")}
                    </span>
                    <span className="mx-2 text-[var(--nq-dim)]">ra</span>
                    <span className="text-[var(--nq-st-ok-ink)]">
                      {h.vao.map((v) => v.ten).join(", ")}
                    </span>
                    <span className="ml-2 text-[var(--nq-dim)]">vào</span>
                  </span>
                </div>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {diff.doi_giua_hai_ca.length > 0 ? (
        <div>
          <p className="mb-2 text-xs font-bold uppercase tracking-widest text-[var(--nq-dim)]">
            Người chuyển sang ca khác (không mất ca)
          </p>
          <ul className="space-y-2">
            {diff.doi_giua_hai_ca.map((c) => (
              <li key={c.nv_id} className="nq-surface-row">
                <span className="text-sm">
                  <strong>{c.ten}</strong>
                  <span className="mx-2 text-[var(--nq-dim)]">
                    {c.tu_ca.map((t) => `${t.thu} ${t.gio}`).join(", ")} →{" "}
                    {c.den_ca.map((d) => `${d.thu} ${d.gio}`).join(", ")}
                  </span>
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {(diff.them.length > 0 || diff.bot.length > 0) ? (
        <div>
          <p className="mb-2 text-xs font-bold uppercase tracking-widest text-[var(--nq-dim)]">
            Lượt vào / ra ca
          </p>
          <ul className="nq-tkb-list">
            {diff.bot.map((b) => (
              <li key={`ra-${b.ca.ca_id}-${b.nv_id}`} data-chieu="ra">
                {b.ten} ra khỏi {b.ca.thu} {b.ca.gio}
              </li>
            ))}
            {diff.them.map((t) => (
              <li key={`vao-${t.ca.ca_id}-${t.nv_id}`} data-chieu="vao">
                {t.ten} vào {t.ca.thu} {t.ca.gio}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <p className="text-xs text-[var(--nq-dim)]">
        Giữ nguyên {diff.giu_nguyen} lượt phân công không đổi.
      </p>
    </div>
  );
}

