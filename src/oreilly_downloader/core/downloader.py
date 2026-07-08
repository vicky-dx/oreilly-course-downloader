from .browsers import Logger
import re
import os
import subprocess
import time
import threading
from colorama import init, Fore
from tqdm import tqdm
import concurrent.futures
import json
from typing import Optional
from .models import Course, Video
from .utils import PathManager

init(autoreset=True)


class FFmpegRunner:
    def __init__(self, ffmpeg_path: str = "ffmpeg"):
        self.ffmpeg_path = ffmpeg_path

    def build_cmd(self, m3u8_url: str, temp_output_path: str, is_audio: bool) -> list:
        fmt_flag = "ipod" if is_audio else "mp4"
        return [
            self.ffmpeg_path,
            "-y",
            "-user_agent",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
            "-reconnect",
            "1",
            "-reconnect_streamed",
            "1",
            "-reconnect_delay_max",
            "5",
            "-i",
            m3u8_url,
            "-c",
            "copy",
            "-f",
            fmt_flag,
            temp_output_path,
        ]

    def start_process(self, cmd: list) -> subprocess.Popen:
        return subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )


class ProgressReporter:
    def __init__(self, base_name: str, bar_pos: int):
        self.base_name = base_name
        self.bar_pos = bar_pos
        self.duration_sec = 0.0
        self.pbar = None
        self.duration_re = re.compile(r"Duration:\s*(?P<time>\d{2}:\d{2}:\d{2}\.\d{2})")
        self.time_re = re.compile(r"time=(?P<time>\d{2}:\d{2}:\d{2}\.\d{2})")

    def _parse_time_to_seconds(self, time_str: str) -> float:
        try:
            h, m, s = time_str.split(":")
            return int(h) * 3600 + int(m) * 60 + float(s)
        except Exception:
            return 0.0

    def process_line(self, line: str, attempt: int):
        if not line:
            return

        # Extract Total Duration
        if self.duration_sec == 0.0:
            dur_match = self.duration_re.search(line)
            if dur_match:
                self.duration_sec = self._parse_time_to_seconds(dur_match.group("time"))
                if not self.pbar and self.duration_sec > 0.0:
                    desc_name = self.base_name[:25] + ("..." if len(self.base_name) > 25 else "")
                    status = "DL" if attempt == 1 else f"RT{attempt}"
                    self.pbar = tqdm(
                        total=int(self.duration_sec),
                        desc=f"[{status}] {desc_name}",
                        position=self.bar_pos,
                        leave=True,
                        bar_format="{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]",
                    )

        # Extract Current Progress Time
        if self.pbar:
            time_match = self.time_re.search(line)
            if time_match:
                current_sec = self._parse_time_to_seconds(time_match.group("time"))
                self.pbar.n = min(int(current_sec), int(self.duration_sec))
                self.pbar.refresh()

    def close(self):
        if self.pbar:
            self.pbar.close()
            self.pbar = None


class RetryPolicy:
    def __init__(self, max_retries: int = 3):
        self.max_retries = max_retries

    def wait(self, attempt: int):
        if attempt < self.max_retries:
            time.sleep(3 * attempt)


class DownloaderService:
    def __init__(self, output_dir: str = "downloads", ffmpeg_path: str = "ffmpeg"):
        self.output_dir = output_dir
        self.ffmpeg_path = ffmpeg_path
        self._pos_lock = threading.Lock()
        self._active_positions = set()
        self.ffmpeg_runner = FFmpegRunner(ffmpeg_path)
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

    def _acquire_progress_position(self) -> int:
        with self._pos_lock:
            pos = 0
            while pos in self._active_positions:
                pos += 1
            self._active_positions.add(pos)
            return pos

    def _release_progress_position(self, pos: int):
        with self._pos_lock:
            self._active_positions.discard(pos)

    def download_video(
        self, m3u8_url: str, output_path: str, max_retries: int = 3
    ) -> bool:
        """Atomic, auto-reconnecting fetch of media files via ffmpeg with Python-level retries."""
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        temp_output_path = output_path + ".part"
        base_name = os.path.basename(output_path)
        bar_pos = self._acquire_progress_position()

        is_audio = output_path.lower().endswith(".m4a")
        ffmpeg_cmd = self.ffmpeg_runner.build_cmd(m3u8_url, temp_output_path, is_audio)
        retry_policy = RetryPolicy(max_retries)

        try:
            for attempt in range(1, max_retries + 1):
                try:
                    process = self.ffmpeg_runner.start_process(ffmpeg_cmd)
                    reporter = ProgressReporter(base_name, bar_pos)
                    stderr_output = []

                    for line in process.stderr:
                        stderr_output.append(line)
                        reporter.process_line(line, attempt)

                    process.wait()
                    reporter.close()

                    if process.returncode == 0:
                        if os.path.exists(temp_output_path):
                            os.replace(temp_output_path, output_path)
                        Logger.success(f"Finished: {base_name}")
                        return True

                    error_lines = [
                        l for l in "".join(stderr_output).split("\n") if l.strip()
                    ]
                    last_error = error_lines[-1] if error_lines else "Unknown error"
                    Logger.error(f"Attempt {attempt} failed: {last_error}")

                except Exception as e:
                    Logger.error(f"Exception on attempt {attempt}: {str(e)}")

                retry_policy.wait(attempt)

            if os.path.exists(temp_output_path):
                os.remove(temp_output_path)
            return False

        finally:
            self._release_progress_position(bar_pos)

    def save_transcript(self, transcript: str, filepath: str):
        """Saves a string transcript locally."""
        if not transcript:
            return

        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(transcript)
        except Exception as e:
            Logger.error(f" Failed to save transcript: {e}")

    def _process_single_item(
        self,
        executor: concurrent.futures.ThreadPoolExecutor,
        video: Video,
        vid_idx: int,
        lesson_title: str,
        less_idx: int,
        module_title: str,
        mod_idx: int,
        course_dir: str,
        scraper,
        resolver,
        config,
        is_audio_only: bool = False,
    ) -> Optional[tuple]:
        """Handles extraction and immediate download of a single video/audio. Returns Tuple if active action taken."""
        vid_file, txt_file = PathManager.get_video_paths(
            course_dir, mod_idx, module_title, less_idx, lesson_title, vid_idx, video.title, is_audio_only
        )

        if is_audio_only:
            if os.path.exists(vid_file):
                Logger.warning(f"Skipping {video.title} (audio already exists)")
                return None
        else:
            if config.transcripts_only and os.path.exists(txt_file):
                Logger.warning(f"Skipping {video.title} (transcript already extracted)")
                return None
            elif not config.transcripts_only and os.path.exists(vid_file):
                # Video is downloaded. Check if the transcript is missing.
                if not os.path.exists(txt_file):
                    Logger.warning(f"Video exists but transcript is missing for {video.title}. Extracting transcript...")
                    video.transcript = scraper.extract_transcript(video.url, resolver)
                    if video.transcript:
                        self.save_transcript(video.transcript, txt_file)
                        Logger.success(f"Transcript extracted.")
                else:
                    Logger.warning(f"Skipping {video.title} (video and transcript already exist)")
                return None

        media_icon = "🎧" if is_audio_only else "🎥"
        media_type = "Audio" if is_audio_only else "Video"
        Logger.info(f"{media_icon} Extracting data for {media_type}: {video.title}")
        Logger.warning(f"Saving to folder: {os.path.basename(os.path.dirname(vid_file))}")

        if config.transcripts_only:
            if is_audio_only:
                Logger.error(f"Transcripts-only mode is not applicable for audiobooks.")
                return ("error", video, "Transcripts not supported for audiobooks")
            video.transcript = scraper.extract_transcript(video.url, resolver)
            if video.transcript:
                self.save_transcript(video.transcript, txt_file)
                Logger.success(f"Transcript extracted.")
                return None
            else:
                Logger.error(f"No transcript available.")
                return ("error", video, "No transcript available")
        else:
            # Extracting the m3u8 url using our decoupled resolver (tries API first, then falls back to sniffer)
            m3u8 = resolver.resolve_m3u8_url(video.url, resolution=config.resolution)
            if m3u8:
                video.m3u8_url = m3u8
                if not is_audio_only:
                    video.transcript = scraper.extract_transcript(video.url, resolver)
                    if video.transcript:
                        self.save_transcript(video.transcript, txt_file)

                Logger.success(f"M3U8 Fetched. Queuing {video.title} for background download...")
                future = executor.submit(self.download_video, m3u8, vid_file)
                return (future, video, vid_file)
            else:
                Logger.error(f"No m3u8 found.")
                return ("error", video, "Could not resolve M3U8 stream URL")

    def download_course(
        self,
        course: Course,
        scraper,
        resolver,
        config,
        course_dir: str,
        is_audio_only: bool = False,
    ):
        """Iterates through the course structure and dispatches video processing with a bounded queue."""
        if not is_audio_only and config.resolution != "best":
            Logger.info(f"Target video resolution: {config.resolution}")

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

                        res = self._process_single_item(
                            executor=executor,
                            video=video,
                            vid_idx=vid_idx,
                            lesson_title=lesson.title,
                            less_idx=less_idx,
                            module_title=module.title,
                            mod_idx=mod_idx,
                            course_dir=course_dir,
                            scraper=scraper,
                            resolver=resolver,
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
                Logger.warning(f"Dead Letter Queue (DLQ) log exported to: {dlq_path}")
            except Exception as e:
                Logger.error(f"{len(failed_items)} items failed to process/download (Failed to write DLQ log: {e})")
        else:
            media_name = "audiobook chapters" if is_audio_only else "course videos"
            Logger.success(f"All {media_name} processed successfully!")
