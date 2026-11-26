import os
import requests
from typing import Optional, Callable, Any
from colorama import Fore

from .browsers import BrowserFactory, IBrowser, Logger
from .auth import AuthService, authenticate_session, HeadlessAutoLoginFailed
from .config import DownloaderConfig
from .course_scraper import CourseStructureScraper
from .media_resolver import MediaUrlResolver
from .downloader import DownloaderService
from .epub import BookDownloaderService
from .utils import SanityUtils, sync_browser_cookies, ensure_headless_if_no_display
from .strategies import ExecutionContext, StrategyDispatcher


class CourseOrchestrator:
    """Manages end-to-end execution lifecycle, browser recovery, and strategy dispatch (SRP)."""

    def __init__(
        self,
        config: DownloaderConfig,
        browser_factory_create: Optional[Callable[..., IBrowser]] = None,
        auth_service_cls: Optional[Callable[..., AuthService]] = None,
        auth_handler: Optional[Callable[..., bool]] = None,
    ):
        self.config = config
        self._browser_factory_create = browser_factory_create or BrowserFactory.create
        self._auth_service_cls = auth_service_cls or AuthService
        self._auth_handler = auth_handler or (lambda driver, auth, cfg: authenticate_session(auth, cfg))

    def execute(self) -> bool:
        """Executes browser initialization, authentication, and content dispatch with headless recovery."""
        clean_session = self.config.auto_signup

        # Check active trial status
        try:
            from .gmail_trick import GmailTrickState

            state = GmailTrickState(self.config.output_dir)
            if self.config.auto_signup:
                active_trial = state.get_active_valid_trial(self.config.base_email)
                if active_trial:
                    Logger.success(
                        f"Active trial account found: {active_trial.get('email')} "
                        f"(Valid until {active_trial.get('expires_at')})"
                    )
                    if not self.config.url:
                        Logger.success("Trial account is still valid. Skipping browser initialization.")
                        return True
                    clean_session = False
            elif not self.config.manual_login:
                history = state.state.get("history", [])
                success_entries = [h for h in history if h.get("status") == "success"]
                if success_entries:
                    last_success = success_entries[-1]
                    active_trial = state.get_active_valid_trial()
                    if not active_trial:
                        Logger.panel(
                            "⚠️ ACTIVE TRIAL ACCOUNT HAS EXPIRED!",
                            [
                                f"Active Account:  {last_success.get('email')}",
                                f"Expiration Date: {last_success.get('expires_at')}",
                                "",
                                "👉 Run 'uv run oreilly-dl --auto-signup' to create a new trial.",
                            ],
                            border_color=Fore.YELLOW,
                        )
        except Exception as e:
            Logger.debug(f"Failed to check active trial status in CourseOrchestrator: {e}")

        if not self.config.url and not self.config.manual_login and not self.config.auto_signup:
            Logger.error(" Error: Course URL is required.")
            return False

        if not ensure_headless_if_no_display(self.config):
            return False

        while True:
            Logger.info("Initializing browser...")
            try:
                factory_kwargs = {
                    "browser_type": self.config.browser_type,
                    "headless": self.config.headless,
                    "clean_session": clean_session,
                }
                if self.config.browser_binary is not None:
                    factory_kwargs["browser_binary"] = self.config.browser_binary

                bm: IBrowser = self._browser_factory_create(**factory_kwargs)
                driver = bm.start()
            except (RuntimeError, FileNotFoundError) as be:
                Logger.error(f"Browser initialization failed: {be}")
                return False
            except Exception as e:
                Logger.error(f"Unexpected error starting browser: {e}")
                return False

            if not driver:
                Logger.error(" Failed to start browser")
                return False

            try:
                auth = self._auth_service_cls(driver)

                if not self._auth_handler(driver, auth, self.config):
                    return False

                if not self.config.url:
                    Logger.success("Session profile authenticated and saved successfully!")
                    return True

                # Setup session cookies from browser driver
                session = requests.Session()
                session.headers.update({
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"
                    )
                })
                sync_browser_cookies(driver, session)

                ks = None
                if not self.config.manual_login and not self.config.epub:
                    Logger.info("Extracting active Kaltura Session (ks) token...")
                    ks = auth.get_ks()
                    if ks:
                        Logger.success(f"Session acquired: {ks[:20]}...")
                    else:
                        Logger.warning("Failed to acquire Kaltura session (ks). Will rely on sniffer fallback.")

                # Pre-flight check for FFmpeg dependency if downloads are required
                ffmpeg_path = SanityUtils.get_ffmpeg_path() or "ffmpeg"
                if not self.config.epub and not self.config.transcripts_only and not SanityUtils.get_ffmpeg_path():
                    Logger.error("Critical dependency missing: FFmpeg could not be found.")
                    Logger.warning(
                        "Please install FFmpeg and add it to your system PATH, or place ffmpeg.exe in the project directory."
                    )
                    Logger.info("👉 Download URL: https://www.ffmpeg.org/download.html")
                    return False

                book_dl = BookDownloaderService(output_dir=self.config.output_dir)
                scraper = CourseStructureScraper(driver)
                resolver = MediaUrlResolver(driver, ks=ks)
                downloader = DownloaderService(output_dir=self.config.output_dir, ffmpeg_path=ffmpeg_path)

                context = ExecutionContext(
                    driver=driver,
                    session=session,
                    scraper=scraper,
                    resolver=resolver,
                    downloader=downloader,
                    book_dl=book_dl,
                    ks=ks,
                )
                # Pre-navigate driver to target URL so that DOM headers and metadata are loaded for autodetection
                try:
                    current_url = getattr(getattr(driver, "navigation", None), "url", "") or ""
                    if isinstance(current_url, str) and current_url.startswith(("http://", "https://")):
                        if current_url.rstrip("/") != self.config.url.rstrip("/"):
                            Logger.info(f"Navigating to {self.config.url}...")
                            driver.navigation.to(self.config.url)
                            import time
                            time.sleep(2)
                except Exception as nav_e:
                    Logger.debug(f"Pre-navigation in CourseOrchestrator failed: {nav_e}")

                dispatcher = StrategyDispatcher()
                if self.config.epub:
                    content_type = "book"
                elif self.config.audiobook:
                    content_type = "audiobook"
                else:
                    content_type = dispatcher.detect_content_type(self.config.url, session=session, driver=driver)
                    Logger.info(f"🔎 Auto-detected format: [{content_type.upper()}]")

                dispatcher.dispatch(content_type, self.config.url, self.config, context)
                return True

            except HeadlessAutoLoginFailed:
                if self.config.headless and SanityUtils.has_display():
                    Logger.warning("Headless auto-login failed. Retrying in headed (non-headless) mode...")
                    self.config.headless = False
                    continue
                if not SanityUtils.has_display():
                    Logger.error("Headless authentication failed and no graphical display ($DISPLAY / $WAYLAND_DISPLAY) is available for visible fallback.")
                return False

            finally:
                bm.stop()
                Logger.info("Done! Cleaned up browser.")
