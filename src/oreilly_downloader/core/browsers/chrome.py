import os
from typing import Optional
from selenium import webdriver
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
from .base import IBrowser
from .logger import Logger
from .profile_lock import CHROME_LOCK_FILES, ProfileLockCleaner
from ..utils import SanityUtils


class ChromeBrowser(IBrowser):
    def __init__(self, headless=True, clean_session=False, browser_binary: Optional[str] = None):
        self.headless = headless
        self.clean_session = clean_session
        self.browser_binary = browser_binary
        self.driver = None
        self.raw_driver = None
        self._profile_dir: Optional[str] = None

    def start(self):
        ProfileLockCleaner.assert_display_available(self.headless, "Chrome")

        opts = webdriver.ChromeOptions()
        if self.headless:
            opts.add_argument("--headless=new")
        opts.add_argument("--disable-gpu")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")

        resolved_binary = SanityUtils.get_chrome_path(self.browser_binary)
        if self.browser_binary and not resolved_binary:
            raise FileNotFoundError(f"Browser binary not found: {self.browser_binary}")
        if resolved_binary:
            opts.binary_location = resolved_binary

        prof = os.path.join(os.getcwd(), "chrome_profile")
        self._profile_dir = prof

        if self.clean_session:
            ProfileLockCleaner.ensure_clean_profile_dir(prof, CHROME_LOCK_FILES)
        else:
            ProfileLockCleaner.cleanup_stale_locks(prof, CHROME_LOCK_FILES)

        pre_existing_locks = ProfileLockCleaner.find_locking_pids(prof)
        opts.add_argument(f"user-data-dir={prof}")
        opts.add_argument("--profile-directory=Default")

        from .browser import Browser

        try:
            raw_driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)
        except Exception as e:
            ProfileLockCleaner.kill_zombie_processes(prof)
            ProfileLockCleaner.remove_lock_files(prof, CHROME_LOCK_FILES)
            raise ProfileLockCleaner.format_browser_start_error(
                e,
                prof,
                browser_name="Chrome",
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
                Logger.debug(f"Error quitting Chrome driver: {e}")
            finally:
                self.raw_driver = None
                self.driver = None
        if self._profile_dir:
            ProfileLockCleaner.kill_zombie_processes(self._profile_dir)
            ProfileLockCleaner.remove_lock_files(self._profile_dir, CHROME_LOCK_FILES)
