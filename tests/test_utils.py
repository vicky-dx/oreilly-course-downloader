import os
import shutil
import pytest
from unittest.mock import patch
from oreilly_downloader.core.utils import SanityUtils, PathManager

def test_sanitize_filename():
    # Test stripping illegal Windows characters and trailing characters
    assert SanityUtils.sanitize_filename("Chapter 1: Intro <Test> ? * |") == "Chapter 1- Intro -Test"
    
    # Test newline removal and space squeezing
    assert SanityUtils.sanitize_filename("Chapter  1\nIntro\r\nDetails") == "Chapter 1 Intro Details"
    
    # Test trailing dots, spaces and dashes
    assert SanityUtils.sanitize_filename("Chapter 1. ") == "Chapter 1"
    assert SanityUtils.sanitize_filename("Chapter 2 - ") == "Chapter 2"
    
    # Test consecutive dashes squeezing
    assert SanityUtils.sanitize_filename("Chapter 3---Intro") == "Chapter 3-Intro"
    
    # Test empty name fallback
    assert SanityUtils.sanitize_filename("?*<>|") == "unnamed"
    
    # Test length truncation (max 80)
    long_name = "A" * 100
    sanitized = SanityUtils.sanitize_filename(long_name)
    assert len(sanitized) == 80
    assert sanitized == "A" * 80

def test_get_ffmpeg_path_system_path():
    with patch("shutil.which", return_value="/usr/bin/ffmpeg"):
        assert SanityUtils.get_ffmpeg_path() == "/usr/bin/ffmpeg"

def test_get_ffmpeg_path_local_paths():
    with patch("shutil.which", return_value=None), \
         patch("os.path.exists", return_value=True) as mock_exists:
        # Should check local directories and return one if exists
        path = SanityUtils.get_ffmpeg_path()
        assert path is not None
        assert mock_exists.called

def test_get_chrome_path_explicit():
    # Test custom path when file exists
    with patch("os.path.exists", return_value=True):
        custom = "/custom/path/to/chrome"
        resolved = SanityUtils.get_chrome_path(custom)
        assert resolved == os.path.abspath(custom)

def test_get_chrome_path_env_var():
    with patch.dict(os.environ, {"OREILLY_BROWSER_BINARY": "/env/path/chrome"}), \
         patch("os.path.exists", side_effect=lambda p: p == "/env/path/chrome"):
        resolved = SanityUtils.get_chrome_path()
        assert resolved == os.path.abspath("/env/path/chrome")

def test_get_chrome_path_shutil_which():
    with patch.dict(os.environ, {}, clear=True), \
         patch("os.path.exists", return_value=False), \
         patch("shutil.which", side_effect=lambda cmd: "/bin/google-chrome" if cmd == "google-chrome" else None):
        resolved = SanityUtils.get_chrome_path()
        assert resolved == "/bin/google-chrome"

def test_get_chrome_path_not_found():
    with patch.dict(os.environ, {}, clear=True), \
         patch("os.path.exists", return_value=False), \
         patch("shutil.which", return_value=None):
        assert SanityUtils.get_chrome_path() is None

def test_get_firefox_path():
    with patch("shutil.which", side_effect=lambda cmd: "/usr/bin/firefox" if cmd == "firefox" else None):
        assert SanityUtils.get_firefox_path() == "/usr/bin/firefox"

def test_path_manager_course_dir():
    course_dir = PathManager.get_course_dir("downloads", "Kafka: Event Streaming?")
    expected = os.path.join("downloads", "Kafka- Event Streaming")
    assert course_dir == expected

def test_path_manager_profile_dir():
    assert PathManager.get_profile_dir("test_prof") == os.path.join(os.getcwd(), "test_prof")
    assert PathManager.get_profile_dir("test_prof", "custom_base") == os.path.join("custom_base", "test_prof")

def test_path_manager_video_paths_with_videos_lesson():
    # When lesson title is "Videos", it should bypass the lesson folder
    course_dir = os.path.join("downloads", "Kafka")
    vid_file, txt_file = PathManager.get_video_paths(
        course_dir=course_dir,
        mod_idx=1,
        mod_title="Introduction",
        less_idx=1,
        less_title="Videos",
        vid_idx=1,
        vid_title="Welcome"
    )
    expected_vid = os.path.join(course_dir, "01 - Introduction", "01 - Welcome.mp4")
    expected_txt = os.path.join(course_dir, "01 - Introduction", "01 - Welcome_transcript.txt")
    assert vid_file == expected_vid
    assert txt_file == expected_txt

def test_path_manager_video_paths_with_other_lesson():
    # When lesson title is not "Videos", it should include the lesson folder
    course_dir = os.path.join("downloads", "Kafka")
    vid_file, txt_file = PathManager.get_video_paths(
        course_dir=course_dir,
        mod_idx=1,
        mod_title="Introduction",
        less_idx=2,
        less_title="Setup Guide",
        vid_idx=1,
        vid_title="Installation"
    )
    expected_vid = os.path.join(course_dir, "01 - Introduction", "02 - Setup Guide", "01 - Installation.mp4")
    expected_txt = os.path.join(course_dir, "01 - Introduction", "02 - Setup Guide", "01 - Installation_transcript.txt")
    assert vid_file == expected_vid
    assert txt_file == expected_txt

def test_path_manager_video_paths_with_audiobook():
    course_dir = os.path.join("downloads", "DesignPatterns")
    vid_file, txt_file = PathManager.get_video_paths(
        course_dir=course_dir,
        mod_idx=1,
        mod_title="Creational",
        less_idx=1,
        less_title="Videos",
        vid_idx=2,
        vid_title="Factory",
        is_audio_only=True
    )
    expected_vid = os.path.join(course_dir, "01 - Creational", "02 - Factory.m4a")
    expected_txt = os.path.join(course_dir, "01 - Creational", "02 - Factory_transcript.txt")
    assert vid_file == expected_vid
    assert txt_file == expected_txt
