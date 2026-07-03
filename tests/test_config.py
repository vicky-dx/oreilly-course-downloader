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
    assert config.browser_type == "firefox"
    assert config.headless is True
    assert config.max_workers == 3
    assert config.output_dir == "downloads"
