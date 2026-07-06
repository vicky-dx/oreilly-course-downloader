import re
import time
import sys
from colorama import Fore
from tqdm import tqdm

_ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

def _strip_ansi(text: str) -> str:
    return _ansi_escape.sub('', text)


class Logger:
    _log_file = None

    @classmethod
    def enable_debug_logging(cls, log_path: str = "downloader.log"):
        """Enables output mirroring to a disk log file."""
        try:
            cls._log_file = open(log_path, "a", encoding="utf-8")
        except Exception:
            pass

    @classmethod
    def print(cls, *args, sep=" ", end="\n", file=None, flush=False):
        """Thread-safe print interceptor that is tqdm-friendly and logged to disk."""
        text = sep.join(str(a) for a in args)
        tqdm.write(text, file=file or sys.stdout, end=end)
        
        if cls._log_file:
            try:
                clean_text = _strip_ansi(text)
                timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
                cls._log_file.write(f"[{timestamp}] {clean_text}{end}")
                cls._log_file.flush()
            except Exception:
                pass

    @classmethod
    def _log(cls, msg: str, color: str, prefix: str = "", icon: str = ""):
        pref_str = f"[{prefix}] " if prefix else ""
        icon_str = f"{icon}  " if icon else ""
        formatted_msg = f"{color}{icon_str}{pref_str}{msg}"
        cls.print(formatted_msg)

    @classmethod
    def info(cls, msg: str, prefix: str = ""):
        cls._log(msg, Fore.CYAN, prefix, icon="ℹ️")

    @classmethod
    def success(cls, msg: str, prefix: str = ""):
        cls._log(msg, Fore.GREEN, prefix, icon="✅")

    @classmethod
    def warning(cls, msg: str, prefix: str = ""):
        cls._log(msg, Fore.YELLOW, prefix, icon="⚠️")

    @classmethod
    def error(cls, msg: str, prefix: str = ""):
        cls._log(msg, Fore.RED, prefix, icon="❌")

    @classmethod
    def debug(cls, msg: str, prefix: str = ""):
        """Logs a debug message to the disk log file only (bypassing console output)."""
        if cls._log_file:
            try:
                import time
                pref_str = f"[{prefix}] " if prefix else ""
                timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
                cls._log_file.write(f"[{timestamp}] [DEBUG] {pref_str}{msg}\n")
                cls._log_file.flush()
            except Exception:
                pass
