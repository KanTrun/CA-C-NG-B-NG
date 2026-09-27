"""Sinh bộ icon ứng dụng + SVG dấu quán từ ảnh gốc `docs/hinh/logo.png`.

Vì sao có script này: hai tệp icon đang phục vụ production đều sai chuẩn —
`public/favicon.ico` chỉ có **1 entry 256×233** (không vuông, không có 16/32 nên
trình duyệt phải tự downscale, nhoè ở tab), và `public/manifest.webmanifest`
**không có khoá `icons`** nên Android không có nguồn icon. Gốc rễ: `favicon.png`
là ảnh **338×307** (tỉ lệ 1.10) chứ không vuông — ICO khai cạnh bằng một byte nên
không biểu diễn được tỉ lệ lệch 1:1.

Script này:
  1. **Vuông hoá** ảnh gốc bằng cách PAD (không kéo giãn — kéo giãn là cách chắc
     chắn nhất để logo méo, và nhiều khả năng đó chính là cách tệp ICO cũ ra đời).
  2. Ghi `.ico` nhiều entry 16/32/48 (Pillow ghi đúng ICONDIR nhiều entry).
  3. Ghi `favicon-16/32`, `apple-touch-icon` 180, `icon-192`, `icon-512`, và
     `icon-512-maskable` (co logo vào 80% để an toàn vùng cắt của Android).
  4. **Trace** phần HÌNH của logo (ly + nhịp tim, cắt tại khoảng trống y=98 để bỏ
     chữ) thành `public/icon.svg` — nhờ vậy favicon SVG và `Logo.tsx` dùng CÙNG
     một dữ liệu path, không thể lệch nhau.

Dùng:
    python scripts/gen_app_icons.py            # sinh đầy đủ
    python scripts/gen_app_icons.py --kiem-tra # chỉ đo, không ghi
    python scripts/gen_app_icons.py --trace-svg # in path SVG ra màn hình

Tất định: cùng ảnh vào → cùng byte ra, không gọi mạng (đúng §14.9 — demo phải
chạy khi đã rút mạng). Chỉ dùng Pillow + numpy + scipy, đều đã khai trong
`docs/THIRD_PARTY.md`.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "docs" / "hinh" / "logo.png"
PUB = ROOT / "apps" / "web" / "public"
LOGO_TS = ROOT / "apps" / "web" / "src" / "ui" / "logo-path.ts"

# Nền đặc cho những chỗ buộc phải tô kín ô. Android cắt tới 20% mỗi cạnh ở chế
# độ adaptive, nên hình phải nằm gọn trong 80% giữa; phần bị cắt là nền ĐẶC theo
# token chứ không phải trong suốt (trong suốt → Android tự bịa nền, và iOS thì
# tô đen).
MASKABLE_SAFE = 0.80
BG_HEX = "#070d12"

# ── Vì sao bộ icon nào cũng có nền sáng ──────────────────────────────────────
# Mực của logo là nâu socola #432012. Đo bằng công thức tương phản WCAG:
#
#     trên nền sáng  → 4.7:1  (16px) … 9.8:1 (192px)   đạt
#     trên nền tối   → 1.25:1 (16px) … 1.40:1 (192px)  KHÔNG ĐỌC ĐƯỢC
#
# Trình duyệt hiện đại vẽ favicon trên cả thanh tab SÁNG và TỐI (Chrome/Edge/
# Safari tự đổi theo theme hệ điều hành). Nâu trên nền tối gần như tàng hình.
# Cách chữa không phải đổi màu mực — đó là màu thương hiệu — mà là **đặt mực lên
# một đĩa nền sáng**, giống huy hiệu. Nhờ vậy cùng một tệp đọc được trên mọi nền,
# và mực vẫn đúng màu gốc.
#
# Đĩa dùng `--nq-accent-50` (#faf6e8) — bậc sáng nhất của chính dải gold trong
# hệ token, nên vẫn là "nền của quán", không phải trắng trơ.
# `apple-touch-icon` và bản maskable thì tô **kín ô vuông** (không phải đĩa):
# iOS không xử lý alpha cho apple-touch-icon (nền trong suốt bị tô đen), còn
# maskable thì mặt nạ của launcher sẽ tự cắt — để lộ góc trong suốt là sai.
PLATE = (250, 246, 232, 255)  # --nq-accent-50
PLATE_HEX = "#faf6e8"
DISC_RATIO = 0.74  # logo chiếm bao nhiêu phần đường kính đĩa
INK_HEX = "#432012"  # mực gốc đo được từ logo.png
FULLBLEED_RATIO = {"apple-touch-icon.png": 0.78, "icon-512-maskable.png": MASKABLE_SAFE}

# ── Trace SVG ────────────────────────────────────────────────────────────────
TRACE_UP = 4  # phóng to trước khi lấy contour
TRACE_SIGMA = 1.2  # làm mượt biên (chính là cách giảm số điểm mà giữ hình dạng)
TRACE_TOL = 1.2  # Douglas-Peucker
TRACE_MIN_PTS = 10
TRACE_BOX = 60.0  # hình chiếm 60/100 đơn vị viewBox (vòng tròn của Logo.tsx: r=45)
WORDMARK_CUT = 98  # y bắt đầu phần CHỮ trong logo.png


def alpha_mask(src: Path, cut: int | None) -> np.ndarray:
    """Mask phần đục của ảnh gốc (a>110). `cut` để bỏ phần chữ phía dưới."""
    a = np.array(Image.open(src).convert("RGBA"))[:, :, 3]
    if cut is not None:
        a = a[:cut, :]
    return a > 110


def crop_to_content(m: np.ndarray) -> np.ndarray:
    ys, xs = np.nonzero(m)
    return m[int(ys.min()) : int(ys.max()) + 1, int(xs.min()) : int(xs.max()) + 1]


def squared_pad(im: Image.Image, bg: tuple[int, int, int, int] | None) -> Image.Image:
    """Đưa ảnh về VUÔNG bằng cách đệm — không kéo giãn."""
    w, h = im.size
    if w == h:
        return im
    side = max(w, h)
    out = Image.new("RGBA", (side, side), bg if bg is not None else (0, 0, 0, 0))
    out.alpha_composite(im, ((side - w) // 2, (side - h) // 2))
    return out


def badge(logo: Image.Image, side: int, *, disc: bool, ratio: float, bg: tuple[int, int, int, int]) -> Image.Image:
    """Logo trên nền sáng: đĩa tròn (tab) hoặc tô kín ô (touch icon / maskable).

    Vì sao không bao giờ để nền trong suốt cho icon trình duyệt: xem khối chú
    thích `PLATE` — nâu #432012 trên nền tối chỉ đạt 1.25:1.
    """
    out = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    if disc:
        # Vẽ đĩa ở 4× rồi thu nhỏ: khử răng cưa cho viền tròn (Pillow không có AA
        # cho ellipse). Ở 16px, viền răng cưa đọc ra là "icon bị vỡ".
        ss = side * 4
        plate = Image.new("RGBA", (ss, ss), (0, 0, 0, 0))
        ImageDraw.Draw(plate).ellipse((0, 0, ss - 1, ss - 1), fill=bg)
        out.alpha_composite(plate.resize((side, side), Image.LANCZOS))
    else:
        out.alpha_composite(Image.new("RGBA", (side, side), bg))

    inner = max(1, int(round(side * ratio)))
    mark = logo.resize((inner, inner), Image.LANCZOS)
    off = (side - inner) // 2
    out.alpha_composite(mark, (off, off))
    return out


# ── Marching squares (tự viết: cv2 không phải dependency của repo) ───────────
_SIDES: dict[str, tuple[float, float]] = {}


def _pt(cy: int, cx: int, side: str) -> tuple[float, float]:
    if side == "T":
        return (cx + 0.5, float(cy))
    if side == "B":
        return (cx + 0.5, cy + 1.0)
    if side == "L":
        return (float(cx), cy + 0.5)
    return (cx + 1.0, cy + 0.5)


_TABLE: dict[int, list[tuple[str, str]]] = {
    1: [("L", "B")],
    2: [("B", "R")],
    3: [("L", "R")],
    4: [("T", "R")],
    5: [("T", "R"), ("L", "B")],
    6: [("T", "B")],
    7: [("T", "L")],
    8: [("T", "L")],
    9: [("T", "B")],
    10: [("T", "L"), ("B", "R")],
    11: [("T", "R")],
    12: [("L", "R")],
    13: [("B", "R")],
    14: [("L", "B")],
}


def marching_squares(f: np.ndarray, level: float = 0.5) -> list[list[tuple[float, float]]]:
    a = f[:-1, :-1] > level
    b = f[:-1, 1:] > level
    c = f[1:, 1:] > level
    d = f[1:, :-1] > level
    code = (
        (a.astype(np.uint8) << 3) | (b.astype(np.uint8) << 2) | (c.astype(np.uint8) << 1) | d.astype(np.uint8)
    )
    segs: dict[tuple[float, float], list[tuple[float, float]]] = {}
    for cy in range(code.shape[0]):
        for cx in range(code.shape[1]):
            for s0, s1 in _TABLE.get(int(code[cy, cx]), []):
                p0, p1 = _pt(cy, cx, s0), _pt(cy, cx, s1)
                segs.setdefault(p0, []).append(p1)
                segs.setdefault(p1, []).append(p0)

    used: set[frozenset[tuple[float, float]]] = set()
    out: list[list[tuple[float, float]]] = []
    for start in list(segs):
        while segs.get(start):
            path = [start]
            cur = start
            while True:
                nxts = segs.get(cur)
                if not nxts:
                    break
                nxt = next((c for c in reversed(nxts) if frozenset((cur, c)) not in used), None)
                if nxt is None:
                    break
                used.add(frozenset((cur, nxt)))
                segs[cur].remove(nxt)
                segs[nxt].remove(cur)
                if nxt == start:
                    break
                path.append(nxt)
                cur = nxt
            if len(path) >= TRACE_MIN_PTS:
                out.append(path)
    return out


def simplify(pts: list[tuple[float, float]], tol: float) -> list[tuple[float, float]]:
    """Douglas-Peucker."""
    if len(pts) < 3:
        return pts
    P = np.asarray(pts, float)
    keep = np.zeros(len(P), bool)
    keep[0] = keep[-1] = True
    stack = [(0, len(P) - 1)]
    while stack:
        i, j = stack.pop()
        if j <= i + 1:
            continue
        a, b = P[i], P[j]
        seg = b - a
        length = float(np.hypot(*seg))
        if length == 0:
            dist = np.hypot(*(P[i + 1 : j] - a).T)
        else:
            # Khoảng cách điểm->đường thẳng, viết tay thay vì np.cross: numpy 2.x
            # cảnh báo `cross` trên vector 2 chiều (sắp bỏ). Công thức tương đương
            # |dx*(ay-y0) - dy*(ax-x0)| / |d|.
            rel = P[i + 1 : j] - a
            dist = np.abs(seg[0] * rel[:, 1] - seg[1] * rel[:, 0]) / length
        k = int(np.argmax(dist))
        if dist[k] > tol:
            keep[i + 1 + k] = True
            stack.extend([(i, i + 1 + k), (i + 1 + k, j)])
    return [tuple(v) for v in P[keep]]


def trace_svg_path(src: Path = SRC) -> str:
    """Trace phần HÌNH của logo thành path SVG trong viewBox 100×100."""
    crop = crop_to_content(alpha_mask(src, WORDMARK_CUT))
    bh, bw = crop.shape
    up = np.array(
        Image.fromarray((crop * 255).astype(np.uint8)).resize((bw * TRACE_UP, bh * TRACE_UP), Image.LANCZOS)
    ).astype(np.float32) / 255.0
    up = ndimage.gaussian_filter(up, sigma=TRACE_SIGMA)
    h, w = up.shape

    scale = TRACE_BOX / max(w, h)
    off_x = (100.0 - w * scale) / 2
    off_y = (100.0 - h * scale) / 2

    parts: list[str] = []
    for ring in marching_squares(up):
        sp = simplify(ring, TRACE_TOL)
        if len(sp) < TRACE_MIN_PTS:
            continue
        pts = [(round(off_x + p[0] * scale, 1), round(off_y + p[1] * scale, 1)) for p in sp]
        d = f"M{pts[0][0]} {pts[0][1]}"
        for px_, py_ in pts[1:]:
            d += f"L{px_} {py_}"
        parts.append(d + "Z")
    return "".join(parts)


def trace_fidelity(src: Path = SRC) -> dict[str, float]:
    """Bằng chứng đo: IoU giữa path đã trace và mask gốc, ở đúng cỡ hiển thị."""
    crop = crop_to_content(alpha_mask(src, WORDMARK_CUT))
    bh, bw = crop.shape
    up = np.array(
        Image.fromarray((crop * 255).astype(np.uint8)).resize((bw * TRACE_UP, bh * TRACE_UP), Image.LANCZOS)
    ).astype(np.float32) / 255.0
    big = ndimage.gaussian_filter(up, sigma=TRACE_SIGMA) > 0.5
    h, w = big.shape

    im = Image.new("1", (w, h), 0)
    dr = ImageDraw.Draw(im)
    for ring in marching_squares(ndimage.gaussian_filter(up, sigma=TRACE_SIGMA)):
        sp = simplify(ring, TRACE_TOL)
        if len(sp) >= TRACE_MIN_PTS:
            dr.polygon(sp, fill=1, outline=1)

    out: dict[str, float] = {}
    for px in (16, 32, 36, 192):
        ref = np.array(Image.fromarray((crop * 255).astype(np.uint8)).resize((px, px), Image.LANCZOS)) > 127
        got = np.array(im.convert("L").resize((px, px), Image.LANCZOS)) > 127
        inter = int((ref & got).sum())
        union = int((ref | got).sum())
        out[f"{px}px"] = round(inter / union, 3) if union else 0.0
    return out


# ── Sinh bộ icon ─────────────────────────────────────────────────────────────
def build_icons(src: Path, out_dir: Path, *, write: bool) -> list[tuple[str, str]]:
    """Trả về [(tên tệp, mô tả)]; chỉ ghi đĩa khi `write=True`."""
    logo = Image.open(src).convert("RGBA")
    made: list[tuple[str, str]] = []

    def emit(name: str, im: Image.Image, desc: str) -> None:
        made.append((name, desc))
        if write:
            out_dir.mkdir(parents=True, exist_ok=True)
            im.save(out_dir / name)

    # Logo đã vuông hoá (đệm, không kéo giãn) rồi tách phần HÌNH: bỏ chữ bên
    # dưới, vì ở 16px dòng chữ chỉ còn là một vệt nhoè.
    sq = squared_pad(logo, None)
    art = logo.crop((0, 0, logo.size[0], WORDMARK_CUT))

    # `mark_im`: hình đặt đúng vị trí gốc (dùng cho đĩa tròn — hình đã cân sẵn
    # trong khung). `mark_sq`: kéo hình vào giữa khung vuông (dùng cho bản tô kín
    # ô, nơi không có đĩa để "đỡ" phần trống phía dưới).
    mark_im = Image.new("RGBA", sq.size, (0, 0, 0, 0))
    mark_im.alpha_composite(art, (0, 0))

    mark_sq = Image.new("RGBA", sq.size, (0, 0, 0, 0))
    mh = crop_to_content(alpha_mask(src, WORDMARK_CUT)).shape[0]
    mark_sq.alpha_composite(art, (0, (sq.size[1] - mh) // 2))

    # 1–3. Icon cho tab: đĩa nền sáng + hình ly/nhịp tim
    for px in (16, 32, 48):
        emit(
            f"favicon-{px}x{px}.png",
            badge(mark_im, px, disc=True, ratio=DISC_RATIO, bg=PLATE),
            f"{px}×{px}, đĩa {PLATE_HEX} + mực gốc",
        )

    # 4. .ico nhiều entry — bản cũ chỉ có 1 entry 256×233 (không vuông) nên
    #    trình duyệt phải tự downscale và nhoè ở tab.
    if write:
        ico_src = badge(mark_im, 256, disc=True, ratio=DISC_RATIO, bg=PLATE)
        ico_src.save(out_dir / "favicon.ico", format="ICO", sizes=[(16, 16), (32, 32), (48, 48)])
    made.append(("favicon.ico", "ICO 3 entry vuông: 16, 32, 48 (bản cũ: 1 entry 256×233)"))

    # 5. Apple touch: tô KÍN ô (iOS bỏ alpha, nền trong suốt bị thành đen)
    emit(
        "apple-touch-icon.png",
        badge(mark_sq, 180, disc=False, ratio=FULLBLEED_RATIO["apple-touch-icon.png"], bg=PLATE),
        "180×180, nền đặc (iOS không xử lý alpha)",
    )

    # 6. PWA icon: đĩa nền sáng, cùng hình với favicon
    for px in (192, 512):
        emit(
            f"icon-{px}.png",
            badge(mark_im, px, disc=True, ratio=DISC_RATIO, bg=PLATE),
            f"{px}×{px}, đĩa {PLATE_HEX} + mực gốc",
        )

    # 7. Maskable: tô kín ô, hình trong 80% giữa (launcher cắt tới 20% mỗi cạnh)
    emit(
        "icon-512-maskable.png",
        badge(mark_sq, 512, disc=False, ratio=MASKABLE_SAFE, bg=PLATE),
        f"512×512, nền đặc, hình trong {int(MASKABLE_SAFE * 100)}% giữa",
    )

    # 8. icon.svg + src/ui/logo-path.ts — CÙNG một dữ liệu path.
    #
    # Vì sao sinh cả tệp TS: `Logo.tsx` (sidebar) và favicon phải là CÙNG một ý
    # tưởng thị giác. Nếu chép path vào hai nơi thì sớm muộn chúng lệch nhau —
    # đúng thứ đang phải sửa. Nên script này là nguồn duy nhất, cả hai đều đọc từ nó.
    #
    # Nền là đĩa sáng (không trong suốt) — cùng lý do tương phản ở khối `PLATE`.
    #
    # `fill-rule="evenodd"` là BẮT BUỘC: path trace ra có 15 vòng rời, và 13
    # trong số đó quay CÙNG chiều. Với `nonzero` (mặc định) các vòng cùng chiều
    # cộng dồn winding number → nét trong bị tô đặc, mất khe hở. Đo được: evenodd
    # 0.87–0.90 so với nonzero 0.82 ở mọi cỡ. Xem `Logo.tsx` cho bản đối chiếu.
    path = trace_svg_path(src)
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" '
        'width="100" height="100" role="img" aria-label="NHỊP QUÁN">\n'
        f'  <circle cx="50" cy="50" r="50" fill="{PLATE_HEX}"/>\n'
        f'  <path d="{path}" fill="{INK_HEX}" fill-rule="evenodd"/>\n'
        "</svg>\n"
    )
    made.append(("icon.svg", "path ly + nhịp tim, cùng dữ liệu với Logo.tsx"))
    if write:
        (out_dir / "icon.svg").write_text(svg, encoding="utf-8")
        LOGO_TS.parent.mkdir(parents=True, exist_ok=True)
        LOGO_TS.write_text(render_logo_ts(path), encoding="utf-8")
    made.append((str(LOGO_TS.relative_to(ROOT)).replace("\\", "/"), "hằng số path cho Logo.tsx"))
    return made


def render_logo_ts(path: str) -> str:
    """Sinh `src/ui/logo-path.ts` — hằng số path dùng chung cho Logo.tsx và icon.svg."""
    rings = [seg + "Z" for seg in path.split("Z") if seg.strip()]
    body = "".join(f'  "{ring}",\n' for ring in rings)
    return (
        "/* SINH TỰ ĐỘNG — đừng sửa tay.\n"
        " *\n"
        " * Nguồn: `docs/hinh/logo.png`, sinh bởi `python scripts/gen_app_icons.py`.\n"
        " *\n"
        " * Vì sao để path ở tệp riêng thay vì viết thẳng trong `Logo.tsx`: dấu quán\n"
        " * xuất hiện ở HAI nơi — sidebar (`Logo.tsx`) và favicon/`icon.svg`. Hai nơi\n"
        " * chép tay hai bản path thì sớm muộn lệch nhau; đúng lỗi đang phải sửa (dấu\n"
        " * quán một đằng, favicon một nẻo). Nên chỉ có MỘT nguồn: script sinh ra tệp\n"
        " * này, `Logo.tsx` và `icon.svg` cùng đọc từ đây.\n"
        " *\n"
        " * Toạ độ trong `viewBox` 100×100, đã canh giữa và chiếm 60 đơn vị — vừa lọt\n"
        " * vòng tròn nét gạch `r=45` mà `Logo.tsx` vẽ quanh nó.\n"
        " */\n"
        "\n"
        "/** Từng vòng của dấu quán (ly cà phê + đường nhịp tim), đã đóng kín. */\n"
        "export const LOGO_RINGS: readonly string[] = [\n"
        f"{body}"
        "];\n"
        "\n"
        "/** Cả dấu quán thành một chuỗi `d` duy nhất — dùng cho `<path>` của SVG. */\n"
        "export const LOGO_PATH_D = LOGO_RINGS.join(\"\");\n"
    )


def check_drift() -> int:
    """Kiểm tệp đã sinh có còn khớp nguồn `docs/hinh/logo.png` hay không.

    Vì sao cần: `logo-path.ts` và bộ icon là **dẫn xuất** của ảnh gốc. Ai đó sửa
    tay một trong hai (hoặc đổi ảnh gốc mà không sinh lại) thì sidebar và favicon
    lệch nhau trở lại — đúng lỗi mà lần này phải dứt điểm. Cổng này phát hiện
    đúng lúc đó, thay vì để phát hiện bằng mắt trên production.

    Không cần byte-identical với PNG (Pillow có thể đổi encoder giữa các phiên
    bản): chỉ so phần **quyết định hình dạng** — nội dung `logo-path.ts` và
    phần `d` của `icon.svg`.
    """
    path = trace_svg_path(SRC)
    problems: list[str] = []

    expected_ts = render_logo_ts(path)
    if not LOGO_TS.exists():
        problems.append(f"THIẾU {LOGO_TS.relative_to(ROOT)}")
    elif LOGO_TS.read_text(encoding="utf-8") != expected_ts:
        problems.append(f"LỆCH {LOGO_TS.relative_to(ROOT)} (chạy lại script để sinh)")

    svg_p = PUB / "icon.svg"
    if not svg_p.exists():
        problems.append("THIẾU apps/web/public/icon.svg")
    elif f'<path d="{path}"' not in svg_p.read_text(encoding="utf-8"):
        problems.append("LỆCH apps/web/public/icon.svg")

    for name in (
        "favicon.ico",
        "favicon-16x16.png",
        "favicon-32x32.png",
        "favicon-48x48.png",
        "apple-touch-icon.png",
        "icon-192.png",
        "icon-512.png",
        "icon-512-maskable.png",
    ):
        if not (PUB / name).exists():
            problems.append(f"THIẾU apps/web/public/{name}")

    # Cấu trúc ICO: bản cũ hỏng đúng ở đây (1 entry, không vuông) nên phải kiểm.
    ico = PUB / "favicon.ico"
    if ico.exists():
        raw = ico.read_bytes()
        if len(raw) >= 6:
            count = int.from_bytes(raw[4:6], "little")
            if count < 2:
                problems.append(f"favicon.ico chỉ có {count} entry (cần ≥2: 16 + 32)")
            else:
                for i in range(count):
                    off = 6 + i * 16
                    w_, h_ = raw[off], raw[off + 1]
                    if w_ != h_:
                        problems.append(f"favicon.ico entry {i} KHÔNG vuông ({w_ or 256}×{h_ or 256})")

    if problems:
        print("Cổng icon: ĐỎ")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("Cổng icon: XANH — icon và logo-path.ts khớp nguồn docs/hinh/logo.png")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Sinh bộ icon cho NHỊP QUÁN từ docs/hinh/logo.png")
    ap.add_argument("--kiem-tra", action="store_true", help="chỉ liệt kê + đo, không ghi")
    ap.add_argument(
        "--kiem-drift",
        action="store_true",
        help="kiểm tệp đã sinh có còn khớp nguồn không (dùng cho CI/pre-push)",
    )
    ap.add_argument("--trace-svg", action="store_true", help="in path SVG đã trace")
    args = ap.parse_args()

    if not SRC.exists():
        raise SystemExit(f"thiếu ảnh gốc {SRC}")

    if args.trace_svg:
        print(trace_svg_path())
        return 0

    if args.kiem_drift:
        return check_drift()

    logo = Image.open(SRC).convert("RGBA")
    print(f"nguồn  : {SRC.relative_to(ROOT)}  {logo.size[0]}×{logo.size[1]}")
    print(f"đích   : {PUB.relative_to(ROOT)}/")
    print(f"chế độ : {'KIỂM TRA (không ghi)' if args.kiem_tra else 'GHI'}\n")

    made = build_icons(SRC, PUB, write=not args.kiem_tra)
    for name, desc in made:
        p = PUB / name
        size = f"{p.stat().st_size:>8,} B" if p.exists() and not args.kiem_tra else " " * 10
        print(f"  {name:<26}{size}  {desc}")

    print("\nđối chiếu trace (IoU path ↔ mask gốc):")
    for k, v in trace_fidelity(SRC).items():
        print(f"  {k:>7}  {v}")

    if args.kiem_tra:
        print("\n(không ghi gì — bỏ --kiem-tra để sinh thật)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
