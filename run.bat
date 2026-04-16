ok merci phase 4@echo off
REM Lance Easycash Tracker (UI Streamlit + scheduler)
cd /d "%~dp0"

if not exist ".venv\Scripts\activate.bat" (
    echo [ERREUR] venv absent. Lance d'abord setup.bat
    pause
    exit /b 1
)

call .venv\Scripts\activate.bat
streamlit run streamlit_app.py
