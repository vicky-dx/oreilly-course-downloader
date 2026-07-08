from .browsers import Logger
import time
import re
import requests
from typing import Optional
from colorama import init, Fore
from .selectors import ExtractorSelectors

init(autoreset=True)


class MediaUrlResolver:
    def __init__(self, browser, ks: Optional[str] = None):
        if hasattr(browser, "driver") and browser.driver is not None:
            self.browser = browser.driver
        else:
            self.browser = browser
        self.driver = self.browser
        self.ks = ks
        self.cached_transcripts = {}
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"
        })
        
        # Configure automatic HTTP retries with exponential backoff
        from urllib3.util import Retry
        from requests.adapters import HTTPAdapter
        
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            raise_on_status=False
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

        if self.driver:
            try:
                for cookie in self.driver.cookies.get_all():
                    self.session.cookies.set(cookie['name'], cookie['value'])
            except Exception as e:
                Logger.warning(f" Warning: Could not initialize resolver session cookies: {e}")

    def _extract_video_id(self, video_url: str) -> Optional[str]:
        """Extracts the unique O'Reilly videoclip ID from the URL (e.g. 9781663754035-a00004)."""
        # Matches ISBN followed by a hyphen and chapter code (e.g. 9781663754035-a00004 or 9781663754035-chapter1)
        match = re.search(r'\b(978\d{10})-[a-zA-Z0-9_-]+', video_url)
        if match:
            return match.group(0)
        # Fallback to any 10-13 digit number followed by a hyphen and chapter code
        match = re.search(r'\b\d{10,13}-[a-zA-Z0-9_-]+', video_url)
        if match:
            return match.group(0)
        return None

    def _resolve_via_api(self, video_id: str) -> Optional[str]:
        """Resolves the .m3u8 stream URL using direct API fetches to O'Reilly and Kaltura."""
        if not self.ks:
            return None

        try:
            # 1. Query O'Reilly VideoClip API to get kaltura_entry_id
            clip_url = f"https://learning.oreilly.com/api/v1/videoclips/{video_id}/"
            
            # Lazy initialize cookies if they are empty
            if not self.session.cookies:
                try:
                    for cookie in self.driver.cookies.get_all():
                        self.session.cookies.set(cookie['name'], cookie['value'])
                except Exception as e:
                    Logger.warning(f" Failed to fetch cookies from driver: {e}")

            clip_resp = self.session.get(clip_url, timeout=15)
            
            # Auto-refresh cookies if unauthorized
            if clip_resp.status_code in (401, 403):
                Logger.warning(f" O'Reilly API unauthorized (status {clip_resp.status_code}). Refreshing cookies...")
                try:
                    self.session.cookies.clear()
                    for cookie in self.driver.cookies.get_all():
                        self.session.cookies.set(cookie['name'], cookie['value'])
                    clip_resp = self.session.get(clip_url, timeout=15)
                except Exception as e:
                    Logger.error(f" Failed to refresh cookies from driver: {e}")

            if clip_resp.status_code != 200:
                Logger.warning(f" O'Reilly VideoClip API returned status {clip_resp.status_code}")
                return None

            clip_data = clip_resp.json()
            
            # Extract transcript if present in the O'Reilly API response
            transcriptions = clip_data.get("transcriptions", [])
            if transcriptions:
                try:
                    trans_obj = next((t for t in transcriptions if t.get("language") == "en"), transcriptions[0])
                    lines_data = trans_obj.get("transcription", {}).get("lines", [])
                    formatted_lines = []
                    for line in lines_data:
                        begin = line.get("begin", "")
                        # Format timestamp (e.g., "00:00:00.519" -> "00:00" or "00:12:34")
                        parts = begin.split(".")
                        time_str = parts[0] if parts else "00:00:00"
                        if time_str.startswith("00:"):
                            time_str = time_str[3:]
                        
                        text = line.get("text", "").strip()
                        if text:
                            formatted_lines.append(f"[{time_str}] {text}")
                    
                    if formatted_lines:
                        self.cached_transcripts[video_id] = "\n\n".join(formatted_lines)
                except Exception as te:
                    Logger.warning(f"   Failed to parse API transcript: {te}")

            entry_id = clip_data.get("kaltura_entry_id")
            if not entry_id:
                Logger.warning(f" O'Reilly API response missing kaltura_entry_id")
                return None

            # 2. Query Kaltura getPlaybackContext API
            playback_url = "https://cdnapisec.kaltura.com/api_v3/service/multirequest"
            payload = {
                "1": {
                    "service": "baseEntry",
                    "action": "getPlaybackContext",
                    "entryId": entry_id,
                    "ks": self.ks,
                    "contextDataParams": {
                        "objectType": "KalturaContextDataParams",
                        "flavorTags": "all"
                    }
                },
                "apiVersion": "3.3.0",
                "format": 1,
                "ks": self.ks,
                "clientTag": "html5:v3.17.86",
                "partnerId": "1926081"
            }

            playback_resp = self.session.post(playback_url, json=payload, timeout=15)
            if playback_resp.status_code != 200:
                Logger.warning(f" Kaltura multirequest API returned status {playback_resp.status_code}")
                return None

            playback_data = playback_resp.json()
            context = playback_data[0]
            sources = context.get("sources", [])

            def _append_ks(hls_url: str) -> str:
                if not self.ks or "/ks/" in hls_url:
                    return hls_url
                if "/a.m3u8" in hls_url:
                    return hls_url.replace("/a.m3u8", f"/ks/{self.ks}/a.m3u8")
                return hls_url

            # Find HLS format (applehttp) source
            hls_source = next((s for s in sources if s.get("format") == "applehttp"), None)
            if hls_source and hls_source.get("url"):
                return _append_ks(hls_source.get("url"))

            # Fallback to any URL format source
            url_source = next((s for s in sources if s.get("format") == "url"), None)
            if url_source and url_source.get("url"):
                return _append_ks(url_source.get("url"))

            Logger.warning(f" No HLS or URL streams found in Kaltura PlaybackContext")
            return None
        except Exception as e:
            Logger.warning(f" Direct API resolution failed: {e}")
            return None

    def _resolve_via_sniffer(self, video_url: str, timeout: int = 45) -> Optional[str]:
        """Resolves the .m3u8 stream URL using the Selenium network sniffer fallback."""
        try:
            # Clear performance entries before navigating
            try:
                self.driver.actions.execute_js("performance.clearResourceTimings();")
            except Exception:
                pass

            self.driver.navigation.to(video_url)
            self.driver.wait.for_present(self.driver.find_element(ExtractorSelectors.BODY), 15)

            script = """
            return window.performance.getEntriesByType("resource")
                .map(e => e.name)
                .filter(name => name.includes('.m3u8'));
            """
            urls = set()
            start_time = time.time()
            Logger.info("Sniffing browser network traffic for .m3u8 stream...")
            last_status_time = start_time
            while time.time() - start_time < timeout:
                current_time = time.time()
                if current_time - last_status_time >= 10:
                    elapsed = int(current_time - start_time)
                    Logger.info(f"   .. Still sniffing ({elapsed}s elapsed) ..")
                    last_status_time = current_time

                main_links = self.driver.actions.execute_js(script)
                if main_links:
                    for link in main_links:
                        urls.add(link)
                
                iframes = self.driver.find_elements(ExtractorSelectors.IFRAMES)
                for iframe in iframes:
                    try:
                        with self.driver.navigation.frame(iframe):
                            iframe_links = self.driver.actions.execute_js(script)
                            if iframe_links:
                                for link in iframe_links:
                                    urls.add(link)
                    except Exception:
                        pass
                if urls:
                    url_list = list(urls)
                    return url_list[0]
                time.sleep(2)
            return None
        except Exception as e:
            Logger.error(f" Sniffer fallback failed: {e}")
            return None

    def _select_resolution(self, master_url: str, target_resolution: str) -> str:
        """Parses the master M3U8 file and extracts the sub-playlist URL for the target resolution."""
        if not target_resolution or target_resolution == "best":
            return master_url

        try:
            # Clean up target resolution string (e.g. "720p" -> 720, "1080p" -> 1080)
            target_height = int(target_resolution.lower().replace("p", ""))
        except ValueError:
            return master_url

        try:
            resp = self.session.get(master_url, timeout=10)
            if resp.status_code != 200:
                return master_url

            lines = resp.text.splitlines()
            streams = [] # list of tuples: (height, url)
            
            i = 0
            while i < len(lines):
                line = lines[i].strip()
                if line.startswith("#EXT-X-STREAM-INF:"):
                    # Extract RESOLUTION value
                    res_match = re.search(r'RESOLUTION=\d+x(\d+)', line)
                    if res_match:
                        height = int(res_match.group(1))
                        # Read the next non-empty line as the stream URL
                        i += 1
                        while i < len(lines) and not lines[i].strip():
                            i += 1
                        if i < len(lines):
                            stream_url = lines[i].strip()
                            import urllib.parse
                            absolute_url = urllib.parse.urljoin(master_url, stream_url)
                            streams.append((height, absolute_url))
                i += 1

            if not streams:
                return master_url

            # Sort streams by height descending (best first)
            streams.sort(key=lambda s: s[0], reverse=True)

            # Find closest match that is <= target_height (or nearest)
            best_match = None
            for height, url in streams:
                if height == target_height:
                    best_match = url
                    break

            if best_match:
                Logger.info(f"Selected matching stream quality: {target_resolution}")
                return best_match

            # Fallback to nearest resolution if exact match not found
            closest_stream = min(streams, key=lambda s: abs(s[0] - target_height))
            Logger.warning(f"Requested resolution {target_resolution} not found. Falling back to nearest: {closest_stream[0]}p")
            return closest_stream[1]

        except Exception as e:
            Logger.warning(f"Resolution selection failed, falling back to master stream: {e}")
            return master_url

    def resolve_m3u8_url(self, video_url: str, timeout: int = 45, resolution: str = "best") -> Optional[str]:
        """Tries fast API-based resolution first, then falls back to Selenium sniffer."""
        video_id = self._extract_video_id(video_url)
        m3u8_url = None
        if video_id and self.ks:
            Logger.info(f"Attempting fast API-based stream resolution for {video_id}...")
            m3u8_url = self._resolve_via_api(video_id)
            if m3u8_url:
                Logger.success(f"Stream resolved via API!")
        
        if not m3u8_url:
            if video_id and self.ks:
                Logger.warning(f"Fast API resolution failed. Falling back to slow browser sniffer...")
            else:
                Logger.info(f"Stream ID not recognized. Initiating browser sniffer (waiting up to {timeout}s)...")
            m3u8_url = self._resolve_via_sniffer(video_url, timeout)

        if m3u8_url:
            return self._select_resolution(m3u8_url, resolution)
        return None
