import pytest
from unittest.mock import MagicMock, patch
from oreilly_downloader.core.media_resolver import MediaUrlResolver

class MockResponse:
    def __init__(self, json_data, status_code=200):
        self.json_data = json_data
        self.status_code = status_code

    def json(self):
        return self.json_data

def test_extract_video_id():
    mock_browser = MagicMock()
    mock_browser.driver = MagicMock()
    resolver = MediaUrlResolver(browser=mock_browser, ks="dummy-ks")
    
    # Test standard O'Reilly video URLs
    url = "https://learning.oreilly.com/videos/course-name/9781806388578/9781806388578-video2_2"
    assert resolver._extract_video_id(url) == "9781806388578-video2_2"
    
    # Test alternative patterns
    url2 = "https://learning.oreilly.com/videos/title/1234567890-chap1"
    assert resolver._extract_video_id(url2) == "1234567890-chap1"
    
    # Test audiobook patterns with standard and hyphenated chapter IDs
    url_audio1 = "https://learning.oreilly.com/library/view/designing-distributed-systems/9781663754035/9781663754035-a00001/"
    assert resolver._extract_video_id(url_audio1) == "9781663754035-a00001"
    
    url_audio2 = "https://learning.oreilly.com/library/view/kafka-building-reliable/9781806388578/9781806388578-chapter-1.html"
    assert resolver._extract_video_id(url_audio2) == "9781806388578-chapter-1"
    
    # Test invalid URLs
    assert resolver._extract_video_id("https://learning.oreilly.com/course/title") is None

@patch("requests.Session.get")
def test_resolve_via_api_success(mock_get):
    # Mock VideoClip response containing kaltura_entry_id and transcripts
    clip_data = {
        "kaltura_entry_id": "1_dummy_entry",
        "transcriptions": [
            {
                "language": "en",
                "transcription": {
                    "lines": [
                        {"begin": "00:00:01.200", "end": "00:00:03.400", "text": "Hello world"}
                    ]
                }
            }
        ]
    }
    
    # Mock Kaltura PlaybackContext multirequest response
    playback_data = [
        {
            "sources": [
                {
                    "format": "applehttp",
                    "url": "https://cdn.kaltura.com/dummy.m3u8"
                }
            ]
        }
    ]
    
    # Configure mock session gets/posts
    mock_get.return_value = MockResponse(clip_data, 200)
    
    mock_browser = MagicMock()
    mock_browser.driver = MagicMock()
    resolver = MediaUrlResolver(browser=mock_browser, ks="dummy-ks")
    resolver.session.post = MagicMock(return_value=MockResponse(playback_data, 200))
    
    m3u8 = resolver._resolve_via_api("9781806388578-video1_1")
    
    assert m3u8 == "https://cdn.kaltura.com/dummy.m3u8"
    assert "9781806388578-video1_1" in resolver.cached_transcripts
    assert resolver.cached_transcripts["9781806388578-video1_1"] == "[00:01] Hello world"

def test_resolve_via_api_no_ks():
    mock_browser = MagicMock()
    mock_browser.driver = MagicMock()
    resolver = MediaUrlResolver(browser=mock_browser, ks=None)
    assert resolver._resolve_via_api("some-id") is None
