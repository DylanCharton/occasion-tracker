@echo off
REM Installation initiale : venv + dependances + init DB
cd /d "%~dp0"

echo.
echo === Easycash Tracker : installation ===
echo.

if not exist ".venv" (
    echo [1/3] Creation du venv...
    py -m venv .venv
    if errorlevel 1 (
        echo [ERREUR] Python introuvable. Installe Python 3.11+ depuis python.org
        pause
        exit /b 1
    )
) else (
    echo [1/3] venv deja present, skip.
)

echo.
echo [2/3] Installation des dependances...
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip --quiet
pip install -r requirements.txt
if errorlevel 1 (
    echo [ERREUR] Installation echouee.
    pause
    exit /b 1
)

echo.
echo [3/3] Initialisation de la base de donnees...
python -m scraper.cli init-db

if not exist ".env" (
    echo.
    echo Copie de .env.example vers .env...
    copy /y .env.example .env >nul
)

echo.
echo === Installation terminee ===
echo.
echo Pour lancer : double-clique sur run.bat
echo Pour configurer Discord : edite le fichier .env
echo.
pause
