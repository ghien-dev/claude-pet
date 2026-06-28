# Claude Pet

A tiny floating Windows desktop widget that reflects [Claude Code](https://claude.ai/code)'s live activity state through color and animation.

![States: grey idle → orange thinking → blue editing → purple running → green done → attention bounce]

---

## What it looks like

| State | Color | Trigger |
|---|---|---|
| `idle` | ● Grey slow breathe | Default / watchdog timeout |
| `thinking` | ◉ Orange pulse | Reading files, searching, web fetch |
| `editing` | ✎ Blue pulse | Writing / editing files |
| `running` | ▶ Purple spinning ring | Bash / Task agent |
| `success` | ✓ Green flash 4 s → idle | Manual trigger |
| `error` | ✕ Red flash 4 s → idle | Manual trigger |
| `attention_done` | ✓ Green glow + **slides to center + bounces** | Claude finishes a turn (Stop / SubagentStop) |
| `attention_notify` | ! Orange glow + **slides to center + bounces** | Claude sends a Notification |

**Attention mode** — when Claude finishes or sends a notification, the pet slides from its corner to the center of the screen and bounces to get your attention. Left-click it to dismiss and slide back. Any new Claude activity also cancels attention mode automatically.

The widget also shows your **Claude usage** overlaid on the pet:
- **7-day ring** — an arc around the circle showing your 7-day token usage (green → yellow → red)
- **5-hour bar** — a thin bar below the circle for the 5-hour rolling window

---

## Requirements

- Windows 10/11
- Python 3.x (from [python.org](https://python.org) — includes tkinter by default)
- [Claude Code](https://claude.ai/code) installed

---

## Install

**One-liner (không cần clone repo):**

```powershell
irm https://raw.githubusercontent.com/ghien-dev/claude-pet/main/install.ps1 | iex
```

**Hoặc clone repo về rồi chạy:**

```bat
install.bat
```

Cả hai đều:
1. Cài `Pillow`
2. Copy files vào `%USERPROFILE%\.claude-pet\`
3. Copy hook handler vào `%USERPROFILE%\.claude\hooks\`
4. Đăng ký tự khởi động cùng Windows
5. Wire Claude Code hooks trong `%USERPROFILE%\.claude\settings.json`
6. Khởi động widget ngay

Sau khi cài: **restart Claude Code** để hooks có hiệu lực.

---

## After updating source files

```bat
update.bat
```

Copies all files to the install directories, updates `settings.json` hooks, and restarts the pet automatically.

---

## Admin panel

The pet serves a web UI at **http://localhost:7007/ui** — open it via:
- Right-click the pet → **Open Admin Panel**
- Or run `python pet_ui.py` from the project dir

The admin panel lets you:
- Trigger any state manually (for testing)
- Edit sound config live (hot-reload, no restart needed)
- Browse the signal log (searchable, filterable by state)

---

## Sound config

Sounds are stored in `pet_sounds.json` (hot-reloaded on every play — no restart needed):

```json
{
  "attention_done":   "SystemAsterisk",
  "attention_notify": "SystemExclamation"
}
```

Valid values: Windows system sound alias (`SystemAsterisk`, `SystemExclamation`, `SystemHand`, `SystemNotification`, `Mail`) or an absolute path to a `.wav` file. Set to `""` or `null` to silence an event.

You can also edit sounds live from the Admin Panel.

---

## Architecture

```
Claude Code runtime
    │  fires hook events
    │  (PreToolUse / PostToolUse / Stop / SubagentStop / UserPromptSubmit / Notification)
    ▼
pet_hooks_handler.py   ← %USERPROFILE%\.claude\hooks\
    │  reads JSON event from stdin
    │  maps tool/event → state string
    │  HTTP POST { state, project, ... } → localhost:7007
    ▼
pet.py                 ← %USERPROFILE%\.claude-pet\  (pythonw, background process)
    │  ThreadingHTTPServer on 127.0.0.1:7007
    │  thread-safe state dispatch via root.after(0, ...)
    ▼
PetWidget (Tkinter + PIL + UpdateLayeredWindow)
    └── 30ms animation tick — renders RGBA frame via Windows layered window API
```

The widget renders with true per-pixel alpha via `UpdateLayeredWindow` — no chroma-key, the glow and circle blend cleanly over any background.

---

## HTTP API

`pet.py` exposes a small HTTP API on port **7007**:

| Method | Path | Description |
|---|---|---|
| `POST /` | `{"state": "...", "flash_ms": 0, "project": "..."}` | Set state. `flash_ms > 0` returns to idle after N ms. |
| `GET /` | — | Returns `{"state": "<current>"}` |
| `GET /ui` | — | Admin panel HTML |
| `GET /logs` | `?state=&q=&sort=&limit=&offset=` | Signal log (JSON) |
| `DELETE /logs` | — | Clear log |
| `GET /sounds` | — | Current sounds config |
| `POST /sounds` | `{"attention_done": "...", ...}` | Save sounds config |

Valid states: `idle | thinking | editing | running | success | error | attention_done | attention_notify`

**Quick test from PowerShell:**
```powershell
python -c "import urllib.request,json; urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:7007', json.dumps({'state':'attention_done'}).encode(), {'Content-Type':'application/json'}, 'POST'))"
```

---

## Files

| File | Installed to | Role |
|---|---|---|
| `pet.py` | `%USERPROFILE%\.claude-pet\` | Tkinter widget + HTTP server :7007 |
| `pet_hooks_handler.py` | `%USERPROFILE%\.claude\hooks\` | Claude Code hook → HTTP bridge |
| `pet_admin.html` | `%USERPROFILE%\.claude-pet\` | Admin panel UI (served by pet.py) |
| `pet_sounds.json` | `%USERPROFILE%\.claude-pet\` | Sound config (hot-reload) |
| `pet_ui.py` | `%USERPROFILE%\.claude-pet\` | Helper: opens admin panel in browser |
| `pet_test.py` | `%USERPROFILE%\.claude-pet\` | Test suite |
| `install.bat` | project dir | First-time installer |
| `update.bat` | project dir | Update + restart |

---

## Interaction

- **Left-drag** — move the pet to any position
- **Left-click** (in attention mode) — dismiss, slide back to corner
- **Right-click** — Hide / Reset idle / Open Admin Panel / Quit
- **Hover** (in attention mode) — pause bounce, snap to exact center

The pet auto-resets to idle if `thinking / editing / running` receives no new event for **45 seconds** (watchdog).

---

## Uninstall

```bat
rmdir /s /q "%USERPROFILE%\.claude-pet"
del "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\ClaudePet.bat"
```

Then remove the `hooks` block from `%USERPROFILE%\.claude\settings.json`.
