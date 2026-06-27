@echo off
REM ╔══════════════════════════════════════════════════╗
REM ║  Claude Pet — Windows Installer                  ║
REM ║  Chạy file này 1 lần là xong                     ║
REM ╚══════════════════════════════════════════════════╝

setlocal

set "INSTALL_DIR=%USERPROFILE%\.claude-pet"
set "HOOKS_DIR=%USERPROFILE%\.claude\hooks"
set "CLAUDE_SETTINGS=%USERPROFILE%\.claude\settings.json"
set "SCRIPT_DIR=%~dp0"

echo.
echo   Claude Pet - Dang cai dat...
echo   ─────────────────────────────────────────────
echo.

REM 0. Cài dependency Pillow (pet.py vẽ widget bằng PIL + layered window)
echo [0/4] Cai dependency Pillow...
python -m pip install --quiet Pillow

REM 1. Tạo thư mục
echo [1/4] Tao thu muc...
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"
if not exist "%HOOKS_DIR%" mkdir "%HOOKS_DIR%"

REM 2. Copy files
echo [2/4] Copy files...
copy /Y "%SCRIPT_DIR%pet.py"           "%INSTALL_DIR%\pet.py"           >nul
copy /Y "%SCRIPT_DIR%hooks_handler.py" "%HOOKS_DIR%\hooks_handler.py"   >nul

REM 3. Tạo startup shortcut (chạy pet khi Windows khởi động)
echo [3/4] Tao startup script...

REM Tạo .bat để launch pet (ẩn cửa sổ console)
set "LAUNCHER=%INSTALL_DIR%\start-pet.bat"
(
  echo @echo off
  echo pythonw "%INSTALL_DIR%\pet.py"
) > "%LAUNCHER%"

REM Tạo shortcut trong Startup folder
set "STARTUP_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "SHORTCUT=%STARTUP_DIR%\ClaudePet.bat"
copy /Y "%LAUNCHER%" "%SHORTCUT%" >nul
echo    Shortcut tao tai: %SHORTCUT%

REM 4. Cài hooks vào Claude settings.json
echo [4/4] Cap nhat Claude hooks...

REM Backup settings.json nếu tồn tại
if exist "%CLAUDE_SETTINGS%" (
    copy /Y "%CLAUDE_SETTINGS%" "%CLAUDE_SETTINGS%.backup" >nul
    echo    Backup: %CLAUDE_SETTINGS%.backup
)

REM Ghi settings.json mới (merge bằng Python)
python -c "
import json, os, sys

settings_path = r'%CLAUDE_SETTINGS%'
hooks_handler = r'python \"%USERPROFILE%\.claude\hooks\hooks_handler.py\"'.replace('%%', '%%')

hook_cmd = {
    'type': 'command',
    'command': r'python \"%%USERPROFILE%%\.claude\hooks\hooks_handler.py\"'
}

new_hooks = {
    'PreToolUse':  [{'matcher': '', 'hooks': [hook_cmd]}],
    'PostToolUse': [{'matcher': '', 'hooks': [hook_cmd]}],
    'Stop':        [{'matcher': '', 'hooks': [hook_cmd]}],
    'Notification':[{'matcher': '', 'hooks': [hook_cmd]}],
}

if os.path.exists(settings_path):
    with open(settings_path) as f:
        data = json.load(f)
else:
    data = {}

data.setdefault('hooks', {}).update(new_hooks)

os.makedirs(os.path.dirname(settings_path), exist_ok=True)
with open(settings_path, 'w') as f:
    json.dump(data, f, indent=2)

print('   Settings saved to:', settings_path)
"

echo.
echo   ─────────────────────────────────────────────
echo   XONG! Lam theo 2 buoc sau:
echo.
echo   1. Chay pet ngay bay gio:
echo      pythonw "%INSTALL_DIR%\pet.py"
echo.
echo   2. Restart Claude Code de hooks co hieu luc.
echo.
echo   Pet se tu dong chay khi Windows khoi dong.
echo   ─────────────────────────────────────────────
echo.
pause
