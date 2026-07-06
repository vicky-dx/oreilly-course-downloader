import os
from selenium import webdriver
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
from .base import IBrowser

class ChromeBrowser(IBrowser):
    def __init__(self, headless=True, clean_session=False):
        self.headless = headless
        self.clean_session = clean_session
        self.driver = None

    def start(self):
        opts = webdriver.ChromeOptions()
        if self.headless:
            opts.add_argument("--headless=new")
        opts.add_argument("--disable-gpu")
        opts.add_argument("--no-sandbox")
        
        prof = os.path.join(os.getcwd(), "chrome_profile")
        if self.clean_session:
            import shutil
            if os.path.exists(prof):
                try:
                    shutil.rmtree(prof, ignore_errors=True)
                except Exception:
                    pass
        opts.add_argument(f"user-data-dir={prof}")
        opts.add_argument("--profile-directory=Default")
        
        from .browser import Browser
        
        raw_driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)
        self.raw_driver = raw_driver
        self.driver = Browser(raw_driver)
        return self.driver


    def stop(self):
        if hasattr(self, 'raw_driver') and self.raw_driver:
            self.raw_driver.quit()

