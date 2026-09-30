"use client";

/**
 * QUANVERSE — Living Cafe OS.
 *
 * Một trạng thái quán, bốn bản chiếu theo vai trò. Bố cục:
 *   hàng vai trò → mặt bằng (2D/3D) + trục 15 phút/chế độ → chi tiết khu vực
 *   → ba lane khách (hương vị · sở thích · AR) → dòng sự kiện.
 *
 * Nguyên tắc giữ từ bản trước: server đã strip dữ liệu theo vai trò, client
 * không tự lọc lại; mọi mã nội bộ đi qua bảng nhãn `exp-present`.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ApiError } from "../../lib/api";
import { getRole, getToken } from "../../lib/session";
import { formatLuc, viError } from "../../lib/present";
import { Icon } from "../../ui/icons";
import { AuthGate } from "../../ui/kit";
import { ExpSkeleton } from "../../ui/experience/exp-kit";
import {
  dataQualityLabel,
  dataQualityLevelLabel,
  eventStatusLabel,
  eventTypeLabel,
  sourceLabel,
} from "../../ui/experience/exp-present";
import LivingMap from "../../ui/experience/quanverse/LivingMap";
import RoleProjection, { type RoleId } from "../../ui/experience/quanverse/RoleProjection";
import ModeRail, { type ModeAction } from "../../ui/experience/quanverse/ModeRail";
import HorizonTimeline from "../../ui/experience/quanverse/HorizonTimeline";
import FlavorUniverse from "../../ui/experience/quanverse/FlavorUniverse";
import PreferenceConsent from "../../ui/experience/quanverse/PreferenceConsent";
import ArLiteOverlay from "../../ui/experience/quanverse/ArLiteOverlay";
import ZoneDetail from "../../ui/experience/quanverse/ZoneDetail";
import PageAssistant from "../../ui/experience/quanverse/PageAssistant";
import type {
  LiveSnapshotUI,
  ZoneUI,
} from "../../ui/experience/quanverse/quanverse-model";

const ALL_ROLES: RoleId[] = ["khach", "nhan_vien", "quan_ly", "chu_quan"];
const ROLE_NAME: Record<RoleId, string> = {
  khach: "Khách",
  nhan_vien: "Nhân viên",
  quan_ly: "Quản lý",
  chu_quan: "Chủ quán",
};

const COPY = {
  snapshot: { doing: "đọc được trạng thái quán" },
  mode: {
    doing: "đổi chế độ quán",
    forbidden: "Chỉ quản lý hoặc chủ quán mới đổi được chế độ quán.",
  },
} as const;

export default function QuanversePage() {
  const [token, setToken] = useState("");
  const [role, setRole] = useState<RoleId>("quan_ly");
  const [ready, setReady] = useState(false);
  const [snap, setSnap] = useState<LiveSnapshotUI | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedZone, setSelectedZone] = useState<string | null>(null);
  const [busyMode, setBusyMode] = useState(false);
  const [canActivateMode, setCanActivateMode] = useState(false);
  /**
   * Máy chủ có thật sự cho đổi vai trò xem không (`null` = chưa biết).
   *
   * `replay_role` chỉ được tôn trọng khi bật chế độ demo/replay; production
   * luôn dùng vai từ token. Không có cờ này thì thanh chọn vai trò vẫn sáng ở
   * production: người dùng bấm "Khách", nút sáng lên, nhưng dữ liệu vẫn là bản
   * chiếu quản lý — UI nói dối đúng chỗ người dùng dùng để KIỂM TRA quyền.
   */
  const [replayAllowed, setReplayAllowed] = useState<boolean | null>(null);
  /**
   * Chốt "máy chủ đã bỏ qua `replay_role`" — MỘT CHIỀU, không bao giờ mở lại.
   *
   * Vì sao cần chốt riêng: khi phát hiện lệch vai, ta đồng bộ `setRole(body.role)`
   * để nút đang sáng khớp dữ liệu. Lần gọi kế tiếp sẽ có `body.role === forRole`
   * (vì đã đồng bộ) và nhánh "khớp" tưởng nhầm là replay hoạt động → bật lại nút
   * → người dùng bấm tiếp → lệch lại. Cờ nhấp nháy giữa hai trạng thái. Chốt
   * một chiều cắt vòng đó: đã biết máy chủ bỏ qua thì giữ nguyên kết luận.
   */
  const replayLockedRef = useRef(false);

  const base = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

  /**
   * Dò xem máy chủ có tôn trọng `replay_role` không — chạy NGAY khi tải trang.
   *
   * Vì sao không đợi người dùng bấm mới biết: nếu chỉ suy từ phản hồi của lần
   * bấm đầu, người dùng đã thấy một thanh nút bấm được (lời hứa sai) rồi mới
   * thấy nó biến mất. Dò trước bằng cách hỏi một vai KHÁC vai phiên: lệch nghĩa
   * là chế độ replay đang tắt. Chỉ so vai, không dùng dữ liệu trả về — nên không
   * tốn gì thêm và không đổi bản chiếu đang hiển thị.
   */
  const probeReplay = useCallback(
    async (sessionRole: string) => {
      const other = ALL_ROLES.find((r) => r !== sessionRole);
      if (!other) return;
      try {
        const res = await fetch(
          `${base}/api/v1/experience/quanverse/snapshot?replay_role=${other}`,
          { headers: token ? { Authorization: `Bearer ${token}` } : {} },
        );
        if (!res.ok) return;
        const body = (await res.json()) as { role?: string };
        if (body.role && body.role !== other) {
          replayLockedRef.current = true;
          setReplayAllowed(false);
        } else {
          setReplayAllowed(true);
        }
      } catch {
        // Không dò được thì để `null` — thanh vai trò giữ nguyên, không kết luận.
      }
    },
    [base, token],
  );

  useEffect(() => {
    setToken(getToken());
    const r = getRole() as RoleId;
    if (ALL_ROLES.includes(r)) setRole(r);
    setReady(true);
  }, []);

  const loadSnapshot = useCallback(async (forRole: RoleId) => {
    setError(null);
    try {
      const qs = `?replay_role=${forRole}`;
      const res = await fetch(`${base}/api/v1/experience/quanverse/snapshot${qs}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new ApiError(res.status);
      const body = (await res.json()) as LiveSnapshotUI;
      setSnap(body);
      // Máy chủ là nguồn sự thật về vai trò. Lệch nghĩa là `replay_role` đã bị
      // bỏ qua (production) → chốt lại và đồng bộ nút đang sáng.
      if (body.role !== forRole) {
        replayLockedRef.current = true;
        setReplayAllowed(false);
        setRole(body.role);
      } else if (!replayLockedRef.current) {
        setReplayAllowed(true);
      }
    } catch (e) {
      setError(viError(e, COPY.snapshot));
    }
  }, [base, token]);

  /**
   * Quyền đổi chế độ do máy chủ quyết, không suy từ vai trò đang xem.
   *
   * Trang này cho phép đổi `replay_role` để xem các bản chiếu khác nhau, nhưng
   * quyền thao tác vẫn thuộc về phiên đăng nhập thật — nếu lấy `role` đang xem
   * thì khách sẽ thấy nút duyệt chế độ.
   */
  const loadModeCapability = useCallback(async () => {
    try {
      const res = await fetch(`${base}/api/v1/experience/quanverse/modes`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) return;
      const body = (await res.json()) as { can_activate?: boolean; role?: string };
      setCanActivateMode(Boolean(body.can_activate));
      // Vai PHIÊN do máy chủ trả — dùng để dò xem `replay_role` có được tôn
      // trọng không (xem `probeReplay`).
      if (body.role) void probeReplay(body.role);
    } catch {
      setCanActivateMode(false);
    }
  }, [base, token, probeReplay]);

  useEffect(() => {
    if (token && ready) {
      void loadSnapshot(role);
      void loadModeCapability();
    }
  }, [token, ready, role, loadSnapshot, loadModeCapability]);

  const actOnMode = useCallback(
    async (mode: string, action: ModeAction) => {
      setBusyMode(true);
      setError(null);
      try {
        const path =
          action === "propose"
            ? `/modes/${mode}/propose`
            : action === "confirm"
              ? `/modes/${mode}/confirm`
              : `/modes/${mode}/deactivate`;
        const res = await fetch(`${base}/api/v1/experience/quanverse${path}`, {
          method: "POST",
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        });
        if (!res.ok) throw new ApiError(res.status);
        await loadSnapshot(role);
      } catch (e) {
        setError(viError(e, COPY.mode));
      } finally {
        setBusyMode(false);
      }
    },
    [base, token, role, loadSnapshot],
  );

  // Khi đổi vai trò, khu vực đang chọn có thể không còn trong bản chiếu mới.
  useEffect(() => {
    setSelectedZone((cur) => {
      if (!cur) return null;
      return snap?.zones?.some((z) => z.zone_id === cur) ? cur : null;
    });
  }, [snap]);

  const selected = useMemo(
    () => snap?.zones?.find((z) => z.zone_id === selectedZone) ?? null,
    [snap, selectedZone],
  );

  /** Tra khu vực theo mã — để sự kiện hiện nhãn khu vực thay vì mã khô. */
  const zoneById = useMemo(() => {
    const map = new Map<string, ZoneUI>();
    for (const z of snap?.zones ?? []) map.set(z.zone_id, z);
    return map;
  }, [snap]);

  if (!ready) return <ExpSkeleton rows={6} />;
  if (!token) return <AuthGate />;

  const quality = snap?.data_quality ?? [];
  const events = snap?.events ?? [];
  const activeModes = (snap?.modes ?? []).filter((m) => m.active).length;

  return (
    <div className="nq-quanverse">
      <header className="nq-exp-header">
        <h1>QUÁNVERSE — Quán sống của bạn</h1>
        <p>
          Một trạng thái quán, bốn bản chiếu theo vai trò. Bản chiếu do máy chủ cắt
          theo quyền — đổi vai trò để thấy phần dữ liệu tương ứng được mở ra hoặc che đi.
        </p>
        {/* Danh tính bản chiếu: có sẵn trong payload nhưng trước đây không hiện,
            nên khi cần đối chiếu "hai người đang xem cùng một bản không" thì
            không có gì để so. */}
        {snap ? (
          <p className="nq-exp-header__ids">
            <span>Quán {snap.store_id}</span>
            <span aria-hidden="true">·</span>
            <span>Bản chiếu {snap.snapshot_id}</span>
          </p>
        ) : null}
      </header>

      {error ? (
        <div className="nq-alert nq-alert--error" role="alert">
          {error}
          <button
            type="button"
            className="nq-linkbtn"
            onClick={() => void loadSnapshot(role)}
          >
            <Icon name="refresh" size={14} />
            Tải lại
          </button>
        </div>
      ) : null}

      {/* Chuyển bản chiếu theo vai trò — vai trò đang xem được đánh dấu rõ.
          Ở production máy chủ bỏ qua `replay_role` (vai lấy từ token), nên
          thanh này phải NÓI THẬT: hoặc là công cụ xem thử hoạt động, hoặc là
          chỉ báo "đang xem bản chiếu của bạn". Nút bấm được mà không đổi gì là
          lời hứa sai — người dùng dùng đúng chỗ này để kiểm tra phân quyền. */}
      <div className="nq-rolebar" role="group" aria-label="Chọn vai trò xem">
        {replayAllowed === false ? (
          <span className="nq-rolechip nq-rolechip--locked" data-testid="role-locked">
            <Icon name="user" size={13} />
            Đang xem bản chiếu theo quyền của bạn
          </span>
        ) : (
          <>
            {ALL_ROLES.map((r) => (
              <button
                key={r}
                type="button"
                className={`nq-rolebtn${role === r ? " is-on" : ""}`}
                data-testid={`role-${r}`}
                aria-pressed={role === r}
                onClick={() => setRole(r)}
              >
                {ROLE_NAME[r]}
              </button>
            ))}
          </>
        )}
        <span className="nq-rolechip">
          <Icon name="refresh" size={13} />
          Bản chiếu trực tiếp
        </span>
      </div>

      {replayAllowed === false ? (
        <p className="nq-quanverse__hint" data-testid="role-locked-note">
          <Icon name="info" size={14} />
          Môi trường này dùng vai trò từ phiên đăng nhập nên không đổi bản chiếu
          được. Muốn xem bốn bản chiếu, chạy ở chế độ diễn tập.
        </p>
      ) : null}

      {!snap ? (
        <ExpSkeleton rows={6} grid />
      ) : (
        <RoleProjection role={snap.role}>
          {/* Tóm tắt trạng thái — bốn con số đọc được trong một lần liếc */}
          <ul className="nq-summary" data-testid="quanverse-summary">
            <li className="nq-statcard">
              <span className="nq-statcard__num">{snap.zones?.length ?? 0}</span>
              <span className="nq-statcard__label">Khu vực trong bản chiếu</span>
            </li>
            <li className="nq-statcard">
              <span className="nq-statcard__num">{activeModes}</span>
              <span className="nq-statcard__label">Chế độ đang bật</span>
            </li>
            <li className="nq-statcard">
              <span className="nq-statcard__num">{snap.next_horizon?.length ?? 0}</span>
              <span className="nq-statcard__label">Mốc trong 15 phút tới</span>
            </li>
            <li className="nq-statcard">
              <span className="nq-statcard__num">{events.length}</span>
              <span className="nq-statcard__label">Sự kiện vận hành</span>
            </li>
          </ul>

          {/* Trợ lý Quánverse — nói thành lời chuyện đang xảy ra, thay vì bắt
              người dùng tự đọc bốn con số trên rồi tự suy ra. */}
          <PageAssistant page="living_map" />

          {quality.length > 0 ? (
            <ul className="nq-quality" aria-label="Chất lượng dữ liệu">
              {quality.map((q) => (
                <li key={q.code} className={`nq-quality__item nq-quality__item--${q.level}`}>
                  {/* Icon theo MỨC, không phải nhị phân info/còn-lại: mức "warning"
                      trước đây rơi vào nhánh `warn` nên hiện đúng, nhưng nếu thêm
                      mức mới (vd "danger") thì lại thành cảnh báo — nay chỉ `info`
                      và `ok` mới là icon thông tin. */}
                  <Icon
                    name={q.level === "info" || q.level === "ok" ? "info" : "warn"}
                    size={14}
                  />
                  <strong>{dataQualityLevelLabel(q.level)}</strong>
                  <span>{dataQualityLabel(q.code)}</span>
                  {/* Câu giải thích đầy đủ của máy chủ. Trước đây chỉ hiện nhãn
                      ngắn của `code`, nên cảnh báo quan trọng ("dữ liệu là fixture,
                      không phải đo thật") bị rút thành một nhãn khó hiểu. */}
                  {q.message ? (
                    <span className="nq-quality__msg">{q.message}</span>
                  ) : null}
                </li>
              ))}
            </ul>
          ) : null}

          {/* Bố cục: MẶT BẰNG full chiều ngang (nội dung rộng, không bị ép cột),
              rồi các panel việc-cần-quyết xuống DƯỚI thành lưới nhiều cột đều
              nhau. Trước đây cột phải bị ép 26–32% nên nội dung bên đó dồn thành
              một dải hẹp, chữ bị bó và kéo dài xuống màn hình. */}
          <div className="nq-quanverse__layout">
            <LivingMap
              zones={snap.zones ?? []}
              selectedId={selectedZone}
              onSelectZone={setSelectedZone}
            />
            <div className="nq-quanverse__panels">
              {selected ? (
                <ZoneDetail
                  zone={selected}
                  events={events}
                  onClose={() => setSelectedZone(null)}
                />
              ) : (
                <p className="nq-quanverse__hint">
                  <Icon name="location" size={14} />
                  Chọn một khu vực trên mặt bằng để xem tải, gợi ý hành động và sự kiện tại chỗ.
                </p>
              )}
              <HorizonTimeline items={snap.next_horizon ?? []} />
              <ModeRail
                modes={snap.modes ?? []}
                onAction={actOnMode}
                busy={busyMode}
                canActivate={canActivateMode}
              />
            </div>
          </div>

          {/* Không gian khách: Hương vị · Sở thích · AR */}
          <div className="nq-quanverse__guests">
            <FlavorUniverse />
            <PreferenceConsent />
            <ArLiteOverlay />
          </div>

          {/* Event/action list theo bản chiếu */}
          <section className="nq-quanverse__events" aria-label="Sự kiện trạng thái">
            <div className="nq-exp-section__head">
              <Icon name="bell" size={16} />
              <h3 className="nq-exp-section__title">Sự kiện</h3>
              <span className="nq-exp-section__spacer" />
              <span className="nq-quanverse__eventcount">{events.length} mục</span>
            </div>
            <ul data-testid="quanverse-events">
              {events.map((ev) => {
                const zone = zoneById.get(ev.zone_id ?? "");
                return (
                  <li key={ev.event_id} className="nq-quanverse__event">
                    <span className="nq-quanverse__eventtype">
                      {eventTypeLabel(ev.event_type)}
                    </span>
                    <span className="nq-quanverse__eventsum">{ev.summary}</span>
                    <span className="nq-quanverse__eventmeta">
                      {/* Mốc thời gian: dữ liệu này vốn đã có trong bản chiếu nhưng
                          chưa từng hiện ra — không có nó thì người đọc không biết
                          sự kiện vừa xảy ra hay từ sáng. */}
                      <time
                        className="nq-quanverse__eventtime"
                        dateTime={ev.occurred_at}
                      >
                        {formatLuc(ev.occurred_at)}
                      </time>
                      {/* Vùng gắn kết: bấm để mở chi tiết khu vực đó. */}
                      {zone ? (
                        <button
                          type="button"
                          className="nq-zonechip"
                          data-testid={`event-zone-${ev.event_id}`}
                          onClick={() => setSelectedZone(zone.zone_id)}
                        >
                          <Icon name="location" size={12} />
                          {zone.label}
                        </button>
                      ) : (
                        <span className="nq-zonechip nq-zonechip--none">
                          Toàn quán
                        </span>
                      )}
                      <span className="nq-quanverse__eventsrc">
                        {sourceLabel(ev.source)}
                      </span>
                      <span className="nq-quanverse__eventstatus">
                        {eventStatusLabel(ev.status)}
                      </span>
                    </span>
                  </li>
                );
              })}
              {events.length === 0 && (
                <li className="nq-quanverse__event nq-quanverse__event--empty">
                  Không có sự kiện vận hành cho bản chiếu này.
                </li>
              )}
            </ul>
          </section>
        </RoleProjection>
      )}
    </div>
  );
}