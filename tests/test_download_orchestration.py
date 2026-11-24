import os
import json
import pytest
from unittest.mock import MagicMock, patch
from oreilly_downloader.core.downloader import DownloaderService, DlqReporter, TranscriptSaver
from oreilly_downloader.core.config import DownloaderConfig, DownloadOptions
from oreilly_downloader.core.models import Course, Module, Lesson, Video

def test_download_course_success(tmp_path):
    # 1. Setup temporary course output directory
    output_dir = tmp_path / "downloads"
    course_dir = output_dir / "Test_Course"
    os.makedirs(course_dir, exist_ok=True)
    
    # 2. Setup config
    config = DownloaderConfig(
        url="https://learning.oreilly.com/course/test-course",
        output_dir=str(output_dir),
        max_workers=2,
        resolution="best",
        transcripts_only=False
    )
    
    # 3. Create dummy course models
    video = Video(title="Intro Video", url="https://learning.oreilly.com/video/1")
    lesson = Lesson(title="Introduction", videos=[video])
    module = Module(title="Chapter 1", lessons=[lesson])
    course = Course(title="Test Course", modules=[module])
    
    # 4. Mock dependencies
    mock_scraper = MagicMock()
    mock_scraper.extract_transcript.return_value = "This is the transcript of Intro Video"
    
    mock_resolver = MagicMock()
    mock_resolver.resolve_m3u8_url.return_value = "https://cdn.kaltura.com/test.m3u8"
    
    # 5. Create downloader service and mock download_video
    downloader = DownloaderService(output_dir=str(output_dir), ffmpeg_path="ffmpeg")
    downloader.download_video = MagicMock(return_value=True)
    
    # 6. Execute download_course
    downloader.download_course(
        course=course,
        scraper=mock_scraper,
        resolver=mock_resolver,
        config=config,
        course_dir=str(course_dir),
        is_audio_only=False
    )
    
    # 7. Assertions
    # Verify resolve_m3u8_url and extract_transcript were called
    mock_resolver.resolve_m3u8_url.assert_called_once_with(video.url, resolution="best")
    mock_scraper.extract_transcript.assert_called_once_with(video.url, mock_resolver)
    
    # Verify download_video was called
    expected_video_path = os.path.join(
        str(course_dir),
        "01 - Chapter 1",
        "01 - Introduction",
        "01 - Intro Video.mp4"
    )
    downloader.download_video.assert_called_once_with("https://cdn.kaltura.com/test.m3u8", expected_video_path)
    
    # Verify transcript was written
    expected_transcript_path = os.path.join(
        str(course_dir),
        "01 - Chapter 1",
        "01 - Introduction",
        "01 - Intro Video_transcript.txt"
    )
    assert os.path.exists(expected_transcript_path)
    with open(expected_transcript_path, "r", encoding="utf-8") as tf:
        assert tf.read() == "This is the transcript of Intro Video"


def test_download_course_skip_existing_files(tmp_path):
    # 1. Setup temporary course output directory
    output_dir = tmp_path / "downloads"
    course_dir = output_dir / "Test_Course"
    os.makedirs(course_dir, exist_ok=True)
    
    # 2. Setup config
    config = DownloaderConfig(
        url="https://learning.oreilly.com/course/test-course",
        output_dir=str(output_dir),
        max_workers=2,
        resolution="best",
        transcripts_only=False
    )
    
    # 3. Create dummy course models
    video = Video(title="Intro Video", url="https://learning.oreilly.com/video/1")
    lesson = Lesson(title="Introduction", videos=[video])
    module = Module(title="Chapter 1", lessons=[lesson])
    course = Course(title="Test Course", modules=[module])
    
    # 4. Create dummy existing video and transcript files on disk
    expected_video_dir = os.path.join(str(course_dir), "01 - Chapter 1", "01 - Introduction", "01 - Intro Video")
    os.makedirs(os.path.dirname(expected_video_dir), exist_ok=True)
    
    video_file = expected_video_dir + ".mp4"
    transcript_file = expected_video_dir + "_transcript.txt"
    
    with open(video_file, "w") as f:
        f.write("dummy-video-data")
    with open(transcript_file, "w") as f:
        f.write("dummy-transcript-data")
        
    # 5. Mock dependencies
    mock_scraper = MagicMock()
    mock_resolver = MagicMock()
    
    # 6. Create downloader service and mock download_video
    downloader = DownloaderService(output_dir=str(output_dir), ffmpeg_path="ffmpeg")
    downloader.download_video = MagicMock()
    
    # 7. Execute download_course
    downloader.download_course(
        course=course,
        scraper=mock_scraper,
        resolver=mock_resolver,
        config=config,
        course_dir=str(course_dir),
        is_audio_only=False
    )
    
    # 8. Assertions
    # Verify everything was skipped because files exist
    mock_resolver.resolve_m3u8_url.assert_not_called()
    mock_scraper.extract_transcript.assert_not_called()
    downloader.download_video.assert_not_called()


def test_download_course_failure_writes_dlq(tmp_path):
    # 1. Setup temporary course output directory
    output_dir = tmp_path / "downloads"
    course_dir = output_dir / "Test_Course"
    os.makedirs(course_dir, exist_ok=True)
    
    # 2. Setup config
    config = DownloaderConfig(
        url="https://learning.oreilly.com/course/test-course",
        output_dir=str(output_dir),
        max_workers=2,
        resolution="best",
        transcripts_only=False
    )
    
    # 3. Create dummy course models
    video = Video(title="Intro Video", url="https://learning.oreilly.com/video/1")
    lesson = Lesson(title="Introduction", videos=[video])
    module = Module(title="Chapter 1", lessons=[lesson])
    course = Course(title="Test Course", modules=[module])
    
    # 4. Mock dependencies to trigger failure (e.g. resolve_m3u8_url returns None)
    mock_scraper = MagicMock()
    mock_scraper.extract_transcript.return_value = None
    
    mock_resolver = MagicMock()
    mock_resolver.resolve_m3u8_url.return_value = None  # Failed resolution
    
    # 5. Create downloader service
    downloader = DownloaderService(output_dir=str(output_dir), ffmpeg_path="ffmpeg")
    
    # 6. Execute download_course
    downloader.download_course(
        course=course,
        scraper=mock_scraper,
        resolver=mock_resolver,
        config=config,
        course_dir=str(course_dir),
        is_audio_only=False
    )
    
    # 7. Assertions
    # Verify failed_downloads.json was generated
    dlq_path = os.path.join(str(course_dir), "failed_downloads.json")
    assert os.path.exists(dlq_path)
    
    with open(dlq_path, "r", encoding="utf-8") as f:
        failed_items = json.load(f)
        
    assert len(failed_items) == 1
    assert failed_items[0]["title"] == "Intro Video"
    assert failed_items[0]["url"] == "https://learning.oreilly.com/video/1"
    assert failed_items[0]["error"] == "Could not resolve M3U8 stream URL"


def test_dlq_reporter_standalone(tmp_path):
    course_dir = tmp_path / "course"
    os.makedirs(course_dir, exist_ok=True)
    failed = [{"title": "Test 1", "url": "https://url1", "error": "timeout"}]
    DlqReporter.write_report(failed, str(course_dir))

    dlq_file = course_dir / "failed_downloads.json"
    assert dlq_file.exists()
    with open(dlq_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert len(data) == 1
    assert data[0]["title"] == "Test 1"


def test_transcript_saver_standalone(tmp_path):
    out_file = tmp_path / "transcripts" / "test.txt"
    TranscriptSaver.save("Hello transcript", str(out_file))
    assert out_file.exists()
    assert out_file.read_text(encoding="utf-8") == "Hello transcript"


def test_download_course_with_download_options_only(tmp_path):
    output_dir = tmp_path / "downloads"
    course_dir = output_dir / "Test_Course"
    os.makedirs(course_dir, exist_ok=True)

    options = DownloadOptions(max_workers=1, resolution="best", transcripts_only=False)
    video = Video(title="V1", url="https://learning.oreilly.com/video/1")
    lesson = Lesson(title="L1", videos=[video])
    module = Module(title="M1", lessons=[lesson])
    course = Course(title="C1", modules=[module])

    mock_scraper = MagicMock()
    mock_scraper.extract_transcript.return_value = "Transcript text"
    mock_resolver = MagicMock()
    mock_resolver.resolve_m3u8_url.return_value = "https://stream.m3u8"

    downloader = DownloaderService(output_dir=str(output_dir), ffmpeg_path="ffmpeg")
    downloader.download_video = MagicMock(return_value=True)

    downloader.download_course(
        course=course,
        scraper=mock_scraper,
        resolver=mock_resolver,
        options=options,
        course_dir=str(course_dir),
    )

    downloader.download_video.assert_called_once()

