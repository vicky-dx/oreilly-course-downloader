# O'Reilly Video Course Downloader 🎓

A powerful, high-performance Python CLI tool to download **complete O'Reilly Learning courses** with their videos and transcripts, automatically organizing them by chapters. 

> **Important Architecture Update:** This project has been entirely rewritten into a modern Python package managed by **[`uv`](https://docs.astral.sh/uv/)**. It's now faster, perfectly cleanly containerized, and much easier to install on any OS.

## ✨ Features

- **📚 Complete Course Downloads**: Extract entire courses with all modules and lessons hierarchically intact.
- **🎥 Video Downloads**: High-quality video downloads via HLS/m3u8 raw streams using `ffmpeg`.
- **📝 Native Transcripts**: Extracts actual text-based video transcripts perfectly formatted with timestamps.
- **⚡ Transcripts-Only Mode**: Bypass video downloads entirely. Skips video streams and extracts just the text (~10x faster, zero storage weight).
- **🗂️ Smart Organization**: Automatically structures output folders by `Module -> Lesson -> Videos`.
- **🔐 Captcha-Resistant "Manual Login"**: Keep getting blocked? Pop open a Stealth browser, log in yourself manually once, and let the scraper use your saved session forever.
- **💾 Persistent Profiles**: Saves your authenticated sessions seamlessly in the background.

---

## 🚀 Quick Start

### 1. Requirements

1. **[`uv`](https://docs.astral.sh/uv/getting-started/installation/)**: The insanely fast Python package manager.
2. **`ffmpeg`**: Required to stitch together the video streams.
3. [Firefox Browser](https://www.firefox.com/)

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

#### Option A: One-Shot Download (If you don't have captchas)
```bash
uv run oreilly-dl "https://learning.oreilly.com/course/your-course-url/12345/" \
  --email "your_email@domain.com" \
  --password "your_password"
```

#### Option B: Transcripts Only (Lightning Fast)
Don't want gigabytes of video? Just grab the text files:
```bash
uv run oreilly-dl "https://learning.oreilly.com/course/your-course-url/12345/" \
  --email "your_email@domain.com" \
  --password "your_password" \
  --transcripts-only
```

#### Option C: Manual Login (Bypass Captchas 🛡️)
If O'Reilly blocks the automated bot login, just use `--manual-login`. It will open a visible UI, wait for you to log yourself in, save your session, and close.
```bash
uv run oreilly-dl --manual-login --browser stealth
```
*(Once done, you can run the download commands **without** passing `--email` or `--password`—it will just use your saved session!)*

---

## ⚙️ Advanced Flags & Configuration

Run `uv run oreilly-dl --help` at any time to see all options:

```text
usage: oreilly-dl [-h] [--email EMAIL] [--password PASSWORD] [--transcripts-only]
                  [--manual-login] [--no-headless] [--browser {firefox,chrome,stealth}]
                  [url]

positional arguments:
  url                   URL of the course to download (optional if using --manual-login)

options:
  --transcripts-only    Only download text transcripts. Skip video `m3u8` downloading.
  --manual-login        Launch an interactive browser to log in and save profile, then exit.
  --no-headless         Run browser in a visible window (great for debugging).
  --browser {firefox,chrome,stealth}
                        Set the browser engine (default: firefox). `stealth` is recommended for heavy anti-bot evasion.
```

---

## 📁 Output Structure

The downloader automatically builds a pristine folder hierarchy matching O'Reilly's exact curriculum:

```text
oreilly-downloader/
├── downloads/
│   └── AWS Certified Solutions Architect/
│       ├── course_structure.json
│       ├── 01 - Cloud Concepts/
│       │   └── 01 - What is Cloud Computing/
│       │       ├── 01 - Video Intro.mp4
│       │       └── 01 - Video Intro_transcript.txt
│       └── ...
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
