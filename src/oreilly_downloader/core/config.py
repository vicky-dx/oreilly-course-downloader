from dataclasses import dataclass
from typing import Optional


@dataclass
class BrowserConfig:
    """Browser execution settings (Interface Segregation Principle)."""
    browser_type: str = "stealth"
    headless: bool = False
    browser_binary: Optional[str] = None


@dataclass
class DownloadOptions:
    """Download performance and destination options (Interface Segregation Principle)."""
    max_workers: int = 3
    resolution: str = "best"
    output_dir: str = "downloads"
    cooling_period: int = 5
    transcripts_only: bool = False


@dataclass
class AuthConfig:
    """Authentication settings and credentials (Interface Segregation Principle)."""
    email: Optional[str] = None
    password: Optional[str] = None
    manual_login: bool = False
    auto_signup: bool = False
    base_email: Optional[str] = None


@dataclass
class ContentOptions:
    """Target content format options (Interface Segregation Principle)."""
    audiobook: bool = False
    epub: bool = False
    web_viewer: bool = False


@dataclass
class DownloaderConfig:
    """Unified configuration composed of modular sub-configs (ISP).
    Maintains full backwards compatibility with flattened constructor parameters.
    """
    url: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None
    browser_type: str = "stealth"
    headless: bool = False
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
    browser_binary: Optional[str] = None
    batch_file: Optional[str] = None
    cooling_period: int = 5
    debug: bool = False

    @property
    def browser_config(self) -> BrowserConfig:
        return BrowserConfig(
            browser_type=self.browser_type,
            headless=self.headless,
            browser_binary=self.browser_binary,
        )

    @property
    def download_options(self) -> DownloadOptions:
        return DownloadOptions(
            max_workers=self.max_workers,
            resolution=self.resolution,
            output_dir=self.output_dir,
            cooling_period=self.cooling_period,
            transcripts_only=self.transcripts_only,
        )

    @property
    def auth_config(self) -> AuthConfig:
        return AuthConfig(
            email=self.email,
            password=self.password,
            manual_login=self.manual_login,
            auto_signup=self.auto_signup,
            base_email=self.base_email,
        )

    @property
    def content_options(self) -> ContentOptions:
        return ContentOptions(
            audiobook=self.audiobook,
            epub=self.epub,
            web_viewer=self.web_viewer,
        )

