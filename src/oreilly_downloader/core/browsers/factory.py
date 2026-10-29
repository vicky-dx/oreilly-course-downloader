from typing import Optional
from .base import IBrowser
from .stealth import StealthChromeBrowser
from .firefox import FirefoxBrowser
from .chrome import ChromeBrowser

class BrowserFactory:
    @staticmethod
    def create(
        browser_type: str,
        headless: bool = True,
        clean_session: bool = False,
        browser_binary: Optional[str] = None,
    ) -> IBrowser:
        if browser_type == "stealth":
            return StealthChromeBrowser(
                headless=headless,
                clean_session=clean_session,
                browser_binary=browser_binary,
            )
        elif browser_type == "firefox":
            return FirefoxBrowser(
                headless=headless,
                clean_session=clean_session,
                browser_binary=browser_binary,
            )
        elif browser_type == "chrome":
            return ChromeBrowser(
                headless=headless,
                clean_session=clean_session,
                browser_binary=browser_binary,
            )
        else:
            raise ValueError(f"Unknown browser type: {browser_type}")
