#Requires -Version 3
<#
.SYNOPSIS
    Claude Pet one-liner installer.
    irm https://raw.githubusercontent.com/ghien-dev/claude-pet/master/install.ps1 | iex

.PARAMETER Dev
    Copy files from local repo dir instead of downloading (for local testing).
    Usage: & .\install.ps1 -Dev
#>
param([switch]$Dev)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# TLS 1.2 cho Windows 10 cu
[System.Net.ServicePointManager]::SecurityProtocol = [System.Net.SecurityProtocolType]::Tls12

$BASE_URL  = 'https://raw.githubusercontent.com/ghien-dev/claude-pet/master'
$LOCAL_SRC = if ($Dev) { $PSScriptRoot } else { $null }
$INSTALL   = "$env:USERPROFILE\.claude-pet"
$HOOKS_DIR = "$env:USERPROFILE\.claude\hooks"
$STARTUP   = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup"

function Write-Step($msg) { Write-Host "  $msg" -ForegroundColor Cyan }
function Write-OK($msg)   { Write-Host "  OK  $msg" -ForegroundColor Green }
function Write-Err($msg)  { Write-Host "  ERR $msg" -ForegroundColor Red }

function Download($file, $dest) {
    if ($LOCAL_SRC) {
        Copy-Item -Path "$LOCAL_SRC\$file" -Destination $dest -Force
    } else {
        Invoke-WebRequest -Uri "$BASE_URL/$file" -OutFile $dest -UseBasicParsing
    }
}

try {
    Write-Host ""
    Write-Host "Claude Pet installer" -ForegroundColor Magenta
    Write-Host "--------------------" -ForegroundColor DarkGray

    # 1. Kiem tra Python
    Write-Step "Checking Python..."
    if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
        Write-Err "Python not found."
        Write-Host ""
        Write-Host "  Install Python 3 from https://python.org (check 'Add to PATH')" -ForegroundColor Yellow
        Write-Host "  Then re-run this installer." -ForegroundColor Yellow
        exit 1
    }
    $pyver = python --version 2>&1
    Write-OK $pyver

    # 2. Tao thu muc
    Write-Step "Creating directories..."
    New-Item -ItemType Directory -Force $INSTALL   | Out-Null
    New-Item -ItemType Directory -Force $HOOKS_DIR | Out-Null
    Write-OK "$INSTALL"
    Write-OK "$HOOKS_DIR"

    # 3. Download files
    Write-Step "Downloading files..."

    $files = @(
        @{ src = 'pet.py';                  dst = "$INSTALL\pet.py" },
        @{ src = 'pet_admin.html';          dst = "$INSTALL\pet_admin.html" },
        @{ src = 'pet_ui.py';               dst = "$INSTALL\pet_ui.py" },
        @{ src = 'pet_test.py';             dst = "$INSTALL\pet_test.py" },
        @{ src = 'pet_update_settings.py';  dst = "$INSTALL\pet_update_settings.py" },
        @{ src = 'pet_hooks_handler.py';    dst = "$HOOKS_DIR\pet_hooks_handler.py" },
        @{ src = 'statusline.js';           dst = "$env:USERPROFILE\.claude\statusline.js" }
    )

    foreach ($f in $files) {
        Download $f.src $f.dst
        Write-OK $f.src
    }

    # pet_sounds.json: chi download neu chua ton tai (giu config cu)
    $soundsDst = "$INSTALL\pet_sounds.json"
    if (-not (Test-Path $soundsDst)) {
        Download 'pet_sounds.json' $soundsDst
        Write-OK 'pet_sounds.json'
    } else {
        Write-Host "  SKIP pet_sounds.json (existing config preserved)" -ForegroundColor DarkGray
    }

    # 4. Cai Pillow
    Write-Step "Installing Pillow..."
    python -m pip install --quiet Pillow
    Write-OK "Pillow"

    # 5. Wire Claude Code hooks
    Write-Step "Wiring Claude Code hooks..."
    python "$INSTALL\pet_update_settings.py"
    Write-OK "hooks wired in ~\.claude\settings.json"

    # 6. Tao autostart
    Write-Step "Registering autostart..."
    $startBat = "$STARTUP\ClaudePet.bat"
    Set-Content -Path $startBat -Value "@echo off`r`npythonw `"$INSTALL\pet.py`""
    Write-OK $startBat

    # 7. Launch pet
    Write-Step "Launching Claude Pet..."
    # Tat instance cu neu dang chay
    $old = Get-WmiObject Win32_Process -Filter "Name='pythonw.exe'" |
           Where-Object { $_.CommandLine -like "*claude-pet*" }
    if ($old) {
        $old | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
        Start-Sleep -Milliseconds 800
    }
    Start-Process pythonw -ArgumentList "`"$INSTALL\pet.py`""
    Start-Sleep -Seconds 2

    # Kiem tra health
    try {
        $resp = Invoke-WebRequest -Uri 'http://127.0.0.1:7007' -UseBasicParsing -TimeoutSec 3
        Write-OK "pet running (HTTP $($resp.StatusCode))"
    } catch {
        Write-Host "  WARN pet may still be starting up" -ForegroundColor Yellow
    }

    # Done
    Write-Host ""
    Write-Host "Claude Pet installed!" -ForegroundColor Green
    Write-Host ""
    Write-Host "  Widget : floating circle on your desktop" -ForegroundColor White
    Write-Host "  Admin  : http://localhost:7007/ui" -ForegroundColor White
    Write-Host "  Next   : restart Claude Code for hooks to take effect" -ForegroundColor Yellow
    Write-Host ""

} catch {
    Write-Host ""
    Write-Err "Installation failed: $_"
    Write-Host ""
    exit 1
}
