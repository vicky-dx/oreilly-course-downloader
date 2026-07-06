import pytest
from unittest.mock import MagicMock, patch
from oreilly_downloader.core.config import DownloaderConfig
from oreilly_downloader.cli import process_course, HeadlessAutoLoginFailed

def test_headless_to_headed_retry_on_login_failure():
    # 1. Prepare configuration
    config = DownloaderConfig(
        url="https://learning.oreilly.com/course/test-course/123/",
        email=None,
        password=None,
        headless=True,
    )
    
    # 2. Mock BrowserFactory, and the Browser Managers it returns
    mock_bm1 = MagicMock()
    mock_driver1 = MagicMock()
    mock_bm1.start.return_value = mock_driver1
    
    mock_bm2 = MagicMock()
    mock_driver2 = MagicMock()
    mock_bm2.start.return_value = mock_driver2
    
    # BrowserFactory.create should return mock_bm1 first, then mock_bm2
    mock_create = MagicMock(side_effect=[mock_bm1, mock_bm2])
    
    # 3. Patch dependencies
    with patch("oreilly_downloader.cli.BrowserFactory.create", mock_create), \
         patch("oreilly_downloader.cli.AuthService") as mock_auth_cls, \
         patch("oreilly_downloader.cli._handle_authentication") as mock_handle_auth:
        
        # Make _handle_authentication raise HeadlessAutoLoginFailed on the first call (headless),
        # and return False on the second call (headed) to exit process_course cleanly.
        mock_handle_auth.side_effect = [HeadlessAutoLoginFailed(), False]
        
        # Run process_course
        process_course(config)
        
        # Verify first call: BrowserFactory.create(..., headless=True)
        mock_create.assert_any_call(
            browser_type=config.browser_type,
            headless=True,
            clean_session=False
        )
        # Verify second call: BrowserFactory.create(..., headless=False)
        mock_create.assert_any_call(
            browser_type=config.browser_type,
            headless=False,
            clean_session=False
        )
        
        # Verify both browser managers were started and stopped
        mock_bm1.start.assert_called_once()
        mock_bm1.stop.assert_called_once()
        mock_bm2.start.assert_called_once()
        mock_bm2.stop.assert_called_once()
        
        # Verify config.headless was set to False
        assert config.headless is False
