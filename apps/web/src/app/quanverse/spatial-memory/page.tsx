"use client";

/** HỒN QUÁN Spatial Memory — map 2D/3D + anchor details + timeline + voice + tour. */

import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiError } from "../../../lib/api";
import { viError } from "../../../lib/present";
import { getToken } from "../../../lib/session";
import { ExpEmpty, ExpSkeleton } from "../../../ui/experience/exp-kit";
import PageAssistant from "../../../ui/experience/quanverse/PageAssistant";
import SpatialAnchorDetails from "../../../ui/experience/spatial/SpatialAnchorDetails";
import SpatialMap from "../../../ui/experience/spatial/SpatialMap";
import type { Anchor2D } from "../../../ui/experience/spatial/SpatialMap2dFallback";
import TourGuide from "../../../ui/experience/spatial/TourGuide";
import VoiceDock from "../../../ui/experience/spatial/VoiceDock";
import { Icon } from "../../../ui/icons";
import { AuthGate } from "../../../ui/kit";

const COPY = { read: { doing: "tải được bản đồ không gian quán" } } as const;

export default function SpatialMemoryPage() {
  const [token, setToken] = useState("");
  const [ready, setReady] = useState(false);
  const [anchors, setAnchors] = useState<Anchor2D[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  /** Lỗi tải giữ đối tượng gốc để `viError` đọc được mã HTTP. */
  const [error, setError] = useState<unknown>(null);
  const [rev, setRev] = useState(0);
  /**
   * Số ký ức đã xác nhận theo neo — cột 3D đọc trực tiếp từ đây.
   *
   * Gộp một lượt cho mọi neo thay vì gọi `/anchors/{id}` từng cái: 8 neo là 8
   * request, mà dữ liệu đã có sẵn ở `/memories`.
   */
  const [memoryCounts, setMemoryCounts] = useState<Record<string, number>>({});
  const [memoryDegraded, setMemoryDegraded] = useState(false);

  const base = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

  useEffect(() => {
    setToken(getToken());
    setReady(true);
  }, []);

  /**
   * Đã đọc xong danh sách neo hay chưa — KHÁC với `ready` (đã biết token hay chưa).
   *
   * Vì sao cần cờ riêng: trước đây trang chỉ có `ready`, và `setReady(true)` chạy
   * trong effect ĐẦU TIÊN, tức TRƯỚC khi biết token. Nên tồn tại một khoảng mà
   * `ready === true`, `token === ""`, `anchors === []` — và nhánh
   * `anchors.length === 0` vẽ ra thông báo **"Chưa có neo nào trên bản đồ"**.
   * Người dùng thấy một câu báo KHÔNG CÓ DỮ LIỆU trong lúc dữ liệu đang về.
   *
   * Đo được bằng `e2e/_diag-height.spec.ts`: chiều cao trang nhảy
   * **720 → 882 → 1288px** trong 200ms đầu, và đáy khung vẽ dịch **203px**
   * (769 → 972) SAU khi khung đã hiện. Đó là layout shift thật, và cũng là lý do
   * bài `spatial-memory.spec.ts` "anchor select shows details" đỏ khi chạy cả bộ:
   * bài đó đo `svgBox` rồi đo từng neo, hai phép đo rơi vào hai trạng thái bố cục
   * khác nhau nên toạ độ không còn khớp (912 > 771).
   *
   * Nay: chỉ khi ĐÃ THỬ đọc xong mà vẫn không có neo thì mới là "chưa có dữ liệu";
   * trong lúc chờ thì giữ skeleton, nên bố cục không nhảy và không có câu báo sai.
   */
  const [anchorsLoaded, setAnchorsLoaded] = useState(false);

  const loadAnchors = useCallback(async () => {
    try {
      const res = await fetch(`${base}/api/v1/experience/map`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new ApiError(res.status);
      const body = (await res.json()) as { anchors: Anchor2D[] };
      setAnchors(body.anchors);
      setSelectedId((cur) =>
        cur && body.anchors.some((a) => a.anchor_id === cur)
          ? cur
          : (body.anchors[0]?.anchor_id ?? null),
      );
      setError(null);
    } catch (e) {
      setError(e);
    } finally {
      // Đặt trong `finally`: đọc lỗi cũng là "đã thử xong", và khi đó nhánh lỗi
      // mới là thứ nên hiện — không phải skeleton treo mãi.
      setAnchorsLoaded(true);
    }
  }, [base, token]);

  const loadMemoryCounts = useCallback(async () => {
    try {
      const res = await fetch(`${base}/api/v1/experience/memories?status=confirmed`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new ApiError(res.status);
      const body = (await res.json()) as { memories: { anchor_id: string }[] };
      const counts: Record<string, number> = {};
      for (const m of body.memories) {
        counts[m.anchor_id] = (counts[m.anchor_id] ?? 0) + 1;
      }
      setMemoryCounts(counts);
      setMemoryDegraded(false);
    } catch {
      // Không chặn bản đồ vì thiếu số đếm — nhưng phải nói thật là chưa đọc được.
      setMemoryCounts({});
      setMemoryDegraded(true);
    }
  }, [base, token]);

  useEffect(() => {
    if (!token) return;
    void loadAnchors();
    void loadMemoryCounts();
  }, [token, loadAnchors, loadMemoryCounts, rev]);

  const selectedLabel = useMemo(
    () => anchors.find((a) => a.anchor_id === selectedId)?.label ?? "",
    [anchors, selectedId],
  );

  /**
   * Một hành động ở KHU VỰC KHÁC trên trang đổi kho ký ức (vd VoiceDock tạo
   * draft mới) → tăng tín hiệu này. Khung chi tiết neo và số đếm ký ức cùng
   * nạp lại, nên "Chờ quyết định" luôn phản ánh đúng kho hiện tại.
   */
  const [detailRev, setDetailRev] = useState(0);
  const refreshAfterRemember = useCallback(() => {
    setDetailRev((r) => r + 1);
    setRev((r) => r + 1);
  }, []);

  if (!ready) return <ExpSkeleton rows={6} />;
  if (!token) return <AuthGate />;
  // Chờ đọc xong danh sách neo trước khi vẽ. Nếu không, nhánh `anchors.length === 0`
  // bên dưới sẽ hiện "Chưa có neo nào trên bản đồ" trong lúc dữ liệu đang về —
  // vừa báo sai, vừa làm bố cục nhảy (xem ghi chú ở `anchorsLoaded`).
  if (!anchorsLoaded && !error) return <ExpSkeleton rows={6} />;

  return (
    <div className="nq-spatial">
      <header className="nq-spatial__header">
        <h1>HỒN QUÁN — Không gian ký ức</h1>
        <p>
          Gắn sự cố, quy trình, lời khen và ký ức vận hành vào bản đồ quán. Ký ức
          chỉ được dùng sau khi có đồng thuận, và luôn xoá được.
        </p>
      </header>

      {error ? (
        <div className="nq-alert nq-alert--error" role="alert">
          {viError(error, COPY.read)}
          <button type="button" className="nq-linkbtn" onClick={() => setRev((r) => r + 1)}>
            <Icon name="refresh" size={14} />
            Thử lại
          </button>
        </div>
      ) : null}
      {memoryDegraded ? (
        <div className="nq-alert nq-alert--warn" role="status">
          Chưa đọc được số ký ức theo neo — cột 3D tạm hiển thị mức cơ sở.
        </div>
      ) : null}

      {anchors.length === 0 && !error ? (
        <ExpEmpty
          icon="location"
          title="Chưa có neo nào trên bản đồ"
          hint="Neo xuất hiện khi quán khai báo khu vực, bàn hoặc thiết bị."
        />
      ) : (
        <div className="nq-spatial__layout">
          <SpatialMap
            anchors={anchors}
            selectedId={selectedId}
            onSelect={setSelectedId}
            memoryCounts={memoryCounts}
          />
          <div className="nq-spatial__side">
            {selectedId ? (
              <SpatialAnchorDetails
                anchorId={selectedId}
                anchorLabel={selectedLabel}
                onChanged={() => setRev((r) => r + 1)}
                refreshSignal={detailRev}
              />
            ) : null}
            <TourGuide anchorLabels={anchors} onFocusAnchor={setSelectedId} />
          </div>
        </div>
      )}

      {/* Trợ lý Quánverse: neo nào còn trống ký ức, ghi nhớ gì tiếp theo. */}
      <PageAssistant page="spatial_memory" />

      <VoiceDock anchorId={selectedId} onRemembered={refreshAfterRemember} />
    </div>
  );
}