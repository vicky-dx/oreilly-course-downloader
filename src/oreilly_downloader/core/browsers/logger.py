import re
import time
import sys
from colorama import Fore, Style
from tqdm import tqdm

_ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

def _strip_ansi(text: str) -> str:
    return _ansi_escape.sub('', text)

def _get_visual_width(text: str) -> int:
    clean = _strip_ansi(text)
    width = 0
    for char in clean:
        if char in ('\ufe0f', '\u200d', '\ufe0e'):
            continue
        val = ord(char)
        # Exclude box drawing characters, block elements, and geometric shapes (U+2500 - U+25FF)
        if val >= 0x2000 and not (0x2500 <= val <= 0x25FF):
            width += 2
        else:
            width += 1
    return width


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
        cls._log(msg, Fore.MAGENTA, prefix, icon="✅")

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

    @classmethod
    def banner(cls):
        """Prints a beautiful product banner in the terminal."""
        cls.print(Fore.CYAN + "┌" + "─" * 58 + "┐")
        # Visual width of title text is 30 (emoji takes 2 columns, text takes 28)
        title_text = "⚡  O'REILLY COURSE DOWNLOADER"
        cls.print(Fore.CYAN + "│ " + Fore.GREEN + Style.BRIGHT + title_text + " " * (56 - 30) + Fore.CYAN + " │")
        # Visual width of subtitle text is 50
        subtitle_text = "   Secure, automated course & audiobook downloader"
        cls.print(Fore.CYAN + "│ " + Fore.LIGHTBLACK_EX + subtitle_text + " " * (56 - 50) + Fore.CYAN + " │")
        cls.print(Fore.CYAN + "└" + "─" * 58 + "┘")

    @classmethod
    def panel(cls, title: str, lines: list, border_color=None, text_color=None, title_color=None):
        """Prints a styled box/panel around the text lines."""
        if border_color is None:
            border_color = Fore.CYAN
        if text_color is None:
            text_color = Fore.RESET
        if title_color is None:
            title_color = Fore.GREEN + Style.BRIGHT

        clean_lines = [str(line) for line in lines]
        
        # Calculate dynamic width based on visual terminal cell width
        max_visual_len = max(_get_visual_width(title) + 4, max(_get_visual_width(line) for line in clean_lines) if clean_lines else 0)
        max_visual_len = max(max_visual_len, 40)
        width = max_visual_len + 4

        # Draw top
        title_part = f" {title} " if title else ""
        title_visual_len = _get_visual_width(title_part)
        fill_len = width - title_visual_len - 2
        left_fill = fill_len // 2
        right_fill = fill_len - left_fill
        
        cls.print(border_color + "┌" + "─" * left_fill + title_color + title_part + border_color + "─" * right_fill + "┐")
        for line in clean_lines:
            line_visual_len = _get_visual_width(line)
            pad = width - line_visual_len - 2
            cls.print(border_color + "│ " + text_color + line + " " * (pad - 1) + border_color + "│")
        cls.print(border_color + "└" + "─" * (width - 2) + "┘")

    @classmethod
    def config_summary(cls, config):
        """Prints a beautiful config dashboard."""
        target_mode = "Course (Video)"
        if config.audiobook:
            target_mode = "Audiobook"
        elif config.epub:
            target_mode = "EPUB Book"
            
        display_url = config.url or 'N/A'
        # Prevent very long URLs from blowing up the console dashboard width (caps at ~55 visual chars)
        if len(display_url) > 55:
            display_url = display_url[:35] + "..." + display_url[-17:]
            
        summary_lines = [
            f"🎯 Mode:       {target_mode}",
            f"🔗 URL:        {display_url}",
            f"📁 Output Dir: {config.output_dir}",
            f"🚀 Browser:    {config.browser_type} (Headless: {config.headless})",
            f"🎥 Resolution: {config.resolution}",
            f"🧵 Workers:    {config.max_workers}"
        ]
        
        cls.panel("CONFIGURATION SUMMARY", summary_lines, border_color=Fore.CYAN)

