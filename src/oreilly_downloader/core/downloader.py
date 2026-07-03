import re
import os
import subprocess
import time
import threading
from colorama import init, Fore
from tqdm import tqdm

init(autoreset=True)


class DownloaderService:
    def __init__(self, output_dir: str = "downloads", ffmpeg_path: str = "ffmpeg"):
        self.output_dir = output_dir
        self.ffmpeg_path = ffmpeg_path
        self._pos_lock = threading.Lock()
        self._active_positions = set()
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

    def _parse_time_to_seconds(self, time_str: str) -> float:
        """Parse HH:MM:SS.xx string to seconds."""
        try:
            h, m, s = time_str.split(":")
            return int(h) * 3600 + int(m) * 60 + float(s)
        except:
            return 0.0

    def download_video(
        self, m3u8_url: str, output_path: str, max_retries: int = 3
    ) -> bool:
        """Atomic, auto-reconnecting fetch of media files via ffmpeg with Python-level retries."""
        # Create output directories if they do not exist
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        temp_output_path = output_path + ".part"
        base_name = os.path.basename(output_path)
        # Allocate a reusable slot for this concurrent download's bar
        bar_pos = self._acquire_progress_position()

        try:
            fmt_flag = "ipod" if output_path.lower().endswith(".m4a") else "mp4"
            ffmpeg_cmd = [
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

            for attempt in range(1, max_retries + 1):
                try:
                    # We'll use tqdm for status updates directly using description
                    process = subprocess.Popen(
                        ffmpeg_cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                    )

                    duration_sec = 0.0
                    pbar = None
                    stderr_output = []

                    # Regex patterns for parsing ffmpeg output
                    duration_re = re.compile(
                        r"Duration:\s*(?P<time>\d{2}:\d{2}:\d{2}\.\d{2})"
                    )
                    time_re = re.compile(r"time=(?P<time>\d{2}:\d{2}:\d{2}\.\d{2})")

                    while True:
                        line = process.stderr.readline()
                        if not line and process.poll() is not None:
                            break

                        if not line:
                            continue

                        stderr_output.append(line)

                        # Extract Total Duration
                        if duration_sec == 0.0:
                            dur_match = duration_re.search(line)
                            if dur_match:
                                duration_sec = self._parse_time_to_seconds(
                                    dur_match.group("time")
                                )
                                if not pbar:
                                    # Truncate long names for a cleaner layout
                                    desc_name = base_name[:25] + (
                                        "..." if len(base_name) > 25 else ""
                                    )
                                    status = "DL" if attempt == 1 else f"RT{attempt}"
                                    pbar = tqdm(
                                        total=int(duration_sec),
                                        desc=f"[{status}] {desc_name}",
                                        position=bar_pos,
                                        leave=True,
                                        bar_format="{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]",
                                    )

                        # Extract Current Progress Time
                        if pbar:
                            time_match = time_re.search(line)
                            if time_match:
                                current_sec = self._parse_time_to_seconds(
                                    time_match.group("time")
                                )
                                pbar.n = min(int(current_sec), int(duration_sec))
                                pbar.refresh()

                    if pbar:
                        pbar.close()

                    if process.returncode == 0:
                        if os.path.exists(temp_output_path):
                            os.replace(temp_output_path, output_path)
                        # Use tqdm.write so we don't break other active bars
                        tqdm.write(Fore.GREEN + f"✅ Finished: {base_name}")
                        return True

                    error_lines = [
                        line for line in "".join(stderr_output).split("\n") if line.strip()
                    ]
                    last_error = error_lines[-1] if error_lines else "Unknown error"
                    tqdm.write(Fore.RED + f"❌ Attempt {attempt} failed: {last_error}")

                except Exception as e:
                    tqdm.write(Fore.RED + f"❌ Exception on attempt {attempt}: {str(e)}")

                if attempt < max_retries:
                    time.sleep(3 * attempt)  # Wait 3s, then 6s before retry

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
            print(Fore.RED + f"❌ Failed to save transcript: {e}")
