import time
import re
import requests
from typing import Optional
from colorama import init, Fore
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

init(autoreset=True)


class MediaUrlResolver:
    def __init__(self, browser, ks: Optional[str] = None):
        self.browser = browser
        self.driver = browser.driver
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
                for cookie in self.driver.get_cookies():
                    self.session.cookies.set(cookie['name'], cookie['value'])
            except Exception as e:
                print(f"{Fore.YELLOW}  ⚠️ Warning: Could not initialize resolver session cookies: {e}")

    def _extract_video_id(self, video_url: str) -> Optional[str]:
        """Extracts the unique O'Reilly videoclip ID from the URL (e.g. 9781663754035-a00004)."""
        # Matches ISBN followed by a hyphen and chapter code (e.g. 9781663754035-a00004 or 9781663754035-chapter1)
        match = re.search(r'\b(978\d{10})-[a-zA-Z0-9_]+', video_url)
        if match:
            return match.group(0)
        # Fallback to any 10-13 digit number followed by a hyphen and chapter code
        match = re.search(r'\b\d{10,13}-[a-zA-Z0-9_]+', video_url)
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
                    for cookie in self.driver.get_cookies():
                        self.session.cookies.set(cookie['name'], cookie['value'])
                except Exception as e:
                    print(f"{Fore.YELLOW}  ⚠️ Failed to fetch cookies from driver: {e}")

            clip_resp = self.session.get(clip_url, timeout=15)
            
            # Auto-refresh cookies if unauthorized
            if clip_resp.status_code in (401, 403):
                print(f"{Fore.YELLOW}  ⚠️ O'Reilly API unauthorized (status {clip_resp.status_code}). Refreshing cookies...")
                try:
                    self.session.cookies.clear()
                    for cookie in self.driver.get_cookies():
                        self.session.cookies.set(cookie['name'], cookie['value'])
                    clip_resp = self.session.get(clip_url, timeout=15)
                except Exception as e:
                    print(f"{Fore.RED}  ❌ Failed to refresh cookies from driver: {e}")

            if clip_resp.status_code != 200:
                print(f"{Fore.YELLOW}  ⚠️ O'Reilly VideoClip API returned status {clip_resp.status_code}")
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
                    print(Fore.YELLOW + f"  ⚠️ Failed to parse API transcript: {te}")

            entry_id = clip_data.get("kaltura_entry_id")
            if not entry_id:
                print(f"{Fore.YELLOW}  ⚠️ O'Reilly API response missing kaltura_entry_id")
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
                print(f"{Fore.YELLOW}  ⚠️ Kaltura multirequest API returned status {playback_resp.status_code}")
                return None

            playback_data = playback_resp.json()
            context = playback_data[0]
            sources = context.get("sources", [])

            # Find HLS format (applehttp) source
            hls_source = next((s for s in sources if s.get("format") == "applehttp"), None)
            if hls_source and hls_source.get("url"):
                return hls_source.get("url")

            # Fallback to any URL format source
            url_source = next((s for s in sources if s.get("format") == "url"), None)
            if url_source and url_source.get("url"):
                return url_source.get("url")

            print(f"{Fore.YELLOW}  ⚠️ No HLS or URL streams found in Kaltura PlaybackContext")
            return None
        except Exception as e:
            print(f"{Fore.YELLOW}  ⚠️ Direct API resolution failed: {e}")
            return None

    def _resolve_via_sniffer(self, video_url: str, timeout: int = 45) -> Optional[str]:
        """Resolves the .m3u8 stream URL using the Selenium network sniffer fallback."""
        try:
            # Clear performance entries before navigating
            try:
                self.driver.execute_script("performance.clearResourceTimings();")
            except:
                pass

            self.driver.get(video_url)
            WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )

            script = """
            return window.performance.getEntriesByType("resource")
                .map(e => e.name)
                .filter(name => name.includes('.m3u8'));
            """
            urls = set()
            start_time = time.time()
            while time.time() - start_time < timeout:
                main_links = self.driver.execute_script(script)
                if main_links:
                    for link in main_links:
                        urls.add(link)
                iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
                for iframe in iframes:
                    try:
                        self.driver.switch_to.frame(iframe)
                        iframe_links = self.driver.execute_script(script)
                        if iframe_links:
                            for link in iframe_links:
                                urls.add(link)
                    except:
                        pass
                    finally:
                        self.driver.switch_to.default_content()
                if urls:
                    url_list = list(urls)
                    return url_list[0]
                time.sleep(2)
            return None
        except Exception as e:
            print(f"{Fore.RED}  ❌ Sniffer fallback failed: {e}")
            return None

    def resolve_m3u8_url(self, video_url: str, timeout: int = 45) -> Optional[str]:
        """Tries fast API-based resolution first, then falls back to Selenium sniffer."""
        video_id = self._extract_video_id(video_url)
        if video_id and self.ks:
            print(f"{Fore.CYAN}  ⚡ Attempting fast API-based stream resolution for {video_id}...")
            m3u8_url = self._resolve_via_api(video_id)
            if m3u8_url:
                print(f"{Fore.GREEN}  ✅ Stream resolved via API!")
                return m3u8_url
            print(f"{Fore.YELLOW}  ⚠️ Fast API resolution failed. Falling back to slow browser sniffer...")

        return self._resolve_via_sniffer(video_url, timeout)


class CourseStructureScraper:
    def __init__(self, browser):
        self.browser = browser
        self.driver = browser.driver

    def extract_transcript(self, video_url: Optional[str] = None, resolver: Optional[MediaUrlResolver] = None) -> Optional[str]:
        if video_url and resolver:
            video_id = resolver._extract_video_id(video_url)
            if video_id:
                # 1. Check cached transcripts from resolving phase
                if video_id in resolver.cached_transcripts:
                    return resolver.cached_transcripts[video_id]
                
                # 2. Try fetching dynamically via the fast O'Reilly API
                if resolver.ks:
                    resolver._resolve_via_api(video_id)
                    if video_id in resolver.cached_transcripts:
                        return resolver.cached_transcripts[video_id]

        # 3. Fallback to slow DOM scraping
        # If we have a video_url and driver is not currently on it, navigate first
        if video_url and self.driver:
            try:
                if video_url not in self.driver.current_url:
                    print(Fore.CYAN + "  ⏳ Navigating to video page for DOM transcript fallback...")
                    self.driver.get(video_url)
            except Exception:
                pass

        # Wait up to 10 seconds for either the transcript body OR the toggle button to appear
        try:
            WebDriverWait(self.driver, 10).until(
                lambda d: d.find_elements(
                    By.CSS_SELECTOR, "div[data-testid='transcript-body']"
                )
                or d.find_elements(
                    By.CSS_SELECTOR, "button[data-testid='transcript-toggle']"
                )
            )
        except TimeoutException:
            # If neither appear within 10 seconds, it's likely a video with no transcript
            return None

        transcript_visible = False
        try:
            containers = self.driver.find_elements(
                By.CSS_SELECTOR, "div[data-testid='transcript']"
            )
            if containers and containers[0].is_displayed():
                transcript_visible = True
        except:
            pass

        if not transcript_visible:
            try:
                toggle_btn = self.driver.find_element(
                    By.CSS_SELECTOR, "button[data-testid='transcript-toggle']"
                )
                if toggle_btn:
                    self.driver.execute_script(
                        "arguments[0].scrollIntoView({block: 'center'});", toggle_btn
                    )
                    time.sleep(0.5)
                    self.driver.execute_script("arguments[0].click();", toggle_btn)
            except Exception:
                pass

        try:
            # Re-fetch container and body and add an explicit wait for the body
            container = WebDriverWait(self.driver, 5).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "div[data-testid='transcript']")
                )
            )
            body = WebDriverWait(container, 5).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "div[data-testid='transcript-body']")
                )
            )

            # Wait for the actual lines to render inside the body
            WebDriverWait(body, 5).until(
                lambda b: len(b.find_elements(By.CSS_SELECTOR, "button")) > 0
            )

            # Asynchronously scroll and scrape the virtualized DOM transcript list
            scroll_script = r"""
            const callback = arguments[arguments.length - 1];
            (async () => {
                try {
                    const body = document.querySelector("div[data-testid='transcript-body']");
                    if (!body) {
                        callback(null);
                        return;
                    }

                    const linesMap = new Map();
                    let lastScrollTop = -1;
                    let scrollAttempts = 0;
                    
                    while (scrollAttempts < 100) {
                        const buttons = Array.from(body.querySelectorAll("button"));
                        buttons.forEach(btn => {
                            const pTags = btn.querySelectorAll("p");
                            if (pTags.length >= 2) {
                                const timestamp = pTags[0].textContent.trim();
                                const text = pTags[1].textContent.trim();
                                if (timestamp && text) {
                                    linesMap.set(timestamp, text);
                                }
                            }
                        });

                        lastScrollTop = body.scrollTop;
                        body.scrollTop += 350;
                        await new Promise(r => setTimeout(r, 120));

                        if (body.scrollTop === lastScrollTop) {
                            await new Promise(r => setTimeout(r, 300));
                            if (body.scrollTop === lastScrollTop) {
                                break;
                            }
                        }
                        scrollAttempts++;
                    }

                    const sortedLines = Array.from(linesMap.entries())
                        .map(([ts, text]) => `[${ts}] ${text}`);
                        
                    callback(sortedLines.join("\n\n"));
                } catch (err) {
                    callback(null);
                }
            })();
            """

            self.driver.set_script_timeout(30)
            transcript = self.driver.execute_async_script(scroll_script)
            return transcript if transcript else None
        except Exception:
            return None

    def extract_course_structure(self, course_url: str):
        self.driver.get(course_url)
        try:
            # Wait for either accordion summary buttons or standard video links to load
            WebDriverWait(self.driver, 15).until(
                lambda d: d.find_elements(By.CSS_SELECTOR, "button.MuiAccordionSummary-root")
                or d.find_elements(By.CSS_SELECTOR, "a[href*='/videos/']")
            )
        except TimeoutException:
            pass

        # Scroll to bottom to ensure everything has loaded
        self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)

        # 1. Try modern accordion-based scraper (handles lazy-loading in MUI layout)
        accordion_script = r"""
        const callback = arguments[arguments.length - 1];
        (async () => {
            try {
                const headers = Array.from(document.querySelectorAll('button.MuiAccordionSummary-root'));
                if (headers.length === 0) {
                    callback(null);
                    return;
                }

                const courseStructure = {};

                for (let i = 0; i < headers.length; i++) {
                    const header = headers[i];
                    let moduleTitle = "";
                    const heading = header.querySelector('h3, h4, h5, h2');
                    if (heading) {
                        moduleTitle = heading.textContent.trim();
                    } else {
                        moduleTitle = (header.textContent || "").trim();
                    }
                    moduleTitle = moduleTitle.split('\n')[0].trim();
                    if (!moduleTitle) {
                        moduleTitle = `Chapter ${i + 1}`;
                    }
                    
                    // Click to expand if not already expanded
                    if (header.getAttribute('aria-expanded') !== 'true' && !header.classList.contains('Mui-expanded')) {
                        header.click();
                        await new Promise(r => setTimeout(r, 450));
                    }

                    // Find panel
                    const controlsId = header.getAttribute('aria-controls');
                    let panel = null;
                    if (controlsId) {
                        panel = document.getElementById(controlsId);
                    }
                    if (!panel) {
                        panel = header.nextElementSibling || header.parentElement.querySelector('[role="region"]');
                    }

                    if (panel) {
                        const links = Array.from(panel.querySelectorAll('a'))
                            .filter(a => {
                                const href = a.getAttribute('href') || '';
                                if (href.includes('/videos/') && !href.includes('/continue/') && !href.includes('/start/')) return true;
                                if (href.includes('/library/view/') && href.includes('video')) return true;
                                return false;
                            });

                        const videos = links.map(link => {
                            let titleText = link.textContent || "";
                            let title = titleText.trim()
                                .replace(/Complete$/i, '')
                                .replace(/\d+[smh](\s+\d+[sm])?(\s*remaining)?\s*$/i, '')
                                .trim();
                            return { title: title, url: link.href };
                        }).filter(v => v.title && v.url);

                        if (videos.length > 0) {
                            courseStructure[moduleTitle] = { "Videos": videos };
                        }
                    }
                }
                callback(courseStructure);
            } catch (err) {
                callback({ error: err.message });
            }
        })();
        """

        try:
            print(Fore.CYAN + "🔍 Scanning course structure (handling lazy-loaded accordions)...")
            self.driver.set_script_timeout(60) # Set script timeout high enough for accordion expansion
            structure = self.driver.execute_async_script(accordion_script)
            if structure and "error" not in structure:
                print(Fore.GREEN + f"✅ Successfully scraped {len(structure)} chapters using modern scraper.")
                return structure
            elif structure and "error" in structure:
                print(Fore.YELLOW + f"⚠️ Modern scraper returned error: {structure['error']}. Falling back to legacy scraper.")
        except Exception as e:
            print(Fore.YELLOW + f"⚠️ Modern scraper failed: {e}. Falling back to legacy scraper.")

        # 2. Fallback to legacy scraper (expects static list)
        print(Fore.CYAN + "🔍 Scanning course structure using legacy fallback...")
        legacy_script = r"""
        function cleanName(text) {
            let t = text.trim();
            t = t.replace(/Complete$/i, '');
            t = t.replace(/\d+[smh](\s+\d+[sm])?(\s*remaining)?\s*$/i, '');     
            return t.trim();
        }
        
        const courseRegex = /(\/videos\/|\/library\/view\/.*\/video|\/course\/.*\/(start|continue)\/)/i;
        
        const allVideoLinks = Array.from(document.querySelectorAll('a'))
            .filter(link => {
                if(!link.href) return false;
                if(link.href.includes('/library/view/') && !link.href.includes('video')) return false;
                if(link.href.includes('#')) return false;
                
                return courseRegex.test(link.href);
            });
            
        const courseStructure = {};
        let currentModule = "Module Content";
        let currentLesson = "Introduction";
        allVideoLinks.forEach(link => {
            const url = link.href;
            const title = cleanName(link.textContent || "");
            let tempParent = link.parentElement;
            let moduleFound = false, lessonFound = false;
            for (let i = 0; i < 10 && tempParent; i++) {
                const prevElems = Array.from(tempParent.parentElement?.children || []);
                const currIdx = prevElems.indexOf(tempParent);
                for (let j = currIdx - 1; j >= 0; j--) {
                    const heading = prevElems[j].querySelector('h2, h3, h4, h5') || (prevElems[j].tagName.match(/H[2-5]/) ? prevElems[j] : null);
                    if (heading) {
                        const ht = cleanName(heading.textContent || "");        
                        if (ht.toLowerCase().includes('module') && !moduleFound) { 
                            if (currentModule !== ht) {
                                currentModule = ht;
                                currentLesson = "Introduction";
                            }
                            moduleFound = true; 
                        }
                        else if (ht.toLowerCase().includes('lesson') && !lessonFound) { 
                            currentLesson = ht; 
                            lessonFound = true; 
                        }
                    }
                }
                tempParent = tempParent.parentElement;
            }
            if (!courseStructure[currentModule]) courseStructure[currentModule] = {};
            if (!courseStructure[currentModule][currentLesson]) courseStructure[currentModule][currentLesson] = [];
            courseStructure[currentModule][currentLesson].push({title: title, url: url});
        });
        return courseStructure;
        """
        return self.driver.execute_script(legacy_script)


# For backwards compatibility with other systems importing ExtractorService directly
class ExtractorService(CourseStructureScraper):
    def __init__(self, browser):
        super().__init__(browser)
        self.resolver = MediaUrlResolver(browser)

    def extract_m3u8_url(self, video_url: str, timeout: int = 45) -> Optional[str]:
        return self.resolver.resolve_m3u8_url(video_url, timeout)
