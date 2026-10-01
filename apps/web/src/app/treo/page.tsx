"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { apiGet, apiSend } from "../../lib/api";
import { matchExact, matchSearch, matchTime, TIME_FILTER_OPTIONS, uniqueSorted, type TimeFilter } from "../../lib/list-filters";
import { actorLabel, formatLuc, ghiNhanLabel, safeText, treoLabel, treoTone, viError } from "../../lib/present";
import { getToken, isManager } from "../../lib/session";
import {
  Alert,
  AuthGate,
  Btn,
  Empty,
  Loading,
  OpsCard,
  PageActions,
  PageHeader,
  PagedList,
  StatusChip,
  TabBar,
  TabButton,
} from "../../ui/kit";
import { FilteredEmpty, ListToolbar } from "../../ui/list-filters";
import { CopilotPane } from "../../ui/copilot/CopilotPane";
import { useStaffNameMap } from "../../ui/ops-pickers";

type ViecTreo = {
  id: string;
  phieu_id?: string;
  mau?: string;
  noi_dung: string;
  created_at?: string;
  nhan_vien?: string;
  trang_thai?: string;
};

type GhiNhan = {
  id?: string;
  loai?: string;
  truoc?: unknown;
  sau?: unknown;
  ai?: string;
  luc?: string;
  nguon?: string;
};

function treoHaystack(v: ViecTreo): string {
  return [v.noi_dung, v.nhan_vien, v.phieu_id, v.mau].filter(Boolean).join(" ");
}

function suaHaystack(g: GhiNhan): string {
  return [g.loai, g.ai, ghiNhanLabel(g.loai), actorLabel(g.ai)].filter(Boolean).join(" ");
}

function suaTomTat(g: GhiNhan): string {
  const loai = ghiNhanLabel(g.loai);
  if (g.nguon === "mo_phong_fixture" || g.nguon === "dung_lai") {
    return `${loai} (dữ liệu mẫu hệ thống)`;
  }
  return loai;
}

export default function TreoPage() {
  const [token, setToken] = useState("");
  const [treo, setTreo] = useState<ViecTreo[]>([]);
  const [sua, setSua] = useState<GhiNhan[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [tab, setTab] = useState<"treo" | "sua">("treo");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [search, setSearch] = useState("");
  const [personF, setPersonF] = useState("all");
  const [timeF, setTimeF] = useState<TimeFilter>("all");
  const [copilotOpen, setCopilotOpen] = useState(false);
  const manager = isManager();
  const staffName = useStaffNameMap();
  /** nv_xx → tên thật; vai trò/agent giữ nhãn của actorLabel; tên người dùng thật giữ nguyên thay vì bị ẩn thành "Nhân viên trong quán". */
  const personName = (id?: string | null) => {
    if (!id) return "";
    if (/^nv_\d+$/i.test(id)) return staffName(id);
    const label = actorLabel(id);
    if (label === "Nhân viên trong quán") return id;
    return label;
  };

  useEffect(() => {
    setToken(getToken());
    if (!getToken()) setLoading(false);
  }, []);

  const load = useCallback(() => {
    if (!getToken()) return;
    Promise.all([
      apiGet<{ items: ViecTreo[] }>("/api/v1/viec-treo")
        .then((d) => setTreo(d.items ?? []))
        .catch(() => setError("Không tải được việc treo.")),
      apiGet<{ items: GhiNhan[] }>("/api/v1/ghi-nhan-sua")
        .then((d) => setSua(d.items ?? []))
        .catch(() => undefined),
    ]).finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (token) load();
  }, [token, load]);

  const activeList = tab === "treo" ? treo : sua;
  const personSource = tab === "treo" ? treo.map((t) => t.nhan_vien) : sua.map((s) => s.ai);
  const personOptions = useMemo(
    () => [{ value: "all", label: "Mọi người" }, ...uniqueSorted(personSource).map((v) => ({ value: v ?? "", label: personName(v) }))],
    [personSource, personName],
  );

  const filteredTreo = useMemo(() => {
    return treo.filter((v) => {
      if (!matchSearch(treoHaystack(v), search)) return false;
      if (!matchExact(v.nhan_vien, personF)) return false;
      if (!matchTime(v.created_at, timeF)) return false;
      return true;
    });
  }, [treo, search, personF, timeF]);

  const filteredSua = useMemo(() => {
    return sua.filter((g) => {
      if (!matchSearch(suaHaystack(g), search)) return false;
      if (!matchExact(g.ai, personF)) return false;
      if (!matchTime(g.luc, timeF)) return false;
      return true;
    });
  }, [sua, search, personF, timeF]);

  const filtered = tab === "treo" ? filteredTreo : filteredSua;
  const filterActive = search.length > 0 || personF !== "all" || timeF !== "all";

  function clearFilters() {
    setSearch("");
    setPersonF("all");
    setTimeF("all");
  }

  useEffect(() => {
    setSearch("");
    setPersonF("all");
    setTimeF("all");
  }, [tab]);

  async function danhDauXong(id: string) {
    setBusy(true);
    setError(null);
    try {
      await apiSend(`/api/v1/viec-treo/${encodeURIComponent(id)}`, { trang_thai: "xong" }, "PATCH");
      setMsg("Đã đánh dấu việc treo là xong.");
      load();
    } catch (e) {
      setError(viError(e, { doing: "đánh dấu việc treo", forbidden: "Chỉ quản lý mới đánh dấu xong việc treo." }));
    } finally {
      setBusy(false);
    }
  }

  const treoDangCho = treo.filter((t) => t.trang_thai !== "xong").length;

  // Phân nhóm việc treo theo trạng thái để bố trí rõ ràng trên màn hình.
  const treoQuaHan = filteredTreo.filter((t) => t.trang_thai === "qua_han");
  const treoDangChoF = filteredTreo.filter((t) => t.trang_thai === "dang_cho");
  const treoXong = filteredTreo.filter((t) => t.trang_thai === "xong");
  const treoKhac = filteredTreo.filter(
    (t) => t.trang_thai !== "qua_han" && t.trang_thai !== "dang_cho" && t.trang_thai !== "xong",
  );

  if (!token) return <AuthGate />;

  return (
    <div className="nq-page">
      <PageHeader
        kicker="Quản lý ca"
        title="Việc treo"
        meta={`${treoDangCho} việc đang chờ · ghi nhận sửa lịch tách riêng để không lẫn.`}
      />
      <PageActions>
        <Btn variant="ghost" onClick={() => setCopilotOpen(true)}>
          Hỏi trợ lý vận hành
        </Btn>
      </PageActions>
      {error ? <Alert>{error}</Alert> : null}
      {msg ? <Alert kind="ok">{msg}</Alert> : null}

      <TabBar>
        <TabButton active={tab === "treo"} onClick={() => setTab("treo")}>
          Việc cần xử lý ({treoDangCho})
        </TabButton>
        <TabButton active={tab === "sua"} onClick={() => setTab("sua")}>
          Lần sửa lịch ({sua.length})
        </TabButton>
      </TabBar>

      {tab === "treo" ? (
        <OpsCard eyebrow="Khu vực 1" title="Việc đang treo trong ca" count={filtered.length} countLabel="việc">
          <ListToolbar
            search={search}
            onSearchChange={setSearch}
            searchPlaceholder="Tìm nội dung treo, phiếu, nhân viên…"
            person={personF}
            onPersonChange={setPersonF}
            personOptions={personOptions}
            time={timeF}
            onTimeChange={(v) => setTimeF(v as TimeFilter)}
            timeOptions={TIME_FILTER_OPTIONS}
            shown={filtered.length}
            total={activeList.length}
            filtered={filterActive}
          />
          {loading ? <Loading skeleton="list">Đang tải việc treo…</Loading> : null}
          {!loading && treo.length === 0 ? <Empty title="Không có việc treo">Ca chạy sạch, không còn việc kẹt.</Empty> : null}
          {!loading && treo.length > 0 && filtered.length === 0 ? <FilteredEmpty onClear={clearFilters} /> : null}

          {!loading && treo.length > 0 && filtered.length > 0 ? (
            <div className="nq-treo-sections">
              {/* Việc quá hạn — ưu tiên xử lý trước */}
              <section className="nq-treo-section">
                <div className="nq-treo-section-head">
                  <h3 className="nq-treo-section-title">
                    <span className="nq-treo-section-dot nq-treo-section-dot--danger" aria-hidden="true" />
                    Quá hạn
                  </h3>
                  <span className="nq-treo-section-count">{treoQuaHan.length} việc</span>
                </div>
                <div className="nq-treo-section-body">
                  {treoQuaHan.length === 0 ? (
                    <p className="nq-treo-empty-note">Không có việc quá hạn.</p>
                  ) : (
                    <PagedList
                      className="nq-treo-grid"
                      items={treoQuaHan}
                      pageSize={12}
                      renderItem={(v) => (
                        <article key={v.id} className="nq-item nq-item--accent-danger">
                          <p className="nq-item-title">{v.noi_dung}</p>
                          <p className="nq-item-sub flex flex-wrap items-center gap-2">
                            <StatusChip tone={treoTone(v.trang_thai)}>{treoLabel(v.trang_thai)}</StatusChip>
                            {v.nhan_vien ? personName(v.nhan_vien) : ""}
                            {v.phieu_id ? (
                              <Link href="/phieu" className="underline text-[var(--nq-accent)]">
                                Mở phiếu
                              </Link>
                            ) : null}
                            {v.created_at ? formatLuc(v.created_at) : ""}
                          </p>
                          {manager ? (
                            <Btn variant="ghost" busy={busy} onClick={() => void danhDauXong(v.id)} className="mt-2">
                              Đánh dấu xong
                            </Btn>
                          ) : null}
                        </article>
                      )}
                    />
                  )}
                </div>
              </section>

              {/* Việc đang chờ làm */}
              <section className="nq-treo-section">
                <div className="nq-treo-section-head">
                  <h3 className="nq-treo-section-title">
                    <span className="nq-treo-section-dot nq-treo-section-dot--warn" aria-hidden="true" />
                    Đang chờ làm
                  </h3>
                  <span className="nq-treo-section-count">{treoDangChoF.length} việc</span>
                </div>
                <div className="nq-treo-section-body">
                  {treoDangChoF.length === 0 ? (
                    <p className="nq-treo-empty-note">Không có việc đang chờ.</p>
                  ) : (
                    <PagedList
                      className="nq-treo-grid"
                      items={treoDangChoF}
                      pageSize={12}
                      renderItem={(v) => (
                        <article key={v.id} className="nq-item nq-item--accent-warn">
                          <p className="nq-item-title">{v.noi_dung}</p>
                          <p className="nq-item-sub flex flex-wrap items-center gap-2">
                            <StatusChip tone={treoTone(v.trang_thai)}>{treoLabel(v.trang_thai)}</StatusChip>
                            {v.nhan_vien ? personName(v.nhan_vien) : ""}
                            {v.phieu_id ? (
                              <Link href="/phieu" className="underline text-[var(--nq-accent)]">
                                Mở phiếu
                              </Link>
                            ) : null}
                            {v.created_at ? formatLuc(v.created_at) : ""}
                          </p>
                          {manager ? (
                            <Btn variant="ghost" busy={busy} onClick={() => void danhDauXong(v.id)} className="mt-2">
                              Đánh dấu xong
                            </Btn>
                          ) : null}
                        </article>
                      )}
                    />
                  )}
                </div>
              </section>

              {/* Việc trạng thái khác (mới ghi…) */}
              {treoKhac.length > 0 ? (
                <section className="nq-treo-section">
                  <div className="nq-treo-section-head">
                    <h3 className="nq-treo-section-title">
                      <span className="nq-treo-section-dot" aria-hidden="true" />
                      Trạng thái khác
                    </h3>
                    <span className="nq-treo-section-count">{treoKhac.length} việc</span>
                  </div>
                  <div className="nq-treo-section-body">
                    <PagedList
                      className="nq-treo-grid"
                      items={treoKhac}
                      pageSize={12}
                      renderItem={(v) => (
                        <article key={v.id} className="nq-item">
                          <p className="nq-item-title">{v.noi_dung}</p>
                          <p className="nq-item-sub flex flex-wrap items-center gap-2">
                            <StatusChip tone={treoTone(v.trang_thai)}>{treoLabel(v.trang_thai)}</StatusChip>
                            {v.nhan_vien ? personName(v.nhan_vien) : ""}
                            {v.phieu_id ? (
                              <Link href="/phieu" className="underline text-[var(--nq-accent)]">
                                Mở phiếu
                              </Link>
                            ) : null}
                            {v.created_at ? formatLuc(v.created_at) : ""}
                          </p>
                          {manager ? (
                            <Btn variant="ghost" busy={busy} onClick={() => void danhDauXong(v.id)} className="mt-2">
                              Đánh dấu xong
                            </Btn>
                          ) : null}
                        </article>
                      )}
                    />
                  </div>
                </section>
              ) : null}

              {/* Việc đã xong — tách riêng, mờ đi để không lẫn với việc cần làm */}
              {treoXong.length > 0 ? (
                <section className="nq-treo-section nq-treo-section--done">
                  <div className="nq-treo-section-head">
                    <h3 className="nq-treo-section-title">
                      <span className="nq-treo-section-dot nq-treo-section-dot--ok" aria-hidden="true" />
                      Đã xong
                    </h3>
                    <span className="nq-treo-section-count">{treoXong.length} việc</span>
                  </div>
                  <div className="nq-treo-section-body">
                    <PagedList
                      className="nq-treo-grid"
                      items={treoXong}
                      pageSize={12}
                      renderItem={(v) => (
                        <article key={v.id} className="nq-item">
                          <p className="nq-item-title">{v.noi_dung}</p>
                          <p className="nq-item-sub flex flex-wrap items-center gap-2">
                            <StatusChip tone={treoTone(v.trang_thai)}>{treoLabel(v.trang_thai)}</StatusChip>
                            {v.nhan_vien ? personName(v.nhan_vien) : ""}
                            {v.phieu_id ? (
                              <Link href="/phieu" className="underline text-[var(--nq-accent)]">
                                Mở phiếu
                              </Link>
                            ) : null}
                            {v.created_at ? formatLuc(v.created_at) : ""}
                          </p>
                        </article>
                      )}
                    />
                  </div>
                </section>
              ) : null}
            </div>
          ) : null}
        </OpsCard>
      ) : (
        <OpsCard eyebrow="Khu vực 2" title="Lần sửa lịch đã ghi" count={filtered.length} countLabel="lần">
          <ListToolbar
            search={search}
            onSearchChange={setSearch}
            searchPlaceholder="Tìm loại sửa, người thao tác…"
            person={personF}
            onPersonChange={setPersonF}
            personOptions={personOptions}
            time={timeF}
            onTimeChange={(v) => setTimeF(v as TimeFilter)}
            timeOptions={TIME_FILTER_OPTIONS}
            shown={filtered.length}
            total={activeList.length}
            filtered={filterActive}
          />
          {loading ? <Loading skeleton="list">Đang tải ghi nhận…</Loading> : null}
          {!loading && sua.length === 0 ? (
            <Empty title="Chưa có lần sửa">Nhả/nhận ca hoặc ghim ô sẽ ghi vào đây.</Empty>
          ) : null}
          {!loading && sua.length > 0 && filtered.length === 0 ? <FilteredEmpty onClear={clearFilters} /> : null}
          <div className="nq-list">
            <PagedList
              items={filteredSua}
              pageSize={10}
              renderItem={(g, i) => (
                <article key={g.id ?? String(i)} className="nq-item">
                  <p className="nq-item-title">{suaTomTat(g)}</p>
                  <p className="nq-item-sub">
                    {personName(g.ai)} · {formatLuc(g.luc)}
                  </p>
                </article>
              )}
            />
          </div>
        </OpsCard>
      )}
      <CopilotPane open={copilotOpen} onClose={() => setCopilotOpen(false)} />
    </div>
  );
}
