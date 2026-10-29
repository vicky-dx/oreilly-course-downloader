import os
import sys
import pytest
from unittest.mock import patch, MagicMock
from oreilly_downloader.core.browsers.factory import BrowserFactory
from oreilly_downloader.core.browsers.stealth import StealthChromeBrowser
from oreilly_downloader.core.browsers.chrome import ChromeBrowser
from oreilly_downloader.core.browsers.firefox import FirefoxBrowser

def test_browser_factory_passes_browser_binary():
    stealth = BrowserFactory.create("stealth", headless=True, browser_binary="/path/to/chrome")
    assert isinstance(stealth, StealthChromeBrowser)
    assert stealth.browser_binary == "/path/to/chrome"

    chrome = BrowserFactory.create("chrome", headless=False, browser_binary="/path/to/chrome")
    assert isinstance(chrome, ChromeBrowser)
    assert chrome.browser_binary == "/path/to/chrome"

    firefox = BrowserFactory.create("firefox", headless=True, browser_binary="/path/to/firefox")
    assert isinstance(firefox, FirefoxBrowser)
    assert firefox.browser_binary == "/path/to/firefox"

def test_stealth_chrome_browser_not_found_raises():
    with patch("oreilly_downloader.core.utils.SanityUtils.get_chrome_path", return_value=None):
        browser = StealthChromeBrowser(headless=True)
        with pytest.raises(RuntimeError) as exc_info:
            browser.start()
        assert "Google Chrome not found" in str(exc_info.value)

def test_stealth_chrome_browser_custom_binary_not_found_raises():
    with patch("os.path.exists", return_value=False), \
         patch("shutil.which", return_value=None):
        browser = StealthChromeBrowser(headless=True, browser_binary="/nonexistent/chrome")
        with pytest.raises(FileNotFoundError):
            browser.start()

