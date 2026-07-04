# O'Reilly Downloader (Video & Audiobook) 🎓

A powerful, high-performance Python CLI tool to download **complete O'Reilly Learning courses and audiobooks** with their videos, audio chapters, and transcripts, automatically organizing them by modules. 

> **Important Architecture Update:** This project has been entirely rewritten into a modern Python package managed by **[`uv`](https://docs.astral.sh/uv/)**. It's now faster, perfectly cleanly containerized, and much easier to install on any OS.
## ✨ Features

- **⚡ Fast API-Based Resolving**: Uses direct Kaltura and O'Reilly APIs to resolve video streams and transcripts instantly. Does not navigate browser tabs or load players unless the API calls fail (falling back to Selenium sniffer).
- **📚 Complete Course Downloads**: Extract entire courses with all modules and lessons hierarchically intact.
- **🎥 Video Downloads**: High-quality video downloads via HLS/m3u8 raw streams using `ffmpeg`.
- **🎧 Audiobook Downloads**: Native audiobook and audio course downloads saved in high-quality `.m4a` format.
- **🏛️ Central Offline Library Dashboard**: Automatically compiles a beautiful local dashboard (`index.html`) containing all downloaded courses/audiobooks with search indexing, reading progress tracking, custom tags overriding, and keyboard navigation.
- **📝 Native Transcripts**: Extracts actual text-based video transcripts parsed directly from the O'Reilly API, saving them as timestamps.
- **⚡ Transcripts-Only Mode**: Bypass video downloads entirely. Skips video streams and extracts just the text (~100x faster, zero storage weight).
- **🗂️ Smart Organization**: Structures output folders logically. If there are no custom sub-lessons, videos are saved directly inside their parent Chapter directories.
- **🔐 Captcha-Resistant "Manual Login"**: Keep getting blocked? Pop open a Stealth browser, log in yourself manually once, and let the scraper use your saved session forever.
- **💾 Persistent Profiles**: Saves your authenticated sessions seamlessly in the background.
- **📈 Bar Recycler**: Uses a thread-safe active position manager to recycle tqdm slots, preventing terminal outputs from drifting.
- **☠️ Dead Letter Queue (DLQ)**: Automatically logs failed resolutions or downloads to `failed_downloads.json` inside the course folder.
- **📝 Diagnostic Logging**: Supports a `--debug` option that saves clean, console-styled tracebacks and execution flow to `downloader.log`.

---

## 🚀 Quick Start

### 1. Requirements

1. **[`uv`](https://docs.astral.sh/uv/getting-started/installation/)**: The insanely fast Python package manager.
2. **`ffmpeg`**: Required to stitch together the video streams. (The tool will perform a pre-flight scan on startup to make sure it's available).

**Install `uv` (Official Standalone Installer):**
```bash
# macOS and Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**Install `ffmpeg`:**
```bash
# Windows
choco install ffmpeg   

# macOS
brew install ffmpeg  

# Linux
sudo apt install ffmpeg 
```

---

### 2. Usage

Because the project is managed by `uv`, you don't need to manually create virtual environments or install `requirements.txt`. Simply clone the project and run the CLI directly:

#### Option A: One-Shot Download
```bash
uv run oreilly-dl "https://learning.oreilly.com/course/your-course-url/12345/" \
  --email "your_email@domain.com" \
  --password "your_password"
```

#### Option B: Transcripts Only (Instant)
```bash
uv run oreilly-dl "https://learning.oreilly.com/course/your-course-url/12345/" \
  --transcripts-only
```

#### Option C: Manual Login (Bypass Captchas 🛡️)
If O'Reilly blocks the automated bot login, just use `--manual-login`. It will open a visible UI, wait for you to log yourself in, save your session, and close.
```bash
uv run oreilly-dl --manual-login
```
*(Once done, you can run the download commands **without** passing `--email` or `--password`—it will just use your saved session!)*

#### Option D: Download Audiobooks 🎧
To download an audiobook, append the `--audiobook` flag. The tool automatically fetches all chapters, skips transcript extraction checks, and saves them as `.m4a` audio files.
```bash
uv run oreilly-dl "https://learning.oreilly.com/videos/designing-distributed-systems/9781663754035/" \
  --audiobook
```

---

## 🏛️ Central Offline Library Dashboard

Every time you run a download command to save a course or audiobook (as shown in the Quick Start options above), the tool automatically resolves, downloads, and links the files inside the `downloads/books/data/` folder.

To browse, search, edit tags, and read all your downloaded books offline, launch the **Central Offline Library Dashboard**. It provides a premium, Apple Books-inspired interface to manage your collections directly.

### Features
- **🗂️ Dynamic Left Sidebar**: Instantly filter collections by Reading Status, Bookmarks, or dynamically calculated subject counts (e.g. `Python (12)`).
- **📝 Category/Tag Override**: Edit category metadata tags on any book directly from the interface. These persist in your local profile database so you can group books your own way.
- **🔍 Fuzzy Search**: Search title, author, publisher, and descriptions instantly.
- **⌨️ Keyboard-Driven UI**: Navigates using Arrow keys, toggles drawer metadata details with `Space`, opens the reading reader in a tab with `Enter`, and shows keyboard guide with `?`.
- **🌓 Adaptive Theme Modes**: Smooth transitions between premium Dark and Light theme presets.

### Launching
Simply run the launcher script inside the `downloads/books/` folder:
- **Windows**: Double-click `start_library.bat`
- **macOS/Linux**: Run `./start_library.sh` (or `python serve_library.py`)

This starts a lightweight web server on `http://127.0.0.1:8000` and opens the dashboard directly in your browser.

---

## 🧪 Running Unit Tests

The codebase includes a fully mocked testing suite suitable for CI/CD environments (runs without hitting live endpoints or spinning up real browsers). Run them using:

```bash
uv run pytest
```

---

## ⚙️ Advanced Flags & Configuration

Run `uv run oreilly-dl --help` at any time to see all options:

```text
usage: oreilly-dl [-h] [--on24-vtt ON24_VTT] [--event-name EVENT_NAME] [--email EMAIL] [--password PASSWORD]
                  [--transcripts-only] [--audiobook] [--epub] [--web-viewer] [--manual-login] [--no-headless]
                  [--browser {firefox,chrome,stealth}] [--output-dir OUTPUT_DIR] [--workers WORKERS] [--debug]
                  [url]

O'Reilly Course (Video/Audio) Downloader

positional arguments:
  url                   URL of the course or audiobook

options:
  -h, --help            show this help message and exit
  --on24-vtt ON24_VTT   Direct URL to an ON24 VTT subtitle file to extract a live-event transcript.
  --event-name EVENT_NAME
                        Name of the event to save the transcript under.
  --email EMAIL         Login email
  --password PASSWORD   Login password
  --transcripts-only    Only download text transcripts. Skip media m3u8 downloading.
  --audiobook           Download O'Reilly audiobooks (saves files as .m4a and handles audiobook page layout).
  --epub                Download O'Reilly books as EPUB files.
  --web-viewer          Generate an interactive, responsive local web reader application for offline viewing.
  --manual-login
  --no-headless
  --browser {firefox,chrome,stealth}
  --output-dir OUTPUT_DIR
                        Directory to save downloaded files
  --workers WORKERS     Max parallel media downloads
  --debug               Enable file logging to downloader.log
```

---

## 📁 Output Structure

The downloader automatically categorizes and organizes your files into subdirectories under the `downloads/` directory:

```text
oreilly-downloader/
├── downloads/
│   ├── books/
│   │   ├── index.html               # Central Library Dashboard
│   │   ├── serve_library.py         # Library server
│   │   └── data/
│   │       └── Learning Spark/      # Extracted book assets
│   │           ├── book/
│   │           └── Learning Spark.epub
│   │
│   ├── courses/                     # Video & Audio Course downloads
│   │   └── AWS Solutions Architect/
│   │       ├── course_structure.json
│   │       ├── failed_downloads.json
│   │       ├── 01 - Cloud Concepts/
│   │       │   ├── 01 - Video Intro.mp4
│   │       │   └── 01 - Video Intro_transcript.txt
│   │       └── ...
│   │
│   └── audiobooks/                  # Audiobook downloads (.m4a files)
│       └── Designing Distributed Systems/
```

---

## 🔧 Troubleshooting

**"Authentication Failed" or stuck on Captcha?**
Use `--manual-login` to authenticate yourself safely in a real window:
```bash
uv run oreilly-dl --manual-login --browser stealth
```

**"ImportError: No module named 'distutils'" on Windows?**
This is resolved natively due to our `uv` setup, but if you bypassed it, make sure standard `setuptools` is in your environment (handled automatically by `uv sync`).

**Video downloads are failing?**
Verify `ffmpeg` is genuinely installed and available in your global system `$PATH`. `ffmpeg -version` should return its version details in your terminal.

**Stuck on an unexpected error or want to report an issue?**
Run the downloader with the `--debug` flag to generate a diagnostics file:
```bash
uv run oreilly-dl "https://learning.oreilly.com/course/..." --debug
```
This intercepts standard console output and writes a clean, timestamped event log along with the full tracebacks of any uncaught exceptions to `downloader.log` in your current working directory. Include this file when opening issues.

---

## ⚠️ Disclaimer

This tool is strictly for **educational purposes and personal offline archiving**. Users are responsible for complying with O'Reilly Media's Terms of Service. Please respect copyright and intellectual property rights.

## 📄 License

MIT License - see the `LICENSE` file for details.

---

## 🎬 ON24 Live Event Transcripts

O'Reilly live training videos are often hosted on the ON24 platform and cannot be downloaded directly. However, you can extract their transcripts standalone:

### Step 1: Find VTT Subtitle URL
1. Open the ON24 video page in your browser
2. Press **F12** to open DevTools -> **Console** tab
3. Copy and paste the script below to find the VTT file URL:
```javascript
// Browser Console Script to Find ON24 VTT Subtitle URL
(function () {
    console.log('🔍 Searching for VTT subtitle files...');
    performance.getEntriesByType('resource').forEach(entry => {
        if (entry.name.includes('.vtt') || entry.name.includes('.srt') ||       
            entry.name.includes('caption') || entry.name.includes('subtitle')) {
            console.log('🎯 Found:', entry.name);
        }
    });
    let originalFetch = window.fetch;
    window.fetch = function (...args) {
        let url = args[0];
        if (typeof url === 'string' && (url.includes('.vtt') || url.includes('.srt') || url.includes('caption'))) {
            console.log('🎯 Subtitle URL:', url);
        }
        return originalFetch.apply(this, args);
    };
    console.log('✓ Monitoring for subtitle files... Play the video if needed.');
})();
```
4. Press **Enter** - it will output the VTT file URL

### Step 2: Download Transcript
Run the main `oreilly-dl` tool using the `--on24-vtt` option and provide an optional name:

```bash
uv run oreilly-dl --on24-vtt "https://event.on24.com/..." --event-name "My Live Event"
```

The transcript will be neatly parsed, stripped of junk tags, and saved as a plain text file inside `downloads/My Live Event/full_transcript.txt`.
