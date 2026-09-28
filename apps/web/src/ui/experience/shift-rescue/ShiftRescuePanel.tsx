"use client";

/**
 * Shift Rescue — luồng đầy đủ: báo vắng → tìm người bù → mời → phản hồi → xác nhận.
 *
 * Bản trước chỉ đi tới `invite` rồi dừng: API có `respond` và `confirm` nhưng
 * không UI nào gọi, nên ca cứu không bao giờ chốt được người — người được mời
 * cũng không có cách nào nhận hoặc từ chối. Bản này đi hết vòng đời và phản ánh
 * đúng trạng thái máy chủ trả về ở từng bước.
 *
 * Chọn ca và người vắng lấy từ `GET /shift-rescue/options` thay vì hardcode một
 * kịch bản — trước đây chỉ chạy được đúng ca "t7_toi / nv_absent_quan".
 */

import { useCallback, useEffect, useState } from "react";
import { ApiError } from "../../../lib/api";
import { viError } from "../../../lib/present";
import { Icon } from "../../icons";
import { ExpEmpty } from "../exp-kit";
import {
  dayPartLabel,
  eligibilityReasonLabel,
  positionLabel,
  rescueStatusLabel,
  weekdayLabel,
} from "../exp-present";
import CandidateTable from "./CandidateTable";

interface Candidate {
  candidate_id: string;
  nv_id: string;
  nv_ten: string;
  safe: boolean;
  reason_passes: string[];
  reason_blocks: string[];
  fairness_delta: number;
  added_hours: number;
  skill_coverage: Record<string, boolean>;
  rank?: number;
}

interface CaseView {
  case_id: string;
  status: string;
  candidates: Candidate[];
  blocked: Candidate[];
  invited: string[];
}

interface ShiftOption {
  shift_id: string;
  thu: string;
  khung: string;
  vi_tri: string;
  bat_dau: string;
  ket_thuc: string;
  assigned: { nv_id: string; ten: string }[];
}

const COPY = {
  options: { doing: "đọc được danh sách ca của quán" },
  intake: { doing: "ghi nhận báo vắng" },
  candidates: { doing: "tìm được người bù an toàn" },
  invite: { doing: "gửi lời mời" },
  respond: { doing: "ghi nhận phản hồi của người được mời" },
  confirm: {
    doing: "chốt người bù cho ca này",
    conflict:
      "Lịch đã đổi ở nơi khác nên chưa chốt được. Tải lại rồi chạy lại từ bước tìm người bù.",
  },
} as const;

/**
 * Gộp lý do loại thành câu đọc được: "vì 2 người vượt giới hạn giờ, 1 người
 * thiếu kỹ năng". Đếm theo MÃ lý do để không lặp lại cùng một câu nhiều lần.
 */
function blockReasonSummary(blocked: { reason_blocks?: string[] }[]): string {
  const counts = new Map<string, number>();
  for (const b of blocked) {
    for (const code of b.reason_blocks ?? []) {
      counts.set(code, (counts.get(code) ?? 0) + 1);
    }
  }
  if (counts.size === 0) return ".";
  const parts = [...counts.entries()]
    .sort((a, b) => b[1] - a[1])
    .map(([code, n]) => `${n} người ${eligibilityReasonLabel(code).toLowerCase()}`);
  return ` vì ${parts.join(", ")}.`;
}

export default function ShiftRescuePanel() {
  const [caseId, setCaseId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [caze, setCaze] = useState<CaseView | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  /** Ca + người vắng do người dùng chọn, không hardcode. */
  const [shifts, setShifts] = useState<ShiftOption[]>([]);
  const [shiftId, setShiftId] = useState("");
  const [absenceNvId, setAbsenceNvId] = useState("");
  const [reason, setReason] = useState("Ốm đột xuất");
  const [optionsError, setOptionsError] = useState<unknown>(null);
  const [nguon, setNguon] = useState<"lich_tuan" | "fixture" | "">("");

  const api = useCallback(
    async <T,>(path: string, body?: unknown, method = "POST"): Promise<T> => {
      const token =
        window.sessionStorage.getItem("nq_token") ||
        window.localStorage.getItem("nq_token") ||
        "";
      const base = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";
      const res = await fetch(`${base}/api/v1${path}`, {
        method,
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: body === undefined ? undefined : JSON.stringify(body),
      });
      if (!res.ok) throw new ApiError(res.status);
      return (await res.json()) as T;
    },
    [],
  );

  // Nạp ca + người đang được phân ca để màn báo vắng có lựa chọn thật.
  useEffect(() => {
    let cancelled = false;
    api<{ shifts: ShiftOption[]; nguon?: string }>("/experience/shift-rescue/options", undefined, "GET")
      .then((res) => {
        if (cancelled) return;
        setShifts(res.shifts ?? []);
        setNguon(res.nguon === "lich_tuan" ? "lich_tuan" : "fixture");
        const first = res.shifts?.[0];
        if (first) {
          setShiftId((cur) => cur || first.shift_id);
          setAbsenceNvId((cur) => cur || (first.assigned[0]?.nv_id ?? ""));
        }
        setOptionsError(null);
      })
      .catch((e) => {
        if (!cancelled) setOptionsError(e);
      });
    return () => {
      cancelled = true;
    };
  }, [api]);

  /** Người đang được phân ca của ca đã chọn — báo vắng chỉ áp cho họ. */
  const currentShift = shifts.find((s) => s.shift_id === shiftId);

  const refreshCase = useCallback(
    async (id: string) => {
      const view = await api<CaseView>(
        `/experience/shift-rescue/${id}`,
        undefined,
        "GET",
      );
      setCaze(view);
      return view;
    },
    [api],
  );

  const intake = useCallback(async () => {
    if (!shiftId || !absenceNvId) {
      setError("Chọn ca và chọn người vắng trước khi ghi nhận.");
      return;
    }
    setBusy(true);
    setError(null);
    setCaze(null);
    setNotice(null);
    try {
      const res = await api<{ case_id: string }>("/experience/shift-rescue/intake", {
        case_id: `rescue_demo_${Date.now()}`,
        absence_nv_id: absenceNvId,
        shift_id: shiftId,
        reason: reason.trim() || "Ốm đột xuất",
      });
      setCaseId(res.case_id);
      await api(`/experience/shift-rescue/${res.case_id}/candidates`);
      await refreshCase(res.case_id);
      setNotice("Đã ghi nhận báo vắng và tìm được danh sách người bù.");
    } catch (e) {
      setError(viError(e, COPY.intake));
    } finally {
      setBusy(false);
    }
  }, [api, absenceNvId, shiftId, reason, refreshCase]);

  const proposeAndInvite = useCallback(
    async (candidateId: string) => {
      if (!caseId) return;
      setBusy(true);
      setError(null);
      setNotice(null);
      try {
        await api(`/experience/shift-rescue/${caseId}/propose`, {
          candidate_id: candidateId,
        });
        await api(`/experience/shift-rescue/${caseId}/invite`, {
          candidate_ids: [candidateId],
        });
        setSelected(candidateId);
        await refreshCase(caseId);
        setNotice("Đã gửi lời mời. Chờ người được mời phản hồi.");
      } catch (e) {
        setError(viError(e, COPY.invite));
      } finally {
        setBusy(false);
      }
    },
    [api, caseId, refreshCase],
  );

  /** Người được mời nhận hoặc từ chối — bước trước đây không có UI. */
  const respond = useCallback(
    async (candidateId: string, accept: boolean) => {
      if (!caseId) return;
      setBusy(true);
      setError(null);
      setNotice(null);
      try {
        await api(`/experience/shift-rescue/${caseId}/respond`, {
          candidate_id: candidateId,
          accept,
        });
        await refreshCase(caseId);
        setNotice(
          accept
            ? "Người được mời đã nhận ca. Bước cuối là xác nhận vào lịch."
            : "Người được mời đã từ chối. Mời người kế tiếp trong danh sách an toàn.",
        );
      } catch (e) {
        setError(viError(e, COPY.respond));
      } finally {
        setBusy(false);
      }
    },
    [api, caseId, refreshCase],
  );

  const confirm = useCallback(async () => {
    if (!caseId || !selected) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const res = await api<{ treo_id?: string }>(`/experience/shift-rescue/${caseId}/confirm`, {
        candidate_id: selected,
      });
      await refreshCase(caseId);
      setNotice(
        res?.treo_id
          ? "Đã chốt người bù — đã tạo việc trong Sổ việc treo, mở /treo để ghim vào lịch tuần."
          : "Đã chốt người bù cho ca này. Thao tác có lưu vết kiểm toán.",
      );
    } catch (e) {
      setError(viError(e, COPY.confirm));
    } finally {
      setBusy(false);
    }
  }, [api, caseId, selected, refreshCase]);

  return (
    <div className="nq-rescue">
      <header className="nq-rescue__header">
        <h1>AI Shift Rescue</h1>
        <p>
          Báo vắng đột xuất → danh sách người thay an toàn theo ràng buộc thật →
          mời → phản hồi → chốt. Không ai bị đưa vào ca mà không được hỏi.
        </p>
        {nguon ? (
          <p className="nq-rescue__nguon" role="note">
            {nguon === "lich_tuan"
              ? "Dữ liệu: ca & người THẬT từ lịch tuần đang áp dụng."
              : "Dữ liệu: mẫu demo (chưa có lịch tuần thật cho tuần này)."}
          </p>
        ) : null}
      </header>

      {error ? (
        <div className="nq-alert nq-alert--error" role="alert">
          {error}
        </div>
      ) : null}
      {notice ? (
        <div className="nq-alert nq-alert--info" role="status">
          {notice}
        </div>
      ) : null}

      {/* Bước 1 — chọn ca và người vắng (không hardcode kịch bản). */}
      <section className="nq-rescue__step" aria-label="Bước 1: báo vắng">
        <h2 className="nq-rescue__stephead">
          <span className="nq-rescue__stepnum">1</span>
          Báo vắng
        </h2>

        {optionsError ? (
          <div className="nq-alert nq-alert--error" role="alert">
            {viError(optionsError, COPY.options)}
          </div>
        ) : shifts.length === 0 ? (
          <ExpEmpty
            icon="calendar"
            title="Chưa có ca nào đang phân người"
            hint="Ca cứu chỉ chạy được khi lịch đã có người — kiểm tra lịch tuần trước."
          />
        ) : (
          <div className="nq-rescue__form">
            <label className="nq-rescue__field">
              <span>Ca cần cứu</span>
              <select
                data-testid="rescue-shift"
                value={shiftId}
                onChange={(e) => {
                  const next = e.target.value;
                  setShiftId(next);
                  const shift = shifts.find((s) => s.shift_id === next);
                  setAbsenceNvId(shift?.assigned[0]?.nv_id ?? "");
                }}
              >
                {shifts.map((s) => (
                  <option key={s.shift_id} value={s.shift_id}>
                    {weekdayLabel(s.thu)} {dayPartLabel(s.khung)} · {s.bat_dau}–
                    {s.ket_thuc} · {positionLabel(s.vi_tri)}
                  </option>
                ))}
              </select>
            </label>

            <label className="nq-rescue__field">
              <span>Người báo vắng</span>
              <select
                data-testid="rescue-absence"
                value={absenceNvId}
                onChange={(e) => setAbsenceNvId(e.target.value)}
              >
                {(currentShift?.assigned ?? []).map((a) => (
                  <option key={a.nv_id} value={a.nv_id}>
                    {a.ten}
                  </option>
                ))}
              </select>
            </label>

            <label className="nq-rescue__field">
              <span>Lý do</span>
              <input
                type="text"
                data-testid="rescue-reason"
                value={reason}
                placeholder="vd: Ốm đột xuất"
                onChange={(e) => setReason(e.target.value)}
              />
            </label>

            <button
              type="button"
              className="nq-btn nq-btn-primary"
              data-testid="rescue-intake"
              disabled={busy || !shiftId || !absenceNvId}
              onClick={intake}
            >
              <Icon name="users" size={16} />
              {busy ? "Đang xử lý…" : "Ghi nhận & tìm người bù"}
            </button>
          </div>
        )}
      </section>

      {caze ? (
        <div className="nq-rescue__case">
          <p className="nq-rescue__status" data-testid="rescue-status">
            Trạng thái ca: <strong>{rescueStatusLabel(caze.status)}</strong>
          </p>

          {/* AI ĐÃ LÀM GÌ — bằng chứng cụ thể, không phải lời hứa.
              Người dùng hỏi "AI ở đâu, làm được gì": khối này trả lời bằng SỐ
              của chính lượt tìm người vừa chạy — bao nhiêu người bị loại và vì
              lý do gì, ai được xếp trên ai theo tiêu chí nào. Mọi con số đều
              lấy từ payload `/shift-rescue/{id}/candidates`, không suy diễn. */}
          <section className="nq-rescue__ai" aria-label="AI đã tính gì cho ca này" data-testid="rescue-ai">
            <div className="nq-rescue__aihead">
              <Icon name="bot" size={16} />
              <h3 className="nq-exp-section__title">AI đã tính gì</h3>
              <span className="nq-exp-section__spacer" />
              <span className="nq-rolechip">
                <Icon name="info" size={13} />
                Luật tất định, không đoán
              </span>
            </div>
            <ul className="nq-rescue__ailist" data-testid="rescue-ai-facts">
              <li>
                Đọc {caze.candidates.length + (caze.blocked?.length ?? 0)} người trong
                danh sách ca, giữ lại <strong>{caze.candidates.length}</strong> người
                không vi phạm ràng buộc cứng.
              </li>
              {caze.blocked?.length ? (
                <li>
                  Loại <strong>{caze.blocked.length}</strong> người
                  {blockReasonSummary(caze.blocked)}
                </li>
              ) : null}
              {caze.candidates.length ? (
                <li>
                  Xếp hạng theo công bằng + số giờ thêm + độ phủ kỹ năng; người đứng
                  đầu là <strong>{caze.candidates[0]?.nv_ten || "—"}</strong>
                  {typeof caze.candidates[0]?.fairness_delta === "number"
                    ? ` (lệch công bằng ${caze.candidates[0].fairness_delta.toFixed(2)}, thêm ${caze.candidates[0].added_hours} giờ)`
                    : ""}
                  .
                </li>
              ) : null}
              <li>
                Không tự mời ai. Hệ thống chỉ đề xuất; gửi lời mời và chốt vẫn là
                bước của quản lý — và người được mời phải tự đồng ý.
              </li>
            </ul>
          </section>

          {/* Bước 2 — bảng so sánh TRẢI NGANG. */}
          <h2 className="nq-rescue__stephead">
            <span className="nq-rescue__stepnum">2</span>
            So sánh người bù ({caze.candidates.length} đủ điều kiện
            {caze.blocked?.length ? `, ${caze.blocked.length} bị loại` : ""})
          </h2>
          {caze.candidates.length === 0 && !caze.blocked?.length ? (
            <ExpEmpty
              icon="warn"
              title="Không có ai đủ điều kiện nhận ca này"
              hint="Cần quản lý đứng ca, giảm suất phục vụ, hoặc mở War Room — hệ thống không tự mời người vi phạm ràng buộc."
            />
          ) : (
            <CandidateTable
              candidates={caze.candidates}
              blocked={caze.blocked ?? []}
              onSelect={(id) => proposeAndInvite(id)}
              disabled={busy || (caze.invited ?? []).length > 0}
              selected={selected}
            />
          )}

          {/* Bước 3 — phản hồi + chốt. */}
          {(caze.invited ?? []).length > 0 ? (
            <section className="nq-rescue__respond" aria-label="Bước 3: phản hồi và chốt">
              <h2 className="nq-rescue__stephead">
                <span className="nq-rescue__stepnum">3</span>
                Phản hồi &amp; chốt
              </h2>
              <p className="nq-rescue__note">
                Ghi lại phản hồi của người được mời. Từ chối thì mời người kế tiếp;
                nhận rồi mới chốt được vào ca.
              </p>
              <div className="nq-rescue__respondrow">
                <span className="nq-rescue__invitedcount">
                  <Icon name="send" size={14} />
                  Đang chờ phản hồi: {caze.invited.length} người
                </span>
                <div className="nq-rescue__respondactions">
                  <button
                    type="button"
                    className="nq-btn-compact nq-modebtn"
                    data-testid="rescue-accept"
                    disabled={busy}
                    onClick={() => respond(caze.invited[0], true)}
                  >
                    <Icon name="check" size={14} />
                    Người được mời nhận ca
                  </button>
                  <button
                    type="button"
                    className="nq-btn-compact nq-modebtn"
                    data-testid="rescue-decline"
                    disabled={busy}
                    onClick={() => respond(caze.invited[0], false)}
                  >
                    <Icon name="close" size={14} />
                    Từ chối
                  </button>
                  <button
                    type="button"
                    className="nq-btn nq-btn-primary"
                    data-testid="rescue-confirm"
                    disabled={busy || caze.status !== "responded"}
                    onClick={confirm}
                  >
                    <Icon name="clipboard" size={15} />
                    {busy ? "Đang chốt…" : "Chốt người bù vào ca"}
                  </button>
                </div>
              </div>
              {caze.status !== "responded" ? (
                <p className="nq-rescue__note">
                  Cần phản hồi nhận ca trước khi chốt — hệ thống không tự gán người
                  vào ca mà chưa ai đồng ý.
                </p>
              ) : null}
            </section>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}