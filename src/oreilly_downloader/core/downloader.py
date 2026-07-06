from .browsers import Logger
import re
import os
import subprocess
import time
import threading
from colorama import init, Fore
from tqdm import tqdm

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

                    while True:
                        line = process.stderr.readline()
                        if not line and process.poll() is not None:
                            break
                        if not line:
                            continue
                        stderr_output.append(line)
                        reporter.process_line(line, attempt)

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
