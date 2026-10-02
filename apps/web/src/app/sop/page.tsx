"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { apiGet, apiSend } from "../../lib/api";
import { safeText, trichDanLabel, trichDanTach, viError } from "../../lib/present";
import { getToken } from "../../lib/session";
import {
  Alert,
  AuthGate,
  Btn,
  BtnLink,
  Field,
  Loading,
  Textarea,
} from "../../ui/kit";
import { CopilotPane } from "../../ui/copilot/CopilotPane";
import { AiInsightPanel } from "../../ui/ai/AiInsightPanel";
import { AskAiBox } from "../../ui/ai/AskAiBox";

type Ans = {
  cau_tra_loi: string;
  trich_dan: string[];
  chua_co: boolean;
  mode?: string;
  provider?: string;
  do_tin?: number;
  canh_bao?: string;
  viec_lam?: string;
  phieu_ma?: string;
  phieu_buoc_ma?: string;
  ngu_canh?: { ngay?: string; thu?: string; khung?: string };
};
type Luat = { id: string; cau?: string; trang_thai: string };

type GoiY = { label: string; q: string };

const BUOC_TEN: Record<string, string> = {
  nhiet_do_tu_lanh: "Ghi nhiệt độ tủ lạnh",
  nhiet_do_tu_dong: "Ghi nhiệt độ tủ đông",
  ve_sinh_quay: "Vệ sinh quầy pha",
  ve_sinh_ban: "Lau bàn khách",
  kiem_ke_dau_ca: "Kiểm kê đầu ca",
  kiem_ke_cuoi_ca: "Kiểm kê cuối ca",
  ban_giao_ca: "Bàn giao ca",
};

function chipLabel(text: string, max = 36): string {
  const t = text.trim();
  if (t.length <= max) return t;
  return `${t.slice(0, max - 1)}…`;
}

function modeMeta(mode?: string, provider?: string): string {
  if (mode === "live") return provider ? `AI · ${provider}` : "AI trực tiếp";
  return "Tra cứu cẩm nang";
}

export default function SopPage() {
  const [token, setToken] = useState("");
  const [q, setQ] = useState("");
  const [a, setA] = useState<Ans | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [luat, setLuat] = useState<Luat[]>([]);
  const [history, setHistory] = useState<string[]>([]);
  const [ctxHint, setCtxHint] = useState("");
  const [nguonF, setNguonF] = useState("all");
  const resultRef = useRef<HTMLDivElement | null>(null);
  const daTuDongHoi = useRef(false);
  const [copilotOpen, setCopilotOpen] = useState(false);

  useEffect(() => {
    setToken(getToken());
    try {
      const raw = localStorage.getItem("nq_sop_history");
      if (raw) setHistory(JSON.parse(raw) as string[]);
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    if (!token) return;
    apiGet<{ items: Luat[] }>(`/api/v1/cam-nang?nguon=${encodeURIComponent(nguonF)}`)
      .then((d) => setLuat((d.items ?? []).filter((x) => x.trang_thai === "hieu_luc")))
      .catch(() => undefined);
    apiGet<{ ngay: string }>("/api/v1/hom-nay")
      .then((d) => setCtxHint(d.ngay ? `Ngày ${d.ngay}` : ""))
      .catch(() => undefined);
  }, [token, nguonF]);

  const goiY = useMemo(() => {
    // Gợi ý chỉ sinh từ luật đang hiệu lực của quán — không dùng danh sách
    // gợi ý cố định cũ (đã lỗi thời sau khi dữ liệu quán thay đổi).
    const fromLuat: GoiY[] = luat.map((l) => {
      const cau = safeText(l.cau, "");
      return { label: chipLabel(cau, 32), q: cau };
    });
    const seen = new Set<string>();
    const out: GoiY[] = [];
    for (const item of fromLuat) {
      if (!item.q || seen.has(item.q)) continue;
      seen.add(item.q);
      out.push(item);
      if (out.length >= 5) break;
    }
    return out;
  }, [luat]);

  const ask = useCallback(async (question: string, nguon?: string) => {
    setError(null);
    const text = question.trim();
    if (!text) {
      setError("Nhập câu hỏi trước khi bấm hỏi.");
      return;
    }
    setQ(text);
    setBusy(true);
    try {
      const chiLuatThat = (nguon ?? nguonF) === "that";
      const d = await apiSend<Ans>("/api/v1/sop", { question: text, chi_luat_that: chiLuatThat });
      setA(d);
      setHistory((prev) => {
        const next = [text, ...prev.filter((x) => x !== text)].slice(0, 8);
        localStorage.setItem("nq_sop_history", JSON.stringify(next));
        return next;
      });
    } catch (e) {
      setError(viError(e, { doing: "hỏi được cẩm nang quán" }));
    } finally {
      setBusy(false);
    }
  }, [nguonF]);

  // Deep-link từ tour/cẩm nang: /sop?q=<câu hỏi> — điền sẵn và hỏi luôn một lần.
  useEffect(() => {
    if (!token || daTuDongHoi.current) return;
    let cau = "";
    try {
      cau = new URLSearchParams(window.location.search).get("q") || "";
    } catch {
      cau = "";
    }
    if (cau.trim()) {
      daTuDongHoi.current = true;
      void ask(cau.trim());
    }
  }, [token, ask]);

  useEffect(() => {
    if (!a || busy) return;
    resultRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [a, busy]);

  if (!token) return <AuthGate />;

  const labelOpts = { luat, buocTen: BUOC_TEN };
  const trichDan = (a?.trich_dan ?? []).map((x) => safeText(x, "")).filter(Boolean);
  const showResult = busy || !!a || !!error;

  return (
    <div className="nq-page nq-page--run nq-sop-copilot">
      <header className="nq-sop-copilot__head">
        <p className="nq-sop-copilot__kicker">Trợ lý quy trình</p>
        <h1 className="nq-sop-copilot__title">Hỏi quy trình quán</h1>
        <p className="nq-sop-copilot__lead">
          Một câu trả lời rõ ràng từ phiếu và luật đã duyệt — lọc theo ca hôm nay, không bịa.
        </p>
        {ctxHint ? <p className="nq-sop-copilot__ctx-hint">{ctxHint}</p> : null}
        <div className="nq-sop-copilot__agent-row">
          <Btn variant="ghost" onClick={() => setCopilotOpen(true)}>
            Hỏi trợ lý vận hành
          </Btn>
          <span className="nq-sop-copilot__agent-note">
            AG-COPILOT tra cứu quy trình và đề xuất luật mới từ lần sửa thật.
          </span>
        </div>
      </header>

      <section className="nq-sop-copilot__shell" aria-label="Hỏi cẩm nang">
        <div className="nq-sop-copilot__compose">
          <div className="nq-sop-copilot__field">
            <Field label="Câu hỏi">
            <Textarea
              value={q}
              onChange={(e) => setQ(e.target.value)}
              rows={2}
              placeholder="Ví dụ: Nhiệt độ tủ lạnh bao nhiêu là được?"
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) void ask(q);
              }}
            />
            </Field>
          </div>
          <Btn
            variant="primary"
            className="nq-sop-copilot__send"
            disabled={busy}
            onClick={() => void ask(q)}
          >
            {busy ? "Đang tra…" : "Hỏi"}
          </Btn>
        </div>

        {goiY.length > 0 ? (
          <div className="nq-sop-copilot__suggest">
            <span className="nq-sop-copilot__suggest-label">Luật hiệu lực của quán</span>
            <div className="nq-sop-copilot__suggest-row" role="list">
              {goiY.map((item) => (
                <button
                  key={item.q}
                  type="button"
                  className="nq-sop-copilot__suggest-chip"
                  title={item.q}
                  disabled={busy}
                  onClick={() => void ask(item.q)}
                >
                  {item.label}
                </button>
              ))}
            </div>
          </div>
        ) : null}

        {history.length > 0 ? (
          <details className="nq-sop-copilot__recent">
            <summary>Câu gần đây ({history.length})</summary>
            <ul>
              {history.map((h) => (
                <li key={h}>
                  <button type="button" disabled={busy} onClick={() => void ask(h)}>
                    {h}
                  </button>
                </li>
              ))}
            </ul>
          </details>
        ) : null}

        {showResult ? (
          <div className="nq-sop-copilot__result" ref={resultRef} aria-live="polite">
            {busy && !a ? <Loading skeleton="text">Đang tra cẩm nang…</Loading> : null}

            {error ? <Alert>{error}</Alert> : null}

            {a ? (
              <article className="nq-sop-copilot__answer">
                <div className="nq-sop-copilot__answer-meta">
                  <span
                    className={
                      a.chua_co
                        ? "nq-sop-copilot__status nq-sop-copilot__status--warn"
                        : "nq-sop-copilot__status nq-sop-copilot__status--ok"
                    }
                  >
                    {a.chua_co ? "Chưa có trong cẩm nang" : "Có trong cẩm nang"}
                  </span>
                  <span className="nq-sop-copilot__mode">{modeMeta(a.mode, a.provider)}</span>
                  {!a.chua_co && typeof a.do_tin === "number" && a.do_tin > 0 ? (
                    <span className="nq-sop-copilot__mode">
                      Tin cậy {Math.round(a.do_tin * 100)}%
                    </span>
                  ) : null}
                  {a.ngu_canh?.thu && a.ngu_canh?.khung ? (
                    <span className="nq-sop-copilot__mode">
                      Ca {a.ngu_canh.thu} · {a.ngu_canh.khung}
                    </span>
                  ) : null}
                </div>

                {a.canh_bao ? <Alert kind="info">{a.canh_bao}</Alert> : null}

                <p className="nq-sop-copilot__answer-text">
                  {safeText(a.cau_tra_loi, "Cẩm nang chưa có câu trả lời cho câu này.")}
                </p>

                {a.chua_co ? (
                  <p className="nq-sop-copilot__cta">
                    <BtnLink href="/cam-nang" variant="ghost">
                      Đề xuất luật mới
                    </BtnLink>
                  </p>
                ) : a.phieu_ma ? (
                  <p className="nq-sop-copilot__cta">
                    <BtnLink href="/phieu" variant="ghost">
                      Mở phiếu quy trình
                    </BtnLink>
                  </p>
                ) : null}

                {trichDan.length > 0 ? (
                  <div className="nq-sop-copilot__sources">
                    <p className="nq-sop-copilot__sources-title">Nguồn dẫn</p>
                    <ul>
                      {trichDan.map((t) => {
                        const { loai } = trichDanTach(t);
                        const label = trichDanLabel(t, labelOpts);
                        const ma = t.includes(":") ? t.split(":").slice(1).join(":") : "";
                        const href =
                          loai === "luat" && ma
                            ? `/cam-nang?id=${encodeURIComponent(ma)}`
                            : loai === "phieu"
                              ? "/phieu"
                              : "";
                        return (
                          <li key={t}>
                            <span className="nq-sop-copilot__source-tag">
                              {loai === "luat" ? "Luật" : loai === "phieu" ? "Phiếu" : "Nguồn"}
                            </span>
                            {href ? <Link href={href}>{label}</Link> : label}
                          </li>
                        );
                      })}
                    </ul>
                  </div>
                ) : null}
              </article>
            ) : null}

            {!busy && !a && !error ? (
              <p className="nq-sop-copilot__placeholder">
                Câu trả lời sẽ hiện tại đây sau khi bạn gửi câu hỏi.
              </p>
            ) : null}
          </div>
        ) : (
          <p className="nq-sop-copilot__placeholder nq-sop-copilot__placeholder--idle">
            Gõ câu hỏi hoặc chọn gợi ý — hệ thống chỉ trả lời từ phiếu và luật quán.
          </p>
        )}
      </section>

      <div className="nq-sop-copilot__suggest" aria-label="Nguồn trả lời">
        <span className="nq-sop-copilot__suggest-label">Nguồn trả lời</span>
        <div className="nq-sop-copilot__suggest-row" role="group">
          <button
            type="button"
            className="nq-sop-copilot__suggest-chip"
            aria-pressed={nguonF === "that"}
            disabled={busy}
            onClick={() => setNguonF("that")}
            title="Chỉ trả lời từ luật quán thật — loại trừ dữ liệu mẫu demo"
          >
            Luật quán thật
          </button>
          <button
            type="button"
            className="nq-sop-copilot__suggest-chip"
            aria-pressed={nguonF === "all"}
            disabled={busy}
            onClick={() => setNguonF("all")}
            title="Trả lời từ mọi luật trong cẩm nang, gồm luật mẫu minh họa"
          >
            Tất cả nguồn
          </button>
        </div>
      </div>

      <footer className="nq-sop-copilot__foot">
        <span>
          {luat.length > 0
            ? `${luat.length} luật đang hiệu lực${nguonF === "that" ? " (nguồn Thật)" : ""}`
            : "Chưa có luật hiệu lực"}
        </span>
        <Link href="/cam-nang">Mở cẩm nang</Link>
      </footer>

      <section className="nq-sop-copilot__ai" aria-label="AI phân tích trang này">
        <AiInsightPanel page="sop" />
        <AskAiBox page="sop" />
      </section>

      <CopilotPane open={copilotOpen} onClose={() => setCopilotOpen(false)} />
    </div>
  );
}
