"""Giao diện Tkinter: thanh điều khiển đầu (Chạy, Dừng, tiến trình, phần cứng), bốn tab
(Tài liệu, Xử lý OCR, Rà soát, Kết quả), mẫu tài liệu, mục Nâng cao, xem trước trang,
thanh tiến trình khi tải engine AI (gói GPU, model Chandra).
"""
from __future__ import annotations

import importlib.util
import json
import logging
import math
import os
import queue
import subprocess
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, font as tkfont, messagebox, ttk

from . import gpu, gpupack, pdf_extract as pe, pipeline, textview
from .cli import collect

gpupack.activate()   # trước khi App.ENGINES đọc find_spec('chandra')

try:  # kéo-thả file: cần tkinterdnd2 (tkdnd); không có thì giao diện vẫn chạy với nút bấm
    from tkinterdnd2 import DND_FILES, TkinterDnD
    _Base, HAS_DND = TkinterDnD.Tk, True
except ImportError:
    DND_FILES, _Base, HAS_DND = None, tk.Tk, False

PALETTES = {
    "sáng": dict(BG="#F4F5F7", CARD="#FFFFFF", TEXT="#1F2328", MUTED="#6B7280", ACCENT="#1F6FEB",
                 ACCENT_DARK="#1858BF", LINE="#D8DCE3", RUN="#1B5E20", RUN_DARK="#14481A", RUN_OFF="#9CB8A0",
                 SEL="#DCE8FB", HEAD="#EEF1F6", TROUGH="#E3E7EE", FIELD="#FFFFFF"),
    "tối": dict(BG="#1B1E23", CARD="#262A31", TEXT="#E6E8EC", MUTED="#9AA3B2", ACCENT="#4C8DFF",
                ACCENT_DARK="#3A74DB", LINE="#3A404A", RUN="#2E7D32", RUN_DARK="#256428", RUN_OFF="#3C5A40",
                SEL="#2F4A70", HEAD="#2F343D", TROUGH="#343A44", FIELD="#1E2228"),
}
FONT_SIZES = {"Nhỏ": 9, "Vừa": 10, "Lớn": 12}
ALPHA_LEVELS = (100, 95, 90, 85, 80)   # độ đục của cửa sổ, phần trăm
PRESETS = {   # mẫu tài liệu: đặt sẵn một số tùy chọn; các ô khác giữ nguyên
    "Sổ tay / sách (mặc định)": dict(upscale="1", cell_reocr=True),
    "Ảnh chụp điện thoại": dict(upscale="2", cell_reocr=True),
    "Chỉ văn bản (không bảng)": dict(upscale="1", cell_reocr=False),
}
INPUT_W = 34   # độ rộng thống nhất của mọi ô nhập và danh sách chọn
HEADER_BTN_W = 150   # ba nút trên thanh đầu (Chạy OCR, Dừng, Tìm nhanh) có cùng kích thước
BTN_W = 300    # chiều rộng chung (px) của các nút tải model và cài gói
INPUT_PX = 330  # độ rộng tối thiểu (px) của cột ô nhập, khớp INPUT_W
SETTINGS = gpupack.pack_dir().parent / "settings.json"
LOG_FILE = gpupack.pack_dir().parent / "logs" / "app.log"
log = logging.getLogger("ocrnhat.gui")


def load_settings() -> dict:
    try:
        return json.loads(SETTINGS.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_settings(data: dict) -> None:
    try:
        SETTINGS.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


def open_path(p: Path) -> None:
    """Mở file hoặc thư mục bằng ứng dụng mặc định của hệ điều hành."""
    if os.name == "nt":
        os.startfile(str(p))  # noqa: S606 (chủ ý: mở bằng ứng dụng mặc định)
    else:
        subprocess.Popen(["xdg-open", str(p)])


def _pick_font() -> str | None:
    """Font giao diện: ưu tiên font có đủ dấu tiếng Việt. Yu Gothic/Meiryo là font tiếng Nhật, dấu dễ bị chồng."""
    fams = set(tkfont.families())
    for f in ("Segoe UI", "Tahoma", "Arial"):
        if f in fams:
            return f
    return None


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
        super().__init__(master, height=self.HEIGHT, highlightthickness=0, bd=0, bg=self._bg, cursor="hand2")
        self._text, self._command, self._state = text, command, state
        self._variant = ("run" if style.startswith("Run") else "accent" if style.startswith("Accent")
                         else "danger" if style.startswith("Danger") else "run_soft" if style.startswith("Soft")
                         else "neutral")
        self._icon = icon   # "stop": hình vuông trắng; "search": kính lúp
        self._font = tkfont.nametofont("TkDefaultFont")
        self._fixed_w = width
        self._hover = self._down = False
        self._apply_width()
        self.bind("<Configure>", lambda e: self._draw())
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<ButtonRelease-1>", self._release)
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
        r = min(self.RADIUS, h // 2, w // 2)
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


class App(_CatMixin, _Base):
    DEV_LABELS = {"auto": "Tự động", "cpu": "CPU", **({"cuda": "GPU (NVIDIA)"} if gpu.ort_cuda_available() else {})}
    KANA_LABELS = {"": "Tắt", "template": "Mẫu chữ IPAGothic (thử nghiệm)", "tesseract": "Tesseract (thử nghiệm)"}
    LANG_LABELS = {"ja": "Tiếng Nhật", "en": "Tiếng Anh", "zh": "Tiếng Trung", "vi": "Tiếng Việt", "all": "Mọi ngôn ngữ (cần Chandra)"}
    # ngôn ngữ được chọn cho từng engine (auto: mọi ngôn ngữ, engine tự chọn theo ngôn ngữ)
    ENGINE_LANGS = {"ndlocr": ("ja",), "chandra": ("ja", "en", "zh", "vi", "all"), "paddle": ("en", "zh"),
                    "ocr_vi": ("vi",), "auto": ("ja", "en", "zh", "vi", "all")}
    # chandra chỉ hiện khi đã cài (exe GPU hoặc gói GPU tùy chọn đã kích hoạt)
    ENGINES = ("auto", "ndlocr") + (("chandra",) if importlib.util.find_spec("chandra") else ()) + ("paddle", "ocr_vi")
    # danh sách engine theo ngôn ngữ
    ENGINE_LABELS = {"auto": "Tự động (công cụ phù hợp)", "ndlocr": "Tiếng Nhật – NDLOCR",
                     "chandra": "Tiếng Nhật – Chandra", "paddle": "Tiếng Anh, Trung – PaddleOCR",
                     "ocr_vi": "Tiếng Việt – VietOCR"}
    MERGE_LABELS = {True: "Gộp trang (mặc định)", False: "Giữ nguyên trang"}

    def _engine_key(self) -> str:
        label = self._var("engine", self.ENGINE_LABELS["auto"]).get()
        return next((k for k, v in self.ENGINE_LABELS.items() if v == label), "auto")

    def __init__(self):
        super().__init__()
        self.title("OCR-Nhat · nhiều ngôn ngữ")
        self.geometry("960x820")
        self.minsize(860, 600)
        self.files: list[Path] = []
        self.statuses: list[str] = []
        self.results: list[tuple[Path, dict]] = []
        self.result_rows: list[tuple[Path, dict]] = []
        self.q: queue.Queue = queue.Queue()
        self.cancel = threading.Event()
        self.worker: threading.Thread | None = None
        self._vars: dict = {}
        self._t0 = 0.0
        self._photo = None
        self.settings = load_settings()
        self.theme = self.settings.get("theme", "sáng")
        self.font_size = int(self.settings.get("font_size", 10))
        self.pal = PALETTES.get(self.theme, PALETTES["sáng"])
        self._style()
        self._logging()
        self._menu()
        self._top_bar()

        # nội dung cuộn dọc để vừa mọi màn hình (kể cả laptop 768px)
        canvas = tk.Canvas(self, background=self.pal["BG"], highlightthickness=0, borderwidth=0)
        vbar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vbar.set)
        vbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        page = ttk.Frame(canvas, style="Page.TFrame", padding=(20, 12))
        win = canvas.create_window((0, 0), window=page, anchor="nw")
        page.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(win, width=e.width))
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-e.delta / 120), "units"))

        self.nb = GradientNotebook(page)
        self.nb.pack(fill="both", expand=True)
        self.tab_src = ttk.Frame(self.nb, style="Page.TFrame", padding=(12, 12))
        self.tab_proc = ttk.Frame(self.nb, style="Page.TFrame", padding=(12, 12))
        self.tab_rev = ttk.Frame(self.nb, style="Page.TFrame", padding=(12, 12))
        self.tab_res = ttk.Frame(self.nb, style="Page.TFrame", padding=(12, 12))
        self.tab_pdf = ttk.Frame(self.nb, style="Page.TFrame", padding=(12, 12))
        self.nb.add(self.tab_src, text="  Tài liệu  ")
        self.tab_ai = ttk.Frame(self.nb, style="Page.TFrame", padding=(12, 12))
        self.nb.add(self.tab_proc, text="  Tùy chọn  ")
        self.nb.add(self.tab_ai, text="  AI powered  ")
        self.nb.add(self.tab_rev, text="  Kiểm tra  ")
        self.nb.add(self.tab_res, text="  Kết quả  ")
        self.nb.add(self.tab_pdf, text="  Công cụ PDF  ")
        self._tab_sources()
        self._tab_process()
        self._tab_review()
        self._tab_results()
        self._tab_pdf()

        self._shortcuts()
        threading.Thread(target=self._hardware_worker, daemon=True).start()
        self.after(150, self.poll)

    # ---------- khởi tạo ----------

    def _logging(self):
        try:
            LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
            handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
            handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
            log.addHandler(handler); log.setLevel(logging.INFO)
        except OSError:
            pass

    def _menu(self):
        menubar = tk.Menu(self)
        view = tk.Menu(menubar, tearoff=0)
        for name in PALETTES:
            view.add_command(label=f"Giao diện {name}", command=lambda n=name: self._set_theme(n))
        size = tk.Menu(view, tearoff=0)
        for label, pt in FONT_SIZES.items():
            size.add_command(label=f"{label} ({pt})", command=lambda p=pt: self._set_font(p))
        view.add_cascade(label="Cỡ chữ", menu=size)
        trans = tk.Menu(view, tearoff=0)
        self._alpha = tk.IntVar(value=int(self.settings.get("alpha", 100)))
        for pct in ALPHA_LEVELS:
            trans.add_radiobutton(label=f"{pct}%", variable=self._alpha, value=pct, command=lambda p=pct: self._set_alpha(p))
        view.add_cascade(label="Độ trong suốt cửa sổ", menu=trans)
        menubar.add_cascade(label="Hiển thị", menu=view)
        self.config(menu=menubar)
        self.attributes("-alpha", self._alpha.get() / 100)   # áp dụng ngay khi mở

    def _set_alpha(self, pct: int):
        """Độ mờ của cả cửa sổ (100% = đục). Áp dụng ngay, không cần khởi động lại."""
        self.settings["alpha"] = pct
        save_settings(self.settings)
        self.attributes("-alpha", pct / 100)

    def _set_theme(self, name: str):
        self.settings["theme"] = name
        save_settings(self.settings)
        messagebox.showinfo("Giao diện", "Giao diện mới sẽ áp dụng sau khi khởi động lại OCR-Nhat.")

    def _set_font(self, pt: int):
        self.settings["font_size"] = pt
        save_settings(self.settings)
        messagebox.showinfo("Cỡ chữ", "Cỡ chữ mới sẽ áp dụng sau khi khởi động lại OCR-Nhat.")

    def _top_bar(self):
        """Thanh điều khiển luôn hiện ở đầu: Chạy, Dừng, tiến trình, trạng thái, phần cứng."""
        top = ttk.Frame(self, style="Page.TFrame", padding=(20, 12, 20, 6))
        top.pack(side="top", fill="x")
        btns = ttk.Frame(top, style="Page.TFrame")
        btns.pack(fill="x")
        self.btn = GradientButton(btns, text="▶  Chạy OCR", style="Run.TButton", command=self.start, width=HEADER_BTN_W)
        self.btn.pack(side="left")
        self.stop = GradientButton(btns, text="Dừng", command=self._request_stop, state="disabled", style="Danger.TButton", icon="stop", width=HEADER_BTN_W)
        self.stop.pack(side="left", padx=8)
        self.find = GradientButton(btns, text="Tìm nhanh", command=self.find_output, icon="search", width=HEADER_BTN_W)
        self.find.pack(side="left", padx=(0, 8))
        Tip(self.find, "Mở thư mục kết quả (mục đang chọn, hoặc mục mới nhất).")
        self.hw = tk.StringVar(value="Đang kiểm tra phần cứng…")
        ttk.Label(btns, textvariable=self.hw, style="Status.TLabel").pack(side="right")
        Tip(self.btn, "Bắt đầu OCR cho mọi file trong danh sách. Phím tắt: Ctrl+R hoặc F5.")
        Tip(self.stop, "Dừng sau trang hiện tại. Các trang đã xong vẫn được lưu (Esc).")
        self.pb = ttk.Progressbar(top, maximum=100, style="Accent.Horizontal.TProgressbar")
        self.pb.pack(fill="x", pady=(0, 4))
        self._cat_init(top, before=self.pb)
        self.status = tk.StringVar(value="Sẵn sàng.")
        ttk.Label(top, textvariable=self.status, style="Status.TLabel", wraplength=880, justify="left").pack(fill="x")

    def _shortcuts(self):
        self.bind("<Control-o>", lambda e: self.add_files())
        self.bind("<Control-r>", lambda e: self.start())
        self.bind("<F5>", lambda e: self.start())
        self.bind("<Escape>", lambda e: self._request_stop() if self.worker and self.worker.is_alive() else None)
        self.tree.bind("<Delete>", lambda e: self.remove_selected())

    # ---------- các tab ----------

    def _tab_sources(self):
        src = self._card(self.tab_src, "Tài liệu nguồn")
        bar = ttk.Frame(src, style="Card.TFrame")
        bar.pack(fill="x", pady=(0, 8))
        b_add = GradientButton(bar, text="Thêm file…", command=self.add_files); b_add.pack(side="left")
        b_dir = GradientButton(bar, text="Thêm thư mục…", command=self.add_dir); b_dir.pack(side="left", padx=6)
        b_del = GradientButton(bar, text="Bỏ mục đã chọn", command=self.remove_selected); b_del.pack(side="left")
        b_clr = GradientButton(bar, text="Bỏ tất cả", command=self.clear); b_clr.pack(side="left", padx=6)
        Tip(b_add, "Chọn một hoặc nhiều file PDF hoặc ảnh (PNG, JPG, TIFF...). Phím tắt: Ctrl+O.")
        Tip(b_dir, "Lấy tất cả PDF và ảnh trong một thư mục.")
        Tip(b_del, "Bỏ mục đang chọn khỏi danh sách (Delete). File gốc vẫn còn.")
        Tip(b_clr, "Bỏ hết mục khỏi danh sách. File gốc vẫn còn.")
        self.count = tk.StringVar(value="Chưa có file nào")
        ttk.Label(bar, textvariable=self.count, style="Muted.TLabel").pack(side="right")
        table = ttk.Frame(src, style="Card.TFrame")
        table.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(table, columns=("name", "folder", "status"), show="headings", height=8, selectmode="extended")
        self.tree.heading("name", text="Tên file", anchor="w")
        self.tree.heading("folder", text="Thư mục", anchor="w")
        self.tree.heading("status", text="Trạng thái", anchor="w")
        self.tree.column("name", width=300, anchor="w")
        self.tree.column("folder", width=430, anchor="w")
        self.tree.column("status", width=120, anchor="w")
        scroll = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        hint = ("Kéo thả file hoặc thư mục vào đây, hoặc bấm “Thêm file…”" if HAS_DND
                else "Bấm “Thêm file…” hoặc “Thêm thư mục…” để chọn PDF/ảnh")
        self.empty = ttk.Label(table, text=hint, style="Hint.TLabel", anchor="center")
        self._refresh_list()
        if HAS_DND:   # kéo file/thư mục từ Explorer vào bất kỳ đâu trong cửa sổ
            for w in (self, self.tree):
                w.drop_target_register(DND_FILES)
                w.dnd_bind("<<Drop>>", self._on_drop)

        out = self._card(self.tab_src, "Đầu ra")
        self._row(out, 0, "Thư mục lưu kết quả", ttk.Entry(out, textvariable=self._var("out", ""), width=INPUT_W))
        b_out = GradientButton(out, text="Chọn…", command=self.pick_out); b_out.grid(row=0, column=2, sticky="w", padx=(8, 0), pady=4)
        Tip(b_out, "Chọn thư mục lưu kết quả. Để trống thì lưu cạnh file gốc.")
        self.out_hint = tk.StringVar()
        self._var("out", "").trace_add("write", lambda *_: self._update_out_hint())
        ttk.Label(out, textvariable=self.out_hint, style="Hint.TLabel", wraplength=900, justify="left").grid(row=4, column=0, columnspan=3, sticky="w", pady=(6, 0))
        self._row(out, 1, "Trang", ttk.Entry(out, textvariable=self._var("pages", ""), width=INPUT_W))
        ttk.Label(out, text="ví dụ 1-5,8 · để trống = tất cả (chỉ áp dụng cho PDF)", style="Hint.TLabel").grid(row=1, column=2, sticky="w", padx=(8, 0))
        cb_mg = ttk.Combobox(out, textvariable=self._var("merge", self.MERGE_LABELS[True]), values=list(self.MERGE_LABELS.values()),
                             state="readonly", width=INPUT_W)
        self._row(out, 2, "Cách ghép trang", cb_mg)
        ttk.Label(out, text="Nối đoạn bị cắt giữa các trang; bỏ trang trống.", style="Hint.TLabel").grid(row=2, column=2, sticky="w", padx=(8, 0))
        Tip(cb_mg, "Gộp: một đoạn văn liền, không ngắt trang. Giữ trang: mỗi trang gốc là một trang Word.")
        checks = ttk.Frame(out, style="Card.TFrame")
        checks.grid(row=3, column=0, columnspan=3, sticky="w", pady=(6, 0))
        cb_m = self._check(checks, "marker", True, "Ghi số trang gốc 【原本 p.N】"); cb_m.pack(anchor="w", pady=2)
        cb_t = self._check(checks, "txt", True, "Ghi kèm file .txt"); cb_t.pack(anchor="w", pady=2)
        cb_r = self._check(checks, "ruby", False, "Giữ chữ phiên âm kana trên chữ Hán (ruby)"); cb_r.pack(anchor="w", pady=2)
        Tip(cb_m, "Mỗi trang trong Word ghi số trang gốc của sách (【原本 p.N】).")
        Tip(cb_t, "Tạo thêm file .txt thuần (dán được vào phần mềm khác).")
        Tip(cb_r, "Chữ phiên âm nhỏ (furigana) hiện phía trên chữ Hán. Mặc định: bỏ.")
        out.columnconfigure(1, weight=1)

    def _tab_process(self):
        # mẫu tài liệu: đặt sẵn tùy chọn theo loại tài liệu
        pre = self._card(self.tab_proc, "Mẫu tài liệu")
        cb_p = ttk.Combobox(pre, textvariable=self._var("preset", next(iter(PRESETS))), values=list(PRESETS),
                            state="readonly", width=INPUT_W)
        self._row(pre, 0, "Loại tài liệu", cb_p)
        cb_p.bind("<<ComboboxSelected>>", lambda e: self._apply_preset())
        ttk.Label(pre, text="Chọn sẵn các tùy chọn hợp với loại tài liệu.",
                  style="Hint.TLabel").grid(row=0, column=2, sticky="w", padx=(8, 0))

        proc = self._card(self.tab_proc, "Cách nhận dạng và phần cứng")
        self.engine_cb = ttk.Combobox(proc, textvariable=self._var("engine", self.ENGINE_LABELS["auto"]),
                                      values=[self.ENGINE_LABELS[k] for k in self.ENGINES],
                                      state="readonly", width=INPUT_W)
        self._row(proc, 0, "Công cụ", self.engine_cb)
        ttk.Label(proc, text="Tự động chọn theo máy. NDLOCR là công cụ mặc định.", style="Hint.TLabel").grid(row=0, column=2, sticky="w", padx=(8, 0))
        self._row(proc, 1, "Phần cứng", ttk.Combobox(proc, textvariable=self._var("dev", self.DEV_LABELS["auto"]),
                                                  values=list(self.DEV_LABELS.values()), state="readonly", width=INPUT_W))
        ttk.Label(proc, text="GPU tăng tốc NDLOCR (chỉ bản GPU).", style="Hint.TLabel").grid(row=1, column=2, sticky="w", padx=(8, 0))
        self.lang_cb = ttk.Combobox(proc, textvariable=self._var("lang", self.LANG_LABELS["ja"]),
                                    values=list(self.LANG_LABELS.values()), state="readonly", width=INPUT_W)
        self._row(proc, 2, "Ngôn ngữ", self.lang_cb)
        ttk.Label(proc, text="Chỉ hiện ngôn ngữ mà công cụ đang chọn đọc được. Mọi ngôn ngữ cần Chandra.", style="Hint.TLabel").grid(row=2, column=2, sticky="w", padx=(8, 0))
        self.engine_cb.bind("<<ComboboxSelected>>", lambda e: self._check_engine_choice())
        self._engine_sync = self._var("engine", self.ENGINE_LABELS["auto"]).trace_add("write", lambda *_: self._sync_lang())
        self._sync_lang()

        # mục Nâng cao: thu gọn, ít dùng
        self.adv_btn = GradientButton(self.tab_proc, text="▸ Nâng cao", command=self._toggle_adv)
        self.adv_btn.pack(anchor="w", pady=(0, 8))
        self.adv = self._card(self.tab_proc, "Nâng cao")
        self.adv_outer = self.adv.master.master
        self.adv_outer.pack_forget()
        self._row(self.adv, 0, "Phóng to ảnh", ttk.Entry(self.adv, textvariable=self._var("upscale", "1"), width=INPUT_W))
        ttk.Label(self.adv, text="1 = giữ nguyên · 2 = gấp đôi (dùng khi chữ nhỏ)", style="Hint.TLabel").grid(row=0, column=2, sticky="w", padx=(8, 0))
        self._row(self.adv, 1, "Chỉ đọc một vùng", ttk.Entry(self.adv, textvariable=self._var("crop", ""), width=INPUT_W))
        ttk.Label(self.adv, text="trái, trên, phải, dưới (pixel) · để trống = cả trang", style="Hint.TLabel").grid(row=1, column=2, sticky="w", padx=(8, 0))
        self._row(self.adv, 2, "Đọc bảng chữ kana (thử nghiệm)", ttk.Combobox(self.adv, textvariable=self._var("kana", self.KANA_LABELS[""]),
                                                            values=list(self.KANA_LABELS.values()), state="readonly", width=INPUT_W))
        cb_c = self._check(self.adv, "cell_reocr", True, "Đọc lại ô bảng bị lẫn đường kẻ")
        cb_c.grid(row=3, column=0, columnspan=3, sticky="w", pady=(6, 0))
        Tip(cb_c, "Cắt riêng ô bị lẫn đường kẻ rồi đọc lại. Chậm hơn một chút; tắt để nhanh hơn.")
        cb_k = self._check(self.adv, "use_cache", True, "Nhớ kết quả đã đọc (chạy lại file cũ sẽ nhanh hơn)")
        cb_k.grid(row=4, column=0, columnspan=3, sticky="w", pady=2)
        Tip(cb_k, "Lưu kết quả từng trang trong thư mục đầu ra (.cache). Tắt nếu muốn đọc lại từ đầu.")
        self.adv.columnconfigure(1, weight=1)

        # engine AI: gói GPU và model Chandra, có thanh tiến trình tải
        self._ai_card()

    def _ai_card(self):
        ai = self._card(self.tab_ai, "Công cụ AI (tùy chọn, chỉ tải một lần)")
        self._model_card(ai)
        if not gpupack.installed():
            row = ttk.Frame(ai, style="Card.TFrame")
            row.pack(fill="x", pady=(0, 6))
            self.pack_btn = GradientButton(row, text="Cài tăng tốc GPU (vài GB)", command=self.install_pack, width=BTN_W)
            self.pack_btn.pack(side="left")
            # thanh tiến trình chỉ hiện khi bắt đầu cài (xem install_pack)
            self.pack_pb = ttk.Progressbar(row, mode="indeterminate", length=220, style="Accent.Horizontal.TProgressbar")
            self.pack_status = tk.StringVar(value="Chỉ dùng cho Chandra. Cần card NVIDIA và Internet. Cài xong thì khởi động lại phần mềm.")
            ttk.Label(ai, textvariable=self.pack_status, style="Hint.TLabel", wraplength=760, justify="left").pack(anchor="w", pady=(0, 10))
        if "chandra" in self.ENGINES:
            from .engines.chandra import model_downloaded
            cb_l = self._check(ai, "chandra_license", False, "Tôi đồng ý điều khoản sử dụng của mô hình Chandra (OpenRAIL-M)")
            cb_l.pack(anchor="w")
            Tip(cb_l, "Mô hình Chandra miễn phí cho cá nhân và nghiên cứu. Chi tiết trong NOTICE.md.")
            row = ttk.Frame(ai, style="Card.TFrame")
            row.pack(fill="x", pady=(6, 0))
            self.dl_btn = GradientButton(row, text="Tải mô hình Chandra", command=self.download_chandra, width=BTN_W)
            self.dl_btn.pack(side="left")
            self.dl_pb = ttk.Progressbar(row, maximum=100, length=220, style="Accent.Horizontal.TProgressbar")
            self.dl_pb.pack(side="left", padx=10)
            ready = model_downloaded()
            self.dl_status = tk.StringVar(value="Đã có mô hình Chandra trên máy." if ready else "Chưa có mô hình Chandra (vài GB, chỉ tải một lần).")
            ttk.Label(ai, textvariable=self.dl_status, style="Hint.TLabel").pack(anchor="w", pady=(4, 0))

    def _model_card(self, parent):
        """Hai bộ mô hình OCR tải trong GUI: PaddleOCR (tiếng Anh, Trung) và VietOCR (tiếng Việt)."""
        from .engines import models as mdl
        from .engines.paddle import PaddleEngine
        from .engines.viet import VietnameseEngine
        self._mrows = {}
        for key, label, fetch, ready in (
            ("paddle", "Tải mô hình OCR (PaddleOCR)", mdl.download_paddle, lambda: PaddleEngine.is_available()[0]),
            ("vi", "Tải mô hình tiếng Việt (VietOCR)", mdl.download_vi, lambda: VietnameseEngine.is_available()[0]),
        ):
            row = ttk.Frame(parent, style="Card.TFrame")
            row.pack(fill="x", pady=(0, 6))
            btn = GradientButton(row, text=label, width=BTN_W, command=lambda k=key: self.download_model(k),
                                 state="disabled" if ready() else "normal")
            btn.pack(side="left")
            spin = Spinner(row, size=20)
            pb = ttk.Progressbar(row, maximum=100, length=200, style="Accent.Horizontal.TProgressbar")
            pb.pack(side="left", padx=10)
            pct = tk.StringVar(value="")
            ttk.Label(row, textvariable=pct, width=12).pack(side="left")
            self._mrows[key] = dict(label=label, fetch=fetch, ready=ready, btn=btn, spin=spin, pb=pb, pct=pct)
        self.pm_status = tk.StringVar(value=self._model_status_text())
        ttk.Label(parent, textvariable=self.pm_status, style="Hint.TLabel", wraplength=760, justify="left").pack(anchor="w", pady=(0, 10))

    def _model_status_text(self) -> str:
        from .engines.paddle import PaddleEngine
        from .engines.viet import VietnameseEngine
        paddle_ok = PaddleEngine.is_available()[0]
        vi_ok = VietnameseEngine.is_available()[0]
        lines = ["PaddleOCR (tiếng Anh, Trung): " + ("đã có." if paddle_ok else "chưa có — bấm nút để tải (vài chục MB)."),
                 "VietOCR (tiếng Việt): " + ("đã có." if vi_ok else "chưa có — bấm nút để tải (khoảng 32 MB).")]
        return "\n".join(lines)

    def download_model(self, key: str):
        row = self._mrows[key]
        row["btn"].config(state="disabled")
        row["pb"]["value"] = 0
        row["pct"].set("0%")
        self.pm_status.set(f"Đang tải {row['label'].replace('Tải ', '')}…")
        row["spin"].pack(side="left", padx=(0, 4), before=row["pb"])
        row["spin"].start()
        threading.Thread(target=self._model_worker, args=(key,), daemon=True).start()

    def _model_worker(self, key: str):
        row = self._mrows[key]
        try:
            row["fetch"](progress=lambda i, n, name, frac: self.q.put(("model_prog", (key, i, n, name, frac))))
            ok, msg = True, f"Đã tải xong: {row['label'].replace('Tải ', '')}."
        except Exception as e:
            log.exception("Lỗi tải mô hình %s", key)
            ok, msg = False, f"Tải thất bại: {e}"
        self.q.put(("model_done", (key, ok, msg)))

    def _on_model_progress(self, key, i, n, name, frac):
        row = self._mrows[key]
        overall = (i + frac) / max(1, n)
        row["pb"]["value"] = 100 * overall
        row["pct"].set(f"{round(100 * overall)}%")
        self.pm_status.set(f"Đang tải {name} (tệp {min(i + 1, n)}/{n})…")

    def _on_model_done(self, key, ok, msg):
        row = self._mrows[key]
        row["spin"].stop()
        row["spin"].pack_forget()
        row["pb"]["value"] = 100 if ok else 0
        row["pct"].set("100%" if ok else "")
        self.pm_status.set(msg + "\n" + self._model_status_text())
        row["btn"].config(state="normal" if not ok else "disabled")

    def _tab_pdf(self):
        self._tab_extract()
        groups = (
            ("Ghép PDF", ("Ghép xen kẽ", "Ghép nhiều file", "Chèn trang lặp lại")),
            ("Khác", ("Xoay trang", "Nén PDF", "Tự động theo thư mục")),
        )
        for title, names in groups:
            card = self._card(self.tab_pdf, title)
            row = ttk.Frame(card, style="Card.TFrame")
            row.pack(fill="x")
            for name in names:
                GradientButton(row, text=name, state="disabled").pack(side="left", padx=(0, 8), pady=4)
            ttk.Label(card, text="Sắp có. Chưa có chức năng.", style="Status.TLabel").pack(anchor="w", pady=(4, 0))

    def _tab_extract(self):
        """Trích xuất trang: danh sách PDF, số trang cần lấy và các tùy chọn đầu ra."""
        self.pdfx_items: list[tuple[Path, int]] = []   # (file, số trang)
        files = self._card(self.tab_pdf, "Tệp PDF")
        bar = ttk.Frame(files, style="Card.TFrame")
        bar.pack(fill="x", pady=(0, 8))
        b_add = GradientButton(bar, text="Thêm file…", command=self._pdfx_add); b_add.pack(side="left")
        b_del = GradientButton(bar, text="Bỏ mục đã chọn", command=self._pdfx_remove); b_del.pack(side="left", padx=6)
        b_clr = GradientButton(bar, text="Bỏ tất cả", command=self._pdfx_clear); b_clr.pack(side="left")
        Tip(b_add, "Chọn một hoặc nhiều file PDF. File gốc không bị thay đổi.")
        Tip(b_del, "Bỏ mục đang chọn khỏi danh sách (Delete).")
        self.pdfx_count = tk.StringVar(value="Chưa có file nào")
        ttk.Label(bar, textvariable=self.pdfx_count, style="Muted.TLabel").pack(side="right")
        table = ttk.Frame(files, style="Card.TFrame")
        table.pack(fill="both", expand=True)
        self.pdfx_tree = ttk.Treeview(table, columns=("no", "name", "pages", "folder"), show="headings", height=5, selectmode="extended")
        for col, text, w in (("no", "#", 50), ("name", "Tên file", 300), ("pages", "Số trang", 90), ("folder", "Thư mục", 420)):
            self.pdfx_tree.heading(col, text=text, anchor="w"); self.pdfx_tree.column(col, width=w, anchor="w")
        self.pdfx_tree.pack(side="left", fill="both", expand=True)
        self.pdfx_tree.bind("<Delete>", lambda e: self._pdfx_remove())

        cfg = self._card(self.tab_pdf, "Cài đặt trích xuất")
        self._row(cfg, 0, "Trang cần lấy", ttk.Entry(cfg, textvariable=self._var("pdfx_pages", ""), width=INPUT_W))
        ttk.Label(cfg, text="ví dụ 2 hoặc 5-23 hoặc 2,5-7,12- (12- là đến trang cuối)", style="Hint.TLabel").grid(row=0, column=2, sticky="w", padx=(8, 0))
        cb_sep = self._check(cfg, "pdfx_separate", False, "Một file riêng cho mỗi nhóm trang")
        cb_sep.grid(row=1, column=0, columnspan=3, sticky="w", pady=2)
        Tip(cb_sep, "Mỗi nhóm cách nhau bởi dấu phẩy thành một file. Tắt: gộp mọi trang thành một file.")
        self._row(cfg, 2, "Thư mục lưu", ttk.Entry(cfg, textvariable=self._var("pdfx_out", ""), width=INPUT_W))
        b_out = GradientButton(cfg, text="Chọn…", command=self._pdfx_pick_out); b_out.grid(row=2, column=2, sticky="w", padx=(8, 0), pady=4)
        Tip(b_out, "Để trống thì lưu cạnh file gốc.")
        self._row(cfg, 3, "Phiên bản PDF", ttk.Combobox(cfg, textvariable=self._var("pdfx_version", "1.5"), values=list(pe.PDF_VERSIONS),
                                                         state="readonly", width=INPUT_W))
        checks = ttk.Frame(cfg, style="Card.TFrame")
        checks.grid(row=4, column=0, columnspan=3, sticky="w", pady=(6, 0))
        cb_ow = self._check(checks, "pdfx_overwrite", False, "Ghi đè nếu file đã có"); cb_ow.pack(anchor="w", pady=2)
        cb_cp = self._check(checks, "pdfx_compress", True, "Nén file đầu ra"); cb_cp.pack(anchor="w", pady=2)
        cb_bm = self._check(checks, "pdfx_nobm", False, "Bỏ bookmark"); cb_bm.pack(anchor="w", pady=2)
        Tip(cb_ow, "Tắt: file trùng tên được ghi thêm số (2), (3)... Bật: thay file cũ.")
        Tip(cb_bm, "Tắt (mặc định): giữ bookmark trỏ tới trang được chọn; mục bị loại thì con của nó được chuyển lên cấp trên.")
        run = ttk.Frame(cfg, style="Card.TFrame")
        run.grid(row=5, column=0, columnspan=3, sticky="w", pady=(10, 0))
        self.pdfx_btn = GradientButton(run, text="▶  Trích xuất", style="Run.TButton", command=self._pdfx_run, width=HEADER_BTN_W)
        self.pdfx_btn.pack(side="left")
        self.pdfx_status = tk.StringVar(value="Thêm file PDF, nhập trang rồi bấm Trích xuất.")
        ttk.Label(run, textvariable=self.pdfx_status, style="Status.TLabel", wraplength=640, justify="left").pack(side="left", padx=12)
        cfg.columnconfigure(1, weight=1)

        split = self._card(self.tab_pdf, "Tách PDF")
        self._row(split, 0, "Kiểu tách", ttk.Combobox(split, textvariable=self._var("pdfx_split", self.SPLIT_LABELS["pages"]),
                                                       values=list(self.SPLIT_LABELS.values()), state="readonly", width=INPUT_W))
        Tip(split.grid_slaves(row=0, column=1)[0], "Theo trang: mỗi file một số trang cố định. Theo bookmark: mỗi mục cấp 1 là một file. Theo dung lượng: gộp trang liên tiếp, mỗi file không quá giới hạn.")
        self._row(split, 1, "Số trang / MB", ttk.Entry(split, textvariable=self._var("pdfx_split_val", "1"), width=INPUT_W))
        ttk.Label(split, text="Theo trang: số trang mỗi file. Theo dung lượng: MB tối đa mỗi file. Bookmark: không dùng.", style="Hint.TLabel").grid(row=1, column=2, sticky="w", padx=(8, 0))
        ttk.Label(split, text="Dùng chung thư mục lưu, ghi đè, nén và bookmark ở thẻ “Cài đặt trích xuất”.", style="Hint.TLabel").grid(row=2, column=0, columnspan=3, sticky="w", pady=(6, 0))
        self.pdfx_split_btn = GradientButton(split, text="▶  Tách file", style="Run.TButton", command=self._pdfx_split_run, width=HEADER_BTN_W)
        self.pdfx_split_btn.grid(row=3, column=0, sticky="w", pady=(10, 0))
        split.columnconfigure(1, weight=1)

    SPLIT_LABELS = {"pages": "Theo số trang", "bookmark": "Theo bookmark cấp 1", "size": "Theo dung lượng tối đa"}

    def _pdfx_add(self):
        for f in map(Path, filedialog.askopenfilenames(filetypes=[("PDF", "*.pdf")])):
            if any(f == g for g, _ in self.pdfx_items):
                continue
            try:
                n = pe.page_count(f)
            except Exception as e:   # PDF hỏng hoặc có mật khẩu
                log.exception("Không đọc được PDF %s", f)
                messagebox.showerror("Không mở được PDF", f"{f.name}: {e}")
                continue
            self.pdfx_items.append((f, n))
        self._pdfx_refresh()

    def _pdfx_remove(self):
        for iid in sorted(self.pdfx_tree.selection(), key=int, reverse=True):
            del self.pdfx_items[int(iid)]
        self._pdfx_refresh()

    def _pdfx_clear(self):
        self.pdfx_items.clear()
        self._pdfx_refresh()

    def _pdfx_refresh(self):
        self.pdfx_tree.delete(*self.pdfx_tree.get_children())
        for i, (f, n) in enumerate(self.pdfx_items):
            self.pdfx_tree.insert("", "end", iid=str(i), values=(i + 1, f.name, n, str(f.parent)))
        self.pdfx_count.set(f"{len(self.pdfx_items)} file" if self.pdfx_items else "Chưa có file nào")

    def _pdfx_pick_out(self):
        d = filedialog.askdirectory()
        if d:
            self._var("pdfx_out", "").set(d)

    def _pdfx_run(self):
        if not self.pdfx_items:
            messagebox.showinfo("Trích xuất trang", "Thêm ít nhất một file PDF.")
            return
        spec = self._var("pdfx_pages", "").get().strip()
        if not spec:
            messagebox.showinfo("Trích xuất trang", "Nhập trang cần lấy, ví dụ 2 hoặc 5-23 hoặc 2,5-7,12-.")
            return
        opts = self._pdfx_options()
        out = self._pdfx_out()
        self._pdfx_start(lambda f: pe.extract_pages(f, spec, out, opts), "Đang trích xuất")

    def _pdfx_split_run(self):
        if not self.pdfx_items:
            messagebox.showinfo("Tách PDF", "Thêm ít nhất một file PDF.")
            return
        label = self._var("pdfx_split", self.SPLIT_LABELS["pages"]).get()
        mode = next(k for k, v in self.SPLIT_LABELS.items() if v == label)
        raw = self._var("pdfx_split_val", "1").get().strip()
        try:
            value = None if mode == "bookmark" else (int(raw) if mode == "pages" else float(raw))
        except ValueError:
            messagebox.showinfo("Tách PDF", "Số trang hoặc dung lượng (MB) phải là số.")
            return
        opts = self._pdfx_options()
        out = self._pdfx_out()
        self._pdfx_start(lambda f: pe.split_pdf(f, mode, value, out, opts), "Đang tách")

    def _pdfx_options(self):
        return pe.ExtractOptions(
            separate=self._var("pdfx_separate", False).get(), overwrite=self._var("pdfx_overwrite", False).get(),
            compress=self._var("pdfx_compress", True).get(), keep_bookmarks=not self._var("pdfx_nobm", False).get(),
            pdf_version=self._var("pdfx_version", "1.5").get())

    def _pdfx_out(self):
        return Path(self._var("pdfx_out", "").get().strip()) if self._var("pdfx_out", "").get().strip() else None

    def _pdfx_start(self, task, verb: str):
        """Chạy task(file) cho từng file trong danh sách, ở luồng nền. Hai nút đều khóa cho đến khi xong."""
        self.pdfx_btn.config(state="disabled"); self.pdfx_split_btn.config(state="disabled")
        files = [f for f, _ in self.pdfx_items]
        threading.Thread(target=self._pdfx_worker, args=(files, task, verb), daemon=True).start()

    def _pdfx_worker(self, files, task, verb):
        done, errors = [], []
        for i, f in enumerate(files, 1):
            self.q.put(("pdfx", f"[{i}/{len(files)}] {verb} {f.name}…"))
            try:
                done += task(f)
            except Exception as e:   # một file lỗi không dừng các file còn lại
                log.exception("Lỗi PDF %s", f)
                errors.append(f"{f.name}: {e}")
        msg = f"Xong: {len(done)} file PDF" + (f", lưu tại {done[-1].parent}" if done else "") + "."
        if errors:
            msg += " Lỗi: " + "; ".join(errors)
        self.q.put(("pdfx_done", msg))

    def _tab_review(self):
        rev = self._card(self.tab_rev, "Kiểm tra kết quả")
        cb_v = self._check(rev, "review", False, "Tạo file so sánh để kiểm tra (*_review.html)")
        cb_v.grid(row=0, column=0, columnspan=3, sticky="w", pady=2)
        Tip(cb_v, "Mở file bằng trình duyệt để so ảnh trang với chữ đã đọc. Dòng nghi ngờ được tô đỏ.")
        self._row(rev, 1, "Ngưỡng nghi ngờ", ttk.Entry(rev, textvariable=self._var("conf", "0.8"), width=INPUT_W))
        ttk.Label(rev, text="Dòng có độ chắc chắn thấp hơn mức này sẽ bị tô đỏ (mặc định 0,8).", style="Hint.TLabel").grid(row=1, column=2, sticky="w", padx=(8, 0))
        rev.columnconfigure(1, weight=1)

    def _tab_results(self):
        res = self._card(self.tab_res, "Kết quả")
        self.res = ttk.Treeview(res, columns=("file", "pages", "tables", "docx"), show="headings", height=6, selectmode="browse")
        for col, text, w in (("file", "Tên file", 260), ("pages", "Trang", 70), ("tables", "Bảng", 70), ("docx", "File Word", 380)):
            self.res.heading(col, text=text, anchor="w"); self.res.column(col, width=w, anchor="w")
        self.res.pack(fill="x")
        self.res.bind("<<TreeviewSelect>>", lambda e: self._preview_refresh())
        bar = ttk.Frame(res, style="Card.TFrame")
        bar.pack(fill="x", pady=(8, 8))
        self.b_docx = GradientButton(bar, text="Mở file Word", command=lambda: self._open_result("docx"), state="disabled")
        self.b_docx.pack(side="left")
        self.b_dir = GradientButton(bar, text="Mở thư mục", command=lambda: self._open_result("dir"), state="disabled")
        self.b_dir.pack(side="left", padx=6)
        self.b_rev = GradientButton(bar, text="Mở file so sánh", command=lambda: self._open_result("review"), state="disabled")
        self.b_rev.pack(side="left")

        prev = self._card(self.tab_res, "Xem trước trang")
        ctl = ttk.Frame(prev, style="Card.TFrame")
        ctl.pack(fill="x", pady=(0, 6))
        ttk.Label(ctl, text="Trang:", style="Card.TLabel").pack(side="left")
        self.prev_page = tk.StringVar(value="1")
        sp = ttk.Spinbox(ctl, from_=1, to=9999, width=8, textvariable=self.prev_page, command=self._preview_refresh)
        sp.pack(side="left", padx=6)
        sp.bind("<Return>", lambda e: self._preview_refresh())
        body = ttk.Frame(prev, style="Card.TFrame")
        body.pack(fill="both", expand=True)
        self.prev_img = tk.Canvas(body, width=420, height=360, background=self.pal["FIELD"], highlightthickness=0)
        self.prev_img.pack(side="left")
        self.prev_text = tk.Text(body, width=50, height=18, wrap="char", background=self.pal["FIELD"],
                                 foreground=self.pal["TEXT"], relief="flat", padx=8, pady=6)
        self.prev_text.pack(side="left", fill="both", expand=True, padx=(10, 0))
        self.prev_text.insert("1.0", "Chọn một file ở danh sách trên để xem trước.")
        self.prev_text.configure(state="disabled")

    # ---------- giao diện chung ----------

    def _style(self):
        pal = self.pal
        base = tkfont.nametofont("TkDefaultFont")
        fam = _pick_font()
        base.configure(size=self.font_size, **({"family": fam} if fam else {}))
        tkfont.nametofont("TkHeadingFont").configure(size=self.font_size, weight="bold", **({"family": fam} if fam else {}))
        self.configure(background=pal["BG"])
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure(".", background=pal["BG"], foreground=pal["TEXT"], font=base)
        s.configure("Page.TFrame", background=pal["BG"])
        s.configure("Card.TFrame", background=pal["CARD"])
        s.configure("CardTitle.TLabel", background=pal["CARD"], foreground=pal["TEXT"], font=("TkDefaultFont", self.font_size + 1, "bold"))
        s.configure("Card.TLabel", background=pal["CARD"], foreground=pal["TEXT"])
        s.configure("Card.TCheckbutton", background=pal["CARD"], foreground=pal["TEXT"])
        s.configure("Muted.TLabel", background=pal["CARD"], foreground=pal["MUTED"])
        s.configure("Hint.TLabel", background=pal["CARD"], foreground=pal["MUTED"])
        s.configure("Status.TLabel", background=pal["BG"], foreground=pal["TEXT"])
        s.configure("TNotebook", background=pal["BG"], borderwidth=0)
        s.configure("TNotebook.Tab", padding=(14, 6), background=pal["HEAD"], foreground=pal["TEXT"])
        s.map("TNotebook.Tab", background=[("selected", pal["CARD"])], foreground=[("selected", pal["ACCENT"])])
        s.configure("TButton", padding=(12, 6), background=pal["CARD"], bordercolor=pal["LINE"], focusthickness=0)
        s.map("TButton", background=[("active", pal["HEAD"]), ("disabled", pal["CARD"])],
              foreground=[("disabled", pal["MUTED"])])
        s.configure("Run.TButton", background=pal["RUN"], foreground="#FFFFFF", bordercolor=pal["RUN"],
                    padding=(22, 10), font=("TkDefaultFont", self.font_size + 1, "bold"))
        s.map("Run.TButton", background=[("active", pal["RUN_DARK"]), ("disabled", pal["RUN_OFF"])],
              foreground=[("disabled", "#FFFFFF")])
        s.configure("Accent.TButton", background=pal["ACCENT"], foreground="#FFFFFF", bordercolor=pal["ACCENT"], padding=(18, 8))
        s.map("Accent.TButton", background=[("active", pal["ACCENT_DARK"])])
        s.configure("TEntry", fieldbackground=pal["FIELD"], bordercolor=pal["LINE"], padding=4, foreground=pal["TEXT"])
        s.configure("TCombobox", fieldbackground=pal["FIELD"], bordercolor=pal["LINE"], padding=3, foreground=pal["TEXT"])
        s.configure("TSpinbox", fieldbackground=pal["FIELD"], bordercolor=pal["LINE"], padding=3, foreground=pal["TEXT"])
        s.configure("Treeview", background=pal["CARD"], fieldbackground=pal["CARD"], foreground=pal["TEXT"], rowheight=24, bordercolor=pal["LINE"])
        s.configure("Treeview.Heading", background=pal["HEAD"], foreground=pal["TEXT"], relief="flat", padding=(8, 4))
        s.map("Treeview", background=[("selected", pal["SEL"])], foreground=[("selected", pal["TEXT"])])
        s.configure("Accent.Horizontal.TProgressbar", background=pal["ACCENT"], troughcolor=pal["TROUGH"], bordercolor=pal["BG"])

    def _card(self, parent, title: str) -> ttk.Frame:
        """Khối tùy chọn: nền thẻ, viền mảnh, tiêu đề đậm ở đầu."""
        outer = tk.Frame(parent, background=self.pal["LINE"])
        outer.pack(fill="x", pady=(0, 12))
        box = ttk.Frame(outer, style="Card.TFrame", padding=(16, 12))
        box.pack(fill="both", expand=True, padx=1, pady=1)
        ttk.Label(box, text=title, style="CardTitle.TLabel").pack(anchor="w", pady=(0, 8))
        body = ttk.Frame(box, style="Card.TFrame")   # phần thân dùng grid, tách khỏi tiêu đề dùng pack
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, minsize=INPUT_PX)   # cột ô nhập không bị co về 0 khi nhãn gợi ý dài
        return body

    def _var(self, name: str, default):
        """Biến Tk theo tên, tạo một lần."""
        if name not in self._vars:
            self._vars[name] = tk.StringVar(value=default) if isinstance(default, str) else tk.BooleanVar(value=default)
        return self._vars[name]

    def _row(self, parent, row: int, label: str, widget):
        """Hàng nhãn + ô nhập. Bố cục dùng grid nên mọi khối cùng một cột nhãn."""
        ttk.Label(parent, text=label, style="Card.TLabel", width=16, anchor="w").grid(row=row, column=0, sticky="w", pady=4, padx=(0, 8))
        widget.grid(row=row, column=1, sticky="w", pady=4)
        return widget

    def _check(self, parent, name: str, default: bool, text: str) -> ttk.Checkbutton:
        return ttk.Checkbutton(parent, text=text, variable=self._var(name, default), style="Card.TCheckbutton")

    def _toggle_adv(self):
        if self.adv_outer.winfo_ismapped():
            self.adv_outer.pack_forget(); self.adv_btn.config(text="▸ Nâng cao")
        else:
            self.adv_outer.pack(fill="x", pady=(0, 12), after=self.adv_btn)
            self.adv_btn.config(text="▾ Nâng cao")

    def _apply_preset(self):
        p = PRESETS[self._var("preset", "").get()]
        self._var("upscale", "1").set(p["upscale"])
        self._var("cell_reocr", True).set(p["cell_reocr"])

    def _check_engine_choice(self):
        key = self._engine_key()
        if key in ("paddle", "ocr_vi"):
            from .engines import paddle, viet
            cls = paddle.PaddleEngine if key == "paddle" else viet.VietnameseEngine
            ok, why = cls.is_available()
            if not ok:
                messagebox.showwarning("Công cụ", f"Chưa dùng được {self.ENGINE_LABELS[key]} vì {why}")
                self._var("engine", self.ENGINE_LABELS["auto"]).set(self.ENGINE_LABELS["auto"])

    def _sync_lang(self):
        key = self._engine_key()
        allowed = [self.LANG_LABELS[k] for k in self.ENGINE_LANGS.get(key, self.ENGINE_LANGS["auto"])]
        self.lang_cb.config(values=allowed, state="readonly")
        if self._var("lang", self.LANG_LABELS["ja"]).get() not in allowed:
            self._var("lang", self.LANG_LABELS["ja"]).set(allowed[0])

    # ---------- danh sách file ----------

    def _refresh_list(self):
        n = len(self.files)
        self.count.set(f"{n} file" if n else "Chưa có file nào")
        if n:
            self.empty.place_forget()
        else:
            self.empty.place(relx=0.5, rely=0.5, anchor="center")

    def _request_stop(self):
        """Yêu cầu dừng: trang đang đọc vẫn xong, sau đó mới dừng."""
        self.cancel.set()
        self.status.set("Đang dừng… chờ trang hiện tại đọc xong.")

    def _update_out_hint(self):
        """Dòng gợi ý thư mục lưu: hiện đường dẫn thật để người dùng biết file sẽ nằm ở đâu."""
        if not hasattr(self, "out_hint"):
            return
        out = self._var("out", "").get().strip()
        if out:
            where = f"Lưu vào: {out}"
        elif self.files:
            where = f"Để trống: lưu cạnh file gốc, ví dụ {self.files[0].parent}"
        else:
            where = "Để trống: lưu cạnh file gốc."
        self.out_hint.set(where + "   ·   Tên file: OCR_<tên không dấu>_<trang đầu>_<trang cuối>")

    def _redraw(self):
        self._update_out_hint()
        self.tree.delete(*self.tree.get_children())
        for i, f in enumerate(self.files):
            self.tree.insert("", "end", iid=str(i), values=(f.name, str(f.parent), self.statuses[i]))
        self._refresh_list()

    def _set_status(self, i: int, text: str):
        if i < len(self.statuses):
            self.statuses[i] = text
            if self.tree.exists(str(i)):
                self.tree.set(str(i), "status", text)

    def add_files(self):
        fs = filedialog.askopenfilenames(filetypes=[("PDF / ảnh", "*.pdf *.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp")])
        self._add(collect(list(fs)))

    def _on_drop(self, event):
        """Nhận đường dẫn từ kéo-thả. tkdnd gửi danh sách, tên có khoảng trắng nằm trong {}."""
        paths = self.tk.splitlist(event.data)
        self._add(collect(list(paths)))
        return event.action

    def add_dir(self):
        d = filedialog.askdirectory()
        if d:
            self._add(collect([d]))

    def _add(self, fs):
        for f in fs:
            if f not in self.files:
                self.files.append(f); self.statuses.append("Chờ")
        self._redraw()

    def remove_selected(self):
        if self.worker and self.worker.is_alive():
            return
        for iid in sorted((int(i) for i in self.tree.selection()), reverse=True):
            del self.files[iid]; del self.statuses[iid]
        self._redraw()

    def clear(self):
        if self.worker and self.worker.is_alive():
            return
        self.files.clear(); self.statuses.clear()
        self._redraw()

    def find_output(self):
        """Mở thư mục kết quả: dòng đang chọn -> kết quả gần nhất -> thư mục lưu đã đặt (hoặc cạnh file đầu tiên)."""
        item = self._selected_result() if self.result_rows else None
        if item:
            target = Path(item[1]["docx"]).parent
        elif self.results:
            target = Path(self.results[-1][1]["docx"]).parent
        elif self.files:
            target = Path(self._var("out", "").get().strip() or self.files[0].parent)
        else:
            messagebox.showinfo("Tìm nhanh", "Chưa có file nào trong danh sách.")
            return
        if not target.is_dir():
            messagebox.showinfo("Tìm nhanh", f"Chưa có thư mục kết quả:\n{target}")
            return
        try:
            open_path(target)
        except OSError as e:
            messagebox.showerror("Tìm nhanh", f"Không mở được thư mục này: {e}")

    def pick_out(self):
        d = filedialog.askdirectory()
        if d:
            self._var("out", "").set(d)

    # ---------- chạy ----------

    def _read_options(self) -> dict:
        """Đọc và kiểm tra các ô nhập. Ném ValueError với thông báo tiếng Việt nếu sai."""
        try:
            conf = float(self._var("conf", "0.8").get())
        except ValueError:
            raise ValueError("Ngưỡng nghi ngờ phải là số, ví dụ 0.8.") from None
        try:
            upscale = float(self._var("upscale", "1").get() or "1")
        except ValueError:
            raise ValueError("Phóng to phải là số, ví dụ 1 hoặc 2.") from None
        if upscale <= 0:
            raise ValueError("Phóng to phải lớn hơn 0.")
        try:
            crop = pipeline.parse_crop(self._var("crop", "").get())
        except ValueError as e:
            raise ValueError("Vùng cắt sai. Nhập theo thứ tự: trái, trên, phải, dưới (pixel).") from None
        dev = next(k for k, v in self.DEV_LABELS.items() if v == self._var("dev", "").get())
        lang = next(k for k, v in self.LANG_LABELS.items() if v == self._var("lang", self.LANG_LABELS["ja"]).get())
        return dict(write_txt=self._var("txt", True).get(), page_marker=self._var("marker", True).get(), lang=lang,
                    device=dev, ruby=self._var("ruby", False).get(),
                    review=self._var("review", False).get(), conf_threshold=conf,
                    engine=self._engine_key(), crop=crop, upscale=upscale,
                    merge_pages=self._var("merge", self.MERGE_LABELS[True]).get() == self.MERGE_LABELS[True],
                    cell_reocr=self._var("cell_reocr", True).get(), use_cache=self._var("use_cache", True).get(),
                    kana_reader=next(k for k, v in self.KANA_LABELS.items() if v == self._var("kana", "").get()))

    def start(self):
        if self.worker and self.worker.is_alive():
            return
        if not self.files:
            messagebox.showinfo("OCR", "Chưa chọn file."); return
        try:
            pages = pipeline.parse_pages(self._var("pages", "").get())
        except ValueError:
            messagebox.showerror("OCR", "Số trang không hợp lệ. Ví dụ: 1-5,8."); return
        try:
            opts = self._read_options()
        except ValueError as e:
            messagebox.showerror("OCR", str(e)); return
        self.statuses = ["Chờ"] * len(self.files)
        self._redraw()
        self.results = []
        self._t0 = time.time()
        self.cancel.clear(); self.btn.config(state="disabled"); self.stop.config(state="normal")
        self._cat_start()
        out = self._var("out", "").get().strip()
        args = (list(self.files), Path(out) if out else None, pages, opts)
        self.worker = threading.Thread(target=self.run_job, args=args, daemon=True); self.worker.start()

    def run_job(self, files, out, pages, opts):
        reviews, errors = [], 0
        for i, f in enumerate(files):
            if self.cancel.is_set():
                break
            self.q.put(("file", (i, "Đang xử lý")))
            self.q.put(("status", f"Đang tải công cụ và đọc {f.name} ({i + 1}/{len(files)})…"))
            try:
                r = pipeline.process_file(
                    f, out, 200, pages if f.suffix.lower() == ".pdf" else None,
                    progress=lambda d, t, m: self.q.put(("prog", (d, t, m))),
                    cancel=self.cancel.is_set, **opts)
                self.results.append((f, r))
                self.q.put(("file", (i, "Dừng" if self.cancel.is_set() else "Xong")))
                if r.get("review"):
                    reviews.append(r["review"])
            except Exception as e:  # một file lỗi không làm dừng các file còn lại
                errors += 1
                log.exception("Không xử lý được %s", f)
                self.q.put(("file", (i, "Lỗi")))
        self.q.put(("results", list(self.results)))
        if self.cancel.is_set():
            msg = "Đã dừng."
        else:
            msg = f"Xong. Kết quả ở: {out}"
            if reviews:
                msg += "\nFile so sánh: " + ", ".join(reviews)
        if errors:
            msg += f"\nCó {errors} file lỗi. Chi tiết trong nhật ký: {LOG_FILE}"
        self.q.put(("done", msg))

    def _hardware_worker(self):
        from . import engines
        try:
            gpus = gpu.detect()
            gtxt = f"GPU: {gpus[0].name}" if gpus else "Không thấy GPU NVIDIA"
            eng, why = engines.resolve("auto")
            text = f"{gtxt} · Công cụ tự động: {eng} ({why})"
        except Exception:
            text = "Không kiểm tra được phần cứng"
        self.q.put(("hw", text))

    def install_pack(self):
        if not messagebox.askyesno("Tăng tốc GPU", "Tải phần mềm tăng tốc GPU, khoảng vài GB. Tiếp tục?"):
            return
        self.pack_btn.config(state="disabled")
        self.pack_pb.pack(side="left", padx=10)
        self.pack_pb.start(12)
        threading.Thread(target=self._pack_worker, daemon=True).start()

    def _pack_worker(self):
        try:
            gpupack.install(progress=lambda m: self.q.put(("pack", m)))
            msg = "Đã cài xong tăng tốc GPU. Hãy khởi động lại OCR-Nhat để dùng Chandra."
        except Exception as e:
            log.exception("Lỗi cài gói GPU")
            msg = f"Cài tăng tốc GPU thất bại: {e}"
        self.q.put(("packdone", msg))

    def download_chandra(self):
        if not self._var("chandra_license", False).get():
            messagebox.showwarning("Chandra", "Hãy tick đồng ý điều khoản Chandra trước khi tải mô hình.")
            return
        self.dl_btn.config(state="disabled")
        self.dl_pb["value"] = 0
        self.dl_status.set("Đang tải mô hình Chandra (vài GB, có thể mất vài phút)…")
        threading.Thread(target=self._download_worker, daemon=True).start()

    def _download_worker(self):
        from .engines.chandra import download_model
        try:
            download_model(progress=lambda d, t: self.q.put(("dl_prog", (d, t))))
            msg = "Đã tải xong mô hình Chandra."
        except Exception as e:
            log.exception("Lỗi tải mô hình Chandra")
            msg = f"Tải mô hình thất bại: {e}"
        self.q.put(("dl", msg))

    # ---------- kết quả và xem trước ----------

    def _populate_results(self, results):
        self.res.delete(*self.res.get_children())
        self.result_rows = results
        for i, (f, r) in enumerate(results):
            self.res.insert("", "end", iid=str(i), values=(f.name, r.get("pages", 0), r.get("tables", 0), Path(r["docx"]).name))
        has = bool(results)
        self.b_docx.config(state="normal" if has else "disabled")
        self.b_dir.config(state="normal" if has else "disabled")
        if has:
            self.res.selection_set("0")
            self.nb.select(self.tab_res)
        self._preview_refresh()

    def _selected_result(self):
        sel = self.res.selection()
        if not sel:
            return None
        return self.result_rows[int(sel[0])]

    def _open_result(self, what: str):
        item = self._selected_result()
        if not item:
            return
        f, r = item
        try:
            if what == "docx":
                open_path(Path(r["docx"]))
            elif what == "dir":
                open_path(Path(r["docx"]).parent)
            elif what == "review" and r.get("review"):
                open_path(Path(r["review"]))
            elif what == "review":
                messagebox.showinfo("Kiểm tra kết quả", "Chưa có file so sánh. Bật “Tạo file so sánh để kiểm tra” ở tab Kiểm tra rồi chạy lại.")
        except OSError as e:
            messagebox.showerror("Mở file", f"Không mở được thư mục này: {e}")

    def _preview_refresh(self):
        item = self._selected_result()
        self.prev_img.delete("all")
        try:
            pno = max(1, int(self.prev_page.get()))
        except ValueError:
            pno = 1
        if not item:
            return
        f, r = item
        self._draw_page(f, pno)
        txt_path = Path(r["docx"]).with_suffix(".txt")
        text = None
        if txt_path.exists():
            text = textview.page_text(txt_path.read_text(encoding="utf-8"), pno)
        self.prev_text.configure(state="normal")
        self.prev_text.delete("1.0", "end")
        if text is None:
            msg = ("Không có chữ cho trang này." if txt_path.exists()
                   else "Không có file .txt. Bật “Ghi kèm file .txt” rồi chạy lại để xem chữ ở đây.")
            self.prev_text.insert("1.0", msg)
        else:
            self.prev_text.insert("1.0", text)
        self.prev_text.configure(state="disabled")

    def _draw_page(self, f: Path, pno: int):
        """Vẽ ảnh trang nguồn (PDF hoặc ảnh) vừa khung xem trước."""
        try:
            if f.suffix.lower() == ".pdf":
                import pypdfium2 as pdfium
                doc = pdfium.PdfDocument(str(f))
                if pno > len(doc):
                    return
                img = doc[pno - 1].render(scale=1.0).to_pil()
            else:
                from PIL import Image
                img = Image.open(f).convert("RGB")
        except Exception:
            log.exception("Không vẽ được bản xem trước %s", f)
            return
        from PIL import ImageTk
        img.thumbnail((420, 360))
        self._photo = ImageTk.PhotoImage(img)
        self.prev_img.create_image(210, 180, image=self._photo)

    # ---------- nhận tin từ luồng nền ----------

    def poll(self):
        try:
            while True:
                k, v = self.q.get_nowait()
                if k == "prog":
                    d, t, m = v
                    self.pb["value"] = 100 * d / max(1, t)
                    self._cat_move(d / max(1, t))
                    eta = ""
                    if d >= 2:
                        rem = (time.time() - self._t0) / d * (t - d)
                        eta = " · còn khoảng dưới 1 phút" if rem < 60 else f" · còn khoảng {round(rem / 60)} phút"
                    self.status.set(f"[{d}/{t}] {m}{eta}")
                elif k == "status":
                    self.status.set(v)
                elif k == "file":
                    self._set_status(*v)
                elif k == "results":
                    self._populate_results(v)
                elif k == "hw":
                    self.hw.set(v)
                elif k == "dl_prog":
                    d, t = v
                    self.dl_pb["value"] = 100 * d / max(1, t)
                    self.dl_status.set(f"Đang tải mô hình Chandra: {d * 100 // max(1, t)}% ({d // 2**20} / {t // 2**20} MB)")
                elif k == "dl":
                    self.dl_status.set(v); self.dl_pb["value"] = 100 if "xong" in v else 0
                    self.dl_btn.config(state="normal")
                elif k == "model_prog":
                    self._on_model_progress(*v)
                elif k == "model_done":
                    self._on_model_done(*v)
                elif k == "pack":
                    self.pack_status.set(v)
                elif k == "pdfx":
                    self.pdfx_status.set(v)
                elif k == "pdfx_done":
                    self.pdfx_status.set(v); self.pdfx_btn.config(state="normal"); self.pdfx_split_btn.config(state="normal")
                elif k == "packdone":
                    self.pack_pb.stop(); self.pack_pb.pack_forget()
                    self.pack_status.set(v); self.pack_btn.config(state="normal")
                else:   # done
                    self._cat_stop()
                    self.status.set(v); self.btn.config(state="normal"); self.stop.config(state="disabled")
                    self.pb["value"] = 100
        except queue.Empty:
            pass
        self.after(150, self.poll)


def run():
    try:   # Windows: không để hệ điều hành làm mờ chữ trên màn hình DPI cao
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    App().mainloop()
