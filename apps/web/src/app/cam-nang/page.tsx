"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { apiGet, apiSend } from "../../lib/api";
import { luatLabel, luatTone, safeText, vfRuleLyDo, viError } from "../../lib/present";
import { matchSearch } from "../../lib/list-filters";
import { getRole, getToken, isChuQuan, isManager } from "../../lib/session";
import {
  Alert,
  AuthGate,
  Btn,
  BtnLink,
  Empty,
  Field,
  FixtureChip,
  Input,
  Loading,
  Notice,
  PageActions,
  PageGrid,
  PageHeader,
  StatusChip,
  Summary,
  TechnicalDrawer,
} from "../../ui/kit";
import { CopilotPane } from "../../ui/copilot/CopilotPane";
import { AiInsightPanel } from "../../ui/ai/AiInsightPanel";
import { AskAiBox } from "../../ui/ai/AskAiBox";

type Luat = {
  id: string;
  cau?: string;
  trang_thai: string;
  tap_su_dung?: number;
  ap_dung?: number;
  ghi_de?: number;
  vf_rule?: string;
  bang_chung?: string[];
  mau_minh_hoa?: boolean;
};

type Pipeline = {
  so_sua_that: number;
  so_mau_san_sang: number;
  so_luat_that_quan: number;
  so_hieu_luc: number;
  so_cho_chot: number;
  so_mau_minh_hoa: number;
  can_chay_8_buoc: boolean;
  insight: { severity: string; message: string };
};

const LOC_TRANG_THAI = [
  { value: "all", label: "Mọi trạng thái" },
  { value: "hieu_luc", label: "Đang hiệu lực" },
  { value: "de_xuat", label: "Mới đề xuất" },
  { value: "qua_vf_rule", label: "Qua vòng kiểm" },
  { value: "cho_chu_quan", label: "Chờ chủ quán" },
];

const LOC_NGUON = [
  { value: "that", label: "Luật quán thật" },
  { value: "mau", label: "Dữ liệu mẫu" },
  { value: "all", label: "Tất cả" },
];

const PAGE_SIZE = 12;

export default function CamNangPage() {
  const [token, setToken] = useState("");
  const [manager, setManager] = useState(false);
  const [chuQuan, setChuQuan] = useState(false);
  const [items, setItems] = useState<Luat[]>([]);
  const [pipeline, setPipeline] = useState<Pipeline | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [statusF, setStatusF] = useState("all");
  const [nguonF, setNguonF] = useState("that");
  const [page, setPage] = useState(1);
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [chiTiet, setChiTiet] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [copilotOpen, setCopilotOpen] = useState(false);
  const [coMau, setCoMau] = useState(false);

  useEffect(() => {
    setToken(getToken());
    setManager(isManager());
    setChuQuan(isChuQuan(getRole()));
    if (!getToken()) setLoading(false);
  }, []);

  const load = useCallback(() => {
    if (!getToken()) return;
    setLoading(true);
    apiGet<{ items: Luat[]; pipeline?: Pipeline; so_luat_that_quan?: number; co_du_lieu_mau?: boolean }>(
      `/api/v1/cam-nang?nguon=${encodeURIComponent(nguonF)}`,
    )
      .then((d) => {
        setItems((d.items ?? []).filter((x) => x && typeof x.id === "string"));
        if (d.pipeline) setPipeline(d.pipeline);
        setCoMau(d.co_du_lieu_mau === true);
        setError(null);
      })
      .catch((e) => setError(viError(e, { doing: "mở được cẩm nang quán" })))
      .finally(() => setLoading(false));
  }, [nguonF]);

  useEffect(() => {
    if (token) load();
  }, [token, load]);

  // Deep-link từ SOP: /cam-nang?id=<luat_id> — mở sẵn điều luật đó.
  useEffect(() => {
    try {
      const id = new URLSearchParams(window.location.search).get("id");
      if (id) setExpanded(id);
    } catch {
      /* ignore */
    }
  }, []);

  // Đổi bộ lọc thì về trang 1.
  useEffect(() => {
    setPage(1);
  }, [search, statusF, nguonF, items.length]);

  const filtered = useMemo(() => {
    return items.filter((luat) => {
      const text = safeText(luat.cau, "");
      if (!matchSearch(`${text} ${luat.id}`, search)) return false;
      if (statusF !== "all" && luat.trang_thai !== statusF) return false;
      return true;
    });
  }, [items, search, statusF]);

  const tongTrang = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const trangHienTai = Math.min(page, tongTrang);
  const pageItems = useMemo(() => {
    const start = (trangHienTai - 1) * PAGE_SIZE;
    return filtered.slice(start, start + PAGE_SIZE);
  }, [filtered, trangHienTai]);

  const soThat = pipeline?.so_luat_that_quan ?? 0;
  const canChay = pipeline?.can_chay_8_buoc ?? false;

  async function chay() {
    setError(null);
    setMsg(null);
    setBusy(true);
    try {
      const d = await apiSend<{
        bi_loai?: { vf_rule?: string };
        so_luat_that_quan?: number;
        pipeline?: Pipeline;
      }>("/api/v1/cam-nang/chay-8-buoc");
      if (d.pipeline) setPipeline(d.pipeline);
      const that = typeof d.so_luat_that_quan === "number" ? d.so_luat_that_quan : 0;
      setMsg(
        that > 0
          ? `Đã hoàn tất đề xuất và tập sự. Quán có ${that} luật sinh từ sửa thật — chủ quán chốt để hiệu lực.`
          : "Đã hoàn tất đề xuất và tập sự. Chủ quán cần chốt riêng trước khi luật có hiệu lực.",
      );
      setChiTiet([`Cổng loại luật: ${safeText(d.bi_loai?.vf_rule, "không có luật nào bị loại")}`]);
      load();
    } catch (e) {
      setError(
        viError(e, {
          doing: "chạy được 8 bước cẩm nang",
          forbidden: "Chỉ quản lý hoặc chủ quán chạy được 8 bước.",
          conflict: "Chưa đủ lần sửa có bằng chứng để chạy 8 bước. Ghi thêm lần sửa rồi chạy lại.",
        }),
      );
    } finally {
      setBusy(false);
    }
  }

  async function chot(id: string) {
    setBusy(true);
    setError(null);
    try {
      await apiSend("/api/v1/cam-nang/duyet", { id, ok: true });
      setMsg("Chủ quán đã chốt luật có hiệu lực — luật sẽ ảnh hưởng lần xếp lịch kế tiếp.");
      load();
    } catch (e) {
      setError(viError(e, { doing: "chốt luật có hiệu lực" }));
    } finally {
      setBusy(false);
    }
  }

  async function goLuat(id: string) {
    setBusy(true);
    setError(null);
    try {
      await apiSend("/api/v1/cam-nang/go", { id });
      setMsg("Đã gỡ luật khỏi hiệu lực.");
      load();
    } catch (e) {
      setError(viError(e, { doing: "gỡ luật" }));
    } finally {
      setBusy(false);
    }
  }

  if (!token) return <AuthGate />;

  const insight = pipeline?.insight;

  return (
    <div className="nq-page nq-page--cam-nang">
      <PageHeader
        kicker="Cẩm nang sống"
        title="Cẩm nang quán"
        meta={`Luật học từ lần sửa thật trong ca. Luật sinh từ quán: ${soThat > 0 ? soThat : "chưa có"}.`}
      />
      {coMau && nguonF !== "that" ? (
        <p className="mb-4">
          <FixtureChip />
        </p>
      ) : null}

      {!loading && pipeline ? (
        <Summary
          cells={[
            { n: pipeline.so_sua_that, k: "Lần sửa thật" },
            { n: pipeline.so_mau_san_sang, k: "Mẫu sẵn sàng", tone: pipeline.so_mau_san_sang > 0 ? "ok" : undefined },
            { n: pipeline.so_hieu_luc, k: "Đang hiệu lực", tone: "ok" },
            { n: pipeline.so_cho_chot, k: "Chờ chốt", tone: "warn" },
          ]}
        />
      ) : null}

      {insight ? (
        <div
          className={`nq-nguoi-insight nq-nguoi-insight--${insight.severity} mb-4`}
          role="status"
          aria-live="polite"
        >
          <p className="nq-nguoi-insight__label">Pipeline 8 bước</p>
          <p className="nq-nguoi-insight__text">{insight.message}</p>
        </div>
      ) : null}

      <PageActions>
        {manager ? (
          <Btn variant="primary" disabled={busy || !canChay} onClick={chay} title={!canChay ? insight?.message : undefined}>
            {busy ? "Đang chạy…" : "Chạy 8 bước xét luật"}
          </Btn>
        ) : (
          <Notice>Bạn xem được luật quán. Quản lý hoặc chủ quán mới chạy 8 bước xét luật.</Notice>
        )}
        <BtnLink href="/sop" variant="ghost">
          Hỏi quy trình
        </BtnLink>
        <Btn variant="ghost" onClick={() => setCopilotOpen(true)}>
          Hỏi trợ lý vận hành
        </Btn>
      </PageActions>

      <div className="flex flex-wrap gap-3 mb-4">
        <div className="flex-1 min-w-[200px]">
          <Field label="Tìm luật">
            <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Tìm theo nội dung…" />
          </Field>
        </div>
        <Field label="Trạng thái">
          <select className="nq-input" value={statusF} onChange={(e) => setStatusF(e.target.value)}>
            {LOC_TRANG_THAI.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Nguồn">
          <select
            className="nq-input"
            value={nguonF}
            onChange={(e) => setNguonF(e.target.value)}
            title="Luật quán thật: loại trừ dữ liệu mẫu demo. Dữ liệu mẫu: chỉ xem đối chiếu."
          >
            {LOC_NGUON.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </Field>
      </div>
      {!loading && !error ? (
        <p className="text-sm text-[var(--nq-dim)] mb-3" role="status">
          {filtered.length} / {items.length} luật
          {nguonF === "that" ? " (nguồn Thật — đã loại dữ liệu mẫu)" : null}
          {tongTrang > 1 ? ` · Trang ${trangHienTai}/${tongTrang}` : null}
        </p>
      ) : null}

      {msg ? <Alert kind="ok">{msg}</Alert> : null}
      {error ? <Alert>{error}</Alert> : null}
      {chiTiet.length > 0 ? <TechnicalDrawer lines={chiTiet} /> : null}
      {loading ? <Loading skeleton="list">Đang mở cẩm nang…</Loading> : null}
      {!loading && !error && filtered.length === 0 ? (
        <Empty>Chưa có luật phù hợp bộ lọc. Luật sinh ra từ lần sửa có bằng chứng trong ca.</Empty>
      ) : null}
      <PageGrid
        main={
      <div className="nq-lawbook">
        {/* Mục lục cuốn luật — đếm theo nhóm trạng thái để người đọc nắm nhanh */}
        <div className="nq-lawbook__toc">
          <p className="nq-lawbook__toc-title">Mục lục</p>
          <ul className="nq-lawbook__toc-list">
            <li>
              <span>Đang hiệu lực</span>
              <span className="nq-lawbook__toc-count">{items.filter((l) => l.trang_thai === "hieu_luc").length}</span>
            </li>
            <li>
              <span>Đang xét duyệt</span>
              <span className="nq-lawbook__toc-count">{items.filter((l) => ["de_xuat", "qua_vf_rule", "cho_chu_quan"].includes(l.trang_thai)).length}</span>
            </li>
            <li>
              <span>Đã loại / tắt</span>
              <span className="nq-lawbook__toc-count">{items.filter((l) => ["loai", "truot_tap_su", "tu_choi", "tu_tat"].includes(l.trang_thai)).length}</span>
            </li>
          </ul>
        </div>

        <ol className="nq-lawbook__list">
          {pageItems.map((luat, idx) => {
            const open = expanded === luat.id;
            const text = safeText(luat.cau, "Luật chưa có câu diễn giải");
            const tapSu = typeof luat.tap_su_dung === "number" ? luat.tap_su_dung : 0;
            const apDung = typeof luat.ap_dung === "number" ? luat.ap_dung : 0;
            const soDieu = (trangHienTai - 1) * PAGE_SIZE + idx + 1;
            return (
              <li
                key={luat.id}
                id={`luat-${luat.id}`}
                className={`nq-lawbook__dieu ${open ? "nq-lawbook__dieu--open" : ""}`}
              >
                <p className="nq-lawbook__dieu-so">Điều {soDieu}</p>
                <div className="nq-lawbook__dieu-head">
                  <p className="nq-lawbook__dieu-text">{text}</p>
                  <div className="nq-lawbook__dieu-meta">
                    <StatusChip tone={luatTone(luat.trang_thai)}>{luatLabel(luat.trang_thai)}</StatusChip>
                    {luat.mau_minh_hoa ? <StatusChip tone="default">Luật mẫu minh họa</StatusChip> : null}
                    {tapSu > 0 || apDung > 0 ? (
                      <span className="nq-lawbook__dieu-note">
                        Tập sự {tapSu} lần · Áp dụng {apDung} lần
                      </span>
                    ) : null}
                  </div>
                </div>
                {text.length > 140 ? (
                  <button
                    type="button"
                    className="nq-lawbook__dieu-toggle"
                    onClick={() => setExpanded(open ? null : luat.id)}
                  >
                    {open ? "Thu gọn điều luật" : "Xem đầy đủ điều luật"}
                  </button>
                ) : null}
                {open ? (
                  <div className="nq-lawbook__dieu-detail">
                    <p className="text-sm">{text}</p>
                    {luat.vf_rule ? (
                      <p className="text-sm text-[var(--nq-ink-muted)] mt-2">
                        Vòng kiểm luật: {vfRuleLyDo(luat.vf_rule)}
                      </p>
                    ) : null}
                    {(luat.bang_chung?.length ?? 0) > 0 ? (
                      <p className="text-xs text-[var(--nq-dim)] mt-1">
                        Bằng chứng: {luat.bang_chung?.length} lần sửa thật trong ca
                      </p>
                    ) : null}
                  </div>
                ) : null}
                {open && (chuQuan || manager) ? (
                  <div className="mt-3 flex flex-wrap gap-2">
                    {chuQuan && luat.trang_thai === "cho_chu_quan" ? (
                      <Btn busy={busy} onClick={() => void chot(luat.id)}>
                        Chốt hiệu lực
                      </Btn>
                    ) : null}
                    {chuQuan && luat.trang_thai === "hieu_luc" && !luat.mau_minh_hoa ? (
                      <Btn variant="ghost" busy={busy} onClick={() => void goLuat(luat.id)}>
                        Gỡ luật
                      </Btn>
                    ) : null}
                  </div>
                ) : null}
              </li>
            );
          })}
        </ol>
        {tongTrang > 1 ? (
          <nav className="mt-4 flex items-center gap-3" aria-label="Phân trang cẩm nang">
            <Btn
              variant="ghost"
              disabled={trangHienTai <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
            >
              Trang trước
            </Btn>
            <span className="text-sm text-[var(--nq-dim)]" role="status">
              Trang {trangHienTai}/{tongTrang}
            </span>
            <Btn
              variant="ghost"
              disabled={trangHienTai >= tongTrang}
              onClick={() => setPage((p) => Math.min(tongTrang, p + 1))}
            >
              Trang sau
            </Btn>
          </nav>
        ) : null}
      </div>
        }
        aside={
          <>
            <AiInsightPanel page="cam-nang" />
            <AskAiBox page="cam-nang" />
          </>
        }
      />

      <CopilotPane open={copilotOpen} onClose={() => setCopilotOpen(false)} />
    </div>
  );
}
