import os
import shutil
import zipfile
import pytest
from xml.etree import ElementTree
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
        ElementTree.fromstring(container_content)
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
    assert os.path.exists(book_assets_dir)
    assert os.path.exists(os.path.join(book_assets_dir, "index.html"))
    assert os.path.exists(os.path.join(book_assets_dir, "content.opf"))
    assert os.path.exists(os.path.join(book_assets_dir, "toc.ncx"))

    # Verify index.html content contains sidebar elements and layout loader script
    with open(os.path.join(book_assets_dir, "index.html"), "r", encoding="utf-8") as f:
        html_viewer = f.read()
        assert "Offline Book Reader" in html_viewer
        assert "toc-list" in html_viewer
        assert "loadTableOfContents()" in html_viewer

def test_serve_py_template_syntax():
    from oreilly_downloader.core.templates import SERVE_PY_TEMPLATE
    try:
        compile(SERVE_PY_TEMPLATE, "serve.py", "exec")
    except SyntaxError as e:
        pytest.fail(f"SERVE_PY_TEMPLATE contains a Python syntax error: {e}")


def test_download_book_skip_if_exists(tmp_path):
    output_dir = os.path.join(tmp_path, "downloads")
    os.makedirs(output_dir, exist_ok=True)

    config = DownloaderConfig(
        url="https://learning.oreilly.com/library/view/test-book/9781491958698/",
        epub=True,
        web_viewer=True,
        output_dir=output_dir,
    )

    # 1. Pretend that the EPUB and web-viewer files already exist
    book_title = "Test-Driven Development with Python, 2nd Edition"
    sanitized_title = "Test-Driven Development with Python, 2nd Edition"
    book_root_dir = os.path.join(output_dir, "books", "data", sanitized_title)
    os.makedirs(book_root_dir, exist_ok=True)
    
    epub_path = os.path.join(book_root_dir, f"{sanitized_title}.epub")
    with open(epub_path, "w") as f:
        f.write("mock epub content")
        
    book_assets_dir = os.path.join(book_root_dir, "book")
    os.makedirs(book_assets_dir, exist_ok=True)

    # 2. Mock requests.Session
    mock_session = MagicMock()
    mock_meta_response = MagicMock()
    mock_meta_response.status_code = 200
    mock_meta_response.json.return_value = {
        "title": book_title + " [Book]",
        "isbn": "9781491958698"
    }
    mock_session.get.return_value = mock_meta_response

    # 3. Call download_book
    service = BookDownloaderService(output_dir=output_dir)
    success = service.download_book(config, mock_session)

    assert success is True
    
    # 4. Verify that we ONLY fetched the metadata, but did NOT make any additional get requests to download files
    # because the download was skipped.
    assert mock_session.get.call_count == 1
    # Check that first call was indeed to the metadata url
    expected_meta_url = "https://learning.oreilly.com/api/v2/epubs/urn:orm:book:9781491958698/"
    mock_session.get.assert_called_once_with(expected_meta_url, timeout=15)


def test_asset_destination_rejects_path_traversal(tmp_path):
    service = BookDownloaderService(output_dir=str(tmp_path))
    temp_dir = os.path.join(str(tmp_path), ".temp_test")
    os.makedirs(temp_dir)

    assert service._get_asset_destination(temp_dir, "../outside.html") is None
    assert service._get_asset_destination(temp_dir, "/tmp/outside.html") is None
    assert service._get_asset_destination(temp_dir, "OEBPS/chapter1.html") == os.path.join(temp_dir, "OEBPS", "chapter1.html")


def test_nested_package_files_are_reported_in_epub(tmp_path):
    service = BookDownloaderService(output_dir=str(tmp_path))
    temp_dir = os.path.join(str(tmp_path), ".temp_test")
    os.makedirs(os.path.join(temp_dir, "OEBPS"))

    opf_path = os.path.join(temp_dir, "OEBPS", "content.opf")
    ncx_path = os.path.join(temp_dir, "OEBPS", "toc.ncx")
    with open(opf_path, "w", encoding="utf-8") as f:
        f.write("<package/>")
    with open(ncx_path, "w", encoding="utf-8") as f:
        f.write("<ncx/>")

    assert service._find_package_file(temp_dir, ".opf") == "OEBPS/content.opf"
    assert service._find_package_file(temp_dir, ".ncx") == "OEBPS/toc.ncx"


def test_chapter_html_is_valid_xhtml(tmp_path):
    service = BookDownloaderService(output_dir=str(tmp_path))
    chapter = service._normalize_xhtml(
        '<div class="intro">Tom & Jerry<br><img src="cover.png"></div>'
    )

    root = ElementTree.fromstring(chapter)
    assert root.tag.endswith("html")
    assert '<br' in chapter
    assert '<img' in chapter
    assert "Tom &amp; Jerry" in chapter


def test_existing_html_root_is_not_double_wrapped(tmp_path):
    service = BookDownloaderService(output_dir=str(tmp_path))
    chapter = service._normalize_xhtml(
        '<html lang="en"><head><title>A &amp; B</title></head><body><p>Hello</p></body></html>'
    )

    assert chapter.count("<html") == 1
    ElementTree.fromstring(chapter)


def test_download_book_with_raw_url_string(tmp_path):
    output_dir = os.path.join(tmp_path, "downloads")
    os.makedirs(output_dir, exist_ok=True)

    url = "https://learning.oreilly.com/library/view/test-book/9781491958698/"

    # Mock responses
    mock_session = MagicMock()
    mock_meta_response = MagicMock()
    mock_meta_response.status_code = 200
    mock_meta_response.json.return_value = {
        "title": "Raw String Book",
        "isbn": "9781491958698"
    }
    mock_files_response = MagicMock()
    mock_files_response.status_code = 200
    mock_files_response.json.return_value = {
        "count": 1,
        "results": [
            {
                "full_path": "content.opf",
                "url": "https://learning.oreilly.com/files/content.opf",
                "media_type": "application/oebps-package+xml"
            }
        ]
    }
    mock_file_download_response = MagicMock()
    mock_file_download_response.status_code = 200
    mock_file_download_response.iter_content.return_value = [b"<package/>"]
    mock_file_download_response.text = "<package/>"

    def get_side_effect(req_url, *args, **kwargs):
        if "files/?limit=" in req_url:
            return mock_files_response
        elif "/files/" in req_url:
            return mock_file_download_response
        return mock_meta_response

    mock_session.get.side_effect = get_side_effect

    service = BookDownloaderService(output_dir=output_dir)
    # ISP: Pass raw URL string directly without constructing DownloaderConfig!
    success = service.download_book(url, mock_session)
    assert success is True
    book_epub = os.path.join(output_dir, "books", "data", "Raw String Book", "Raw String Book.epub")
    assert os.path.exists(book_epub)



