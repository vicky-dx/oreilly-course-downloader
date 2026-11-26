from .logger import Logger
import os
import re
import shutil
from typing import Optional
from colorama import Fore, init
import undetected_chromedriver as uc  # type: ignore
from .base import IBrowser
from .profile_lock import CHROME_LOCK_FILES, ProfileLockCleaner
from ..utils import SanityUtils

init(autoreset=True)


class StealthChromeBrowser(IBrowser):
    def __init__(self, headless=True, clean_session=False, browser_binary: Optional[str] = None):
        self.headless = headless
        self.clean_session = clean_session
        self.browser_binary = browser_binary
        self.driver = None
        self.raw_driver = None
        self._profile_dir: Optional[str] = None

    def _get_options(self):
        opts = uc.ChromeOptions()
        opts.add_argument("--window-size=1920,1080")
        opts.add_argument("--start-maximized")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")

        # NOTE: Do NOT spoof the User-Agent or manually change blink features!
        # undetected_chromedriver patches the chromedriver binary directly.
        if self.headless:
            opts.add_argument("--headless=new")
        return opts

    def _kill_zombie_chrome_processes(self, profile_dir: str):
        ProfileLockCleaner.kill_zombie_processes(profile_dir)

    def _launch_uc(self, prof: str, resolved_binary: str, version_main: Optional[int] = None):
        kwargs = {
            "options": self._get_options(),
            "user_data_dir": prof,
            "browser_executable_path": resolved_binary,
        }
        if version_main is not None:
            kwargs["version_main"] = version_main
        return uc.Chrome(**kwargs)

    def start(self):
        ProfileLockCleaner.assert_display_available(self.headless, "Chrome")

        prof = os.path.join(os.getcwd(), "browser_profile_stealth")
        self._profile_dir = prof

        if self.clean_session:
            ProfileLockCleaner.ensure_clean_profile_dir(prof, CHROME_LOCK_FILES)
        else:
            ProfileLockCleaner.cleanup_stale_locks(prof, CHROME_LOCK_FILES)

        resolved_binary = SanityUtils.get_chrome_path(self.browser_binary)
        if self.browser_binary and not resolved_binary:
            Logger.error(f"Specified browser binary was not found: {self.browser_binary}")
            raise FileNotFoundError(f"Browser binary not found: {self.browser_binary}")

        if not resolved_binary:
            Logger.panel("❌ GOOGLE CHROME NOT FOUND", [
                "undetected-chromedriver requires Google Chrome or a Chromium browser.",
                "Google Chrome was not found in standard system locations or PATH.",
                "",
                "👉 Solutions:",
                "   1. Install Google Chrome: https://www.google.com/chrome/",
                "   2. Or specify your browser executable path via CLI:",
                "      uv run oreilly-dl <url> -b \"C:\\path\\to\\chrome.exe\"",
                "   3. Or set the OREILLY_BROWSER_BINARY environment variable.",
                "   4. Or run with another browser: '--browser firefox'"
            ], border_color=Fore.RED, title_color=Fore.RED)
            raise RuntimeError(
                "Google Chrome not found. Please install Chrome or specify its location using -b / --browser-binary."
            )

        # Record any unkillable pre-existing processes holding the profile before launch
        pre_existing_locks = ProfileLockCleaner.find_locking_pids(prof)

        self._clean_uc_cache()
        Logger.info(f"Starting True Stealth Chrome (Headless: {self.headless})...")

        try:
            raw_driver = self._launch_uc(prof, resolved_binary)
        except Exception as e:
            err_msg = str(e)

            # Clean up any half-started Chrome subprocess and lock files left by the failed launch
            ProfileLockCleaner.kill_zombie_processes(prof)
            ProfileLockCleaner.remove_lock_files(prof, CHROME_LOCK_FILES)

            # Handle version mismatch first
            if "supports chrome version" in err_msg.lower():
                match = re.search(r"current browser version is (\d+)", err_msg, re.IGNORECASE)
                if match:
                    ver = int(match.group(1))
                    Logger.warning(f"Chrome version mismatch. Retrying with driver version {ver}...")
                    self._clean_uc_cache()
                    try:
                        raw_driver = self._launch_uc(prof, resolved_binary, version_main=ver)
                    except Exception as retry_e:
                        ProfileLockCleaner.kill_zombie_processes(prof)
                        ProfileLockCleaner.remove_lock_files(prof, CHROME_LOCK_FILES)
                        raise ProfileLockCleaner.format_browser_start_error(
                            retry_e,
                            prof,
                            browser_name="Chrome",
                            headless=self.headless,
                            had_locking_pids=pre_existing_locks,
                        )
                else:
                    raise e
            else:
                raise ProfileLockCleaner.format_browser_start_error(
                    e,
                    prof,
                    browser_name="Chrome",
                    headless=self.headless,
                    had_locking_pids=pre_existing_locks,
                )

        from .browser import Browser
        self.raw_driver = raw_driver
        self.driver = Browser(raw_driver)
        return self.driver

    def stop(self):
        if getattr(self, "raw_driver", None):
            try:
                self.raw_driver.quit()
            except Exception as e:
                Logger.debug(f"Error quitting Stealth Chrome driver: {e}")
            finally:
                self.raw_driver = None
                self.driver = None
        if self._profile_dir:
            ProfileLockCleaner.kill_zombie_processes(self._profile_dir)
            ProfileLockCleaner.remove_lock_files(self._profile_dir, CHROME_LOCK_FILES)

    def _clean_uc_cache(self):
        """Cleans up undetected_chromedriver's binary cache safely to avoid FileExistsErrors on Windows."""
        try:
            appdata = os.environ.get("APPDATA")
            if appdata:
                uc_cache_dir = os.path.join(appdata, "undetected_chromedriver")
                if os.path.exists(uc_cache_dir):
                    try:
                        shutil.rmtree(uc_cache_dir, ignore_errors=True)
                    except Exception as e:
                        Logger.debug(f"Failed to remove uc cache directory: {e}")
        except Exception as e:
            Logger.debug(f"Failed to clean undetected_chromedriver cache: {e}")
