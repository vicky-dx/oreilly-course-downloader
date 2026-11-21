from .browsers import Logger
import os
import re
import json
import shutil
import zipfile
import requests
import concurrent.futures
from html import escape
from html import unescape
from html.parser import HTMLParser
from xml.sax.saxutils import escape as xml_escape
from xml.etree import ElementTree
from typing import Optional, Dict, Any, List
from colorama import Fore, init
from tqdm import tqdm
from .utils import SanityUtils
from .templates import (
    FONT_FACES_TEMPLATE,
    FORMATTING_OVERRIDES,
    WEB_VIEWER_HTML_TEMPLATE
)
from .library_templates import (
    ORM_ICONS_CSS_TEMPLATE,
    LIBRARY_INDEX_HTML_TEMPLATE,
    LIBRARY_SERVE_PY_TEMPLATE,
    LIBRARY_BAT_LAUNCHER_TEMPLATE,
    LIBRARY_SH_LAUNCHER_TEMPLATE
)

init(autoreset=True)


class _XHTMLSerializer(HTMLParser):
    VOID_ELEMENTS = {
        "area", "base", "br", "col", "embed", "hr", "img", "input",
        "link", "meta", "param", "source", "track", "wbr",
    }

    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.parts: List[str] = []

    def handle_starttag(self, tag: str, attrs):
        rendered_attrs = "".join(
            f' {name}="{escape(value or "", quote=True)}"'
            for name, value in attrs
        )
        if tag.lower() in self.VOID_ELEMENTS:
            self.parts.append(f"<{tag}{rendered_attrs}/>")
        else:
            self.parts.append(f"<{tag}{rendered_attrs}>")

    def handle_startendtag(self, tag: str, attrs):
        rendered_attrs = "".join(
            f' {name}="{escape(value or "", quote=True)}"'
            for name, value in attrs
        )
        self.parts.append(f"<{tag}{rendered_attrs}/>")

    def handle_endtag(self, tag: str):
        if tag.lower() not in self.VOID_ELEMENTS:
            self.parts.append(f"</{tag}>")

    def handle_data(self, data: str):
        self.parts.append(escape(data, quote=False))

    def handle_entityref(self, name: str):
        rendered = unescape(f"&{name};")
        self.parts.append(escape(rendered, quote=False))

    def handle_charref(self, name: str):
        self.parts.append(escape(unescape(f"&#{name};"), quote=False))

    def handle_comment(self, data: str):
        self.parts.append(f"<!--{data}-->")


class BookDownloaderService:
    def __init__(self, output_dir: str = "downloads"):
        self.output_dir = output_dir

    def extract_isbn(self, url: str) -> Optional[str]:
        """Extracts the ISBN (10-13 digits) from the book URL."""
        if not isinstance(url, str):
            return None
        # Check standard view pattern: /view/book-title/9781491983638/
        match = re.search(r'/view/[^/]+/(\d{10,13})', url)
        if match:
            return match.group(1)
        # Fallback to any 10-13 digit sequence in URL
        match = re.search(r'\b\d{10,13}\b', url)
        if match:
            return match.group(0)
        return None

    def fix_mojibake(self, text: str) -> str:
        """Fixes common double-encoded UTF-8 (mojibake) sequences."""
        if not text:
            return text
        replacements = {
            "â": "“",
            "â": "”",
            "â": "’",
            "â": "‘",
            "â": "‐",
            "â": "–",
            "â": "—",
            "â¯": " ",  # narrow no-break space -> normal space
            "â€": " ",
            "â¢": "•",
            "â¦": "…",
            "â¢": "™",
            "â": "−",
            "â ": "†",
            "â¡": "‡",
            "Ã¢â‚¬Å“": "“",
            "Ã¢â‚¬Â": "”",
            "Ã¢â‚¬â„¢": "’",
        }
        for bad, good in replacements.items():
            text = text.replace(bad, good)
        return text

    def _normalize_xhtml(self, content: str) -> str:
        """Serialize chapter HTML as XHTML and ensure a valid HTML root element."""
        content = re.sub(r'^\s*<\?xml[^>]*\?>\s*', "", content, flags=re.IGNORECASE)
        content = re.sub(r'<!doctype[^>]*>', "", content, flags=re.IGNORECASE)

        serializer = _XHTMLSerializer()
        serializer.feed(content)
        serializer.close()
        normalized = "".join(serializer.parts).strip()

        if not re.search(r"<html(?:\s|>)", normalized, flags=re.IGNORECASE):
            normalized = f"""<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="en" lang="en">
<head>
  <meta charset="utf-8"/>
  <title>Chapter</title>
  <link rel="stylesheet" type="text/css" href="epub.css"/>
</head>
<body>
  <div id="book-content">
{normalized}
  </div>
</body>
</html>"""

        return '<?xml version="1.0" encoding="utf-8"?>\n' + normalized

    def _get_asset_destination(self, temp_dir: str, full_path: str) -> Optional[str]:
        """Resolve an API asset path without allowing it to escape temp_dir."""
        if not isinstance(full_path, str) or not full_path.strip():
            return None
        if full_path.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", full_path):
            return None

        normalized = full_path.replace("\\", "/").lstrip("/")
        if any(part in ("", ".", "..") for part in normalized.split("/")):
            return None

        temp_dir = os.path.abspath(temp_dir)
        dest_path = os.path.abspath(os.path.join(temp_dir, *normalized.split("/")))
        if os.path.commonpath([temp_dir, dest_path]) != temp_dir:
            return None
        return dest_path

    def _find_package_file(self, temp_dir: str, extension: str) -> str:
        """Find an OPF or NCX file recursively and return its EPUB-relative path."""
        for root, _, files in os.walk(temp_dir):
            for file in files:
                if file.lower().endswith(extension.lower()):
                    rel_path = os.path.relpath(os.path.join(root, file), temp_dir)
                    return rel_path.replace(os.path.sep, "/")
        return "content.opf" if extension.lower() == ".opf" else ""

    def _download_file(self, session: requests.Session, url: str, dest_path: str, isbn: str) -> bool:
        """Downloads a single file, handles relative path rewriting/XHTML wrapping for HTML files, and saves it locally."""
        try:
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            lower_dest_path = dest_path.lower()
            
            # Identify text files to clean up double encoding
            is_text = False
            for ext in ['.html', '.xhtml', '.css', '.ncx', '.opf']:
                if lower_dest_path.endswith(ext):
                    is_text = True
                    break

            if is_text:
                response = session.get(url, timeout=20)
                if response.status_code == 200:
                    response.encoding = 'utf-8'
                    content = response.text
                    
                    # Fix any double-encoded UTF-8 (mojibake)
                    content = self.fix_mojibake(content)

                    # For HTML files: rewrite urls and wrap in XHTML if needed
                    if lower_dest_path.endswith('.html') or lower_dest_path.endswith('.xhtml'):
                        content = content.replace(f"/api/v2/epubs/urn:orm:book:{isbn}/files/", "")
                        content = self._normalize_xhtml(content)
                        
                        with open(dest_path, "w", encoding="utf-8") as f:
                            f.write(content)
                        return True

                    # For CSS files: prepend fonts/formatting
                    elif lower_dest_path.endswith('.css'):
                        # Try to load custom override_v1.css from workspace
                        override_paths = [
                            os.path.join(os.getcwd(), "..", "override_v1.css"),
                            os.path.join(os.getcwd(), "override_v1.css"),
                            os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "override_v1.css")
                        ]
                        override_content = ""
                        for path in override_paths:
                            if os.path.exists(path):
                                try:
                                    with open(path, "r", encoding="utf-8") as f:
                                        override_content = f.read()
                                    Logger.success(f"Found and applied custom CSS override from: {path}")
                                    break
                                except Exception as ce:
                                    Logger.warning(f"Failed to read CSS override file {path}: {ce}")
                        
                        content = FONT_FACES_TEMPLATE + content + "\n" + override_content + "\n" + FORMATTING_OVERRIDES
                        with open(dest_path, "w", encoding="utf-8") as f:
                            f.write(content)
                        return True

                    # For metadata/xml files (.ncx, .opf)
                    else:
                        try:
                            ElementTree.fromstring(content)
                        except ElementTree.ParseError:
                            return False
                        with open(dest_path, "w", encoding="utf-8") as f:
                            f.write(content)
                        return True
                else:
                    return False
            
            # For binary files (images, fonts, stylesheets, etc.): download as stream and save raw bytes
            response = session.get(url, stream=True, timeout=20)
            if response.status_code == 200:
                with open(dest_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                return True
            else:
                return False
        except Exception:
            return False

    def download_book(self, config: Any, session: requests.Session) -> bool:
        """Downloads the complete O'Reilly book assets and packages them into an EPUB file."""
        isbn = self.extract_isbn(config.url)
        if not isbn:
            Logger.error(f" Could not extract a valid ISBN/Book ID from URL: {config.url}")
            return False

        Logger.info(f"Detected Book ID (ISBN): {isbn}")
        
        # 1. Fetch book metadata
        meta_url = f"https://learning.oreilly.com/api/v2/epubs/urn:orm:book:{isbn}/"
        Logger.info(f"Fetching book metadata...")
        try:
            meta_resp = session.get(meta_url, timeout=15)
            if meta_resp.status_code != 200:
                Logger.error(f" O'Reilly API returned status {meta_resp.status_code} for metadata. Are you authenticated?")
                return False
            meta_data = meta_resp.json()
        except Exception as e:
            Logger.error(f" Failed to fetch book metadata: {e}")
            return False

        # Extract title and sanitize it
        raw_title = meta_data.get("title")
        if not isinstance(raw_title, str) or not raw_title.strip():
            raw_title = f"OReilly_Book_{isbn}"
        # Clean title suffix patterns
        book_title = re.sub(r'\s*\[book\]\s*$', "", raw_title, flags=re.IGNORECASE).strip()
        sanitized_title = SanityUtils.sanitize_filename(book_title)
        
        Logger.success(f"Title: {book_title}")

        # Check if the book is already fully downloaded and packaged
        book_root_dir = os.path.join(self.output_dir, "books", "data", sanitized_title)
        epub_filename = f"{sanitized_title}.epub"
        epub_path = os.path.join(book_root_dir, epub_filename)
        book_assets_dir = os.path.join(book_root_dir, "book")
        
        epub_exists = os.path.isfile(epub_path) and os.path.getsize(epub_path) > 0
        viewer_needed = getattr(config, "web_viewer", False)
        viewer_exists = os.path.exists(book_assets_dir)
        
        if epub_exists and (not viewer_needed or viewer_exists):
            Logger.success(f" Skipping book: {book_title} (Already downloaded and packaged)")
            Logger.info(f"   - EPUB: {epub_path}")
            if viewer_needed:
                Logger.info(f"   - Web Viewer: {book_assets_dir}")
            return True
        
        # 2. Fetch files list
        files_url = f"https://learning.oreilly.com/api/v2/epubs/urn:orm:book:{isbn}/files/?limit=1000"
        Logger.info(f"Fetching book file structure...")
        try:
            files_resp = session.get(files_url, timeout=15)
            if files_resp.status_code != 200:
                Logger.error(f" O'Reilly API returned status {files_resp.status_code} for files list.")
                return False
            files_data = files_resp.json()
        except Exception as e:
            Logger.error(f" Failed to fetch book file structure: {e}")
            return False

        results = files_data.get("results", [])
        if not results:
            Logger.error(" No book files were returned by the O'Reilly API.")
            return False

        Logger.success(f" Found {len(results)} assets (HTML, images, CSS, fonts).")

        # Create temporary working directory inside output_dir
        temp_dir = os.path.join(self.output_dir, f".temp_{isbn}")
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        os.makedirs(temp_dir, exist_ok=True)

        failed_assets = []
        
        # 3. Concurrently download all files
        max_workers = config.max_workers
        Logger.info(f"Downloading book assets concurrently (using {max_workers} workers)...")

        def _download_task(asset: Dict[str, Any]) -> Dict[str, Any]:
            full_path = asset.get("full_path")
            download_url = asset.get("url")
            dest_path = self._get_asset_destination(temp_dir, full_path)
            if not dest_path or not download_url:
                return {"asset": asset, "success": False}
            
            success = self._download_file(session, download_url, dest_path, isbn)
            return {"asset": asset, "success": success}

        # Submit tasks to thread pool
        futures = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            for asset in results:
                if not asset.get("full_path") or not asset.get("url"):
                    continue
                futures.append(executor.submit(_download_task, asset))

            # Progress bar over finished tasks
            for future in tqdm(concurrent.futures.as_completed(futures), total=len(futures), desc="Downloading Assets"):
                res = future.result()
                if not res["success"]:
                    failed_assets.append(res["asset"])

        # DLQ Reporting
        if failed_assets:
            Logger.warning(f" Failed to download {len(failed_assets)} asset(s).")
            # If critical metadata files (OPF or NCX) failed, abort
            critical_failures = [
                f for f in failed_assets
                if str(f.get("full_path", "")).lower().endswith((".opf", ".ncx"))
            ]
            if critical_failures:
                Logger.error(f" Critical metadata asset(s) { [f.get('full_path') for f in critical_failures] } failed. Aborting EPUB creation.")
                shutil.rmtree(temp_dir)
                return False
            else:
                Logger.warning("Non-critical assets failed. Attempting to package EPUB anyway...")

        # 4. Package into EPUB file
        # Create books/{sanitized_title}/ parent directory structure
        book_root_dir = os.path.join(self.output_dir, "books", "data", sanitized_title)
        os.makedirs(book_root_dir, exist_ok=True)

        epub_filename = f"{sanitized_title}.epub"
        epub_path = os.path.join(book_root_dir, epub_filename)
        Logger.info(f"Packaging EPUB file: {epub_path}...")
        
        try:
            with zipfile.ZipFile(epub_path, "w", zipfile.ZIP_DEFLATED) as epub:
                # EPUB Spec requirement: Write 'mimetype' first, uncompressed (STORED)
                mimetype_info = zipfile.ZipInfo("mimetype")
                mimetype_info.compress_type = zipfile.ZIP_STORED
                epub.writestr(mimetype_info, "application/epub+zip")

                # Find the actual OPF filename dynamically
                opf_file = self._find_package_file(temp_dir, ".opf")

                # EPUB Spec requirement: Write 'META-INF/container.xml'
                container_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="{xml_escape(opf_file)}" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""
                epub.writestr("META-INF/container.xml", container_xml)

                # Write all downloaded assets
                for root, _, files in os.walk(temp_dir):
                    for file in files:
                        full_path = os.path.join(root, file)
                        rel_path = os.path.relpath(full_path, temp_dir)
                        # Normalize path separators to forward slashes for EPUB
                        rel_zip_path = rel_path.replace(os.path.sep, "/")
                        
                        # Skip if mimetype or container.xml were somehow placed here
                        if rel_zip_path in ["mimetype", "META-INF/container.xml"]:
                            continue
                        
                        epub.write(full_path, rel_zip_path)
            
            Logger.success(f"Successfully created EPUB: {epub_path}")

            # 5. If web_viewer configuration is enabled, copy the temp directory to output interactive folder
            if getattr(config, "web_viewer", False):
                try:
                    book_assets_dir = os.path.join(book_root_dir, "book")
                    if os.path.exists(book_assets_dir):
                        shutil.rmtree(book_assets_dir)
                    
                    # Copy temp directory contents to interactive directory
                    shutil.copytree(temp_dir, book_assets_dir)
                    
                    # Write local index.html viewer file
                    index_html_path = os.path.join(book_assets_dir, "index.html")
                    
                    # Find OPF and NCX files in temp_dir
                    opf_file = self._find_package_file(temp_dir, ".opf")
                    
                    ncx_file = self._find_package_file(temp_dir, ".ncx")
                    
                    viewer_html = WEB_VIEWER_HTML_TEMPLATE
                    viewer_html = viewer_html.replace('__OPF_FILE_PLACEHOLDER__', opf_file)
                    viewer_html = viewer_html.replace('__NCX_FILE_PLACEHOLDER__', ncx_file)
                    
                    with open(index_html_path, "w", encoding="utf-8") as f:
                        f.write(viewer_html)

                    # Write local orm-icons.css stylesheet
                    orm_icons_path = os.path.join(book_assets_dir, "orm-icons.css")
                    with open(orm_icons_path, "w", encoding="utf-8") as f:
                        f.write(ORM_ICONS_CSS_TEMPLATE)

                    # Ensure local override_v1.css stylesheet exists to prevent console 404 error
                    override_css_path = os.path.join(book_assets_dir, "override_v1.css")
                    if not os.path.exists(override_css_path):
                        try:
                            import importlib.resources
                            ref = importlib.resources.files("oreilly_downloader.core.resources.templates").joinpath("override_v1.css")
                            override_css_content = ref.read_text(encoding="utf-8")
                        except Exception:
                            override_css_content = "/* Custom CSS overrides for book web viewer */\n"

                        with open(override_css_path, "w", encoding="utf-8") as f:
                            f.write(override_css_content)

                    # Ensure local epub.css stylesheet exists to prevent console 404 errors and restore layout styles
                    epub_css_path = os.path.join(book_assets_dir, "epub.css")
                    if not os.path.exists(epub_css_path):
                        # Find other CSS files in the temp_dir to merge into epub.css
                        other_css_files = []
                        for root, _, files in os.walk(temp_dir):
                            for file in files:
                                if file.endswith('.css') and file not in ['orm-icons.css', 'override_v1.css', 'epub.css']:
                                    other_css_files.append(os.path.join(root, file))
                        
                        if other_css_files:
                            try:
                                css_content = ""
                                for css_file in other_css_files:
                                    with open(css_file, "r", encoding="utf-8") as f:
                                        css_content += f"/* Source: {os.path.basename(css_file)} */\n" + f.read() + "\n"
                                with open(epub_css_path, "w", encoding="utf-8") as f:
                                    f.write(css_content)
                            except Exception:
                                with open(epub_css_path, "w", encoding="utf-8") as f:
                                    f.write("/* Fallback placeholder stylesheet */\n")
                        else:
                            with open(epub_css_path, "w", encoding="utf-8") as f:
                                f.write("/* Placeholder stylesheet to prevent console 404 errors */\n")

                    # Only write book reader assets, no individual viewer servers/launchers required.

                    # Write Unified Library Dashboard files in the parent directory (downloads/books/)
                    library_dir = os.path.dirname(os.path.dirname(book_root_dir))
                    os.makedirs(library_dir, exist_ok=True)
                    
                    lib_index_path = os.path.join(library_dir, "index.html")
                    with open(lib_index_path, "w", encoding="utf-8") as f:
                        f.write(LIBRARY_INDEX_HTML_TEMPLATE)
                        
                    lib_serve_path = os.path.join(library_dir, "serve_library.py")
                    with open(lib_serve_path, "w", encoding="utf-8") as f:
                        f.write(LIBRARY_SERVE_PY_TEMPLATE)
                        
                    lib_bat_path = os.path.join(library_dir, "start_library.bat")
                    with open(lib_bat_path, "w", encoding="utf-8") as f:
                        f.write(LIBRARY_BAT_LAUNCHER_TEMPLATE)
                        
                    lib_sh_path = os.path.join(library_dir, "start_library.sh")
                    with open(lib_sh_path, "w", encoding="utf-8") as f:
                        f.write(LIBRARY_SH_LAUNCHER_TEMPLATE)
                        
                    try:
                        os.chmod(lib_sh_path, 0o755)
                        os.chmod(lib_serve_path, 0o755)
                    except Exception:
                        pass

                    Logger.success(f"Successfully created interactive web viewer assets under: {book_assets_dir}")
                    Logger.success(f"Unified Library Dashboard created/updated at: {library_dir}")
                    Logger.success(f"Run '{os.path.join(library_dir, 'start_library.bat')}' (Windows) or './start_library.sh' (Mac/Linux) to view all your books!")
                except Exception as wve:
                    Logger.warning(f"Warning: Could not update interactive web viewer folder: {wve}")
                    Logger.warning("Please close any open start_viewer.bat console window and try again.")

            return True
        except Exception as e:
            Logger.error(f" Failed to package EPUB file: {e}")
            return False
        finally:
            # Clean up temporary downloads
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)


