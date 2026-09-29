"use client";

/**
 * War Room — chọn kịch bản, chạy mô phỏng, đề xuất, xác nhận.
 *
 * Bản trước dừng ở bước đề xuất: API có `confirm` nhưng không UI nào gọi, nên
 * đề xuất tạo ra rồi bỏ đó — không ai chốt, không biết phương án nào đã được
 * quyết. Bản này theo dõi đề xuất trong phiên và cho chốt ngay tại chỗ, kèm
 * nhắc rõ mô phỏng không tự đổi lịch thật.
 *
 * Cũng bỏ việc in `option_id` thô ra tiêu đề drawer: người vận hành đọc tên
 * phương án, không đọc mã.
 */

import { useCallback, useState } from "react";
import { Icon } from "../../icons";
import { viError } from "../../../lib/present";
import { eligibilityReasonLabel, proposalStatusLabel, warOptionTitle } from "../exp-present";
import NowBrief from "./NowBrief";
import ScenarioComparison from "./ScenarioComparison";
import ScenarioPicker from "./ScenarioPicker";
import {
  snapshotHashForScenario,
  type WarRoomOption,
  type WarRoomScenarioInput,
} from "./war-room-model";
import {
  warRoomConfirm,
  warRoomPropose,
  warRoomSimulate,
  warRoomSimulateLive,
  type WarRoomLiveResponse,
} from "../experience-api";

type SimResult = {
  simulation_id: string;
  baseline_snapshot_hash: string;
  baseline: Record<string, string | number | boolean>;
  options: WarRoomOption[];
};

/** Đề xuất đã tạo trong phiên — cần theo dõi để chốt được. */
type Proposal = {
  optionId: string;
  proposalId: string;
  status: string;
  confirmed: boolean;
};

const COPY = {
  simulate: { doing: "chạy mô phỏng" },
  propose: {
    doing: "tạo đề xuất từ phương án này",
    conflict: "Phương án này vi phạm ràng buộc cứng hoặc dữ liệu nền đã cũ. Chạy lại mô phỏng.",
  },
  confirm: {
    doing: "chốt đề xuất này",
    conflict: "Đề xuất đã đổi ở nơi khác. Chạy lại mô phỏng rồi chốt lại.",
  },
} as const;

export default function WarRoom() {
  const [scenarios, setScenarios] = useState<WarRoomScenarioInput[]>([]);
  const [result, setResult] = useState<SimResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedOptionId, setSelectedOptionId] = useState<string | null>(null);
  const [evidenceOption, setEvidenceOption] = useState<WarRoomOption | null>(null);
  const [proposing, setProposing] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [live, setLive] = useState<WarRoomLiveResponse | null>(null);
  const [liveBusy, setLiveBusy] = useState(false);
  const [liveError, setLiveError] = useState<string | null>(null);

  /** Mô phỏng trên DỮ LIỆU THẬT của tuần đang chạy — tính các phương án thật. */
  const simulateLive = useCallback(async () => {
    setLiveBusy(true);
    setLiveError(null);
    try {
      const resp = await warRoomSimulateLive({});
      setLive(resp);
      if (!resp.co_du_lieu) {
        setLiveError("Tuần này chưa có lịch xếp nên chưa mô phỏng được trên dữ liệu thật. Hãy xếp lịch ở /lich-tuan trước.");
      }
    } catch (e) {
      setLiveError(viError(e, COPY.simulate));
    } finally {
      setLiveBusy(false);
    }
  }, []);

  const toggleScenario = useCallback((scenario: WarRoomScenarioInput) => {
    setScenarios((prev) => {
      const exists = prev.some((s) => s.scenario_id === scenario.scenario_id);
      if (exists) return prev.filter((s) => s.scenario_id !== scenario.scenario_id);
      return [...prev, scenario];
    });
    setResult(null);
    setProposal(null);
  }, []);

  const simulate = useCallback(async () => {
    if (scenarios.length < 2) {
      setError("Chọn ít nhất 2 kịch bản để so sánh.");
      return;
    }
    setBusy(true);
    setError(null);
    setResult(null);
    setProposal(null);
    setNotice(null);
    try {
      const snap = snapshotHashForScenario(scenarios[0]);
      const resp = await warRoomSimulate({
        request_id: `wr_${Date.now()}`,
        baseline_snapshot: snap,
        scenarios,
        requested_by: "quan_ly_demo",
      });
      setResult({
        simulation_id: resp.simulation_id,
        baseline_snapshot_hash: resp.baseline_snapshot_hash,
        baseline: resp.baseline ?? {},
        options: resp.options ?? [],
      });
      setSelectedOptionId(null);
    } catch (e) {
      setError(viError(e, COPY.simulate));
    } finally {
      setBusy(false);
    }
  }, [scenarios]);

  const propose = useCallback(
    async (optionId: string) => {
      if (!result || !result.options?.length) return;
      const opt = result.options.find((o) => o.option_id === optionId);
      if (!opt) return;
      setProposing(true);
      setNotice(null);
      try {
        const res = await warRoomPropose(
          result.simulation_id,
          optionId,
          result.baseline_snapshot_hash,
        );
        setProposal({
          optionId,
          proposalId: res.proposal.proposal_id,
          status: res.proposal.status,
          confirmed: false,
        });
        setNotice(
          `Đã tạo đề xuất (${proposalStatusLabel(res.proposal.status)}). Xác nhận để chốt — mô phỏng không tự đổi lịch thật.`,
        );
      } catch (e) {
        setError(viError(e, COPY.propose));
      } finally {
        setProposing(false);
      }
    },
    [result],
  );

  /** Chốt đề xuất — bước trước đây không có UI. */
  const confirm = useCallback(async () => {
    if (!result || !proposal) return;
    setConfirming(true);
    setNotice(null);
    try {
      const res = await warRoomConfirm(result.simulation_id, proposal.optionId);
      setProposal((p) => (p ? { ...p, confirmed: res.confirmed } : p));
      setNotice(
        res.treo_id
          ? "Đã chốt đề xuất và tạo việc trong Sổ việc treo — mở /treo để ghim vào vận hành."
          : "Đã chốt đề xuất. Mô phỏng chỉ để so sánh — đổi lịch thật vẫn là bước riêng, có người duyệt.",
      );
    } catch (e) {
      setError(viError(e, COPY.confirm));
    } finally {
      setConfirming(false);
    }
  }, [result, proposal]);

  const proposalOption = proposal
    ? (result?.options.find((o) => o.option_id === proposal.optionId) ?? null)
    : null;

  return (
    <div className="nq-war">
      <header className="nq-war__header">
        <h1>War Room — Phòng điều hành</h1>
        <p>
          So sánh các phương án “nếu… thì…” dựa trên mô phỏng tất định. Không
          thay đổi lịch thật.
        </p>
      </header>

      {/* CHẾ ĐỘ DỮ LIỆU THẬT — tính phương án trên lịch tuần đang chạy. */}
      <section className="nq-war__live" aria-label="Mô phỏng trên dữ liệu thật">
        <div className="nq-war__livehead">
          <div>
            <h2>Mô phỏng trên lịch tuần đang chạy</h2>
            <p className="nq-muted">
              Dựng baseline từ phân công thật, rồi tính các phương án (giữ nguyên ·
              thêm người · điều chuyển). Số ra từ chính lịch của quán.
            </p>
          </div>
          <button
            type="button"
            className="nq-btn nq-btn-primary"
            onClick={() => void simulateLive()}
            disabled={liveBusy}
            data-testid="war-live-run"
          >
            {liveBusy ? "Đang tính…" : "Chạy trên dữ liệu thật"}
          </button>
        </div>
        {liveError ? <div className="nq-alert nq-alert--info" role="status">{liveError}</div> : null}
        {live && live.co_du_lieu ? (
          <div className="nq-war__liveresult" data-testid="war-live-result">
            <p className="nq-war__livesum">
              Tuần {(live.baseline?.tuan_iso as string) ?? "—"} ·{" "}
              {(live.baseline?.chi_so as Record<string, number>)?.so_ca ?? 0} ca ·{" "}
              {(live.baseline?.chi_so as Record<string, number>)?.so_ca_thieu ?? 0} ca thiếu
            </p>
            <ul className="nq-war__liveopts">
              {live.options.map((o) => (
                <li key={o.option_id} className="nq-war__liveopt" data-live-opt={o.option_id}>
                  <strong>{o.label ?? o.scenario_id}</strong>
                  {o.reason ? <p className="nq-war__livereason">{o.reason}</p> : null}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </section>

      {/* TÌNH HÌNH HIỆN TẠI — trả lời câu hỏi đầu tiên người trực ca cần:
          "bây giờ quán đang thế nào, có gì đáng lo". Trước đây trang chỉ có 5
          thẻ kịch bản cứng, nên người dùng không biết mình đang quyết định
          trên nền tình hình nào. Panel này đọc TẮT CẢ dữ liệu thật của quán
          (bản chiếu + trợ lý) qua cùng một endpoint `brief` đã có. */}
      <section className="nq-war__now" aria-label="Tình hình hiện tại của quán">
        <div className="nq-exp-section__head">
          <Icon name="refresh" size={16} />
          <h2 className="nq-exp-section__title">Tình hình hiện tại</h2>
          <span className="nq-exp-section__spacer" />
          <span className="nq-rolechip">
            <Icon name="info" size={13} />
            Đọc từ hệ thống
          </span>
        </div>
        <NowBrief />
      </section>

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

      <ScenarioPicker selected={scenarios} onToggle={toggleScenario} disabled={busy} />

      <div className="nq-war__actions">
        <button
          type="button"
          className="nq-btn nq-btn-primary"
          disabled={busy || scenarios.length < 2}
          onClick={simulate}
        >
          <Icon name="play" size={16} />
          {busy ? "Đang mô phỏng…" : "Chạy mô phỏng"}
        </button>
      </div>

      {result ? (
        <ScenarioComparison
          baseline={result.baseline}
          options={result.options ?? []}
          selectedOptionId={selectedOptionId}
          onSelect={setSelectedOptionId}
          onPropose={propose}
          onShowEvidence={setEvidenceOption}
          proposing={proposing}
        />
      ) : null}

      {/* Đề xuất trong phiên — nơi bấm chốt. */}
      {proposal ? (
        <section className="nq-war-proposal" aria-label="Đề xuất trong phiên">
          <div className="nq-war-proposal__head">
            <Icon name="clipboard" size={16} />
            <h3 className="nq-exp-section__title">
              Đề xuất:{" "}
              {warOptionTitle(proposal.optionId, "Phương án đã chọn")}
            </h3>
            <span className="nq-exp-section__spacer" />
            <span className={`nq-chip${proposal.confirmed ? " nq-chip--ok" : " nq-chip--warn"}`}>
              {proposal.confirmed ? "Đã chốt" : proposalStatusLabel(proposal.status)}
            </span>
          </div>
          {proposalOption ? (
            <p className="nq-war-proposal__sum">
              {proposalOption.risk
                ? `Rủi ro cần biết: ${proposalOption.risk}`
                : "Không ghi nhận rủi ro đặc biệt trong mô phỏng."}
            </p>
          ) : null}
          {!proposal.confirmed ? (
            <button
              type="button"
              className="nq-btn nq-btn-primary"
              data-testid="confirm-proposal-btn"
              disabled={confirming}
              onClick={confirm}
            >
              <Icon name="check" size={16} />
              {confirming ? "Đang chốt…" : "Chốt đề xuất này"}
            </button>
          ) : null}
        </section>
      ) : null}

      {/* KHÔNG còn `CrisisRoom` ở đây: nó render đúng 5 preset mà `ScenarioPicker`
          phía trên đã render. Hai chỗ chọn cùng một danh sách là lỗi gốc khiến
          trang trông như "chỉ là bấm vô 2 mục". Một công cụ chọn duy nhất. */}

      {evidenceOption ? (
        <div
          className="nq-drawer"
          role="dialog"
          aria-modal="true"
          aria-label="Vì sao phương án này"
        >
          <div className="nq-drawer__inner">
            <button
              type="button"
              className="nq-drawer__close"
              aria-label="Đóng"
              onClick={() => setEvidenceOption(null)}
            >
              <Icon name="close" size={18} />
            </button>
            <h2>Vì sao: {warOptionTitle(evidenceOption.option_id, "Phương án đã chọn")}</h2>
            <p className="nq-drawer__risk">Rủi ro: {evidenceOption.risk || "Không ghi nhận"}</p>
            <h3>Nguồn dữ liệu</h3>
            <ul className="nq-drawer__refs">
              {(evidenceOption.evidence_refs ?? []).map((ref: string, i: number) => (
                <li key={i}>{ref}</li>
              ))}
            </ul>
            {evidenceOption.constraint_violations?.length ? (
              <div className="nq-alert nq-alert--error">
                Ràng buộc cứng chưa đạt:{" "}
                {evidenceOption.constraint_violations.map(eligibilityReasonLabel).join("; ")}
              </div>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}
