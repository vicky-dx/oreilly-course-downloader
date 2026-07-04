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

import sys
import traceback

_original_print = builtins.print
_log_file = None
_ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

def _strip_ansi(text: str) -> str:
    return _ansi_escape.sub('', text)

def _tqdm_print(*args, sep=" ", end="\n", file=None, flush=False):
    text = sep.join(str(a) for a in args)
    tqdm.write(text, file=file or sys.stdout, end=end)
    
    global _log_file
    if _log_file:
        try:
            clean_text = _strip_ansi(text)
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            _log_file.write(f"[{timestamp}] {clean_text}{end}")
            _log_file.flush()
        except:
            pass

builtins.print = _tqdm_print

def _handle_unhandled_exception(exctype, value, tb):
    tb_lines = traceback.format_exception(exctype, value, tb)
    tb_text = "".join(tb_lines)
    print(Fore.RED + f"\n💥 Critical error occurred:\n{tb_text}")
    
    global _log_file
    if _log_file:
        try:
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            _log_file.write(f"\n[{timestamp}] !!! CRITICAL UNHANDLED EXCEPTION !!!\n{tb_text}\n")
            _log_file.flush()
        except:
            pass
    sys.exit(1)

init(autoreset=True)

from .core.browsers import BrowserFactory, IBrowser
from .core.auth import AuthService
from .core.extractor import CourseStructureScraper, MediaUrlResolver
from .core.downloader import DownloaderService
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
    email: Optional[str],
    password: Optional[str],
    manual_login: bool,
) -> bool:
    """Handles the authentication flow either manually, via credentials, or via existing session."""
    if manual_login:
        print(Fore.YELLOW + "\n=======================================================")
        print(Fore.YELLOW + "⚠️ MANUAL LOGIN MODE ACTIVE")
        print(Fore.YELLOW + "=======================================================")

        driver.get("https://learning.oreilly.com/accounts/login/")
        print(Fore.CYAN + "\n⏳ Please log in via the newly opened browser window.")
        input(
            Fore.MAGENTA
            + "⏳ ONCE YOU ARE SUCCESSFULLY ON THE HOMEPAGE, press ENTER here to continue..."
        )

        if auth.is_logged_in():
            print(Fore.GREEN + "✅ Confirmed logged in manually. Profile saved!")
        else:
            print(Fore.RED + "⚠️ Warning: Could not detect logged-in state.")
        print(
            Fore.GREEN
            + "✨ Manual setup complete. Please close and run the script normally to download courses."
        )
        return False

    if email and password:
        if not auth.login(email, password):
            print(
                Fore.RED
                + "\n❌ Authentication failed. (Possible CAPTCHA block or invalid credentials)"
            )
            print(
                Fore.YELLOW
                + "👉 Solution: Run 'uv run oreilly-dl --manual-login --browser stealth' to log in yourself safely."
            )
            return False
        return True

    if not auth.is_logged_in():
        print(Fore.RED + "\n❌ Error: You are NOT logged in.")
        print(
            Fore.YELLOW
            + "👉 Solution: pass '--email' and '--password', OR use '--manual-login'"
        )
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
            print(Fore.YELLOW + f"⏩ Skipping {video.title} (audio already exists)")
            return None
    else:
        if config.transcripts_only and os.path.exists(txt_file):
            print(Fore.YELLOW + f"⏩ Skipping {video.title} (transcript already extracted)")
            return None
        elif not config.transcripts_only and os.path.exists(vid_file):
            # Video is downloaded. Check if the transcript is missing.
            if not os.path.exists(txt_file):
                print(Fore.YELLOW + f"⏩ Video exists but transcript is missing for {video.title}. Extracting transcript...")
                video.transcript = scraper.extract_transcript(video.url, resolver)
                if video.transcript:
                    downloader.save_transcript(video.transcript, txt_file)
                    print(Fore.GREEN + f"✅ Transcript extracted.")
            else:
                print(Fore.YELLOW + f"⏩ Skipping {video.title} (video and transcript already exist)")
            return None

    media_icon = "🎧" if is_audio_only else "🎥"
    media_type = "Audio" if is_audio_only else "Video"
    print(f"\n{Fore.CYAN}{media_icon} Extracting data for {media_type}: {video.title}")
    print(
        Fore.YELLOW
        + f"📁 Saving to folder: {os.path.basename(os.path.dirname(vid_file))}"
    )

    if config.transcripts_only:
        if is_audio_only:
            print(Fore.RED + f"❌ Transcripts-only mode is not applicable for audiobooks.")
            return ("error", video, "Transcripts not supported for audiobooks")
        video.transcript = scraper.extract_transcript(video.url, resolver)
        if video.transcript:
            downloader.save_transcript(video.transcript, txt_file)
            print(Fore.GREEN + f"✅ Transcript extracted.")
            return None
        else:
            print(Fore.RED + f"❌ No transcript available.")
            return ("error", video, "No transcript available")
    else:
        # Extracting the m3u8 url using our decoupled resolver (tries API first, then falls back to sniffer)
        m3u8 = resolver.resolve_m3u8_url(video.url)
        if m3u8:
            video.m3u8_url = m3u8
            if not is_audio_only:
                video.transcript = scraper.extract_transcript(video.url, resolver)
                if video.transcript:
                    downloader.save_transcript(video.transcript, txt_file)

            print(
                Fore.GREEN
                + f"✅ M3U8 Fetched. Queuing {video.title} for background download..."
            )
            future = executor.submit(downloader.download_video, m3u8, vid_file)
            return (future, video, vid_file)
        else:
            print(Fore.RED + f"❌ No m3u8 found.")
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
            print(f"\n{Fore.YELLOW}⚠️ {len(failed_items)} items failed to process/download.")
            print(f"{Fore.YELLOW}👉 Dead Letter Queue (DLQ) log exported to: {dlq_path}")
        except Exception as e:
            print(f"\n{Fore.RED}❌ {len(failed_items)} items failed to process/download (Failed to write DLQ log: {e})")
    else:
        media_name = "audiobook chapters" if is_audio_only else "course videos"
        print(f"\n{Fore.GREEN}✅ All {media_name} processed successfully!")


def process_course(config: DownloaderConfig):
    print(Fore.CYAN + "🚀 Initializing browser...")
    bm: IBrowser = BrowserFactory.create(browser_type=config.browser_type, headless=config.headless)
    driver = bm.start()

    if not driver:
        print(Fore.RED + "❌ Failed to start browser")
        return

    try:
        auth = AuthService(bm)

        if not _handle_authentication(driver, auth, config.email, config.password, config.manual_login):
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
                for cookie in driver.get_cookies():
                    session.cookies.set(cookie['name'], cookie['value'])
            except Exception as ce:
                print(Fore.YELLOW + f"  ⚠️ Failed to copy cookies from browser: {ce}")

            book_dl = BookDownloaderService(output_dir=config.output_dir)
            success = book_dl.download_book(config, session)
            if success:
                print(Fore.GREEN + "\n✨ Book downloaded and packaged successfully!")
            else:
                print(Fore.RED + "\n❌ Failed to download or package the book.")
            return

        # Retrieve Kaltura session token (ks) if we are in normal download mode
        ks = None
        if not config.manual_login:
            print(Fore.CYAN + "🔑 Extracting active Kaltura Session (ks) token...")
            ks = auth.get_ks()
            if ks:
                print(Fore.GREEN + f"✅ Session acquired: {ks[:20]}...")
            else:
                print(Fore.YELLOW + "⚠️ Failed to acquire Kaltura session (ks). Will rely on sniffer fallback.")

        # Pre-flight check for FFmpeg dependency if downloads are required
        ffmpeg_path = "ffmpeg"
        if not config.transcripts_only:
            detected_path = SanityUtils.get_ffmpeg_path()
            if not detected_path:
                print(Fore.RED + "\n❌ Critical dependency missing: FFmpeg could not be found.")
                print(Fore.YELLOW + "Please install FFmpeg and add it to your system PATH, or place ffmpeg.exe in the project directory.")
                print(Fore.CYAN + "👉 Download URL: https://www.ffmpeg.org/download.html")
                return
            ffmpeg_path = detected_path

        scraper = CourseStructureScraper(bm)
        resolver = MediaUrlResolver(bm, ks=ks)
        downloader = DownloaderService(output_dir=config.output_dir, ffmpeg_path=ffmpeg_path)

        print(Fore.CYAN + "📚 Extracting course structure...")
        structure = scraper.extract_course_structure(config.url, config.audiobook)
        if not structure:
            print(Fore.RED + "❌ Failed to extract course structure.")
            return

        # Dynamically extract course title from driver title (removing common suffix like [Video], [Book], [Audiobook], or [Audio Book])
        course_title = "OReilly Extracted Course"
        if driver:
            try:
                raw_title = driver.title
                if raw_title:
                    course_title = re.sub(r'\s*\[video\]\s*$', "", raw_title, flags=re.IGNORECASE)
                    course_title = re.sub(r'\s*\[book\]\s*$', "", course_title, flags=re.IGNORECASE)
                    course_title = re.sub(r'\s*\[(audiobook|audio\s+book)\]\s*$', "", course_title, flags=re.IGNORECASE)
                    course_title = course_title.strip()
            except Exception:
                pass

        is_audio_only = config.audiobook

        course = build_course(structure, title=course_title)
        print(Fore.GREEN + f"✅ Found {len(course.modules)} modules")
        if is_audio_only:
            print(Fore.CYAN + "🎧 Audiobook/Audio-only course detected! Saving files with .m4a extension...")
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

    finally:
        bm.stop()
        print(f"\n{Fore.MAGENTA}✨ Done! Cleaned up browser.")


def main():
    parser = argparse.ArgumentParser(description="O'Reilly Course (Video/Audio) Downloader")
    parser.add_argument("url", nargs="?", help="URL of the course or audiobook")
    parser.add_argument(
        "--on24-vtt",
        help="Direct URL to an ON24 VTT subtitle file to extract a live-event transcript.",
    )
    parser.add_argument(
        "--event-name",
        default="ON24_Live_Event",
        help="Name of the event to save the transcript under.",
    )
    parser.add_argument("--email", help="Login email")
    parser.add_argument("--password", help="Login password")
    parser.add_argument(
        "--transcripts-only",
        action="store_true",
        help="Only download text transcripts. Skip media m3u8 downloading.",
    )
    parser.add_argument(
        "--audiobook",
        action="store_true",
        help="Download O'Reilly audiobooks (saves files as .m4a and handles audiobook page layout).",
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
    parser.add_argument("--manual-login", action="store_true")
    parser.add_argument("--no-headless", action="store_true")
    parser.add_argument(
        "--browser", choices=["firefox", "chrome", "stealth"], default="stealth"
    )
    parser.add_argument(
        "--output-dir", default="downloads", help="Directory to save downloaded files"
    )
    parser.add_argument(
        "--workers", type=int, default=3, help="Max parallel media downloads"
    )
    parser.add_argument(
        "--debug", action="store_true", help="Enable file logging to downloader.log"
    )

    args = parser.parse_args()

    if args.debug:
        global _log_file
        try:
            _log_file = open("downloader.log", "a", encoding="utf-8")
            sys.excepthook = _handle_unhandled_exception
            print(Fore.CYAN + "📝 Logging active. Detailed logs and errors will be saved to 'downloader.log'.")
        except Exception as e:
            print(Fore.YELLOW + f"⚠️ Warning: Could not initialize log file: {e}")

    if args.on24_vtt:
        print(
            Fore.CYAN + f"\n[ON24 Transcript Mode] Processing Event: {args.event_name}"
        )
        vtt_content = VttProcessor.download_vtt(args.on24_vtt)
        if vtt_content:
            captions = VttProcessor.parse_vtt(vtt_content)
            if captions:
                transcript = VttProcessor.format_transcript(captions, args.event_name)
                dl_svc = DownloaderService(output_dir=args.output_dir)
                out_path = os.path.join(
                    dl_svc.output_dir, args.event_name, "full_transcript.txt"
                )
                dl_svc.save_transcript(transcript, out_path)
                print(
                    Fore.GREEN
                    + f"\n✨ Success! Saved standalone transcript to: {out_path}"
                )
        return

    active_headless = False if args.manual_login else not args.no_headless

    if not args.manual_login and not args.url:
        parser.error(
            "The course URL is required unless using --manual-login or --on24-vtt"
        )

    is_epub = args.epub
    if args.url and "/library/view/" in args.url:
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
    )

    process_course(config)


if __name__ == "__main__":
    main()
