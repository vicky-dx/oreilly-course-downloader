import importlib.resources

def _load(filename: str) -> str:
    ref = importlib.resources.files("oreilly_downloader.core.resources.templates").joinpath(filename)
    return ref.read_text(encoding="utf-8")

ORM_ICONS_CSS_TEMPLATE = _load("orm_icons.css")
LIBRARY_INDEX_HTML_TEMPLATE = _load("library_index.html")
LIBRARY_SERVE_PY_TEMPLATE = _load("library_serve.py.template")
LIBRARY_BAT_LAUNCHER_TEMPLATE = _load("library_launch.bat")
LIBRARY_SH_LAUNCHER_TEMPLATE = _load("library_launch.sh")
