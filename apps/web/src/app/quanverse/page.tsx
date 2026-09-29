"use client";

/**
 * QUÁNVERSE — Trung tâm điều hành quán.
 *
 * Một màn trả lời: quán đang thế nào · điểm nào có vấn đề · 15 phút tới có gì ·
 * nhân sự/khu vực nào đang chịu tải · dữ liệu thật hay mô phỏng · AI dựa trên
 * dữ liệu nào.
 *
 * ─── KIẾN TRÚC ────────────────────────────────────────────────────────────
 *
 * Trang này là VỎ MỎNG. Nó chỉ:
 *   1. giữ state (vai trò đang xem · nguồn dữ liệu · khu vực đang chọn),
 *   2. gọi ĐÚNG MỘT hàm của tầng đọc (`getQuanverseRepository`),
 *   3. xếp tám khối.
 * Mọi phép biến đổi dữ liệu nằm trong `repository/`. Không có `fetch` ở đây,
 * không có `?? 0`, không có phép tính nào trên số liệu.
 *
 * ─── ĐÃ BỎ KHỎI TRANG NÀY ─────────────────────────────────────────────────
 *
 * · 3D (react-three-fiber / Canvas / WebGL) — bản đồ là 2D/DOM.
 * · Tab War Room và Cứu ca (cùng các route /quanverse/war-room, /shift-rescue).
 * · Mọi bề mặt KHÁCH HÀNG: hành trình khách, hương vị, sở thích, AR-lite.
 * · Quánverse là bề mặt VẬN HÀNH, không phải CRM và không phải app cho khách.
 */

import dynamic from "next/dynamic";
import { useCallback, useEffect, useState } from "react";
import { getRole, getToken, isManager } from "../../lib/session";
import { AuthGate, Skeleton } from "../../ui/kit";
import type {
  QuanverseRole,
  QuanverseViewModel,
} from "../../ui/experience/quanverse/quanverse-contract";
import {
  QUANVERSE_SCENARIOS,
  getQuanverseRepository,
  mockChoPhep,
  type QuanverseScenario,
} from "../../ui/experience/quanverse/repository";
import AiCopilot from "../../ui/experience/quanverse/ops/AiCopilot";
import CapacityForecast from "../../ui/experience/quanverse/ops/CapacityForecast";
import DataSourceBadge, {
  ProvenancePanel,
} from "../../ui/experience/quanverse/ops/DataSourceBadge";
import EventsList from "../../ui/experience/quanverse/ops/EventsList";
import ExecutiveSnapshot from "../../ui/experience/quanverse/ops/ExecutiveSnapshot";
import HeaderBlock from "../../ui/experience/quanverse/ops/HeaderBlock";
import NeedsAttention from "../../ui/experience/quanverse/ops/NeedsAttention";
import Timeline15 from "../../ui/experience/quanverse/ops/Timeline15";

// Bản đồ 2D chạy phía client; tách chunk để phần đầu trang hiện ngay.
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

  const [scenario, setScenario] = useState<QuanverseScenario>(MAC_DINH_SCENARIO);
  const [dungMock, setDungMock] = useState(false);

  const choPhepMock = mockChoPhep();

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
      const repo = getQuanverseRepository({
        source: dungMock ? "mock" : "real",
        scenario,
      });
      const data = await repo.getViewModel({ role, scenario });
      setVm(data);
    } catch (e) {
      // Tầng đọc đã cô lập lỗi từng nguồn; chỉ tới đây khi dựng cả view-model hỏng.
      setError(e instanceof Error ? e.message : "Không đọc được dữ liệu Quánverse.");
      setVm(null);
    } finally {
      setLoading(false);
    }
  }, [dungMock, scenario, role]);

  useEffect(() => {
    if (token && ready) void load();
  }, [token, ready, load]);

  useEffect(() => {
    setSelectedZone((cur) =>
      cur && vm?.zones.some((z) => z.zoneId === cur) ? cur : null,
    );
  }, [vm]);

  if (!ready) return <Skeleton rows={6} />;
  if (!token) return <AuthGate />;

  const isMock = vm?.dataSource === "mock";

  return (
    <div className="nq-qv" data-testid="quanverse-root">
      {error ? (
        <div className="nq-alert nq-alert--error" role="alert">
          {error}
          <button type="button" className="nq-linkbtn" onClick={() => void load()}>
            Tải lại
          </button>
        </div>
      ) : null}

      {/* Thanh điều khiển: nguồn dữ liệu + bản chiếu theo vai trò */}
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
            onClick={() => setDungMock((v) => !v)}
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
        <>
          {/* A. HEADER — tình trạng quán */}
          <HeaderBlock
            header={vm.header}
            dataSource={vm.dataSource}
            scenarioLabel={vm.scenarioLabel}
          />

          {/* B. EXECUTIVE SNAPSHOT — sáu KPI */}
          <ExecutiveSnapshot kpis={vm.kpis} />

          {/* Lưới chính: bản đồ 2D + cột việc cần xử lý */}
          <div className="nq-qv__grid">
            <OperationalMap2dClient
              zones={vm.zones}
              selectedId={selectedZone}
              onSelect={setSelectedZone}
            />

            <div className="nq-qv__col">
              {/* D. CẦN XỬ LÝ NGAY */}
              <NeedsAttention actions={vm.actions} onFocusZone={setSelectedZone} />

              {/* E. 15 PHÚT TỚI */}
              <Timeline15 items={vm.timeline} isMock={isMock} />
            </div>
          </div>

          {/* F. NĂNG LỰC / TẢI VẬN HÀNH + G. AI COPILOT */}
          <div className="nq-qv__grid nq-qv__grid--two">
            <CapacityForecast capacity={vm.capacity} isMock={isMock} />
            <AiCopilot copilot={vm.copilot} provenance={vm.provenance} />
          </div>

          {/* H. SỰ KIỆN VẬN HÀNH */}
          <EventsList events={vm.events} onFocusZone={setSelectedZone} />

          {/* Chất lượng dữ liệu + nguồn lỗi */}
          {vm.dataQuality.length > 0 ? (
            <ul className="nq-qv__quality" aria-label="Chất lượng dữ liệu">
              {vm.dataQuality.map((q, i) => (
                <li
                  key={`${q.code}-${i}`}
                  className={`nq-qv__quality-item nq-qv__quality-item--${q.level}`}
                >
                  {q.message}
                </li>
              ))}
            </ul>
          ) : null}

          <ProvenancePanel provenance={vm.provenance} />
        </>
      )}
    </div>
  );
}
