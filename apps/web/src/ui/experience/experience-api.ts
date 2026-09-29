/** Typed client cho Grand AI Experience API (Phase 02 War Room). */

import { apiGet, apiSend } from "../../lib/api";
import type {
  WarRoomComparison,
  WarRoomScenario,
  WarRoomOption,
} from "../../lib/contracts";
import type { WarRoomScenarioInput } from "./war-room/war-room-model";

/**
 * Trợ lý Quánverse — tóm tắt tất định + hỏi đáp có căn cứ.
 *
 * `QuanverseBrief` là dữ liệu SỐ do máy chủ tính (không LLM), nên panel tóm tắt
 * luôn hiển thị được kể cả khi chưa có API key. `QuanverseAskResponse` mang
 * `grounded`/`citations` để UI nói rõ khi câu trả lời KHÔNG có bản ghi nào hậu
 * thuẫn — theo đúng hợp đồng "vắng trích dẫn = không bịa".
 */
export type QuanversePageId =
  | "living_map"
  | "war_room"
  | "shift_rescue"
  | "rules"
  | "spatial_memory";

export interface QuanverseMetric {
  key: string;
  label: string;
  value: number | null;
  unit: string;
  tone: "default" | "ok" | "warn" | "danger";
}

export interface QuanverseDataQualityNotice {
  code: string;
  level: "info" | "warning" | "error";
  message: string;
}

export interface QuanverseBrief {
  page: QuanversePageId;
  headline: string;
  facts: string[];
  metrics: QuanverseMetric[];
  risks: string[];
  next_actions: string[];
  grounded_refs: string[];
  data_quality: QuanverseDataQualityNotice[];
}

export interface QuanverseAskResponse {
  page: QuanversePageId;
  question: string;
  answer: string;
  brief: QuanverseBrief;
  citations: string[];
  unsupported_claims: string[];
  grounded: boolean;
  provider: string;
}

export function quanverseBrief(page: QuanversePageId): Promise<QuanverseBrief> {
  return apiGet<QuanverseBrief>(`/api/v1/experience/quanverse/brief/${page}`);
}

export function quanverseAsk(
  page: QuanversePageId,
  question: string,
): Promise<QuanverseAskResponse> {
  return apiSend<QuanverseAskResponse>("/api/v1/experience/quanverse/ask", {
    page,
    question,
  });
}

export interface WarRoomSimulateRequest {
  request_id: string;
  baseline_snapshot: string;
  scenarios: WarRoomScenarioInput[];
  requested_by: string;
}

export interface WarRoomSimulateResponse extends WarRoomComparison {
  replayable: boolean;
  simulation_id: string;
  baseline_snapshot_hash: string;
  baseline: Record<string, string | number | boolean>;
  options: WarRoomOption[];
}

export interface WarRoomProposeResponse {
  proposal: {
    proposal_id: string;
    status: string;
    snapshot_hash: string;
    evidence_refs: string[];
  };
  status: string;
  replayable: boolean;
}

export function warRoomSimulate(
  req: WarRoomSimulateRequest,
): Promise<WarRoomSimulateResponse> {
  return apiSend<WarRoomSimulateResponse>(
    "/api/v1/experience/war-room/simulate",
    req,
  );
}

export function warRoomGetScenarios(
  simulationId: string,
): Promise<WarRoomComparison> {
  return apiGet<WarRoomComparison>(
    `/api/v1/experience/war-room/scenarios/${simulationId}`,
  );
}

/** Mô phỏng trên DỮ LIỆU THẬT của tuần đang chạy (không preset). */
export interface WarRoomLiveOption extends WarRoomOption {
  label?: string;
  reason?: string;
  reason_provider?: string;
  load?: Record<string, number>;
  chi_tiet?: Record<string, string | number>;
}

export interface WarRoomLiveResponse {
  co_du_lieu: boolean;
  baseline: Record<string, unknown>;
  baseline_snapshot_hash?: string;
  options: WarRoomLiveOption[];
  nguon?: string;
}
export function warRoomSimulateLive(req: {
  tuan_iso?: string | null;
  ca_id?: string;
  khung?: string;
}): Promise<WarRoomLiveResponse> {
  return apiSend<WarRoomLiveResponse>(
    "/api/v1/experience/war-room/simulate-live",
    { tuan_iso: req.tuan_iso ?? null, ca_id: req.ca_id ?? "", khung: req.khung ?? "" },
  );
}

export function warRoomPropose(
  simulationId: string,
  optionId: string,
  expectedSnapshotHash: string,
): Promise<WarRoomProposeResponse> {
  return apiSend<WarRoomProposeResponse>(
    `/api/v1/experience/war-room/${simulationId}/propose`,
    { option_id: optionId, expected_snapshot_hash: expectedSnapshotHash },
  );
}

export function warRoomConfirm(
  simulationId: string,
  optionId?: string,
): Promise<{ confirmed: boolean; mutation: string; treo_id?: string; note?: string }> {
  return apiSend(`/api/v1/experience/war-room/${simulationId}/confirm`, {
    option_id: optionId ?? null,
  });
}

export function formatVnd(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return "—";
  }
  return new Intl.NumberFormat("vi-VN", {
    style: "currency",
    currency: "VND",
    maximumFractionDigits: 0,
  }).format(value);
}

export function optionLabel(option: { option_id: string }): string {
  return option.option_id;
}