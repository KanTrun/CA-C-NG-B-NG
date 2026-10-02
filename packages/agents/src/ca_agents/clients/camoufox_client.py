"""Camoufox browser lifecycle wrapper — optional dependency.

Camoufox là Firefox custom build chống fingerprint-detection, API Python
chính thức qua Playwright. Tier cào browser-thật cho AG-TREND (TikTok/Threads).

Package là OPTIONAL: chưa cài / chưa `camoufox fetch` / thiếu system deps
→ mọi hàm raise `CamoufoxUnavailable` → chuỗi source rớt tầng gracefully.

Public API:
    CamoufoxUnavailable        -- raise khi chưa cài `camoufox`, chưa `camoufox fetch`,
                                   HOẶC thiếu system deps để launch (phân biệt rõ trong message).
    is_available() -> bool     -- check nhanh: import + thử launch/close rỗng,
                                   cache kết quả 1 lần/process.
    scrape_page(url, extractor, timeout_s) -> Any
                                  -- launch browser → goto → extractor(page) → close,
                                   có retry (chỉ lỗi goto timeout/network) + concurrency guard.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

# ── Env config (lazy đọc mỗi lần gọi để test override được) ──
_DEFAULT_TIMEOUT_S = 45
_DEFAULT_MAX_CONCURRENT = 2
_RETRY_BACKOFF_S = 1.0
_MAX_ATTEMPTS = 2  # 1 lần chạy + 1 lần retry


class CamoufoxUnavailable(Exception):
    """Raised khi Camoufox không dùng được (chưa cài / chưa fetch / thiếu system deps)."""


class _GotoError(Exception):
    """Lỗi goto trang (timeout/network) — loại duy nhất được retry."""


def _env_flag(name: str, default: str = "1") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _is_enabled() -> bool:
    return _env_flag("CA_CAMOUFOX_ENABLED", "1")


def _is_headless() -> bool:
    return _env_flag("CA_CAMOUFOX_HEADLESS", "1")


def _get_timeout_s() -> int:
    return max(5, _env_int("CA_CAMOUFOX_TIMEOUT_S", _DEFAULT_TIMEOUT_S))


def _get_max_concurrent() -> int:
    return max(1, _env_int("CA_CAMOUFOX_MAX_CONCURRENT", _DEFAULT_MAX_CONCURRENT))


# Semaphore tạo lazy theo env hiện tại (test override env trước lần đầu gọi).
_semaphore_lock = threading.Lock()
_semaphore: threading.Semaphore | None = None


def _get_semaphore() -> threading.Semaphore:
    global _semaphore
    with _semaphore_lock:
        if _semaphore is None:
            _semaphore = threading.Semaphore(_get_max_concurrent())
        return _semaphore


def _reset_semaphore() -> None:
    """Reset semaphore (chỉ dùng trong test để override env)."""
    global _semaphore
    with _semaphore_lock:
        _semaphore = None


# Cache kết quả is_available 1 lần/process (tránh launch thử lặp lại mỗi request).
_availability_lock = threading.Lock()
_availability_cache: bool | None = None


def _classify_launch_error(e: Exception) -> str:
    """Phân loại lỗi launch để log hướng dẫn đúng (§1.4 — system deps vs binary)."""
    msg = str(e).lower()
    if "no such file" in msg or "not found" in msg or "fetch" in msg or "camoufox fetch" in msg:
        return "chưa chạy `camoufox fetch` (thiếu binary ~300MB)"
    if (
        "libgtk" in msg
        or "libasound" in msg
        or "dbus-glib" in msg
        or "x11" in msg
        or "shared library" in msg
        or "cannot open shared object" in msg
    ):
        return (
            "thiếu system deps Linux cho headless Firefox "
            "(libgtk-3-0, libasound2, libdbus-glib-1-2, libx11-xcb1, fonts...) — "
            "xem docs/runbooks/camoufox-scraping.md"
        )
    return f"launch lỗi khác: {type(e).__name__}: {e}"


def _install_dir() -> Any:
    """Thư mục cài thật của camoufox, hoặc None nếu không đọc được."""
    try:
        from camoufox.pkgman import INSTALL_DIR

        return INSTALL_DIR
    except Exception:  # noqa: BLE001 — chẩn đoán không được làm hỏng luồng chính
        return None


def _preflight() -> None:
    """Kiểm tra binary CÓ SẴN trước khi launch — chặn đường tự tải lại 300MB.

    `camoufox` không báo lỗi khi thiếu binary: `camoufox_path()` tự `install()`
    vài trăm MB vào container đang chạy. Trên VM production 20GB (đã từng chạm
    `no space left on device`) đó là đường hỏng, và nó biến một lỗi cấu hình
    thành một sự cố đĩa. Ở đây ta từ chối sớm, kèm đúng đường dẫn đang tìm.

    `CAMOUFOX_INSTALL_DIR` vừa ghim chỗ cài, vừa là công tắc: khi nó được đặt,
    camoufox bỏ qua hoàn toàn nhánh tự tải — nên chỉ cần kiểm tra tồn tại.
    """
    install_dir = _install_dir()
    if install_dir is None:
        return
    if os.path.isdir(install_dir) and os.listdir(install_dir):
        return
    raise CamoufoxUnavailable(
        f"thiếu binary Camoufox tại {install_dir} — "
        "dựng lại image với `CAMOUFOX_INSTALL_DIR=/opt/camoufox` + `python -m camoufox fetch` "
        "(xem infra/docker/Dockerfile.api và docs/runbooks/camoufox-scraping.md)"
    )


def _try_launch() -> None:
    """Import camoufox + thử launch/close rỗng. Raise CamoufoxUnavailable nếu fail."""
    try:
        from camoufox.sync_api import Camoufox  # lazy import — optional dep
    except ImportError as e:
        raise CamoufoxUnavailable(
            "chưa cài package `camoufox` — cài: pip install -U 'camoufox[geoip]'"
        ) from e

    _preflight()

    # Camoufox là optional dep không có type stub — cast để mypy strict khỏi
    # bac `no-untyped-call`; runtime không đổi.
    from typing import Any, cast

    CamoufoxT = cast(Any, Camoufox)
    try:
        cm = CamoufoxT(headless=True)
        browser = cm.__enter__()
        browser.new_page()  # verify binary + system deps thật sự chạy
        cm.__exit__(None, None, None)
    except Exception as e:  # noqa: BLE001
        raise CamoufoxUnavailable(_classify_launch_error(e)) from e


def is_available() -> bool:
    """
    Check nhanh Camoufox có dùng được không: import + launch/close rỗng.

    Cache kết quả 1 lần/process. Trả False ngay khi CA_CAMOUFOX_ENABLED=0.
    """
    global _availability_cache
    if not _is_enabled():
        return False
    with _availability_lock:
        if _availability_cache is not None:
            return _availability_cache
        try:
            _try_launch()
            _availability_cache = True
            logger.info("camoufox_available headless=%s", _is_headless())
        except CamoufoxUnavailable as e:
            _availability_cache = False
            logger.warning("camoufox_unavailable_skipping reason=%s", e)
        return _availability_cache


def _reset_availability_cache() -> None:
    """Reset cache availability (chỉ dùng trong test để override env)."""
    global _availability_cache
    with _availability_lock:
        _availability_cache = None


def _attempt_once(
    camoufox_cls: Any,
    url: str,
    extractor: Callable[[Any], Any],
    timeout_ms: int,
    user_data_dir: str | None = None,
) -> Any:
    """1 lần launch → goto → extract → close.

    Launch (constructor + __enter__) và body tách riêng để phân loại lỗi:
        - Lỗi launch (binary/system deps) → CamoufoxUnavailable (kèm hướng dẫn cài).
        - Lỗi goto (timeout/network)      → _GotoError (caller retry 1 lần).
        - Lỗi extractor (selector/parse)   → propagate thẳng, KHÔNG retry.

    Gọi __enter__/__exit__ thủ công thay vì `with` để lỗi extractor không
    rơi vào nhánh classify launch — browser vẫn luôn đóng trong finally.
    """
    # Camoufox 0.5.x BẮT BUỘC dùng `persistent_context=True` khi truyền
    # `user_data_dir` — nếu chỉ truyền `user_data_dir` thì Playwright raise
    # `TypeError: BrowserType.launch() got an unexpected keyword argument
    # 'user_data_dir'` (đo thực tế 2026-09-26). Thiếu cờ này khiến MỌI tầng cần
    # profile đăng nhập (Threads Trending Now) chết ngay từ lúc launch.
    launch_kwargs: dict[str, Any] = {
        "headless": _is_headless(),
        "geoip": True,
        "humanize": True,
    }
    if user_data_dir:
        launch_kwargs["persistent_context"] = True
        launch_kwargs["user_data_dir"] = user_data_dir

    try:
        cm = camoufox_cls(**launch_kwargs)
        browser = cm.__enter__()
    except Exception as e:  # noqa: BLE001
        raise CamoufoxUnavailable(_classify_launch_error(e)) from e

    try:
        page = browser.new_page() if hasattr(browser, "new_page") else browser
        try:
            page.goto(url, timeout=timeout_ms)
        except Exception as e:  # noqa: BLE001
            raise _GotoError(f"{type(e).__name__}: {e}") from e
        return extractor(page)
    finally:
        try:
            cm.__exit__(None, None, None)
        except Exception:  # noqa: BLE001 — cleanup lỗi không được nuốt lỗi gốc
            pass


def scrape_page(
    url: str,
    extractor: Callable[[Any], Any],
    timeout_s: int | None = None,
    user_data_dir: str | None = None,
) -> Any:
    """
    Launch Camoufox → goto url → chạy extractor(page) → đóng browser.

    Sync, gọi từ code sync trong ag_trend.py (route FastAPI offload qua
    threadpool riêng — không đụng event loop).

    Concurrency guard: semaphore CA_CAMOUFOX_MAX_CONCURRENT (default 2) bao
    quanh phần launch — vượt giới hạn → chờ, không launch vô hạn Firefox.

    Retry: 1 lần backoff ~1s, CHỈ cho lỗi goto timeout/network. Lỗi extractor
    (logic selector) và lỗi launch (binary/system deps) raise thẳng để chuỗi
    rớt tầng ngay.

    Args:
        url:           trang cần cào (vd: https://www.tiktok.com/search?q=...).
        extractor:     hàm nhận Playwright page, trả dữ liệu đã extract.
        timeout_s:     timeout goto + extract (default env CA_CAMOUFOX_TIMEOUT_S=45).
        user_data_dir: đường dẫn profile lưu session đăng nhập (optional).

    Raises:
        CamoufoxUnavailable: chưa cài / chưa fetch / thiếu system deps / bị tắt qua env.
        Exception gốc:       lỗi goto sau khi retry hết, hoặc lỗi extractor propagate.

    Returns:
        Kết quả extractor(page).
    """
    if not _is_enabled():
        raise CamoufoxUnavailable("CA_CAMOUFOX_ENABLED=0 — tier Camoufox bị tắt")

    try:
        from camoufox.sync_api import Camoufox  # lazy import — optional dep
    except ImportError as e:
        raise CamoufoxUnavailable(
            "chưa cài package `camoufox` — cài: pip install -U 'camoufox[geoip]'"
        ) from e

    effective_timeout = _get_timeout_s() if timeout_s is None else max(5, timeout_s)
    effective_profile = user_data_dir or os.getenv("CA_THREADS_USER_DATA_DIR") or os.getenv("CA_CAMOUFOX_USER_DATA_DIR")
    semaphore = _get_semaphore()

    last_goto_error: _GotoError | None = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        # Concurrency guard: chờ slot — không launch vô hạn browser song song (OOM).
        with semaphore:
            try:
                return _attempt_once(
                    Camoufox,
                    url,
                    extractor,
                    effective_timeout * 1000,
                    user_data_dir=effective_profile,
                )
            except _GotoError as goto_err:
                last_goto_error = goto_err
        # Backoff NGOÀI semaphore — không giữ slot khi chờ retry.
        if attempt < _MAX_ATTEMPTS:
            logger.warning(
                "camoufox_scrape_retry attempt=%d/%d url=%s error=%s",
                attempt,
                _MAX_ATTEMPTS,
                url[:80],
                last_goto_error,
            )
            time.sleep(_RETRY_BACKOFF_S)

    # Retry hết — re-raise lỗi goto gốc (giữ type gốc: TimeoutError/network...).
    cause = last_goto_error.__cause__ if last_goto_error is not None else None
    if cause is not None:
        raise cause
    raise TimeoutError(f"camoufox scrape_page fail sau {_MAX_ATTEMPTS} lần: {url[:80]}")
