import os
import re
import json
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from dataclasses import dataclass
import requests

from .browsers import Logger
from .config import DownloaderConfig
from .course_scraper import CourseStructureScraper
from .media_resolver import MediaUrlResolver
from .downloader import DownloaderService
from .epub import BookDownloaderService
from .models import Course, build_course
from .utils import PathManager


@dataclass
class ExecutionContext:
    """Shared execution context holding active services and browser sessions (ISP & DIP)."""
    driver: Any
    session: requests.Session
    scraper: CourseStructureScraper
    resolver: MediaUrlResolver
    downloader: DownloaderService
    book_dl: BookDownloaderService
    ks: Optional[str] = None


class ContentStrategy(ABC):
    """Abstract Strategy interface for downloading different O'Reilly content types (OCP & SRP)."""
    @abstractmethod
    def can_handle(
        self,
        url: str,
        session: Optional[requests.Session] = None,
        driver: Optional[Any] = None,
    ) -> bool:
        """Returns True if this strategy can handle the given URL/target."""
        pass

    @abstractmethod
    def handle(
        self,
        url: str,
        config: DownloaderConfig,
        context: ExecutionContext,
    ) -> bool:
        """Executes the content download strategy. Returns True on success, False or raises on failure."""
        pass


class BookStrategy(ContentStrategy):
    """Handles EPUB books extraction, metadata fetching, and EPUB zip packaging."""
    def can_handle(
        self,
        url: str,
        session: Optional[requests.Session] = None,
        driver: Optional[Any] = None,
    ) -> bool:
        lower_url = url.lower()
        if "/videos/" in lower_url or "/course/" in lower_url or "/audiobooks/" in lower_url:
            return False

        if "/books/" in lower_url:
            return True

        # Extract ISBN for API probe
        match = re.search(r'/(?:library/)?view/[^/]+/(\d{10,13})', url) or re.search(r'\b(\d{10,13})\b', url)
        isbn = match.group(1) if match else None

        if session is not None and isbn:
            try:
                epub_api_url = f"https://learning.oreilly.com/api/v2/epubs/urn:orm:book:{isbn}/"
                resp = session.get(epub_api_url, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    if "files" in data:
                        return True
            except Exception as e:
                Logger.debug(f"EPUB API probe failed for {url}: {e}")

        if driver is not None:
            try:
                title = getattr(getattr(driver, "navigation", None), "title", "") or ""
                if isinstance(title, str) and re.search(r'[\(\[]book[\)\]]', title, re.IGNORECASE):
                    return True
            except Exception:
                pass

        if "/library/view/" in lower_url and "video" not in lower_url and "audio" not in lower_url and session is None and driver is None:
            return True

        return False

    def handle(
        self,
        url: str,
        config: DownloaderConfig,
        context: ExecutionContext,
    ) -> bool:
        config.epub = True
        config.audiobook = False
        config.url = url
        success = context.book_dl.download_book(config, context.session)
        if not success:
            raise RuntimeError("EPUB download or packaging failed.")
        return True


class CourseStrategy(ContentStrategy):
    """Handles structured video courses scraping, resolving M3U8 streams, and video downloading."""
    def can_handle(
        self,
        url: str,
        session: Optional[requests.Session] = None,
        driver: Optional[Any] = None,
    ) -> bool:
        lower_url = url.lower()
        if "/course/" in lower_url:
            return True
        if driver is not None:
            try:
                title = getattr(getattr(driver, "navigation", None), "title", "") or ""
                if isinstance(title, str) and re.search(r'\[video\]', title, re.IGNORECASE):
                    return True
            except Exception:
                pass
        if "/videos/" in lower_url:
            return True
        return False

    def handle(
        self,
        url: str,
        config: DownloaderConfig,
        context: ExecutionContext,
    ) -> bool:
        config.epub = False
        config.audiobook = False
        config.url = url

        structure = context.scraper.extract_course_structure(url, is_audiobook=False)
        if not structure:
            raise RuntimeError(f"Failed to extract course structure for {url}.")

        # Dynamically extract course title from driver title (prefer landing page title from scraper)
        raw_title = getattr(context.scraper, "course_title", "") or getattr(getattr(context.driver, "navigation", None), "title", "") or ""
        cleaned_title = re.sub(
            r'\s*[\(\[](video|book|audiobook|audio\s+book)[\)\]]\s*$', "", str(raw_title), flags=re.IGNORECASE
        ).strip()
        if not cleaned_title:
            cleaned_title = "OReilly Extracted Item"

        course = build_course(structure, title=cleaned_title)
        base_dir = os.path.join(context.downloader.output_dir, "courses")
        course_dir = PathManager.get_course_dir(base_dir, course.title)
        os.makedirs(course_dir, exist_ok=True)

        with open(os.path.join(course_dir, "course_structure.json"), "w", encoding="utf-8") as f:
            json.dump(course.structure, f, indent=2)

        context.downloader.download_course(
            course,
            context.scraper,
            context.resolver,
            config,
            course_dir,
            is_audio_only=False,
        )
        return True


class AudiobookStrategy(ContentStrategy):
    """Handles audiobook chapters extraction and .m4a audio downloading."""
    def can_handle(
        self,
        url: str,
        session: Optional[requests.Session] = None,
        driver: Optional[Any] = None,
    ) -> bool:
        lower_url = url.lower()
        if "/books/" in lower_url:
            return False

        if "/audiobooks/" in lower_url or re.search(r'[-_/]audiobooks?[-_/]?', lower_url):
            return True

        if driver is not None:
            try:
                title = getattr(getattr(driver, "navigation", None), "title", "") or ""
                if isinstance(title, str) and re.search(r'[\(\[](video|book)[\)\]]', title, re.IGNORECASE):
                    return False
                if isinstance(title, str) and re.search(r'[\(\[](audiobook|audio\s+book)[\)\]]', title, re.IGNORECASE):
                    return True
                if hasattr(driver, "actions"):
                    audio_script = r"""
                    const icon = document.querySelector("div[data-testid='contentIcon']");
                    if (icon) {
                        const label = (icon.querySelector('.orm-IconLabel-label')?.textContent || '').trim().toLowerCase();
                        const title = (icon.querySelector('.orm-Icon-title')?.textContent || '').trim().toLowerCase();
                        if (label === 'book' || title === 'book' || icon.querySelector('.orm-icon-book')) return false;
                        if (label === 'video' || title === 'video' || icon.querySelector('.orm-icon-video')) return false;
                        if (label === 'audiobook' || title === 'audio book' || icon.querySelector('span.orm-icon-audio-book')) return true;
                    }
                    const h1 = document.querySelector("h1[data-datadog-id='ucv-title-header']");
                    if (h1 && /[\(\[]audiobook[\)\]]/i.test(h1.textContent)) return true;
                    return false;
                    """
                    is_audio_dom = driver.actions.execute_js(audio_script)
                    if is_audio_dom is True:
                        return True
            except Exception:
                pass
        return False

    def handle(
        self,
        url: str,
        config: DownloaderConfig,
        context: ExecutionContext,
    ) -> bool:
        config.epub = False
        config.audiobook = True
        config.url = url

        structure = context.scraper.extract_course_structure(url, is_audiobook=True)
        if not structure:
            raise RuntimeError(f"Failed to extract audiobook structure for {url}.")

        raw_title = getattr(context.scraper, "course_title", "") or getattr(getattr(context.driver, "navigation", None), "title", "") or ""
        cleaned_title = re.sub(
            r'\s*[\(\[](video|book|audiobook|audio\s+book)[\)\]]\s*$', "", str(raw_title), flags=re.IGNORECASE
        ).strip()
        if not cleaned_title:
            cleaned_title = "OReilly Extracted Item"

        course = build_course(structure, title=cleaned_title)
        base_dir = os.path.join(context.downloader.output_dir, "audiobooks")
        course_dir = PathManager.get_course_dir(base_dir, course.title)
        os.makedirs(course_dir, exist_ok=True)

        with open(os.path.join(course_dir, "course_structure.json"), "w", encoding="utf-8") as f:
            json.dump(course.structure, f, indent=2)

        context.downloader.download_course(
            course,
            context.scraper,
            context.resolver,
            config,
            course_dir,
            is_audio_only=True,
        )
        return True


class StrategyDispatcher:
    """Dispatches download requests to the registered strategy (Open/Closed Principle)."""
    def __init__(self):
        self._strategies: Dict[str, ContentStrategy] = {
            "book": BookStrategy(),
            "course": CourseStrategy(),
            "audiobook": AudiobookStrategy(),
        }

    def register(self, content_type: str, strategy: ContentStrategy) -> None:
        """Registers a new content download strategy."""
        self._strategies[content_type.strip().lower()] = strategy

    def get_strategy(self, content_type: str) -> ContentStrategy:
        strategy = self._strategies.get(content_type.strip().lower())
        if not strategy:
            available = ", ".join(self._strategies.keys())
            raise ValueError(f"No strategy registered for content type '{content_type}'. Available: [{available}]")
        return strategy

    def dispatch(
        self,
        content_type: str,
        url: str,
        config: DownloaderConfig,
        context: ExecutionContext,
    ) -> bool:
        strategy = self.get_strategy(content_type)
        return strategy.handle(url, config, context)

    def detect_content_type(
        self,
        url: str,
        session: Optional[requests.Session] = None,
        driver: Optional[Any] = None,
    ) -> str:
        """Autodetects content type by querying registered strategies in priority order (OCP)."""
        # Prioritize audiobook -> book -> course
        for candidate in ["book", "audiobook", "course"]:
            strategy = self._strategies.get(candidate)
            if strategy and strategy.can_handle(url, session=session, driver=driver):
                return candidate

        # Check any other custom registered strategies
        for name, strategy in self._strategies.items():
            if name not in ["audiobook", "book", "course"] and strategy.can_handle(url, session=session, driver=driver):
                return name

        return "course"
