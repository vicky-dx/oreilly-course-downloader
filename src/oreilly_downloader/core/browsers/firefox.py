import os
from typing import Optional
from selenium import webdriver
from webdriver_manager.firefox import GeckoDriverManager
from selenium.webdriver.firefox.service import Service
from .base import IBrowser
from .logger import Logger
from .profile_lock import FIREFOX_LOCK_FILES, ProfileLockCleaner
from ..utils import SanityUtils


class FirefoxBrowser(IBrowser):
    def __init__(self, headless=True, clean_session=False, browser_binary: Optional[str] = None):
        self.headless = headless
        self.clean_session = clean_session
        self.browser_binary = browser_binary
        self.driver = None
        self.raw_driver = None
        self._profile_dir: Optional[str] = None

    def start(self):
        ProfileLockCleaner.assert_display_available(self.headless, "Firefox")

        opts = webdriver.FirefoxOptions()
        if self.headless:
            opts.add_argument("--headless")

        resolved_binary = SanityUtils.get_firefox_path(self.browser_binary)
        if self.browser_binary and not resolved_binary:
            raise FileNotFoundError(f"Browser binary not found: {self.browser_binary}")
        if resolved_binary:
            opts.binary_location = resolved_binary

        prof = os.path.join(os.getcwd(), "firefox_profile")
        self._profile_dir = prof

        if self.clean_session:
            ProfileLockCleaner.ensure_clean_profile_dir(prof, FIREFOX_LOCK_FILES)
        else:
            ProfileLockCleaner.cleanup_stale_locks(prof, FIREFOX_LOCK_FILES)

        if not os.path.exists(prof):
            os.makedirs(prof)

        pre_existing_locks = ProfileLockCleaner.find_locking_pids(prof)
        opts.add_argument("-profile")
        opts.add_argument(prof)

        from .browser import Browser

        try:
            raw_driver = webdriver.Firefox(
                service=Service(GeckoDriverManager().install()), options=opts
            )
        except Exception as e:
            ProfileLockCleaner.kill_zombie_processes(prof)
            ProfileLockCleaner.remove_lock_files(prof, FIREFOX_LOCK_FILES)
            raise ProfileLockCleaner.format_browser_start_error(
                e,
                prof,
                browser_name="Firefox",
                headless=self.headless,
                had_locking_pids=pre_existing_locks,
            )

        self.raw_driver = raw_driver
        self.driver = Browser(raw_driver)
        return self.driver

    def stop(self):
        if getattr(self, "raw_driver", None):
            try:
                self.raw_driver.quit()
            except Exception as e:
                Logger.debug(f"Error quitting Firefox driver: {e}")
            finally:
                self.raw_driver = None
                self.driver = None
        if self._profile_dir:
            ProfileLockCleaner.kill_zombie_processes(self._profile_dir)
            ProfileLockCleaner.remove_lock_files(self._profile_dir, FIREFOX_LOCK_FILES)
