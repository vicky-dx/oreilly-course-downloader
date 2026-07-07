from .browsers import Logger
import time
from typing import Optional
from .selectors import ExtractorSelectors
from .media_resolver import MediaUrlResolver


class CourseStructureScraper:
    def __init__(self, browser):
        if hasattr(browser, "driver") and browser.driver is not None:
            self.browser = browser.driver
        else:
            self.browser = browser
        self.driver = self.browser

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
                if video_url not in self.driver.navigation.url:
                    Logger.info("Navigating to video page for DOM transcript fallback...")
                    self.driver.navigation.to(video_url)
            except Exception:
                pass

        # Wait up to 10 seconds for either the transcript body OR the toggle button to appear
        try:
            self.driver.wait.for_any([
                self.driver.find_element(ExtractorSelectors.TRANSCRIPT_BODY),
                self.driver.find_element(ExtractorSelectors.TRANSCRIPT_TOGGLE)
            ], 10)
        except Exception:
            # If neither appear within 10 seconds, it's likely a video with no transcript
            return None

        transcript_visible = False
        try:
            containers = self.driver.find_elements(ExtractorSelectors.TRANSCRIPT_CONTAINER)
            if containers and containers[0].is_displayed():
                transcript_visible = True
        except Exception:
            pass

        if not transcript_visible:
            try:
                toggle_btn = self.driver.find_element(ExtractorSelectors.TRANSCRIPT_TOGGLE)
                if toggle_btn:
                    self.driver.actions.execute_js(
                        "arguments[0].scrollIntoView({block: 'center'});", toggle_btn
                    )
                    time.sleep(0.5)
                    self.driver.actions.execute_js("arguments[0].click();", toggle_btn)
            except Exception:
                pass

        try:
            # Re-fetch container and body and add an explicit wait for the body
            container = self.driver.wait.for_present(self.driver.find_element(ExtractorSelectors.TRANSCRIPT_CONTAINER), 5)
            body = self.driver.wait.for_present(container.find(ExtractorSelectors.TRANSCRIPT_BODY), 5)

            # Wait for the actual lines (buttons) to render inside the body
            self.driver.wait.for_child_count(body, ExtractorSelectors.BUTTON_GENERIC, 0, 5)

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

            self.driver.actions.set_script_timeout(30)
            transcript = self.driver.actions.execute_async_js(scroll_script)
            return transcript if transcript else None
        except Exception:
            return None

    def extract_course_structure(self, course_url: str, is_audiobook: bool = False):
        self.driver.navigation.to(course_url)
        try:
            # Wait for either accordion summary buttons or standard video links to load
            self.driver.wait.for_any([
                self.driver.find_element(ExtractorSelectors.ACCORDION_SUMMARY),
                self.driver.find_element(ExtractorSelectors.VIDEO_ANCHORS)
            ], 15)
        except Exception:
            pass

        # Scroll to bottom to ensure everything has loaded
        self.driver.actions.execute_js("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)

        # 1. Try modern accordion-based scraper (handles lazy-loading in MUI layout)
        accordion_script = r"""
        const callback = arguments[arguments.length - 1];
        const isAudiobook = arguments[0] === true;
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
                                if (href.includes('/continue/') || href.includes('/start/')) return false;
                                
                                const text = (a.textContent || '').trim().toLowerCase();
                                if (text === 'continue' || text === 'start') return false;
                                
                                if (href.includes('/videos/')) return true;
                                if (href.includes('/library/view/') && href.includes('video')) return true;
                                
                                if (isAudiobook) {
                                    const bookIdMatch = window.location.pathname.match(/\b\d{10,13}\b/);
                                    if (bookIdMatch) {
                                        const bookId = bookIdMatch[0];
                                        const match = href.match(new RegExp(`${bookId}-[a-zA-Z0-9_-]+`));
                                        if (match) return true;
                                    }
                                }
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
                courseStructure;
                callback(courseStructure);
            } catch (err) {
                callback({ error: err.message });
            }
        })();
        """

        try:
            Logger.info("Scanning course structure (handling lazy-loaded accordions)...")
            self.driver.actions.set_script_timeout(60) # Set script timeout high enough for accordion expansion
            structure = self.driver.actions.execute_async_js(accordion_script, is_audiobook)
            if structure and "error" not in structure:
                Logger.success(f" Successfully scraped {len(structure)} chapters using modern scraper.")
                return structure
            elif structure and "error" in structure:
                Logger.error(f" Modern scraper returned error: {structure['error']}. Falling back to legacy scraper.")
        except Exception as e:
            Logger.warning(f" Modern scraper failed: {e}. Falling back to legacy scraper.")

        # 2. Fallback to legacy scraper (expects static list)
        Logger.info("Scanning course structure using legacy fallback...")
        legacy_script = r"""
        const isAudiobook = arguments[0] === true;
        function cleanName(text) {
            let t = text.trim();
            t = t.replace(/Complete$/i, '');
            t = t.replace(/\d+[smh](\s+\d+[sm])?(\s*remaining)?\s*$/i, '');     
            return t.trim();
        }
        
        const bookIdMatch = window.location.pathname.match(/\b\d{10,13}\b/);
        const bookId = bookIdMatch ? bookIdMatch[0] : null;

        const allVideoLinks = Array.from(document.querySelectorAll('a'))
            .filter(link => {
                if(!link.href) return false;
                if(link.href.includes('#')) return false;
                if(link.href.includes('/continue/') || link.href.includes('/start/')) return false;
                
                const text = (link.textContent || '').trim().toLowerCase();
                if (text === 'continue' || text === 'start') return false;
                
                // Match standard videos
                if (link.href.includes('/videos/')) return true;
                if (link.href.includes('/library/view/') && link.href.includes('video')) return true;
                
                // Match bookId-specific patterns
                if (isAudiobook && bookId) {
                    const match = link.href.match(new RegExp(`${bookId}-[a-zA-Z0-9_-]+`));
                    if (match) return true;
                }
                
                return false;
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
        return self.driver.actions.execute_js(legacy_script, is_audiobook)


# For backwards compatibility with other systems importing ExtractorService directly
class ExtractorService(CourseStructureScraper):
    def __init__(self, browser):
        super().__init__(browser)
        self.resolver = MediaUrlResolver(browser)

    def extract_m3u8_url(self, video_url: str, timeout: int = 45) -> Optional[str]:
        return self.resolver.resolve_m3u8_url(video_url, timeout)
