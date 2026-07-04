# O'Reilly Downloader templates definition

FONT_FACES_TEMPLATE = """@font-face {
  font-family: 'DejaVuSans';
  font-weight: bold;
  font-style: normal;
  src: url('DejaVuSans-Bold.otf');
}
@font-face {
  font-family: 'DejaVuSerif';
  font-weight: normal;
  font-style: normal;
  src: url('DejaVuSerif.otf');
}
@font-face {
  font-family: 'Ubuntu Mono';
  font-weight: normal;
  font-style: normal;
  src: url('UbuntuMono-Regular.otf');
}
@font-face {
  font-family: 'Ubuntu Mono';
  font-weight: bold;
  font-style: normal;
  src: url('UbuntuMono-Bold.otf');
}
@font-face {
  font-family: 'Ubuntu Mono';
  font-weight: normal;
  font-style: italic;
  src: url('UbuntuMono-Italic.otf');
}
@font-face {
  font-family: 'Ubuntu Mono';
  font-weight: bold;
  font-style: italic;
  src: url('UbuntuMono-BoldItalic.otf');
}
@font-face {
  font-family: 'Ubuntu Mono BoldItal';
  font-weight: bold;
  font-style: italic;
  src: url('UbuntuMono-BoldItalic.otf');
}
"""

FORMATTING_OVERRIDES = """
/* Beautiful Code Block Styling */
.orm-ChapterReader-codeSnippetContainer,
pre[data-type="programlisting"],
pre {
  background-color: #f6f8fa !important;
  border: 1px solid #e1e4e8 !important;
  border-radius: 6px !important;
  padding: 12px 16px !important;
  margin: 20px 0 !important;
  font-family: "Ubuntu Mono", monospace !important;
  font-size: 0.85em !important;
  line-height: 1.45 !important;
  display: block !important;
  overflow-x: auto !important;
  white-space: pre-wrap !important;
  word-break: break-all !important;
}

/* Beautiful Figure & Image Centering Override */
#book-content #sbo-rt-content figure,
#book-content #sbo-rt-content .figure {
  text-align: center !important;
  margin: 24px auto !important;
  display: block !important;
  border: none !important;
  padding: 0 !important;
}
#book-content #sbo-rt-content figure img {
  display: block !important;
  margin: 0 auto 8px auto !important;
  max-width: 100% !important;
  height: auto !important;
}
#book-content #sbo-rt-content .figure h6,
#book-content #sbo-rt-content figcaption,
#book-content #sbo-rt-content .figure_legend h6 {
  text-align: center !important;
  font-family: "Noto serif", serif !important;
  font-size: 0.750em !important;
  font-weight: bold !important;
  margin-top: 8px !important;
  display: block !important;
  line-height: 1.25 !important;
}
"""

SERVE_PY_TEMPLATE = """import http.server
import json
import os
import sys
import socket
import webbrowser
import threading
import urllib.request

class OReillyRequestHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/book_path":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            path_data = {"path": os.path.abspath(".")}
            self.wfile.write(json.dumps(path_data).encode('utf-8'))
            return
        elif self.path == "/book/notes.json":
            target_path = os.path.join("book", "notes.json")
            if not os.path.exists(target_path):
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(b"[]")
                return
        super().do_GET()

    def do_POST(self):
        if self.path == "/book/notes.json":
            try:
                content_length = int(self.headers.get('Content-Length', 0))
                if content_length > 0:
                    post_data = self.rfile.read(content_length)
                    data = json.loads(post_data.decode('utf-8'))
                    
                    target_path = os.path.join("book", "notes.json")
                    with open(target_path, "w", encoding="utf-8") as f:
                        json.dump(data, f, indent=2)
                        
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(b'{"status":"success"}')
                    return
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(str(e).encode('utf-8'))
                return
        self.send_response(400)
        self.end_headers()
        self.wfile.write(b'{"status":"error","message":"Invalid endpoint"}')

def check_existing_server(port, current_path):
    try:
        url = f"http://127.0.0.1:{port}/api/book_path"
        req = urllib.request.Request(url)
        # Disable proxy handlers for direct local connection to avoid hangs
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(req, timeout=0.5) as response:
            if response.status == 200:
                data = json.loads(response.read().decode('utf-8'))
                return data.get("path") == current_path
    except Exception:
        pass
    return False

if __name__ == "__main__":
    # Always serve from the directory containing this script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    current_path = os.path.abspath(".")

    port = None
    existing_port = None

    for p in range(8000, 8021):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(('127.0.0.1', p))
            s.close()
            port = p
            break
        except socket.error:
            if check_existing_server(p, current_path):
                existing_port = p
                break

    if existing_port:
        url = f"http://127.0.0.1:{existing_port}/book/index.html"
        print(f"ℹ️ Book reader server is already running for this book on port {existing_port}.")
        print("🔗 Opening reader page in browser...")
        webbrowser.open(url)
        sys.exit(0)

    if not port:
        print("❌ Error: Could not find any free port between 8000 and 8020 to start the server.")
        sys.exit(1)

    server_address = ('127.0.0.1', port)
    httpd = http.server.HTTPServer(server_address, OReillyRequestHandler)
    
    url = f"http://127.0.0.1:{port}/book/index.html"
    print(f"🚀 Starting O'Reilly Offline Reader Server on {url}")
    print("Press Ctrl+C inside this window to stop the server.")

    # Auto-open browser tab
    def open_browser():
        webbrowser.open(url)
    threading.Timer(0.5, open_browser).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\\n👋 Stopping reader server. Goodbye!")
"""

BAT_LAUNCHER_TEMPLATE = """@echo off
echo 🚀 Starting local offline book reader...
python serve.py
"""

SH_LAUNCHER_TEMPLATE = """#!/bin/bash
echo "🚀 Starting local offline book reader..."
python3 serve.py
"""


WEB_VIEWER_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Offline Book Reader</title>
  <!-- Load standard O'Reilly typography fonts from Google Fonts and CDN for OpenDyslexic -->
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Noto+Serif:ital,wght@0,400;0,700;1,400;1,700&family=Open+Sans:ital,wght@0,400;0,600;0,700;1,400&family=Ubuntu+Mono:ital,wght@0,400;0,700;1,400;1,700&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/open-dyslexic@1.0.3/open-dyslexic.min.css">
  <link rel="stylesheet" href="orm-icons.css">
  
  <style>
    :root {
      --bg-color: #ffffff;
      --text-color: #222222;
      --sidebar-bg: #f7f9fa;
      --sidebar-border: #e1e4e6;
      --active-link-bg: #e2e8f0;
      --font-size: 18px;
    }
    
    body.theme-sepia {
      --bg-color: #f4ecd8;
      --text-color: #5b4636;
      --sidebar-bg: #eae0c9;
      --sidebar-border: #dcd0b4;
      --active-link-bg: #d0c2a5;
    }
    
    body.ucvMode-black {
      --bg-color: #121212;
      --text-color: #e0e0e0;
      --sidebar-bg: #1e1e1e;
      --sidebar-border: #2d2d2d;
      --active-link-bg: #333333;
    }

    * { box-sizing: border-box; }
    
    /* Base styling rules for ORM font icons */
    [class^="orm-icon-"], [class*=" orm-icon-"] {
      font-family: 'ORM Icons' !important;
      font-style: normal;
      font-weight: normal;
      font-variant: normal;
      text-transform: none;
      line-height: 1;
      display: inline-block;
      vertical-align: middle;
    }
    
    body, html {
      margin: 0; padding: 0;
      width: 100%; height: 100%;
      background-color: var(--bg-color);
      color: var(--text-color);
      transition: background-color 0.2s, color 0.2s;
    }

    /* Font Family Specifiers to override override_v1.css !important tags using CSS specificity */
    #book-content.font-family-serif,
    #book-content.font-family-serif #sbo-rt-content h1,
    #book-content.font-family-serif #sbo-rt-content h2,
    #book-content.font-family-serif #sbo-rt-content h3,
    #book-content.font-family-serif #sbo-rt-content h4,
    #book-content.font-family-serif #sbo-rt-content h5,
    #book-content.font-family-serif #sbo-rt-content h6,
    #book-content.font-family-serif #sbo-rt-content p,
    #book-content.font-family-serif #sbo-rt-content span,
    #book-content.font-family-serif #sbo-rt-content li,
    #book-content.font-family-serif #sbo-rt-content td,
    #book-content.font-family-serif #sbo-rt-content th {
      font-family: "Noto Serif", Georgia, Cambria, serif !important;
    }

    #book-content.font-family-sans,
    #book-content.font-family-sans #sbo-rt-content h1,
    #book-content.font-family-sans #sbo-rt-content h2,
    #book-content.font-family-sans #sbo-rt-content h3,
    #book-content.font-family-sans #sbo-rt-content h4,
    #book-content.font-family-sans #sbo-rt-content h5,
    #book-content.font-family-sans #sbo-rt-content h6,
    #book-content.font-family-sans #sbo-rt-content p,
    #book-content.font-family-sans #sbo-rt-content span,
    #book-content.font-family-sans #sbo-rt-content li,
    #book-content.font-family-sans #sbo-rt-content td,
    #book-content.font-family-sans #sbo-rt-content th {
      font-family: "Open Sans", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important;
    }

    #book-content.font-family-dyslexic,
    #book-content.font-family-dyslexic #sbo-rt-content h1,
    #book-content.font-family-dyslexic #sbo-rt-content h2,
    #book-content.font-family-dyslexic #sbo-rt-content h3,
    #book-content.font-family-dyslexic #sbo-rt-content h4,
    #book-content.font-family-dyslexic #sbo-rt-content h5,
    #book-content.font-family-dyslexic #sbo-rt-content h6,
    #book-content.font-family-dyslexic #sbo-rt-content p,
    #book-content.font-family-dyslexic #sbo-rt-content span,
    #book-content.font-family-dyslexic #sbo-rt-content li,
    #book-content.font-family-dyslexic #sbo-rt-content td,
    #book-content.font-family-dyslexic #sbo-rt-content th {
      font-family: "OpenDyslexic", sans-serif !important;
    }

    #container {
      display: flex;
      width: 100%;
      height: 100%;
      overflow: hidden;
    }

    #main-content {
      flex: 1;
      height: 100%;
      display: flex;
      flex-direction: column;
      overflow-y: auto;
      background-color: var(--bg-color);
    }

    #reader-container {
      max-width: 800px;
      width: 100%;
      margin: 0 auto;
      padding: 40px 20px 100px 20px;
      min-height: 100%;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
    }

    #book-content {
      font-size: inherit;
      line-height: 1.6;
      flex: 1;
    }

    #bottom-bar {
      position: fixed;
      bottom: 0;
      left: 0;
      right: 320px; /* Leaves space for right sidebar */
      height: 60px;
      background-color: var(--bg-color);
      border-top: 1px solid var(--sidebar-border);
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 0 40px;
      font-size: 14px;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      z-index: 10;
      transition: right 0.2s, background-color 0.2s;
    }

    #container.sidebar-hidden #bottom-bar {
      right: 0;
    }

    .nav-arrow {
      background: none;
      border: 1px solid var(--sidebar-border);
      border-radius: 4px;
      color: var(--text-color);
      padding: 8px 16px;
      cursor: pointer;
      font-weight: 500;
      transition: background 0.1s;
    }
    .nav-arrow:hover {
      background-color: var(--active-link-bg);
    }

    #progress-indicator {
      font-weight: 500;
      color: var(--text-color);
      opacity: 0.8;
      display: flex;
      align-items: center;
      gap: 8px;
    }

    #sidebar {
      width: 320px;
      height: 100%;
      border-left: 1px solid var(--sidebar-border);
      background-color: var(--sidebar-bg);
      display: flex;
      flex-direction: column;
      overflow: hidden;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      transition: margin-right 0.2s;
    }

    #sidebar.hidden {
      margin-right: -320px;
    }

    .sidebar-header {
      padding: 20px 20px 10px 20px;
      border-bottom: 1px solid var(--sidebar-border);
    }

    #sidebar-book-title {
      font-weight: 700;
      font-size: 16px;
      line-height: 1.3;
      margin-bottom: 4px;
      color: var(--text-color);
    }

    #sidebar-book-author {
      font-size: 13px;
      opacity: 0.7;
      margin-bottom: 12px;
      color: var(--text-color);
    }

    /* Sidebar Navigation Tabs */
    .sidebar-tabs {
      display: flex;
      border-bottom: 1px solid var(--sidebar-border);
      margin-top: 10px;
    }
    .sidebar-tab {
      flex: 1;
      background: none;
      border: none;
      padding: 8px 0;
      cursor: pointer;
      font-size: 13px;
      font-weight: 600;
      color: var(--text-color);
      opacity: 0.6;
      text-align: center;
      transition: opacity 0.15s, border-bottom 0.15s;
    }
    .sidebar-tab:hover {
      opacity: 1;
    }
    .sidebar-tab.active {
      opacity: 1;
      border-bottom: 2px solid #007a87; /* O'Reilly Teal bottom border */
    }

    #sidebar-tab-content-chapters,
    #sidebar-tab-content-notes {
      flex: 1;
      overflow-y: auto;
    }
    #sidebar-tab-content-notes.hidden {
      display: none;
    }

    .search-wrapper {
      position: relative;
      padding: 10px 15px;
      border-bottom: 1px solid var(--sidebar-border);
      display: flex;
      align-items: center;
      background-color: var(--sidebar-bg);
    }

    #toc-search {
      width: 100%;
      padding: 8px 30px 8px 12px;
      font-size: 13px;
      border: 1px solid var(--sidebar-border);
      border-radius: 4px;
      background-color: var(--bg-color);
      color: var(--text-color);
      outline: none;
      transition: border-color 0.15s;
    }

    #toc-search:focus {
      border-color: #007a87; /* O'Reilly Teal */
    }

    #toc-search-clear {
      position: absolute;
      right: 25px;
      font-size: 18px;
      font-weight: bold;
      cursor: pointer;
      opacity: 0.5;
      user-select: none;
      color: var(--text-color);
    }

    #toc-search-clear:hover {
      opacity: 1;
    }

    #toc-list {
      position: relative;
      border-left: 2px solid #007a87; /* O'Reilly Teal/Green vertical line */
      margin: 15px 15px 15px 25px;
      padding: 0;
    }

    #toc-list ul {
      list-style: none;
      padding: 0;
      margin: 0;
    }

    #toc-list ul.level-2 {
      padding-left: 10px;
    }

    #toc-list ul.level-3 {
      padding-left: 15px;
    }

    #toc-list li {
      margin: 0;
      padding: 0;
    }

    #toc-list li .item-wrapper {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 8px 15px 8px 10px;
      cursor: pointer;
      font-size: 14px;
      line-height: 1.35;
      color: var(--text-color);
      transition: background 0.1s, color 0.1s;
    }

    #toc-list li .item-wrapper:hover {
      background-color: var(--active-link-bg);
    }

    #toc-list li.active > .item-wrapper {
      font-weight: 700;
      background-color: var(--active-link-bg);
      color: #007a87; /* Active text color */
      border-left: 3px solid #d3002d; /* Left Red indicator border */
      padding-left: 7px; /* Compensate border width */
    }

    .chevron {
      font-size: 11px;
      font-weight: bold;
      color: var(--text-color);
      opacity: 0.7;
      margin-left: 10px;
      display: inline-flex;
      align-items: center;
      transition: transform 0.2s;
    }

    #toggle-sidebar {
      background: none;
      border: 1px solid var(--sidebar-border);
      border-radius: 4px;
      color: var(--text-color);
      padding: 8px 12px;
      cursor: pointer;
      font-size: 14px;
    }
    #toggle-sidebar:hover {
      background-color: var(--active-link-bg);
    }

    /* Inline Gear Button inside bottom bar */
    #settings-gear-btn {
      width: 36px;
      height: 36px;
      border-radius: 4px;
      border: 1px solid var(--sidebar-border);
      background-color: #d3002d; /* O'Reilly red */
      color: #ffffff;
      cursor: pointer;
      display: flex;
      justify-content: center;
      align-items: center;
      transition: background 0.15s;
    }
    #settings-gear-btn:hover {
      background-color: #b30025;
    }
    
    /* Settings Popup Panel styling */
    #settings-popup {
      position: fixed;
      bottom: 70px;
      right: 416px; /* 320px sidebar + 96px padding to align with bottom-bar button */
      width: 320px;
      background-color: var(--bg-color);
      border: 1px solid var(--sidebar-border);
      border-radius: 6px;
      box-shadow: 0 4px 16px rgba(0,0,0,0.15);
      padding: 20px;
      z-index: 99;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      transition: right 0.2s, background-color 0.2s, color 0.2s;
    }
    #container.sidebar-hidden #settings-popup {
      right: 96px; /* Shift right when sidebar is hidden */
    }
    #settings-popup.hidden {
      display: none !important;
    }
    
    .popup-arrow {
      position: absolute;
      bottom: -8px;
      right: 12px;
      width: 0;
      height: 0;
      border-left: 8px solid transparent;
      border-right: 8px solid transparent;
      border-top: 8px solid var(--sidebar-border);
    }
    .popup-arrow::after {
      content: '';
      position: absolute;
      top: -9px;
      left: -8px;
      width: 0;
      height: 0;
      border-left: 8px solid transparent;
      border-right: 8px solid transparent;
      border-top: 8px solid var(--bg-color);
    }

    .settings-section {
      margin-bottom: 20px;
    }
    .settings-section:last-child {
      margin-bottom: 0;
    }
    .section-title {
      font-size: 11px;
      font-weight: 700;
      color: var(--text-color);
      opacity: 0.5;
      text-align: center;
      margin-bottom: 12px;
      letter-spacing: 1px;
    }
    .options-row {
      display: flex;
      gap: 10px;
      justify-content: space-between;
    }

    .settings-section + .settings-section {
      border-top: 1px solid var(--sidebar-border);
      padding-top: 16px;
    }

    .option-card {
      flex: 1;
      border: 1px solid var(--sidebar-border);
      border-radius: 4px;
      padding: 10px 5px;
      cursor: pointer;
      text-align: center;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      background-color: var(--bg-color);
      color: var(--text-color);
      transition: border-color 0.15s, box-shadow 0.15s;
    }
    .option-card:hover {
      background-color: var(--sidebar-bg);
      border-color: #a1a4a6;
    }
    .option-card.active {
      border: 1.5px solid #d3002d !important;
      box-shadow: 0 0 0 1px #d3002d;
      background-color: var(--bg-color) !important;
    }

    .card-preview {
      font-weight: bold;
      height: 40px;
      display: flex;
      align-items: center;
      justify-content: center;
      margin-bottom: 5px;
      text-align: center;
    }
    .card-label {
      font-size: 11px;
      font-weight: 500;
      opacity: 0.8;
      text-transform: capitalize;
    }

    /* Color Previews in Popup */
    .color-preview {
      font-size: 8px;
      line-height: 1.1;
      padding: 4px;
      height: 40px;
      border-radius: 2px;
      overflow: hidden;
      font-family: sans-serif;
      font-weight: normal;
    }
    .theme-light .color-preview { background-color: #ffffff; color: #222222; border: 1px solid #e1e4e6; }
    .theme-sepia .color-preview { background-color: #f4ecd8; color: #5b4636; border: 1px solid #dcd0b4; }
    .theme-dark .color-preview { background-color: #2b2b36; color: #e0e0e0; border: 1px solid #333333; }

    /* Width Previews in Popup */
    .width-preview {
      font-size: 18px;
      font-family: monospace;
    }

    /* Font Family Previews in Popup */
    .font-preview { font-size: 20px; }
    .serif-font { font-family: "Noto Serif", Georgia, serif; }
    .sans-font { font-family: "Open Sans", sans-serif; font-weight: normal; }
    .dyslexic-font { font-family: "OpenDyslexic", sans-serif; font-weight: normal; }

    /* Highlights & Note styling */
    .book-highlight {
      cursor: pointer;
      transition: opacity 0.15s;
    }
    .book-highlight:hover {
      opacity: 0.85;
    }
    .book-highlight.yellow { background-color: rgba(255, 213, 79, 0.45); border-bottom: 1.5px solid rgba(255, 213, 79, 0.85); }
    .book-highlight.green { background-color: rgba(165, 214, 167, 0.45); border-bottom: 1.5px solid rgba(165, 214, 167, 0.85); }
    .book-highlight.pink { background-color: rgba(244, 143, 177, 0.45); border-bottom: 1.5px solid rgba(244, 143, 177, 0.85); }
    .book-highlight.blue { background-color: rgba(144, 202, 249, 0.45); border-bottom: 1.5px solid rgba(144, 202, 249, 0.85); }
    
    .book-highlight.has-note::after {
      content: ' 📝';
      font-size: 10px;
      margin-left: 2px;
      cursor: pointer;
      vertical-align: super;
      display: inline-block;
      opacity: 0.8;
    }

    /* Program callout overlap alignment fix */
    #book-content #sbo-rt-content dl.calloutlist dd {
      margin-left: 2.5rem !important;
      padding-left: 0.5rem !important;
    }

    /* Selection Context Menu Tooltip */
    #selection-tooltip {
      position: absolute;
      display: flex;
      align-items: center;
      background-color: #2e2e38;
      border-radius: 4px;
      box-shadow: 0 4px 12px rgba(0,0,0,0.3);
      padding: 0 4px;
      height: 38px;
      z-index: 1000;
      color: #ffffff;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      font-size: 13px;
      transition: opacity 0.1s;
      pointer-events: auto;
    }
    #selection-tooltip::after {
      content: '';
      position: absolute;
      bottom: -6px;
      left: 50%;
      transform: translateX(-50%);
      width: 0; height: 0;
      border-left: 6px solid transparent;
      border-right: 6px solid transparent;
      border-top: 6px solid #2e2e38;
    }

    .tooltip-item {
      display: flex;
      align-items: center;
      justify-content: center;
      height: 100%;
      padding: 0 10px;
      cursor: pointer;
      user-select: none;
      transition: background 0.1s;
    }
    .tooltip-item:hover {
      background-color: #3e3e4a;
    }
    .tooltip-divider {
      width: 1px;
      height: 20px;
      background-color: rgba(255, 255, 255, 0.15);
      align-self: center;
    }

    /* Color picker dropdown inside selection tooltip */
    .color-selector-wrapper {
      position: relative;
      display: flex;
      align-items: center;
      gap: 5px;
      padding: 0 10px;
    }
    .selected-color-dot {
      width: 12px;
      height: 12px;
      border-radius: 50%;
      background-color: #ffd54f;
      display: inline-block;
      box-shadow: inset 0 0 0 1px rgba(0,0,0,0.15);
    }
    .dropdown-arrow {
      font-size: 8px;
      opacity: 0.6;
    }
    .color-dropdown-menu {
      position: absolute;
      bottom: 44px;
      left: 50%;
      transform: translateX(-50%);
      background-color: #2e2e38;
      border-radius: 4px;
      box-shadow: 0 2px 8px rgba(0,0,0,0.3);
      padding: 8px;
      display: flex;
      gap: 8px;
      z-index: 1001;
    }
    .color-dropdown-menu.hidden {
      display: none;
    }
    .color-dot {
      width: 16px;
      height: 16px;
      border-radius: 50%;
      cursor: pointer;
      box-shadow: inset 0 0 0 1px rgba(0,0,0,0.15);
      transition: transform 0.1s;
    }
    .color-dot:hover {
      transform: scale(1.2);
    }

    /* Notes list styling in sidebar */
    .sidebar-note-item {
      padding: 15px 20px;
      border-bottom: 1px solid var(--sidebar-border);
      cursor: pointer;
      transition: background 0.15s;
      position: relative;
    }
    .sidebar-note-item:hover {
      background-color: var(--active-link-bg);
    }
    .sidebar-note-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 6px;
      font-size: 11px;
      font-weight: bold;
      opacity: 0.6;
    }
    .sidebar-note-text {
      font-size: 13px;
      font-style: italic;
      color: var(--text-color);
      opacity: 0.8;
      margin-bottom: 6px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      border-left: 2px solid #ccc;
      padding-left: 6px;
    }
    .sidebar-note-text.yellow { border-color: #ffd54f; }
    .sidebar-note-text.green { border-color: #a5d6a7; }
    .sidebar-note-text.pink { border-color: #f48fb1; }
    .sidebar-note-text.blue { border-color: #90caf9; }

    .sidebar-note-comment {
      font-size: 13px;
      font-weight: 500;
      color: var(--text-color);
    }
    .delete-note-btn {
      background: none;
      border: none;
      color: #c62828;
      cursor: pointer;
      padding: 4px;
      opacity: 0.6;
      transition: opacity 0.1s;
    }
    .delete-note-btn:hover {
      opacity: 1;
    }

    /* Note editor modal styles */
    #note-editor-modal {
      position: fixed;
      top: 0; left: 0; width: 100%; height: 100%;
      background-color: rgba(0,0,0,0.4);
      display: flex;
      justify-content: center;
      align-items: center;
      z-index: 2000;
    }
    #note-editor-modal.hidden {
      display: none;
    }
    .modal-content {
      background-color: var(--bg-color);
      color: var(--text-color);
      border: 1px solid var(--sidebar-border);
      border-radius: 6px;
      box-shadow: 0 4px 20px rgba(0,0,0,0.25);
      width: 400px;
      padding: 20px;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }
    .modal-header {
      font-size: 15px;
      font-weight: bold;
      margin-bottom: 12px;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .modal-close {
      cursor: pointer;
      font-size: 18px;
      opacity: 0.6;
    }
    .modal-close:hover { opacity: 1; }
    .modal-textarea {
      width: 100%;
      height: 90px;
      border: 1px solid var(--sidebar-border);
      border-radius: 4px;
      padding: 10px;
      font-family: inherit;
      font-size: 14px;
      resize: none;
      background-color: var(--sidebar-bg);
      color: var(--text-color);
      margin-bottom: 15px;
    }
    .modal-buttons {
      display: flex;
      justify-content: flex-end;
      gap: 10px;
    }
    .modal-btn {
      padding: 8px 16px;
      border-radius: 4px;
      border: 1px solid var(--sidebar-border);
      background-color: var(--sidebar-bg);
      color: var(--text-color);
      cursor: pointer;
      font-size: 13px;
      font-weight: 500;
    }
    .modal-btn:hover {
      background-color: var(--active-link-bg);
    }
    .modal-btn.primary {
      background-color: #d3002d;
      color: #ffffff;
      border: none;
    }
    .modal-btn.primary:hover {
      background-color: #b30025;
    }
    .modal-btn.danger {
      background-color: #ffebee;
      color: #c62828;
      border: 1px solid #ffcdd2;
    }
    .modal-btn.danger:hover {
      background-color: #ffcdd2;
    }

    /* Note Hover Tooltip */
    #note-hover-tooltip {
      position: absolute;
      background-color: #2e2e38;
      color: #ffffff;
      padding: 8px 12px;
      border-radius: 4px;
      box-shadow: 0 2px 8px rgba(0,0,0,0.3);
      font-size: 13px;
      z-index: 1050;
      max-width: 250px;
      word-wrap: break-word;
      pointer-events: none;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }
    #note-hover-tooltip.hidden {
      display: none;
    }
    .hidden {
      display: none !important;
    }
  </style>
  <!-- Load EPUB CSS directly so our styling rules match -->
  <link rel="stylesheet" href="override_v1.css">
  <link rel="stylesheet" href="epub.css">
</head>
<body>
  <div id="container">
    <div id="main-content">
      <div id="reader-container">
        <!-- Exact ID hierarchy matching O'Reilly stylesheet selectors -->
        <div id="book-content" class="font-family-serif">
          <div style="text-align:center; padding-top: 150px;">
            <h2>Loading book viewer...</h2>
          </div>
        </div>
        
        <!-- Bottom navigation bar -->
        <div id="bottom-bar">
          <button id="prev-btn" class="nav-arrow">◀ Previous</button>
          <div id="progress-indicator">
            <button id="history-back-btn" class="nav-arrow" title="Go back to previous page" style="margin-right: 8px; display: none; align-items: center; justify-content: center; gap: 4px;">
              <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor" style="vertical-align: middle; margin-right: 4px;">
                <path d="M20 11H7.83l5.59-5.59L12 4l-8 8 8 8 1.41-1.41L7.83 13H20v-2z"/>
              </svg>
              Back
            </button>
            <button id="toggle-sidebar">
              <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor" style="vertical-align: middle; margin-right: 6px;">
                <path d="M3 18h18v-2H3v2zm0-5h18v-2H3v2zm0-7v2h18V6H3z"/>
              </svg>
              Chapters
            </button>
            <span id="current-chapter-title">Book Reader</span>
          </div>
          <div style="display:flex; align-items:center; gap:10px;">
            <button id="settings-gear-btn" title="Reader Settings">
              <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor" style="vertical-align: middle;">
                <path d="M19.43 12.98c.04-.32.07-.64.07-.98s-.03-.66-.07-.98l2.11-1.65c.19-.15.24-.42.12-.64l-2-3.46c-.12-.22-.39-.3-.61-.22l-2.49 1c-.52-.4-1.08-.73-1.69-.98l-.38-2.65C14.46 2.18 14.25 2 14 2h-4c-.25 0-.46.18-.49.42l-.38 2.65c-.61.25-1.17.59-1.69.98l-2.49-1c-.23-.09-.49 0-.61.22l-2 3.46c-.13.22-.07.49.12.64l2.11 1.65c-.04.32-.07.65-.07.98s.03.66.07.98l-2.11 1.65c-.19.15-.24.42-.12.64l2 3.46c.12.22.39.3.61.22l2.49-1c.52.4 1.08.73 1.69.98l.38 2.65c.03.24.24.42.49.42h4c.25 0 .46-.18.49-.42l.38-2.65c.61-.25 1.17-.59 1.69-.98l2.49 1c.23.09.49 0 .61-.22l2-3.46c.12-.22.07-.49-.12-.64l-2.11-1.65zM12 15.5c-1.93 0-3.5-1.57-3.5-3.5s1.57-3.5 3.5-3.5 3.5 1.57 3.5 3.5-1.57 3.5-3.5 3.5z"/>
              </svg>
            </button>
            <button id="next-btn" class="nav-arrow">Next ▶</button>
          </div>
        </div>
      </div>
    </div>

    <!-- TOC Sidebar on the Right -->
    <div id="sidebar">
      <div class="sidebar-header">
        <div class="book-info">
          <div id="sidebar-book-title">Loading Book...</div>
          <div id="sidebar-book-author">O'Reilly Offline Reader</div>
        </div>
        <div class="sidebar-tabs">
          <button class="sidebar-tab active" id="tab-chapters">Contents</button>
          <button class="sidebar-tab" id="tab-notes">Highlights</button>
        </div>
      </div>
      
      <!-- Chapters content panel -->
      <div id="sidebar-tab-content-chapters">
        <div class="search-wrapper">
          <input type="text" id="toc-search" placeholder="Search topics..." autocomplete="off">
          <span id="toc-search-clear" class="hidden">&times;</span>
        </div>
        <div id="toc-list"></div>
      </div>

      <!-- Notes content panel -->
      <div id="sidebar-tab-content-notes" class="hidden">
        <div id="notes-list-empty" style="padding: 20px; text-align: center; opacity: 0.6; font-size: 13px;">
          No notes or highlights yet. Select text to highlight it.
        </div>
        <div id="notes-list"></div>
      </div>
    </div>
  </div>

  <!-- Settings Panel Popup (Exactly replicates user layout) -->
  <div id="settings-popup" class="hidden">
    <div class="popup-arrow"></div>
    
    <!-- FONT SIZE -->
    <div class="settings-section">
      <div class="section-title">FONT SIZE</div>
      <div class="options-row">
        <div class="option-card font-size-card" data-size="small" onclick="setFontSize('small')">
          <div class="card-preview" style="font-size: 13px;">Aa</div>
          <div class="card-label">Small</div>
        </div>
        <div class="option-card font-size-card" data-size="medium" onclick="setFontSize('medium')">
          <div class="card-preview" style="font-size: 16px;">Aa</div>
          <div class="card-label">Medium</div>
        </div>
        <div class="option-card font-size-card" data-size="large" onclick="setFontSize('large')">
          <div class="card-preview" style="font-size: 20px;">Aa</div>
          <div class="card-label">Large</div>
        </div>
      </div>
    </div>

    <!-- COLOR MODE -->
    <div class="settings-section">
      <div class="section-title">COLOR MODE</div>
      <div class="options-row">
        <div class="option-card color-card theme-light" onclick="setReaderTheme('light')">
          <div class="card-preview color-preview">Gain tech knowledge learning</div>
          <div class="card-label">Light</div>
        </div>
        <div class="option-card color-card theme-sepia" onclick="setReaderTheme('sepia')">
          <div class="card-preview color-preview">Gain tech knowledge learning</div>
          <div class="card-label">Sepia</div>
        </div>
        <div class="option-card color-card theme-dark" onclick="setReaderTheme('dark')">
          <div class="card-preview color-preview">Gain tech knowledge learning</div>
          <div class="card-label">Dark</div>
        </div>
      </div>
    </div>

    <!-- READER WIDTH -->
    <div class="settings-section">
      <div class="section-title">READER WIDTH</div>
      <div class="options-row">
        <div class="option-card width-card" data-width="small" onclick="setReaderWidth('small')">
          <div class="card-preview width-preview">&gt; ☰ &lt;</div>
          <div class="card-label">Small</div>
        </div>
        <div class="option-card width-card" data-width="medium" onclick="setReaderWidth('medium')">
          <div class="card-preview width-preview">☰</div>
          <div class="card-label">Medium</div>
        </div>
        <div class="option-card width-card" data-width="large" onclick="setReaderWidth('large')">
          <div class="card-preview width-preview">&lt; ☰ &gt;</div>
          <div class="card-label">Large</div>
        </div>
      </div>
    </div>

    <!-- FONT FAMILY -->
    <div class="settings-section">
      <div class="section-title">FONT FAMILY</div>
      <div class="options-row">
        <div class="option-card font-family-card" data-font="serif" onclick="setFontFamily('serif')">
          <div class="card-preview font-preview serif-font">a</div>
          <div class="card-label">Serif</div>
        </div>
        <div class="option-card font-family-card" data-font="sans" onclick="setFontFamily('sans')">
          <div class="card-preview font-preview sans-font">a</div>
          <div class="card-label">Sans-Serif</div>
        </div>
        <div class="option-card font-family-card" data-font="dyslexic" onclick="setFontFamily('dyslexic')">
          <div class="card-preview font-preview dyslexic-font">a</div>
          <div class="card-label">Open Dyslexic</div>
        </div>
      </div>
    </div>
  </div>

  <!-- Floating Selection Tooltip (Matches user screenshot: Yellow | Highlight | Add Note | Copy | Link) -->
  <div id="selection-tooltip" class="hidden">
    <div class="tooltip-item color-selector-wrapper">
      <span class="selected-color-dot" id="current-color-indicator"></span>
      <span class="dropdown-arrow">▼</span>
      <div class="color-dropdown-menu hidden" id="color-picker-menu">
        <span class="color-dot" data-color="yellow" style="background-color: #ffd54f;"></span>
        <span class="color-dot" data-color="green" style="background-color: #a5d6a7;"></span>
        <span class="color-dot" data-color="pink" style="background-color: #f48fb1;"></span>
        <span class="color-dot" data-color="blue" style="background-color: #90caf9;"></span>
      </div>
    </div>
    <div class="tooltip-divider"></div>
    <div class="tooltip-item" id="btn-highlight">Highlight</div>
    <div class="tooltip-divider"></div>
    <div class="tooltip-item" id="btn-add-note">Add Note</div>
    <div class="tooltip-divider"></div>
    <div class="tooltip-item" id="btn-copy">Copy</div>
    <div class="tooltip-divider"></div>
    <div class="tooltip-item" id="btn-link" title="Copy section link">
      <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor" style="vertical-align: middle;">
        <path d="M3.9 12c0-1.71 1.39-3.1 3.1-3.1h4V7H7c-2.76 0-5 2.24-5 5s2.24 5 5 5h4v-1.9H7c-1.71 0-3.1-1.39-3.1-3.1zM8 13h8v-2H8v2zm9-6h-4v1.9h4c1.71 0 3.1 1.39 3.1 3.1s-1.39 3.1-3.1 3.1h-4V17h4c2.76 0 5-2.24 5-5s-2.24-5-5-5z"/>
      </svg>
    </div>
  </div>

  <!-- Note Editor Modal -->
  <div id="note-editor-modal" class="hidden">
    <div class="modal-content">
      <div class="modal-header">
        <span id="modal-title-text">Add Note</span>
        <span class="modal-close" id="btn-modal-close">&times;</span>
      </div>
      <textarea class="modal-textarea" id="note-textarea" placeholder="Type your note here..."></textarea>
      <div class="modal-buttons">
        <button class="modal-btn danger hidden" id="btn-modal-delete">Delete Highlight</button>
        <button class="modal-btn" id="btn-modal-cancel">Cancel</button>
        <button class="modal-btn primary" id="btn-modal-save">Save</button>
      </div>
    </div>
  </div>

  <!-- Note Hover Tooltip -->
  <div id="note-hover-tooltip" class="hidden"></div>

  <!-- Lightbox Modal for Images -->
  <div id="image-lightbox" class="hidden" style="position: fixed; top: 0; left: 0; width: 100%; height: 100%; background-color: rgba(0,0,0,0.85); display: flex; justify-content: center; align-items: center; z-index: 3000; opacity: 0; transition: opacity 0.2s ease;">
    <span id="close-lightbox" style="position: absolute; top: 20px; right: 30px; color: #ffffff; font-size: 35px; font-weight: bold; cursor: pointer; user-select: none;">&times;</span>
    <img id="lightbox-img" src="" alt="Enlarged figure" style="max-width: 90%; max-height: 90%; object-fit: contain; border-radius: 4px; box-shadow: 0 4px 20px rgba(0,0,0,0.5);">
  </div>

  <script>
    let currentChapter = "";
    let flatChapters = [];
    let currentChapterIndex = -1;
    let allNotes = []; // List of all highlights and notes globally
    let selectedColor = "yellow";
    let activeHighlightId = null; // Active highlight being edited in modal
    let tempSelectionRange = null; // Hold range between text selection and note modal input
    let historyStack = [];
    let isScrollingFromClick = false;
    
    // Toggle sidebar visibility
    const sidebar = document.getElementById('sidebar');
    document.getElementById('toggle-sidebar').addEventListener('click', () => {
      sidebar.classList.toggle('hidden');
      document.getElementById('container').classList.toggle('sidebar-hidden');
    });

    // Sidebar Tabs Switcher logic
    document.getElementById('tab-chapters').addEventListener('click', () => {
      document.getElementById('tab-chapters').classList.add('active');
      document.getElementById('tab-notes').classList.remove('active');
      document.getElementById('sidebar-tab-content-chapters').classList.remove('hidden');
      document.getElementById('sidebar-tab-content-notes').classList.add('hidden');
    });

    document.getElementById('tab-notes').addEventListener('click', () => {
      document.getElementById('tab-chapters').classList.remove('active');
      document.getElementById('tab-notes').classList.add('active');
      document.getElementById('sidebar-tab-content-chapters').classList.add('hidden');
      document.getElementById('sidebar-tab-content-notes').classList.remove('hidden');
      updateNotesSidebar();
    });

    // TOC Sidebar Real-time Search/Filter Logic
    const searchInput = document.getElementById('toc-search');
    const searchClear = document.getElementById('toc-search-clear');
    
    searchInput.addEventListener('input', () => {
      const query = searchInput.value.toLowerCase().trim();
      
      if (query === "") {
        searchClear.classList.add('hidden');
        document.querySelectorAll('#toc-list li').forEach(li => {
          li.style.display = '';
        });
        const activeLi = document.querySelector('#toc-list li.active');
        if (activeLi) {
          updateAccordionState(activeLi);
        }
        return;
      }
      
      searchClear.classList.remove('hidden');
      
      // Hide all items and their nested ul folders initially
      const allLis = document.querySelectorAll('#toc-list li');
      allLis.forEach(li => {
        li.style.display = 'none';
        const subUl = li.querySelector('ul');
        if (subUl) subUl.style.display = 'none';
      });
      
      allLis.forEach(li => {
        const span = li.querySelector('.item-wrapper > span');
        if (span && span.textContent.toLowerCase().includes(query)) {
          // Show this matched list item
          li.style.display = '';
          
          // Force matched folders to open
          const subUl = li.querySelector('ul');
          if (subUl) subUl.style.display = 'block';
          
          // Show all parent list items and container ul blocks
          let parent = li.parentElement;
          while (parent && parent.id !== 'toc-list') {
            if (parent.tagName === 'UL') {
              parent.style.display = 'block';
            }
            if (parent.tagName === 'LI') {
              parent.style.display = '';
            }
            parent = parent.parentElement;
          }
        }
      });
    });
    
    searchClear.addEventListener('click', () => {
      searchInput.value = "";
      searchInput.dispatchEvent(new Event('input'));
      searchInput.focus();
    });

    // Settings popup logic
    const gearBtn = document.getElementById('settings-gear-btn');
    const popup = document.getElementById('settings-popup');
    gearBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      popup.classList.toggle('hidden');
    });
    document.addEventListener('click', () => {
      popup.classList.add('hidden');
    });
    popup.addEventListener('click', (e) => {
      e.stopPropagation();
    });

    // History back button trigger
    document.getElementById('history-back-btn').addEventListener('click', () => {
      if (historyStack.length > 0) {
        const prev = historyStack.pop();
        const prevSrc = typeof prev === 'string' ? prev : prev.src;
        const prevScrollTop = typeof prev === 'object' ? prev.scrollTop : 0;
        
        const baseSrc = prevSrc.split('#')[0];
        const li = document.querySelector(`li[data-src="${prevSrc}"]`) || 
                   document.querySelector(`li[data-src^="${baseSrc}"]`);
        loadChapter(prevSrc, li, prevScrollTop);
        
        if (historyStack.length === 0) {
          document.getElementById('history-back-btn').style.display = 'none';
        }
      }
    });

    // Selection tooltip dropdown picker toggle
    const tooltip = document.getElementById('selection-tooltip');
    const colorPickerWrapper = document.querySelector('.color-selector-wrapper');
    const colorMenu = document.getElementById('color-picker-menu');
    colorPickerWrapper.addEventListener('click', (e) => {
      e.stopPropagation();
      colorMenu.classList.toggle('hidden');
    });

    // Color picker options logic
    document.querySelectorAll('.color-dot').forEach(dot => {
      dot.addEventListener('click', (e) => {
        e.stopPropagation();
        selectedColor = dot.dataset.color;
        updateCurrentColorIndicator();
        colorMenu.classList.add('hidden');
      });
    });

    function updateCurrentColorIndicator() {
      const colors = { yellow: '#ffd54f', green: '#a5d6a7', pink: '#f48fb1', blue: '#90caf9' };
      document.getElementById('current-color-indicator').style.backgroundColor = colors[selectedColor];
    }
    updateCurrentColorIndicator();

    // Theme changer
    function setReaderTheme(theme) {
      document.body.className = '';
      if (theme === 'sepia') {
        document.body.classList.add('theme-sepia');
      } else if (theme === 'dark') {
        document.body.classList.add('ucvMode-black'); // Matches O'Reilly .ucvMode-black selector
      }
      
      document.querySelectorAll('.color-card').forEach(c => c.classList.remove('active'));
      const activeCard = document.querySelector(`.color-card.theme-${theme}`);
      if (activeCard) activeCard.classList.add('active');
      
      localStorage.setItem('reader-theme', theme);
    }

    // Font size changer
    function setFontSize(size) {
      const sizes = { small: '1.0em', medium: '1.25em', large: '1.5em' };
      document.getElementById('reader-container').style.fontSize = sizes[size];
      
      document.querySelectorAll('.font-size-card').forEach(c => c.classList.remove('active'));
      const activeCard = document.querySelector(`.font-size-card[data-size="${size}"]`);
      if (activeCard) activeCard.classList.add('active');
      
      localStorage.setItem('reader-fontsize-name', size);
    }

    // Reader width changer
    function setReaderWidth(width) {
      const widths = { small: '50ch', medium: '70ch', large: '90ch' };
      document.getElementById('reader-container').style.maxWidth = widths[width];
      
      document.querySelectorAll('.width-card').forEach(c => c.classList.remove('active'));
      const activeCard = document.querySelector(`.width-card[data-width="${width}"]`);
      if (activeCard) activeCard.classList.add('active');
      
      localStorage.setItem('reader-width-name', width);
    }

    // Font family changer
    function setFontFamily(font) {
      const el = document.getElementById('book-content');
      el.classList.remove('font-family-serif', 'font-family-sans', 'font-family-dyslexic');
      el.classList.add('font-family-' + font);
      
      document.querySelectorAll('.font-family-card').forEach(c => c.classList.remove('active'));
      const activeCard = document.querySelector(`.font-family-card[data-font="${font}"]`);
      if (activeCard) activeCard.classList.add('active');
      
      localStorage.setItem('reader-fontfamily', font);
    }

    // Restore saved settings
    const savedTheme = localStorage.getItem('reader-theme') || 'light';
    setReaderTheme(savedTheme);

    const savedFontSize = localStorage.getItem('reader-fontsize-name') || 'medium';
    setFontSize(savedFontSize);

    const savedWidth = localStorage.getItem('reader-width-name') || 'medium';
    setReaderWidth(savedWidth);

    const savedFontFamily = localStorage.getItem('reader-fontfamily') || 'serif';
    setFontFamily(savedFontFamily);

    // Get ISBN/Book ID from relative location or pathname
    function getBookIsbn() {
      // In web viewer layout, url is in format: /book/index.html.
      // We can fallback or parse title from docTitle
      const title = document.getElementById('sidebar-book-title').innerText || 'default';
      return title.replace(/[^a-zA-Z0-9]/g, '_');
    }

    // Server annotations GET/POST sync functions
    function loadNotesFromServer() {
      return fetch('notes.json')
        .then(r => {
          if (r.ok) return r.json();
          throw new Error("No notes file");
        })
        .then(data => {
          allNotes = Array.isArray(data) ? data : [];
          try {
            applyHighlightsForCurrentChapter();
            updateNotesSidebar();
          } catch (e) {
            console.error("Notes rendering failed:", e);
          }
        })
        .catch(err => {
          // Fallback to localStorage if server file is empty/erroring
          try {
            const key = 'oreilly-notes-' + getBookIsbn();
            const localData = localStorage.getItem(key);
            allNotes = localData ? JSON.parse(localData) : [];
            if (!Array.isArray(allNotes)) allNotes = [];
          } catch (e) {
            console.error("Local storage notes parse failed:", e);
            allNotes = [];
          }
          try {
            applyHighlightsForCurrentChapter();
            updateNotesSidebar();
          } catch (e) {
            console.error("Apply/update notes failed:", e);
          }
        });
    }

    function saveNotesToServer() {
      const key = 'oreilly-notes-' + getBookIsbn();
      localStorage.setItem(key, JSON.stringify(allNotes));
      
      fetch('notes.json', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(allNotes)
      })
      .then(r => {
        if (!r.ok) console.error("Server notes write failed");
      })
      .catch(err => {
        console.error("Failed to write notes to server:", err);
      });
      updateNotesSidebar();
    }

    // Range serialization character offset helpers
    function getCharacterOffset(container, node, offset) {
      let range = document.createRange();
      range.selectNodeContents(container);
      range.setEnd(node, offset);
      return range.toString().length;
    }

    function setRangeByOffsets(container, startOffset, endOffset) {
      let range = document.createRange();
      let charCount = 0;
      let startNode = null;
      let startCharOffset = 0;
      let endNode = null;
      let endCharOffset = 0;
      
      const treeWalker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT, null, false);
      let node;
      while ((node = treeWalker.nextNode())) {
        const len = node.textContent.length;
        if (!startNode && charCount + len >= startOffset) {
          startNode = node;
          startCharOffset = startOffset - charCount;
        }
        if (!endNode && charCount + len >= endOffset) {
          endNode = node;
          endCharOffset = endOffset - charCount;
          break;
        }
        charCount += len;
      }
      
      if (startNode && endNode) {
        try {
          range.setStart(startNode, startCharOffset);
          range.setEnd(endNode, endCharOffset);
          return range;
        } catch (e) {
          console.error("Failed to set range offsets", e);
        }
      }
      return null;
    }

    // Highlights wrapping renderer (handles splitting text nodes correctly)
    function highlightRange(range, colorClass, highlightId) {
      if (!range) return;
      const startContainer = range.startContainer;
      const endContainer = range.endContainer;
      
      // Setup event listeners for the highlights
      const setupHighlightEl = (el) => {
        el.addEventListener('click', (e) => {
          e.stopPropagation();
          openEditModal(highlightId);
        });
        
        // Show tooltip on hover
        el.addEventListener('mouseenter', (e) => {
          const noteObj = allNotes.find(n => n.id === highlightId);
          if (noteObj && noteObj.note) {
            const hoverTooltip = document.getElementById('note-hover-tooltip');
            hoverTooltip.innerText = noteObj.note;
            hoverTooltip.classList.remove('hidden');
            
            // Position above the highlight span
            const rect = el.getBoundingClientRect();
            hoverTooltip.style.left = `${rect.left + window.scrollX + (rect.width/2) - (hoverTooltip.offsetWidth/2)}px`;
            hoverTooltip.style.top = `${rect.top + window.scrollY - hoverTooltip.offsetHeight - 8}px`;
          }
        });
        
        el.addEventListener('mouseleave', () => {
          document.getElementById('note-hover-tooltip').classList.add('hidden');
        });
      };

      if (startContainer === endContainer) {
        const span = document.createElement('span');
        span.className = `book-highlight ${colorClass}`;
        span.dataset.id = highlightId;
        try {
          range.surroundContents(span);
          setupHighlightEl(span);
        } catch (e) {
          // If range spans mismatched tags, wrap outer content
          console.warn("Could not wrap single container cleanly, wrapping inner nodes:", e);
        }
        return;
      }
      
      // Gather all text nodes in range
      const textNodes = [];
      const walker = document.createTreeWalker(
        range.commonAncestorContainer,
        NodeFilter.SHOW_TEXT,
        null,
        false
      );
      
      let insideRange = false;
      let node;
      while ((node = walker.nextNode())) {
        if (node === startContainer) {
          insideRange = true;
        }
        if (insideRange) {
          textNodes.push(node);
        }
        if (node === endContainer) {
          break;
        }
      }
      
      // Wrap each text node range separately
      textNodes.forEach((node) => {
        const nodeRange = document.createRange();
        let start = 0;
        let end = node.textContent.length;
        
        if (node === startContainer) {
          start = range.startOffset;
        }
        if (node === endContainer) {
          end = range.endOffset;
        }
        
        if (start < end) {
          nodeRange.setStart(node, start);
          nodeRange.setEnd(node, end);
          
          const span = document.createElement('span');
          span.className = `book-highlight ${colorClass}`;
          span.dataset.id = highlightId;
          try {
            nodeRange.surroundContents(span);
            setupHighlightEl(span);
          } catch(e) {
            console.warn("Node wrap skipped", e);
          }
        }
      });
    }

    // Apply highlights of current chapter
    function applyHighlightsForCurrentChapter() {
      const wrapper = document.getElementById('book-content');
      if (!wrapper) return;
      
      const chapterNotes = allNotes.filter(n => n && n.chapter === currentChapter);
      chapterNotes.forEach(note => {
        if (!note || typeof note.start !== 'number' || typeof note.end !== 'number') return;
        const range = setRangeByOffsets(wrapper, note.start, note.end);
        if (range) {
          highlightRange(range, note.color || 'yellow', note.id);
          if (note.note) {
            document.querySelectorAll(`span.book-highlight[data-id="${note.id}"]`).forEach(span => {
              span.classList.add('has-note');
            });
          }
        }
      });
    }

    // Selection event handler displaying selection tooltip above text range
    function handleTextSelection() {
      const selection = window.getSelection();
      if (!selection || selection.rangeCount === 0 || selection.isCollapsed || selection.toString().trim() === "") {
        tooltip.classList.add('hidden');
        colorMenu.classList.add('hidden');
        return;
      }
      
      const range = selection.getRangeAt(0);
      
      // Ensure selection is inside #book-content
      const container = document.getElementById('book-content');
      if (!container.contains(range.commonAncestorContainer)) {
        tooltip.classList.add('hidden');
        colorMenu.classList.add('hidden');
        return;
      }
      
      tempSelectionRange = range.cloneRange();
      
      // Calculate selection coordinates to position tooltip bar
      const rect = range.getBoundingClientRect();
      
      // Calculate coordinates with safety bounds to avoid layout shifts or scrollbars jitter
      let left = rect.left + window.scrollX + (rect.width/2) - (tooltip.offsetWidth/2);
      let top = rect.top + window.scrollY - tooltip.offsetHeight - 10;
      
      // Ensure it doesn't push off screen boundaries (causes scrollbar jitter)
      left = Math.max(10, Math.min(left, window.innerWidth - tooltip.offsetWidth - 10));
      top = Math.max(10, top);
      
      tooltip.style.left = `${left}px`;
      tooltip.style.top = `${top}px`;
      tooltip.classList.remove('hidden');
    }

    document.addEventListener('mouseup', () => {
      setTimeout(handleTextSelection, 10);
    });
    
    document.addEventListener('selectionchange', () => {
      // Hide selection bar if selection is collapsed
      const selection = window.getSelection();
      if (!selection || selection.rangeCount === 0 || selection.isCollapsed) {
        tooltip.classList.add('hidden');
        colorMenu.classList.add('hidden');
      }
    });

    // Snappy mousedown trigger to hide selection bar instantly before starting new select drag
    document.addEventListener('mousedown', (e) => {
      if (tooltip && !tooltip.classList.contains('hidden')) {
        // Only hide if the click is outside the tooltip bar and outside the note modal
        if (!tooltip.contains(e.target) && !document.getElementById('note-editor-modal').contains(e.target)) {
          tooltip.classList.add('hidden');
          colorMenu.classList.add('hidden');
        }
      }
    });

    // Tooltip highlight trigger button
    document.getElementById('btn-highlight').addEventListener('click', () => {
      if (!tempSelectionRange) return;
      
      const selectionStr = tempSelectionRange.toString();
      const container = document.getElementById('book-content');
      const start = getCharacterOffset(container, tempSelectionRange.startContainer, tempSelectionRange.startOffset);
      const end = getCharacterOffset(container, tempSelectionRange.endContainer, tempSelectionRange.endOffset);
      
      const newHighlight = {
        id: 'hl_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9),
        chapter: currentChapter,
        start: start,
        end: end,
        text: selectionStr,
        color: selectedColor,
        note: "",
        created: Date.now()
      };
      
      allNotes.push(newHighlight);
      saveNotesToServer();
      applyHighlightsForCurrentChapter();
      
      window.getSelection().removeAllRanges();
      tooltip.classList.add('hidden');
    });

    // Tooltip note editor modal trigger button
    document.getElementById('btn-add-note').addEventListener('click', () => {
      if (!tempSelectionRange) return;
      
      const selectionStr = tempSelectionRange.toString();
      const container = document.getElementById('book-content');
      const start = getCharacterOffset(container, tempSelectionRange.startContainer, tempSelectionRange.startOffset);
      const end = getCharacterOffset(container, tempSelectionRange.endContainer, tempSelectionRange.endOffset);
      
      // Show note editor modal immediately
      activeHighlightId = null;
      document.getElementById('modal-title-text').innerText = "Add Note";
      document.getElementById('note-textarea').value = "";
      document.getElementById('btn-modal-delete').classList.add('hidden');
      document.getElementById('note-editor-modal').classList.remove('hidden');
      
      // Save temporary metrics
      tempSelectionData = {
        chapter: currentChapter,
        start: start,
        end: end,
        text: selectionStr
      };
      
      window.getSelection().removeAllRanges();
      tooltip.classList.add('hidden');
    });

    // Copy selected text to clipboard
    document.getElementById('btn-copy').addEventListener('click', () => {
      if (!tempSelectionRange) return;
      const text = tempSelectionRange.toString();
      navigator.clipboard.writeText(text).then(() => {
        alert("Text copied to clipboard!");
      });
      window.getSelection().removeAllRanges();
      tooltip.classList.add('hidden');
    });

    // Copy page relative reference link
    document.getElementById('btn-link').addEventListener('click', () => {
      // Generate query link e.g. index.html?ch=ch02.html
      const currentLoc = window.location.href.split('?')[0];
      const linkUrl = `${currentLoc}?ch=${encodeURIComponent(currentChapter)}`;
      navigator.clipboard.writeText(linkUrl).then(() => {
        alert("Direct link copied to clipboard:\\n" + linkUrl);
      });
      window.getSelection().removeAllRanges();
      tooltip.classList.add('hidden');
    });

    // Modal buttons actions
    document.getElementById('btn-modal-cancel').addEventListener('click', () => {
      document.getElementById('note-editor-modal').classList.add('hidden');
    });
    document.getElementById('btn-modal-close').addEventListener('click', () => {
      document.getElementById('note-editor-modal').classList.add('hidden');
    });

    document.getElementById('btn-modal-save').addEventListener('click', () => {
      const noteVal = document.getElementById('note-textarea').value.trim();
      
      if (activeHighlightId) {
        // Edit existing highlight/note
        const noteObj = allNotes.find(n => n.id === activeHighlightId);
        if (noteObj) {
          noteObj.note = noteVal;
          // Refresh elements classes
          document.querySelectorAll(`span.book-highlight[data-id="${activeHighlightId}"]`).forEach(span => {
            if (noteVal !== "") {
              span.classList.add('has-note');
            } else {
              span.classList.remove('has-note');
            }
          });
          saveNotesToServer();
        }
      } else if (tempSelectionData) {
        // Create new highlight + note
        const noteId = 'hl_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
        const newHighlight = {
          id: noteId,
          chapter: tempSelectionData.chapter,
          start: tempSelectionData.start,
          end: tempSelectionData.end,
          text: tempSelectionData.text,
          color: selectedColor,
          note: noteVal,
          created: Date.now()
        };
        
        allNotes.push(newHighlight);
        saveNotesToServer();
        applyHighlightsForCurrentChapter();
      }
      
      document.getElementById('note-editor-modal').classList.add('hidden');
    });

    // Delete notes trigger inside modal
    document.getElementById('btn-modal-delete').addEventListener('click', () => {
      if (!activeHighlightId) return;
      
      if (confirm("Are you sure you want to delete this highlight and note?")) {
        // Remove from list
        allNotes = allNotes.filter(n => n.id !== activeHighlightId);
        saveNotesToServer();
        
        // Reload entire chapter content to strip tags cleanly
        const baseSrc = currentChapter.split('#')[0];
        const activeItem = document.querySelector(`li[data-src="${currentChapter}"]`) ||
                           document.querySelector(`li[data-src^="${baseSrc}"]`);
        
        // Bypass current chapter checks by resetting active parameter
        currentChapter = "";
        loadChapter(baseSrc, activeItem);
        
        document.getElementById('note-editor-modal').classList.add('hidden');
      }
    });

    function openEditModal(highlightId) {
      const noteObj = allNotes.find(n => n.id === highlightId);
      if (!noteObj) return;
      
      activeHighlightId = highlightId;
      document.getElementById('modal-title-text').innerText = "Edit Note";
      document.getElementById('note-textarea').value = noteObj.note || "";
      document.getElementById('btn-modal-delete').classList.remove('hidden');
      document.getElementById('note-editor-modal').classList.remove('hidden');
    }

    // Populate Sidebar Notes Aggregation panel
    function updateNotesSidebar() {
      const notesList = document.getElementById('notes-list');
      const notesListEmpty = document.getElementById('notes-list-empty');
      if (!notesList || !notesListEmpty) return;
      
      notesList.innerHTML = "";
      
      if (!allNotes || allNotes.length === 0) {
        notesListEmpty.style.display = 'block';
        return;
      }
      notesListEmpty.style.display = 'none';
      
      // Sort notes by created timestamp
      const validNotes = allNotes.filter(n => n && n.chapter && typeof n.created === 'number');
      const sorted = [...validNotes].sort((a,b) => b.created - a.created);
      
      sorted.forEach(note => {
        const item = document.createElement('div');
        item.className = 'sidebar-note-item';
        
        // Find clean chapter title label from toc list
        const baseCh = note.chapter.split('#')[0];
        const li = document.querySelector(`li[data-src="${note.chapter}"]`) || 
                   document.querySelector(`li[data-src^="${baseCh}"]`);
        const chLabel = li ? li.querySelector('span').textContent : "Chapter";
        
        item.innerHTML = `
          <div class="sidebar-note-header">
            <span>${chLabel}</span>
            <button class="delete-note-btn" title="Delete note">&times;</button>
          </div>
          <div class="sidebar-note-text ${note.color}">"${note.text}"</div>
          <div class="sidebar-note-comment">${note.note ? note.note : '<span style="opacity:0.5; font-style:italic;">No note text</span>'}</div>
        `;
        
        // Clicking note list item navigates to exact chapter and scrolls
        item.addEventListener('click', () => {
          navigateTo(note.chapter);
          
          // Smooth scroll to highlight
          setTimeout(() => {
            const highlightSpans = document.querySelectorAll(`span.book-highlight[data-id="${note.id}"]`);
            if (highlightSpans.length > 0) {
              highlightSpans[0].scrollIntoView({ behavior: 'smooth', block: 'center' });
              
              // Pulsate highlight to catch attention
              highlightSpans.forEach(span => {
                span.style.transition = 'opacity 0.2s';
                span.style.opacity = '0.3';
                setTimeout(() => span.style.opacity = '1', 200);
                setTimeout(() => span.style.opacity = '0.3', 400);
                setTimeout(() => span.style.opacity = '1', 600);
              });
            }
          }, 350);
        });
        
        // Sidebar delete item button logic
        item.querySelector('.delete-note-btn').addEventListener('click', (e) => {
          e.stopPropagation();
          if (confirm("Delete this highlight?")) {
            allNotes = allNotes.filter(n => n.id !== note.id);
            saveNotesToServer();
            
            // Reload chapter if active to clear spans
            if (currentChapter.split('#')[0] === baseCh) {
              currentChapter = "";
              loadChapter(note.chapter, li);
            } else {
              updateNotesSidebar();
            }
          }
        });
        
        notesList.appendChild(item);
      });
    }

    // Recursive TOC NCX XML Parser with chevron accordions
    function parseNode(node, container, level = 1) {
      const children = Array.from(node.childNodes).filter(n => n.nodeName === 'navPoint');
      if (children.length === 0) return;
      
      const ul = document.createElement('ul');
      ul.classList.add(`level-${level}`);
      
      children.forEach(child => {
        const labelEl = child.querySelector('navLabel > text') || child.getElementsByTagName('text')[0];
        const contentEl = child.querySelector('content') || child.getElementsByTagName('content')[0];
        if (!labelEl || !contentEl) return;
        
        const label = labelEl.textContent.trim();
        const src = contentEl.getAttribute('src');
        
        const li = document.createElement('li');
        li.setAttribute('data-src', src);
        li.classList.add(`item-level-${level}`);
        
        const itemWrapper = document.createElement('div');
        itemWrapper.classList.add('item-wrapper');
        
        const span = document.createElement('span');
        span.textContent = label;
        itemWrapper.appendChild(span);
        
        flatChapters.push({ label, src });
        
        // If this navPoint has child navPoints, it is collapsible
        const hasChildren = Array.from(child.childNodes).some(n => n.nodeName === 'navPoint');
        if (hasChildren) {
          li.classList.add('collapsible');
          const chevron = document.createElement('span');
          chevron.className = 'chevron';
          chevron.innerHTML = '▼'; // Default collapsed state representation
          
          chevron.addEventListener('click', (e) => {
            e.stopPropagation(); // Prevent parent itemWrapper click event from bubbling (stops navigation)
            const subUl = Array.from(li.childNodes).find(n => n.nodeName === 'UL' || n.tagName === 'UL');
            if (subUl) {
              const isCollapsed = subUl.style.display === 'none' || subUl.style.display === '';
              if (isCollapsed) {
                subUl.style.display = 'block';
                chevron.innerHTML = '▲';
                chevron.classList.add('expanded');
              } else {
                subUl.style.display = 'none';
                chevron.innerHTML = '▼';
                chevron.classList.remove('expanded');
              }
            }
          });
          
          itemWrapper.appendChild(chevron);
        }
        
        li.appendChild(itemWrapper);
        ul.appendChild(li);
        
        // Recursively parse children
        parseNode(child, li, level + 1);
        
        // Event listener for navigation
        itemWrapper.addEventListener('click', (e) => {
          e.stopPropagation();
          navigateTo(src);
        });
      });
      container.appendChild(ul);
    }

    // Dynamic accordion toggler checking DOM ancestor tree relationships
    function updateAccordionState(activeLi) {
      const allCollapsible = document.querySelectorAll('#toc-list li.collapsible');
      allCollapsible.forEach(li => {
        const subUl = li.querySelector('ul');
        const chevron = li.querySelector('.chevron');
        if (!subUl) return;

        // Check if this li is an ancestor of the activeLi (or is the activeLi itself)
        let isAncestor = false;
        let temp = activeLi;
        while (temp && temp.id !== 'toc-list') {
          if (temp === li) {
            isAncestor = true;
            break;
          }
          temp = temp.parentElement;
        }

        if (isAncestor) {
          subUl.style.display = 'block';
          if (chevron) {
            chevron.innerHTML = '▲';
            chevron.classList.add('expanded');
          }
        } else {
          subUl.style.display = 'none';
          if (chevron) {
            chevron.innerHTML = '▼';
            chevron.classList.remove('expanded');
          }
        }
      });
    }

    // Load table of contents
    fetch('toc.ncx')
      .then(response => response.text())
      .then(xmlStr => {
        const parser = new DOMParser();
        const xml = parser.parseFromString(xmlStr, "text/xml");
        const navMap = xml.getElementsByTagName("navMap")[0];
        const tocList = document.getElementById('toc-list');
        
        // Fetch book title and author
        const titleEl = xml.getElementsByTagName("docTitle")[0];
        if (titleEl) {
          const textEl = titleEl.getElementsByTagName("text")[0];
          if (textEl) {
            document.getElementById('sidebar-book-title').innerText = textEl.textContent;
            document.title = textEl.textContent + " - O'Reilly Offline Reader";
          }
        }
        
        const authorEl = xml.getElementsByTagName("docAuthor")[0];
        if (authorEl) {
          const textEl = authorEl.getElementsByTagName("text")[0];
          if (textEl) document.getElementById('sidebar-book-author').innerText = "By " + textEl.textContent;
        }

        // Parse recursively
        parseNode(navMap, tocList);

        // Auto-load target chapter or first chapter
        const urlParams = new URLSearchParams(window.location.search);
        const startCh = urlParams.get('ch') || (flatChapters.length > 0 ? flatChapters[0].src : null);
        
        // Sync local storage / server notes database
        loadNotesFromServer()
          .catch(err => console.error("Error loading notes database:", err))
          .finally(() => {
            if (startCh) {
              const baseCh = startCh.split('#')[0];
              const li = document.querySelector(`li[data-src="${startCh}"]`) || 
                         document.querySelector(`li[data-src^="${baseCh}"]`);
              loadChapter(startCh, li);
            }
          });
      })
      .catch(err => {
        console.error("Failed to load table of contents:", err);
      });

    // Update bottom pagination buttons
    function updateNavigation() {
      const prevBtn = document.getElementById('prev-btn');
      const nextBtn = document.getElementById('next-btn');

      if (currentChapterIndex > 0) {
        prevBtn.style.visibility = 'visible';
        prevBtn.onclick = () => {
          const prevCh = flatChapters[currentChapterIndex - 1];
          const li = document.querySelector(`li[data-src="${prevCh.src}"]`);
          loadChapter(prevCh.src, li);
        };
      } else {
        prevBtn.style.visibility = 'hidden';
      }

      if (currentChapterIndex < flatChapters.length - 1 && currentChapterIndex !== -1) {
        nextBtn.style.visibility = 'visible';
        nextBtn.onclick = () => {
          const nextCh = flatChapters[currentChapterIndex + 1];
          const li = document.querySelector(`li[data-src="${nextCh.src}"]`);
          loadChapter(nextCh.src, li);
        };
      } else {
        nextBtn.style.visibility = 'hidden';
      }
    }
    // Navigate with history tracking (pushes previous src & scroll position to history stack)
    function navigateTo(src) {
      if (currentChapter && currentChapter !== src) {
        const mainContent = document.getElementById('main-content');
        historyStack.push({
          src: currentChapter,
          scrollTop: mainContent ? mainContent.scrollTop : 0
        });
        if (historyStack.length > 50) historyStack.shift();
        
        const backBtn = document.getElementById('history-back-btn');
        if (backBtn) backBtn.style.display = 'inline-flex';
      }
      const baseSrc = src.split('#')[0];
      const li = document.querySelector(`li[data-src="${src}"]`) || 
                 document.querySelector(`li[data-src^="${baseSrc}"]`);
      loadChapter(src, li);
    }

    // Load XHTML chapter dynamically
    function loadChapter(src, activeElement, restoreScrollTop) {
      const baseSrc = src.split('#')[0];
      const fragmentId = src.split('#')[1];
      const currentBase = currentChapter.split('#')[0];

      // Update URL search parameters silently
      const newUrl = window.location.protocol + "//" + window.location.host + window.location.pathname + `?ch=${src}`;
      window.history.replaceState({ path: newUrl }, '', newUrl);

      // Update active sidebar item
      const listItems = document.querySelectorAll('#toc-list li');
      listItems.forEach(li => li.classList.remove('active'));
      if (activeElement) {
        activeElement.classList.add('active');
        document.getElementById('current-chapter-title').innerText = activeElement.querySelector('span').textContent;
        
        // Auto-scroll sidebar TOC container to bring the active element into view
        activeElement.scrollIntoView({ behavior: 'smooth', block: 'nearest' });

        // Update chevrons and recursive accordion lists
        updateAccordionState(activeElement);
      }

      // Update index for prev/next navigation (exact match first, then base fallback)
      currentChapterIndex = flatChapters.findIndex(ch => ch.src === src);
      if (currentChapterIndex === -1) {
        currentChapterIndex = flatChapters.findIndex(ch => ch.src.split('#')[0] === baseSrc);
      }
      updateNavigation();

      if (currentBase === baseSrc && currentChapter !== "") {
        // Same chapter, just scroll to fragment element
        currentChapter = src;
        if (restoreScrollTop !== undefined && restoreScrollTop !== null) {
          document.getElementById('main-content').scrollTop = restoreScrollTop;
        } else if (fragmentId) {
          const fragmentEl = document.getElementById(fragmentId);
          if (fragmentEl) {
            isScrollingFromClick = true;
            fragmentEl.scrollIntoView({ behavior: 'smooth' });
            setTimeout(() => { isScrollingFromClick = false; }, 800);
            return;
          }
        } else {
          document.getElementById('main-content').scrollTop = 0;
        }
        return;
      }

      currentChapter = src;
      const wrapper = document.getElementById('book-content');
      wrapper.innerHTML = "<div style='text-align:center; padding-top: 150px;'><h3>Loading chapter...</h3></div>";

      fetch(baseSrc)
        .then(response => response.text())
        .then(html => {
          const parser = new DOMParser();
          const doc = parser.parseFromString(html, "text/html");
          
          const content = doc.getElementById('book-content') || doc.body;
          wrapper.innerHTML = content.innerHTML;

          // Re-apply notes & highlights for the freshly loaded chapter
          applyHighlightsForCurrentChapter();

          if (restoreScrollTop !== undefined && restoreScrollTop !== null) {
            document.getElementById('main-content').scrollTop = restoreScrollTop;
          } else if (fragmentId) {
            const fragmentEl = document.getElementById(fragmentId);
            if (fragmentEl) {
              isScrollingFromClick = true;
              fragmentEl.scrollIntoView({ behavior: 'smooth' });
              setTimeout(() => { isScrollingFromClick = false; }, 800);
              return;
            }
          } else {
            document.getElementById('main-content').scrollTop = 0;
          }
        })
        .catch(err => {
          wrapper.innerHTML = `<div style='text-align:center; color:red; padding-top: 150px;'><h3>Failed to load chapter: ${baseSrc}</h3></div>`;
          console.error(err);
        });

    }

    // Intercept clicks on links inside book content to keep navigation local and SPA-based
    document.getElementById('book-content').addEventListener('click', (e) => {
      const anchor = e.target.closest('a');
      if (!anchor) return;

      const href = anchor.getAttribute('href');
      if (!href) return;

      // External links should open in a new tab
      if (href.startsWith('http://') || href.startsWith('https://') || href.startsWith('//')) {
        anchor.setAttribute('target', '_blank');
        return;
      }

      // Check if it's an image link (e.g. figure-1.jpg)
      const isImage = href.match(/\.(jpg|jpeg|png|gif|svg|webp|bmp)(?:\?.*)?$/i);
      if (isImage) {
        e.preventDefault();
        showImageLightbox(href);
        return;
      }

      // Local bookmark hash links (e.g. #co_CO1-1)
      if (href.startsWith('#')) {
        e.preventDefault();
        
        // Push the current scroll position to history stack before jumping
        const mainContent = document.getElementById('main-content');
        historyStack.push({
          src: currentChapter,
          scrollTop: mainContent ? mainContent.scrollTop : 0
        });
        if (historyStack.length > 50) historyStack.shift();
        
        const backBtn = document.getElementById('history-back-btn');
        if (backBtn) backBtn.style.display = 'inline-flex';

        const targetId = href.substring(1);
        const targetEl = document.getElementById(targetId);
        if (targetEl) {
          isScrollingFromClick = true;
          targetEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
          targetEl.style.transition = 'background-color 0.3s';
          const oldBg = targetEl.style.backgroundColor;
          targetEl.style.backgroundColor = 'rgba(255, 235, 59, 0.3)';
          setTimeout(() => {
            targetEl.style.backgroundColor = oldBg;
            isScrollingFromClick = false;
          }, 1000);
        }
        return;
      }

      // Internal relative document link (e.g. ch02.html#sec)
      e.preventDefault();

      // Find matching TOC list item to sync sidebar
      const targetSrc = href;
      navigateTo(targetSrc);
    });

    function showImageLightbox(src) {
      const lightbox = document.getElementById('image-lightbox');
      const img = document.getElementById('lightbox-img');
      img.src = src;
      lightbox.classList.remove('hidden');
      void lightbox.offsetWidth; // Trigger layout
      lightbox.style.opacity = '1';
    }

    function hideImageLightbox() {
      const lightbox = document.getElementById('image-lightbox');
      lightbox.style.opacity = '0';
      setTimeout(() => {
        lightbox.classList.add('hidden');
        document.getElementById('lightbox-img').src = '';
      }, 200);
    }

    document.getElementById('close-lightbox').addEventListener('click', hideImageLightbox);
    document.getElementById('image-lightbox').addEventListener('click', (e) => {
      if (e.target === document.getElementById('image-lightbox')) {
        hideImageLightbox();
      }
    });

    // ScrollSpy active TOC tracking on scroll
    let scrollSpyTimeout = null;

    function handleScrollSpy() {
      if (isScrollingFromClick) return;
      const mainContent = document.getElementById('main-content');
      if (!mainContent) return;
      
      const currentBase = currentChapter.split('#')[0];
      const items = [];
      document.querySelectorAll('#toc-list li').forEach(li => {
        const src = li.getAttribute('data-src');
        if (src && src.split('#')[0] === currentBase) {
          const fragId = src.split('#')[1] || null;
          items.push({ li, fragId });
        }
      });
      
      if (items.length === 0) return;
      
      let activeItem = items[0];
      const scrollThreshold = 120;
      
      for (let i = 0; i < items.length; i++) {
        const item = items[i];
        if (item.fragId) {
          const targetEl = document.getElementById(item.fragId);
          if (targetEl) {
            const rect = targetEl.getBoundingClientRect();
            const mainRect = mainContent.getBoundingClientRect();
            const relativeTop = rect.top - mainRect.top;
            if (relativeTop <= scrollThreshold) {
              activeItem = item;
            } else {
              break;
            }
          }
        }
      }
      
      if (activeItem && !activeItem.li.classList.contains('active')) {
        document.querySelectorAll('#toc-list li').forEach(li => li.classList.remove('active'));
        activeItem.li.classList.add('active');
        document.getElementById('current-chapter-title').innerText = activeItem.li.querySelector('span').textContent;
        
        // Auto-scroll sidebar TOC container to bring the active element into view
        activeItem.li.scrollIntoView({ behavior: 'smooth', block: 'nearest' });

        // Update chevrons and recursive accordion lists
        updateAccordionState(activeItem.li);
      }
    }

    document.getElementById('main-content').addEventListener('scroll', () => {
      if (scrollSpyTimeout) clearTimeout(scrollSpyTimeout);
      scrollSpyTimeout = setTimeout(handleScrollSpy, 50);
    });
  </script>
</body>
</html>
"""



ORM_ICONS_CSS_TEMPLATE = '''@font-face { font-family: "ORM Icons"; font-style: normal; font-weight: 400; font-display: block; src: url(https://learning.oreilly.com/files/public/design-system/orm-icons.c8bbe02cfb4e.woff2) format("woff2"), url(https://learning.oreilly.com/files/public/design-system/orm-icons.8e12acfc4088.woff) format("woff"); } .orm-icon-2-day-training:before { content: "\f101"; } .orm-icon-add-plus:before { content: "\f102"; } .orm-icon-admin:before { content: "\f103"; } .orm-icon-align-left:before { content: "\f104"; } .orm-icon-align-right:before { content: "\f105"; } .orm-icon-answers:before { content: "\f106"; } .orm-icon-article:before { content: "\f107"; } .orm-icon-assessment-2:before { content: "\f108"; } .orm-icon-assessment:before { content: "\f109"; } .orm-icon-assignment:before { content: "\f10a"; } .orm-icon-attachment-2:before { content: "\f10b"; } .orm-icon-attachment:before { content: "\f10c"; } .orm-icon-audio-book:before { content: "\f10d"; } .orm-icon-audio-file:before { content: "\f10e"; } .orm-icon-avatar:before { content: "\f10f"; } .orm-icon-back:before { content: "\f110"; } .orm-icon-bar-chart:before { content: "\f111"; } .orm-icon-beta:before { content: "\f112"; } .orm-icon-bold:before { content: "\f113"; } .orm-icon-book:before { content: "\f114"; } .orm-icon-bullet-list:before { content: "\f115"; } .orm-icon-calendar-download-a:before { content: "\f116"; } .orm-icon-calendar-download-b:before { content: "\f117"; } .orm-icon-calendar-subscribe-a:before { content: "\f118"; } .orm-icon-calendar-subscribe-b:before { content: "\f119"; } .orm-icon-case-study:before { content: "\f11a"; } .orm-icon-center-align:before { content: "\f11b"; } .orm-icon-certifications:before { content: "\f11c"; } .orm-icon-change-owner:before { content: "\f11d"; } .orm-icon-check-indeterminate:before { content: "\f11e"; } .orm-icon-check-list:before { content: "\f11f"; } .orm-icon-checkmark-box:before { content: "\f120"; } .orm-icon-checkmark-circle:before { content: "\f121"; } .orm-icon-checkmark:before { content: "\f122"; } .orm-icon-chevron-down:before { content: "\f123"; } .orm-icon-chevron-left:before { content: "\f124"; } .orm-icon-chevron-right:before { content: "\f125"; } .orm-icon-chevron-up:before { content: "\f126"; } .orm-icon-close-x:before { content: "\f127"; } .orm-icon-code:before { content: "\f128"; } .orm-icon-collection:before { content: "\f129"; } .orm-icon-complete:before { content: "\f12a"; } .orm-icon-copy:before { content: "\f12b"; } .orm-icon-cut:before { content: "\f12c"; } .orm-icon-dashboard:before { content: "\f12d"; } .orm-icon-devices-other:before { content: "\f12e"; } .orm-icon-document:before { content: "\f12f"; } .orm-icon-draft:before { content: "\f130"; } .orm-icon-edit-group:before { content: "\f131"; } .orm-icon-edit:before { content: "\f132"; } .orm-icon-email:before { content: "\f133"; } .orm-icon-event-reminder:before { content: "\f134"; } .orm-icon-event:before { content: "\f135"; } .orm-icon-expert-playlist:before { content: "\f136"; } .orm-icon-external-link:before { content: "\f137"; } .orm-icon-facebook:before { content: "\f138"; } .orm-icon-filter-toggle:before { content: "\f139"; } .orm-icon-highlight:before { content: "\f13a"; } .orm-icon-history:before { content: "\f13b"; } .orm-icon-home:before { content: "\f13c"; } .orm-icon-image:before { content: "\f13d"; } .orm-icon-indent:before { content: "\f13e"; } .orm-icon-info-fill:before { content: "\f13f"; } .orm-icon-info-outline:before { content: "\f140"; } .orm-icon-insert:before { content: "\f141"; } .orm-icon-italic:before { content: "\f142"; } .orm-icon-jupyter-notebooks:before { content: "\f143"; } .orm-icon-keynote-a:before { content: "\f144"; } .orm-icon-keynote-b:before { content: "\f145"; } .orm-icon-keynote-c:before { content: "\f146"; } .orm-icon-learning-path:before { content: "\f147"; } .orm-icon-link:before { content: "\f148"; } .orm-icon-linkedin:before { content: "\f149"; } .orm-icon-listen:before { content: "\f14a"; } .orm-icon-live:before { content: "\f14b"; } .orm-icon-location:before { content: "\f14c"; } .orm-icon-lock:before { content: "\f14d"; } .orm-icon-log-in:before { content: "\f14e"; } .orm-icon-log-out:before { content: "\f14f"; } .orm-icon-maximize-2:before { content: "\f150"; } .orm-icon-maximize:before { content: "\f151"; } .orm-icon-menu:before { content: "\f152"; } .orm-icon-minimize-2:before { content: "\f153"; } .orm-icon-minimize:before { content: "\f154"; } .orm-icon-mobile-phone:before { content: "\f155"; } .orm-icon-more:before { content: "\f156"; } .orm-icon-move:before { content: "\f157"; } .orm-icon-note:before { content: "\f158"; } .orm-icon-notification:before { content: "\f159"; } .orm-icon-numbered-list:before { content: "\f15a"; } .orm-icon-o-dot:before { content: "\f15b"; } .orm-icon-organization-playlist:before { content: "\f15c"; } .orm-icon-oriole:before { content: "\f15d"; } .orm-icon-outdent:before { content: "\f15e"; } .orm-icon-pagination-overflow:before { content: "\f15f"; } .orm-icon-paste:before { content: "\f160"; } .orm-icon-pause:before { content: "\f161"; } .orm-icon-person:before { content: "\f162"; } .orm-icon-pie-chart:before { content: "\f163"; } .orm-icon-play-2:before { content: "\f164"; } .orm-icon-play:before { content: "\f165"; } .orm-icon-playlist-add:before { content: "\f166"; } .orm-icon-preview:before { content: "\f167"; } .orm-icon-previous-2:before { content: "\f168"; } .orm-icon-previous:before { content: "\f169"; } .orm-icon-printing:before { content: "\f16a"; } .orm-icon-progress:before { content: "\f16b"; } .orm-icon-project-2:before { content: "\f16c"; } .orm-icon-project:before { content: "\f16d"; } .orm-icon-public-playlist:before { content: "\f16e"; } .orm-icon-publish:before { content: "\f16f"; } .orm-icon-queue-old:before { content: "\f170"; } .orm-icon-queue:before { content: "\f171"; } .orm-icon-recommendation:before { content: "\f172"; } .orm-icon-recording-2:before { content: "\f173"; } .orm-icon-recording:before { content: "\f174"; } .orm-icon-refresh:before { content: "\f175"; } .orm-icon-remove:before { content: "\f176"; } .orm-icon-resource-centers:before { content: "\f177"; } .orm-icon-sandboxes:before { content: "\f178"; } .orm-icon-save:before { content: "\f179"; } .orm-icon-search:before { content: "\f17a"; } .orm-icon-session-a:before { content: "\f17b"; } .orm-icon-session-b:before { content: "\f17c"; } .orm-icon-settings:before { content: "\f17d"; } .orm-icon-share-file:before { content: "\f17e"; } .orm-icon-share-post:before { content: "\f17f"; } .orm-icon-share:before { content: "\f180"; } .orm-icon-spell-check:before { content: "\f181"; } .orm-icon-star-rating-fill:before { content: "\f182"; } .orm-icon-star-rating-outline:before { content: "\f183"; } .orm-icon-stop:before { content: "\f184"; } .orm-icon-success:before { content: "\f185"; } .orm-icon-tablet:before { content: "\f186"; } .orm-icon-text-color-2:before { content: "\f187"; } .orm-icon-text-color:before { content: "\f188"; } .orm-icon-time-2:before { content: "\f189"; } .orm-icon-time:before { content: "\f18a"; } .orm-icon-TOC-close:before { content: "\f18b"; } .orm-icon-TOC-open:before { content: "\f18c"; } .orm-icon-topics:before { content: "\f18d"; } .orm-icon-tutorial-a:before { content: "\f18e"; } .orm-icon-tutorial-b:before { content: "\f18f"; } .orm-icon-tutorial-c:before { content: "\f190"; } .orm-icon-tutorials:before { content: "\f191"; } .orm-icon-tv-console:before { content: "\f192"; } .orm-icon-twitter:before { content: "\f193"; } .orm-icon-unlock:before { content: "\f194"; } .orm-icon-video:before { content: "\f195"; } .orm-icon-volume:before { content: "\f196"; } .orm-icon-warning-bang:before { content: "\f197"; } .orm-icon-warning-fill:before { content: "\f198"; } .orm-icon-warning-outline:before { content: "\f199"; } .orm-icon-youtube:before { content: "\f19a"; } .orm-icon-zoom-in:before { content: "\f19b"; } .orm-icon-zoom-out:before { content: "\f19c"; } '''
