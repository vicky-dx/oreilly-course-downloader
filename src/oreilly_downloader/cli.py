import argparse
import os
import json
import time
import concurrent.futures
import re
from typing import Optional

from colorama import init, Fore
from tqdm import tqdm
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
from .core.auth import AuthService
from .core.course_scraper import CourseStructureScraper
from .core.media_resolver import MediaUrlResolver
from .core.downloader import DownloaderService

# Bind global print to our thread-safe and disk-logging Logger class
builtins.print = Logger.print
from .core.models import Course, Module, Lesson, Video
from .core.utils import PathManager, SanityUtils
from .core.vtt import VttProcessor
from .core.config import DownloaderConfig


class HeadlessAutoLoginFailed(Exception):
    """Raised when auto-login (session restore) fails in headless mode, triggering a headed retry."""
    pass



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
    """Handles the authentication flow either manually, via credentials, or via existing session."""
    if config.auto_signup:
        Logger.info("=======================================================")
        Logger.warning("🆕 AUTOMATIC SIGN UP ACTIVE")
        Logger.warning("=======================================================")

        from .core.gmail_trick import GmailTrickState, get_dot_variation
        import random
        import string

        state = GmailTrickState(config.output_dir)
        if config.base_email:
            state.set_base_email(config.base_email)

        # Smart Bypass: Check if a non-expired success entry already exists
        active_trial = state.get_active_valid_trial(config.base_email)
        if active_trial:
            Logger.success(f"Active trial account found: {active_trial.get('email')} (Valid until {active_trial.get('expires_at')})")
            if auth.is_logged_in():
                Logger.success("Existing session is already authenticated. Skipping auto-signup.")
                return True
            
            email_cached = active_trial.get("email")
            password_cached = active_trial.get("password")
            if email_cached and password_cached:
                Logger.info("Attempting to restore session using cached credentials...")
                if auth.login(email_cached, password_cached):
                    Logger.success("Successfully restored active session!")
                    return True
                elif config.headless:
                    raise HeadlessAutoLoginFailed()
            Logger.warning("Existing trial login failed. Proceeding with new trial creation...")

        base_email = state.get_base_email()
        if not base_email:
            Logger.error(" Error: Base email is required for auto-signup.")
            Logger.warning("👉 Solution: Run 'uv run oreilly-dl --auto-signup --base-email \"your_email@gmail.com\"'")
            return False

        index = state.get_unused_random_index()
        email_variant = get_dot_variation(base_email, index)

        first_names = ["John", "Jane", "Robert", "Emily", "Michael", "Sarah", "David", "Jessica", "James", "Karen", "Thomas", "Lisa", "Charles", "Sandra"]
        last_names = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson"]
        first_name = random.choice(first_names)
        last_name = random.choice(last_names)

        # Generate a strong 16-character password
        chars = string.ascii_letters + string.digits + "!@#$%^&*"
        password = "".join(random.choice(chars) for _ in range(16))

        Logger.info(f"📧 Base Email:    {base_email}")
        Logger.info(f"📧 Email Variant: {email_variant} (Index: {index})")
        Logger.info(f"👤 Name:          {first_name} {last_name}")
        Logger.info(f"🔑 Password:      {password}")
        Logger.warning("=======================================================\n")

        success = auth.register_account(email_variant, password, first_name, last_name)
        if success:
            state.add_history(email_variant, index, "success", password=password)
            Logger.success("Confirmed registered and logged in successfully. Profile saved!")
            Logger.success(f"📝 Registered account details:")
            Logger.success(f"   - Email: {email_variant}")
            Logger.success(f"   - Password: {password}")
            Logger.info("✨ You can now close the browser and run standard downloads without credentials.")
        else:
            state.add_history(email_variant, index, "failed", password=password)
            Logger.error("Registration failed or OTP was incorrect.")
        return False

    if config.manual_login:
        Logger.info("=======================================================")
        Logger.warning(" MANUAL LOGIN MODE ACTIVE")
        Logger.warning("=======================================================")

        driver.navigation.to("https://learning.oreilly.com/accounts/login/")
        Logger.info("⏳ Please log in via the newly opened browser window.")
        Logger.warning("⏳ ONCE YOU ARE SUCCESSFULLY ON THE HOMEPAGE:")
        input("👉 Press ENTER here in the terminal to continue...")

        if auth.is_logged_in():
            Logger.success(" Confirmed logged in manually. Profile saved!")
        else:
            Logger.error(" Warning: Could not detect logged-in state.")
        Logger.success("✨ Manual setup complete. Please close and run the script normally to download courses.")
        return False

    if config.email and config.password:
        if not auth.login(config.email, config.password):
            Logger.error("Authentication failed. (Possible CAPTCHA block or invalid credentials)")
            Logger.warning("👉 Solution: Run 'uv run oreilly-dl --manual-login --browser stealth' to log in yourself safely.")
            return False
        return True

    if not auth.is_logged_in():
        # Check if we have cached active trial credentials to automatically restore the session
        from .core.gmail_trick import GmailTrickState
        try:
            state = GmailTrickState(config.output_dir)
            active_trial = state.get_active_valid_trial()
            if active_trial:
                email_cached = active_trial.get("email")
                password_cached = active_trial.get("password")
                if email_cached and password_cached:
                    Logger.info("Detected valid active trial account in history. Attempting auto-login...")
                    if auth.login(email_cached, password_cached):
                        Logger.success("Successfully logged in using cached trial credentials!")
                        return True
                    elif config.headless:
                        raise HeadlessAutoLoginFailed()
        except HeadlessAutoLoginFailed:
            raise
        except Exception as e:
            Logger.debug(f"Failed during standard trial restore verification: {e}")

        Logger.error("Error: You are NOT logged in.")
        Logger.warning("👉 Solution: pass '--email' and '--password', OR use '--manual-login' / '--auto-signup'")
        return False

    return True


def _process_single_video(
    executor: concurrent.futures.ThreadPoolExecutor,
    video: Video,
    vid_idx: int,
    lesson_title: str,
    less_idx: int,
    module_title: str,
    mod_idx: int,
    course_dir: str,
    driver,
    scraper: CourseStructureScraper,
    resolver: MediaUrlResolver,
    downloader: DownloaderService,
    config: DownloaderConfig,
    is_audio_only: bool = False,
) -> Optional[tuple]:
    """Handles extraction and immediate download of a single video. Returns Tuple if active action taken."""
    vid_file, txt_file = PathManager.get_video_paths(
        course_dir, mod_idx, module_title, less_idx, lesson_title, vid_idx, video.title, is_audio_only
    )

    if is_audio_only:
        if os.path.exists(vid_file):
            Logger.warning(f" Skipping {video.title} (audio already exists)")
            return None
    else:
        if config.transcripts_only and os.path.exists(txt_file):
            Logger.warning(f" Skipping {video.title} (transcript already extracted)")
            return None
        elif not config.transcripts_only and os.path.exists(vid_file):
            # Video is downloaded. Check if the transcript is missing.
            if not os.path.exists(txt_file):
                Logger.warning(f" Video exists but transcript is missing for {video.title}. Extracting transcript...")
                video.transcript = scraper.extract_transcript(video.url, resolver)
                if video.transcript:
                    downloader.save_transcript(video.transcript, txt_file)
                    Logger.success(f" Transcript extracted.")
            else:
                Logger.warning(f" Skipping {video.title} (video and transcript already exist)")
            return None

    media_icon = "🎧" if is_audio_only else "🎥"
    media_type = "Audio" if is_audio_only else "Video"
    Logger.info(f"{media_icon} Extracting data for {media_type}: {video.title}")
    Logger.warning(f"📁 Saving to folder: {os.path.basename(os.path.dirname(vid_file))}")

    if config.transcripts_only:
        if is_audio_only:
            Logger.error(f" Transcripts-only mode is not applicable for audiobooks.")
            return ("error", video, "Transcripts not supported for audiobooks")
        video.transcript = scraper.extract_transcript(video.url, resolver)
        if video.transcript:
            downloader.save_transcript(video.transcript, txt_file)
            Logger.success(f" Transcript extracted.")
            return None
        else:
            Logger.error(f" No transcript available.")
            return ("error", video, "No transcript available")
    else:
        # Extracting the m3u8 url using our decoupled resolver (tries API first, then falls back to sniffer)
        m3u8 = resolver.resolve_m3u8_url(video.url, resolution=config.resolution)
        if m3u8:
            video.m3u8_url = m3u8
            if not is_audio_only:
                video.transcript = scraper.extract_transcript(video.url, resolver)
                if video.transcript:
                    downloader.save_transcript(video.transcript, txt_file)

            Logger.success(f" M3U8 Fetched. Queuing {video.title} for background download...")
            future = executor.submit(downloader.download_video, m3u8, vid_file)
            return (future, video, vid_file)
        else:
            Logger.error(f" No m3u8 found.")
            return ("error", video, "Could not resolve M3U8 stream URL")


def _download_videos_concurrently(
    course: Course,
    driver,
    scraper: CourseStructureScraper,
    resolver: MediaUrlResolver,
    downloader: DownloaderService,
    config: DownloaderConfig,
    course_dir: str,
    is_audio_only: bool = False,
):
    """Iterates through the course structure and dispatches video processing with a bounded queue to avoid M3U8 expiration."""

    max_workers = config.max_workers
    running_futures = set()
    future_to_video = {}
    failed_items = []

    def process_done_futures(done_set):
        for f in done_set:
            if f in future_to_video:
                video, vid_file = future_to_video.pop(f)
                try:
                    success = f.result()
                    if not success:
                        failed_items.append({
                            "title": video.title,
                            "url": video.url,
                            "path": vid_file,
                            "error": "ffmpeg download failed"
                        })
                except Exception as e:
                    failed_items.append({
                        "title": video.title,
                        "url": video.url,
                        "path": vid_file,
                        "error": f"Exception: {str(e)}"
                    })

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        for mod_idx, module in enumerate(course.modules, 1):
            for less_idx, lesson in enumerate(module.lessons, 1):
                for vid_idx, video in enumerate(lesson.videos, 1):

                    # Bounding the queue: Wait if we already have max_workers active downloads
                    while len(running_futures) >= max_workers:
                        done, running_futures = concurrent.futures.wait(
                            running_futures,
                            return_when=concurrent.futures.FIRST_COMPLETED,
                        )
                        process_done_futures(done)

                    res = _process_single_video(
                        executor=executor,
                        video=video,
                        vid_idx=vid_idx,
                        lesson_title=lesson.title,
                        less_idx=less_idx,
                        module_title=module.title,
                        mod_idx=mod_idx,
                        course_dir=course_dir,
                        driver=driver,
                        scraper=scraper,
                        resolver=resolver,
                        downloader=downloader,
                        config=config,
                        is_audio_only=is_audio_only,
                    )

                    if res:
                        if res[0] == "error":
                            _, video, err_msg = res
                            failed_items.append({
                                "title": video.title,
                                "url": video.url,
                                "error": err_msg
                            })
                        else:
                            future, video, vid_file = res
                            running_futures.add(future)
                            future_to_video[future] = (video, vid_file)

        if running_futures:
            done, _ = concurrent.futures.wait(running_futures)
            process_done_futures(done)

    # Dead Letter Queue (DLQ) Reporting and Exporting
    if failed_items:
        dlq_path = os.path.join(course_dir, "failed_downloads.json")
        try:
            with open(dlq_path, "w", encoding="utf-8") as f:
                json.dump(failed_items, f, indent=2)
            Logger.warning(f"{len(failed_items)} items failed to process/download.")
            Logger.warning(f"👉 Dead Letter Queue (DLQ) log exported to: {dlq_path}")
        except Exception as e:
            Logger.error(f"{len(failed_items)} items failed to process/download (Failed to write DLQ log: {e})")
    else:
        media_name = "audiobook chapters" if is_audio_only else "course videos"
        Logger.success(f"All {media_name} processed successfully!")


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
                    Logger.warning("=======================================================")
                    Logger.warning("  ACTIVE TRIAL ACCOUNT HAS EXPIRED!")
                    Logger.warning("=======================================================")
                    Logger.info(f"Active Account:  {last_success.get('email')}")
                    Logger.info(f"Expiration Date: {last_success.get('expires_at')}")
                    Logger.warning("👉 Run 'uv run oreilly-dl --auto-signup' to create a new trial.")
                    Logger.warning("=======================================================\n")
    except Exception as e:
        Logger.debug(f"Failed to check active trial status in process_course: {e}")

    if not config.url:
        Logger.error(" Error: Course URL is required.")
        return

    while True:
        Logger.info("🚀 Initializing browser...")
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
                    Logger.info("✨ Book downloaded and packaged successfully!")
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

            Logger.info("📚 Extracting course structure...")
            structure = scraper.extract_course_structure(config.url, config.audiobook)
            if not structure:
                Logger.error(" Failed to extract course structure.")
                return

            # Dynamically extract course title from driver title (removing common suffix like [Video], [Book], [Audiobook], or [Audio Book])
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

            _download_videos_concurrently(
                course, driver, scraper, resolver, downloader, config, course_dir, is_audio_only=is_audio_only
            )
            break

        except HeadlessAutoLoginFailed:
            if config.headless:
                Logger.warning("⚠️ Headless auto-login failed. Retrying in headed (non-headless) mode...")
                config.headless = False
                continue
            break

        finally:
            bm.stop()
            Logger.info(f"✨ Done! Cleaned up browser.")


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
            Logger.info(f"✨ Success! Saved standalone transcript to: {out_path}")


def _validate_arguments(args, parser):
    if args.auto_signup:
        if not args.base_email:
            parser.error("--base-email is strictly required when using --auto-signup")
        
        domain = args.base_email.split("@")[-1].lower() if "@" in args.base_email else ""
        if "gmail.com" not in domain and "googlemail.com" not in domain:
            parser.error("--base-email must be a Gmail address (e.g. 'username@gmail.com') as auto-signup works for Gmail only")

    if not args.manual_login and not args.auto_signup and not args.url:
        parser.error(
            "The course URL is required unless using --manual-login, --auto-signup or --on24-vtt"
        )


def main():
    if sys.platform.startswith('win'):
        try:
            sys.stdout.reconfigure(encoding='utf-8')
            sys.stderr.reconfigure(encoding='utf-8')
        except Exception:
            pass
    import socket
    socket.setdefaulttimeout(30)
    parser = argparse.ArgumentParser(description="O'Reilly Course (Video/Audio) Downloader")
    parser.add_argument("--email", help="Login email")
    parser.add_argument("--password", help="Login password")
    parser.add_argument(
        "--manual-login",
        action="store_true",
        help="Authenticate manually in a visible browser profile",
    )
    parser.add_argument(
        "--auto-signup",
        action="store_true",
        help="Automated trial registration using Google dot trick (works for Gmail only)",
    )
    parser.add_argument(
        "--base-email",
        help="Base Gmail address to use for the Google dot trick",
    )
    parser.add_argument(
        "--no-headless",
        action="store_true",
        help="Run scraper browser in non-headless mode",
    )
    parser.add_argument(
        "--browser",
        choices=["firefox", "chrome", "stealth"],
        default="stealth",
        help="Browser type to use for scraping (default: stealth)",
    )
    parser.add_argument(
        "--epub",
        action="store_true",
        help="Download O'Reilly books as EPUB files.",
    )
    parser.add_argument(
        "--web-viewer",
        action="store_true",
        help="Generate an interactive, responsive local web reader application for offline viewing.",
    )
    parser.add_argument(
        "--audiobook",
        action="store_true",
        help="Download O'Reilly audiobooks (saves files as .m4a and handles audiobook page layout).",
    )
    parser.add_argument(
        "--transcripts-only",
        action="store_true",
        help="Only download text transcripts. Skip media m3u8 downloading.",
    )
    parser.add_argument(
        "--output-dir",
        default="downloads",
        help="Directory to save downloaded files (default: downloads)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=3,
        help="Max parallel media downloads (default: 3)",
    )
    parser.add_argument(
        "--resolution",
        "-r",
        choices=["best", "1080p", "720p", "480p", "360p"],
        default="best",
        help="Video download resolution quality selection (default: best)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable file logging to downloader.log",
    )
    parser.add_argument(
        "--on24-vtt",
        help="Direct URL to an ON24 VTT subtitle file to extract a live-event transcript.",
    )
    parser.add_argument(
        "--event-name",
        default="ON24_Live_Event",
        help="Name of the event to save the transcript under (default: ON24_Live_Event).",
    )
    parser.add_argument("url", nargs="?", help="URL of the course or audiobook")

    args = parser.parse_args()

    _init_logging(args.debug)

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

    process_course(config)


if __name__ == "__main__":
    main()
