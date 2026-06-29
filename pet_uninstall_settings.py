#!/usr/bin/env python3
"""
pet_uninstall_settings.py -- Xoa Claude hooks cua Claude Pet khoi settings.json
Duoc goi boi uninstall.bat.
Usage: python pet_uninstall_settings.py [path/to/settings.json]
"""

import json
import os
import sys


def main():
    settings_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.expanduser("~"), ".claude", "settings.json"
    )

    if not os.path.exists(settings_path):
        print("   settings.json khong ton tai, bo qua")
        return

    with open(settings_path, encoding="utf-8") as f:
        data = json.load(f)

    pet_key = "pet_hooks_handler.py"
    if "hooks" in data:
        for ev in list(data["hooks"]):
            entries = data["hooks"][ev]
            kept = [
                e for e in entries
                if not any(pet_key in h.get("command", "") for h in e.get("hooks", []))
            ]
            if kept:
                data["hooks"][ev] = kept
            else:
                del data["hooks"][ev]
        if not data["hooks"]:
            del data["hooks"]

    with open(settings_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    print("   Hooks da xoa khoi", settings_path)


if __name__ == "__main__":
    main()
