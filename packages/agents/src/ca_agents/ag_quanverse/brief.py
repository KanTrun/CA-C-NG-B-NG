"""Quánverse Brief — tổng hợp TẤT ĐỊNH cho 5 trang của bề mặt Quánverse.

Vì sao có module này
--------------------
Năm trang Quánverse đều đã có endpoint thật trả dữ liệu thật, nhưng người dùng
vẫn phải tự đọc số rồi tự suy ra "chuyện gì đang xảy ra". Không có chỗ nào nói
thành lời rằng *hôm nay có mấy việc cần quyết, cái nào gấp, vì sao*. Module này
dựng đúng khối đó — từ chính các con số hệ thống đã tính, **không gọi LLM**.

Ranh giới với LLM (ADR-002)
---------------------------
`build_brief` trả `QuanverseBrief` toàn số liệu tất định. LLM (nếu bật) chỉ nhận
khối này làm ngữ cảnh và được phép DIỄN ĐẠT LẠI — không thêm số, không bịa kết
luận. Vì vậy mọi câu trả lời đều truy được về `grounded_refs`, và khi không có
bản ghi nào thì brief nói thẳng "chưa có dữ liệu" thay vì suy diễn.

Quy ước số (giống plan hao hụt): `None` = CHƯA CÓ DỮ LIỆU, `0.0` = có dữ liệu và
bằng không. UI in "—" cho `None`, không được in "0".
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from ca_contracts import (
    DataQualityNotice,
    QuanverseBrief,
    QuanverseMetric,
    QuanversePage,
)


@dataclass
class PageFacts:
    """Đầu vào thô cho một brief — mọi trường đều do lớp HTTP đọc từ hệ thống.

    Giữ dạng dataclass (không phải BaseModel) vì đây là đối tượng CHUYỀN TAY nội
    bộ, không qua JSON: hợp đồng ra ngoài là `QuanverseBrief`.
    """

    page: QuanversePage
    headline: str = ""
    facts: list[str] = field(default_factory=list)
    metrics: list[QuanverseMetric] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    next_actions: list[str] = field(default_factory=list)
    grounded_refs: list[str] = field(default_factory=list)
    data_quality: list[DataQualityNotice] = field(default_factory=list)


def _metric(
    key: str,
    label: str,
    value: float | None,
    *,
    unit: str = "",
    tone: str = "default",
) -> QuanverseMetric:
    """Tạo metric, ép `tone` về tập hợp lệ để dữ liệu xấu không làm vỡ hợp đồng."""
    allowed = {"default", "ok", "warn", "danger"}
    return QuanverseMetric(
        key=key,
        label=label,
        value=value,
        unit=unit,
        tone=tone if tone in allowed else "default",  # type: ignore[arg-type]
    )


def _load_tone(load: float | None) -> str:
    """Ngưỡng tải khu vực — CÙNG ngưỡng với `ZoneDetail.advice` ở UI (0.7 / 0.4).

    Giữ đúng hai mốc đó ở cả hai phía để brief và bảng chi tiết không bao giờ
    nói ngược nhau về cùng một khu vực.
    """
    if load is None:
        return "default"
    if load >= 0.7:
        return "danger"
    if load >= 0.4:
        return "warn"
    return "ok"


def _fmt_pct(value: float | None) -> str:
    """`None` → 'chưa có dữ liệu' (KHÔNG phải 0%)."""
    if value is None:
        return "chưa có dữ liệu"
    return f"{round(value * 100)}%"


# ── Bản đồ quán (Living Map) ────────────────────────────────────────────────


def brief_living_map(
    *,
    zones: list[dict[str, Any]],
    events: list[dict[str, Any]],
    modes: list[dict[str, Any]],
    horizon: list[dict[str, Any]],
    data_quality: list[dict[str, Any]] | None = None,
    thoi_tiet: dict[str, Any] | None = None,
    stations: dict[str, Any] | None = None,
    forecast: dict[str, Any] | None = None,
) -> PageFacts:
    """Tổng hợp `/quanverse` — khu vực quá tải, việc 15 phút tới, chế độ đang bật."""
    out = PageFacts(page=QuanversePage.LIVING_MAP)

    zone_rows = [z for z in zones if z.get("active", True)]
    hot = [z for z in zone_rows if (z.get("load_signal") or 0) >= 0.7]
    warm = [z for z in zone_rows if 0.4 <= (z.get("load_signal") or 0) < 0.7]
    active_modes = [m for m in modes if m.get("active")]

    # Ưu tiên trạng thái tải từ stations thật (canh_bao) nếu có.
    if isinstance(stations, dict) and stations.get("co_du_lieu"):
        station_rows = [
            s for s in (stations.get("stations") or []) if isinstance(s, dict)
        ]
        hot_live = [s for s in station_rows if s.get("canh_bao") == "qua_tai"]
        warm_live = [s for s in station_rows if s.get("canh_bao") == "chu_y"]
        if hot_live or warm_live or station_rows:
            hot = [
                {
                    "zone_id": s.get("zone_id"),
                    "label": s.get("ten") or s.get("zone_id"),
                    "load_signal": 0.9 if s.get("canh_bao") == "qua_tai" else 0.5,
                }
                for s in hot_live
            ]
            warm = [
                {
                    "zone_id": s.get("zone_id"),
                    "label": s.get("ten") or s.get("zone_id"),
                    "load_signal": 0.5,
                }
                for s in warm_live
            ]
            chi = stations.get("chi_so") or {}
            if chi.get("don_dang_xu_ly") is not None:
                out.metrics.append(
                    _metric(
                        "orders_live",
                        "Đơn đang xử lý",
                        float(chi["don_dang_xu_ly"]),
                        unit="đơn",
                        tone="warn" if float(chi["don_dang_xu_ly"]) >= 4 else "default",
                    )
                )
                out.grounded_refs.append("stations.chi_so.don_dang_xu_ly")

    if isinstance(forecast, dict) and forecast.get("co_du_lieu"):
        peaks = forecast.get("giao_dich_nhat") or []
        days = forecast.get("so_ngay_du_lieu")
        if peaks:
            labels = ", ".join(f"{int(h):02d}:00" for h in peaks[:3])
            out.facts.append(f"Giờ đông nhất theo lịch sử đơn: {labels}.")
            out.grounded_refs.append("forecast.giao_dich_nhat")
        if days is not None:
            out.metrics.append(
                _metric(
                    "forecast_days",
                    "Ngày dữ liệu dự báo",
                    float(days),
                    unit="ngày",
                )
            )
            out.grounded_refs.append("forecast.so_ngay_du_lieu")

    out.headline = f"{len(zone_rows)} khu vực đang mở · {len(active_modes)} chế độ bật"

    out.metrics.append(_metric("zones", "Khu vực đang mở", float(len(zone_rows)), unit="khu vực"))
    out.metrics.append(
        _metric(
            "hot_zones",
            "Khu vực quá tải",
            float(len(hot)),
            unit="khu vực",
            tone="danger" if hot else "ok",
        )
    )
    out.metrics.append(
        _metric(
            "active_modes",
            "Chế độ đang bật",
            float(len(active_modes)),
            unit="chế độ",
            tone="ok" if active_modes else "default",
        )
    )
    out.metrics.append(
        _metric(
            "horizon",
            "Mốc trong 15 phút tới",
            float(len(horizon)),
            unit="mốc",
            tone="warn" if len(horizon) >= 4 else "default",
        )
    )

    for z in hot:
        label = str(z.get("label") or z.get("zone_id") or "")
        out.risks.append(f"{label} đang quá tải ({_fmt_pct(z.get('load_signal'))})")
        out.grounded_refs.append(str(z.get("zone_id") or label))
    if not hot and warm:
        names = ", ".join(str(z.get("label") or z.get("zone_id")) for z in warm)
        out.facts.append(f"Chưa có khu vực quá tải, nhưng {names} đang ở mức chú ý.")

    confirmed_events = [e for e in events if str(e.get("status") or "") in {"confirmed", "da_xac_nhan", ""}]
    if events:
        out.facts.append(f"{len(events)} sự kiện vận hành đang được ghi nhận.")
        for e in confirmed_events[:5]:
            summary = str(e.get("summary") or "").strip()
            if summary:
                out.facts.append(summary)
                ref = str(e.get("event_id") or "")
                if ref:
                    out.grounded_refs.append(ref)

    for item in horizon[:6]:
        title = str(item.get("title") or "").strip()
        if title:
            out.next_actions.append(title)
            ref = str(item.get("item_id") or "")
            if ref:
                out.grounded_refs.append(ref)

    for mode in active_modes:
        code = str(mode.get("mode") or "")
        if code:
            out.facts.append(f"Chế độ {code} đang bật.")
            out.grounded_refs.append(code)

    # AI FORECAST — tín hiệu thời tiết (nếu có). Chỉ gắn fact/risk tất định,
    # không bịa số nhu cầu. Mode Trời mưa vẫn cần người duyệt.
    if isinstance(thoi_tiet, dict) and thoi_tiet.get("co_du_lieu"):
        hien_tai_raw = thoi_tiet.get("hien_tai")
        vi_tri_raw = thoi_tiet.get("vi_tri")
        impact_raw = thoi_tiet.get("anh_huong_quan")
        hien_tai: dict[str, Any] = hien_tai_raw if isinstance(hien_tai_raw, dict) else {}
        vi_tri: dict[str, Any] = vi_tri_raw if isinstance(vi_tri_raw, dict) else {}
        impact: dict[str, Any] = impact_raw if isinstance(impact_raw, dict) else {}
        mo_ta = str(hien_tai.get("mo_ta") or "").strip()
        nhiet = hien_tai.get("nhiet_do")
        thanh = str(vi_tri.get("thanh_pho") or "").strip()
        tinh = str(vi_tri.get("tinh") or "").strip()
        noi = ", ".join(x for x in (thanh, tinh) if x)
        if mo_ta:
            temp_s = f", {nhiet:.0f}°C" if isinstance(nhiet, (int, float)) else ""
            loc_s = f" tại {noi}" if noi else ""
            out.facts.append(f"Thời tiết hiện tại{loc_s}: {mo_ta}{temp_s}.")
            out.grounded_refs.append("thoi_tiet_hom_nay")
        tom_tat = str(impact.get("tom_tat") or "").strip()
        if tom_tat:
            if impact.get("de_xuat_mode"):
                out.risks.append(tom_tat)
            else:
                out.facts.append(tom_tat)
        for yeu in list(impact.get("yeu_to") or [])[:3]:
            text = str(yeu).strip()
            if text:
                out.facts.append(text)
        mode_dx = str(impact.get("de_xuat_mode") or "").strip()
        if mode_dx:
            label = str(impact.get("de_xuat_mode_label") or mode_dx)
            out.next_actions.append(
                f"Cân nhắc đề xuất chế độ {label} (cần quản lý duyệt — không tự bật)."
            )
            out.grounded_refs.append(f"de_xuat_mode:{mode_dx}")
    elif isinstance(thoi_tiet, dict) and thoi_tiet.get("can_cau_hinh"):
        out.data_quality.append(
            DataQualityNotice(
                code="thoi_tiet_thieu_dia_chi",
                level="info",
                message="Chưa có vị trí quán (GPS hoặc địa chỉ) nên AI FORECAST chưa có tín hiệu thời tiết.",
            )
        )

    for dq in data_quality or []:
        try:
            out.data_quality.append(DataQualityNotice.model_validate(dq))
        except Exception:  # pragma: no cover - fixture lạ không được làm sập brief
            continue
    if not zone_rows:
        out.risks.append("Chưa đọc được khu vực nào của quán.")

    return out


# ── Phòng tình huống (War Room) ─────────────────────────────────────────────


def brief_war_room(
    *,
    simulation: dict[str, Any] | None,
    scenarios_requested: list[str] | None = None,
) -> PageFacts:
    """Tổng hợp `/quanverse/war-room` — phương án nào rẻ/an toàn nhất, cảnh báo gì."""
    out = PageFacts(page=QuanversePage.WAR_ROOM)
    if not simulation:
        out.headline = "Chưa chạy mô phỏng nào"
        out.next_actions.append("Chọn kịch bản và chạy mô phỏng để so sánh phương án.")
        out.risks.append("Chưa có bản mô phỏng nên không có gì để so sánh.")
        return out

    options = list(simulation.get("options") or [])
    baseline = simulation.get("baseline") or {}
    sim_id = str(simulation.get("simulation_id") or "")

    out.headline = f"{len(options)} phương án cho {len(scenarios_requested or [])} kịch bản"
    out.metrics.append(_metric("options", "Phương án", float(len(options)), unit="phương án"))

    stale = [o for o in options if o.get("stale_data")]
    violations = [o for o in options if o.get("constraint_violations")]
    costly = [o for o in options if (o.get("estimated_cost") or 0) > 0]

    out.metrics.append(
        _metric("stale", "Phương án dùng số cũ", float(len(stale)), unit="phương án",
                tone="warn" if stale else "ok")
    )
    out.metrics.append(
        _metric("violations", "Phương án vi phạm ràng buộc", float(len(violations)), unit="phương án",
                tone="danger" if violations else "ok")
    )

    if baseline:
        out.facts.append(
            "Mốc so sánh là trạng thái hiện tại của quán "
            f"(hash {str(simulation.get('baseline_snapshot_hash') or '?')[:8]})."
        )
        ref = str(simulation.get("baseline_snapshot_hash") or "")
        if ref:
            out.grounded_refs.append(ref)

    # Phương án không vi phạm + không dùng số cũ là nhóm "dùng được".
    usable = [o for o in options if not o.get("constraint_violations") and not o.get("stale_data")]
    if usable:
        cheapest = min(
            (o for o in usable if o.get("estimated_cost") is not None),
            key=lambda o: o.get("estimated_cost") or 0,
            default=None,
        )
        if cheapest is not None:
            out.facts.append(
                f"Phương án ít tốn kém nhất trong nhóm dùng được: {cheapest.get('option_id')} "
                f"({cheapest.get('estimated_cost')} đ)."
            )
            out.grounded_refs.append(str(cheapest.get("option_id") or ""))

    for o in violations:
        out.risks.append(
            f"{o.get('option_id')} vi phạm ràng buộc: "
            + ", ".join(str(v) for v in (o.get("constraint_violations") or []))
        )
        out.grounded_refs.append(str(o.get("option_id") or ""))
    for o in stale:
        out.risks.append(f"{o.get('option_id')} dùng dữ liệu đã cũ — nên chạy lại mô phỏng.")

    if costly and usable:
        out.next_actions.append("Đối chiếu chi phí với doanh thu ước tính trước khi chốt.")
    if violations:
        out.next_actions.append("Xem lý do vi phạm ràng buộc ở từng phương án trước khi đề xuất.")

    if sim_id:
        out.grounded_refs.append(sim_id)
    if not options:
        out.risks.append("Mô phỏng không sinh được phương án nào.")
    return out


# ── Cứu ca (Shift Rescue) ───────────────────────────────────────────────────


def brief_shift_rescue(
    *,
    case: dict[str, Any] | None,
    shifts: list[dict[str, Any]] | None = None,
) -> PageFacts:
    """Tổng hợp `/quanverse/shift-rescue` — ai bù được, ai bị loại vì sao."""
    out = PageFacts(page=QuanversePage.SHIFT_RESCUE)
    shifts = shifts or []

    if not case:
        out.headline = "Chưa có ca nào đang cần cứu"
        out.metrics.append(_metric("shifts", "Ca đang phân người", float(len(shifts)), unit="ca"))
        out.next_actions.append("Báo vắng một ca để hệ thống tìm người bù.")
        if shifts:
            for s in shifts[:5]:
                out.facts.append(
                    f"Ca {s.get('shift_id')} ({s.get('thu')} {s.get('khung')}) có "
                    f"{len(s.get('assigned') or [])} người."
                )
                out.grounded_refs.append(str(s.get("shift_id") or ""))
        return out

    status = str(case.get("status") or "reported")
    candidates = list(case.get("candidates") or [])
    blocked = list(case.get("blocked") or [])
    invited = list(case.get("invited") or [])
    case_id = str(case.get("case_id") or status)

    out.headline = f"Ca {case.get('shift_id')} · {len(candidates)} người bù được đề xuất"
    out.metrics.append(_metric("candidates", "Người bù đủ điều kiện", float(len(candidates)),
                               unit="người", tone="ok" if candidates else "warn"))
    out.metrics.append(_metric("blocked", "Bị loại", float(len(blocked)), unit="người",
                               tone="warn" if blocked else "default"))
    out.metrics.append(_metric("invited", "Đã mời", float(len(invited)), unit="người"))

    out.facts.append(f"Trạng thái hồ sơ: {status}.")
    out.grounded_refs.append(case_id)

    safe = [c for c in candidates if c.get("safe")]
    out.metrics.append(_metric("safe", "An toàn về công bằng", float(len(safe)), unit="người",
                               tone="ok" if safe else "warn"))

    for c in safe[:5]:
        name = str(c.get("nv_ten") or c.get("nv_id") or "")
        coverage = c.get("skill_coverage")
        cov_txt = f"{round(coverage * 100)}% kỹ năng" if isinstance(coverage, (int, float)) else "chưa rõ kỹ năng"
        out.facts.append(
            f"{name}: {cov_txt}, thêm {c.get('added_hours')} giờ, "
            f"lệch công bằng {c.get('fairness_delta')}."
        )
        out.grounded_refs.append(str(c.get("candidate_id") or c.get("nv_id") or name))

    for b in blocked[:5]:
        name = str(b.get("nv_ten") or b.get("nv_id") or "")
        why = ", ".join(str(x) for x in (b.get("reason_blocks") or [])) or "không rõ lý do"
        out.risks.append(f"{name} bị loại: {why}")
        ref = str(b.get("candidate_id") or b.get("nv_id") or "")
        if ref:
            out.grounded_refs.append(ref)

    if not candidates:
        out.risks.append("Không có ai đủ điều kiện bù ca này — cần quản lý can thiệp.")
        out.next_actions.append("Cân nhắc đổi khung ca hoặc nhờ chủ quán duyệt ngoại lệ.")

    escalation = case.get("escalation")
    if escalation:
        out.risks.append(f"Cần leo thang: {escalation}")

    if candidates and status in {"candidates_ready", "reported", "resolving"}:
        out.next_actions.append("Gửi lời mời cho người phù hợp nhất rồi chờ họ phản hồi.")
    if status == "responded":
        out.next_actions.append("Người được mời đã phản hồi — chốt phương án bù ca.")
    return out


# ── Luật của quán (Rules) ───────────────────────────────────────────────────


def brief_rules(
    *,
    candidates: list[dict[str, Any]],
    sources: list[str] | None = None,
) -> PageFacts:
    """Tổng hợp `/quanverse/rules` — có luật nào đáng ban hành, độ tin cậy ra sao."""
    out = PageFacts(page=QuanversePage.RULES)
    candidates = candidates or []

    by_status: dict[str, int] = {}
    for c in candidates:
        by_status[str(c.get("status") or "unknown")] = by_status.get(str(c.get("status") or "unknown"), 0) + 1

    ready = [c for c in candidates if str(c.get("status")) in {"de_xuat", "candidate", "ready"}]
    out.headline = (
        f"{len(candidates)} quyết định lặp lại được phát hiện · {len(ready)} chờ ban hành"
    )

    out.metrics.append(_metric("candidates", "Ứng viên luật", float(len(candidates)), unit="luật"))
    out.metrics.append(_metric("ready", "Chờ ban hành", float(len(ready)), unit="luật",
                               tone="warn" if ready else "default"))
    if sources:
        out.metrics.append(_metric("sources", "Nguồn bằng chứng", float(len(sources)), unit="nguồn"))
        out.grounded_refs.extend(str(s) for s in sources)

    for c in candidates[:8]:
        sentence = str(c.get("sentence") or "").strip()
        if not sentence:
            continue
        conf = c.get("confidence")
        conf_txt = f"độ tin cậy {round(float(conf) * 100)}%" if isinstance(conf, (int, float)) else "chưa chấm độ tin cậy"
        out.facts.append(f"{sentence} ({conf_txt}, trạng thái {c.get('status')}).")
        out.grounded_refs.append(str(c.get("candidate_id") or ""))
        if isinstance(conf, (int, float)) and conf < 0.5:
            out.risks.append(f"Luật \"{sentence}\" có độ tin cậy thấp — cần thêm bằng chứng.")

    for status, count in sorted(by_status.items()):
        if status not in {"de_xuat", "candidate", "ready"}:
            out.facts.append(f"{count} luật ở trạng thái {status}.")

    if ready:
        out.next_actions.append("Chạy thử cô lập (shadow test) trước khi ban hành luật.")
    if not candidates:
        out.risks.append("Chưa phát hiện quyết định lặp nào — cần thêm dữ liệu ca.")
        out.next_actions.append("Ghi thêm quyết định đổi ca để hệ thống học được luật.")
    return out


# ── Ký ức quán (Spatial Memory) ─────────────────────────────────────────────


def brief_spatial_memory(
    *,
    anchors: list[dict[str, Any]],
    memory_counts: dict[str, int] | None,
    selected_anchor: dict[str, Any] | None = None,
) -> PageFacts:
    """Tổng hợp `/quanverse/spatial-memory` — neo nào có ký ức, neo nào còn trống."""
    out = PageFacts(page=QuanversePage.SPATIAL_MEMORY)
    memory_counts = memory_counts or {}
    total = sum(memory_counts.values())
    with_memory = [a for a in anchors if memory_counts.get(str(a.get("anchor_id")))]

    out.headline = f"{len(anchors)} neo · {total} ký ức đã xác nhận"
    out.metrics.append(_metric("anchors", "Neo không gian", float(len(anchors)), unit="neo"))
    out.metrics.append(_metric("memories", "Ký ức đã xác nhận", float(total), unit="ký ức",
                               tone="ok" if total else "warn"))
    out.metrics.append(
        _metric("empty_anchors", "Neo chưa có ký ức", float(len(anchors) - len(with_memory)),
                unit="neo", tone="warn" if len(anchors) - len(with_memory) else "ok")
    )

    for a in anchors[:10]:
        aid = str(a.get("anchor_id") or "")
        count = memory_counts.get(aid, 0)
        label = str(a.get("label") or a.get("khu_vuc") or aid)
        if count:
            out.facts.append(f"{label}: {count} ký ức đã xác nhận.")
        else:
            out.facts.append(f"{label}: chưa có ký ức nào.")
        if aid:
            out.grounded_refs.append(aid)

    empty = [a for a in anchors if not memory_counts.get(str(a.get("anchor_id")))]
    if empty:
        names = ", ".join(str(a.get("label") or a.get("anchor_id")) for a in empty[:4])
        out.next_actions.append(f"Ghi nhớ điều đáng lưu cho khu vực còn trống: {names}.")

    if selected_anchor:
        ref = str(selected_anchor.get("anchor_id") or "")
        if ref:
            out.grounded_refs.append(ref)
        out.facts.append(
            f"Đang xem neo {selected_anchor.get('label') or ref} "
            f"({memory_counts.get(ref, 0)} ký ức đã xác nhận)."
        )

    if not anchors:
        out.risks.append("Chưa đọc được neo nào của quán.")
    if not total:
        out.risks.append("Chưa có ký ức nào được xác nhận — trợ lý sẽ không dám kết luận gì.")
    return out


# ── Điểm vào duy nhất ───────────────────────────────────────────────────────

# Mỗi builder có chữ ký riêng (kwargs khác nhau) nên dict phải khai `Callable`
# với `**kwargs`: nếu không, mypy suy ra union các hàm và báo "Cannot call
# function of unknown type" khi gọi. Router chịu trách nhiệm truyền ĐÚNG payload
# cho từng trang; `build_brief` chỉ điều phối.
_Builder = Callable[..., PageFacts]

_BUILDERS: dict[QuanversePage, _Builder] = {
    QuanversePage.LIVING_MAP: brief_living_map,
    QuanversePage.WAR_ROOM: brief_war_room,
    QuanversePage.SHIFT_RESCUE: brief_shift_rescue,
    QuanversePage.RULES: brief_rules,
    QuanversePage.SPATIAL_MEMORY: brief_spatial_memory,
}


def build_brief(page: QuanversePage, **payload: Any) -> QuanverseBrief:
    """Dựng `QuanverseBrief` cho một trang — điểm vào DUY NHẤT.

    Router chỉ đọc dữ liệu thô rồi gọi hàm này; nhờ vậy bản tóm tắt ở UI và ngữ
    cảnh đưa cho LLM là CÙNG một khối, không thể lệch số (cùng khuôn với
    `ag_waste.tinh_tu_nguon`).
    """
    builder = _BUILDERS.get(page)
    if builder is None:
        return QuanverseBrief(
            page=page,
            headline="Chưa hỗ trợ tổng hợp cho trang này",
            risks=["Trang này chưa có bộ tổng hợp."],
        )
    facts = builder(**payload)
    return QuanverseBrief(
        page=facts.page,
        headline=facts.headline or "Chưa có dữ liệu",
        facts=facts.facts,
        metrics=facts.metrics,
        risks=facts.risks,
        next_actions=facts.next_actions,
        grounded_refs=facts.grounded_refs,
        data_quality=facts.data_quality,
    )
