import os
from unittest.mock import MagicMock, patch
import pytest

from oreilly_downloader.core.auth import HeadlessAutoLoginFailed
from oreilly_downloader.core.batch import BatchProcessor
from oreilly_downloader.core.browsers.chrome import ChromeBrowser
from oreilly_downloader.core.browsers.firefox import FirefoxBrowser
from oreilly_downloader.core.browsers.profile_lock import (
    CHROME_LOCK_FILES,
    FIREFOX_LOCK_FILES,
    ProfileLockCleaner,
)
from oreilly_downloader.core.browsers.stealth import StealthChromeBrowser
from oreilly_downloader.core.config import DownloaderConfig
from oreilly_downloader.core.orchestrator import CourseOrchestrator
from oreilly_downloader.core.utils import SanityUtils, ensure_headless_if_no_display


# --- SanityUtils.has_display() combinations ---

def test_has_display_linux_env_combinations(monkeypatch):
    if os.name == "nt":
        assert SanityUtils.has_display() is True
        return

    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    with patch("os.uname", return_value=type("U", (), {"sysname": "Linux"})()):
        assert SanityUtils.has_display() is False

        monkeypatch.setenv("DISPLAY", "   ")
        assert SanityUtils.has_display() is False

        monkeypatch.setenv("DISPLAY", ":0")
        assert SanityUtils.has_display() is True

        monkeypatch.delenv("DISPLAY", raising=False)
        monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
        assert SanityUtils.has_display() is True


def test_has_display_macos_always_true(monkeypatch):
    if os.name == "nt":
        return
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    with patch("os.uname", return_value=type("U", (), {"sysname": "Darwin"})()):
        assert SanityUtils.has_display() is True


# --- ProfileLockCleaner stale lock & symlink cleanup ---

def test_cleanup_stale_linux_chrome_locks_including_broken_symlinks(tmp_path):
    prof = tmp_path / "browser_profile_stealth"
    prof.mkdir()

    # Broken symlink (SingletonLock on Linux after crash/container reboot)
    singleton_lock = prof / "SingletonLock"
    os.symlink("dead-container-999999", singleton_lock)
    singleton_cookie = prof / "SingletonCookie"
    os.symlink("1234567890", singleton_cookie)
    singleton_socket = prof / "SingletonSocket"
    singleton_socket.write_text("", encoding="utf-8")
    win_lock = prof / "lockfile"
    win_lock.write_text("", encoding="utf-8")

    # Sanity: os.path.exists is False for broken symlinks, lexists is True
    assert not os.path.exists(singleton_lock)
    assert os.path.lexists(singleton_lock)

    with patch.object(ProfileLockCleaner, "find_locking_pids", return_value=[]):
        ProfileLockCleaner.cleanup_stale_locks(str(prof), CHROME_LOCK_FILES)

    for name in CHROME_LOCK_FILES:
        assert not os.path.lexists(prof / name)


def test_cleanup_stale_firefox_locks(tmp_path):
    prof = tmp_path / "firefox_profile"
    prof.mkdir()
    for name in FIREFOX_LOCK_FILES:
        (prof / name).write_text("lock", encoding="utf-8")

    with patch.object(ProfileLockCleaner, "find_locking_pids", return_value=[]):
        ProfileLockCleaner.cleanup_stale_locks(str(prof), FIREFOX_LOCK_FILES)

    for name in FIREFOX_LOCK_FILES:
        assert not os.path.lexists(prof / name)


def test_is_browser_cmdline_matches_only_browser_processes(tmp_path):
    prof = str(tmp_path / "browser_profile_stealth")
    assert ProfileLockCleaner._is_browser_cmdline(
        f"/usr/bin/google-chrome --user-data-dir={prof} --headless=new", prof
    )
    assert ProfileLockCleaner._is_browser_cmdline(
        f"/usr/bin/firefox -profile {prof}", prof
    )
    # Must NOT match unrelated commands mentioning the directory
    assert not ProfileLockCleaner._is_browser_cmdline(
        f"pytest {prof}/test.py", prof
    )
    assert not ProfileLockCleaner._is_browser_cmdline(
        "/usr/bin/google-chrome --user-data-dir=/other/dir", prof
    )


# --- Error diagnosis: must NOT misreport startup crashes as profile locks ---

def test_format_browser_start_error_startup_crash_not_reported_as_lock(tmp_path):
    prof = str(tmp_path / "browser_profile_stealth")
    exc = RuntimeError("Message: session not created: cannot connect to chrome at 127.0.0.1:45678")

    with patch("oreilly_downloader.core.browsers.profile_lock.SanityUtils.has_display", return_value=True), \
         patch("oreilly_downloader.core.browsers.profile_lock.Logger.error") as mock_err:
        result = ProfileLockCleaner.format_browser_start_error(
            exc, prof, browser_name="Chrome", headless=True, had_locking_pids=[]
        )

    assert isinstance(result, RuntimeError)
    assert "failed to start" in str(result).lower()
    assert "locked" not in str(result).lower()
    assert "task manager" not in str(result).lower()
    assert all("Profile Lock" not in str(c) for c in mock_err.call_args_list)


def test_format_browser_start_error_real_lock_reports_pids(tmp_path):
    prof = str(tmp_path / "browser_profile_stealth")
    exc = RuntimeError("Message: cannot connect to chrome at 127.0.0.1:45678")

    with patch("oreilly_downloader.core.browsers.profile_lock.SanityUtils.has_display", return_value=True), \
         patch("oreilly_downloader.core.browsers.profile_lock.Logger.error") as mock_err:
        result = ProfileLockCleaner.format_browser_start_error(
            exc, prof, browser_name="Chrome", headless=True, had_locking_pids=[4242]
        )

    assert "4242" in str(result)
    assert "locked by active processes" in str(result)
    assert any("Browser Profile Lock Detected" in str(c) for c in mock_err.call_args_list)


def test_format_browser_start_error_no_display_headed(tmp_path):
    prof = str(tmp_path / "browser_profile_stealth")
    exc = RuntimeError("cannot connect to chrome")

    with patch("oreilly_downloader.core.browsers.profile_lock.SanityUtils.has_display", return_value=False):
        result = ProfileLockCleaner.format_browser_start_error(
            exc, prof, browser_name="Chrome", headless=False, had_locking_pids=[]
        )

    assert "no graphical display" in str(result).lower()
    assert "--headless" in str(result)


# --- Browser.start() combinations across Stealth, Chrome, Firefox ---

@pytest.mark.parametrize("browser_cls", [StealthChromeBrowser, ChromeBrowser, FirefoxBrowser])
def test_headed_browser_without_display_fails_fast_with_clear_error(browser_cls):
    browser = browser_cls(headless=False)
    with patch("oreilly_downloader.core.browsers.profile_lock.SanityUtils.has_display", return_value=False):
        with pytest.raises(RuntimeError) as exc_info:
            browser.start()
    assert "no graphical display" in str(exc_info.value).lower()
    assert "--headless" in str(exc_info.value)


def test_stealth_browser_cleans_failed_launch_and_handles_version_mismatch(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    browser = StealthChromeBrowser(headless=True)
    mock_driver = MagicMock()

    with patch("oreilly_downloader.core.utils.SanityUtils.get_chrome_path", return_value="/usr/bin/google-chrome"), \
         patch("oreilly_downloader.core.browsers.stealth.uc.Chrome", side_effect=[
             RuntimeError("This version of ChromeDriver only supports Chrome version 120. Current browser version is 158"),
             mock_driver,
         ]) as mock_uc, \
         patch.object(ProfileLockCleaner, "kill_zombie_processes") as mock_kill, \
         patch.object(ProfileLockCleaner, "remove_lock_files") as mock_rm:
        driver = browser.start()

    assert driver.raw_driver is mock_driver
    assert mock_uc.call_count == 2
    assert mock_uc.call_args_list[1].kwargs["version_main"] == 158
    assert mock_kill.called
    assert mock_rm.called

    # stop() safely quits and cleans up
    browser.stop()
    mock_driver.quit.assert_called_once()
    assert browser.raw_driver is None


def test_stealth_browser_stop_resilient_when_quit_raises(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    browser = StealthChromeBrowser(headless=True)
    browser._profile_dir = str(tmp_path / "browser_profile_stealth")
    mock_raw = MagicMock()
    mock_raw.quit.side_effect = RuntimeError("already dead")
    browser.raw_driver = mock_raw

    with patch.object(ProfileLockCleaner, "kill_zombie_processes") as mock_kill, \
         patch.object(ProfileLockCleaner, "remove_lock_files") as mock_rm:
        browser.stop()

    assert browser.raw_driver is None
    assert browser.driver is None
    mock_kill.assert_called_once_with(browser._profile_dir)
    mock_rm.assert_called_once_with(browser._profile_dir, CHROME_LOCK_FILES)


# --- Orchestrator & BatchProcessor display-less auto-headless & fallback ---

def test_ensure_headless_if_no_display_auto_switches_for_downloads():
    cfg = DownloaderConfig(url="https://learning.oreilly.com/course/test/1/", headless=False)
    with patch("oreilly_downloader.core.utils.SanityUtils.has_display", return_value=False):
        ok = ensure_headless_if_no_display(cfg)
    assert ok is True
    assert cfg.headless is True


def test_ensure_headless_if_no_display_blocks_manual_login():
    cfg = DownloaderConfig(manual_login=True, headless=False)
    with patch("oreilly_downloader.core.utils.SanityUtils.has_display", return_value=False):
        ok = ensure_headless_if_no_display(cfg)
    assert ok is False


def test_orchestrator_auto_switches_to_headless_without_display():
    cfg = DownloaderConfig(url="https://learning.oreilly.com/course/test/1/", headless=False)
    mock_bm = MagicMock()
    mock_bm.start.return_value = MagicMock()
    mock_create = MagicMock(return_value=mock_bm)

    with patch("oreilly_downloader.core.utils.SanityUtils.has_display", return_value=False):
        orch = CourseOrchestrator(
            config=cfg,
            browser_factory_create=mock_create,
            auth_handler=lambda driver, auth, c: False,
        )
        result = orch.execute()

    assert result is False
    assert cfg.headless is True
    mock_create.assert_called_once()
    assert mock_create.call_args.kwargs["headless"] is True
    mock_bm.stop.assert_called_once()


def test_orchestrator_manual_login_without_display_returns_false_without_starting_browser():
    cfg = DownloaderConfig(manual_login=True, headless=False)
    mock_create = MagicMock()

    with patch("oreilly_downloader.core.utils.SanityUtils.has_display", return_value=False):
        orch = CourseOrchestrator(config=cfg, browser_factory_create=mock_create)
        result = orch.execute()

    assert result is False
    mock_create.assert_not_called()


def test_orchestrator_headless_auto_login_failed_without_display_exits_cleanly():
    """When HeadlessAutoLoginFailed fires in a display-less container, orchestrator must NOT
    attempt a headed retry (which would waste time creating a browser that immediately crashes).
    It should return False immediately with a clear error message."""
    cfg = DownloaderConfig(url="https://learning.oreilly.com/course/test/1/", headless=False)
    mock_bm = MagicMock()
    mock_bm.start.return_value = MagicMock()
    mock_create = MagicMock(return_value=mock_bm)

    def auth_handler_raises_headless_fail(driver, auth, c):
        raise HeadlessAutoLoginFailed()

    with patch("oreilly_downloader.core.utils.SanityUtils.has_display", return_value=False), \
         patch("oreilly_downloader.core.orchestrator.SanityUtils.has_display", return_value=False):
        orch = CourseOrchestrator(
            config=cfg,
            browser_factory_create=mock_create,
            auth_handler=auth_handler_raises_headless_fail,
        )
        result = orch.execute()

    assert result is False
    assert cfg.headless is True
    # Browser was created exactly once (the headless attempt), never a second headed attempt
    mock_create.assert_called_once()
    assert mock_create.call_args.kwargs["headless"] is True
    mock_bm.stop.assert_called_once()


def test_batch_processor_auto_switches_headless_and_handles_auth_failure_without_display(tmp_path):
    batch_file = tmp_path / "urls.txt"
    batch_file.write_text("https://learning.oreilly.com/course/test/\n", encoding="utf-8")

    cfg = DownloaderConfig(url=None, output_dir=str(tmp_path), headless=False)
    mock_bm = MagicMock()
    mock_bm.start.return_value = MagicMock()

    with patch("oreilly_downloader.core.utils.SanityUtils.has_display", return_value=False), \
         patch("oreilly_downloader.core.batch.BrowserFactory.create", return_value=mock_bm) as mock_create, \
         patch("oreilly_downloader.core.batch.AuthService"), \
         patch("oreilly_downloader.core.batch.authenticate_session", side_effect=HeadlessAutoLoginFailed()):
        processor = BatchProcessor(cfg, batch_file_path=str(batch_file))
        results = processor.run()

    assert results == []
    assert cfg.headless is True
    mock_create.assert_called_once()
    assert mock_create.call_args.kwargs["headless"] is True
    mock_bm.stop.assert_called_once()
