import re
import os
import shutil
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
            name = name[:80].rstrip(" .-")
            
        return name if name else "unnamed"

    @staticmethod
    def get_ffmpeg_path() -> Optional[str]:
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

    @staticmethod
    def get_chrome_path(custom_path: Optional[str] = None) -> Optional[str]:
        """Resolves a valid Chrome/Chromium executable path."""
        # 1. Check explicit custom path
        if custom_path:
            if os.path.exists(custom_path):
                return os.path.abspath(custom_path)
            # Check if it was passed as just a command name in PATH
            which_custom = shutil.which(custom_path)
            if which_custom:
                return which_custom
            return None

        # 2. Check OREILLY_BROWSER_BINARY environment variable
        env_binary = os.environ.get("OREILLY_BROWSER_BINARY")
        if env_binary and os.path.exists(env_binary):
            return os.path.abspath(env_binary)

        # 3. Check system PATH for common Chrome & Chromium binaries
        binaries = [
            "google-chrome",
            "google-chrome-stable",
            "chrome",
            "chromium",
            "chromium-browser",
            "brave-browser",
            "brave",
            "msedge",
        ]
        for b in binaries:
            found = shutil.which(b)
            if found:
                return found

        # 4. Check OS-specific standard installation locations
        is_windows = os.name == "nt"
        is_mac = os.uname().sysname == "Darwin" if hasattr(os, "uname") else False

        candidate_paths = []
        if is_windows:
            local_appdata = os.environ.get("LOCALAPPDATA", "")
            prog_files = os.environ.get("PROGRAMFILES", r"C:\Program Files")
            prog_files_x86 = os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")

            candidate_paths.extend([
                os.path.join(local_appdata, r"Google\Chrome\Application\chrome.exe"),
                os.path.join(prog_files, r"Google\Chrome\Application\chrome.exe"),
                os.path.join(prog_files_x86, r"Google\Chrome\Application\chrome.exe"),
                os.path.join(prog_files, r"BraveSoftware\Brave-Browser\Application\brave.exe"),
                os.path.join(local_appdata, r"BraveSoftware\Brave-Browser\Application\brave.exe"),
                os.path.join(prog_files_x86, r"Microsoft\Edge\Application\msedge.exe"),
                os.path.join(prog_files, r"Microsoft\Edge\Application\msedge.exe"),
            ])
        elif is_mac:
            candidate_paths.extend([
                "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
                "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
                "/Applications/Chromium.app/Contents/MacOS/Chromium",
            ])
        else:
            # Linux paths
            candidate_paths.extend([
                "/usr/bin/google-chrome",
                "/usr/bin/google-chrome-stable",
                "/usr/bin/chromium",
                "/usr/bin/chromium-browser",
                "/usr/bin/brave-browser",
                "/snap/bin/chromium",
            ])

        for p in candidate_paths:
            if p and os.path.exists(p):
                return p

        return None

    @staticmethod
    def get_firefox_path(custom_path: Optional[str] = None) -> Optional[str]:
        """Resolves a valid Firefox executable path."""
        if custom_path:
            if os.path.exists(custom_path):
                return os.path.abspath(custom_path)
            which_custom = shutil.which(custom_path)
            if which_custom:
                return which_custom
            return None

        env_binary = os.environ.get("OREILLY_BROWSER_BINARY")
        if env_binary and os.path.exists(env_binary):
            return os.path.abspath(env_binary)

        found = shutil.which("firefox")
        if found:
            return found

        is_windows = os.name == "nt"
        is_mac = os.uname().sysname == "Darwin" if hasattr(os, "uname") else False

        candidate_paths = []
        if is_windows:
            prog_files = os.environ.get("PROGRAMFILES", r"C:\Program Files")
            prog_files_x86 = os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")
            candidate_paths.extend([
                os.path.join(prog_files, r"Mozilla Firefox\firefox.exe"),
                os.path.join(prog_files_x86, r"Mozilla Firefox\firefox.exe"),
            ])
        elif is_mac:
            candidate_paths.append("/Applications/Firefox.app/Contents/MacOS/firefox")
        else:
            candidate_paths.extend([
                "/usr/bin/firefox",
                "/snap/bin/firefox",
            ])

        for p in candidate_paths:
            if p and os.path.exists(p):
                return p

        return None

class PathManager:
    @staticmethod
    def get_course_dir(base_dir: str, course_title: str) -> str:
        return os.path.join(base_dir, SanityUtils.sanitize_filename(course_title))

    @staticmethod
    def get_profile_dir(profile_name: str, base_dir: Optional[str] = None) -> str:
        if base_dir:
            return os.path.join(base_dir, profile_name)
        return os.path.join(os.getcwd(), profile_name)

    @staticmethod
    def get_video_paths(course_dir: str, mod_idx: int, mod_title: str, less_idx: int, less_title: str, vid_idx: int, vid_title: str, is_audio_only: bool = False):
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
        ext = ".m4a" if is_audio_only else ".mp4"
        return f"{vid_base_dir}{ext}", f"{vid_base_dir}_transcript.txt"
