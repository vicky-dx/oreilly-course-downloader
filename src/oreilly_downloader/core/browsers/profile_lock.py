import os
import shutil
import signal
import subprocess
import time
from typing import Iterable, List, Optional, Tuple
from colorama import Fore

from .logger import Logger
from ..utils import SanityUtils

CHROME_LOCK_FILES: Tuple[str, ...] = (
    "lockfile",
    "SingletonLock",
    "SingletonCookie",
    "SingletonSocket",
)

FIREFOX_LOCK_FILES: Tuple[str, ...] = (
    "parent.lock",
    ".parentlock",
    "lock",
)

_BROWSER_BIN_MARKERS: Tuple[str, ...] = (
    "chrome",
    "chromium",
    "chromedriver",
    "brave",
    "msedge",
    "firefox",
    "geckodriver",
)


class ProfileLockCleaner:
    """Cross-platform browser profile lock detection, zombie cleanup, and error diagnosis."""

    @staticmethod
    def _is_browser_cmdline(cmdline: str, profile_dir: str) -> bool:
        if not cmdline:
            return False
        abs_prof = os.path.abspath(profile_dir)
        real_prof = os.path.realpath(profile_dir)
        if profile_dir not in cmdline and abs_prof not in cmdline and real_prof not in cmdline:
            return False
        lower_cmd = cmdline.lower()
        return any(marker in lower_cmd for marker in _BROWSER_BIN_MARKERS)

    @staticmethod
    def find_locking_pids(profile_dir: str) -> List[int]:
        """Finds active browser/driver PIDs referencing profile_dir without requiring external tools on Linux."""
        if not profile_dir:
            return []

        current_pid = os.getpid()
        parent_pid = os.getppid() if hasattr(os, "getppid") else -1
        pids: List[int] = []

        if os.name == "nt":
            prof_name = os.path.basename(os.path.abspath(profile_dir)).replace("'", "''")
            try:
                cmd = (
                    'powershell -NoProfile -Command "'
                    "Get-CimInstance Win32_Process | "
                    f"Where-Object {{ ($_.Name -match 'chrome|chromedriver|firefox|geckodriver|msedge|brave') -and ($_.CommandLine -like '*{prof_name}*') }} | "
                    'Select-Object -ExpandProperty ProcessId"'
                )
                output = subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.DEVNULL, timeout=5)
                for line in output.splitlines():
                    line = line.strip()
                    if line.isdigit():
                        pid = int(line)
                        if pid not in (current_pid, parent_pid):
                            pids.append(pid)
            except Exception:
                pass
            return sorted(set(pids))

        # Pure-Python /proc scan on Linux (works in minimal containers without lsof/ps)
        if os.path.isdir("/proc"):
            try:
                for entry in os.listdir("/proc"):
                    if not entry.isdigit():
                        continue
                    pid = int(entry)
                    if pid in (current_pid, parent_pid):
                        continue
                    cmdline_path = os.path.join("/proc", entry, "cmdline")
                    try:
                        with open(cmdline_path, "rb") as f:
                            raw = f.read()
                        if not raw:
                            continue
                        cmdline = raw.replace(b"\x00", b" ").decode("utf-8", errors="ignore")
                        if ProfileLockCleaner._is_browser_cmdline(cmdline, profile_dir):
                            pids.append(pid)
                    except (OSError, PermissionError):
                        continue
            except Exception:
                pass

        # Fallback for macOS / BSD or open directory descriptors via lsof if installed
        if not pids and os.path.exists(profile_dir) and shutil.which("lsof"):
            try:
                output = subprocess.check_output(
                    ["lsof", "-t", profile_dir],
                    text=True,
                    stderr=subprocess.DEVNULL,
                    timeout=5,
                )
                for line in output.splitlines():
                    line = line.strip()
                    if line.isdigit():
                        pid = int(line)
                        if pid not in (current_pid, parent_pid):
                            pids.append(pid)
            except Exception:
                pass

        return sorted(set(pids))

    @staticmethod
    def kill_zombie_processes(profile_dir: str, timeout: float = 2.0) -> List[int]:
        """Terminates lingering browser/driver processes associated with profile_dir."""
        pids = ProfileLockCleaner.find_locking_pids(profile_dir)
        if not pids:
            return []

        if os.name == "nt":
            for pid in pids:
                try:
                    subprocess.run(
                        ["taskkill", "/F", "/PID", str(pid)],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=5,
                    )
                except Exception:
                    pass
            return pids

        for pid in pids:
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass

        deadline = time.monotonic() + timeout
        remaining = list(pids)
        while remaining and time.monotonic() < deadline:
            still_alive = []
            for pid in remaining:
                try:
                    os.kill(pid, 0)
                    still_alive.append(pid)
                except OSError:
                    pass
            remaining = still_alive
            if remaining:
                time.sleep(0.1)

        for pid in remaining:
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass

        if remaining:
            time.sleep(0.1)

        return pids

    @staticmethod
    def find_lock_files(profile_dir: str, lock_names: Iterable[str] = CHROME_LOCK_FILES) -> List[str]:
        """Returns existing lock file paths (including broken symlinks via os.path.lexists)."""
        if not profile_dir:
            return []
        found = []
        for name in lock_names:
            path = os.path.join(profile_dir, name)
            if os.path.lexists(path):
                found.append(path)
        return found

    @staticmethod
    def remove_lock_files(profile_dir: str, lock_names: Iterable[str] = CHROME_LOCK_FILES) -> List[str]:
        """Removes lock files/symlinks from profile_dir and returns paths that were removed."""
        removed = []
        for path in ProfileLockCleaner.find_lock_files(profile_dir, lock_names):
            try:
                os.unlink(path)
                removed.append(path)
            except OSError as e:
                Logger.debug(f"Failed to remove lock file '{path}': {e}")
        return removed

    @staticmethod
    def cleanup_stale_locks(profile_dir: str, lock_names: Iterable[str] = CHROME_LOCK_FILES) -> None:
        """Detects and cleans up stale profile lock files/symlinks and zombie processes."""
        locks = ProfileLockCleaner.find_lock_files(profile_dir, lock_names)
        pids = ProfileLockCleaner.find_locking_pids(profile_dir)

        if locks or pids:
            Logger.warning("Stale browser profile lock detected. Cleaning up background processes and lock files...")
            if pids:
                ProfileLockCleaner.kill_zombie_processes(profile_dir)
            ProfileLockCleaner.remove_lock_files(profile_dir, lock_names)

    @staticmethod
    def ensure_clean_profile_dir(profile_dir: str, lock_names: Iterable[str] = CHROME_LOCK_FILES) -> None:
        """Terminates processes holding profile_dir and removes the directory cleanly."""
        if not os.path.lexists(profile_dir):
            return
        Logger.warning("Cleaning previous browser session profile to ensure a fresh registration...")
        ProfileLockCleaner.kill_zombie_processes(profile_dir)
        ProfileLockCleaner.remove_lock_files(profile_dir, lock_names)
        try:
            shutil.rmtree(profile_dir, ignore_errors=True)
        except Exception as e:
            Logger.error(f" Could not fully clear session folder: {e}")

    @staticmethod
    def assert_display_available(headless: bool, browser_name: str = "Browser") -> None:
        """Fails fast with a clear message if a visible browser is requested without a GUI display."""
        if not headless and not SanityUtils.has_display():
            Logger.panel(
                "❌ NO GRAPHICAL DISPLAY AVAILABLE",
                [
                    f"Cannot launch visible {browser_name} (Headless: False) without an X11 or Wayland display.",
                    "Neither $DISPLAY nor $WAYLAND_DISPLAY is set in this environment.",
                    "",
                    "👉 Solutions:",
                    "   1. Run with '--headless' for server/container execution.",
                    "   2. Or run inside an X11/Wayland session (or via xvfb-run).",
                ],
                border_color=Fore.RED,
                title_color=Fore.RED,
            )
            raise RuntimeError(
                f"Cannot launch visible {browser_name}: no graphical display ($DISPLAY or $WAYLAND_DISPLAY) detected. "
                "Run with '--headless' or inside an X/Wayland session."
            )

    @staticmethod
    def format_browser_start_error(
        exception: Exception,
        profile_dir: str,
        browser_name: str = "Chrome",
        headless: bool = True,
        had_locking_pids: Optional[List[int]] = None,
    ) -> Exception:
        """Diagnoses browser launch failures accurately instead of blaming profile locks unconditionally."""
        err_msg = str(exception)
        lower_msg = err_msg.lower()

        if "supports chrome version" in lower_msg:
            return exception

        if "binary location must be a string" in lower_msg or "cannot find chrome binary" in lower_msg:
            Logger.panel(
                "❌ CHROME BINARY ERROR",
                [
                    "Could not locate the Chrome/Chromium executable binary.",
                    f"Details: {err_msg}",
                    "",
                    "👉 Solutions:",
                    "   1. Specify your browser path: uv run oreilly-dl <url> -b \"path/to/chrome\"",
                    "   2. Or set the OREILLY_BROWSER_BINARY environment variable.",
                ],
                border_color=Fore.RED,
                title_color=Fore.RED,
            )
            return RuntimeError("Chrome binary could not be located. Please pass -b / --browser-binary.")

        connection_failure = any(
            marker in lower_msg
            for marker in (
                "cannot connect to chrome",
                "chrome not reachable",
                "session not created",
                "devtoolsactiveport file doesn't exist",
                "unable to discover open pages",
                "process unexpectedly closed",
                "failed to start",
            )
        )
        if not connection_failure:
            return exception

        if not headless and not SanityUtils.has_display():
            return RuntimeError(
                f"Cannot launch visible {browser_name}: no graphical display ($DISPLAY or $WAYLAND_DISPLAY) detected. "
                "Run with '--headless' or inside an X/Wayland session."
            )

        locking_pids = had_locking_pids if had_locking_pids is not None else ProfileLockCleaner.find_locking_pids(profile_dir)
        if locking_pids:
            pid_list = ", ".join(str(p) for p in locking_pids)
            Logger.error("Browser Profile Lock Detected!")
            Logger.warning(f"Active background processes ({pid_list}) are locking the profile directory:")
            Logger.warning(f"   Folder: {profile_dir}")
            Logger.info("👉 Solution:")
            if os.name == "nt":
                Logger.info("   1. Open Task Manager and terminate any active 'chrome.exe' or 'chromedriver.exe' processes.")
            else:
                Logger.info(f"   1. Terminate the locking processes (e.g. 'kill -9 {' '.join(str(p) for p in locking_pids)}').")
            Logger.info("   2. Alternatively, run the script with '--browser chrome' or '--browser firefox'.")
            return RuntimeError(
                f"{browser_name} profile '{profile_dir}' is locked by active processes ({pid_list})."
            )

        # No process is locking the profile: Chrome/Firefox crashed or failed to start
        Logger.error(f"{browser_name} failed to start (Headless: {headless}).")
        Logger.warning(f"   Profile: {profile_dir}")
        Logger.warning(f"   Cause:   {err_msg}")
        Logger.info("👉 Troubleshooting:")
        if os.name == "nt":
            Logger.info("   1. Verify Chrome/Firefox is installed and up to date.")
            Logger.info("   2. Try running with '--browser chrome' or '--browser firefox'.")
        else:
            if not headless:
                Logger.info("   1. If running in a container/SSH without X11, pass '--headless'.")
            else:
                Logger.info("   1. In minimal containers, verify Chrome shared libraries are installed (e.g. 'google-chrome --headless --dump-dom about:blank').")
            Logger.info("   2. Check container '/dev/shm' size or try '--browser firefox' / '--browser chrome'.")
        return RuntimeError(
            f"{browser_name} failed to start (Headless: {headless}): {err_msg}"
        )
