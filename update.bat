@echo off
REM ╔══════════════════════════════════════════════════════════╗
REM ║  Claude Pet — Update, Restart & Test                     ║
REM ╚══════════════════════════════════════════════════════════╝

setlocal enabledelayedexpansion

set "INSTALL_DIR=%USERPROFILE%\.claude-pet"
set "HOOKS_DIR=%USERPROFILE%\.claude\hooks"
set "CLAUDE_SETTINGS=%USERPROFILE%\.claude\settings.json"
set "SCRIPT_DIR=%~dp0"
set "ERRORS=0"
set "BACKUP_DT="
set "BACKUP_STATUS=?"
set "COPY_STATUS=?"
set "SETTINGS_STATUS=?"
set "PET_STATUS=?"
set "TEST_STATUS=?"
set "TEST_EXIT=1"

echo.
echo   ======================================================
echo     Claude Pet -- Update, Restart and Test
echo   ======================================================
echo.

REM ── Lay timestamp backup (PowerShell, fallback wmic) ─────────────────────────
for /f %%I in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss" 2^>nul') do set "BACKUP_DT=%%I"
if "!BACKUP_DT!"=="" (
    for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value 2^>nul') do (
        if not "%%I"=="" set "_WM=%%I"
    )
    if defined _WM set "BACKUP_DT=!_WM:~0,8!_!_WM:~8,6!"
)
if "!BACKUP_DT!"=="" set "BACKUP_DT=backup"

REM ── 1. Tao thu muc neu chua co ──────────────────────────────────────────────
echo   [1/6] Chuan bi thu muc cai dat...

python -m pip install --quiet Pillow "qrcode[pil]" 2>nul

if not exist "%INSTALL_DIR%" (
    mkdir "%INSTALL_DIR%"
    echo         + Tao moi: %INSTALL_DIR%
) else (
    echo         . Da co:   %INSTALL_DIR%
)
if not exist "%HOOKS_DIR%" (
    mkdir "%HOOKS_DIR%"
    echo         + Tao moi: %HOOKS_DIR%
) else (
    echo         . Da co:   %HOOKS_DIR%
)

REM ── 2. Backup cac file .claude truoc khi sua ─────────────────────────────────
echo.
echo   [2/6] Backup files .claude (suffix: .backup.!BACKUP_DT!)...

set "_E0=!ERRORS!"
call :backup_file "%CLAUDE_SETTINGS%"
call :backup_file "%HOOKS_DIR%\pet_hooks_handler.py"
set /a "_BERRS=!ERRORS!-!_E0!"
if !_BERRS! EQU 0 ( set "BACKUP_STATUS=OK" ) else ( set "BACKUP_STATUS=!_BERRS! loi" )

REM ── 3. Copy files ───────────────────────────────────────────────────────────
echo.
echo   [3/6] Copy files...

set "_E0=!ERRORS!"
call :copyfile "pet.py"                 "%INSTALL_DIR%\pet.py"
call :copyfile "pet_admin.html"         "%INSTALL_DIR%\pet_admin.html"
call :copyfile "pet_hooks_handler.py"   "%HOOKS_DIR%\pet_hooks_handler.py"
call :copyfile "pet_ui.py"              "%INSTALL_DIR%\pet_ui.py"
call :copyfile "pet_test.py"            "%INSTALL_DIR%\pet_test.py"
call :copyfile "pet_update_settings.py" "%INSTALL_DIR%\pet_update_settings.py"
call :copyfile "statusline.js"          "%USERPROFILE%\.claude\statusline.js"

if not exist "%INSTALL_DIR%\pet_sounds.json" (
    copy /Y "%SCRIPT_DIR%pet_sounds.json" "%INSTALL_DIR%\pet_sounds.json" >nul 2>&1
    echo         OK  pet_sounds.json        (tao moi)
) else (
    echo         .   pet_sounds.json        (giu nguyen config hien co)
)
set /a "_CERRS=!ERRORS!-!_E0!"
if !_CERRS! EQU 0 ( set "COPY_STATUS=OK" ) else ( set "COPY_STATUS=!_CERRS! loi" )

REM ── 4. Cap nhat Claude hooks trong settings.json ─────────────────────────────
echo.
echo   [4/6] Cap nhat Claude hooks (settings.json)...

python "%SCRIPT_DIR%pet_update_settings.py" "%CLAUDE_SETTINGS%"
if errorlevel 1 (
    echo         [!!] Loi khi cap nhat settings.json
    set /a ERRORS+=1
    set "SETTINGS_STATUS=FAIL"
) else (
    set "SETTINGS_STATUS=OK"
)

REM ── 5. Restart pet ───────────────────────────────────────────────────────────
echo.
echo   [5/6] Khoi dong lai pet...

taskkill /f /im pythonw.exe >nul 2>&1
echo         . Da dung pythonw.exe cu (neu co)
timeout /t 1 /nobreak >nul

start "" pythonw "%INSTALL_DIR%\pet.py"
echo         . Dang cho pet khoi dong (2 giay)...
timeout /t 2 /nobreak >nul

python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:7007', timeout=2)" >nul 2>&1
if errorlevel 1 (
    echo         [!!] Pet khong phan hoi tai :7007 -- kiem tra Python/pythonw
    set /a ERRORS+=1
    set "PET_STATUS=FAIL"
) else (
    echo         OK  Pet dang phan hoi tai http://127.0.0.1:7007
    set "PET_STATUS=OK"
)

REM ── 6. Chay test suite ───────────────────────────────────────────────────────
echo.
echo   [6/6] Chay test suite...
echo.
timeout /t 1 /nobreak >nul

echo   ------------------------------------------------------
python "%SCRIPT_DIR%pet_test.py"
set "TEST_EXIT=!errorlevel!"
echo   ------------------------------------------------------

if !TEST_EXIT! EQU 0 (
    set "TEST_STATUS=OK -- tat ca test passed"
) else (
    set "TEST_STATUS=FAIL -- co test bao loi (xem log o tren)"
)

REM ── Bao cao tong ket ─────────────────────────────────────────────────────────
echo.
echo   ======================================================
echo     BAO CAO KET QUA
echo   ======================================================
echo.
echo   Backup (.backup.!BACKUP_DT!)   :  !BACKUP_STATUS!
echo     %USERPROFILE%\.claude\settings.json
echo     %USERPROFILE%\.claude\hooks\pet_hooks_handler.py
echo     (statusline.js khong backup -- khong phai user config)
echo.
echo   [1/6] Thu muc cai dat          :  OK
echo   [2/6] Backup .claude files     :  !BACKUP_STATUS!
echo   [3/6] Copy files               :  !COPY_STATUS!
echo   [4/6] Cap nhat settings.json   :  !SETTINGS_STATUS!
echo   [5/6] Restart pet              :  !PET_STATUS!
echo   [6/6] Test suite               :  !TEST_STATUS!
echo.

if !ERRORS! EQU 0 (
    if !TEST_EXIT! EQU 0 (
        echo   >> HOAN TAT -- Khong co loi.
    ) else (
        echo   >> CANH BAO -- Copy/config OK nhung test suite bao loi.
    )
) else (
    echo   >> THAT BAI -- Co !ERRORS! loi trong qua trinh update.
)

echo.
echo   Admin Panel  :  http://127.0.0.1:7007/ui
echo   Test lai     :  python "%INSTALL_DIR%\pet_test.py"
echo   Luu y        :  Restart Claude Code neu day la lan dau cai hooks.
echo.
echo   ======================================================
echo.
echo   Nhan Enter de dong cua so...
pause >nul
goto :eof


REM ── Backup mot file (bo qua neu khong ton tai) ────────────────────────────────
:backup_file
set "_BP=%~1"
set "_BN=%~nx1"
set "_BD=%~dp1"

if exist "!_BP!" (
    copy /Y "!_BP!" "!_BD!!_BN!.backup.!BACKUP_DT!" >nul 2>&1
    if errorlevel 1 (
        echo         [!!] Backup that bai: !_BN!
        set /a ERRORS+=1
    ) else (
        echo         OK  !_BN!.backup.!BACKUP_DT!
    )
) else (
    echo         .   !_BN!  -- chua ton tai, bo qua
)
goto :eof


REM ── Copy mot file tu SCRIPT_DIR va bao loi ────────────────────────────────────
:copyfile
set "_FNAME=%~1"
set "_DST=%~2"

copy /Y "%SCRIPT_DIR%%_FNAME%" "%_DST%" >nul 2>&1
if errorlevel 1 (
    echo         [!!] !_FNAME!  -- KHONG copy duoc
    set /a ERRORS+=1
) else (
    echo         OK  !_FNAME!
)
goto :eof
