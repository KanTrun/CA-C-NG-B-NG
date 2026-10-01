# mypy: disable-error-code="no-untyped-def,no-untyped-call,type-arg,no-any-return,unused-ignore"
"""Property-based test cho Math Layer AG-PRICING (plan 260913-1455 mục 4.6).

Plan mục 4.6 **[ĐỀ XUẤT MỚI]**: dùng `hypothesis` sinh ngẫu nhiên hàng nghìn tổ
hợp giá/rating, kiểm tra BẤT BIẾN (invariants) thay vì chỉ test vài ca cố định.

Bốn bất biến bắt buộc theo plan:
1. P25 <= P50 <= P75 luôn đúng.
2. WR luôn nằm trong [min(R, 4.2), max(R, 4.2)].
3. AMBI luôn nằm trong [min(Core, Substitutes), max(Core, Substitutes)] theo trung vị.
4. [v2.1] `sweet_spot_*_display` sau làm tròn luôn lệch `sweet_spot_*_raw`
   trong biên độ ± step/2.

ADR-002: hypothesis sinh dữ liệu bằng PRNG có seed nội bộ của nó — mỗi bất biến
được kiểm trên hàng trăm ca, và MỌI ca đều phải đúng. Không network, không LLM.

Toàn bộ giá/rating ở đây là DỮ LIỆU MÔ PHỎNG do hypothesis sinh, không phải số
liệu thu thập thật từ ShopeeFood/Google Maps.
"""

from __future__ import annotations

import math

import pytest
from ca_agents.ag_pricing.math_layer import (
    check_cost_plus_warning,
    competitive_intensity,
    compute_ambi,
    compute_percentile_stats,
    compute_sweet_spot,
    distance_decay_weight,
    is_valid_price,
    min_viable_price,
    passes_gates,
    percentile_linear,
    price_zone,
    risk_zone_threshold,
    round_to_market_convention,
    sample_weight,
    weighted_rating,
)
from ca_contracts.catchment_survey_v2 import StoreRecord

try:
    from hypothesis import given, settings
    from hypothesis import strategies as st
except ImportError:
    pytest.skip("hypothesis is required for property-based tests", allow_module_level=True)

from pytest import approx

# Chậm (~5000+ examples hypothesis, CPU-bound) — chạy ở job unit-slow.
pytestmark = pytest.mark.slow

# Sai số chấp nhận được do số học dấu phẩy động (không phải sai số nghiệp vụ).
EPS = 1e-6

# Giá F&B hợp lý để hypothesis không phí mẫu vào vùng vô nghĩa (VNĐ).
gia_vnd = st.floats(min_value=0.0, max_value=5_000_000.0, allow_nan=False, allow_infinity=False)
gia_duong = st.floats(min_value=1.0, max_value=5_000_000.0, allow_nan=False, allow_infinity=False)
danh_gia = st.floats(min_value=0.0, max_value=5.0, allow_nan=False, allow_infinity=False)
so_review = st.integers(min_value=0, max_value=1_000_000)
trong_so = st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)
ban_kinh = st.floats(min_value=0.0, max_value=50.0, allow_nan=False, allow_infinity=False)
boi_so = st.sampled_from([(1000, 5000, 5000), (1000, 1000, 1000), (5000, 5000, 5000), (500, 2000, 1000)])
nhom_lam_tron = st.sampled_from(["beverage", "mon_chinh", "mon_khac", ""])


def _store(**overrides: object) -> StoreRecord:
    base: dict[str, object] = {
        "store_id": "res_prop",
        "name": "Quán mô phỏng",
        "lat": 10.762622,
        "lng": 106.660172,
        "review_count": 320,
        "rating": 4.6,
        "weighted_rating": 4.55,
        "passed_gate1": True,
        "passed_gate2": True,
    }
    base.update(overrides)
    return StoreRecord(**base)  # type: ignore[arg-type]


# ── Bất biến 1 (plan mục 4.6): P25 <= P50 <= P75 ─────────────────────────────


@settings(max_examples=300, deadline=None)
@given(st.lists(gia_vnd, min_size=1, max_size=60))
def test_bat_bien_1_phan_vi_luon_don_dieu(values: list[float]) -> None:
    """P25 <= P50 <= P75 với MỌI rổ giá, kể cả rổ có giá trùng nhau."""
    p25 = percentile_linear(values, 25.0)
    p50 = percentile_linear(values, 50.0)
    p75 = percentile_linear(values, 75.0)

    assert p25 <= p50 <= p75
    # Phân vị không được vượt ra ngoài khoảng dữ liệu thật
    assert min(values) - EPS <= p25
    assert p75 <= max(values) + EPS
    assert math.isfinite(p25) and math.isfinite(p50) and math.isfinite(p75)


@settings(max_examples=200, deadline=None)
@given(st.lists(gia_vnd, min_size=1, max_size=40), st.lists(st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False), min_size=2, max_size=5))
def test_bat_bien_1_phan_vi_don_dieu_theo_q(values: list[float], qs: list[float]) -> None:
    """q tăng → phân vị không giảm. Tổng quát hoá bất biến 1 của plan."""
    ket_qua = [percentile_linear(values, q) for q in sorted(qs)]
    assert ket_qua == sorted(ket_qua)


@settings(max_examples=200, deadline=None)
@given(st.lists(gia_vnd, min_size=0, max_size=60), st.integers(min_value=1, max_value=20))
def test_bat_bien_insufficient_data_khop_dung_dieu_kien(values: list[float], min_n: int) -> None:
    """Cờ `insufficient_data` phải đúng bằng điều kiện n < min_sample_size (plan mục 4.1)."""
    stats = compute_percentile_stats(values, min_sample_size=min_n)

    assert stats.sample_size == len(values)
    assert stats.insufficient_data is (len(values) < min_n)
    if stats.insufficient_data:
        # Không đủ mẫu → KHÔNG được trả phân vị (tránh hiển thị số không đáng tin)
        assert (stats.p25, stats.p50, stats.p75) == (0.0, 0.0, 0.0)
    else:
        assert stats.p25 <= stats.p50 <= stats.p75


# ── Bất biến 2 (plan mục 4.6): WR ∈ [min(R, 4.2), max(R, 4.2)] ──────────────


@settings(max_examples=400, deadline=None)
@given(so_review, danh_gia, st.integers(min_value=0, max_value=500), danh_gia)
def test_bat_bien_2_wr_nam_giua_rating_va_prior(v: int, r: float, m: int, c: float) -> None:
    """WR là tổ hợp lồi của R và C → luôn nằm trong [min(R,C), max(R,C)].

    Plan mục 4.6 phát biểu với C = 4.2; ở đây tổng quát cho mọi prior C.
    """
    wr = weighted_rating(v, r, m=m, prior_c=c)

    assert math.isfinite(wr)
    assert min(r, c) - EPS <= wr <= max(r, c) + EPS


@settings(max_examples=300, deadline=None)
@given(so_review, danh_gia)
def test_bat_bien_2_wr_voi_prior_chuan_4_2(v: int, r: float) -> None:
    """Đúng chữ bất biến trong plan: prior C = 4.2, m = 50."""
    wr = weighted_rating(v, r, m=50, prior_c=4.2)

    assert min(r, 4.2) - EPS <= wr <= max(r, 4.2) + EPS
    assert 0.0 - EPS <= wr <= 5.0 + EPS


@settings(max_examples=200, deadline=None)
@given(so_review, danh_gia, st.integers(min_value=1, max_value=500))
def test_bat_bien_2_wr_tien_ve_rating_khi_mau_lon(v: int, r: float, m: int) -> None:
    """Thêm một lượt review không được đẩy WR ra xa R hơn (tính đơn điệu)."""
    wr_v = weighted_rating(v, r, m=m, prior_c=4.2)
    wr_v1 = weighted_rating(v + 1, r, m=m, prior_c=4.2)

    if r >= 4.2:
        assert wr_v1 >= wr_v - EPS
    else:
        assert wr_v1 <= wr_v + EPS


# ── Bất biến 3 (plan mục 4.6): AMBI ∈ [min, max] theo trung vị ───────────────


@settings(max_examples=300, deadline=None)
@given(gia_vnd, st.lists(gia_vnd, min_size=1, max_size=10), trong_so)
def test_bat_bien_3_ambi_nam_trong_khoang_trung_vi(
    core_median: float, sub_medians: list[float], w_core: float
) -> None:
    """AMBI là tổ hợp lồi của Median(Core) và mean(Median Substitutes).

    Với w_core + w_subs = 1 và cả hai >= 0 → AMBI luôn nằm trong
    [min(core, subs), max(core, subs)].
    """
    w_subs = 1.0 - w_core
    ambi = compute_ambi(core_median, sub_medians, w_core=w_core, w_subs=w_subs)

    lo = min([core_median, *sub_medians])
    hi = max([core_median, *sub_medians])

    assert math.isfinite(ambi)
    assert lo - EPS <= ambi <= hi + EPS


@settings(max_examples=200, deadline=None)
@given(gia_vnd, st.lists(gia_vnd, min_size=1, max_size=10))
def test_bat_bien_3_ambi_voi_trong_so_chuan_0_5(core_median: float, sub_medians: list[float]) -> None:
    """Đúng chữ công thức plan mục 1.3: 0.5·Core + 0.5·mean(Subs)."""
    ambi = compute_ambi(core_median, sub_medians, w_core=0.5, w_subs=0.5)
    mong_doi = 0.5 * core_median + 0.5 * (sum(sub_medians) / len(sub_medians))

    assert ambi == approx(mong_doi, rel=1e-9, abs=1e-6)
    lo = min([core_median, *sub_medians])
    hi = max([core_median, *sub_medians])
    assert lo - EPS <= ambi <= hi + EPS


@settings(max_examples=200, deadline=None)
@given(gia_vnd, st.lists(gia_vnd, min_size=1, max_size=10))
def test_bat_bien_3_ambi_khong_co_substitute_thi_bang_core(core_median: float, sub_medians: list[float]) -> None:
    """Không có nhóm thay thế → AMBI = Median(Core), không chia 0, không NaN."""
    ambi = compute_ambi(core_median, [], w_core=0.5, w_subs=0.5)
    assert ambi == approx(core_median, rel=1e-9, abs=1e-6)
    assert math.isfinite(ambi)
    # sub_medians không được âm thầm ảnh hưởng khi truyền rỗng
    assert len(sub_medians) >= 1


@settings(max_examples=200, deadline=None)
@given(gia_vnd, trong_so)
def test_bat_bien_3_vung_rui_ro_luon_lon_hon_hoac_bang_ambi(ambi: float, he_so: float) -> None:
    """Ngưỡng vùng rủi ro = AMBI × hệ số, với hệ số >= 1 thì không thấp hơn AMBI."""
    if he_so < 1.0:
        return
    assert risk_zone_threshold(ambi, he_so=he_so) >= ambi - EPS


# ── Bất biến 4 (plan mục 4.6, v2.1): display lệch raw trong ± step/2 ─────────


@settings(max_examples=400, deadline=None)
@given(gia_vnd, nhom_lam_tron, boi_so)
def test_bat_bien_4_lam_tron_khong_lech_qua_nua_buoc(
    price: float, category_group: str, steps: tuple[int, int, int]
) -> None:
    """Plan mục 4.6 [v2.1]: |display − raw| <= step/2."""
    display = round_to_market_convention(price, category_group, steps)

    beverage_step, main_step, default_step = steps
    if category_group == "beverage":
        step = beverage_step
    elif category_group == "mon_chinh":
        step = main_step
    else:
        step = default_step

    assert isinstance(display, int)
    assert display % step == 0 or abs(display % step - step) < EPS
    assert abs(display - price) <= step / 2 + EPS
    assert display >= 0


@settings(max_examples=300, deadline=None)
@given(
    st.lists(gia_vnd, min_size=0, max_size=40),
    gia_vnd,
    nhom_lam_tron,
    boi_so,
)
def test_bat_bien_4_sweet_spot_display_lech_raw_trong_nua_buoc(
    prices: list[float], ambi: float, category_group: str, steps: tuple[int, int, int]
) -> None:
    """Bất biến 4 áp trên cả cặp low/high của Sweet Spot (plan mục 4.6 [v2.1])."""
    zone = compute_sweet_spot(
        prices, ambi, p_low=40.0, p_high=60.0,
        category_group=category_group, rounding_steps=steps,
    )

    beverage_step, main_step, default_step = steps
    if category_group == "beverage":
        step = beverage_step
    elif category_group == "mon_chinh":
        step = main_step
    else:
        step = default_step

    assert abs(zone.low_display - zone.low_raw) <= step / 2 + EPS
    assert abs(zone.high_display - zone.high_raw) <= step / 2 + EPS
    # _raw không bao giờ bị ghi đè bởi giá làm tròn (plan mục 1.5.7)
    assert zone.low_raw == approx(percentile_linear(prices, 40.0), rel=1e-9, abs=1e-6)


@settings(max_examples=300, deadline=None)
@given(st.lists(gia_vnd, min_size=0, max_size=40), gia_vnd, nhom_lam_tron, boi_so)
def test_bat_bien_sweet_spot_co_inverted_dung_dieu_kien(
    prices: list[float], ambi: float, category_group: str, steps: tuple[int, int, int]
) -> None:
    """Cờ `inverted` phải đúng bằng điều kiện high_raw < low_raw.

    GIẢ ĐỊNH NGOÀI PLAN: khi AMBI < P_low, công thức plan cho ra khoảng giá lộn.
    Math Layer KHÔNG tự kẹp (kẹp sẽ phá bất biến `high_raw = min(AMBI, P60)`) mà
    chỉ gắn cờ để caller cảnh báo — xem docstring `compute_sweet_spot`.
    """
    zone = compute_sweet_spot(
        prices, ambi, p_low=40.0, p_high=60.0,
        category_group=category_group, rounding_steps=steps,
    )

    assert math.isfinite(zone.low_raw) and math.isfinite(zone.high_raw)
    assert zone.inverted is (zone.high_raw < zone.low_raw)
    if not zone.inverted:
        assert zone.low_raw <= zone.high_raw + EPS
        assert zone.low_display <= zone.high_display


@settings(max_examples=200, deadline=None)
@given(st.lists(gia_vnd, min_size=1, max_size=40), gia_vnd)
def test_bat_bien_sweet_spot_high_khong_vuot_ambi(prices: list[float], ambi: float) -> None:
    """Plan mục 4.4: high_raw = min(AMBI, P60) → không bao giờ vượt AMBI."""
    zone = compute_sweet_spot(prices, ambi, p_low=40.0, p_high=60.0,
                              category_group="mon_chinh", rounding_steps=(1000, 5000, 5000))
    assert zone.high_raw <= ambi + EPS


# ── Bất biến bổ sung: các hàm còn lại của Math Layer ─────────────────────────


@settings(max_examples=300, deadline=None)
@given(st.integers(min_value=-1000, max_value=100_000), ban_kinh)
def test_bat_bien_competitive_intensity_khong_am_khong_nan(count: int, radius: float) -> None:
    """Plan mục 4.5: CI >= 0, hữu hạn, và = 0 khi diện tích không dương."""
    ci = competitive_intensity(count, radius, pi=3.14159)

    assert math.isfinite(ci)
    assert ci >= 0.0
    if radius <= 0.0:
        assert ci == 0.0
    if count <= 0:
        assert ci == 0.0


@settings(max_examples=300, deadline=None)
@given(st.floats(min_value=-100.0, max_value=100.0, allow_nan=False, allow_infinity=False),
       st.floats(min_value=0.0, max_value=5.0, allow_nan=False, allow_infinity=False))
def test_bat_bien_distance_decay_nam_trong_0_1(distance: float, alpha: float) -> None:
    """W = 1/(1+alpha·d) phải luôn trong (0, 1] với d >= 0."""
    w = distance_decay_weight(distance, alpha=alpha)
    assert math.isfinite(w)
    assert 0.0 < w <= 1.0 + EPS


@settings(max_examples=300, deadline=None)
@given(so_review, danh_gia, st.booleans(), st.booleans(), st.booleans(), trong_so)
def test_bat_bien_sample_weight_chi_nhan_ba_gia_tri(
    review_count: int,
    rating: float,
    has_badge: bool,
    gate1: bool,
    gate2: bool,
    factor: float,
) -> None:
    """Trọng số mẫu ∈ {0, factor, 1} — không có giá trị lơ lửng nào khác."""
    store = _store(
        review_count=review_count,
        rating=rating,
        passed_gate1=gate1,
        passed_gate2=gate2,
        low_confidence=has_badge,
    )
    w = sample_weight(store, low_confidence_factor=factor)

    assert w in (0.0, factor, 1.0)
    if not (gate1 and gate2):
        assert w == 0.0


@settings(max_examples=300, deadline=None)
@given(so_review, danh_gia, danh_gia, st.booleans(),
       st.integers(min_value=0, max_value=200),
       st.floats(min_value=0.0, max_value=5.0, allow_nan=False, allow_infinity=False),
       st.floats(min_value=0.0, max_value=5.0, allow_nan=False, allow_infinity=False))
def test_bat_bien_passes_gates_dung_chu_cong_thuc(
    review_count: int,
    rating: float,
    wr: float,
    has_badge: bool,
    min_v: int,
    min_r: float,
    min_wr: float,
) -> None:
    """Kết quả phải khớp ĐÚNG biểu thức boolean trong plan mục 4.2."""
    store = _store(
        review_count=review_count, rating=rating, weighted_rating=wr,
        has_favorite_badge=has_badge,
    )
    gate1, gate2 = passes_gates(store, min_v=min_v, min_r=min_r, min_wr=min_wr)

    assert gate1 == (review_count >= min_v or has_badge)
    assert gate2 == (rating >= min_r and wr >= min_wr)
    assert isinstance(gate1, bool) and isinstance(gate2, bool)


@settings(max_examples=300, deadline=None)
@given(st.integers(min_value=0, max_value=1_000_000),
       st.floats(min_value=0.01, max_value=0.99, allow_nan=False, allow_infinity=False))
def test_bat_bien_min_viable_price_khong_thap_hon_cogs(cogs: int, margin: float) -> None:
    """Giá hoà vốn mục tiêu phải >= COGS (vì margin ∈ (0,1))."""
    mvp = min_viable_price(cogs, target_margin_ratio=margin)
    assert math.isfinite(mvp)
    assert mvp >= cogs - EPS


@settings(max_examples=200, deadline=None)
@given(gia_vnd, st.one_of(st.none(), gia_vnd))
def test_bat_bien_cost_plus_warning_chi_true_khi_tran_thap_hon_hoa_von(
    high_raw: float, min_viable: float | None
) -> None:
    warning = check_cost_plus_warning(high_raw, min_viable)
    assert isinstance(warning, bool)
    assert warning is (min_viable is not None and high_raw < min_viable)


@settings(max_examples=300, deadline=None)
@given(gia_vnd, gia_vnd, st.floats(min_value=1.0, max_value=3.0, allow_nan=False, allow_infinity=False))
def test_bat_bien_price_zone_tra_ve_dung_ba_ma(price: float, ambi: float, he_so: float) -> None:
    """Ba vùng giá phải phủ kín trục số, không chồng lấn, không sót."""
    zone = price_zone(price, ambi, he_so=he_so)
    assert zone in {"an_toan", "canh_bao", "rui_ro"}

    nguong_rui_ro = risk_zone_threshold(ambi, he_so=he_so)
    if price <= ambi:
        assert zone == "an_toan"
    elif price > nguong_rui_ro:
        assert zone == "rui_ro"
    else:
        assert zone == "canh_bao"


@settings(max_examples=300, deadline=None)
@given(st.floats(allow_nan=True, allow_infinity=True))
def test_bat_bien_is_valid_price_khong_bao_gio_true_voi_nan_hay_inf(price: float) -> None:
    """NaN/inf không bao giờ được coi là giá hợp lệ — nếu lọt vào sẽ phá phân vị."""
    if math.isnan(price) or math.isinf(price):
        assert is_valid_price(price) is False
    else:
        assert is_valid_price(price) == (5000 <= price <= 2_000_000)
