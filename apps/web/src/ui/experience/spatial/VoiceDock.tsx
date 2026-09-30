"use client";

/**
 * VoiceDock — hỏi HỒN QUÁN bằng chữ (mic là bước sau), trả lời có căn cứ.
 *
 * Không in `proposal_id` ra UI: người hỏi cần biết "đã đề xuất ghi nhớ" và
 * "đang chờ ai duyệt", không cần mã nội bộ.
 */

import { useEffect, useRef, useState } from "react";
import { ApiError } from "../../../lib/api";
import { viError } from "../../../lib/present";
import { getNvId } from "../../../lib/session";
import { Icon } from "../../icons";

interface VoiceResponse {
  turn_id: string;
  transcript: string;
  response_text: string;
  citations: string[];
  grounded: boolean;
  proposal?: { proposal_id: string } | null;
}

interface Props {
  anchorId: string | null;
  /**
   * Báo cho trang cha khi một đề xuất ghi nhớ đã được tạo — để khung chi
   * tiết neo nạp lại và draft mới hiện ngay trong "Chờ quyết định".
   *
   * Bản trước không có chữ ký này, nên sau khi người dùng nói "nhớ điều này…"
   * UI khẳng định "chờ quản lý xác nhận" nhưng KHÔNG có gì xảy ra tiếp: quản
   * lý phải tự F5 mới thấy draft (nếu API có lưu). Luồng gãy ngay tại chỗ.
   */
  onRemembered?: () => void;
}

const COPY = {
  ask: {
    doing: "hỏi được HỒN QUÁN",
    missing: "Neo này chưa có ký ức nào để trả lời. Chọn neo khác hoặc ghi nhớ điều gì đó trước.",
  },
} as const;

export default function VoiceDock({ anchorId, onRemembered }: Props) {
  const [transcript, setTranscript] = useState("");
  const [response, setResponse] = useState<VoiceResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const base = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";
  const token =
    typeof window !== "undefined" &&
    (window.sessionStorage.getItem("nq_token") ||
      window.localStorage.getItem("nq_token"));
  const tokenStr = typeof token === "string" ? token : "";

  async function ask() {
    const text = transcript.trim();
    if (!text) return;
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`${base}/api/v1/experience/voice/turn`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(tokenStr ? { Authorization: `Bearer ${tokenStr}` } : {}),
        },
        body: JSON.stringify({
          conversation_id: `conv_${Date.now()}`,
          transcript: text,
          anchor_id: anchorId,
          requester_id: getNvId() || "quan_ly_demo",
        }),
      });
      if (!res.ok) throw new ApiError(res.status);
      const body = (await res.json()) as VoiceResponse;
      setResponse(body);
      // Đề xuất mới sinh ra → báo trang cha nạp lại chi tiết neo + số đếm,
      // để draft hiện ngay trong "Chờ quyết định" và cột 3D cập nhật số ký ức.
      if (body.proposal) onRemembered?.();
    } catch (e) {
      setError(viError(e, COPY.ask));
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  return (
    <section className="nq-voicedock" aria-label="Giọng nói / văn bản HỒN QUÁN">
      <div className="nq-voicedock__input">
        <input
          ref={inputRef}
          type="text"
          value={transcript}
          data-testid="voice-input"
          onChange={(e) => setTranscript(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && ask()}
          placeholder="Hỏi: 'Ở đây từng xảy ra chuyện gì?' hoặc 'Nhớ điều này…'"
          aria-label="Hỏi HỒN QUÁN"
        />
        <button
          type="button"
          className="nq-btn nq-btn-primary"
          data-testid="voice-ask"
          disabled={busy || !transcript.trim() || !anchorId}
          onClick={ask}
        >
          <Icon name="send" size={15} />
          {busy ? "Đang xử lý…" : "Hỏi"}
        </button>
      </div>

      {!anchorId ? (
        <p className="nq-voicedock__hint">
          Chọn một neo trên bản đồ trước — câu trả lời luôn gắn với một khu vực cụ thể.
        </p>
      ) : null}

      {error ? (
        <div className="nq-alert nq-alert--error" role="alert">
          {error}
        </div>
      ) : null}

      {response ? (
        <div className="nq-voicedock__response" data-testid="voice-response" aria-live="polite">
          <p className="nq-voicedock__text">{response.response_text}</p>
          {/* Khối trích dẫn CHỈ tồn tại khi thật sự có ký ức đã xác nhận.
              Bản trước luôn render thẻ này, và khi không có trích dẫn thì in
              "Chưa có ký ức nào đã xác nhận ở khu vực này". Nhìn thì vô hại,
              nhưng nó phá đúng hợp đồng mà e2e dùng để bắt lỗi bịa:
              `expect(resp.locator(".nq-voicedock__citations")).toHaveCount(0)`
              — thẻ luôn có mặt nên phép kiểm "không bịa" không bao giờ chạy đúng.
              Sự VẮNG MẶT của thẻ chính là bằng chứng máy kiểm được; còn câu
              "chưa có ký ức nào" đã nằm trong `response_text` do agent sinh
              ("Chưa có ký ức đã xác nhận cho khu vực này. (Không suy đoán nội dung.)"),
              nên không mất thông tin cho người dùng. */}
          {response.citations.length ? (
            <p className="nq-voicedock__citations">
              {`Dựa trên ${response.citations.length} ký ức đã xác nhận`}
            </p>
          ) : null}
          {response.proposal ? (
            <p className="nq-voicedock__proposal">
              <Icon name="pin" size={13} />
              Đã đề xuất ghi nhớ điều này — chờ quản lý xác nhận trước khi lưu.
            </p>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}