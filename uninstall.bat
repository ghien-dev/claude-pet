@echo off
setlocal

set "INSTALL_DIR=%USERPROFILE%\.claude-pet"
set "HOOKS_DIR=%USERPROFILE%\.claude\hooks"
set "CLAUDE_SETTINGS=%USERPROFILE%\.claude\settings.json"
set "STARTUP_BAT=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\ClaudePet.bat"

echo.
echo   Claude Pet - Gỡ cài đặt...
echo   ─────────────────────────────────────────────
echo.

REM 1. Kill process
echo [1/4] Tat Claude Pet...
powershell -NoProfile -Command ^
  "Get-WmiObject Win32_Process -Filter \"Name='pythonw.exe'\" | Where-Object { $_.CommandLine -like '*claude-pet*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
echo    Done

REM 2. Xoa thu muc cai dat
echo [2/4] Xoa %INSTALL_DIR%...
if exist "%INSTALL_DIR%" (
    rmdir /s /q "%INSTALL_DIR%"
    echo    Xoa xong
) else (
    echo    Khong tim thay, bo qua
)

REM 3. Xoa hook handler file (chi xoa file cua pet, khong xoa thu muc)
echo [3/4] Xoa hook handler...
if exist "%HOOKS_DIR%\pet_hooks_handler.py" (
    del /q "%HOOKS_DIR%\pet_hooks_handler.py"
    echo    Xoa %HOOKS_DIR%\pet_hooks_handler.py
) else (
    echo    Khong tim thay, bo qua
)

REM 4. Xoa autostart
echo [4/4] Xoa autostart...
if exist "%STARTUP_BAT%" (
    del /q "%STARTUP_BAT%"
    echo    Xoa %STARTUP_BAT%
) else (
    echo    Khong tim thay, bo qua
)

REM 5. Xoa hooks pet_hooks_handler.py khoi settings.json (giu statusLine va hooks khac)
echo [5/4] Xoa hooks trong settings.json...
python "%~dp0pet_uninstall_settings.py" "%CLAUDE_SETTINGS%"

echo.
echo   ─────────────────────────────────────────────
echo   Gỡ cài đặt hoàn tất!
echo   Restart Claude Code de hooks ngung hoat dong.
echo   ─────────────────────────────────────────────
echo.
pause
