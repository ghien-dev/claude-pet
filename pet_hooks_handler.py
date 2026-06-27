#!/usr/bin/env python3
"""
pet_hooks_handler.py — Claude Code hook handler
Claude Code gọi file này qua stdin với JSON event data.

Đặt file này ở: ~/.claude/hooks/pet_hooks_handler.py
Cấu hình trong ~/.claude/settings.json (xem README hoặc chạy update.bat)
"""

import sys
import json
import os

PET_URL = "http://127.0.0.1:7007"

# Map tool name → pet state (dùng cho PreToolUse / PostToolUse)
TOOL_STATE_MAP = {
    # editing
    "Write":        "editing",
    "Edit":         "editing",
    "MultiEdit":    "editing",
    "NotebookEdit": "editing",
    "TodoWrite":    "editing",
    # running / testing
    "Bash":         "running",
    "Task":         "running",
    # thinking / reading
    "Read":         "thinking",
    "Glob":         "thinking",
    "Grep":         "thinking",
    "LS":           "thinking",
    "WebSearch":    "thinking",
    "WebFetch":     "thinking",
    "TodoRead":     "thinking",
    "MCP":          "thinking",
}

def send_state(state: str, flash_ms: int = 0, extra: dict = None):
    try:
        import urllib.request
        payload = {"state": state, "flash_ms": flash_ms}
        if extra:
            payload.update(extra)
        body = json.dumps(payload).encode()
        req  = urllib.request.Request(
            PET_URL,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        urllib.request.urlopen(req, timeout=1)
    except Exception:
        pass  # pet không chạy → bỏ qua hoàn toàn


def main():
    try:
        raw   = sys.stdin.read()
        event = json.loads(raw) if raw.strip() else {}
    except Exception:
        event = {}

    hook_name = event.get("hook_event_name", "")
    tool_name = event.get("tool_name", "")

    # Forward toàn bộ raw hook event; truncate tool_response để tránh log bloat
    fwd = dict(event)
    if isinstance(fwd.get("tool_response"), str) and len(fwd["tool_response"]) > 2000:
        fwd["tool_response"] = fwd["tool_response"][:2000] + "\n…[truncated]"

    meta = {
        **fwd,
        "project": os.path.basename(os.getcwd()),
        "cwd":     os.getcwd(),
        "hook":    hook_name,   # short alias cho UI
        "tool":    tool_name,   # short alias cho UI
    }

    if hook_name in ("Stop", "SubagentStop"):
        send_state("attention_done", extra=meta)

    elif hook_name == "UserPromptSubmit":
        send_state("thinking", extra=meta)

    elif hook_name in ("PreToolUse", "PostToolUse"):
        state = TOOL_STATE_MAP.get(tool_name, "thinking")
        send_state(state, extra=meta)

    elif hook_name == "Notification":
        send_state("attention_notify", extra=meta)

    # Luôn exit 0 — không block Claude
    sys.exit(0)


if __name__ == "__main__":
    main()
