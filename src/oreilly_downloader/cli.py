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
from .core.models import Course, Module, Lesson, Video
from .core.utils import PathManager, SanityUtils
from .core.vtt import VttProcessor
from .core.config import DownloaderConfig


def build_course(structure: dict, title: str = "OReilly Extracted Course") -> Course:
    """Builds a Course object from the scraped structure dict."""
    course = Course(title=title, modules=[], structure=structure)
    for mod_name, lessons_dict in structure.items():
        module = Module(title=mod_name, lessons=[])
        for lesson_name, videos_list in lessons_dict.items():
            lesson = Lesson(title=lesson_name, videos=[])
            for v_data in videos_list:
                video = Video(title=v_data["title"], url=v_data["url"])
                lesson.videos.append(video)
            module.lessons.append(lesson)
        course.modules.append(module)
    return course


def _handle_authentication(
    driver,
    auth: AuthService,
    config: DownloaderConfig,
) -> bool:
    """Delegates authentication orchestration to AuthService helper (preserves test mocking compatibility)."""
    return authenticate_session(auth, config)


def process_course(config: DownloaderConfig):
    clean_session = config.auto_signup

    # Check active trial status
    try:
        from .core.gmail_trick import GmailTrickState
        
        state = GmailTrickState(config.output_dir)
        if config.auto_signup:
            active_trial = state.get_active_valid_trial(config.base_email)
            if active_trial:
                Logger.success(f"Active trial account found: {active_trial.get('email')} (Valid until {active_trial.get('expires_at')})")
                if not config.url:
                    Logger.success("Trial account is still valid. Skipping browser initialization.")
                    return
                # Reuse existing logged-in session profile instead of cleaning it
                clean_session = False
        elif not config.manual_login:
            history = state.state.get("history", [])
            success_entries = [h for h in history if h.get("status") == "success"]
            if success_entries:
                last_success = success_entries[-1]
                active_trial = state.get_active_valid_trial()
                if not active_trial:
                    Logger.panel("⚠️ ACTIVE TRIAL ACCOUNT HAS EXPIRED!", [
                        f"Active Account:  {last_success.get('email')}",
                        f"Expiration Date: {last_success.get('expires_at')}",
                        "",
                        "👉 Run 'uv run oreilly-dl --auto-signup' to create a new trial."
                    ], border_color=Fore.YELLOW)
    except Exception as e:
        Logger.debug(f"Failed to check active trial status in process_course: {e}")

    if not config.url and not config.manual_login and not config.auto_signup:
        Logger.error(" Error: Course URL is required.")
        return

    while True:
        Logger.info("Initializing browser...")
        bm: IBrowser = BrowserFactory.create(
            browser_type=config.browser_type,
            headless=config.headless,
            clean_session=clean_session
        )
        driver = bm.start()

        if not driver:
            Logger.error(" Failed to start browser")
            return

        try:
            auth = AuthService(bm)

            if not _handle_authentication(driver, auth, config):
                return

            if not config.url:
                Logger.success("Session profile authenticated and saved successfully!")
                return

            if config.epub:
                import requests
                from .core.epub import BookDownloaderService
                
                # Setup session cookies from browser driver
                session = requests.Session()
                session.headers.update({
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"
                })
                try:
                    for cookie in driver.cookies.get_all():
                        session.cookies.set(cookie['name'], cookie['value'])
                except Exception as ce:
                    Logger.warning(f"   Failed to copy cookies from browser: {ce}")

                book_dl = BookDownloaderService(output_dir=config.output_dir)
                success = book_dl.download_book(config, session)
                if success:
                    Logger.info("Book downloaded and packaged successfully!")
                else:
                    Logger.error("Failed to download or package the book.")
                return

            # Retrieve Kaltura session token (ks) if we are in normal download mode
            ks = None
            if not config.manual_login:
                Logger.info("🔑 Extracting active Kaltura Session (ks) token...")
                ks = auth.get_ks()
                if ks:
                    Logger.success(f" Session acquired: {ks[:20]}...")
                else:
                    Logger.warning(" Failed to acquire Kaltura session (ks). Will rely on sniffer fallback.")

            # Pre-flight check for FFmpeg dependency if downloads are required
            ffmpeg_path = "ffmpeg"
            if not config.transcripts_only:
                detected_path = SanityUtils.get_ffmpeg_path()
                if not detected_path:
                    Logger.error("Critical dependency missing: FFmpeg could not be found.")
                    Logger.warning("Please install FFmpeg and add it to your system PATH, or place ffmpeg.exe in the project directory.")
                    Logger.info("👉 Download URL: https://www.ffmpeg.org/download.html")
                    return
                ffmpeg_path = detected_path

            scraper = CourseStructureScraper(bm)
            resolver = MediaUrlResolver(bm, ks=ks)
            downloader = DownloaderService(output_dir=config.output_dir, ffmpeg_path=ffmpeg_path)

            Logger.info("Extracting course structure...")
            structure = scraper.extract_course_structure(config.url, config.audiobook)
            if not structure:
                Logger.error(" Failed to extract course structure.")
                return

            # Dynamically extract course title from driver title
            course_title = "OReilly Extracted Course"
            try:
                raw_title = driver.navigation.title
                if raw_title:
                    course_title = re.sub(r'\s*\[video\]\s*$', "", raw_title, flags=re.IGNORECASE)
                    course_title = re.sub(r'\s*\[book\]\s*$', "", course_title, flags=re.IGNORECASE)
                    course_title = re.sub(r'\s*\[(audiobook|audio\s+book)\]\s*$', "", course_title, flags=re.IGNORECASE)
                    course_title = course_title.strip()
            except Exception as e:
                Logger.debug(f"Failed to extract course title from page title: {e}")

            is_audio_only = config.audiobook

            course = build_course(structure, title=course_title)
            Logger.success(f" Found {len(course.modules)} modules")
            if is_audio_only:
                Logger.info("🎧 Audiobook/Audio-only course detected! Saving files with .m4a extension...")
                base_dir = os.path.join(downloader.output_dir, "audiobooks")
            else:
                base_dir = os.path.join(downloader.output_dir, "courses")

            course_dir = PathManager.get_course_dir(base_dir, course.title)
            os.makedirs(course_dir, exist_ok=True)

            with open(
                os.path.join(course_dir, "course_structure.json"), "w", encoding="utf-8"
            ) as f:
                json.dump(course.structure, f, indent=2)

            downloader.download_course(
                course, scraper, resolver, config, course_dir, is_audio_only=is_audio_only
            )
            break

        except HeadlessAutoLoginFailed:
            if config.headless:
                Logger.warning("Headless auto-login failed. Retrying in headed (non-headless) mode...")
                config.headless = False
                continue
            break

        finally:
            bm.stop()
            Logger.info(f"Done! Cleaned up browser.")


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

    # 3. Main URL presence check
    if not args.manual_login and not args.auto_signup and not args.on24_vtt and not args.url:
        parser.error(
            "The course URL is required unless using --manual-login, --auto-signup or --on24-vtt"
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
        default=3,
        help="Max parallel segment/media downloads (default: 3).\n[Optional]",
    )
    dl_group.add_argument(
        "--resolution",
        "-r",
        choices=["best", "1080p", "720p", "480p", "360p"],
        default="best",
        help="Target video stream resolution (default: best).\n[Optional]",
    )
    dl_group.add_argument(
        "--output-dir",
        default="downloads",
        help="Root directory where downloads are saved (default: downloads).\n[Optional]",
    )

    # 5. Browser & Run Options
    run_group = parser.add_argument_group("Browser & Execution Settings")
    run_group.add_argument(
        "--no-headless",
        action="store_true",
        help="Run browser in non-headless (visible) mode for debugging.\n[Optional]",
    )
    run_group.add_argument(
        "--browser",
        choices=["firefox", "chrome", "stealth"],
        default="stealth",
        help="Underlying browser automation profile (default: stealth).\n[Optional]",
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

    active_headless = False if (args.manual_login or args.auto_signup) else not args.no_headless

    is_epub = args.epub
    if args.url and "/library/view/" in args.url and not args.audiobook:
        is_epub = True

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
        audiobook=args.audiobook,
        epub=is_epub,
        web_viewer=args.web_viewer,
        auto_signup=args.auto_signup,
        base_email=args.base_email,
        resolution=args.resolution,
    )

    if config.url:
        Logger.config_summary(config)
    process_course(config)


if __name__ == "__main__":
    main()
