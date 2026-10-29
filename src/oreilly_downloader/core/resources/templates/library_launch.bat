@echo off
chcp 65001 >nul
echo 🚀 Starting central O'Reilly Offline Library...
set PYTHONIOENCODING=utf-8

where python >nul 2>nul
if %errorlevel% equ 0 (
    python serve_library.py
    goto end
)

where py >nul 2>nul
if %errorlevel% equ 0 (
    py -3 serve_library.py
    goto end
)

where uv >nul 2>nul
if %errorlevel% equ 0 (
    uv run python serve_library.py
    goto end
)

echo ❌ Python was not found in your PATH.
echo Please install Python 3.12+ or run 'uv run python serve_library.py'.
pause

:end
