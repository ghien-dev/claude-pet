# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

Claude Pet is a tiny floating Windows desktop widget that reflects Claude Code's live activity state through color and animation. It has two runtime components: a Tkinter GUI process (`pet.py`) and a Claude Code hook handler (`hooks_handler.py`).

## Files

| File | Installed to | Role |
|---|---|---|
| `pet.py` | `%USERPROFILE%\.claude-pet\` | Tkinter widget + HTTP server :7007 |
| `pet_hooks_handler.py` | `%USERPROFILE%\.claude\hooks\` | Claude Code hook → HTTP bridge |
| `pet_ui.py` | `%USERPROFILE%\.claude-pet\` | Web control panel :7008 |
| `pet_sounds.json` | `%USERPROFILE%\.claude-pet\` | Sounds config (hot-reload, không cần restart pet) |
| `pet_test.py` | `%USERPROFILE%\.claude-pet\` | Test suite — chạy độc lập hoặc qua update.bat |
| `settings.json` | project ref | Hook wiring reference (applied by install/update) |

`hooks_handler.py` is superseded by `pet_hooks_handler.py` — can be deleted.

## Commands

**Install (chạy lần đầu):**
```bat
install.bat
```

**Update + restart (sau mỗi lần sửa file):**
```bat
update.bat
```
Copies all files to install dirs, updates `~\.claude\settings.json`, restarts pet.

**Control Panel (test states + sửa sounds config):**
```powershell
python "$env:USERPROFILE\.claude-pet\pet_ui.py"
# hoặc từ project dir:
python pet_ui.py
```
Mở browser tại `http://localhost:7008`.

**Chạy test suite độc lập:**
```powershell
python pet_test.py
# hoặc từ install dir:
python "$env:USERPROFILE\.claude-pet\pet_test.py"
```

**Khởi động pet thủ công:**
```powershell
pythonw "$env:USERPROFILE\.claude-pet\pet.py"
```

**Test state thủ công qua CLI:**
```powershell
python -c "import urllib.request,json; urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:7007', json.dumps({'state':'attention_done'}).encode(), {'Content-Type':'application/json'}, 'POST'))"
```
Valid states: `idle | thinking | editing | running | success | error | attention_done | attention_notify`

**Uninstall:**
```bat
rmdir /s /q "%USERPROFILE%\.claude-pet"
del "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\ClaudePet.bat"
```
Xóa block `hooks` trong `%USERPROFILE%\.claude\settings.json`.

## Architecture

```
Claude Code runtime
    │  fires hook events (PreToolUse / PostToolUse / Stop / UserPromptSubmit / Notification)
    ▼
hooks_handler.py   — installed at %USERPROFILE%\.claude\hooks\hooks_handler.py
    │  reads JSON event from stdin, maps tool/event name → state string
    │  HTTP POST { state, flash_ms } → localhost:7007
    ▼
pet.py             — runs as a separate pythonw process
    │  HTTPServer thread on 127.0.0.1:7007 receives state updates
    │  calls pet.set_state() via root.after(0, ...) (thread-safe Tkinter dispatch)
    ▼
PetWidget (Tkinter)
    └── 80ms animation tick loop draws pulse/spin/flash per state
```

### State machine

| State | Trigger | Visual | Behavior |
|---|---|---|---|
| `idle` | default / watchdog timeout | grey slow breathe | stays at corner |
| `thinking` | Read/Glob/Grep/WebSearch/UserPromptSubmit | orange pulse | corner |
| `editing` | Write/Edit/MultiEdit/NotebookEdit/TodoWrite | blue pulse | corner |
| `running` | Bash/Task | purple spinning ring | corner |
| `success` | manual | green flash 4 s → idle | corner |
| `error` | manual | red flash 4 s → idle | corner |
| `attention_done` | **Stop / SubagentStop** | green glow pulse | **slides to center → bounce** |
| `attention_notify` | **Notification** | orange glow pulse | **slides to center → bounce** |

**Attention mode** (`attention_done` / `attention_notify`):
- Pet slides to screen center with ease-out animation (~500ms)
- Bounces continuously at center to draw attention
- Hover over pet → bounce pauses, pet snaps to exact center
- Mouse leaves → bounce resumes
- **Left-click → slides back to original corner, state → idle**
- New Claude event (e.g. next prompt) → cancels attention, teleports back to corner

`ACTIVE_TIMEOUT_S = 45` — if a thinking/editing/running state receives no new event for 45 seconds, the widget auto-resets to idle.

### Sound config (`SOUNDS` dict in `pet.py`)

```python
SOUNDS = {
    "attention_done":   "SystemAsterisk",    # thay bằng r"C:\path\to\done.wav" nếu muốn
    "attention_notify": "SystemExclamation",
}
```
Giá trị hợp lệ: tên Windows system sound (`SystemAsterisk`, `SystemExclamation`, `SystemHand`, `SystemNotification`, `Mail`) hoặc đường dẫn tuyệt đối tới file `.wav`. Để tắt âm thanh cho một sự kiện, đặt giá trị `""` hoặc `None`.

### HTTP API (`pet.py` server on port 7007)

- `POST /` — `{"state": "<state>", "flash_ms": 0}` — sets state; `flash_ms > 0` returns to idle after that many milliseconds
- `GET /`  — returns `{"state": "<current>"}` for health checks

`hooks_handler.py` always exits 0 and swallows HTTP errors so a stopped pet never blocks Claude.

### Window

- Transparent chroma-key background (`#010101`) — makes the circle appear to float
- `overrideredirect(True)` removes the title bar; `-topmost True` keeps it above all windows
- Left-drag to reposition; right-click for Hide / Reset idle / Quit
