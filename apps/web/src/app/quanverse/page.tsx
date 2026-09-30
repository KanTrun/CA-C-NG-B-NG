"use client";

/**
 * QUÁNVERSE — Cockpit Trung tâm điều hành AI.
 *
 * Vỏ mỏng: state (role · nguồn · zone · hour · ask · modes) → một repository
 * → bố cục cockpit 3 cột. Mọi biến đổi số liệu nằm trong repository/.
 *
 * Ranh giới: bề mặt VẬN HÀNH. Không guest/Flavor/AR/3D. Modes = human confirm.
 */

import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useState } from "react";
import { getRole, getToken, isManager } from "../../lib/session";
import { AuthGate, Skeleton, TechnicalDrawer } from "../../ui/kit";
import { Reveal } from "../../ui/motion/Reveal";
import type {
  QuanverseAskResult,
  QuanverseKpi,
  QuanverseModesState,
  QuanverseRole,
  QuanverseViewModel,
} from "../../ui/experience/quanverse/quanverse-contract";
import {
  locActionsTheoZone,
  locEventsTheoZone,
  locTimelineTheoZone,
  zoneNongNhat,
} from "../../ui/experience/quanverse/quanverse-contract";
import {
  QUANVERSE_SCENARIOS,
  getQuanverseRepository,
  mockChoPhep,
  type QuanverseScenario,
} from "../../ui/experience/quanverse/repository";
import AiCopilot from "../../ui/experience/quanverse/ops/AiCopilot";
import CapabilityBoard from "../../ui/experience/quanverse/ops/CapabilityBoard";
import CapacityForecast from "../../ui/experience/quanverse/ops/CapacityForecast";
import DataSourceBadge, {
  ProvenancePanel,
} from "../../ui/experience/quanverse/ops/DataSourceBadge";
import EventsList from "../../ui/experience/quanverse/ops/EventsList";
import ExecutiveSnapshot from "../../ui/experience/quanverse/ops/ExecutiveSnapshot";
import HeaderBlock from "../../ui/experience/quanverse/ops/HeaderBlock";
import ModeRail from "../../ui/experience/quanverse/ops/ModeRail";
import NeedsAttention from "../../ui/experience/quanverse/ops/NeedsAttention";
import Timeline15 from "../../ui/experience/quanverse/ops/Timeline15";
import ZoneFocus from "../../ui/experience/quanverse/ops/ZoneFocus";

const OperationalMap2dClient = dynamic(
  () => import("../../ui/experience/quanverse/ops/OperationalMap2d"),
  { ssr: false, loading: () => <Skeleton rows={4} /> },
);

const ALL_ROLES: QuanverseRole[] = ["nhan_vien", "quan_ly", "chu_quan"];
const ROLE_NAME: Record<QuanverseRole, string> = {
  khach: "Khách",
  nhan_vien: "Nhân viên",
  quan_ly: "Quản lý",
  chu_quan: "Chủ quán",
};

const MAC_DINH_SCENARIO: QuanverseScenario = "cao_diem";

export default function QuanversePage() {
  const [token, setToken] = useState("");
  const [role, setRole] = useState<QuanverseRole>("quan_ly");
  const [ready, setReady] = useState(false);
  const [manager, setManager] = useState(false);

  const [vm, setVm] = useState<QuanverseViewModel | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedZone, setSelectedZone] = useState<string | null>(null);
  const [selectedHour, setSelectedHour] = useState<number | null>(null);
  const [focusPanel, setFocusPanel] = useState<"actions" | "timeline" | null>(null);

  const [askResult, setAskResult] = useState<QuanverseAskResult | null>(null);
  const [askBusy, setAskBusy] = useState(false);
  const [askPrefill, setAskPrefill] = useState("");

  const [modesState, setModesState] = useState<QuanverseModesState | null>(null);
  const [busyMode, setBusyMode] = useState<string | null>(null);

  const [scenario, setScenario] = useState<QuanverseScenario>(MAC_DINH_SCENARIO);
  const [dungMock, setDungMock] = useState(false);

  const choPhepMock = mockChoPhep();

  const repo = useMemo(
    () =>
      getQuanverseRepository({
        source: dungMock ? "mock" : "real",
        scenario,
      }),
    [dungMock, scenario],
  );

  useEffect(() => {
    setToken(getToken());
    const r = getRole() as QuanverseRole;
    if (ALL_ROLES.includes(r)) setRole(r);
    setManager(isManager());
    setReady(true);
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [data, modes] = await Promise.all([
        repo.getViewModel({ role, scenario }),
        repo.listModes(),
      ]);
      setVm(data);
      setModesState({
        ...modes,
        canActivate: modes.canActivate && (isManager() || role === "quan_ly" || role === "chu_quan"),
        role,
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Không đọc được dữ liệu Quánverse.");
      setVm(null);
    } finally {
      setLoading(false);
    }
  }, [repo, scenario, role]);

  useEffect(() => {
    if (token && ready) void load();
  }, [token, ready, load]);

  useEffect(() => {
    setSelectedZone((cur) =>
      cur && vm?.zones.some((z) => z.zoneId === cur) ? cur : null,
    );
  }, [vm]);

  const zoneLabel =
    selectedZone && vm
      ? (vm.zones.find((z) => z.zoneId === selectedZone)?.label ?? null)
      : null;

  const zoneFocus =
    selectedZone && vm
      ? (vm.zones.find((z) => z.zoneId === selectedZone) ?? null)
      : null;

  const actionsLoc = useMemo(
    () => (vm ? locActionsTheoZone(vm.actions, selectedZone) : []),
    [vm, selectedZone],
  );
  const eventsLoc = useMemo(
    () => (vm ? locEventsTheoZone(vm.events, selectedZone) : []),
    [vm, selectedZone],
  );
  const timelineLoc = useMemo(
    () => (vm ? locTimelineTheoZone(vm.timeline, selectedZone) : []),
    [vm, selectedZone],
  );

  const askSuggestions = useMemo(() => {
    const out: string[] = [];
    if (zoneLabel) out.push(`Vì sao ${zoneLabel} đang đáng chú ý?`);
    if (selectedHour !== null) {
      out.push(`Vì sao đỉnh tải lúc ${String(selectedHour).padStart(2, "0")}:00?`);
    }
    out.push("Khu vực nào đang quá tải?");
    out.push("15 phút tới cần chú ý gì?");
    return out.slice(0, 3);
  }, [zoneLabel, selectedHour]);

  const handleAsk = useCallback(
    async (question: string) => {
      const q = question.trim();
      if (!q) return;
      setAskBusy(true);
      setAskPrefill(q);
      try {
        const result = await repo.askQuestion({ question: q, page: "living_map" });
        setAskResult(result);
      } finally {
        setAskBusy(false);
      }
    },
    [repo],
  );

  const runMode = useCallback(
    async (mode: string, action: "propose" | "confirm" | "deactivate") => {
      setBusyMode(mode);
      try {
        const next =
          action === "propose"
            ? await repo.proposeMode(mode)
            : action === "confirm"
              ? await repo.confirmMode(mode)
              : await repo.deactivateMode(mode);
        setModesState({ ...next, role, canActivate: next.canActivate || manager });
        // Reload events/snapshot sau khi mode đổi.
        await load();
      } catch {
        // Giữ state cũ; provenance sẽ báo nếu đọc lại fail.
      } finally {
        setBusyMode(null);
      }
    },
    [repo, role, manager, load],
  );

  const onKpiClick = useCallback(
    (key: QuanverseKpi["key"]) => {
      if (!vm) return;
      if (key === "alerts" || key === "queue") {
        const hot = zoneNongNhat(vm.zones);
        if (hot) setSelectedZone(hot);
        setFocusPanel("actions");
      } else if (key === "upcoming") {
        setFocusPanel("timeline");
      }
    },
    [vm],
  );

  if (!ready) return <Skeleton rows={6} />;
  if (!token) return <AuthGate />;

  const isMock = vm?.dataSource === "mock";
  const qualityLines = (vm?.dataQuality ?? []).map((q) => `[${q.level}] ${q.message}`);
  const provenanceLines = (vm?.provenance ?? []).map(
    (p) =>
      `${p.ok ? "OK" : "LỖI"} · ${p.label} · ${p.endpoint}${
        p.status ? ` · HTTP ${p.status}` : ""
      }`,
  );

  return (
    <div className="nq-qv nq-qv--cockpit" data-testid="quanverse-root">
      {error ? (
        <div className="nq-alert nq-alert--error" role="alert">
          {error}
          <button type="button" className="nq-linkbtn" onClick={() => void load()}>
            Tải lại
          </button>
        </div>
      ) : null}

      <div className="nq-qv__toolbar">
        <DataSourceBadge
          dataSource={vm?.dataSource ?? "real"}
          scenario={vm?.scenario ?? (dungMock ? scenario : null)}
          updatedAt={vm?.header.updatedAt ?? null}
          provenance={vm?.provenance ?? []}
          scenarioOptions={QUANVERSE_SCENARIOS}
          canChooseSource={choPhepMock}
          onChangeScenario={(s) => {
            setDungMock(true);
            setScenario(s);
            setAskResult(null);
          }}
        />

        <div className="nq-qv__roles" role="group" aria-label="Chọn vai trò xem">
          {ALL_ROLES.map((r) => (
            <button
              key={r}
              type="button"
              className={`nq-qv__rolebtn${role === r ? " is-on" : ""}`}
              data-testid={`role-${r}`}
              aria-pressed={role === r}
              onClick={() => setRole(r)}
            >
              {ROLE_NAME[r]}
            </button>
          ))}
          {!manager ? (
            <span
              className="nq-qv__roledisabled"
              title="Cần vai trò Quản lý hoặc Chủ quán"
            >
              Bản chiếu đầy đủ yêu cầu quyền quản lý
            </span>
          ) : null}
        </div>

        {choPhepMock ? (
          <button
            type="button"
            className={`nq-qv__sourcebtn${dungMock ? " is-on" : ""}`}
            aria-pressed={dungMock}
            data-testid="toggle-source"
            onClick={() => {
              setDungMock((v) => !v);
              setAskResult(null);
            }}
          >
            {dungMock ? "Đang xem: Mô phỏng" : "Đang xem: Dữ liệu thật"}
          </button>
        ) : null}
      </div>

      {!vm && loading ? (
        <Skeleton rows={6} />
      ) : !vm ? (
        <p className="nq-qv-trong" data-testid="quanverse-empty">
          <span className="nq-qv-trong__text">Chưa có dữ liệu</span>
          <span className="nq-qv-trong__hint">
            Chưa đọc được trạng thái quán từ hệ thống.
          </span>
        </p>
      ) : (
        <Reveal className="nq-qv__cockpit">
          {/* Pulse: header + KPI gọn */}
          <div className="nq-qv__pulse">
            <HeaderBlock
              header={vm.header}
              dataSource={vm.dataSource}
              scenarioLabel={vm.scenarioLabel}
            />
            <ExecutiveSnapshot kpis={vm.kpis} onKpiClick={onKpiClick} />
          </div>

          {/* Cockpit 3 cột — stretch đầy chiều cao, không để lỗ trống giữa cột */}
          <div className="nq-qv__deck">
            <div className="nq-qv__col nq-qv__col--map">
              <OperationalMap2dClient
                zones={vm.zones}
                selectedId={selectedZone}
                onSelect={setSelectedZone}
              />
              <ZoneFocus
                zone={zoneFocus}
                zones={vm.zones}
                onClear={() => setSelectedZone(null)}
                onAsk={(q) => {
                  setAskPrefill(q);
                  void handleAsk(q);
                }}
                onFocusActions={() => setFocusPanel("actions")}
                onPickZone={setSelectedZone}
              />
            </div>

            <div
              className={`nq-qv__col nq-qv__col--mid${
                focusPanel === "actions" ? " is-focus-actions" : ""
              }${focusPanel === "timeline" ? " is-focus-timeline" : ""}`}
            >
              <NeedsAttention
                actions={actionsLoc}
                filterZoneLabel={zoneLabel}
                onClearFilter={() => setSelectedZone(null)}
                onFocusZone={setSelectedZone}
                onAsk={(q) => {
                  setAskPrefill(q);
                  void handleAsk(q);
                }}
              />
              <Timeline15 items={timelineLoc} isMock={isMock} />
              <CapacityForecast
                capacity={vm.capacity}
                isMock={isMock}
                selectedHour={selectedHour}
                onSelectHour={(h) => {
                  setSelectedHour(h);
                  if (h !== null) {
                    setAskPrefill(
                      `Vì sao đỉnh tải lúc ${String(h).padStart(2, "0")}:00?`,
                    );
                  }
                }}
              />
            </div>

            <div className="nq-qv__col nq-qv__col--ai">
              <AiCopilot
                copilot={vm.copilot}
                provenance={vm.provenance}
                askResult={askResult}
                askBusy={askBusy}
                askPrefill={askPrefill}
                suggestions={askSuggestions}
                onAsk={(q) => void handleAsk(q)}
                onClearAsk={() => {
                  setAskResult(null);
                  setAskPrefill("");
                }}
              />
              <ModeRail
                modesState={modesState}
                busyMode={busyMode}
                onPropose={(m) => void runMode(m, "propose")}
                onConfirm={(m) => void runMode(m, "confirm")}
                onDeactivate={(m) => void runMode(m, "deactivate")}
              />
              <EventsList
                events={eventsLoc}
                filterZoneLabel={zoneLabel}
                onClearFilter={() => setSelectedZone(null)}
                onFocusZone={setSelectedZone}
              />
            </div>
          </div>

          <CapabilityBoard
            vm={vm}
            dataSource={vm.dataSource}
            canMock={choPhepMock}
            onEnableMock={() => {
              setDungMock(true);
              setScenario("cao_diem");
              setAskResult(null);
            }}
          />

          <TechnicalDrawer
            summary="Chi tiết kỹ thuật · nguồn & chất lượng dữ liệu"
            lines={[...qualityLines, ...provenanceLines]}
          />
          <ProvenancePanel provenance={vm.provenance} />
        </Reveal>
      )}
    </div>
  );
}
