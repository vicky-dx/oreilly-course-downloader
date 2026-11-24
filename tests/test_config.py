from oreilly_downloader.core.config import DownloaderConfig

def test_downloader_config_defaults():
    config = DownloaderConfig(
        url="https://learning.oreilly.com/course/test-course/123/",
        email="test@example.com",
        password="password"
    )
    assert config.url == "https://learning.oreilly.com/course/test-course/123/"
    assert config.email == "test@example.com"
    assert config.password == "password"
    assert config.browser_type == "stealth"
    assert config.headless is False
    assert config.max_workers == 3
    assert config.output_dir == "downloads"
    assert config.audiobook is False
    assert config.browser_binary is None
    assert config.cooling_period == DownloaderConfig.cooling_period

def test_downloader_config_with_custom_binary_and_output():
    config = DownloaderConfig(
        url="https://learning.oreilly.com/course/test-course/123/",
        output_dir="custom_output",
        browser_binary="/usr/bin/google-chrome-stable",
    )
    assert config.output_dir == "custom_output"
    assert config.browser_binary == "/usr/bin/google-chrome-stable"


def test_downloader_config_modular_sub_configs():
    from oreilly_downloader.core.config import BrowserConfig, DownloadOptions, AuthConfig, ContentOptions

    config = DownloaderConfig(
        url="https://learning.oreilly.com/course/test-course/123/",
        browser_type="stealth",
        headless=True,
        max_workers=5,
        resolution="720p",
        cooling_period=15,
        email="user@example.com",
        audiobook=True,
    )

    b_cfg = config.browser_config
    assert isinstance(b_cfg, BrowserConfig)
    assert b_cfg.browser_type == "stealth"
    assert b_cfg.headless is True

    dl_opts = config.download_options
    assert isinstance(dl_opts, DownloadOptions)
    assert dl_opts.max_workers == 5
    assert dl_opts.resolution == "720p"
    assert dl_opts.cooling_period == 15

    a_cfg = config.auth_config
    assert isinstance(a_cfg, AuthConfig)
    assert a_cfg.email == "user@example.com"

    c_opts = config.content_options
    assert isinstance(c_opts, ContentOptions)
    assert c_opts.audiobook is True
    assert c_opts.epub is False
