import os
import pytest
from unittest.mock import MagicMock, patch, call
from oreilly_downloader.core.config import DownloaderConfig
from oreilly_downloader.core.batch import (
    parse_batch_file,
    detect_content_type,
    BatchProcessor,
    BatchItemResult,
)


def test_parse_batch_file_valid(tmp_path):
    batch_file = tmp_path / "download_me.txt"
    batch_file.write_text(
        """# This is a comment
https://learning.oreilly.com/course/agentic-ai/9781807785192/

// Another comment
https://learning.oreilly.com/videos/ai-engineering/9781663753052/
   https://learning.oreilly.com/library/view/ai-engineering/9781098166298/   

# Trailing comment
""",
        encoding="utf-8",
    )

    urls = parse_batch_file(str(batch_file))
    assert len(urls) == 3
    assert urls[0] == "https://learning.oreilly.com/course/agentic-ai/9781807785192/"
    assert urls[1] == "https://learning.oreilly.com/videos/ai-engineering/9781663753052/"
    assert urls[2] == "https://learning.oreilly.com/library/view/ai-engineering/9781098166298/"


def test_parse_batch_file_empty(tmp_path):
    empty_file = tmp_path / "empty.txt"
    empty_file.write_text("# Only comments\n   \n", encoding="utf-8")

    with pytest.raises(ValueError, match="No valid URLs found"):
        parse_batch_file(str(empty_file))


def test_parse_batch_file_not_found():
    with pytest.raises(FileNotFoundError):
        parse_batch_file("non_existent_file_12345.txt")


def test_detect_content_type_url_patterns():
    # Definite course pattern
    assert detect_content_type("https://learning.oreilly.com/course/python/123/") == "course"
    # Definite audiobook pattern
    assert detect_content_type("https://learning.oreilly.com/audiobooks/atomic-habits/9780525624134/") == "audiobook"
    # Definite book pattern
    assert detect_content_type("https://learning.oreilly.com/books/python-crash-course/9781593279288/") == "book"


def test_detect_content_type_ambiguous_url_with_epub_api():
    # URL is /library/view/ which could be book or video
    url = "https://learning.oreilly.com/library/view/ai-engineering/9781098166298/"

    mock_session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"files": ["content.opf", "chapter1.html"]}
    mock_session.get.return_value = mock_resp

    content_type = detect_content_type(url, session=mock_session)
    assert content_type == "book"
    mock_session.get.assert_called_once_with(
        "https://learning.oreilly.com/api/v2/epubs/urn:orm:book:9781098166298/",
        timeout=10,
    )


def test_detect_content_type_videos_url_as_audiobook_via_page_title():
    # Issue #8 example: audiobook hosted under /videos/ URL
    url = "https://learning.oreilly.com/videos/ai-engineering/9781663753052/"

    # EPUB API returns 404 (not a book)
    mock_session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_session.get.return_value = mock_resp

    mock_driver = MagicMock()
    mock_driver.navigation.title = "AI Engineering [Audiobook]"

    content_type = detect_content_type(url, session=mock_session, driver=mock_driver)
    assert content_type == "audiobook"


def test_detect_content_type_videos_url_as_course_via_page_title():
    url = "https://learning.oreilly.com/videos/fastapi/9781804613764/"

    mock_session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_session.get.return_value = mock_resp

    mock_driver = MagicMock()
    mock_driver.navigation.title = "Building Web APIs with FastAPI [Video]"

    content_type = detect_content_type(url, session=mock_session, driver=mock_driver)
    assert content_type == "course"


def test_detect_content_type_audiobook_via_dom():
    url = "https://learning.oreilly.com/videos/ai-engineering/9781663753052/"

    mock_session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_session.get.return_value = mock_resp

    mock_driver = MagicMock()
    mock_driver.navigation.title = "AI Engineering"
    mock_driver.actions.execute_js.return_value = True

    content_type = detect_content_type(url, session=mock_session, driver=mock_driver)
    assert content_type == "audiobook"


def test_detect_content_type_audiobook_via_parenthesized_title():
    # Example from user: Design for How People Learn (Audiobook)
    url = "https://learning.oreilly.com/videos/design-for-how/9780135369814/"

    mock_session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_session.get.return_value = mock_resp

    mock_driver = MagicMock()
    mock_driver.navigation.title = "Design for How People Learn (Audiobook)"

    content_type = detect_content_type(url, session=mock_session, driver=mock_driver)
    assert content_type == "audiobook"


def test_detect_content_type_exact_user_batch_items():
    book_url = "https://learning.oreilly.com/library/view/ai-engineering/9781098166298/"
    audio_url = "https://learning.oreilly.com/videos/ai-engineering/9781663753052/"
    course_url = "https://learning.oreilly.com/course/agentic-ai-architectures/9781807785192/"

    session = MagicMock()
    def get_side_effect(url, *args, **kwargs):
        resp = MagicMock()
        if "9781098166298" in url:
            resp.status_code = 200
            resp.json.return_value = {"files": ["content.opf"]}
        else:
            resp.status_code = 404
        return resp
    session.get.side_effect = get_side_effect

    # 1. Book with session + driver -> Must be "book"
    mock_driver_book = MagicMock()
    mock_driver_book.navigation.title = "AI Engineering [Book]"
    assert detect_content_type(book_url, session=session, driver=mock_driver_book) == "book"

    # 2. Audiobook with session + driver -> Must be "audiobook"
    mock_driver_audio = MagicMock()
    mock_driver_audio.navigation.title = "AI Engineering (Audiobook)"
    assert detect_content_type(audio_url, session=session, driver=mock_driver_audio) == "audiobook"

    # 3. Course with session + driver -> Must be "course"
    mock_driver_course = MagicMock()
    mock_driver_course.navigation.title = "Agentic AI Architectures [Video]"
    assert detect_content_type(course_url, session=session, driver=mock_driver_course) == "course"




def test_batch_processor_single_browser_lifecycle(tmp_path):
    batch_file = tmp_path / "urls.txt"
    batch_file.write_text(
        "https://learning.oreilly.com/course/course-1/\n"
        "https://learning.oreilly.com/library/view/book-1/9781234567890/\n",
        encoding="utf-8",
    )

    config = DownloaderConfig(
        url=None,
        output_dir=str(tmp_path),
        cooling_period=0,
    )

    mock_bm = MagicMock()
    mock_driver = MagicMock()
    mock_bm.start.return_value = mock_driver

    with patch("oreilly_downloader.core.batch.BrowserFactory.create", return_value=mock_bm), \
         patch("oreilly_downloader.core.batch.AuthService") as mock_auth_cls, \
         patch("oreilly_downloader.core.batch.authenticate_session", return_value=True), \
         patch("oreilly_downloader.core.batch.CourseStructureScraper") as mock_scraper_cls, \
         patch("oreilly_downloader.core.batch.MediaUrlResolver") as mock_resolver_cls, \
         patch("oreilly_downloader.core.batch.DownloaderService") as mock_dl_cls, \
         patch("oreilly_downloader.core.batch.BookDownloaderService") as mock_book_cls, \
         patch("oreilly_downloader.core.batch.detect_content_type") as mock_detect:

        mock_detect.side_effect = ["course", "book"]

        mock_dl_instance = mock_dl_cls.return_value
        mock_book_instance = mock_book_cls.return_value
        mock_book_instance.download_book.return_value = True
        mock_scraper_instance = mock_scraper_cls.return_value
        mock_scraper_instance.extract_course_structure.return_value = {"Chapter 1": {}}

        processor = BatchProcessor(config, batch_file_path=str(batch_file))
        results = processor.run()

        # Browser started and stopped ONCE for all items
        mock_bm.start.assert_called_once()
        mock_bm.stop.assert_called_once()

        assert len(results) == 2
        assert results[0].success is True
        assert results[0].content_type == "course"
        assert results[1].success is True
        assert results[1].content_type == "book"


def test_batch_processor_cooling_period(tmp_path):
    batch_file = tmp_path / "urls.txt"
    batch_file.write_text(
        "https://learning.oreilly.com/course/course-1/\n"
        "https://learning.oreilly.com/course/course-2/\n"
        "https://learning.oreilly.com/course/course-3/\n",
        encoding="utf-8",
    )

    config = DownloaderConfig(
        url=None,
        output_dir=str(tmp_path),
        cooling_period=90,  # 90 seconds (1.5 min) cooling period
    )

    mock_bm = MagicMock()
    mock_driver = MagicMock()
    mock_bm.start.return_value = mock_driver

    with patch("oreilly_downloader.core.batch.BrowserFactory.create", return_value=mock_bm), \
         patch("oreilly_downloader.core.batch.AuthService"), \
         patch("oreilly_downloader.core.batch.authenticate_session", return_value=True), \
         patch("oreilly_downloader.core.batch.detect_content_type", return_value="course"), \
         patch("oreilly_downloader.core.batch.CourseStructureScraper"), \
         patch("oreilly_downloader.core.batch.MediaUrlResolver"), \
         patch("oreilly_downloader.core.batch.DownloaderService"), \
         patch("oreilly_downloader.core.batch.time.sleep") as mock_sleep:

        processor = BatchProcessor(config, batch_file_path=str(batch_file))
        results = processor.run()

        assert len(results) == 3
        # For 3 items, sleep is called between 1->2 and 2->3 (exactly 2 times)
        assert mock_sleep.call_count == 2
        mock_sleep.assert_has_calls([call(90), call(90)])


def test_batch_processor_fault_tolerance(tmp_path):
    batch_file = tmp_path / "urls.txt"
    batch_file.write_text(
        "https://learning.oreilly.com/course/good-course/\n"
        "https://learning.oreilly.com/course/failing-course/\n"
        "https://learning.oreilly.com/course/another-good-course/\n",
        encoding="utf-8",
    )

    config = DownloaderConfig(
        url=None,
        output_dir=str(tmp_path),
        cooling_period=0,
    )

    mock_bm = MagicMock()
    mock_driver = MagicMock()
    mock_bm.start.return_value = mock_driver

    with patch("oreilly_downloader.core.batch.BrowserFactory.create", return_value=mock_bm), \
         patch("oreilly_downloader.core.batch.AuthService"), \
         patch("oreilly_downloader.core.batch.authenticate_session", return_value=True), \
         patch("oreilly_downloader.core.batch.detect_content_type", return_value="course"), \
         patch("oreilly_downloader.core.batch.CourseStructureScraper") as mock_scraper_cls, \
         patch("oreilly_downloader.core.batch.MediaUrlResolver"), \
         patch("oreilly_downloader.core.batch.DownloaderService"):

        # The scraper returns structure for #1 and #3, but raises error for #2
        mock_scraper = mock_scraper_cls.return_value
        mock_scraper.extract_course_structure.side_effect = [
            {"Chapter 1": {}},
            RuntimeError("Network timeout loading accordion"),
            {"Chapter 1": {}},
        ]

        processor = BatchProcessor(config, batch_file_path=str(batch_file))
        results = processor.run()

        # All 3 processed, #2 marked failed, #1 and #3 marked success
        assert len(results) == 3
        assert results[0].success is True
        assert results[1].success is False
        assert "Network timeout" in results[1].error_message
        assert results[2].success is True


def test_cli_routes_to_batch_processor_with_flag(tmp_path):
    batch_file = tmp_path / "urls.txt"
    batch_file.write_text("https://learning.oreilly.com/course/test/\n", encoding="utf-8")

    from oreilly_downloader.cli import main
    test_args = ["oreilly-dl", "--batch", str(batch_file), "--cooling-period", "120"]

    with patch("sys.argv", test_args), \
         patch("oreilly_downloader.core.batch.BatchProcessor.run") as mock_run:
        main()
        mock_run.assert_called_once()


def test_cli_routes_to_batch_processor_with_positional_file(tmp_path):
    batch_file = tmp_path / "download_me.txt"
    batch_file.write_text("https://learning.oreilly.com/course/test/\n", encoding="utf-8")

    from oreilly_downloader.cli import main
    test_args = ["oreilly-dl", str(batch_file)]

    with patch("sys.argv", test_args), \
         patch("oreilly_downloader.core.batch.BatchProcessor.run") as mock_run:
        main()
        mock_run.assert_called_once()


def test_cli_defaults_headless_false_and_cooling_period(tmp_path):
    batch_file = tmp_path / "download_me.txt"
    batch_file.write_text("https://learning.oreilly.com/course/test/\n", encoding="utf-8")

    from oreilly_downloader.cli import main
    test_args = ["oreilly-dl", str(batch_file)]

    with patch("sys.argv", test_args), \
         patch("oreilly_downloader.core.batch.BatchProcessor") as mock_processor_cls:
        main()
        mock_processor_cls.assert_called_once()
        config = mock_processor_cls.call_args[0][0]
        assert config.headless is False
        assert config.cooling_period == DownloaderConfig.cooling_period


def test_cli_headless_flag_enables_headless(tmp_path):
    batch_file = tmp_path / "download_me.txt"
    batch_file.write_text("https://learning.oreilly.com/course/test/\n", encoding="utf-8")

    from oreilly_downloader.cli import main
    test_args = ["oreilly-dl", str(batch_file), "--headless"]

    with patch("sys.argv", test_args), \
         patch("oreilly_downloader.core.batch.BatchProcessor") as mock_processor_cls:
        main()
        mock_processor_cls.assert_called_once()
        config = mock_processor_cls.call_args[0][0]
        assert config.headless is True


