"use client";

import { useCallback, useEffect, useState } from "react";
import { apiGet, apiSend } from "../../lib/api";
import { actorLabel, formatLuc, safeText, viError } from "../../lib/present";
import { getToken } from "../../lib/session";
import { CopilotPane } from "../../ui/copilot/CopilotPane";
import {
    Alert,
    AuthGate,
    Btn,
    Empty,
    Field,
    Loading,
    OpsCard,
    PageActions,
    PageHeader,
    PagedList,
    Textarea,
} from "../../ui/kit";

type Sbar = {
  id?: string;
  luc?: string;
  tinh_hinh?: unknown;
  boi_canh?: unknown;
  danh_gia?: unknown;
  de_nghi?: unknown;
  co_lech_so?: boolean;
  vf_number_conflict?: { chu_de: string; gia_tri: number[]; cau: string[] }[];
};

const CHU_DE_LABEL: Record<string, string> = {
  ket: "Tiền két",
  doanh_thu: "Doanh thu",
  chi_phi: "Chi phí",
  hao_hut: "Hao hụt",
};

function dinhDangTien(v: number): string {
  return v.toLocaleString("vi-VN") + "đ";
}

export default function HandoverPage() {
  const [token, setToken] = useState("");
  const [text, setText] = useState("");
  const [out, setOut] = useState<Sbar | null>(null);
  const [history, setHistory] = useState<Sbar[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [copilotOpen, setCopilotOpen] = useState(false);

  useEffect(() => {
    setToken(getToken());
  }, []);

  const loadHistory = useCallback(() => {
    if (!getToken()) return;
    apiGet<{ items: Sbar[] }>("/api/v1/handover")
      .then((d) => setHistory((d.items ?? []).slice().reverse()))
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    if (token) loadHistory();
  }, [token, loadHistory]);

  async function run() {
    setError(null);
    if (!text.trim()) {
      setError("Ghi nội dung ca trước khi tách bàn giao.");
      return;
    }
    setBusy(true);
    try {
      const d = await apiSend<Sbar>("/api/v1/handover", { text: text.trim() });
      setOut(d);
      loadHistory();
    } catch (e) {
      setError(viError(e, { doing: "tách được bàn giao thành bốn phần" }));
    } finally {
      setBusy(false);
    }
  }

  if (!token) return <AuthGate />;

  return (
    <div className="nq-page nq-page--run">
      <PageHeader
        kicker="SBAR"
        title="Bàn giao"
        meta="Ghi ca vừa rồi theo mẫu Tình hình · Bối cảnh · Đánh giá · Đề nghị — hệ thống tách và lưu cho ca sau."
      />
      <PageActions>
        <Btn variant="ghost" onClick={() => setCopilotOpen(true)}>
          Hỏi trợ lý vận hành
        </Btn>
      </PageActions>
      <Field label="Nội dung ca">
        <Textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={8}
          placeholder={
            "Tình hình: …\nBối cảnh: …\nĐánh giá: …\nĐề nghị: …\nTreo: … (nếu có việc kẹt)"
          }
        />
      </Field>
      <Btn variant="primary" disabled={busy} onClick={run}>
        {busy ? "Đang tách…" : "Tách thành bàn giao"}
      </Btn>
      {error ? <Alert>{error}</Alert> : null}
      {busy && !out ? <Loading skeleton="text">Đang tách nội dung ca…</Loading> : null}
      {out ? (
        <OpsCard eyebrow="Bàn giao cho ca sau" title="Bốn phần đã tách">
          {out.co_lech_so && Array.isArray(out.vf_number_conflict) && out.vf_number_conflict.length > 0 ? (
            <Alert>
              <strong>Phát hiện số liệu lệch giữa các ca — cần người xác minh:</strong>
              <ul style={{ margin: "var(--nq-s2) 0 0", paddingLeft: "1.1em" }}>
                {out.vf_number_conflict.map((c) => (
                  <li key={c.chu_de}>
                    {CHU_DE_LABEL[c.chu_de] ?? c.chu_de}: {" "}
                    {c.gia_tri.map((v) => dinhDangTien(v)).join(" ≠ ")}
                  </li>
                ))}
              </ul>
              <span style={{ display: "block", marginTop: "var(--nq-s2)" }}>
                Hệ thống không tự chọn bên nào — quản lý đối chiếu sổ rồi chốt.
              </span>
            </Alert>
          ) : null}
          <p>
            <strong>Tình hình:</strong> {safeText(out.tinh_hinh, "chưa nhận ra trong nội dung")}
          </p>
          <p>
            <strong>Bối cảnh:</strong> {safeText(out.boi_canh, "chưa nhận ra trong nội dung")}
          </p>
          <p>
            <strong>Đánh giá:</strong> {safeText(out.danh_gia, "chưa nhận ra trong nội dung")}
          </p>
          <p>
            <strong>Đề nghị:</strong> {safeText(out.de_nghi, "chưa nhận ra trong nội dung")}
          </p>
        </OpsCard>
      ) : (
        !busy && !error && <Empty>Chưa tách lần nào. Ghi nội dung ca rồi bấm tách.</Empty>
      )}

      {history.length > 0 ? (
        <OpsCard density="compact" eyebrow="Lịch sử" title="Bàn giao gần đây" count={history.length} countLabel="lần">
          <PagedList
            items={history}
            pageSize={10}
            className="nq-list"
            renderItem={(h) => (
              <article key={h.id ?? h.luc} className="nq-item">
                <p className="nq-item-title">{safeText(h.tinh_hinh, "Bàn giao ca")}</p>
                <p className="nq-item-sub">
                  {formatLuc(h.luc)} · {actorLabel("nhan_vien")}
                </p>
              </article>
            )}
          />
        </OpsCard>
      ) : null}
      <CopilotPane open={copilotOpen} onClose={() => setCopilotOpen(false)} />
    </div>
  );
}
