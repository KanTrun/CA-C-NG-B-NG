"""Redesign nền ảnh — GIỮ NGUYÊN bao bì sản phẩm gốc, AI chỉ vẽ lại nền.

Nguyên tắc bất biến: pixel của sản phẩm (ly/chai/lọ/bình/hộp/túi…) lấy 100% từ
ảnh gốc (không qua model vẽ lại), nền mới sinh bằng text-to-image rồi composite
cục bộ bằng Pillow.

Ba nhóm vấn đề đã sửa so với bản đầu:

1. **Biến dạng / lem viền.**  Nền sinh ra bị ``resize`` thẳng về khung đích nên
   méo tỷ lệ; ly ``resize`` ở chế độ RGBA không nhân trước alpha nên màu nền cũ
   lem vào rìa trong suốt; rìa mask còn giữ lớp pixel pha giữa ly và nền cũ nên
   hiện viền sáng quanh ly.  Bản này: nền cắt kiểu ``cover`` (giữ tỷ lệ, crop
   dư), ly scale theo tỷ lệ **đồng nhất** và đặt theo đường chân đế, alpha được
   nhân trước khi resize, và rìa mask được co + siết ngưỡng để bỏ quầng nền cũ.

2. **Ảnh lỗi.**  Provider cộng đồng trả ảnh rác (một màu, quá tối/sáng, gần
   trùng nền cũ) mà vẫn được chấp nhận.  Bản này kiểm tra nền TRƯỚC khi ghép và
   thử lại với seed khác; hết lượt thì trả lỗi ``bad_background`` kèm gợi ý thay
   vì ghép ra ảnh hỏng.

3. **Chậm.**  Bản cũ gọi tuần tự vision-bbox → LLM viết lại prompt → sinh nền.
   Bản này: vision chạy **song song** với sinh nền, prompt nền lấy từ phong cách
   thiết kế (tất định, không gọi LLM) khi quán có brand kit, và có cache theo
   (prompt, kích thước, seed) để bấm lại không tốn thêm thời gian.

Fail-closed: không tách được chủ thể, hoặc nền không đạt kiểm tra → trả lỗi rõ
ràng, không bịa ảnh.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from typing import cast

import numpy as np
from PIL import Image, ImageFilter
from scipy import ndimage

from ca_agents.image_gen import (
    ASPECT_DIMS,
    ImageGenResult,
    _cf_image_any_field,
    _cf_ready,
    _pollinations_image,
)
from ca_agents.llm import complete
from ca_agents.menu_style import MenuStyle

logger = logging.getLogger(__name__)

# Ảnh hạ độ phân giải khi tính mask (nhanh, đủ chính xác cho canvas ~1344px).
# 640px là điểm cân bằng: nhỏ hơn thì rìa ly răng cưa, lớn hơn thì flood-fill chậm.
_MASK_MAX_DIM = 640
# Model Cloudflare dùng để sinh NỀN (khác model sinh ảnh hoàn chỉnh).
#
# Nền bị phủ bởi hiệu ứng (hào quang, vignette, bóng đổ) và chỉ chiếm phần rìa
# khung, nên không cần model đắt: ``flux-2-klein-4b`` rẻ và nhanh hơn
# ``flux-2-dev`` mà chất lượng nền không khác biệt khi mắt người nhìn ảnh cuối.
# Tiết kiệm neurons/ngày cũng cho phép quán tạo được nhiều ảnh hơn.
_CF_BG_MODEL = "@cf/black-forest-labs/flux-2-klein-4b"
# Ngưỡng khác biệt màu mỗi kênh khi lan vùng nền từ biên ảnh.
_BG_TOLERANCE_PER_CHANNEL = 28.0
# Bán kính (khoảng cách màu euclide RGB) coi một pixel là "cùng màu nền".
# Pixel xa MỌI cụm màu nền không bao giờ được coi là nền — chặn flood-fill rò qua
# vùng bokeh chuyển sắc mà vẫn giữ được ly nước có màu khác nền.
#
# 80 là mức đã dùng từ trước; giữ nguyên vì các test đo chất lượng tách chủ thể
# (tỷ lệ chủ thể, giữ đúng pixel ly) đều dựa trên giá trị này.
_BG_GLOBAL_RADIUS = 80.0
# Số CỤM màu nền lấy từ viền ảnh (k-means nhỏ trên pixel biên).
#
# Vì sao cần nhiều hơn 1: bản cũ so mọi pixel với ĐÚNG một màu nền trung bình của
# biên. Ảnh có biên nhiều màu (nền xanh đậm phía trên + khay/bàn sáng phía dưới)
# cho ra màu trung bình nằm GIỮA hai màu, nên cả hai vùng đều bị coi là "xa nền"
# → mask giữ luôn cả khay/bàn làm "chủ thể", và vệt nền cũ lộ ra trong ảnh ghép.
# Lấy nhiều cụm thì mỗi vùng nền khớp với cụm gần nó nhất.
_BG_CLUSTERS = 3
# Số vòng lặp k-means. 8 là đủ hội tụ cho vài trăm pixel biên; nhiều hơn không
# cải thiện kết quả mà tốn thời gian.
_BG_KMEANS_ITERS = 8
# Co mask vào bao nhiêu pixel (ở độ phân giải mask) để cắt lớp viền nền cũ.
# Ảnh gốc luôn còn 1–2px quầng màu nền cũ ở rìa ly; không co thì quầng đó nằm
# đè lên nền mới và tạo viền sáng quanh ly khi đổi sang nền tối.
_MASK_ERODE_PX = 1
# Siết ngưỡng alpha sau khi làm mờ: phần đuôi feather (dưới ngưỡng này) là pixel
# pha giữa ly và nền cũ — đặt về 0 hoàn toàn thay vì để nửa trong suốt.
_MASK_FEATHER_FLOOR = 0.18

# ── Kiểm tra nền trước khi composite (chống "ảnh lỗi") ──────────────────────
# Nền một màu / gần một màu → vô nghĩa, ghép vào chỉ ra ảnh phẳng.
_BG_MIN_STD = 6.0
# Nền quá tối hoặc quá sáng đều làm ly mất tương phản.
_BG_MIN_MEAN = 12.0
_BG_MAX_MEAN = 246.0
# Khoảng cách màu euclide tối thiểu giữa nền mới và nền cũ. Dưới ngưỡng này coi
# như model bỏ qua prompt và trả lại chính khung nền cũ. Để rất thấp (2.5) vì
# nền cũ sáng và nền studio sáng có thể trùng màu trung bình một cách hợp lệ.
_BG_MIN_COLOR_DELTA = 2.5
# Số lần thử lại sinh nền với seed khác khi kiểm tra không đạt.
_BG_ATTEMPTS = 2

# ── Hiệu ứng thiết kế quanh ly (không sửa một pixel nào của ly) ─────────────
# Hào quang ấm: cường độ tối đa và bán kính tương đối so với chiều rộng ly.
_GLOW_ALPHA = 70
_GLOW_RADIUS_FACTOR = 0.62
# Vignette tối 4 góc.
_VIGNETTE_STRENGTH = 32.0
# Bóng đổ dưới ly.
_SHADOW_OPACITY = 0.45
# Ly chiếm tối đa bao nhiêu khung (rộng/cao). 0.78 rộng là ngưỡng còn chừa nền
# để ảnh đọc ra "ly trên nền" thay vì "ly dán kín khung".
_SUBJECT_WIDTH_RATIO = 0.78
_SUBJECT_HEIGHT_RATIO = 0.86
# Khoảng chừa phía dưới đáy ly (% chiều cao khung).
_BOTTOM_MARGIN_RATIO = 0.07

# Cache nền theo (prompt, w, h, seed, model) trong bộ nhớ tiến trình. Giữ tối đa
# 12 ảnh (~1.5MB mỗi ảnh) — đủ để bấm "tạo lại" hoặc đổi tỷ lệ mà không gọi mạng.
_BG_CACHE: dict[str, bytes] = {}
_BG_CACHE_MAX = 12


def _bg_cache_get(key: str) -> bytes | None:
    return _BG_CACHE.get(key)


def _bg_cache_put(key: str, blob: bytes) -> None:
    if len(_BG_CACHE) >= _BG_CACHE_MAX:
        # Xoá mục cũ nhất (dict giữ thứ tự chèn).
        _BG_CACHE.pop(next(iter(_BG_CACHE)), None)
    _BG_CACHE[key] = blob


def _bg_cache_key(prompt: str, width: int, height: int, seed: int | None) -> str:
    model = os.environ.get("POLLINATIONS_MODEL", "flux").strip() or "flux"
    raw = f"{prompt}|{width}x{height}|{seed}|{model}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


# Hậu tố an toàn: đảm bảo model nền KHÔNG vẽ thêm ly nước/đồ ăn/chữ vào ảnh nền.
# "no text" cần thiết vì model hay vẽ biển hiệu/menu chữ nhòe ở hậu cảnh.
_BG_NEGATION = (
    ", absolutely no drink, no beverage, no glass, no cup, no bottle, no mug, "
    "no straw, no spoon, no topping, no food, no hands, no people, no text, "
    "no logo, no watermark, empty scene, nothing on the surface, background only"
)

_BG_PROMPT_SYSTEM = """You rewrite an image-generation prompt so it describes ONLY the \
background scene (surface, setting, lighting, mood, camera style) of a cafe beverage photo. \
The drink itself will be removed and replaced by a real photo of the actual drink.
Rules:
1. Keep the style, lighting, color palette and lens/composition hints of the original prompt.
2. Describe the scene as if the drink was never there (empty table / counter / setting).
3. NEVER mention any drink, glass, cup, bottle, mug, straw, topping, fruit or food.
4. NEVER mention text, letters, numbers, logos, menus, signs or price tags.
Return JSON only: {"background_prompt_en": "..."}"""

_BBOX_SYSTEM = """You locate the single main liquid product container (a bottle, jar, \
jug, carton, pouch, can, glass or cup holding a drink) in a cafe photo. Return its \
tightest bounding box in normalized coordinates (0..1, origin at top-left, x right, \
y down). Include garnish, lid, cap, label and straw if attached.
Return JSON only: {"x1": 0.1, "y1": 0.1, "x2": 0.9, "y2": 0.9}"""

# Prompt nền dự phòng khi LLM lỗi — mô tả chung, không nhắc tới đồ uống.
_BG_FALLBACK = (
    "warm cozy modern cafe interior, rustic wooden table surface in foreground, "
    "soft golden hour bokeh lights in the distance, professional food photography "
    "backdrop, shallow depth of field"
)


def _border_clusters(border_px: np.ndarray, k: int, iters: int) -> np.ndarray:
    """Gom pixel viền ảnh thành ``k`` cụm màu (k-means nhỏ, thuần numpy).

    Vì sao không dùng màu trung bình: ảnh có biên nhiều màu (nền tối phía trên +
    khay sáng phía dưới) cho ra trung bình nằm giữa hai màu — cả hai vùng đều bị
    coi là "xa nền" nên bị giữ làm chủ thể, làm vệt nền cũ lộ ra khi ghép.

    Khởi tạo bằng cách LẤY MẪU ĐỀU trên pixel viền (deterministic, không random)
    để cùng một ảnh luôn cho cùng mask — cần cho test và cho việc bấm lại ra cùng
    kết quả khi cùng seed.

    Args:
        border_px: Mảng ``(n, 3)`` màu các pixel ở viền ảnh.
        k: Số cụm mong muốn.
        iters: Số vòng lặp.

    Returns:
        Mảng ``(k, 3)`` tâm cụm. ``k`` bị kẹp theo số pixel khả dụng.
    """
    n = border_px.shape[0]
    k = max(1, min(k, n))
    # Lấy mẫu đều: bước nhảy cố định để không phụ thuộc thứ tự pixel.
    idx = np.linspace(0, n - 1, k).astype(np.int64)
    centers = border_px[idx].astype(np.float32)

    for _ in range(max(1, iters)):
        # Khoảng cách mỗi pixel tới từng tâm: (n, k)
        dist = np.sqrt(((border_px[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2))
        labels = np.argmin(dist, axis=1)
        moved = False
        for i in range(k):
            members = border_px[labels == i]
            if members.shape[0] == 0:
                # Cụm rỗng: để nguyên tâm (không random) nhằm giữ tính tất định.
                continue
            new_center = members.mean(axis=0).astype(np.float32)
            if not np.allclose(new_center, centers[i], atol=0.5):
                moved = True
            centers[i] = new_center
        if not moved:
            break
    return centers


def _min_dist_to_centers(arr: np.ndarray, centers: np.ndarray) -> np.ndarray:
    """Khoảng cách màu euclide từ mỗi pixel tới CỤM GẦN NHẤT. Mảng ``(h, w)``."""
    h, w = arr.shape[:2]
    best = np.full((h, w), np.inf, dtype=np.float32)
    for center in centers:
        d = np.sqrt(((arr - center) ** 2).sum(axis=2))
        np.minimum(best, d, out=best)
    return best


def _grow_background(
    arr: np.ndarray,
    seed: np.ndarray,
    tol_per_channel: float,
    allowed: np.ndarray | None = None,
) -> np.ndarray:
    """Lan vùng nền từ các pixel biên (seed) theo độ tương đồng màu CỤC BỘ.

    BFS vector hóa theo frontier: mỗi bước chỉ xét pixel kề frontier, nạp vào
    nền nếu màu của nó gần với MỘT pixel nền kề bên (tổng lệch 3 kênh < ngưỡng).
    ``allowed`` (tùy chọn): bộ lọc TOÀN CỤC — pixel chỉ được coi là nền nếu nằm
    trong tập cho phép. Cần vì flood-fill thuần local bị "rò" qua nền chuyển sắc
    nhẹ (bokeh): chuỗi bước nhỏ tích lũy thành khoảng cách lớn.
    """
    threshold = tol_per_channel * 3.0
    h, w = arr.shape[:2]
    bg = seed.copy()
    ys, xs = np.nonzero(bg)
    frontier = np.stack([ys, xs], axis=1)
    offsets = ((1, 0), (-1, 0), (0, 1), (0, -1))

    while frontier.shape[0]:
        # Mọi pixel chưa thuộc nền và kề một pixel frontier.
        cand_y = np.concatenate([frontier[:, 0] + o[0] for o in offsets])
        cand_x = np.concatenate([frontier[:, 1] + o[1] for o in offsets])
        inb = (cand_y >= 0) & (cand_y < h) & (cand_x >= 0) & (cand_x < w)
        cand_y, cand_x = cand_y[inb], cand_x[inb]
        fresh = ~bg[cand_y, cand_x]
        cand_y, cand_x = cand_y[fresh], cand_x[fresh]
        if cand_y.size == 0:
            break
        if allowed is not None:
            keep = allowed[cand_y, cand_x]
            cand_y, cand_x = cand_y[keep], cand_x[keep]
            if cand_y.size == 0:
                break

        # Lệch màu tới pixel nền gần nhất trong 4 neighbor.
        dists = np.full(cand_y.shape, np.inf)
        for dy, dx in offsets:
            py, px = cand_y + dy, cand_x + dx
            ok = (py >= 0) & (py < h) & (px >= 0) & (px < w) & bg[py.clip(0, h - 1), px.clip(0, w - 1)]
            d = np.abs(arr[cand_y, cand_x] - arr[py.clip(0, h - 1), px.clip(0, w - 1)]).sum(axis=1)
            dists = np.where(ok, np.minimum(dists, d), dists)
        acc = dists < threshold
        new_y, new_x = cand_y[acc], cand_x[acc]
        if new_y.size == 0:
            break
        # Khử trùng lặp: 1 pixel có thể kề 4 frontier → chỉ nạp + đưa vào frontier MỘT lần,
        # nếu không frontier nhân bản theo cấp số nhân và tràn bộ nhớ trên nền rộng.
        add = np.zeros((h, w), dtype=bool)
        add[new_y, new_x] = True
        add &= ~bg
        if not bool(add.any()):
            break
        bg |= add
        fy, fx = np.nonzero(add)
        frontier = np.stack([fy, fx], axis=1)
    return bg


def _subject_bbox(image_bytes: bytes, image_mime: str) -> tuple[float, float, float, float] | None:
    """Xin Vision LLM hộp bao kín bao bì đựng nước (normalized 0..1). Lỗi → None (bỏ prior)."""
    res = complete(
        system=_BBOX_SYSTEM,
        user="Locate the main liquid product container in this photo.",
        task="vision:bg_redesign_bbox",
        timeout_s=30.0,
        json_mode=True,
        image_bytes=image_bytes,
        image_mime=image_mime,
    )
    if not res.ok:
        logger.info("bbox vision unavailable (%s), segmenting without box prior", res.reason)
        return None
    try:
        data = json.loads(res.text)
        x1, y1 = float(data["x1"]), float(data["y1"])
        x2, y2 = float(data["x2"]), float(data["y2"])
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None
    xa, xb = sorted((min(max(x1, 0.0), 1.0), min(max(x2, 0.0), 1.0)))
    ya, yb = sorted((min(max(y1, 0.0), 1.0), min(max(y2, 0.0), 1.0)))
    if xb - xa < 0.05 or yb - ya < 0.05:
        return None
    return xa, ya, xb, yb


def _subject_alpha(
    img: Image.Image, bbox: tuple[float, float, float, float] | None
) -> np.ndarray | None:
    """Alpha mask chủ thể (float 0..1, cùng cỡ img). None nếu không tin cậy."""
    arr = np.asarray(img.convert("RGB"), dtype=np.float32)
    h, w = arr.shape[:2]

    border = max(2, min(h, w) // 120)
    seed = np.zeros((h, w), dtype=bool)
    seed[:border, :] = True
    seed[-border:, :] = True
    seed[:, :border] = True
    seed[:, -border:] = True

    # Mô hình nền là CỤM MÀU của viền ảnh (không phải một màu trung bình): biên có
    # thể gồm nền tối phía trên và khay/bàn sáng phía dưới — trung bình hai màu đó
    # nằm giữa, khiến cả hai vùng bị coi là "xa nền" và bị giữ làm chủ thể.
    border_px = arr[seed].reshape(-1, 3)
    centers = _border_clusters(border_px, _BG_CLUSTERS, _BG_KMEANS_ITERS)
    gdist = _min_dist_to_centers(arr, centers)
    # Pixel gần MỘT TRONG CÁC màu nền mới được phép là nền → flood-fill không rò
    # qua vùng bokeh chuyển sắc xa biên.
    allowed = gdist < _BG_GLOBAL_RADIUS

    bg = _grow_background(arr, seed, _BG_TOLERANCE_PER_CHANNEL, allowed=allowed)
    subj = ~bg

    if bbox is not None:
        x1, y1, x2, y2 = bbox
        margin = 0.06
        box = np.zeros((h, w), dtype=bool)
        box[
            max(0, int((y1 - margin) * h)) : min(h, int((y2 + margin) * h)),
            max(0, int((x1 - margin) * w)) : min(w, int((x2 + margin) * w)),
        ] = True
        subj &= box

    labels, n = ndimage.label(subj)
    if n == 0:
        return None
    sizes = ndimage.sum_labels(subj.astype(np.int32), labels, index=np.arange(1, n + 1))
    largest = int(np.argmax(sizes)) + 1
    subj = cast("np.ndarray", labels == largest)
    subj = ndimage.binary_fill_holes(subj)

    ratio = float(subj.mean())
    if ratio < 0.03 or ratio > 0.92:
        logger.info("subject ratio %.3f outside trusted range", ratio)
        return None

    subj = ndimage.binary_closing(subj, structure=np.ones((3, 3)))
    subj = ndimage.binary_opening(subj, structure=np.ones((3, 3)))
    # LẤP LỖ BÊN TRONG chủ thể lần nữa sau closing/opening: đế ly/chân ly có màu
    # trùng khay nền nên bị loại khỏi mask, tạo lỗ hổng ở đáy ly → ảnh ghép mất đế.
    # Fill holes chỉ lấp vùng KÍN bên trong nên không kéo nền ngoài vào.
    filled = ndimage.binary_fill_holes(subj)
    if bool(filled.any()):
        subj = filled
    # Co mask: bỏ lớp pixel pha giữa ly và nền CŨ nằm sát rìa. Không co thì đổi
    # sang nền tối sẽ thấy viền sáng/bẩn ôm quanh ly (quầng nền cũ).
    if _MASK_ERODE_PX > 0:
        eroded = ndimage.binary_erosion(subj, iterations=_MASK_ERODE_PX)
        if bool(eroded.any()):
            subj = eroded
    sigma = max(1.0, min(h, w) / 350.0)
    alpha = ndimage.gaussian_filter(subj.astype(np.float32), sigma=sigma)
    alpha = np.clip(alpha, 0.0, 1.0)
    # Siết đuôi feather: giá trị rất nhỏ là pixel nền cũ còn sót, đặt về 0.
    alpha = np.where(alpha < _MASK_FEATHER_FLOOR, 0.0, alpha)
    return cast("np.ndarray", alpha)


def _tight_crop(subject: Image.Image, alpha: np.ndarray) -> tuple[Image.Image, np.ndarray]:
    """Crop sát chủ thể (hộp bao alpha > 0.05) để scale không phí chỗ trống."""
    ys, xs = np.nonzero(alpha > 0.05)
    if len(ys) == 0:
        return subject, alpha
    y0, y1 = max(0, int(ys.min()) - 4), min(alpha.shape[0], int(ys.max()) + 5)
    x0, x1 = max(0, int(xs.min()) - 4), min(alpha.shape[1], int(xs.max()) + 5)
    return subject.crop((x0, y0, x1, y1)), alpha[y0:y1, x0:x1]


def _cover_resize(img: Image.Image, width: int, height: int) -> Image.Image:
    """Đưa ảnh về đúng khung bằng cách CẮT bớt (cover) — không bóp méo tỷ lệ.

    Bản cũ dùng ``resize((width, height))`` thẳng, nên nền 1024×1024 đem về
    896×1120 bị kéo dọc ~25% → mọi đường trong nền (mép bàn, vệt sáng, bokeh
    tròn) đều méo. Ở đây scale theo cạnh LỚN HƠN rồi crop phần dư ở giữa, nên
    tỷ lệ gốc của ảnh nền được giữ nguyên.
    """
    src_w, src_h = img.size
    if src_w <= 0 or src_h <= 0:
        return img
    scale = max(width / src_w, height / src_h)
    new_w = max(width, int(round(src_w * scale)))
    new_h = max(height, int(round(src_h * scale)))
    resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
    left = (new_w - width) // 2
    top = (new_h - height) // 2
    return resized.crop((left, top, left + width, top + height))


def _premultiplied_resize(rgba: Image.Image, size: tuple[int, int]) -> Image.Image:
    """Resize RGBA có nhân trước alpha — chống lem màu nền cũ vào rìa ly.

    Pillow nội suy từng kênh ĐỘC LẬP khi resize RGBA. Ở pixel ngoài mask, kênh
    RGB vẫn chứa màu nền cũ (thường là trắng), nên màu đó bị kéo vào rìa ly và
    tạo viền xám/bẩn. Nhân RGB với alpha trước khi resize rồi chia lại sau là
    cách chuẩn để tránh hiện tượng này.
    """
    arr = np.asarray(rgba, dtype=np.float32)
    if arr.ndim != 3 or arr.shape[2] != 4:
        return rgba.resize(size, Image.Resampling.LANCZOS)
    alpha = arr[:, :, 3:4] / 255.0
    premul = np.concatenate([arr[:, :, :3] * alpha, arr[:, :, 3:4]], axis=2)
    resized = np.asarray(
        Image.fromarray(premul.astype(np.uint8), mode="RGBA").resize(
            size, Image.Resampling.LANCZOS
        ),
        dtype=np.float32,
    )
    out_alpha = resized[:, :, 3:4] / 255.0
    safe = np.where(out_alpha > 1e-3, out_alpha, 1.0)
    out_rgb = np.clip(resized[:, :, :3] / safe, 0.0, 255.0)
    out = np.concatenate([out_rgb, resized[:, :, 3:4]], axis=2)
    return Image.fromarray(out.astype(np.uint8), mode="RGBA")


def _background_is_usable(bg_img: Image.Image, old_bg_color: np.ndarray) -> tuple[bool, str]:
    """Kiểm tra nền sinh ra có dùng được không. Trả ``(ok, lý do)``.

    Chặn các dạng "ảnh lỗi" provider cộng đồng hay trả: ảnh một màu, ảnh nhiễu
    đen, ảnh quá tối/sáng, và ảnh gần như TRÙNG nền cũ (model bỏ qua prompt rồi
    trả lại chính khung ảnh gốc — khi đó coi như đổi nền thất bại nhưng người
    dùng vẫn thấy ảnh cũ, tưởng là ảnh mới).
    """
    small = bg_img.convert("RGB").resize((96, 96), Image.Resampling.BILINEAR)
    arr = np.asarray(small, dtype=np.float32)
    if arr.ndim != 3 or arr.shape[2] != 3 or arr.size == 0:
        return False, "bad_background"
    mean = float(arr.mean())
    std = float(arr.std())
    if std < _BG_MIN_STD:
        return False, "flat_background"
    if mean < _BG_MIN_MEAN or mean > _BG_MAX_MEAN:
        return False, "extreme_background"
    new_color = arr.reshape(-1, 3).mean(axis=0)
    if float(np.sqrt(((new_color - old_bg_color) ** 2).sum())) < _BG_MIN_COLOR_DELTA:
        return False, "background_unchanged"
    return True, ""


def _edge_color(img: Image.Image) -> np.ndarray:
    """Màu trung bình của viền ảnh gốc — mốc so sánh "nền mới có đổi không"."""
    small = img.convert("RGB").resize((64, 64), Image.Resampling.BILINEAR)
    arr = np.asarray(small, dtype=np.float32)
    border = np.concatenate(
        [
            arr[:2].reshape(-1, 3),
            arr[-2:].reshape(-1, 3),
            arr[:, :2].reshape(-1, 3),
            arr[:, -2:].reshape(-1, 3),
        ]
    )
    return cast("np.ndarray", border.mean(axis=0))


def _fit_subject(
    subject_rgba: Image.Image, width: int, height: int
) -> tuple[Image.Image, int, int]:
    """Scale ly theo tỷ lệ ĐỒNG NHẤT và đặt theo đường chân đế.

    Bản cũ dùng ``min()`` trên hai tỷ lệ rồi làm tròn xuống, nên ly nhỏ hơn cần
    thiết và lệch khỏi tâm vài pixel ở khung có kích thước lẻ. Ở đây tính một
    scale duy nhất, làm tròn về số nguyên, rồi căn giữa theo hiệu số thực.
    """
    sw, sh = subject_rgba.size
    if sw <= 0 or sh <= 0:
        return subject_rgba, 0, 0
    scale = min(width * _SUBJECT_WIDTH_RATIO / sw, height * _SUBJECT_HEIGHT_RATIO / sh)
    new_w = max(1, int(round(sw * scale)))
    new_h = max(1, int(round(sh * scale)))
    subj = _premultiplied_resize(subject_rgba, (new_w, new_h))
    x = (width - new_w) // 2
    # Đặt đáy ly cao hơn mép dưới để còn thấy mặt bàn (bóng đổ cần chỗ).
    y = int(round(height * (1.0 - _BOTTOM_MARGIN_RATIO))) - new_h
    y = max(0, min(y, height - new_h))
    return subj, x, y


def _glow_layer(width: int, height: int, x: int, y: int, new_w: int, new_h: int) -> Image.Image:
    """Hào quang ấm phía sau ly + vignette nhẹ — hiệu ứng QUANH ly, không sửa pixel ly."""
    glow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    cx, cy = x + new_w // 2, y + int(new_h * 0.55)
    r = max(8, int(max(new_w, new_h) * _GLOW_RADIUS_FACTOR))
    # Gradient tỏa tròn: sáng ở tâm, tắt dần ra ngoài. Bậc 2 cho vệt sáng mềm,
    # không lộ vòng tròn rõ nét trên nền trơn như gradient tuyến tính.
    yy, xx = np.mgrid[0 : 2 * r, 0 : 2 * r]
    dist = np.sqrt((xx - r) ** 2 + (yy - r) ** 2) / r
    halo_arr = np.clip((1.0 - dist) ** 2 * _GLOW_ALPHA, 0, 255).astype(np.uint8)
    halo = Image.fromarray(halo_arr)
    halo_rgb = Image.new("RGBA", halo.size, (255, 226, 170, 0))
    halo_rgb.putalpha(halo)
    glow.paste(halo_rgb, (cx - r, cy - r), halo_rgb)

    # Vignette: tối 4 góc. Cũng dùng alpha bậc 2 để chuyển tiếp mượt.
    vy, vx = np.mgrid[0:height, 0:width]
    dx = (vx / max(1, width - 1) - 0.5) * 2
    dy = (vy / max(1, height - 1) - 0.5) * 2
    radial = np.clip((dx * dx + dy * dy) - 0.55, 0, 1)
    v = (radial * radial + radial) * 0.5 * _VIGNETTE_STRENGTH
    vig = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    vig.putalpha(Image.fromarray(v.astype(np.uint8)))
    black = Image.new("RGBA", (width, height), (10, 6, 4, 0))
    black.putalpha(vig.getchannel("A"))
    glow = Image.alpha_composite(glow, black)
    return glow


def _composite(
    subject_rgba: Image.Image, background: Image.Image, width: int, height: int
) -> Image.Image:
    """Dán ly nước gốc (pixel không đổi) lên nền mới, kèm bóng đổ + hiệu ứng sáng."""
    canvas = _cover_resize(background.convert("RGB"), width, height)
    subj, x, y = _fit_subject(subject_rgba, width, height)
    new_w, new_h = subj.size

    canvas = canvas.convert("RGBA")
    # Hào quang sau ly (trước khi dán chủ thể → chủ thể gốc nằm trên cùng).
    canvas = Image.alpha_composite(canvas, _glow_layer(width, height, x, y, new_w, new_h))

    # Bóng đổ: tô đen theo alpha của DẢI ĐÁY ly (không dùng cả cột dọc, nếu không
    # bóng sẽ loang thành vệt dài phía trên), lệch nhẹ xuống dưới rồi làm mờ.
    band = max(2, int(new_h * 0.18))
    top = max(0, new_h - band)
    shadow_alpha = subj.getchannel("A").crop((0, top, new_w, new_h)).point(
        lambda v: int(v * _SHADOW_OPACITY)
    )
    shadow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    shadow.paste(
        Image.new("RGBA", (new_w, band), (0, 0, 0, 255)),
        (x, y + top + max(2, int(height * 0.008))),
        shadow_alpha,
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=max(3.0, width * 0.010)))
    canvas = Image.alpha_composite(canvas, shadow)

    canvas.paste(subj, (x, y), subj)
    return canvas.convert("RGB")


def _background_prompt_only(prompt_en: str) -> str:
    """Viết lại prompt thành mô tả nền-only qua LLM; lỗi → fallback cố định."""
    res = complete(
        system=_BG_PROMPT_SYSTEM,
        user=prompt_en[:2000],
        task="bg_redesign:prompt",
        timeout_s=12.0,
        json_mode=True,
    )
    if res.ok:
        try:
            bg = str(json.loads(res.text).get("background_prompt_en", "")).strip()
            if len(bg) >= 20:
                return bg
        except json.JSONDecodeError:
            logger.info("bg prompt rewrite returned bad json, using fallback")
    return _BG_FALLBACK


def build_background_prompt(prompt_en: str, style: MenuStyle | None) -> str:
    """Dựng prompt nền cuối cùng.

    - Có ``style`` (quán đã lưu phong cách): prompt TẤT ĐỊNH từ phong cách, không
      gọi LLM. Nhờ vậy 10 ly của cùng một quán ra cùng một phong cách, và tiết
      kiệm 3–10 giây chờ LLM mỗi ảnh.
    - Không có ``style``: phải viết lại prompt gốc nên cần LLM (lỗi → fallback).
    """
    if style is not None:
        return style.to_prompt()
    return _background_prompt_only(prompt_en) + _BG_NEGATION


def _cloudflare_background(
    *,
    prompt: str,
    timeout_s: float,
    seed: int | None,
    width: int,
    height: int,
) -> ImageGenResult | None:
    """Sinh nền qua Cloudflare Workers AI. None = "không dùng được" → thử Pollinations.

    Cloudflare nhận thẳng ``width``/``height`` (đã kiểm chứng 896×1120 và
    768×1344 đều trả đúng kích thước) nên KHÔNG cần bảng kích thước riêng như
    NVIDIA trước đây — dùng chung ``ASPECT_DIMS`` với mọi provider còn lại.

    Trả ``ImageGenResult(ok=False)`` khi provider đã trả lời nhưng lỗi thật
    (429 hết neurons/ngày, ảnh hỏng) — lúc đó nền không dùng được và
    ``_generate_background`` sẽ thử seed khác rồi mới nhường Pollinations.
    """
    cf = _cf_ready()
    if cf is None:
        return None
    if timeout_s <= 3.0:
        return None
    account, token = cf
    model = os.environ.get("CLOUDFLARE_IMAGE_MODEL", "").strip() or _CF_BG_MODEL
    return _cf_image_any_field(
        account=account,
        token=token,
        model=model,
        prompt=prompt,
        timeout_s=timeout_s,
        width=width,
        height=height,
        seed=seed if seed is not None else 0,
    )


def _generate_background(
    prompt: str,
    width: int,
    height: int,
    seed: int | None,
    timeout_s: float,
    old_bg_color: np.ndarray,
) -> tuple[Image.Image | None, str, str]:
    """Sinh nền có cache + kiểm tra chất lượng + thử lại seed khác.

    Trả ``(ảnh, lỗi, provider)`` — ``ảnh`` là None nghĩa là thất bại.
    """
    tried: set[int | None] = set()
    last_error = "no_image_in_response"
    provider = "pollinations"
    for attempt in range(_BG_ATTEMPTS):
        attempt_seed = None if seed is None else seed + attempt
        if attempt_seed in tried:
            continue
        tried.add(attempt_seed)
        key = _bg_cache_key(prompt, width, height, attempt_seed)
        blob = _bg_cache_get(key)
        if blob is None:
            # Cloudflare trước (có hạn mức miễn phí rõ ràng, nhanh) rồi mới tới
            # Pollinations (không cần key nhưng hay 429 khi đông).
            #
            # Cloudflare lỗi THẬT (429 hết neurons/ngày, 5xx) vẫn phải nhường
            # Pollinations: hết hạn mức theo ngày là chuyện bình thường, không
            # được để nó làm cả tính năng đứng khi còn nguồn miễn phí khác.
            res = _cloudflare_background(
                prompt=prompt,
                timeout_s=timeout_s,
                seed=attempt_seed,
                width=width,
                height=height,
            )
            if res is not None and not res.ok:
                logger.info(
                    "cloudflare background failed (%s), trying pollinations",
                    (res.error or "")[:80],
                )
                res = None
            if res is None:
                res = _pollinations_image(
                    prompt=prompt,
                    timeout_s=timeout_s,
                    width=width,
                    height=height,
                    seed=attempt_seed,
                    # Lần đầu đã có retry nội bộ của provider; lần thử lại thứ hai
                    # không cần thêm nữa, tránh nhân đôi thời gian chờ.
                    attempts=2 if attempt == 0 else 1,
                )
            if not res.ok:
                last_error = res.error or "no_image_in_response"
                provider = res.provider or provider
                continue
            blob = res.image_bytes
            provider = res.provider or provider
            _bg_cache_put(key, blob)
        else:
            provider = "cache"
        try:
            with Image.open(io.BytesIO(blob)) as opened:
                opened.load()
                img: Image.Image = opened.convert("RGB")
        except Exception:  # noqa: BLE001 — PIL raise nhiều loại lỗi ảnh hỏng
            last_error = "bad_background_image"
            _BG_CACHE.pop(key, None)
            continue
        ok, reason = _background_is_usable(img, old_bg_color)
        if not ok:
            logger.info("background rejected (%s), attempt %d", reason, attempt + 1)
            last_error = reason
            # Cache ảnh hỏng chỉ tổ lặp lại lỗi — xoá để lần sau thử lại mạng.
            _BG_CACHE.pop(key, None)
            continue
        return img, "", provider
    return None, last_error, provider


def _decode_original(original_bytes: bytes) -> Image.Image | None:
    """Mở ảnh gốc; None nếu file không phải ảnh đọc được.

    Trả bản sao đã ``convert("RGB")`` rồi đóng handle: ảnh gốc là JPEG nhiều
    megapixel, giữ handle mở suốt quá trình composite làm tăng bộ nhớ đỉnh mà
    không dùng lại file.
    """
    try:
        with Image.open(io.BytesIO(original_bytes)) as opened:
            opened.load()
            return opened.convert("RGB")
    except Exception:  # noqa: BLE001 — PIL raise nhiều loại lỗi ảnh hỏng
        return None


def generate_background_redesign(
    original_bytes: bytes,
    prompt_en: str,
    *,
    original_mime: str = "image/jpeg",
    aspect_ratio: str = "1:1",
    seed: int | None = None,
    timeout_s: float = 45.0,
    style: MenuStyle | None = None,
) -> ImageGenResult:
    """Giữ nguyên sản phẩm trong ảnh gốc, chỉ thiết kế lại background.

    Chạy cho MỌI loại bao bì đựng chất lỏng (ly, chai, lọ, bình, hộp, túi) — thuật
    toán tách chủ thể dựa trên màu viền ảnh nên không phụ thuộc hình dạng.

    Quy trình (vision và sinh nền chạy SONG SONG):

    1. Song song: (a) Vision LLM tìm hộp bao sản phẩm — prior, lỗi vẫn chạy tiếp;
       (b) sinh nền theo phong cách (hoặc viết lại prompt nếu chưa có phong cách).
    2. Flood-fill màu từ biên tách nền; chủ thể = pixel gốc 100%.
    3. Nền không đạt kiểm tra chất lượng → thử seed khác; hết lượt → lỗi rõ ràng.
    4. Composite chủ thể gốc lên nền mới + hào quang + vignette + bóng đổ.

    Fail-closed: tách chủ thể không tin cậy → ``segment_failed``; nền hỏng sau
    khi thử lại → trả đúng lý do, KHÔNG ghép thành ảnh lỗi.
    """
    if not original_bytes:
        return ImageGenResult(ok=False, error="missing_original_image")
    if not prompt_en.strip():
        return ImageGenResult(ok=False, error="empty_prompt")

    img = _decode_original(original_bytes)
    if img is None:
        return ImageGenResult(ok=False, error="invalid_original_image")

    w0, h0 = img.size
    if w0 < 64 or h0 < 64:
        return ImageGenResult(ok=False, error="original_too_small")

    width, height = ASPECT_DIMS.get(aspect_ratio, (1024, 1024))
    bg_prompt = build_background_prompt(prompt_en, style)
    old_bg_color = _edge_color(img)

    # Bước 1: vision (LLM, I/O mạng) và sinh nền (I/O mạng ảnh) độc lập nhau —
    # chạy SONG SONG để tổng thời gian là max thay vì tổng cộng dồn (trước đây
    # tuần tự: ~5s bbox + ~10s LLM prompt + ~30s nền ≈ 45s cho một ảnh).
    # Không dùng `with ThreadPoolExecutor` vì khối đó chờ MỌI thread xong khi
    # thoát, làm mất tác dụng của việc thoát sớm khi tách chủ thể thất bại.
    pool = ThreadPoolExecutor(max_workers=2)
    bbox_future = pool.submit(_subject_bbox, original_bytes, original_mime)
    bg_future = pool.submit(
        _generate_background, bg_prompt, width, height, seed, timeout_s, old_bg_color
    )

    try:
        bbox = bbox_future.result()
    except Exception:  # noqa: BLE001 — prior không bắt buộc, lỗi thì bỏ qua
        logger.exception("bg_redesign: vision bbox lỗi, tách chủ thể không prior")
        bbox = None

    # Bước 2: tách chủ thể (CPU) chạy ĐÈ lên thời gian ảnh nền còn đang tải.
    ratio = min(1.0, _MASK_MAX_DIM / max(w0, h0))
    small = img.convert("RGB").resize(
        (max(2, int(w0 * ratio)), max(2, int(h0 * ratio))), Image.Resampling.LANCZOS
    )
    alpha_small = _subject_alpha(small, bbox)
    if alpha_small is None:
        # Thoát sớm: không đáng chờ nốt ảnh nền cho một kết quả chắc chắn hỏng.
        pool.shutdown(wait=False, cancel_futures=True)
        return ImageGenResult(
            ok=False,
            provider="local-composite",
            error="segment_failed",
            text="Không tách được sản phẩm ra khỏi nền. Hãy thử ảnh có nền đơn giản hơn "
            "(ít vật xung quanh, nền không trùng màu sản phẩm), "
            "hoặc bỏ chọn 'giữ nguyên sản phẩm' để AI vẽ toàn bộ.",
        )

    try:
        bg_img, bg_error, bg_provider = bg_future.result()
    except Exception:  # noqa: BLE001 — lỗi bất ngờ trong luồng sinh nền
        logger.exception("bg_redesign: luồng sinh nền lỗi")
        bg_img, bg_error, bg_provider = None, "background_task_failed", "pollinations"
    finally:
        pool.shutdown(wait=False)

    # Bước 3: kiểm tra nền — báo lỗi rõ thay vì ghép ra ảnh hỏng.
    if bg_img is None:
        return ImageGenResult(
            ok=False,
            provider=bg_provider or "pollinations",
            error=bg_error or "no_image_in_response",
            text="Nền AI không dùng được (ảnh trả về trống, một màu, hoặc trùng nền cũ). "
            "Bấm 'Tạo lại ảnh khác' để thử seed khác, hoặc chọn phong cách khác.",
        )

    # Đưa mask về độ phân giải gốc, ghép alpha vào ảnh gốc (pixel giữ nguyên).
    alpha_full = (
        np.asarray(
            Image.fromarray((alpha_small * 255.0).astype(np.uint8)).resize(
                (w0, h0), Image.Resampling.BILINEAR
            ),
            dtype=np.float32,
        )
        / 255.0
    )
    subject = img.convert("RGBA")
    subject.putalpha(Image.fromarray((alpha_full * 255.0).astype(np.uint8)))
    cropped, alpha_crop = _tight_crop(subject, alpha_full)
    cropped = cropped.copy()
    cropped.putalpha(Image.fromarray((alpha_crop * 255.0).astype(np.uint8)))

    canvas = _composite(cropped, bg_img, width, height)
    out = io.BytesIO()
    canvas.save(out, format="PNG")
    return ImageGenResult(
        ok=True,
        image_bytes=out.getvalue(),
        image_mime="image/png",
        provider="local-composite",
        # Ghi PROVIDER THẬT đã sinh nền (cloudflare / pollinations / cache) thay
        # vì hằng số cứng: đây là thông tin người vận hành cần khi ảnh nền ra
        # xấu — biết đổ lỗi cho nguồn nào và có nên đổi cấu hình hay không.
        model=f"{bg_provider or 'pollinations'}-bg+pillow",
        text=(
            f"style={style.slug if style is not None else 'auto'} "
            f"background_prompt={bg_prompt[:120]}"
        ),
    )
