import os
from selenium import webdriver
from webdriver_manager.firefox import GeckoDriverManager
from selenium.webdriver.firefox.service import Service
from .base import IBrowser


class FirefoxBrowser(IBrowser):
    def __init__(self, headless=True, clean_session=False):
        self.headless = headless
        self.clean_session = clean_session
        self.driver = None

    def start(self):
        opts = webdriver.FirefoxOptions()
        if self.headless:
            opts.add_argument("--headless")

        prof = os.path.join(os.getcwd(), "firefox_profile")
        if self.clean_session:
            import shutil
            if os.path.exists(prof):
                try:
                    shutil.rmtree(prof, ignore_errors=True)
                except Exception:
                    pass
        if not os.path.exists(prof):
            os.makedirs(prof)

        opts.add_argument("-profile")
        opts.add_argument(prof)

        from .browser import Browser
        
        raw_driver = webdriver.Firefox(
            service=Service(GeckoDriverManager().install()), options=opts
        )
        self.raw_driver = raw_driver
        self.driver = Browser(raw_driver)
        return self.driver


    def stop(self):
        if hasattr(self, 'raw_driver') and self.raw_driver:
            self.raw_driver.quit()

