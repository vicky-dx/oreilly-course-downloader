import os
import re
import copy
import json
import time
import requests
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from colorama import Fore

from .browsers import BrowserFactory, IBrowser, Logger
from .auth import AuthService, authenticate_session, HeadlessAutoLoginFailed
from .config import DownloaderConfig
from .course_scraper import CourseStructureScraper
from .media_resolver import MediaUrlResolver
from .downloader import DownloaderService
from .epub import BookDownloaderService
from .models import Course, Module, Lesson, Video, build_course
from .utils import PathManager, SanityUtils, sync_browser_cookies, ensure_headless_if_no_display
from .strategies import ExecutionContext, StrategyDispatcher


def resolve_batch_file_path(file_path: str) -> str:
    """Resolves batch file path, handling OS path separators, bash-escaped variants
    (e.g. '.download-me.txt' produced by bash unescaping '.\\download-me.txt'),
    and searching parent directories when running from a subfolder.
    """
    if not file_path or not isinstance(file_path, str):
        return file_path

    # Direct check
    if os.path.isfile(file_path):
        return os.path.abspath(file_path)

    candidates = [
        file_path,
        os.path.normpath(file_path),
        file_path.replace("\\", "/"),
    ]

    # Handle common bash escape artifact on Linux/macOS:
    # If the user ran `.\download-me.txt` in bash, bash converts `\d` to `d`, resulting in `.download-me.txt`
    basename = os.path.basename(file_path)
    if basename.startswith(".") and not basename.startswith("..") and len(basename) > 1:
        candidates.append(basename[1:])
        dirname = os.path.dirname(file_path)
        if dirname:
            candidates.append(os.path.join(dirname, basename[1:]))

    if basename not in candidates:
        candidates.append(basename)

    # Check candidates directly in current working directory
    for cand in candidates:
        if cand and os.path.isfile(cand):
            return os.path.abspath(cand)

    # Search in parent directories (up to 4 levels) if running from a subfolder
    search_dirs = []
    curr = os.getcwd()
    for _ in range(4):
        parent = os.path.dirname(curr)
        if parent and parent != curr:
            search_dirs.append(parent)
            curr = parent
        else:
            break

    for sdir in search_dirs:
        for cand in candidates:
            if not cand:
                continue
            full_p = os.path.normpath(os.path.join(sdir, cand))
            if os.path.isfile(full_p):
                Logger.info(f"Resolved batch file from parent directory: {full_p}")
                return full_p

    return file_path


def parse_batch_file(file_path: str) -> List[str]:
    """Reads a text file of URLs, stripping comments (# and //) and blank lines."""
    resolved_path = resolve_batch_file_path(file_path)
    if not os.path.isfile(resolved_path):
        raise FileNotFoundError(f"Batch file not found: {file_path}")

    urls: List[str] = []
    with open(resolved_path, "r", encoding="utf-8") as f:
        for line in f:
            cleaned = line.strip()
            if not cleaned or cleaned.startswith("#") or cleaned.startswith("//"):
                continue
            urls.append(cleaned)

    if not urls:
        raise ValueError(f"No valid URLs found in batch file: {file_path}")

    return urls


def detect_content_type(
    url: str,
    session: Optional[requests.Session] = None,
    driver: Optional[Any] = None,
) -> str:
    """Autodetects whether an O'Reilly URL points to a 'course', 'audiobook', or 'book'.
    Delegates dynamically to registered ContentStrategy implementations (OCP).
    """
    dispatcher = StrategyDispatcher()
    return dispatcher.detect_content_type(url, session=session, driver=driver)


@dataclass
class BatchItemResult:
    url: str
    content_type: str
    success: bool
    title: Optional[str] = None
    error_message: Optional[str] = None


class BatchProcessor:
    def __init__(self, config: DownloaderConfig, batch_file_path: Optional[str] = None):
        self.config = config
        self.batch_file_path = batch_file_path or config.batch_file
        if not self.batch_file_path:
            raise ValueError("No batch file path provided.")
        self.urls = parse_batch_file(self.batch_file_path)
        self.results: List[BatchItemResult] = []

    def run(self) -> List[BatchItemResult]:
        clean_session = self.config.auto_signup

        if not ensure_headless_if_no_display(self.config):
            return []

        Logger.info(f"Starting batch processor for {len(self.urls)} items...")

        while True:
            Logger.info("Initializing browser session...")

            factory_kwargs = {
                "browser_type": self.config.browser_type,
                "headless": self.config.headless,
                "clean_session": clean_session,
            }
            if self.config.browser_binary is not None:
                factory_kwargs["browser_binary"] = self.config.browser_binary

            try:
                bm: IBrowser = BrowserFactory.create(**factory_kwargs)
                driver = bm.start()
            except (RuntimeError, FileNotFoundError) as be:
                Logger.error(f"Browser initialization failed: {be}")
                return []

            if not driver:
                raise RuntimeError("Failed to start browser for batch processing.")

            try:
                auth = AuthService(driver)
                if not authenticate_session(auth, self.config):
                    return []

                # Prepare HTTP requests session with browser cookies
                session = requests.Session()
                session.headers.update({
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"
                })
                sync_browser_cookies(driver, session)

                # Extract Kaltura token once if needed
                ks = None
                if not self.config.manual_login:
                    Logger.info("Extracting active Kaltura Session (ks) token for batch...")
                    ks = auth.get_ks()

                # Pre-flight FFmpeg check
                ffmpeg_path = SanityUtils.get_ffmpeg_path() or "ffmpeg"

                scraper = CourseStructureScraper(driver)
                resolver = MediaUrlResolver(driver, ks=ks)
                downloader = DownloaderService(output_dir=self.config.output_dir, ffmpeg_path=ffmpeg_path)
                book_dl = BookDownloaderService(output_dir=self.config.output_dir)

                context = ExecutionContext(
                    driver=driver,
                    session=session,
                    scraper=scraper,
                    resolver=resolver,
                    downloader=downloader,
                    book_dl=book_dl,
                    ks=ks,
                )
                dispatcher = StrategyDispatcher()

                total = len(self.urls)
                for index, url in enumerate(self.urls, start=1):
                    Logger.panel(
                        f"📦 Batch Item [{index}/{total}]",
                        [f"Target: {url}"],
                        border_color=Fore.CYAN
                    )

                    content_type = "course"
                    item_title = None
                    if hasattr(context.scraper, "course_title"):
                        context.scraper.course_title = ""

                    try:
                        # Navigate driver to target URL if not already there, so DOM header and contentIcon are loaded
                        try:
                            current_url = getattr(getattr(driver, "navigation", None), "url", "") or ""
                            if isinstance(current_url, str) and current_url.startswith(("http://", "https://")):
                                if current_url.rstrip("/") != url.rstrip("/"):
                                    driver.navigation.to(url)
                                    time.sleep(2)
                        except Exception as nav_e:
                            Logger.debug(f"Pre-navigation in batch item failed: {nav_e}")

                        # Autodetect format
                        content_type = detect_content_type(url, session=session, driver=driver)
                        Logger.info(f"🔎 Auto-detected format: [{content_type.upper()}]")

                        item_config = copy.copy(self.config)
                        dispatcher.dispatch(content_type, url, item_config, context)

                        raw_title = getattr(context.scraper, "course_title", "") or getattr(getattr(driver, "navigation", None), "title", "")
                        if not isinstance(raw_title, str) or not raw_title.strip():
                            raw_title = "OReilly Extracted Item"
                        cleaned_title = re.sub(
                            r'\s*[\(\[](video|book|audiobook|audio\s+book)[\)\]]\s*$', "", raw_title, flags=re.IGNORECASE
                        ).strip()
                        if not cleaned_title:
                            cleaned_title = "OReilly Extracted Item"
                        item_title = cleaned_title

                        self.results.append(BatchItemResult(
                            url=url,
                            content_type=content_type,
                            success=True,
                            title=item_title
                        ))
                        Logger.success(f"Item [{index}/{total}] completed successfully!")

                    except Exception as e:
                        Logger.error(f"Error processing item [{index}/{total}] ({url}): {e}")
                        self.results.append(BatchItemResult(
                            url=url,
                            content_type=content_type,
                            success=False,
                            error_message=str(e),
                            title=item_title
                        ))

                    # Cooling period between downloads (skip after the last item)
                    if index < total and self.config.cooling_period > 0:
                        Logger.info(f"⏳ Cooling down for {self.config.cooling_period}s before next download...")
                        time.sleep(self.config.cooling_period)

                break

            except HeadlessAutoLoginFailed:
                if self.config.headless and SanityUtils.has_display():
                    Logger.warning("Headless auto-login failed. Retrying in headed (non-headless) mode...")
                    self.config.headless = False
                    continue
                Logger.error("Headless authentication failed and no graphical display ($DISPLAY / $WAYLAND_DISPLAY) is available for visible fallback.")
                return []

            finally:
                bm.stop()
                Logger.info("Batch browser session cleaned up.")

        self.print_summary()
        return self.results

    def print_summary(self):
        """Displays a clean summary table of the batch download execution."""
        success_count = sum(1 for r in self.results if r.success)
        total = len(self.results)
        
        summary_lines = [
            f"Total Processed: {total}",
            f"Successful:      {success_count}",
            f"Failed:          {total - success_count}",
            "",
            "Results Breakdown:"
        ]
        
        for idx, res in enumerate(self.results, start=1):
            status_icon = "✅" if res.success else "❌"
            label = f"[{res.content_type.upper()}]"
            name = res.title or res.url
            if res.success:
                summary_lines.append(f" {status_icon} {label:<11} {name}")
            else:
                summary_lines.append(f" {status_icon} {label:<11} {name} (Error: {res.error_message})")

        Logger.panel(
            f"📊 Batch Download Summary: {success_count}/{total} Successful",
            summary_lines,
            border_color=Fore.GREEN if success_count == total else Fore.YELLOW
        )
