import os
import shutil
import zipfile
import pytest
from unittest.mock import MagicMock, patch
from oreilly_downloader.core.config import DownloaderConfig
from oreilly_downloader.core.epub import BookDownloaderService

def test_downloader_config_epub_default():
    config = DownloaderConfig(
        url="https://learning.oreilly.com/library/view/test-book/9781234567890/",
        epub=True
    )
    assert config.epub is True

def test_extract_isbn():
    service = BookDownloaderService()
    # Test valid 13-digit ISBN extraction from standard URL
    assert service.extract_isbn("https://learning.oreilly.com/library/view/designing-distributed-systems/9781491983638/") == "9781491983638"
    
    # Test valid 10-digit ISBN extraction from URL
    assert service.extract_isbn("https://learning.oreilly.com/library/view/another-book/0134757599/") == "0134757599"

    # Test raw numeric string fallback
    assert service.extract_isbn("9781491983638") == "9781491983638"
    assert service.extract_isbn("https://learning.oreilly.com/library/view/title/1234567890123/") == "1234567890123"

    # Test invalid URL
    assert service.extract_isbn("https://learning.oreilly.com/library/view/title/") is None

def test_download_book_success(tmp_path):
    output_dir = os.path.join(tmp_path, "downloads")
    os.makedirs(output_dir, exist_ok=True)
    
    config = DownloaderConfig(
        url="https://learning.oreilly.com/library/view/test-book/9781491958698/",
        epub=True,
        output_dir=output_dir,
        max_workers=2
    )

    # Mock responses
    mock_session = MagicMock()
    
    # Mock metadata request
    mock_meta_response = MagicMock()
    mock_meta_response.status_code = 200
    mock_meta_response.json.return_value = {
        "title": "Test-Driven Development with Python, 2nd Edition [Book]",
        "isbn": "9781491958650"
    }

    # Mock files request
    mock_files_response = MagicMock()
    mock_files_response.status_code = 200
    mock_files_response.json.return_value = {
        "count": 4,
        "results": [
            {
                "full_path": "content.opf",
                "url": "https://learning.oreilly.com/api/v2/epubs/urn:orm:book:9781491958698/files/content.opf",
                "media_type": "application/oebps-package+xml"
            },
            {
                "full_path": "toc.ncx",
                "url": "https://learning.oreilly.com/api/v2/epubs/urn:orm:book:9781491958698/files/toc.ncx",
                "media_type": "application/x-dtbncx+xml"
            },
            {
                "full_path": "epub.css",
                "url": "https://learning.oreilly.com/api/v2/epubs/urn:orm:book:9781491958698/files/epub.css",
                "media_type": "text/css"
            },
            {
                "full_path": "chapter1.html",
                "url": "https://learning.oreilly.com/api/v2/epubs/urn:orm:book:9781491958698/files/chapter1.html",
                "media_type": "text/html",
                "kind": "chapter"
            }
        ]
    }

    # Mock individual file download content request
    mock_file_download_response = MagicMock()
    mock_file_download_response.status_code = 200
    mock_file_download_response.iter_content.return_value = [b"dummy data"]
    mock_file_download_response.text = "<div>dummy html content</div>"

    # Assign side effects to requests.Session.get calls
    def get_side_effect(url, *args, **kwargs):
        if "urn:orm:book:9781491958698/files/?limit=" in url:
            return mock_files_response
        elif "urn:orm:book:9781491958698/files/" in url:
            return mock_file_download_response
        else:
            return mock_meta_response

    mock_session.get.side_effect = get_side_effect

    service = BookDownloaderService(output_dir=output_dir)
    success = service.download_book(config, mock_session)

    assert success is True
    
    # Check that EPUB is generated in the books subdirectory
    expected_epub = os.path.join(output_dir, "books", "data", "Test-Driven Development with Python, 2nd Edition", "Test-Driven Development with Python, 2nd Edition.epub")
    assert os.path.exists(expected_epub)

    # Check zip contents
    with zipfile.ZipFile(expected_epub, "r") as epub:
        # Verify mandatory EPUB files
        assert "mimetype" in epub.namelist()
        assert "META-INF/container.xml" in epub.namelist()
        
        # Verify mimetype is uncompressed
        mimetype_info = epub.getinfo("mimetype")
        assert mimetype_info.compress_type == zipfile.ZIP_STORED
        assert epub.read("mimetype") == b"application/epub+zip"
        
        # Verify container.xml contents
        container_content = epub.read("META-INF/container.xml").decode("utf-8")
        assert 'full-path="content.opf"' in container_content
        
        # Verify downloaded files
        assert "content.opf" in epub.namelist()
        assert "toc.ncx" in epub.namelist()
        assert "epub.css" in epub.namelist()
        assert "chapter1.html" in epub.namelist()

    # Check that temp directory is cleaned up
    temp_dir = os.path.join(output_dir, ".temp_9781491958698")
    assert not os.path.exists(temp_dir)

def test_download_book_with_web_viewer(tmp_path):
    output_dir = os.path.join(tmp_path, "downloads")
    os.makedirs(output_dir, exist_ok=True)
    
    config = DownloaderConfig(
        url="https://learning.oreilly.com/library/view/test-book/9781491958698/",
        epub=True,
        web_viewer=True,
        output_dir=output_dir,
        max_workers=2
    )

    mock_session = MagicMock()
    
    mock_meta_response = MagicMock()
    mock_meta_response.status_code = 200
    mock_meta_response.json.return_value = {
        "title": "Interactive Book Test",
        "isbn": "9781491958698"
    }

    mock_files_response = MagicMock()
    mock_files_response.status_code = 200
    mock_files_response.json.return_value = {
        "count": 2,
        "results": [
            {
                "full_path": "content.opf",
                "url": "https://learning.oreilly.com/api/v2/epubs/urn:orm:book:9781491958698/files/content.opf",
                "media_type": "application/oebps-package+xml"
            },
            {
                "full_path": "toc.ncx",
                "url": "https://learning.oreilly.com/api/v2/epubs/urn:orm:book:9781491958698/files/toc.ncx",
                "media_type": "application/x-dtbncx+xml"
            }
        ]
    }

    mock_file_download_response = MagicMock()
    mock_file_download_response.status_code = 200
    mock_file_download_response.iter_content.return_value = [b"dummy data"]
    mock_file_download_response.text = "<div>dummy html content</div>"

    def get_side_effect(url, *args, **kwargs):
        if "urn:orm:book:9781491958698/files/?limit=" in url:
            return mock_files_response
        elif "urn:orm:book:9781491958698/files/" in url:
            return mock_file_download_response
        else:
            return mock_meta_response

    mock_session.get.side_effect = get_side_effect

    service = BookDownloaderService(output_dir=output_dir)
    success = service.download_book(config, mock_session)

    assert success is True
    
    # Check that EPUB is generated
    book_root_dir = os.path.join(output_dir, "books", "data", "Interactive Book Test")
    expected_epub = os.path.join(book_root_dir, "Interactive Book Test.epub")
    assert os.path.exists(expected_epub)

    # Check that web viewer files are created in the book subfolder
    book_assets_dir = os.path.join(book_root_dir, "book")
    assert os.path.exists(book_root_dir)
    assert os.path.exists(os.path.join(book_root_dir, "start_viewer.bat"))
    assert os.path.exists(os.path.join(book_root_dir, "start_viewer.sh"))
    assert os.path.exists(os.path.join(book_root_dir, "serve.py"))
    assert os.path.exists(book_assets_dir)
    assert os.path.exists(os.path.join(book_assets_dir, "index.html"))
    assert os.path.exists(os.path.join(book_assets_dir, "content.opf"))
    assert os.path.exists(os.path.join(book_assets_dir, "toc.ncx"))

    # Verify index.html content contains sidebar elements and layout loader script
    with open(os.path.join(book_assets_dir, "index.html"), "r", encoding="utf-8") as f:
        html_viewer = f.read()
        assert "Offline Book Reader" in html_viewer
        assert "toc-list" in html_viewer
        assert "fetch('toc.ncx')" in html_viewer

def test_serve_py_template_syntax():
    from oreilly_downloader.core.templates import SERVE_PY_TEMPLATE
    try:
        compile(SERVE_PY_TEMPLATE, "serve.py", "exec")
    except SyntaxError as e:
        pytest.fail(f"SERVE_PY_TEMPLATE contains a Python syntax error: {e}")

