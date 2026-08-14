@echo off
echo ============================================
echo   Smart Knowledge QA System - Quick Start
echo ============================================

cd /d "%~dp0"

REM ---- create venv (first run) ----
if not exist ".venv" (
    echo [1/4] Creating virtual environment...
    python -m venv .venv
)

REM ---- install deps (first run) ----
if not exist ".venv\Lib\site-packages\fastapi" (
    echo [2/4] Installing dependencies...
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
)

REM ---- create .env if missing ----
if not exist ".env" (
    copy ".env.example" ".env" >nul
    echo [3/4] .env created. Please edit LLM_API_KEY inside.
)

echo [4/4] Starting server: http://127.0.0.1:8000
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 0.0.0.0 --port 8000
pause
