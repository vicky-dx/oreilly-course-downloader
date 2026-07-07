from dataclasses import dataclass
from typing import Optional


@dataclass
class DownloaderConfig:
    url: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None
    browser_type: str = "firefox"
    headless: bool = True
    transcripts_only: bool = False
    manual_login: bool = False
    output_dir: str = "downloads"
    max_workers: int = 3
    audiobook: bool = False
    epub: bool = False
    web_viewer: bool = False
    auto_signup: bool = False
    base_email: Optional[str] = None
    resolution: str = "best"




