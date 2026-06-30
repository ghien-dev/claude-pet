@echo off
REM ╔══════════════════════════════════════════════════╗
REM ║  Claude Pet — Windows Installer                  ║
REM ║  Chạy file này 1 lần là xong                     ║
REM ╚══════════════════════════════════════════════════╝

setlocal

set "INSTALL_DIR=%USERPROFILE%\.claude-pet"
set "HOOKS_DIR=%USERPROFILE%\.claude\hooks"
set "CLAUDE_DIR=%USERPROFILE%\.claude"
set "CLAUDE_SETTINGS=%CLAUDE_DIR%\settings.json"
set "STARTUP_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "SCRIPT_DIR=%~dp0"

echo.
echo   Claude Pet - Dang cai dat...
echo   ─────────────────────────────────────────────
echo.

REM 1. Kiem tra Python
echo [1/6] Kiem tra Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo   [!!] Khong tim thay Python. Cai tu https://python.org va thu lai.
    pause & exit /b 1
)
python --version

REM 2. Tao thu muc
echo [2/6] Tao thu muc...
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"
if not exist "%HOOKS_DIR%"   mkdir "%HOOKS_DIR%"
if not exist "%CLAUDE_DIR%"  mkdir "%CLAUDE_DIR%"
echo    OK

REM 3. Copy files
echo [3/6] Copy files...
copy /Y "%SCRIPT_DIR%pet.py"                 "%INSTALL_DIR%\pet.py"                  >nul && echo    OK  pet.py
copy /Y "%SCRIPT_DIR%pet_admin.html"         "%INSTALL_DIR%\pet_admin.html"          >nul && echo    OK  pet_admin.html
copy /Y "%SCRIPT_DIR%pet_ui.py"              "%INSTALL_DIR%\pet_ui.py"               >nul && echo    OK  pet_ui.py
copy /Y "%SCRIPT_DIR%pet_test.py"            "%INSTALL_DIR%\pet_test.py"             >nul && echo    OK  pet_test.py
copy /Y "%SCRIPT_DIR%pet_update_settings.py" "%INSTALL_DIR%\pet_update_settings.py" >nul && echo    OK  pet_update_settings.py
copy /Y "%SCRIPT_DIR%pet_hooks_handler.py"   "%HOOKS_DIR%\pet_hooks_handler.py"     >nul && echo    OK  pet_hooks_handler.py
copy /Y "%SCRIPT_DIR%statusline.js"          "%CLAUDE_DIR%\statusline.js"            >nul && echo    OK  statusline.js
if not exist "%INSTALL_DIR%\pet_sounds.json" (
    copy /Y "%SCRIPT_DIR%pet_sounds.json" "%INSTALL_DIR%\pet_sounds.json" >nul && echo    OK  pet_sounds.json
) else (
    echo    .   pet_sounds.json  (giu nguyen config hien co)
)

REM 4. Cai Pillow va qrcode
echo [4/6] Cai Pillow, qrcode...
python -m pip install --quiet Pillow "qrcode[pil]"
echo    OK  Pillow, qrcode

REM 5. Wire Claude Code hooks + statusLine
echo [5/6] Cap nhat Claude hooks (settings.json)...
python "%INSTALL_DIR%\pet_update_settings.py" "%CLAUDE_SETTINGS%"

REM 6. Tao autostart
echo [6/6] Tao autostart...
set "STARTUP_BAT=%STARTUP_DIR%\ClaudePet.bat"
echo @echo off > "%STARTUP_BAT%"
echo pythonw "%INSTALL_DIR%\pet.py" >> "%STARTUP_BAT%"
echo    OK  %STARTUP_BAT%

REM Launch pet
echo.
echo   Khoi dong pet...
powershell -NoProfile -Command ^
  "Get-WmiObject Win32_Process -Filter \"Name='pythonw.exe'\" | Where-Object { $_.CommandLine -like '*claude-pet*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
timeout /t 1 /nobreak >nul
start "" pythonw "%INSTALL_DIR%\pet.py"
timeout /t 2 /nobreak >nul

python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:7007', timeout=2)" >nul 2>&1
if errorlevel 1 (
    echo   [!!] Pet chua phan hoi tai :7007 -- kiem tra lai
) else (
    echo   OK  pet dang chay tai http://127.0.0.1:7007
)

echo.
echo   ─────────────────────────────────────────────
echo   XONG! Restart Claude Code de hooks co hieu luc.
echo.
echo   Widget : floating circle on your desktop
echo   Admin  : http://localhost:7007/ui
echo   ─────────────────────────────────────────────
echo.
pause
