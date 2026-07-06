from .browsers import Logger
import os
import re
import json
import shutil
import zipfile
import requests
import concurrent.futures
from typing import Optional, Dict, Any, List
from colorama import Fore, init
from tqdm import tqdm
from .utils import SanityUtils
from .templates import (
    FONT_FACES_TEMPLATE,
    FORMATTING_OVERRIDES,
    BAT_LAUNCHER_TEMPLATE,
    SH_LAUNCHER_TEMPLATE,
    WEB_VIEWER_HTML_TEMPLATE,
    SERVE_PY_TEMPLATE
)
from .library_templates import (
    ORM_ICONS_CSS_TEMPLATE,
    LIBRARY_INDEX_HTML_TEMPLATE,
    LIBRARY_SERVE_PY_TEMPLATE,
    LIBRARY_BAT_LAUNCHER_TEMPLATE,
    LIBRARY_SH_LAUNCHER_TEMPLATE
)

init(autoreset=True)

class BookDownloaderService:
    def __init__(self, output_dir: str = "downloads"):
        self.output_dir = output_dir

    def extract_isbn(self, url: str) -> Optional[str]:
        """Extracts the ISBN (10-13 digits) from the book URL."""
        # Check standard view pattern: /view/book-title/9781491983638/
        match = re.search(r'/view/[^/]+/(\d{10,13})', url)
        if match:
            return match.group(1)
        # Fallback to any 10-13 digit sequence in URL
        match = re.search(r'\b\d{10,13}\b', url)
        if match:
            return match.group(0)
        return None

    def _download_file(self, session: requests.Session, url: str, dest_path: str, isbn: str) -> bool:
        """Downloads a single file, handles relative path rewriting/XHTML wrapping for HTML files, and saves it locally."""
        try:
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            
            # For HTML files: download, rewrite urls, wrap in XHTML skeleton, and save as text
            if dest_path.endswith('.html') or dest_path.endswith('.xhtml'):
                response = session.get(url, timeout=20)
                if response.status_code == 200:
                    content = response.text
                    
                    # Rewrite O'Reilly absolute API paths to relative paths
                    content = content.replace(f"/api/v2/epubs/urn:orm:book:{isbn}/files/", "")
                    
                    # Check if already wrapped, if not wrap it in a proper XHTML skeleton with book-content container
                    if "<html>" not in content.lower():
                        wrapped_content = f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="en" lang="en">
<head>
  <meta charset="utf-8"/>
  <title>Chapter</title>
  <link rel="stylesheet" type="text/css" href="epub.css"/>
</head>
<body>
  <div id="book-content">
{content}
  </div>
</body>
</html>"""
                        content = wrapped_content
                    
                    with open(dest_path, "w", encoding="utf-8") as f:
                        f.write(content)
                    return True
                else:
                    return False

            # For CSS files: download, prepend font face declarations, and save
            if dest_path.endswith('.css'):
                response = session.get(url, timeout=20)
                if response.status_code == 200:
                    css_content = response.text
                    
                    # Try to load custom override_v1.css from workspace
                    override_paths = [
                        os.path.join(os.getcwd(), "..", "override_v1.css"),
                        os.path.join(os.getcwd(), "override_v1.css"),
                        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "override_v1.css")
                    ]
                    found_override = False
                    for path in override_paths:
                        if os.path.exists(path):
                            try:
                                with open(path, "r", encoding="utf-8") as f:
                                    css_content = f.read()
                                Logger.success(f"🎨 Found and applied custom CSS override from: {path}")
                                found_override = True
                                break
                            except Exception as ce:
                                Logger.warning(f" Failed to read CSS override file {path}: {ce}")
                    
                    css_content = FONT_FACES_TEMPLATE + css_content + FORMATTING_OVERRIDES
                    with open(dest_path, "w", encoding="utf-8") as f:
                        f.write(css_content)
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

        Logger.info(f"📖 Detected Book ID (ISBN): {isbn}")
        
        # 1. Fetch book metadata
        meta_url = f"https://learning.oreilly.com/api/v2/epubs/urn:orm:book:{isbn}/"
        Logger.info(f"⚡ Fetching book metadata...")
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
        raw_title = meta_data.get("title", f"OReilly_Book_{isbn}")
        # Clean title suffix patterns
        book_title = re.sub(r'\s*\[book\]\s*$', "", raw_title, flags=re.IGNORECASE).strip()
        sanitized_title = SanityUtils.sanitize_filename(book_title)
        
        Logger.success(f"📖 Title: {book_title}")

        # Check if the book is already fully downloaded and packaged
        book_root_dir = os.path.join(self.output_dir, "books", "data", sanitized_title)
        epub_filename = f"{sanitized_title}.epub"
        epub_path = os.path.join(book_root_dir, epub_filename)
        book_assets_dir = os.path.join(book_root_dir, "book")
        
        epub_exists = os.path.exists(epub_path)
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
        Logger.info(f"⚡ Fetching book file structure...")
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
        Logger.info(f"📥 Downloading book assets concurrently (using {max_workers} workers)...")

        def _download_task(asset: Dict[str, Any]) -> Dict[str, Any]:
            full_path = asset.get("full_path")
            download_url = asset.get("url")
            dest_path = os.path.join(temp_dir, full_path)
            
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
            critical_failures = [f for f in failed_assets if f.get("full_path") in ["content.opf", "toc.ncx"]]
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
        Logger.info(f"📦 Packaging EPUB file: {epub_path}...")
        
        try:
            with zipfile.ZipFile(epub_path, "w", zipfile.ZIP_DEFLATED) as epub:
                # EPUB Spec requirement: Write 'mimetype' first, uncompressed (STORED)
                mimetype_info = zipfile.ZipInfo("mimetype")
                mimetype_info.compress_type = zipfile.ZIP_STORED
                epub.writestr(mimetype_info, "application/epub+zip")

                # EPUB Spec requirement: Write 'META-INF/container.xml'
                container_xml = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="content.opf" media-type="application/oebps-package+xml"/>
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
            
            Logger.success(f"🎉 Successfully created EPUB: {epub_path}")

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
                    with open(index_html_path, "w", encoding="utf-8") as f:
                        f.write(WEB_VIEWER_HTML_TEMPLATE)

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

                    Logger.success(f"🎉 Successfully created interactive web viewer assets under: {book_assets_dir}")
                    Logger.success(f"📚 Unified Library Dashboard created/updated at: {library_dir}")
                    Logger.success(f"👉 Run '{os.path.join(library_dir, 'start_library.bat')}' (Windows) or './start_library.sh' (Mac/Linux) to view all your books!")
                except Exception as wve:
                    Logger.warning(f" Warning: Could not update interactive web viewer folder: {wve}")
                    Logger.warning("👉 Please close any open start_viewer.bat console window and try again.")

            return True
        except Exception as e:
            Logger.error(f" Failed to package EPUB file: {e}")
            return False
        finally:
            # Clean up temporary downloads
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)


