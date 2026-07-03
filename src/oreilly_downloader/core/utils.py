import re
import os
from typing import Optional

class SanityUtils:
    @staticmethod
    def sanitize_filename(name: str) -> str:
        # Replace Windows-restricted characters with a dash
        name = re.sub(r'[<>:"/\\|?*]', '-', name)
        
        # Replace newlines/carriage returns
        name = name.replace('\n', ' ').replace('\r', '')
        
        # Squeeze consecutive spaces and strip
        name = " ".join(name.split()).strip()
        
        # Strip trailing periods, spaces, and dashes to prevent Windows path issues
        name = name.strip(" .-")
        
        # Squeeze consecutive dashes
        name = re.sub(r'-+', '-', name)
        
        # Truncate length to prevent deep-nested MAX_PATH issues
        if len(name) > 80:
            name = name[:77].strip(" .-") + "..."
            
        return name if name else "unnamed"

    @staticmethod
    def get_ffmpeg_path() -> Optional[str]:
        import shutil
        
        # 1. Check system PATH
        path = shutil.which("ffmpeg")
        if path:
            return path
            
        # 2. Check common directories based on OS
        is_windows = os.name == "nt"
        binary_name = "ffmpeg.exe" if is_windows else "ffmpeg"
        
        common_paths = [
            os.path.join(os.getcwd(), binary_name),
            os.path.join(os.getcwd(), "bin", binary_name),
        ]
        
        if is_windows:
            common_paths.extend([
                r"C:\ffmpeg\bin\ffmpeg.exe",
                r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
            ])
            
        for p in common_paths:
            if os.path.exists(p):
                return p
        return None

class PathManager:
    @staticmethod
    def get_course_dir(base_dir: str, course_title: str) -> str:
        return os.path.join(base_dir, SanityUtils.sanitize_filename(course_title))

    @staticmethod
    def get_video_paths(course_dir: str, mod_idx: int, mod_title: str, less_idx: int, less_title: str, vid_idx: int, vid_title: str):
        if less_title == "Videos":
            vid_base_dir = os.path.join(
                course_dir,
                f"{mod_idx:02d} - {SanityUtils.sanitize_filename(mod_title)}",
                f"{vid_idx:02d} - {SanityUtils.sanitize_filename(vid_title)}",
            )
        else:
            vid_base_dir = os.path.join(
                course_dir,
                f"{mod_idx:02d} - {SanityUtils.sanitize_filename(mod_title)}",
                f"{less_idx:02d} - {SanityUtils.sanitize_filename(less_title)}",
                f"{vid_idx:02d} - {SanityUtils.sanitize_filename(vid_title)}",
            )
        return f"{vid_base_dir}.mp4", f"{vid_base_dir}_transcript.txt"
