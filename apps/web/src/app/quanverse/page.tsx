"use client";

/**
 * QUÁNVERSE 2.0 — Trung tâm điều hành AI (Chủ quán + Giám khảo).
 *
 * 4 khối: [1 VERDICT JEV] [2 TOP 3] [3 timeline+capacity] [4 hỏi AI + strip zone].
 * 3 trạng thái dữ liệu: du / thieu_1_phan / trong (S3 không gọi JEV, không đoán).
 * Xóa mock/scenario/role-buttons. Role auto từ session. Dữ liệu chỉ DB thật.
 */

import dynamic from "next/dynamic";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { getRole, getToken, isManager } from "../../lib/session";
import { AuthGate, Skeleton, TechnicalDrawer } from "../../ui/kit";
import type {
  QuanverseAskResult,
  QuanverseEvidence,
  QuanverseJev,
  QuanverseModesState,
  QuanverseRole,
  QuanverseViewModel,
} from "../../ui/experience/quanverse/quanverse-contract";
import { RealQuanverseRepository } from "../../ui/experience/quanverse/repository/real";
import AiCopilot from "../../ui/experience/quanverse/ops/AiCopilot";
import CapacityForecast from "../../ui/experience/quanverse/ops/CapacityForecast";
import HeaderBlock from "../../ui/experience/quanverse/ops/HeaderBlock";
import InsufficientCard from "../../ui/experience/quanverse/ops/InsufficientCard";
import Timeline15 from "../../ui/experience/quanverse/ops/Timeline15";
import Top3List from "../../ui/experience/quanverse/ops/Top3List";
import VerdictBar from "../../ui/experience/quanverse/ops/VerdictBar";
import ZoneFocus from "../../ui/experience/quanverse/ops/ZoneFocus";

const OperationalMap2dClient = dynamic(
  () => import("../../ui/experience/quanverse/ops/OperationalMap2d"),
  { ssr: false, loading: () => <Skeleton rows={4} /> },
);

export default function QuanversePage() {
  const [token, setToken] = useState("");
  const [role, setRole] = useState<QuanverseRole>("quan_ly");
  const [ready, setReady] = useState(false);
  const [manager, setManager] = useState(false);
  const [debug, setDebug] = useState(false);

  const [vm, setVm] = useState<QuanverseViewModel | null>(null);
  const [evidence, setEvidence] = useState<QuanverseEvidence | null>(null);
  const [jev, setJev] = useState<QuanverseJev | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedZone, setSelectedZone] = useState<string | null>(null);
  const [selectedHour, setSelectedHour] = useState<number | null>(null);

  const [askResult, setAskResult] = useState<QuanverseAskResult | null>(null);
  const [askBusy, setAskBusy] = useState(false);
  const [askPrefill, setAskPrefill] = useState("");

  const [modesState, setModesState] = useState<QuanverseModesState | null>(null);
  const [busyMode, setBusyMode] = useState<string | null>(null);
  const [demoBusy, setDemoBusy] = useState(false);

  const repo = useMemo(() => new RealQuanverseRepository(), []);

  useEffect(() => {
    setToken(getToken());
    const r = getRole() as QuanverseRole;
    if (r === "nhan_vien" || r === "quan_ly" || r === "chu_quan") setRole(r);
    try {
      setDebug(new URLSearchParams(window.location.search).get("debug") === "1");
    } catch {
      setDebug(false);
    }
    setManager(isManager());
    setReady(true);
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [judged, viewModel, modes] = await Promise.all([
        repo.judgeJev(),
        repo.getViewModel({ role }).catch(() => null),
        repo.listModes().catch(() => null),
      ]);
      if (judged) {
        setEvidence(judged.evidence);
        setJev(judged.jev);
      } else {
        const ev = await repo.getEvidence().catch(() => null);
        setEvidence(ev);
        setJev(null);
      }
      setVm(viewModel);
      if (modes) setModesState({ ...modes, role });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Không đọc được dữ liệu Quánverse.");
    } finally {
      setLoading(false);
    }
  }, [repo, role]);

  useEffect(() => {
    if (token && ready) void load();
  }, [token, ready, load]);

  useEffect(() => {
    setSelectedZone((cur) =>
      cur && vm?.zones.some((z) => z.zoneId === cur) ? cur : null,
    );
  }, [vm]);

  const handleAsk = useCallback(
    async (question: string) => {
      const q = question.trim();
      if (!q) return;
      setAskBusy(true);
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
        setModesState({ ...next, role });
        await load();
      } catch {
        // Giữ state cũ.
      } finally {
        setBusyMode(null);
      }
    },
    [repo, role, load],
  );

  const handleDemoSetup = useCallback(async () => {
    setDemoBusy(true);
    try {
      await repo.demoSetup();
      setAskResult(null);
      await load();
    } finally {
      setDemoBusy(false);
    }
  }, [repo, load]);

  const zoneFocus = selectedZone && vm ? (vm.zones.find((z) => z.zoneId === selectedZone) ?? null) : null;
  const activeMode = modesState?.modes.find((m) => m.active) ?? null;
  const draftMode = modesState?.modes.find((m) => m.status === "draft") ?? null;
  const suggestMode = draftMode ?? (activeMode ? null : (modesState?.modes[0] ?? null));

  const askSuggestions = useMemo(() => {
    const out: string[] = [];
    if (zoneFocus) out.push(`Vì sao ${zoneFocus.label} đáng chú ý?`);
    if (selectedHour !== null) out.push(`Vì sao đỉnh tải lúc ${String(selectedHour).padStart(2, "0")}:00?`);
    out.push("Quán lúc này cần làm gì trước?");
    out.push("Vì sao JEV kết luận như vậy?");
    return out.slice(0, 3);
  }, [zoneFocus, selectedHour]);

  if (!ready) return <Skeleton rows={6} />;
  if (!token) return <AuthGate />;

  const trong = !evidence || evidence.trangThai === "trong";
  const qualityLines = (vm?.dataQuality ?? []).map((q) => `[${q.level}] ${q.message}`);
  const provenanceLines = (vm?.provenance ?? []).map(
    (p) => `${p.ok ? "OK" : "LỖI"} · ${p.label} · ${p.endpoint}`,
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

      <div className="nq-qv__toolbar" data-testid="quanverse-source">
        <span className="nq-qvsrc__badge nq-qvsrc__badge--real" data-testid="source-badge">
          <span className="nq-qvsrc__dot" aria-hidden="true" />
          Dữ liệu thật
        </span>
        <span className="nq-qvsrc__detail">
          {role === "chu_quan" ? "Chủ quán" : role === "quan_ly" ? "Quản lý" : "Nhân viên"} · JEV judge/rank · không mock
        </span>
        {manager ? (
          <button
            type="button"
            className="nq-qvsrc__btn"
            data-testid="demo-setup-btn-top"
            disabled={demoBusy}
            onClick={() => void handleDemoSetup()}
            title="Nạp dữ liệu demo bằng bản ghi nghiệp vụ thật"
          >
            {demoBusy ? "Đang chuẩn bị…" : "⚙ Demo Setup"}
          </button>
        ) : null}
      </div>

      {!evidence && loading ? (
        <Skeleton rows={6} />
      ) : trong && !loading ? (
        <InsufficientCard evidence={evidence} isManager={manager} demoBusy={demoBusy} onDemoSetup={() => void handleDemoSetup()} />
      ) : !vm || !evidence ? (
        <Skeleton rows={6} />
      ) : (
        <div className="nq-qv__cockpit">
          {vm ? <HeaderBlock header={vm.header} dataSource="real" scenarioLabel={null} /> : null}

          {/* [1] VERDICT */}
          <VerdictBar evidence={evidence} jev={jev} />

          <div className="nq-qv__deck">
            <div className="nq-qv__col nq-qv__col--map">
              <OperationalMap2dClient
                zones={vm.zones}
                selectedId={selectedZone}
                onSelect={(z) => setSelectedZone(z)}
              />
              <ZoneFocus
                zone={zoneFocus}
                zones={vm.zones}
                onClear={() => setSelectedZone(null)}
                onAsk={(q) => void handleAsk(q)}
                onFocusActions={() => {}}
                onPickZone={(z) => setSelectedZone(z)}
              />
            </div>

            <div className="nq-qv__col nq-qv__col--mid">
              {/* [2] TOP 3 */}
              <Top3List evidence={evidence} jev={jev} onAsk={(q) => void handleAsk(q)} />
              {/* [3] 15p + năng lực gộp */}
              <Timeline15 items={vm.timeline} isMock={false} />
              <CapacityForecast
                capacity={vm.capacity}
                isMock={false}
                selectedHour={selectedHour}
                onSelectHour={(h) => setSelectedHour(h)}
              />
            </div>

            <div className="nq-qv__col nq-qv__col--ai">
              {/* [4] HỎI AI */}
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
                onFocusZone={(z) => setSelectedZone(z)}
              />
              {/* 1 đề xuất mode duy nhất (human confirm) */}
              {suggestMode ? (
                <section className="nq-qv-card" data-testid="quanverse-modes" data-mode={suggestMode.mode} aria-label="Đề xuất chế độ">
                  <div className="nq-qv-card__head">
                    <h2 className="nq-qv-card__title">Đề xuất chế độ</h2>
                    <span className="nq-qv-card__spacer" />
                    <span className="nq-qvcapab__st nq-qvcapab__st--ok">{suggestMode.status === "active" ? "Đang bật" : suggestMode.status === "draft" ? "Chờ duyệt" : "Đang tắt"}</span>
                  </div>
                  <p className="nq-qvmode__label" data-testid={`mode-${suggestMode.mode}`}>{suggestMode.label}</p>
                  {suggestMode.effect ? <p className="nq-qvmode__effect">{suggestMode.effect}</p> : null}
                  <div className="nq-qvmode__actions">
                    {suggestMode.status === "off" && modesState?.canActivate ? (
                      <button
                        type="button"
                        className="nq-qvmode__btn nq-qvmode__btn--primary"
                        data-testid={`mode-propose-${suggestMode.mode}`}
                        disabled={busyMode === suggestMode.mode}
                        onClick={() => void runMode(suggestMode.mode, "propose")}
                      >
                        Đề xuất (cần duyệt)
                      </button>
                    ) : null}
                    {suggestMode.status === "draft" && modesState?.canActivate ? (
                      <button
                        type="button"
                        className="nq-qvmode__btn nq-qvmode__btn--primary"
                        data-testid={`mode-confirm-${suggestMode.mode}`}
                        disabled={busyMode === suggestMode.mode}
                        onClick={() => void runMode(suggestMode.mode, "confirm")}
                      >
                        Duyệt bật
                      </button>
                    ) : null}
                    {suggestMode.status === "active" && modesState?.canActivate ? (
                      <button
                        type="button"
                        className="nq-qvmode__btn"
                        disabled={busyMode === suggestMode.mode}
                        onClick={() => void runMode(suggestMode.mode, "deactivate")}
                      >
                        Tắt
                      </button>
                    ) : null}
                    <Link className="nq-linkbtn" href="/lich-tuan">
                      Mở Lịch tuần để hành động
                    </Link>
                  </div>
                  <p className="nq-qvai__disclaimer">JEV chỉ rank — người quyết định và thực hiện.</p>
                </section>
              ) : null}
            </div>
          </div>

          {debug ? (
            <TechnicalDrawer
              summary="Chi tiết kỹ thuật · nguồn & chất lượng dữ liệu (?debug=1)"
              lines={[...qualityLines, ...provenanceLines]}
            />
          ) : null}
        </div>
      )}
    </div>
  );
}
