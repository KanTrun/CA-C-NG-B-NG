"use client";

/**
 * MemoryInline — ký ức quán (Hồn quán) nhúng thẳng vào /quanverse:
 * xem ký ức đã xác nhận · đề xuất ký ức mới · xác nhận (consent) ngay tại chỗ.
 *
 * Chỉ ĐỌC + ghi qua API ký ức (không mutation lịch/nhân sự). Dữ liệu thật từ
 * `GET /experience/memories`; thêm mới qua `/memories/propose` → `/consent`.
 */

import { useCallback, useEffect, useState } from "react";
import { ExpEmpty } from "../exp-kit";
import { Icon } from "../../icons";

interface Memory {
  memory_id: string;
  anchor_id: string;
  content: string;
  status: string;
  consent_status: string;
}

export default function MemoryInline() {
  const token =
    typeof window !== "undefined"
      ? window.sessionStorage.getItem("nq_token") || window.localStorage.getItem("nq_token") || ""
      : "";
  const base = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";
  const auth: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};

  const [items, setItems] = useState<Memory[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [anchor, setAnchor] = useState("");
  const [content, setContent] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const res = await fetch(`${base}/api/v1/experience/memories`, { headers: auth });
      if (!res.ok) throw new Error(String(res.status));
      const body = (await res.json()) as { memories?: Memory[] };
      setItems(body.memories ?? []);
      setError(null);
    } catch {
      setError("Chưa đọc được ký ức.");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [base, token]);

  useEffect(() => {
    void load();
  }, [load]);

  const propose = useCallback(async () => {
    if (!anchor.trim() || !content.trim()) {
      setError("Cần chọn khu vực và nội dung ký ức.");
      return;
    }
    setBusy(true);
    try {
      const res = await fetch(`${base}/api/v1/experience/memories/propose`, {
        method: "POST",
        headers: { ...auth, "Content-Type": "application/json" },
        body: JSON.stringify({
          proposal_id: `ui_${Date.now()}`,
          anchor_id: anchor.trim(),
          owner_scope: "quan",
          content: content.trim(),
          source_event_ids: [],
          visibility: "staff",
          proposed_by: "quan_ly",
        }),
      });
      if (!res.ok) throw new Error(String(res.status));
      setContent("");
      await load();
      setError(null);
    } catch {
      setError("Không tạo được đề xuất ký ức.");
    } finally {
      setBusy(false);
    }
  }, [anchor, content, base, auth, load]);

  const confirm = useCallback(
    async (id: string) => {
      try {
        await fetch(`${base}/api/v1/experience/memories/${encodeURIComponent(id)}/consent`, {
          method: "POST",
          headers: { ...auth, "Content-Type": "application/json" },
          body: JSON.stringify({ grant: true }),
        });
        await load();
      } catch {
        setError("Không xác nhận được ký ức.");
      }
    },
    [base, auth, load],
  );

  return (
    <div className="nq-meminline">
      {error ? <p className="nq-meminline__err">{error}</p> : null}
      {items.length === 0 ? (
        <ExpEmpty icon="pin" title="Chưa có ký ức nào" hint="Thêm ký ức đầu tiên bên dưới." />
      ) : (
        <ul className="nq-meminline__list" data-testid="quanverse-memories">
          {items.map((m) => (
            <li key={m.memory_id} className="nq-meminline__item">
              <div className="nq-meminline__body">
                <span className="nq-meminline__anchor">
                  <Icon name="location" size={12} /> {m.anchor_id}
                </span>
                <span className="nq-meminline__content">{m.content}</span>
              </div>
              {m.status === "confirmed" ? (
                <span className="nq-meminline__ok">
                  <Icon name="check" size={12} /> đã xác nhận
                </span>
              ) : (
                <button
                  type="button"
                  className="nq-btn-compact nq-modebtn"
                  onClick={() => void confirm(m.memory_id)}
                >
                  <Icon name="check" size={13} />
                  Xác nhận
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
      <div className="nq-meminline__form">
        <input
          aria-label="Khu vực"
          placeholder="Khu vực (vd: bar)"
          value={anchor}
          onChange={(e) => setAnchor(e.target.value)}
        />
        <input
          aria-label="Nội dung ký ức"
          placeholder="Ký ức mới…"
          value={content}
          onChange={(e) => setContent(e.target.value)}
        />
        <button type="button" className="nq-btn-compact nq-modebtn" disabled={busy} onClick={() => void propose()}>
          <Icon name="plus" size={13} />
          {busy ? "Đang lưu…" : "Thêm ký ức"}
        </button>
      </div>
    </div>
  );
}
