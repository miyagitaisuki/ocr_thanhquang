"""Widget dùng chung cho giao diện Tkinter: nút gradient, thanh tab, tip, vòng quay, mèo tiến trình.
Tách khỏi gui.py để test được phần không cần cửa sổ chính.
"""
from __future__ import annotations

import math
import tkinter as tk
from tkinter import font as tkfont, ttk

def _sc(widget, px: int) -> int:
    """Đổi kích thước thiết kế (px ở 96 DPI) sang pixel thật theo DPI màn hình (Tk scaling)."""
    return max(1, round(px * widget.tk.call("tk", "scaling") / (96 / 72)))


def _hex(c: str) -> tuple:
    return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))


def _mix(a: str, b: str, t: float) -> str:
    """Trộn màu a về phía b (t = 0..1)."""
    return "#%02X%02X%02X" % tuple(round(x + (y - x) * t) for x, y in zip(_hex(a), _hex(b)))


def _lum(c: str) -> float:
    r, g, b = _hex(c)
    return 0.299 * r + 0.587 * g + 0.114 * b


def _parent_bg(widget) -> str:
    """Màu nền của khung chứa gần nhất, để nút khớp nền (ttk không cho đọc trực tiếp)."""
    style = ttk.Style()
    w = widget
    while w is not None:
        cls = w.winfo_class()
        if cls in ("TFrame", "TLabelframe"):
            bg = style.lookup(str(w.cget("style")) or cls, "background")
        elif cls in ("Frame", "Canvas", "Tk", "Toplevel"):
            bg = w.cget("background")
        else:
            bg = ""
        if bg:
            return bg
        w = w.master
    return "#F4F5F7"


class GradientButton(tk.Canvas):
    """Nút chức năng có gradient dọc (ttk không hỗ trợ gradient). API giống ttk.Button: text, command, state, style.

    style "Run.TButton" -> xanh lá (Chạy OCR), "Accent.TButton" -> xanh dương, còn lại trung tính theo nền.
    width (px) đặt chiều rộng cố định; không đặt thì theo độ dài chữ.
    """

    VARIANTS = {"run": ("#34B25C", "#1B5E20", "#FFFFFF"), "accent": ("#5B9BFF", "#1F6FEB", "#FFFFFF"),
                "danger": ("#F2625C", "#B71C1C", "#FFFFFF"),
                "run_soft": ("#7FCB92", "#3E9A55", "#FFFFFF")}   # tab không được chọn: xanh nhạt hơn
    HEIGHT = 32
    RADIUS = 8   # bán kính góc bo tròn (px)
    ICON_W, ICON_GAP = 16, 8

    def __init__(self, master, text: str = "", command=None, state: str = "normal", style: str = "",
                 width: int | None = None, icon: str | None = None, **_):
        self._bg = _parent_bg(master)
        super().__init__(master, height=_sc(master, self.HEIGHT), highlightthickness=0, bd=0, bg=self._bg, cursor="hand2")
        self._text, self._command, self._state = text, command, state
        self._variant = ("run" if style.startswith("Run") else "accent" if style.startswith("Accent")
                         else "danger" if style.startswith("Danger") else "run_soft" if style.startswith("Soft")
                         else "neutral")
        self._icon = icon   # "stop": hình vuông trắng; "search": kính lúp
        self._font = tkfont.nametofont("TkDefaultFont")
        self._fixed_w = _sc(master, width) if width else None
        self._hover = self._down = False
        self._apply_width()
        self.bind("<Configure>", lambda e: self._draw())
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<ButtonRelease-1>", self._release)
        # bàn phím: Tab để tới nút, Enter hoặc Space để bấm
        self._focused = False
        self.configure(takefocus=1)
        self.bind("<FocusIn>", lambda e: self._set_focus(True))
        self.bind("<FocusOut>", lambda e: self._set_focus(False))
        self.bind("<Return>", self._key)
        self.bind("<space>", self._key)
        self._draw()

    def set_variant(self, variant: str):
        self._variant = variant
        self._draw()

    def _apply_width(self):
        extra = (self.ICON_W + self.ICON_GAP) if self._icon else 0
        tk.Canvas.configure(self, width=self._fixed_w or self._font.measure(self._text) + 36 + extra)

    def _colors(self) -> tuple[str, str, str]:
        """(đỉnh, đáy, chữ) theo biến thể, trạng thái và nền."""
        light = _lum(self._bg) > 128
        if self._state == "disabled" and self._variant == "danger":   # Dừng: đỏ nhạt, vẫn nhận ra là nút dừng
            return "#E8776F", "#C2453F", "#FFFFFF"
        if self._state == "disabled":
            top, bot, fg = ("#D9DDE3", "#C5CAD2", "#8A919C") if light else ("#3D434C", "#30353C", "#6B7280")
            return top, bot, fg
        if self._variant == "neutral":
            top = _mix(self._bg, "#FFFFFF", 0.75 if light else 0.18)
            bot = _mix(self._bg, "#000000", 0.14 if light else 0.35)
            fg = "#1F2328" if light else "#E6E8EC"
        else:
            top, bot, fg = self.VARIANTS[self._variant]
        if self._down:
            top, bot = _mix(top, "#000000", 0.15), _mix(bot, "#000000", 0.15)
        elif self._hover:
            top, bot = _mix(top, "#FFFFFF", 0.12), _mix(bot, "#FFFFFF", 0.12)
        return top, bot, fg

    def _draw(self):
        self.delete("all")
        w, h = max(1, self.winfo_width()), max(1, self.winfo_height())
        top, bot, fg = self._colors()
        r = min(_sc(self, self.RADIUS), h // 2, w // 2)
        for y in range(h):
            yc = y + 0.5   # bo góc: thu hẹp mỗi dòng theo cung tròn ở đầu và cuối nút
            if yc < r:
                inset = r - math.sqrt(max(0.0, r * r - (r - yc) ** 2))
            elif yc > h - r:
                inset = r - math.sqrt(max(0.0, r * r - (yc - (h - r)) ** 2))
            else:
                inset = 0
            self.create_line(inset, y, w - inset, y, fill=_mix(top, bot, y / max(1, h - 1)))
        icon_w = (self.ICON_W + self.ICON_GAP) if self._icon else 0
        x0 = (w - icon_w - self._font.measure(self._text)) / 2
        if self._icon:
            self._draw_icon(x0, h / 2, fg)
        self.create_text(x0 + icon_w, h / 2, text=self._text, fill=fg, font=self._font, anchor="w")
        if self._focused and self._state != "disabled":   # viền đứt khi nút đang có tiêu điểm bàn phím
            self.create_rectangle(4, 4, w - 4, h - 4, outline=fg, dash=(2, 2))

    def _set_focus(self, on: bool):
        self._focused = on
        self._draw()

    def _key(self, _e):
        if self._state != "disabled" and self._command:
            self._command()

    def _draw_icon(self, x: float, cy: float, color: str):
        if self._icon == "stop":
            self.create_rectangle(x + 2, cy - 6, x + 13, cy + 5, fill=color, outline="")
        elif self._icon == "search":
            self.create_oval(x + 1, cy - 8, x + 11, cy + 2, outline=color, width=2)
            self.create_line(x + 9, cy + 1, x + 14, cy + 6, fill=color, width=3, capstyle="round")

    def configure(self, cnf=None, **kw):
        kw = dict(cnf or {}, **kw)
        if "text" in kw:
            self._text = kw.pop("text")
            if self._fixed_w is None:
                self._apply_width()
        if "state" in kw:
            self._state = kw.pop("state")
        if "command" in kw:
            self._command = kw.pop("command")
        if kw:
            tk.Canvas.configure(self, **kw)
        self._draw()

    config = configure

    def cget(self, key):
        if key == "text":
            return self._text
        if key == "state":
            return self._state
        return tk.Canvas.cget(self, key)

    def _on_enter(self, _e):
        if self._state != "disabled":
            self._hover = True
            self._draw()

    def _on_leave(self, _e):
        self._hover = self._down = False
        self._draw()

    def _press(self, _e):
        if self._state != "disabled":
            self.focus_set()
            self._down = True
            self._draw()

    def _release(self, _e):
        if self._state == "disabled":
            return
        fire = self._down and self._hover
        self._down = False
        self._draw()
        if fire and self._command:
            self._command()


class GradientNotebook(tk.Frame):
    """Thanh tab bo tròn, gradient xanh như nút Chạy OCR. Chỉ có add() và select() như ttk.Notebook."""

    def __init__(self, master, **_):
        super().__init__(master, bg=_parent_bg(master), highlightthickness=0, bd=0)
        self._bar = tk.Frame(self, bg=self["bg"], highlightthickness=0, bd=0)
        self._bar.pack(fill="x", pady=(0, 10))
        self._body = tk.Frame(self, bg=self["bg"], highlightthickness=0, bd=0)
        self._body.pack(fill="both", expand=True)
        self._tabs: list[tuple[tk.Misc, GradientButton]] = []

    def add(self, child, text: str = ""):
        btn = GradientButton(self._bar, text=text.strip(), style="Soft.TButton",
                             command=lambda c=child: self.select(c))
        btn.pack(side="left", padx=(0, 8))
        self._tabs.append((child, btn))
        if len(self._tabs) == 1:
            self.select(child)

    def select(self, child):
        for c, b in self._tabs:
            b.set_variant("run" if c is child else "run_soft")
            c.pack_forget()
        child.pack(in_=self._body, fill="both", expand=True)

    def tabs(self) -> list:
        return [c for c, _ in self._tabs]


CAT_ORANGE = "#F2A03D"


class _CatMixin:
    """Mèo chạy trên đường ray dưới thanh tiến trình. Vẽ bằng Canvas, không cần file ảnh.

    Vị trí theo tiến trình OCR; chân đổi khung mỗi 130 ms khi đang chạy; về đích thì đứng cạnh cờ.
    """

    def _cat_init(self, parent, before):
        """Vùng mèo nằm ngay trên thanh tiến trình; chân mèo chạm mép trên thanh."""
        self.cat = tk.Canvas(parent, height=34, highlightthickness=0, bd=0, bg=_parent_bg(parent))
        self.cat.pack(fill="x", pady=(10, 0), before=before)
        self._cat_pos, self._cat_frame, self._cat_running, self._cat_job = 0.0, 0, False, None
        self._cat_finished = False
        self.cat.bind("<Configure>", lambda e: self._cat_draw())
        self.after(50, self._cat_draw)

    def _cat_start(self):
        self._cat_pos, self._cat_finished = 0.0, False
        self._cat_running = True
        self._cat_loop()

    def _cat_loop(self):
        if not self._cat_running:
            return
        self._cat_frame ^= 1
        self._cat_draw()
        self._cat_job = self.after(130, self._cat_loop)

    def _cat_move(self, frac: float):
        self._cat_pos = max(0.0, min(1.0, frac))
        self._cat_draw()

    def _cat_stop(self):
        """Hết việc: mèo về đích nếu không bị dừng giữa chừng."""
        self._cat_running = False
        if self._cat_job is not None:
            self.after_cancel(self._cat_job)
            self._cat_job = None
        self._cat_finished = not self.cancel.is_set()
        if self._cat_finished:
            self._cat_pos = 1.0
        self._cat_frame = 0
        self._cat_draw()

    def _cat_draw(self):
        c = self.cat
        c.delete("all")
        w = max(1, c.winfo_width())
        ground = max(10, c.winfo_height() - 1)   # mép trên thanh tiến trình
        # cờ về đích
        if self._cat_finished:
            c.create_line(w - 10, ground, w - 10, 4, fill=self.pal["MUTED"], width=2)
            c.create_polygon(w - 10, 4, w - 1, 8, w - 10, 12, fill="#2E7D32", outline="")
        x0 = 4 + (w - 64) * self._cat_pos
        bob = 0 if self._cat_finished or not self._cat_running else (1 if self._cat_frame else 0)
        y = ground - bob
        o = CAT_ORANGE
        # đuôi, thân, đầu, tai, mắt
        c.create_line(x0 + 9, y - 6, x0 + 2, y - 12, x0 + 1, y - 19, smooth=True, width=3, fill=o)
        c.create_oval(x0 + 8, y - 17, x0 + 37, y - 6, fill=o, outline="")
        c.create_oval(x0 + 30, y - 24, x0 + 46, y - 9, fill=o, outline="")
        c.create_polygon(x0 + 32, y - 22, x0 + 33, y - 30, x0 + 37, y - 23, fill=o, outline="")
        c.create_polygon(x0 + 39, y - 23, x0 + 42, y - 30, x0 + 44, y - 21, fill=o, outline="")
        c.create_oval(x0 + 40, y - 17, x0 + 43, y - 14, fill=self.pal["TEXT"], outline="")
        # chân: hai khung xen kẽ khi chạy, đứng yên khi về đích
        if self._cat_running and not self._cat_finished:
            a, b = ((x0 + 33, x0 + 37), (x0 + 13, x0 + 9)) if self._cat_frame == 0 else ((x0 + 33, x0 + 29), (x0 + 13, x0 + 17))
        else:
            a, b = ((x0 + 33, x0 + 37), (x0 + 13, x0 + 9))
        for fx, fy in (a, b):
            c.create_line(fx, y - 8, fy, ground, width=3, fill=o)


class Tip:
    """Chú thích khi di chuột vào: hiện sau 0,4 giây, ẩn khi rời chuột."""

    def __init__(self, widget, text: str):
        self.widget, self.text, self.win, self.job = widget, text, None, None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")

    def _schedule(self, _e):
        self._cancel()
        self.job = self.widget.after(400, self._show)

    def _cancel(self):
        if self.job:
            self.widget.after_cancel(self.job); self.job = None

    def _show(self):
        x = self.widget.winfo_rootx(); y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self.win = tk.Toplevel(self.widget); self.win.wm_overrideredirect(True); self.win.wm_geometry(f"+{x}+{y}")
        tk.Label(self.win, text=self.text, justify="left", wraplength=320, background="#1F2328", foreground="#FFFFFF",
                 padx=8, pady=5, font=("TkDefaultFont", 9)).pack()

    def _hide(self, _e):
        self._cancel()
        if self.win:
            self.win.destroy(); self.win = None


class Spinner(tk.Canvas):
    """Vòng tròn xoay báo đang làm việc. start()/stop(); stop() dừng xoay, còn hiện hay ẩn do người gọi quyết."""

    def __init__(self, master, size: int = 20, **kw):
        style = ttk.Style()
        bg = style.lookup("Card.TFrame", "background") or None
        fg = style.lookup("Accent.Horizontal.TProgressbar", "background") or "#2e7d32"
        super().__init__(master, width=size, height=size, highlightthickness=0, bd=0, bg=bg, **kw)
        pad = 3
        self._arc = self.create_arc(pad, pad, size - pad, size - pad, start=0, extent=270,
                                    style="arc", width=3, outline=fg)
        self._angle = 0
        self._job = None

    def start(self):
        if self._job is None:
            self._tick()

    def _tick(self):
        self._angle = (self._angle - 30) % 360
        self.itemconfigure(self._arc, start=self._angle)
        self._job = self.after(60, self._tick)

    def stop(self):
        if self._job is not None:
            self.after_cancel(self._job)
            self._job = None
