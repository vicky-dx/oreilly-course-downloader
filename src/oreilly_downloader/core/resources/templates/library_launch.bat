@echo off
chcp 65001 >nul
echo 🚀 Starting central O'Reilly Offline Library...
set PYTHONIOENCODING=utf-8
python serve_library.py
