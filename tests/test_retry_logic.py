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


from oreilly_downloader.core.downloader import DownloaderService
import os

@patch("time.sleep")
def test_download_video_retry_success(mock_sleep, tmp_path):
    output_file = tmp_path / "video.mp4"
    part_file = tmp_path / "video.mp4.part"
    
    # Attempt 1: fails
    mock_proc1 = MagicMock()
    mock_proc1.wait.return_value = 1
    mock_proc1.returncode = 1
    mock_proc1.stderr = ["Error: timeout"]
    
    # Attempt 2: succeeds
    mock_proc2 = MagicMock()
    mock_proc2.wait.return_value = 0
    mock_proc2.returncode = 0
    mock_proc2.stderr = ["Duration: 00:01:00.00", "time=00:00:30.00", "time=00:01:00.00"]
    
    call_count = 0
    def side_effect_func(cmd):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return mock_proc1
        else:
            with open(part_file, "w") as f:
                f.write("stream-bytes")
            return mock_proc2

    downloader = DownloaderService(output_dir=str(tmp_path), ffmpeg_path="ffmpeg")
    mock_start = MagicMock(side_effect=side_effect_func)
    downloader.ffmpeg_runner.start_process = mock_start
    
    # Run
    result = downloader.download_video(
        m3u8_url="https://test/stream.m3u8",
        output_path=str(output_file),
        max_retries=3
    )
    
    # Assertions
    assert result is True
    assert mock_start.call_count == 2
    mock_sleep.assert_called_once_with(3) # Sleeps for 3s after attempt 1
    assert os.path.exists(output_file)
    with open(output_file, "r") as f:
        assert f.read() == "stream-bytes"


@patch("time.sleep")
def test_download_video_retry_max_failures(mock_sleep, tmp_path):
    output_file = tmp_path / "video.mp4"
    downloader = DownloaderService(output_dir=str(tmp_path), ffmpeg_path="ffmpeg")
    
    # Mock processes failing 3 times
    proc_fails = []
    for _ in range(3):
        p = MagicMock()
        p.wait.return_value = 1
        p.returncode = 1
        p.stderr = ["Error Code 500"]
        proc_fails.append(p)
        
    mock_start = MagicMock(side_effect=proc_fails)
    downloader.ffmpeg_runner.start_process = mock_start
    
    # Run
    result = downloader.download_video(
        m3u8_url="https://test/stream.m3u8",
        output_path=str(output_file),
        max_retries=3
    )
    
    # Assertions
    assert result is False
    assert mock_start.call_count == 3
    # Check that it slept for attempt 1 (3s) and attempt 2 (6s)
    mock_sleep.assert_any_call(3)
    mock_sleep.assert_any_call(6)
    assert mock_sleep.call_count == 2
    assert not os.path.exists(output_file)

