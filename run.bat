@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul 2>nul
REM ============================================================
REM   IWAS Water Distribution AI - Setup and Run (Windows)
REM   Works on a machine with NOTHING installed - will install
REM   Python itself via winget if it is missing.
REM ============================================================
cd /d "%~dp0"

echo.
echo ======================================
echo   IWAS Water AI - Setup
echo ======================================
echo.

REM ---- 1. Check for Python 3.10+ -----------------------------
set "PYTHON_BIN="
for %%P in (python python3 py) do (
    if not defined PYTHON_BIN (
        where %%P >nul 2>nul
        if !errorlevel! == 0 (
            for /f "tokens=2 delims= " %%V in ('%%P --version 2^>^&1') do set "PYVER=%%V"
            for /f "tokens=1,2 delims=." %%A in ("!PYVER!") do (
                set "PYMAJOR=%%A"
                set "PYMINOR=%%B"
            )
            if "!PYMAJOR!"=="3" (
                if !PYMINOR! geq 10 (
                    set "PYTHON_BIN=%%P"
                )
            )
        )
    )
)

if defined PYTHON_BIN goto :found_python

echo No suitable Python 3.10+ found. Installing via winget...
where winget >nul 2>nul
if errorlevel 1 (
    echo.
    echo ERROR: winget not found on this machine.
    echo Please install Python 3.10+ manually from:
    echo   https://www.python.org/downloads/
    echo IMPORTANT: check the box "Add Python to PATH" during install.
    echo Then re-run this script.
    echo.
    pause
    exit /b 1
)

echo Installing Python 3.11 - this may take a few minutes...
winget install -e --id Python.Python.3.11 --scope user --silent --accept-source-agreements --accept-package-agreements

echo.
echo Python has been installed.
echo Please CLOSE this window and double-click run.bat again.
echo (Windows needs a fresh terminal window to detect the new PATH.)
echo.
echo NOTE: If "python --version" still does not work after reopening,
echo Windows may be using the Microsoft Store Python stub instead of
echo the real install. To fix this:
echo   Settings - Apps - Advanced app settings - App execution aliases
echo   Turn OFF "python.exe" and "python3.exe", then reopen the terminal.
echo.
pause
exit /b 0

:found_python
echo Using Python: %PYTHON_BIN%
%PYTHON_BIN% --version
echo.

REM ---- 2. Virtual environment ---------------------------------
if not exist ".venv\Scripts\activate.bat" (
    echo Creating virtual environment...
    %PYTHON_BIN% -m venv .venv
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment.
        pause
        exit /b 1
    )
)
call .venv\Scripts\activate.bat

REM ---- 3. Install dependencies ---------------------------------
echo Installing dependencies - this may take a minute on first run...
python -m pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
if errorlevel 1 (
    echo ERROR: Failed to install dependencies.
    pause
    exit /b 1
)
echo Dependencies installed.
echo.

REM ---- 4. Check .env and API key --------------------------------
if not exist ".env" (
    if exist ".env.example" (
        echo No .env found - creating one from .env.example...
        copy /y .env.example .env >nul
        echo.
        echo ====================================================
        echo   A .env file has been created at:
        echo   %cd%\.env
        echo.
        echo   Open it in Notepad, add your API key, save it,
        echo   then re-run this script.
        echo ====================================================
        echo.
        pause
        exit /b 1
    ) else (
        echo ERROR: No .env or .env.example file found.
        pause
        exit /b 1
    )
)

REM Robust .env parser - skips blank lines, comments, and lines without =
set "LLM_PROVIDER="
set "GROQ_API_KEY="
set "GEMINI_API_KEY="
set "OPENAI_API_KEY="
set "ANTHROPIC_API_KEY="
for /f "usebackq eol=# tokens=1,* delims==" %%A in (".env") do (
    if not "%%A"=="" if not "%%B"=="" (
        set "%%A=%%B"
    )
)

if not defined LLM_PROVIDER set "LLM_PROVIDER=groq"
echo LLM Provider: %LLM_PROVIDER%

set "KEY_MISSING=0"
set "KEY_NAME="
set "SIGNUP="

if /i "%LLM_PROVIDER%"=="groq" (
    if not defined GROQ_API_KEY set "KEY_MISSING=1" & set "KEY_NAME=GROQ_API_KEY" & set "SIGNUP=https://console.groq.com"
    if "%GROQ_API_KEY%"=="gsk_your_key_here" set "KEY_MISSING=1" & set "KEY_NAME=GROQ_API_KEY" & set "SIGNUP=https://console.groq.com"
)
if /i "%LLM_PROVIDER%"=="gemini" (
    if not defined GEMINI_API_KEY set "KEY_MISSING=1" & set "KEY_NAME=GEMINI_API_KEY" & set "SIGNUP=https://aistudio.google.com/app/apikey"
    if "%GEMINI_API_KEY%"=="your_key_here" set "KEY_MISSING=1" & set "KEY_NAME=GEMINI_API_KEY" & set "SIGNUP=https://aistudio.google.com/app/apikey"
)
if /i "%LLM_PROVIDER%"=="openai" (
    if not defined OPENAI_API_KEY set "KEY_MISSING=1" & set "KEY_NAME=OPENAI_API_KEY" & set "SIGNUP=https://platform.openai.com/api-keys"
    if "%OPENAI_API_KEY%"=="sk-your_key_here" set "KEY_MISSING=1" & set "KEY_NAME=OPENAI_API_KEY" & set "SIGNUP=https://platform.openai.com/api-keys"
)
if /i "%LLM_PROVIDER%"=="anthropic" (
    if not defined ANTHROPIC_API_KEY set "KEY_MISSING=1" & set "KEY_NAME=ANTHROPIC_API_KEY" & set "SIGNUP=https://console.anthropic.com"
    if "%ANTHROPIC_API_KEY%"=="sk-ant-your_key_here" set "KEY_MISSING=1" & set "KEY_NAME=ANTHROPIC_API_KEY" & set "SIGNUP=https://console.anthropic.com"
)

if "%KEY_MISSING%"=="1" (
    echo.
    echo ====================================================
    echo   WARNING: %KEY_NAME% is not set in .env
    echo   Sign up for a free key at: %SIGNUP%
    echo   Then add this line to .env:
    echo     %KEY_NAME%=your_key_here
    echo   Then re-run this script.
    echo ====================================================
    echo.
    pause
    exit /b 1
)
echo API key found for %LLM_PROVIDER%
echo.

REM ---- 5. Seed databases -----------------------------------------
if not exist "data\supply.db" (
    echo Seeding core databases...
    python data\seed.py
    if errorlevel 1 (
        echo ERROR: Database seeding failed.
        pause
        exit /b 1
    )
    echo Core databases seeded.
) else (
    echo Core databases already seeded. ^(delete data\*.db to reseed^)
)

if exist "data\ward_data.csv" (
    if not exist "data\ward.db" (
        echo Seeding ward database from data\ward_data.csv...
        python data\seed_ward.py
        echo Ward database seeded.
    ) else (
        echo Ward database already seeded.
    )
) else (
    echo.
    echo WARNING: data\ward_data.csv not found - ward DB will be empty.
    echo.
)
echo.

REM ---- 6. Start orchestrator ---------------------------------------
echo ======================================
echo   Starting IWAS orchestrator...
echo   Open http://localhost:8000 in your browser
echo   Press Ctrl+C to stop
echo ======================================
echo.

set "PYTHONPATH=."
uvicorn orchestrator.main:app --port 8000

pause
