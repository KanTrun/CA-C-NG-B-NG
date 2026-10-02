# mypy: disable-error-code="no-untyped-def,no-untyped-call,type-arg,no-any-return,unused-ignore"
"""Test camoufox_client — mock toàn bộ, không mở browser thật (CA_AGENT_MODE=replay).

Cover theo PR 1 §IV:
    - ImportError path (chưa cài package)
    - Thiếu-binary path (chưa `camoufox fetch`)
    - Launch-lỗi-system-deps path
    - Timeout path
    - Retry path (1 lần backoff, chỉ lỗi goto)
    - Extractor được gọi
    - Browser luôn đóng kể cả khi extractor raise
    - Concurrency guard (semaphore) chặn đúng số lượng
"""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path
from types import ModuleType
from typing import Any
from unittest.mock import MagicMock

import pytest
from ca_agents.clients import camoufox_client
from ca_agents.clients.camoufox_client import (
    CamoufoxUnavailable,
    is_available,
    scrape_page,
)


def _stub_sync_api(fake_camoufox: MagicMock) -> ModuleType:
    """Tạo stub module camoufox.sync_api với attribute Camoufox = fake."""
    stub = ModuleType("camoufox.sync_api")
    stub.Camoufox = fake_camoufox  # type: ignore[attr-defined]
    return stub


def _install_camoufox(monkeypatch: pytest.MonkeyPatch, fake_camoufox: MagicMock) -> None:
    """Cài fake module camoufox.sync_api vào sys.modules."""
    monkeypatch.setitem(sys.modules, "camoufox.sync_api", _stub_sync_api(fake_camoufox))


def _remove_camoufox(monkeypatch: pytest.MonkeyPatch) -> None:
    """Giả lập package chưa cài: xóa module khỏi sys.modules."""
    monkeypatch.setitem(sys.modules, "camoufox", None)
    monkeypatch.setitem(sys.modules, "camoufox.sync_api", None)


@pytest.fixture(autouse=True)
def _reset_caches(monkeypatch: pytest.MonkeyPatch):
    """Reset cache availability + semaphore trước mỗi test (env override được)."""
    monkeypatch.setenv("CA_CAMOUFOX_ENABLED", "1")
    monkeypatch.setenv("CA_CAMOUFOX_HEADLESS", "1")
    monkeypatch.setenv("CA_CAMOUFOX_TIMEOUT_S", "45")
    monkeypatch.setenv("CA_CAMOUFOX_MAX_CONCURRENT", "2")
    camoufox_client._reset_availability_cache()
    camoufox_client._reset_semaphore()
    yield
    camoufox_client._reset_availability_cache()
    camoufox_client._reset_semaphore()


def _make_fake_camoufox(launch_error: Exception | None = None) -> MagicMock:
    """Fake camoufox.sync_api.Camoufox — context manager launch/close.

    Camoufox sync API là context manager: constructor + __enter__ = launch,
    __exit__ = close + teardown Playwright. Mock __enter__ trả về browser
    mock, __exit__ trả False (không nuốt exception).
    """
    fake = MagicMock()
    browser = MagicMock()
    fake.return_value.__enter__.return_value = browser
    fake.return_value.__exit__.return_value = False
    if launch_error is not None:
        fake.side_effect = launch_error
    return fake


# ── ImportError path ──


def test_is_available_false_when_package_missing(monkeypatch: pytest.MonkeyPatch):
    """Chưa cài package camoufox → is_available False, không raise."""
    _remove_camoufox(monkeypatch)
    assert is_available() is False


def test_scrape_page_raises_unavailable_when_package_missing(monkeypatch: pytest.MonkeyPatch):
    """scrape_page với camoufox chưa cài → CamoufoxUnavailable với message hướng dẫn."""
    _remove_camoufox(monkeypatch)
    with pytest.raises(CamoufoxUnavailable, match="chưa cài package"):
        scrape_page("https://example.com", lambda page: None)


# ── Thiếu-binary path ──


def test_is_available_false_when_binary_not_fetched(monkeypatch: pytest.MonkeyPatch):
    """Đã cài package nhưng chưa `camoufox fetch` → phân loại lỗi binary."""
    fake = _make_fake_camoufox(
        launch_error=FileNotFoundError("Camoufox binary not found — run `camoufox fetch`")
    )
    _install_camoufox(monkeypatch, fake)
    assert is_available() is False


def test_scrape_page_raises_unavailable_when_binary_missing(monkeypatch: pytest.MonkeyPatch):
    """scrape_page khi thiếu binary → CamoufoxUnavailable phân loại 'chưa fetch'."""
    fake = _make_fake_camoufox(
        launch_error=FileNotFoundError("No such file or directory: camoufox binary")
    )
    _install_camoufox(monkeypatch, fake)
    with pytest.raises(CamoufoxUnavailable, match="camoufox fetch"):
        scrape_page("https://example.com", lambda page: None)


# ── Preflight: chặn đường tự tải lại 300MB (sự cố 2026-10-02) ──


def test_preflight_blocks_when_install_dir_missing(monkeypatch: pytest.MonkeyPatch):
    """Thư mục cài không tồn tại → chặn TRƯỚC khi launch.

    `camoufox` không báo lỗi khi thiếu binary: nó tự `install()` vài trăm MB vào
    container đang chạy. Trên VM production 20GB (đã từng chạm `no space left on
    device`) đường đó vừa hỏng vừa nguy hiểm, nên phải từ chối sớm.
    """
    monkeypatch.setattr(
        camoufox_client, "_install_dir", lambda: Path("/khong/ton/tai/camoufox")
    )
    fake = _make_fake_camoufox()
    _install_camoufox(monkeypatch, fake)

    with pytest.raises(CamoufoxUnavailable, match="thiếu binary Camoufox"):
        camoufox_client._try_launch()

    # Chốt quan trọng: KHÔNG được chạm tới launch (tức không kích hoạt auto-install).
    assert not fake.called, "preflight phải chặn trước khi gọi Camoufox()"


def test_preflight_passes_when_install_dir_populated(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    """Thư mục cài có dữ liệu → preflight cho qua, launch diễn ra bình thường."""
    (tmp_path / "version.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(camoufox_client, "_install_dir", lambda: tmp_path)
    fake = _make_fake_camoufox()
    _install_camoufox(monkeypatch, fake)

    camoufox_client._try_launch()

    assert fake.called, "preflight không được chặn khi binary có sẵn"


def test_preflight_ignores_empty_install_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Thư mục tồn tại nhưng RỖNG cũng là thiếu binary — `camoufox fetch` chưa chạy."""
    assert tmp_path.is_dir() and not list(tmp_path.iterdir())
    monkeypatch.setattr(camoufox_client, "_install_dir", lambda: tmp_path)

    with pytest.raises(CamoufoxUnavailable, match="thiếu binary Camoufox"):
        camoufox_client._preflight()


def test_preflight_never_raises_when_introspection_fails(monkeypatch: pytest.MonkeyPatch):
    """Không đọc được INSTALL_DIR → bỏ qua preflight, không chặn oan.

    Chẩn đoán hỏng KHÔNG được biến thành lỗi nghiệp vụ: nếu nhánh này raise thì
    một thay đổi nội bộ của `camoufox` sẽ làm chết cả tính năng khảo sát.
    """
    monkeypatch.setattr(camoufox_client, "_install_dir", lambda: None)
    camoufox_client._preflight()  # không raise là đạt


# ── System-deps path ──


def test_is_available_false_when_system_deps_missing(monkeypatch: pytest.MonkeyPatch):
    """Thiếu system libs Linux (libgtk...) → phân loại lỗi system deps, không phải binary."""
    fake = _make_fake_camoufox(
        launch_error=OSError(
            "libgtk-3.so.0: cannot open shared object file: No such file or directory"
        )
    )
    _install_camoufox(monkeypatch, fake)
    assert is_available() is False


def test_scrape_page_raises_unavailable_when_system_deps_missing(monkeypatch: pytest.MonkeyPatch):
    fake = _make_fake_camoufox(
        launch_error=OSError("libasound.so.2: cannot open shared object file")
    )
    _install_camoufox(monkeypatch, fake)
    with pytest.raises(CamoufoxUnavailable, match="system deps"):
        scrape_page("https://example.com", lambda page: None)


# ── Happy path ──


def test_is_available_true_when_launch_ok(monkeypatch: pytest.MonkeyPatch):
    fake = _make_fake_camoufox()
    _install_camoufox(monkeypatch, fake)
    assert is_available() is True
    # Cache 1 lần/process: lần 2 không launch lại.
    assert is_available() is True
    assert fake.call_count == 1


def test_scrape_page_calls_extractor_and_closes_browser(monkeypatch: pytest.MonkeyPatch):
    """Launch → goto → extractor → close. Extractor nhận đúng page object."""
    fake = _make_fake_camoufox()
    _install_camoufox(monkeypatch, fake)

    result = scrape_page("https://www.tiktok.com/search?q=test", lambda p: {"page": p})
    assert result["page"] is not None
    browser = fake.return_value.__enter__.return_value
    assert browser.new_page.call_count == 1
    page = browser.new_page.return_value
    page.goto.assert_called_once_with("https://www.tiktok.com/search?q=test", timeout=45 * 1000)
    fake.return_value.__exit__.assert_called_once()


def test_scrape_page_browser_closed_even_when_extractor_raises(monkeypatch: pytest.MonkeyPatch):
    """Extractor raise → browser vẫn phải close trong finally (không leak process)."""
    fake = _make_fake_camoufox()
    _install_camoufox(monkeypatch, fake)

    def bad_extractor(page: Any) -> Any:
        raise ValueError("selector không match")

    with pytest.raises(ValueError, match="selector không match"):
        scrape_page("https://example.com", bad_extractor)
    fake.return_value.__exit__.assert_called_once()


# ── Timeout + retry path ──


def test_scrape_page_retries_once_on_goto_timeout(monkeypatch: pytest.MonkeyPatch):
    """Goto timeout lần 1 → retry 1 lần (backoff ngắn) → lần 2 thành công."""
    fake = _make_fake_camoufox()
    _install_camoufox(monkeypatch, fake)
    monkeypatch.setattr(camoufox_client, "_RETRY_BACKOFF_S", 0.01)

    page = fake.return_value.__enter__.return_value.new_page.return_value
    page.goto.side_effect = [
        TimeoutError("net::ERR_TIMED_OUT"),  # lần 1 fail
        None,  # lần 2 ok
    ]
    result = scrape_page("https://example.com", lambda p: "ok")
    assert result == "ok"
    assert page.goto.call_count == 2
    # mỗi attempt đóng browser riêng (2 lần __exit__)
    assert fake.return_value.__exit__.call_count == 2


def test_scrape_page_raises_original_after_retry_exhausted(monkeypatch: pytest.MonkeyPatch):
    """Goto timeout cả 2 lần → raise lỗi gốc (TimeoutError) để chuỗi rớt tầng."""
    fake = _make_fake_camoufox()
    _install_camoufox(monkeypatch, fake)
    monkeypatch.setattr(camoufox_client, "_RETRY_BACKOFF_S", 0.01)

    page = fake.return_value.__enter__.return_value.new_page.return_value
    page.goto.side_effect = TimeoutError("net::ERR_TIMED_OUT")
    with pytest.raises(TimeoutError):
        scrape_page("https://example.com", lambda p: "ok")
    assert page.goto.call_count == 2


def test_scrape_page_no_retry_on_extractor_error(monkeypatch: pytest.MonkeyPatch):
    """Extractor raise (lỗi logic, không phải network) → không retry, raise ngay."""
    fake = _make_fake_camoufox()
    _install_camoufox(monkeypatch, fake)

    calls: list[int] = []

    def bad_extractor(page: Any) -> Any:
        calls.append(1)
        raise ValueError("DOM đổi")

    with pytest.raises(ValueError):
        scrape_page("https://example.com", bad_extractor)
    assert len(calls) == 1  # không retry


# ── Env config ──


def test_scrape_page_disabled_raises_unavailable(monkeypatch: pytest.MonkeyPatch):
    """CA_CAMOUFOX_ENABLED=0 → raise ngay, không đụng browser."""
    monkeypatch.setenv("CA_CAMOUFOX_ENABLED", "0")
    with pytest.raises(CamoufoxUnavailable, match="CA_CAMOUFOX_ENABLED=0"):
        scrape_page("https://example.com", lambda p: None)


def test_is_available_false_when_disabled(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CA_CAMOUFOX_ENABLED", "0")
    assert is_available() is False


def test_scrape_page_timeout_env_override(monkeypatch: pytest.MonkeyPatch):
    """CA_CAMOUFOX_TIMEOUT_S override → goto nhận timeout tương ứng (ms)."""
    fake = _make_fake_camoufox()
    _install_camoufox(monkeypatch, fake)
    monkeypatch.setenv("CA_CAMOUFOX_TIMEOUT_S", "30")
    scrape_page("https://example.com", lambda p: None)
    page = fake.return_value.__enter__.return_value.new_page.return_value
    page.goto.assert_called_once_with("https://example.com", timeout=30 * 1000)


# ── Concurrency guard ──


def test_semaphore_blocks_beyond_max_concurrent(monkeypatch: pytest.MonkeyPatch):
    """MAX_CONCURRENT=2 → tối đa 2 browser mở song song, cái thứ 3 chờ."""
    fake = _make_fake_camoufox()
    _install_camoufox(monkeypatch, fake)
    monkeypatch.setenv("CA_CAMOUFOX_MAX_CONCURRENT", "2")
    camoufox_client._reset_semaphore()

    active = 0
    peak = 0
    lock = threading.Lock()

    def slow_extractor(page: Any) -> Any:
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(0.15)
        with lock:
            active -= 1
        return "ok"

    threads = [
        threading.Thread(target=lambda: scrape_page("https://example.com", slow_extractor))
        for _ in range(4)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert peak == 2  # không bao giờ quá 2 browser song song
