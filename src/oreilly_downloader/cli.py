import argparse
import os
import json
import re
from typing import Optional
from colorama import init, Fore
import builtins
import sys
import traceback

def _handle_unhandled_exception(exctype, value, tb):
    tb_lines = traceback.format_exception(exctype, value, tb)
    tb_text = "".join(tb_lines)
    Logger.error(f"\n💥 Critical error occurred:\n{tb_text}")
    sys.exit(1)

init(autoreset=True)

from .core.browsers import BrowserFactory, IBrowser, Logger
from .core.auth import AuthService, authenticate_session, HeadlessAutoLoginFailed
from .core.course_scraper import CourseStructureScraper
from .core.media_resolver import MediaUrlResolver
from .core.downloader import DownloaderService

# Bind global print to our thread-safe and disk-logging Logger class
builtins.print = Logger.print
from .core.models import Course, Module, Lesson, Video, build_course
from .core.utils import PathManager, SanityUtils, sync_browser_cookies
from .core.strategies import ExecutionContext, StrategyDispatcher
from .core.epub import BookDownloaderService
from .core.config import DownloaderConfig
from .core.orchestrator import CourseOrchestrator


def _handle_authentication(
    driver,
    auth: AuthService,
    config: DownloaderConfig,
) -> bool:
    """Delegates authentication orchestration to AuthService helper (preserves test mocking compatibility)."""
    return authenticate_session(auth, config)


def process_course(config: DownloaderConfig):
    """Executes course downloading using CourseOrchestrator (SRP)."""
    orchestrator = CourseOrchestrator(
        config=config,
        browser_factory_create=BrowserFactory.create,
        auth_service_cls=AuthService,
        auth_handler=_handle_authentication,
    )
    return orchestrator.execute()


def _init_logging(debug: bool):
    if debug:
        try:
            Logger.enable_debug_logging("downloader.log")
            sys.excepthook = _handle_unhandled_exception
            Logger.info("Logging active. Detailed logs and errors will be saved to 'downloader.log'.")
        except Exception as e:
            Logger.warning(f"Could not initialize log file: {e}")


def _handle_on24_vtt(on24_vtt: str, event_name: str, output_dir: str):
    Logger.info(f"[ON24 Transcript Mode] Processing Event: {event_name}")
    vtt_content = VttProcessor.download_vtt(on24_vtt)
    if vtt_content:
        captions = VttProcessor.parse_vtt(vtt_content)
        if captions:
            transcript = VttProcessor.format_transcript(captions, event_name)
            dl_svc = DownloaderService(output_dir=output_dir)
            out_path = os.path.join(
                dl_svc.output_dir, event_name, "full_transcript.txt"
            )
            dl_svc.save_transcript(transcript, out_path)
            Logger.info(f"Success! Saved standalone transcript to: {out_path}")


def _validate_arguments(args, parser):
    # 1. Credentials pair check
    if (args.email and not args.password) or (args.password and not args.email):
        parser.error("Both --email and --password must be provided together for credential login")

    # 2. Auto-signup requirements check
    if args.auto_signup:
        if not args.base_email:
            parser.error("--base-email is strictly required when using --auto-signup")
        
        domain = args.base_email.split("@")[-1].lower() if "@" in args.base_email else ""
        if "gmail.com" not in domain and "googlemail.com" not in domain:
            parser.error("--base-email must be a Gmail address (e.g. 'username@gmail.com') as auto-signup works for Gmail only")

    # 3. Main URL or Batch file presence check
    if args.url and not getattr(args, "batch", None):
        from .core.batch import resolve_batch_file_path
        resolved = resolve_batch_file_path(args.url)
        if os.path.isfile(resolved) or args.url.endswith((".txt", ".urls", ".list")):
            args.batch = resolved if os.path.isfile(resolved) else args.url
            args.url = None

    if not args.manual_login and not args.auto_signup and not args.on24_vtt and not args.url and not getattr(args, "batch", None):
        parser.error(
            "The course URL or --batch file is required unless using --manual-login, --auto-signup or --on24-vtt"
        )

class CustomArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        Logger.print(f"\n{Fore.RED}❌  Error: {message}")
        
        tip = None
        lower_msg = message.lower()
        if "both --email and --password" in lower_msg:
            tip = (
                "👉 To login with your credentials, pass both options:\n"
                f"   {Fore.CYAN}uv run oreilly-dl <url> --email your@email.com --password yourpassword"
            )
        elif "base-email is strictly required" in lower_msg:
            tip = (
                "👉 To register a new account automatically, pass both options:\n"
                f"   {Fore.CYAN}uv run oreilly-dl <url> --auto-signup --base-email yourname@gmail.com"
            )
        elif "must be a gmail address" in lower_msg:
            tip = (
                "👉 The Gmail dot trick requires a Gmail inbox. Provide a Gmail address:\n"
                f"   {Fore.CYAN}uv run oreilly-dl <url> --auto-signup --base-email username@gmail.com"
            )
        elif "course url is required" in lower_msg:
            tip = (
                "👉 To download a course or audiobook, provide the URL as the first argument:\n"
                f"   {Fore.CYAN}uv run oreilly-dl https://learning.oreilly.com/videos/title/...\n\n"
                f"{Fore.RESET}👉 Or, to set up session credentials standalone without a URL:\n"
                f"   {Fore.CYAN}uv run oreilly-dl --manual-login\n"
                f"   {Fore.CYAN}uv run oreilly-dl --auto-signup --base-email username@gmail.com"
            )
        elif "unrecognized arguments" in lower_msg:
            tip = (
                "👉 You passed an unknown option. Refer to the help manual:\n"
                f"   {Fore.CYAN}uv run oreilly-dl --help"
            )
        elif "invalid int value" in lower_msg or "invalid choice" in lower_msg:
            tip = (
                "👉 Check the value you passed for that option. Run help for type details:\n"
                f"   {Fore.CYAN}uv run oreilly-dl --help"
            )

        if tip:
            Logger.print(f"\n{Fore.YELLOW}{tip}\n")
            
        sys.exit(2)


def main():
    if sys.platform.startswith('win'):
        try:
            sys.stdout.reconfigure(encoding='utf-8')
            sys.stderr.reconfigure(encoding='utf-8')
        except Exception:
            pass
    import socket
    socket.setdefaulttimeout(30)
    
    parser = CustomArgumentParser(
        description="O'Reilly Course (Video/Audio) Downloader",
        usage="oreilly-dl [url] [options]",
        formatter_class=argparse.RawTextHelpFormatter
    )

    # 1. Target URL (Required/Optional depending on mode)
    parser.add_argument(
        "url", 
        nargs="?", 
        help="URL of the course, audiobook, or book to download.\n[REQUIRED unless --manual-login, --auto-signup, or --on24-vtt is specified]"
    )

    # 2. Authentication Settings
    auth_group = parser.add_argument_group("Authentication Settings")
    auth_group.add_argument(
        "--email", 
        help="O'Reilly login email address.\n[REQUIRED for credential login (must be paired with --password)]"
    )
    auth_group.add_argument(
        "--password", 
        help="O'Reilly login password.\n[REQUIRED for credential login (must be paired with --email)]"
    )
    auth_group.add_argument(
        "--manual-login",
        action="store_true",
        help="Log in manually using a visible browser profile.\n[Optional, saves session for subsequent runs]",
    )
    auth_group.add_argument(
        "--auto-signup",
        action="store_true",
        help="Register a new trial account automatically using Gmail dot trick.\n[Optional, requires --base-email]",
    )
    auth_group.add_argument(
        "--base-email",
        help="Base Gmail address used to generate variations (e.g. 'yourname@gmail.com').\n[REQUIRED when --auto-signup is active]",
    )

    # 3. Content Options
    content_group = parser.add_argument_group("Content & Media Format Options")
    content_group.add_argument(
        "--epub",
        action="store_true",
        help="Download O'Reilly books as EPUB files.\n[Optional]",
    )
    content_group.add_argument(
        "--audiobook",
        action="store_true",
        help="Download audiobooks / audio courses (saves as .m4a).\n[Optional]",
    )
    content_group.add_argument(
        "--transcripts-only",
        action="store_true",
        help="Extract video/audio text transcripts only, bypassing media downloads.\n[Optional]",
    )
    content_group.add_argument(
        "--web-viewer",
        action="store_true",
        help="Generate an interactive, responsive local web reader application for offline viewing.\n[Optional]",
    )

    # 4. Download Settings
    dl_group = parser.add_argument_group("Download & Performance Options")
    dl_group.add_argument(
        "--workers",
        type=int,
        default=DownloaderConfig.max_workers,
        help=f"Max parallel segment/media downloads (default: {DownloaderConfig.max_workers}).\n[Optional]",
    )
    dl_group.add_argument(
        "--resolution",
        "-r",
        choices=["best", "1080p", "720p", "480p", "360p"],
        default=DownloaderConfig.resolution,
        help=f"Target video stream resolution (default: {DownloaderConfig.resolution}).\n[Optional]",
    )
    dl_group.add_argument(
        "--output-dir",
        "-o",
        default=os.environ.get("OREILLY_OUTPUT_DIR", DownloaderConfig.output_dir),
        help=f"Root directory where downloads are saved (default: '{DownloaderConfig.output_dir}' or $OREILLY_OUTPUT_DIR).\n[Optional]",
    )
    dl_group.add_argument(
        "--batch",
        "-f",
        help="Path to a text file containing multiple URLs to download in a single browser session.\n[Optional]",
    )
    dl_group.add_argument(
        "--cooling-period",
        "--delay",
        type=int,
        default=DownloaderConfig.cooling_period,
        help=f"Cooling period in seconds between batch downloads (default: {DownloaderConfig.cooling_period}s).\n[Optional]",
    )

    # 5. Browser & Run Options
    run_group = parser.add_argument_group("Browser & Execution Settings")
    run_group.add_argument(
        "--headless",
        action="store_true",
        help="Run browser in headless (hidden/background) mode.\n[Optional, default is visible/non-headless]",
    )
    run_group.add_argument(
        "--no-headless",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    run_group.add_argument(
        "--browser",
        choices=["firefox", "chrome", "stealth"],
        default=DownloaderConfig.browser_type,
        help=f"Underlying browser automation profile (default: {DownloaderConfig.browser_type}).\n[Optional]",
    )
    run_group.add_argument(
        "--browser-binary",
        "-b",
        default=os.environ.get("OREILLY_BROWSER_BINARY"),
        help="Custom executable path for Chrome/Chromium/Firefox (default: $OREILLY_BROWSER_BINARY).\n[Optional]",
    )
    run_group.add_argument(
        "--debug",
        action="store_true",
        help="Enable full file logging to downloader.log.\n[Optional]",
    )

    # 6. ON24 Subtitle Mode
    vtt_group = parser.add_argument_group("ON24 Live Event Subtitle Options")
    vtt_group.add_argument(
        "--on24-vtt",
        help="Direct URL to an ON24 VTT subtitle file to extract a live-event transcript.\n[Optional]",
    )
    vtt_group.add_argument(
        "--event-name",
        default="ON24_Live_Event",
        help="Output folder/file name for the extracted ON24 event transcript.\n[Optional, defaults to 'ON24_Live_Event']",
    )

    args = parser.parse_args()

    _init_logging(args.debug)

    # Draw beautiful product banner
    Logger.banner()

    if args.on24_vtt:
        _handle_on24_vtt(args.on24_vtt, args.event_name, args.output_dir)
        return

    _validate_arguments(args, parser)

    active_headless = False
    if getattr(args, "headless", False) and not (args.manual_login or args.auto_signup):
        active_headless = True

    is_epub = args.epub
    is_audiobook = args.audiobook
    if args.url and not is_epub and not is_audiobook:
        lower_url = args.url.lower()
        if "/books/" in lower_url:
            is_epub = True
        elif "/audiobooks/" in lower_url:
            is_audiobook = True

    config = DownloaderConfig(
        url=args.url,
        email=args.email,
        password=args.password,
        browser_type=args.browser,
        headless=active_headless,
        transcripts_only=args.transcripts_only,
        manual_login=args.manual_login,
        output_dir=args.output_dir,
        max_workers=args.workers,
        audiobook=is_audiobook,
        epub=is_epub,
        web_viewer=args.web_viewer,
        auto_signup=args.auto_signup,
        base_email=args.base_email,
        resolution=args.resolution,
        browser_binary=args.browser_binary,
        batch_file=getattr(args, "batch", None),
        cooling_period=getattr(args, "cooling_period", DownloaderConfig.cooling_period),
        debug=args.debug,
    )

    if config.batch_file:
        from .core.batch import BatchProcessor
        try:
            processor = BatchProcessor(config)
            processor.run()
        except FileNotFoundError as fnf:
            Logger.error(f"{fnf}")
            Logger.info(f"👉 Current directory: {os.getcwd()}")
            Logger.info("👉 Please verify the file path and make sure the file exists.")
            sys.exit(1)
        except ValueError as ve:
            Logger.error(f"{ve}")
            Logger.info("👉 Ensure the batch file contains valid O'Reilly URLs (lines starting with # or // are ignored).")
            sys.exit(1)
        except Exception as e:
            Logger.error(f"Batch processing error: {e}")
            if config.debug:
                traceback.print_exc()
            sys.exit(1)
        return

    if config.url:
        Logger.config_summary(config)
    try:
        success = process_course(config)
        if not success:
            sys.exit(1)
    except Exception as e:
        Logger.error(f"Download execution failed: {e}")
        if config.debug:
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
