"""
Claude Pet - Floating desktop widget for Windows
Nhận trạng thái qua HTTP (localhost:7007) và hiển thị icon nổi góc màn hình.

States: idle | thinking | editing | running | success | error | attention_done | attention_notify
"""

import tkinter as tk
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import threading
import json
import math
import time
import sys
import os
import winsound
import collections
import ctypes
from ctypes import wintypes
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageChops
from urllib.parse import urlparse, parse_qs

# ── Sounds config (đọc từ file mỗi lần play — hot-reload từ UI không cần restart) ──
SOUNDS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pet_sounds.json")
DEFAULT_SOUNDS = {
    "attention_done":   "SystemAsterisk",
    "attention_notify": "SystemExclamation",
}

# ── Usage tracking ────────────────────────────────────────────────────────────
USAGE_FILE = os.path.join(os.environ.get("USERPROFILE", os.path.expanduser("~")),
                          ".claude", "usage_state.json")
DIAG_XBM = "#define d_width 4\n#define d_height 4\nstatic char d_bits[] = {0x01,0x02,0x04,0x08};"

# ── Signal log (newest first, max 1000 entries) ────────────────────────────────
_signal_log  = collections.deque(maxlen=1000)
_log_counter = 0
_log_lock    = threading.Lock()

# ── Màu & emoji theo trạng thái ──────────────────────────────────────────────
STATES = {
    "idle":             {"color": "#4a4a5a", "glow": "#6b6b8a", "label": "●",  "text": "Idle"},
    "thinking":         {"color": "#f59e0b", "glow": "#fbbf24", "label": "◉",  "text": "Thinking..."},
    "editing":          {"color": "#3b82f6", "glow": "#60a5fa", "label": "✎",  "text": "Editing..."},
    "running":          {"color": "#8b5cf6", "glow": "#a78bfa", "label": "▶",  "text": "Running..."},
    "success":          {"color": "#10b981", "glow": "#34d399", "label": "✓",  "text": "Done!"},
    "error":            {"color": "#ef4444", "glow": "#f87171", "label": "✕",  "text": "Error!"},
    "attention_done":   {"color": "#10b981", "glow": "#34d399", "label": "✓",  "text": "Done! Click me"},
    "attention_notify": {"color": "#f59e0b", "glow": "#fbbf24", "label": "!",  "text": "Your turn!"},
}


GLOW_MARGIN      = 20   # px lề quanh layout 84 để glow fade hết (không bị cắt vuông)
WINDOW_SIZE      = 84 + 2 * GLOW_MARGIN   # 124px — layout cũ + lề glow
CORNER_MARGIN    = 20   # px
ACTIVE_TIMEOUT_S = 45   # giây không có event → tự về idle (watchdog)


class PetWidget:
    def __init__(self):
        self.root = tk.Tk()
        self.state = "idle"
        self.anim_tick = 0
        self.flash_until = 0
        self.last_event_time = 0

        self._project = ""

        # Usage data
        self._usage = {
            "seven_day_pct": 0.0, "seven_day_progress": 0.0,
            "five_hour_pct": 0.0,  "five_hour_progress": 0.0,
        }

        # Attention mode
        self._attention_mode = False
        self._bouncing = False
        self._hover = False
        self._sliding = False
        self._home_pos = None       # (x, y) lưu vị trí góc để quay về
        self._center_pos = None     # (x, y) tọa độ giữa màn hình (fixed)

        # Drag tracking
        self._drag_x = 0
        self._drag_y = 0
        self._drag_moved = False

        self._setup_window()
        self._build_ui()
        self._setup_input()
        self._position_window()
        self._setup_layered()
        self._poll_usage()
        self._tick()

    # ── Window setup ──────────────────────────────────────────────────────────
    def _setup_window(self):
        r = self.root
        r.overrideredirect(True)
        r.attributes("-topmost", True)
        r.configure(bg="#000000")
        r.resizable(False, False)
        r.geometry(f"{WINDOW_SIZE}x{WINDOW_SIZE}")

    def _position_window(self):
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x  = sw - WINDOW_SIZE - CORNER_MARGIN
        y  = sh - WINDOW_SIZE - CORNER_MARGIN - 48  # above taskbar
        self.root.geometry(f"{WINDOW_SIZE}x{WINDOW_SIZE}+{x}+{y}")

    # ── UI (menu only — vẽ bằng PIL + layered window, không dùng Canvas) ─────────
    def _build_ui(self):
        self.menu = tk.Menu(self.root, tearoff=0)
        self.menu.add_command(label="Open Admin Panel", command=self._open_ui)
        self.menu.add_separator()
        self.menu.add_command(label="Hide",       command=self.root.withdraw)
        self.menu.add_command(label="Reset idle", command=self._reset_idle)
        self.menu.add_separator()
        self.menu.add_command(label="Quit",       command=self.root.destroy)
        self.root.bind("<Button-3>", self._show_menu)

    def _setup_layered(self):
        """Bật WS_EX_LAYERED để dùng UpdateLayeredWindow (alpha thật từng pixel)."""
        self.root.update_idletasks()
        self.root.update()
        hwnd = _user32.GetAncestor(self.root.winfo_id(), GA_ROOT)
        ex = _user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        _user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex | WS_EX_LAYERED)
        self._hwnd = hwnd

    # ── Input ─────────────────────────────────────────────────────────────────
    def _setup_input(self):
        self.root.bind("<ButtonPress-1>",   self._on_press)
        self.root.bind("<B1-Motion>",       self._on_drag)
        self.root.bind("<ButtonRelease-1>", self._on_release)
        self.root.bind("<Enter>",           self._on_hover_enter)
        self.root.bind("<Leave>",           self._on_hover_leave)

    def _on_press(self, e):
        self._drag_x = e.x
        self._drag_y = e.y
        self._drag_moved = False

    def _on_drag(self, e):
        if self._attention_mode or self._sliding:
            return
        dx = e.x - self._drag_x
        dy = e.y - self._drag_y
        if abs(dx) > 3 or abs(dy) > 3:
            self._drag_moved = True
        x = self.root.winfo_x() + dx
        y = self.root.winfo_y() + dy
        self.root.geometry(f"+{x}+{y}")

    def _on_release(self, e):
        # Phân biệt click vs drag: nếu không di chuyển = click
        if not self._drag_moved and self._attention_mode:
            self._return_home()

    def _on_hover_enter(self, e):
        self._hover = True
        # Snap về đúng tâm khi hover (dừng bounce ngay gọn)
        if self._attention_mode and self._center_pos and not self._sliding:
            bx, by = self._center_pos
            self.root.geometry(f"+{bx}+{by}")

    def _on_hover_leave(self, e):
        self._hover = False

    def _show_menu(self, e):
        self.menu.tk_popup(e.x_root, e.y_root)

    def _open_ui(self):
        import webbrowser
        webbrowser.open("http://127.0.0.1:7007/ui")

    # ── Attention mode ────────────────────────────────────────────────────────
    def _enter_attention(self, state: str):
        """Gọi từ main thread (qua root.after). Slide vào giữa màn hình, bounce."""
        # Nếu đã trong attention mode thì giữ nguyên home_pos ban đầu
        if not self._attention_mode:
            self._home_pos = (self.root.winfo_x(), self.root.winfo_y())

        self._attention_mode = True
        self._bouncing = False
        self._hover = False
        self._sliding = True

        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        cx = sw // 2 - WINDOW_SIZE // 2
        cy = sh // 2 - WINDOW_SIZE // 2
        self._center_pos = (cx, cy)

        self._play_sound(state)
        self._slide_to(cx, cy, on_done=self._start_bounce)

    def _slide_to(self, tx: int, ty: int, steps: int = 20, on_done=None):
        """Ease-out slide animation (recursive via after)."""
        cx = self.root.winfo_x()
        cy = self.root.winfo_y()
        if steps <= 0 or (abs(tx - cx) < 2 and abs(ty - cy) < 2):
            self.root.geometry(f"+{tx}+{ty}")
            self._sliding = False
            if on_done:
                on_done()
            return
        # Ease-out: mỗi bước đi 1/3 khoảng còn lại
        nx = cx + (tx - cx) // 3
        ny = cy + (ty - cy) // 3
        self.root.geometry(f"+{nx}+{ny}")
        self.root.after(22, lambda: self._slide_to(tx, ty, steps - 1, on_done))

    def _start_bounce(self):
        self._bouncing = True

    def _return_home(self):
        """Slide về góc cũ và reset idle."""
        self._attention_mode = False
        self._bouncing = False
        self._sliding = True
        tx, ty = self._home_pos if self._home_pos else (
            self.root.winfo_screenwidth() - WINDOW_SIZE - CORNER_MARGIN,
            self.root.winfo_screenheight() - WINDOW_SIZE - CORNER_MARGIN - 48,
        )
        self._home_pos = None
        self.state = "idle"
        self._slide_to(tx, ty)

    def _reset_idle(self):
        """Right-click Reset idle — hoạt động trong và ngoài attention mode."""
        if self._attention_mode:
            self._return_home()
        else:
            self.set_state("idle")

    # ── Usage data ──────────────────────────────────────────────────────────────
    def _poll_usage(self):
        try:
            with open(USAGE_FILE, encoding="utf-8") as f:
                d = json.load(f)
            s7 = d.get("seven_day") or {}
            s5 = d.get("five_hour") or {}
            r7 = s7.get("resets_at_unix") or 0
            r5 = s5.get("resets_at_unix") or 0
            if not r7 and not r5:
                return
            now = time.time()
            if r7:
                self._usage["seven_day_pct"]      = float(s7.get("used_percentage") or 0)
                self._usage["seven_day_progress"]  = max(0.0, min(1.0, (now - (r7 - 7 * 86400)) / (7 * 86400)))
            if r5:
                self._usage["five_hour_pct"]       = float(s5.get("used_percentage") or 0)
                self._usage["five_hour_progress"]  = max(0.0, min(1.0, (now - (r5 - 5 * 3600)) / (5 * 3600)))
        except Exception:
            pass

    # ── State (thread-safe via root.after) ────────────────────────────────────
    def set_state(self, state: str, flash_ms: int = 0, project: str = ""):
        def _do():
            if state not in STATES:
                return
            self._poll_usage()
            self.last_event_time = time.time()
            if project:
                self._project = project

            if state in ("attention_done", "attention_notify"):
                self.state = state
                self._enter_attention(state)
                return

            # Nếu đang ở attention mode mà có event mới → hủy attention, về chỗ cũ
            if self._attention_mode:
                self._attention_mode = False
                self._bouncing = False
                self._sliding = False
                if self._home_pos:
                    hx, hy = self._home_pos
                    self._home_pos = None
                    self.root.geometry(f"+{hx}+{hy}")

            self.state = state
            if flash_ms > 0:
                self.flash_until = time.time() + flash_ms / 1000

        self.root.after(0, _do)

    # ── Sound ─────────────────────────────────────────────────────────────────
    def _play_sound(self, state: str):
        try:
            with open(SOUNDS_FILE, encoding="utf-8") as f:
                sounds = json.load(f)
        except Exception:
            sounds = DEFAULT_SOUNDS
        sound = sounds.get(state, "")
        if not sound:
            return
        try:
            flags = winsound.SND_ASYNC
            if sound.lower().endswith(".wav"):
                winsound.PlaySound(sound, flags | winsound.SND_FILENAME)
            else:
                winsound.PlaySound(sound, flags | winsound.SND_ALIAS)
        except Exception:
            pass

    # ── Animation loop (30ms tick) ────────────────────────────────────────────
    def _tick(self):
        self.anim_tick += 1
        t_s = time.time()

        if self.anim_tick % 2000 == 1:
            self._poll_usage()

        # Bounce: cửa sổ ĐỨNG YÊN ở giữa; cụm vòng tròn nảy trong bitmap (thanh 5H làm sàn).
        # Chỉ nảy khi đã tới giữa (không sliding) và không hover.
        bounce_px = 0.0
        if self._bouncing and not self._sliding and not self._hover:
            bounce_px = 14 * abs(math.sin(t_s * 4.0))

        # Flash → idle
        if self.flash_until and t_s > self.flash_until:
            self.flash_until = 0
            self.state = "idle"

        # Watchdog: active state stuck quá lâu
        if self.state in ("thinking", "editing", "running") and self.last_event_time:
            if t_s - self.last_event_time > ACTIVE_TIMEOUT_S:
                self.state = "idle"
                self.last_event_time = 0

        try:
            img = compose_frame(self.state, self._attention_mode,
                                self._project, self._usage, t_s, bounce_px)
            _push_layered(self._hwnd, img)
        except Exception:
            pass

        self.root.after(30, self._tick)

    def run(self):
        self.root.mainloop()


# ── PIL frame composition (full widget rendered to one RGBA image) ───────────
_FONT_DIR   = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
_FONT_CACHE = {}

def _font(kind: str, size: int):
    key = (kind, size)
    f = _FONT_CACHE.get(key)
    if f is not None:
        return f
    names = {
        "icon": ["seguisym.ttf", "segoeui.ttf"],   # ● ◉ ✎ ▶ ✓ ✕ glyphs
        "bold": ["segoeuib.ttf", "seguisym.ttf"],
        "reg":  ["segoeui.ttf"],
    }[kind]
    f = None
    for n in names:
        try:
            f = ImageFont.truetype(os.path.join(_FONT_DIR, n), size)
            break
        except Exception:
            continue
    if f is None:
        f = ImageFont.load_default()
    _FONT_CACHE[key] = f
    return f


def _draw_status(d, text, x, y, font, SS, t_s):
    """Vẽ status label: chữ căn giữa CỐ ĐỊNH; nếu text kết thúc '...' thì bỏ '...'
    và vẽ dấu chấm CHẠY ĐỘNG (./../...) bên phải → hiệu ứng 'đang chạy', không lệch."""
    white  = (255, 255, 255, 255)
    stroke = dict(stroke_width=max(1, SS), stroke_fill=(0, 0, 0, 170))
    if text.endswith("..."):
        word = text[:-3]
        d.text((x, y), word, font=font, fill=white, anchor="mm", **stroke)
        n = int(t_s * 2) % 4
        if n:
            wlen = d.textlength(word, font=font)
            d.text((x + wlen / 2, y), "." * n, font=font, fill=white,
                   anchor="lm", **stroke)
    else:
        d.text((x, y), text, font=font, fill=white, anchor="mm", **stroke)


def compose_frame(state: str, attention: bool, project: str, usage: dict,
                  t_s: float, bounce: float = 0.0):
    """Vẽ toàn bộ widget (glow + circle + spinner + ring + bar + text) vào 1 ảnh
    RGBA WINDOW_SIZE² với alpha thật. Render ở 2x rồi LANCZOS downscale → anti-alias.

    Layout gốc dùng hệ tọa độ 84px tâm (36,36); cộng GLOW_MARGIN (O) để chừa lề
    cho glow fade hết, không bị cắt vuông ở mép cửa sổ.

    `bounce` (px, ≥0): chỉ dùng ở attention — dịch CỤM vòng tròn lên trong bitmap,
    thanh 5H đứng yên làm "sàn" → cảm giác vòng tròn chạm thanh rồi nảy lên."""
    SS = 2
    O  = GLOW_MARGIN
    cc = 36 + O                 # tâm X nội dung (1x)
    W  = WINDOW_SIZE * SS
    CX = cc * SS

    s        = STATES[state]
    cr, cg, cb = _hex_to_rgb(s["color"])
    gr, gg, gb = _hex_to_rgb(s["glow"])

    if state == "thinking":
        intensity = 0.45 + 0.45 * math.sin(t_s * 2.25); base_r = 26; glow_extra = 6 + intensity * 5
    elif state == "editing":
        intensity = 0.45 + 0.45 * math.sin(t_s * 3.51); base_r = 26; glow_extra = 5 + intensity * 4
    elif state == "running":
        intensity = 0.7;                                base_r = 26; glow_extra = 9
    elif state in ("success", "error"):
        intensity = abs(math.sin(t_s * 4.39));          base_r = 26; glow_extra = 8 + intensity * 6
    elif state in ("attention_done", "attention_notify"):
        intensity = 0.5 + 0.5 * math.sin(t_s * 3.51);   base_r = 26; glow_extra = 9 + intensity * 7
    else:  # idle
        intensity = 0.2 + 0.1 * math.sin(t_s * 0.63);   base_r = 25; glow_extra = 4 + intensity * 2

    # Bounce: dịch cụm vòng tròn theo trục Y trong bitmap (thanh 5H đứng yên).
    # Lúc nghỉ (bounce=0): đáy ring (r=29) chạm mép trên thanh 5H (y=72.5) → DROP=7.5.
    gy  = (7.5 - bounce) if attention else 0.0
    cyc = cc + gy               # tâm Y của cụm vòng tròn (1x)
    CY  = cyc * SS

    img = Image.new("RGBA", (W, W), (0, 0, 0, 0))

    # ── GLOW: ellipse → GaussianBlur → fade ra alpha=0 (alpha thật, không khung) ──
    glow_alpha = int(min(220, 150 + intensity * 70))
    g_r = (base_r + glow_extra) * SS
    glow = Image.new("RGBA", (W, W), (gr, gg, gb, 0))
    ImageDraw.Draw(glow).ellipse([CX - g_r, CY - g_r, CX + g_r, CY + g_r],
                                 fill=(gr, gg, gb, glow_alpha))
    glow = glow.filter(ImageFilter.GaussianBlur(radius=9 * SS))
    img = Image.alpha_composite(img, glow)

    d = ImageDraw.Draw(img)

    # ── MAIN CIRCLE ──
    cr_px = base_r * SS
    d.ellipse([CX - cr_px, CY - cr_px, CX + cr_px, CY + cr_px], fill=(cr, cg, cb, 255))

    # ── SPIN ARC (running) ──
    if state == "running":
        ar = (base_r - 4) * SS
        spin = (t_s * 240) % 360
        d.arc([CX - ar, CY - ar, CX + ar, CY + ar],
              start=spin, end=spin + 270, fill=(gr, gg, gb, 255), width=4 * SS)

    # ── 7-day ring (luôn hiện) ──
    SEG = 360.0 / 7
    ring_bbox = [(cc - 29) * SS, (cyc - 29) * SS, (cc + 29) * SS, (cyc + 29) * SS]
    for i in range(7):
        a0 = (i * SEG - 90) % 360
        d.arc(ring_bbox, start=a0, end=a0 + (SEG - 2), fill=(37, 37, 53, 255), width=4 * SS)

    s7_pct  = usage.get("seven_day_pct", 0.0)
    s7_prog = usage.get("seven_day_progress", 0.0)
    if s7_pct > 0:
        uc = _hex_to_rgb(_usage_color(s7_pct))
        d.arc(ring_bbox, start=270, end=270 + s7_pct / 100.0 * 360,
              fill=(uc[0], uc[1], uc[2], 255), width=4 * SS)

    # tick marks (r=26→33)
    for i in range(7):
        ang = math.radians(90 - i * SEG)
        ca, sa = math.cos(ang), math.sin(ang)
        d.line([(cc + 26 * ca) * SS, (cyc - 26 * sa) * SS,
                (cc + 33 * ca) * SS, (cyc - 33 * sa) * SS],
               fill=(255, 255, 255, 110), width=SS)

    # day pointer (shadow + arrow)
    ang = math.radians(90 - s7_prog * 360)
    ca, sa = math.cos(ang), math.sin(ang)
    perp = ang + math.pi / 2
    pc, ps = math.cos(perp), math.sin(perp)
    tip  = (cc + 33 * ca, cyc - 33 * sa)
    base = (cc + 37 * ca, cyc - 37 * sa)
    dx, dy = 2.5 * pc, -2.5 * ps
    s_tip  = (cc + 32 * ca, cyc - 32 * sa)
    s_base = (cc + 38 * ca, cyc - 38 * sa)
    sdx, sdy = 3.5 * pc, -3.5 * ps
    d.polygon([(s_tip[0] * SS, s_tip[1] * SS),
               ((s_base[0] + sdx) * SS, (s_base[1] + sdy) * SS),
               ((s_base[0] - sdx) * SS, (s_base[1] - sdy) * SS)], fill=(0, 0, 0, 150))
    d.polygon([(tip[0] * SS, tip[1] * SS),
               ((base[0] + dx) * SS, (base[1] + dy) * SS),
               ((base[0] - dx) * SS, (base[1] - dy) * SS)], fill=(255, 255, 255, 255))

    # ── 5-hour bar (LUÔN hiện — kể cả attention; đứng yên làm "sàn" để vòng nảy lên) ──
    d.rectangle([(6 + O) * SS, (72.5 + O) * SS, (66 + O) * SS, (77.5 + O) * SS],
                fill=(37, 37, 53, 255), outline=(255, 255, 255, 255), width=SS)
    s5_pct  = usage.get("five_hour_pct", 0.0)
    s5_prog = usage.get("five_hour_progress", 0.0)
    x2 = 6 + s5_pct / 100.0 * 60
    if x2 > 6:
        uc5 = _hex_to_rgb(_usage_color(s5_pct))
        d.rectangle([(6 + O) * SS, (72.5 + O) * SS, (x2 + O) * SS, (77.5 + O) * SS],
                    fill=(uc5[0], uc5[1], uc5[2], 255))
    for k in range(1, 5):
        xx = (6 + k * 12 + O) * SS
        d.line([xx, (70 + O) * SS, xx, (80 + O) * SS], fill=(255, 255, 255, 110), width=SS)
    px = 6 + s5_prog * 60
    d.polygon([((px + O) * SS, (76.5 + O) * SS), ((px - 4 + O) * SS, (82.5 + O) * SS),
               ((px + 4 + O) * SS, (82.5 + O) * SS)], fill=(0, 0, 0, 150))
    d.polygon([((px + O) * SS, (77.5 + O) * SS), ((px - 3 + O) * SS, (81.5 + O) * SS),
               ((px + 3 + O) * SS, (81.5 + O) * SS)], fill=(255, 255, 255, 255))

    # ── Text (icon + label) — đều dịch theo gy (cùng cụm vòng tròn) ──
    if attention:
        proj = project
        if len(proj) > 11:
            proj = proj[:10] + "…"
        lbl = proj if proj else s["text"]
        d.text((cc * SS, (17 + O + gy) * SS), lbl, font=_font("bold", int(8 * SS * 1.5)),
               fill=(255, 255, 255, 255), anchor="mm")
        icon_y = 40
    else:
        _draw_status(d, s["text"], cc * SS, (48 + O + gy) * SS,
                     _font("bold", int(7 * SS * 1.5)), SS, t_s)
        icon_y = 30
    if state != "running":
        d.text((cc * SS, (icon_y + O + gy) * SS), s["label"], font=_font("icon", 22 * SS),
               fill=(255, 255, 255, 255), anchor="mm")

    return img.resize((WINDOW_SIZE, WINDOW_SIZE), Image.LANCZOS)


# ── Windows layered window (per-pixel alpha via UpdateLayeredWindow) ──────────
_user32 = ctypes.windll.user32
_gdi32  = ctypes.windll.gdi32

GWL_EXSTYLE   = -20
WS_EX_LAYERED = 0x00080000
ULW_ALPHA     = 0x02
GA_ROOT       = 2


class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
                ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD)]


class _BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", _BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]


class _BLENDFUNCTION(ctypes.Structure):
    _fields_ = [("BlendOp", ctypes.c_byte), ("BlendFlags", ctypes.c_byte),
                ("SourceConstantAlpha", ctypes.c_byte), ("AlphaFormat", ctypes.c_byte)]


_user32.GetAncestor.restype     = wintypes.HWND
_user32.GetAncestor.argtypes    = [wintypes.HWND, wintypes.UINT]
_user32.GetWindowLongW.restype  = wintypes.LONG
_user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
_user32.SetWindowLongW.restype  = wintypes.LONG
_user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.LONG]
_user32.GetDC.restype           = wintypes.HDC
_user32.GetDC.argtypes          = [wintypes.HWND]
_user32.ReleaseDC.argtypes      = [wintypes.HWND, wintypes.HDC]
_user32.UpdateLayeredWindow.restype  = wintypes.BOOL
_user32.UpdateLayeredWindow.argtypes = [
    wintypes.HWND, wintypes.HDC, ctypes.POINTER(wintypes.POINT),
    ctypes.POINTER(wintypes.SIZE), wintypes.HDC, ctypes.POINTER(wintypes.POINT),
    wintypes.DWORD, ctypes.POINTER(_BLENDFUNCTION), wintypes.DWORD]
_gdi32.CreateCompatibleDC.restype  = wintypes.HDC
_gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
_gdi32.CreateDIBSection.restype  = wintypes.HBITMAP
_gdi32.CreateDIBSection.argtypes = [
    wintypes.HDC, ctypes.POINTER(_BITMAPINFO), wintypes.UINT,
    ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD]
_gdi32.SelectObject.restype  = wintypes.HGDIOBJ
_gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
_gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
_gdi32.DeleteDC.argtypes     = [wintypes.HDC]


def _pil_to_bgra(img):
    """RGBA (straight) → premultiplied BGRA bytes (top-down) cho UpdateLayeredWindow."""
    r, g, b, a = img.split()
    r = ImageChops.multiply(r, a)
    g = ImageChops.multiply(g, a)
    b = ImageChops.multiply(b, a)
    return Image.merge("RGBA", (b, g, r, a)).tobytes("raw", "RGBA")


def _push_layered(hwnd, img):
    w, h = img.size
    data = _pil_to_bgra(img)
    screen = _user32.GetDC(None)
    memdc  = _gdi32.CreateCompatibleDC(screen)
    bmi = _BITMAPINFO()
    bmi.bmiHeader.biSize        = ctypes.sizeof(_BITMAPINFOHEADER)
    bmi.bmiHeader.biWidth       = w
    bmi.bmiHeader.biHeight      = -h          # top-down
    bmi.bmiHeader.biPlanes      = 1
    bmi.bmiHeader.biBitCount    = 32
    bmi.bmiHeader.biCompression = 0           # BI_RGB
    bits = ctypes.c_void_p()
    hbmp = _gdi32.CreateDIBSection(screen, ctypes.byref(bmi), 0, ctypes.byref(bits), None, 0)
    try:
        ctypes.memmove(bits, data, len(data))
        old = _gdi32.SelectObject(memdc, hbmp)
        size  = wintypes.SIZE(w, h)
        src   = wintypes.POINT(0, 0)
        blend = _BLENDFUNCTION(0, 0, 255, 1)  # AC_SRC_OVER, AC_SRC_ALPHA
        _user32.UpdateLayeredWindow(hwnd, screen, None, ctypes.byref(size),
                                    memdc, ctypes.byref(src), 0,
                                    ctypes.byref(blend), ULW_ALPHA)
        _gdi32.SelectObject(memdc, old)
    finally:
        _gdi32.DeleteObject(hbmp)
        _gdi32.DeleteDC(memdc)
        _user32.ReleaseDC(None, screen)


# ── Log & sounds helpers ─────────────────────────────────────────────────────
def _load_admin_html() -> str:
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pet_admin.html")
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except Exception:
        return "<html><body><p>pet_admin.html not found. Run update.bat.</p></body></html>"


def _append_log(state: str, flash_ms: int, payload: dict, source: str):
    global _log_counter
    with _log_lock:
        _log_counter += 1
        ts = time.time()
        ms = int(ts * 1000) % 1000
        dt = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts)) + f".{ms:03d}"
        _signal_log.appendleft({
            "id": _log_counter, "ts": ts, "dt": dt,
            "state": state, "flash_ms": flash_ms,
            "payload": payload, "source": source,
        })


def _read_sounds() -> dict:
    try:
        with open(SOUNDS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return dict(DEFAULT_SOUNDS)


def _write_sounds(sounds: dict):
    with open(SOUNDS_FILE, "w", encoding="utf-8") as f:
        json.dump(sounds, f, indent=2, ensure_ascii=False)


# ── HTTP server (:7007) ───────────────────────────────────────────────────────
def make_handler(pet: PetWidget):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a): pass

        def do_GET(self):
            path = self.path.split("?")[0]
            if path == "/":
                accept = self.headers.get("Accept", "")
                if "text/html" in accept:
                    self._redirect("/ui")
                else:
                    self._json(200, {"state": pet.state})
            elif path == "/ui":
                self._html(_load_admin_html())
            elif path == "/logs":
                self._serve_logs()
            elif path == "/sounds":
                self._json(200, _read_sounds())
            elif path == "/pet_status":
                self._json(200, {"state": pet.state})
            else:
                self._json(404, {"error": "not found"})

        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            body   = self.rfile.read(length)
            path   = self.path.split("?")[0]
            if path == "/":
                try:
                    data  = json.loads(body)
                    state   = data.get("state", "idle")
                    flash   = int(data.get("flash_ms", 0))
                    project = data.get("project", "")
                    _append_log(state, flash, data, self.client_address[0])
                    pet.set_state(state, flash, project)
                    self._json(200, {"ok": True, "state": state})
                except Exception as ex:
                    self._json(400, {"error": str(ex)})
            elif path == "/sounds":
                try:
                    _write_sounds(json.loads(body))
                    self._json(200, {"ok": True})
                except Exception as ex:
                    self._json(400, {"error": str(ex)})
            else:
                self._json(404, {"error": "not found"})

        def do_DELETE(self):
            if self.path.split("?")[0] == "/logs":
                with _log_lock:
                    _signal_log.clear()
                self._json(200, {"ok": True})
            else:
                self._json(404, {"error": "not found"})

        def do_OPTIONS(self):
            self.send_response(200)
            self.send_header("Allow", "GET, POST, DELETE, OPTIONS")
            self.end_headers()

        def _serve_logs(self):
            qs        = parse_qs(urlparse(self.path).query)
            state_str = qs.get("state", [None])[0]
            q         = (qs.get("q", [""])[0]).strip().lower()
            sort      = qs.get("sort",   ["desc"])[0]
            limit     = max(1, min(1000, int(qs.get("limit",  ["50"])[0])))
            offset    = max(0,           int(qs.get("offset", ["0"])[0]))
            with _log_lock:
                logs = list(_signal_log)
            if state_str:
                keep = set(state_str.split(","))
                logs = [l for l in logs if l["state"] in keep]
            if q:
                logs = [l for l in logs if q in l["state"] or q in json.dumps(l["payload"]).lower()]
            if sort == "asc":
                logs = list(reversed(logs))
            total = len(logs)
            self._json(200, {"logs": logs[offset:offset + limit], "total": total,
                             "offset": offset, "limit": limit})

        def _json(self, code: int, obj: dict):
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", len(body))
            self.end_headers()
            self.wfile.write(body)

        def _html(self, content: str):
            data = content.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", len(data))
            self.end_headers()
            self.wfile.write(data)

        def _redirect(self, location: str):
            self.send_response(302)
            self.send_header("Location", location)
            self.end_headers()

    return Handler


def start_server(pet: PetWidget, port: int = 7007):
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(pet))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print(f"[claude-pet] HTTP  :  http://127.0.0.1:{port}")
    print(f"[claude-pet] Admin :  http://127.0.0.1:{port}/ui")


# ── Helpers ───────────────────────────────────────────────────────────────────
def _usage_color(pct: float) -> str:
    if pct < 60: return "#34d399"
    if pct < 80: return "#fbbf24"
    return "#f87171"

def _hex_to_rgb(h: str):
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)

def _rgb_to_hex(r, g, b):
    return f"#{min(r,255):02x}{min(g,255):02x}{min(b,255):02x}"

def _blend_hex(c1: str, c2: str, t: float) -> str:
    r1, g1, b1 = _hex_to_rgb(c1)
    r2, g2, b2 = _hex_to_rgb(c2)
    return _rgb_to_hex(int(r1+(r2-r1)*t), int(g1+(g2-g1)*t), int(b1+(b2-b1)*t))


# ── Entry ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    pet = PetWidget()
    start_server(pet)
    pet.run()
