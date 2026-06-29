#!/usr/bin/env python3
"""
pet_update_settings.py -- Cap nhat Claude hooks trong settings.json
Duoc goi boi update.bat.
Usage: python pet_update_settings.py [path/to/settings.json]
"""

import json
import os
import sys


def main():
    settings_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.expanduser("~"), ".claude", "settings.json"
    )

    hooks_dir = os.path.join(os.path.expanduser("~"), ".claude", "hooks")
    handler = os.path.join(hooks_dir, "pet_hooks_handler.py")
    hook_cmd = {
        "type": "command",
        "command": f'python "{handler}"',
    }
    entry = {"matcher": "", "hooks": [hook_cmd]}
    new_hooks = {
        "UserPromptSubmit": [entry],
        "PreToolUse":       [entry],
        "PostToolUse":      [entry],
        "Stop":             [entry],
        "SubagentStop":     [entry],
        "Notification":     [entry],
    }

    data = {}
    if os.path.exists(settings_path):
        with open(settings_path, encoding="utf-8") as f:
            data = json.load(f)

    old_keys = set(data.get("hooks", {}).keys())
    data["hooks"] = new_hooks
    new_keys = set(new_hooks.keys())

    statusline_js = os.path.join(os.path.expanduser("~"), ".claude", "statusline.js")
    data["statusLine"] = {
        "type": "command",
        "command": f'node "{statusline_js}"',
    }

    os.makedirs(os.path.dirname(settings_path), exist_ok=True)
    with open(settings_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    added   = new_keys - old_keys
    updated = new_keys & old_keys
    if added:   print("      + Them hooks:", ", ".join(sorted(added)))
    if updated: print("      . Cap nhat:  ", ", ".join(sorted(updated)))
    print("      OK statusLine:", statusline_js)
    print("      OK:", settings_path)


if __name__ == "__main__":
    main()
