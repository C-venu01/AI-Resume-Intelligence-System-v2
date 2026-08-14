@echo off
REM ==========================================
REM AI Resume Intelligence System 2.0
REM One-Click Startup Script (Windows)
REM ==========================================

echo.
echo  ====================================================
echo   AI Resume Intelligence System 2.0
echo   Cloud-Based Hiring Copilot
echo  ====================================================
echo.

REM Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed. Install Python 3.12+ from python.org
    pause
    exit /b 1
)

REM Install dependencies
echo [1/3] Installing Python dependencies...
cd backend
pip install -r requirements.txt --quiet
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install dependencies
    pause
    exit /b 1
)

REM Download SpaCy model
echo [2/3] Downloading SpaCy NLP model...
python -m spacy download en_core_web_sm --quiet 2>nul

REM Start server
echo [3/3] Starting FastAPI server...
echo.
echo  ====================================================
echo   Server starting at: http://localhost:8000
echo   API Docs at:        http://localhost:8000/docs
echo   Press Ctrl+C to stop
echo  ====================================================
echo.

REM Open browser after a short delay
start "" cmd /c "timeout /t 3 /nobreak >nul && start http://localhost:8000"

REM Start the server
python main.py
