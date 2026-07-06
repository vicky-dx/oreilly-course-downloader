import importlib.resources

def _load(filename: str) -> str:
    ref = importlib.resources.files("oreilly_downloader.core.resources.templates").joinpath(filename)
    return ref.read_text(encoding="utf-8")

FONT_FACES_TEMPLATE = _load("font_faces.css")
FORMATTING_OVERRIDES = _load("formatting_overrides.css")
SERVE_PY_TEMPLATE = _load("serve.py.template")
BAT_LAUNCHER_TEMPLATE = _load("launch.bat")
SH_LAUNCHER_TEMPLATE = _load("launch.sh")
WEB_VIEWER_HTML_TEMPLATE = _load("web_viewer.html")
