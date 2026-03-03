@echo off
chcp 65001 >nul
title GameWiki Assistant Build Tool

echo.
echo ======================================
echo     GameWiki Assistant Build Tool
echo ======================================
echo.

:: Check Python (try py launcher first, then python)
set "PYTHON_CMD="
py -3 --version >nul 2>&1
if %errorlevel% equ 0 (set "PYTHON_CMD=py -3") else (
    python --version >nul 2>&1
    if %errorlevel% equ 0 (set "PYTHON_CMD=python") else (
        echo [ERROR] Python not found. Please install Python 3.8 or higher.
        echo Download: https://www.python.org/downloads/
        pause
        exit /b 1
    )
)

:: Check we are in project root
if not exist "src\game_wiki_tooltip\qt_app.py" (
    echo [ERROR] Please run this script from the project root directory.
    echo Current directory: %CD%
    pause
    exit /b 1
)

echo Building in onedir mode (avoids single-exe DLL issues)...
echo.

:: Run build script with onedir mode
%PYTHON_CMD% build_exe.py --mode onedir

:: Check build result (onedir output: GameWikiAssistant_Portable_onedir\GameWikiAssistant\)
if exist "GameWikiAssistant_Portable_onedir\GameWikiAssistant\GameWikiAssistant.exe" (
    echo.
    echo Build succeeded.
    echo Output: %CD%\GameWikiAssistant_Portable_onedir\GameWikiAssistant
    echo Main exe: GameWikiAssistant.exe
    echo.
    
    set /p choice="Open output folder? (y/n): "
    if /i "%choice%"=="y" (
        explorer "%~dp0GameWikiAssistant_Portable_onedir"
    )
) else (
    echo.
    echo [ERROR] Build failed. Check the messages above.
)

echo.
pause
