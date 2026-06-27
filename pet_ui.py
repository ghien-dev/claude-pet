#!/usr/bin/env python3
"""
pet_ui.py — Mở Claude Pet Admin Panel trong browser.
Admin UI được serve bởi pet.py tại http://127.0.0.1:7007/ui
"""
import sys
import urllib.request
import webbrowser

PET_URL = "http://127.0.0.1:7007"

if __name__ == "__main__":
    try:
        urllib.request.urlopen(PET_URL, timeout=2)
    except Exception:
        print("[claude-pet-ui] ERROR: pet.py chua chay tren :7007")
        print(f'  Khoi dong: pythonw "%USERPROFILE%\\.claude-pet\\pet.py"')
        sys.exit(1)
    url = PET_URL + "/ui"
    print(f"[claude-pet-ui] Opening: {url}")
    webbrowser.open(url)
