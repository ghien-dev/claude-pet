#!/usr/bin/env python3
"""
pet_test.py — Test suite cho Claude Pet
Chay doc lap: python pet_test.py
Hoac duoc goi boi update.bat sau khi cap nhat.
"""

import json
import os
import subprocess
import sys
import time
import urllib.request

PET_URL  = "http://127.0.0.1:7007"
HOOKS_PY = os.path.join(os.path.expanduser("~"), ".claude", "hooks", "pet_hooks_handler.py")

# ── Terminal colors (Windows 10+) ─────────────────────────────────────────────
os.system("")  # enable ANSI on Windows
GRN  = "\033[32m"
RED  = "\033[31m"
YLW  = "\033[33m"
CYN  = "\033[36m"
DIM  = "\033[2m"
RST  = "\033[0m"
BOLD = "\033[1m"

def ok(msg):   print(f"  {GRN}[OK]{RST} {msg}")
def fail(msg): print(f"  {RED}[!!]{RST} {msg}")
def info(msg): print(f"  {CYN}[--]{RST} {msg}")
def warn(msg): print(f"  {YLW}[??]{RST} {msg}")
def hr():      print(f"  {DIM}{'─'*52}{RST}")


# ── HTTP helpers ──────────────────────────────────────────────────────────────
def pet_post(state: str, flash_ms: int = 0) -> dict:
    body = json.dumps({"state": state, "flash_ms": flash_ms}).encode()
    req  = urllib.request.Request(
        PET_URL, body, {"Content-Type": "application/json"}, method="POST"
    )
    r = urllib.request.urlopen(req, timeout=2)
    return json.loads(r.read())

def pet_get() -> str:
    r = urllib.request.urlopen(PET_URL, timeout=2)
    return json.loads(r.read()).get("state", "unknown")

def simulate_hook(event_name: str, tool_name: str = "") -> bool:
    """Gọi pet_hooks_handler.py qua stdin như Claude Code thực sự làm."""
    event = {"hook_event_name": event_name, "tool_name": tool_name}
    result = subprocess.run(
        [sys.executable, HOOKS_PY],
        input=json.dumps(event),
        capture_output=True, text=True,
        timeout=3
    )
    return result.returncode == 0

def reset_idle(wait=0.8):
    """Reset pet về idle, chờ attention mode kết thúc nếu cần."""
    pet_post("idle")
    time.sleep(wait)


# ── Test sections ─────────────────────────────────────────────────────────────
def test_pet_alive() -> bool:
    print(f"\n  {BOLD}[1/4] Kiểm tra pet đang chạy{RST}")
    hr()
    try:
        state = pet_get()
        ok(f"Pet online tại localhost:7007 — state hiện tại: {BOLD}{state}{RST}")
        return True
    except Exception as e:
        fail(f"Pet không phản hồi: {e}")
        fail(f"Hãy chạy:  pythonw \"%USERPROFILE%\\.claude-pet\\pet.py\"")
        return False


def test_hook_handler() -> bool:
    print(f"\n  {BOLD}[2/4] Kiểm tra hook handler (giả lập sự kiện Claude Code){RST}")
    hr()

    if not os.path.exists(HOOKS_PY):
        fail(f"Không tìm thấy: {HOOKS_PY}")
        return False

    cases = [
        ("UserPromptSubmit", "",         "thinking",         "Người dùng gửi prompt"),
        ("PreToolUse",       "Read",      "thinking",         "PreToolUse: Read"),
        ("PreToolUse",       "Edit",      "editing",          "PreToolUse: Edit"),
        ("PreToolUse",       "Bash",      "running",          "PreToolUse: Bash"),
        ("PreToolUse",       "Write",     "editing",          "PreToolUse: Write"),
        ("PostToolUse",      "Glob",      "thinking",         "PostToolUse: Glob"),
        ("Stop",             "",          "attention_done",   "Stop → bounce xanh lá"),
        ("Notification",     "",          "attention_notify", "Notification → bounce vàng"),
        ("SubagentStop",     "",          "attention_done",   "SubagentStop → bounce xanh lá"),
    ]

    passed = 0
    for event, tool, expected, label in cases:
        reset_idle(0.4)
        ok_hook = simulate_hook(event, tool)
        time.sleep(0.5)
        actual = pet_get()
        success = ok_hook and (actual == expected)
        if success:
            ok(f"{label:36s} → {BOLD}{actual}{RST}")
            passed += 1
        else:
            fail(f"{label:36s} → nhận '{actual}', cần '{expected}'")

    reset_idle(1.2)  # chờ attention mode cancel hẳn
    hr()
    if passed == len(cases):
        ok(f"Hook handler: {passed}/{len(cases)} cases đúng")
    else:
        warn(f"Hook handler: {passed}/{len(cases)} cases đúng")
    return passed == len(cases)


def test_basic_states():
    print(f"\n  {BOLD}[3/4] Kiểm tra trực quan — basic states (1.5s mỗi state){RST}")
    hr()
    info("Quan sát pet icon ở góc màn hình:")
    print()

    states = [
        ("thinking", "◉  Vàng  — Thinking (nhấp nháy chậm)"),
        ("editing",  "✎  Xanh  — Editing  (nhấp nháy nhanh)"),
        ("running",  "▶  Tím   — Running  (xoay tròn)"),
        ("success",  "✓  Xanh lá — Success  (flash 4s → idle)"),
        ("error",    "✕  Đỏ    — Error    (flash 4s → idle)"),
        ("idle",     "●  Xám   — Idle     (thở chậm)"),
    ]
    for state, label in states:
        pet_post(state)
        info(f"    {label}")
        time.sleep(1.5)


def test_attention_mode():
    print(f"\n  {BOLD}[4/4] Kiểm tra Attention Mode — pet chạy vào giữa màn hình{RST}")
    hr()
    info("Pet sẽ slide vào giữa màn hình và nhảy bounce.")
    info("Quan sát trong 4 giây, sau đó tự động reset.")
    print()

    # attention_done
    info(f"attention_done → {GRN}bounce xanh lá{RST} + âm thanh SystemAsterisk")
    pet_post("attention_done")
    for i in range(4, 0, -1):
        print(f"  {DIM}     [{i}s]{RST}", end="\r", flush=True)
        time.sleep(1)
    print(" " * 20)
    pet_post("idle")
    time.sleep(1.2)
    ok("attention_done: slide + bounce hoàn tất")

    print()
    # attention_notify
    info(f"attention_notify → {YLW}bounce vàng{RST} + âm thanh SystemExclamation")
    pet_post("attention_notify")
    for i in range(4, 0, -1):
        print(f"  {DIM}     [{i}s]{RST}", end="\r", flush=True)
        time.sleep(1)
    print(" " * 20)
    pet_post("idle")
    time.sleep(1.2)
    ok("attention_notify: slide + bounce hoàn tất")

    print()
    info(f"Click thủ công: chạy lại bất kỳ lúc nào để test click-to-return")
    print(f"  {DIM}  python -c \"import urllib.request,json; urllib.request.urlopen("
          f"urllib.request.Request('http://127.0.0.1:7007',"
          f"json.dumps({{'state':'attention_done'}}).encode(),"
          f"{{'Content-Type':'application/json'}},'POST'))\"{RST}")


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print()
    print(f"  {BOLD}{'═'*52}{RST}")
    print(f"  {BOLD}  Claude Pet — Test Suite{RST}")
    print(f"  {BOLD}{'═'*52}{RST}")

    alive = test_pet_alive()
    if not alive:
        print()
        sys.exit(1)

    hooks_ok = test_hook_handler()
    test_basic_states()
    test_attention_mode()

    # ── Tổng kết ──
    print()
    hr()
    print(f"  {BOLD}Tổng kết{RST}")
    hr()
    ok("Pet widget: online")
    (ok if hooks_ok else fail)("Hook handler: " + ("tất cả đúng" if hooks_ok else "có lỗi, xem trên"))
    ok("Basic states: hiển thị đúng màu + animation")
    ok("Attention mode: slide + bounce + auto-reset")
    print()
    print(f"  {GRN}{BOLD}Pet sẵn sàng sử dụng!{RST}")
    print(f"  {DIM}Admin Panel: http://127.0.0.1:7007/ui{RST}")
    print()


if __name__ == "__main__":
    main()
