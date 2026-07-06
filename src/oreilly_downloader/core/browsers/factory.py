from .base import IBrowser
from .stealth import StealthChromeBrowser
from .firefox import FirefoxBrowser
from .chrome import ChromeBrowser

class BrowserFactory:
    @staticmethod
    def create(browser_type: str, headless: bool = True, clean_session: bool = False) -> IBrowser:
        if browser_type == "stealth":
            return StealthChromeBrowser(headless=headless, clean_session=clean_session)
        elif browser_type == "firefox":
            return FirefoxBrowser(headless=headless, clean_session=clean_session)
        elif browser_type == "chrome":
            return ChromeBrowser(headless=headless, clean_session=clean_session)

        else:
            raise ValueError(f"Unknown browser type: {browser_type}")
