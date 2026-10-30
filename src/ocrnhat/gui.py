"""Giao diện Tkinter: thanh điều khiển đầu (Chạy, Dừng, tiến trình, phần cứng), bốn tab
(Tài liệu, Xử lý OCR, Rà soát, Kết quả), mẫu tài liệu, mục Nâng cao, xem trước trang,
thanh tiến trình khi tải engine AI (gói GPU, model Chandra).
"""
from __future__ import annotations

import importlib.util
import json
import logging
import os
import queue
import subprocess
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, font as tkfont, messagebox, ttk

from . import gpu, gpupack, pipeline, textview
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
    fams = set(tkfont.families())
    for f in ("Yu Gothic UI", "Meiryo", "Segoe UI", "Helvetica"):
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
                "danger": ("#F2625C", "#B71C1C", "#FFFFFF")}
    HEIGHT = 32
    ICON_W, ICON_GAP = 16, 8

    def __init__(self, master, text: str = "", command=None, state: str = "normal", style: str = "",
                 width: int | None = None, icon: str | None = None, **_):
        self._bg = _parent_bg(master)
        super().__init__(master, height=self.HEIGHT, highlightthickness=0, bd=0, bg=self._bg, cursor="hand2")
        self._text, self._command, self._state = text, command, state
        self._variant = ("run" if style.startswith("Run") else "accent" if style.startswith("Accent")
                         else "danger" if style.startswith("Danger") else "neutral")
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
        for y in range(h):
            self.create_line(0, y, w, y, fill=_mix(top, bot, y / max(1, h - 1)))
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


class App(_Base):
    DEV_LABELS = {"auto": "Tự động", "cpu": "CPU", **({"cuda": "GPU (NVIDIA)"} if gpu.ort_cuda_available() else {})}
    KANA_LABELS = {"": "Tắt", "template": "Mẫu IPAGothic (thử nghiệm)", "tesseract": "Tesseract (thử nghiệm)"}
    LANG_LABELS = {"ja": "Tiếng Nhật", "en": "Tiếng Anh", "zh": "Tiếng Trung", "vi": "Tiếng Việt", "all": "Mọi ngôn ngữ"}
    # ngôn ngữ được chọn cho từng engine (auto: mọi ngôn ngữ, engine tự chọn theo ngôn ngữ)
    ENGINE_LANGS = {"ndlocr": ("ja",), "chandra": ("ja", "en", "zh", "vi", "all"), "paddle": ("en", "zh"),
                    "ocr_vi": ("vi",), "auto": ("ja", "en", "zh", "vi", "all")}
    # chandra chỉ hiện khi đã cài (exe GPU hoặc gói GPU tùy chọn đã kích hoạt)
    ENGINES = ("auto", "ndlocr") + (("chandra",) if importlib.util.find_spec("chandra") else ()) + ("paddle", "ocr_vi")
    # danh sách engine theo ngôn ngữ
    ENGINE_LABELS = {"auto": "Tự động (engine phù hợp)", "ndlocr": "Tiếng Nhật – NDLOCR",
                     "chandra": "Tiếng Nhật – Chandra", "paddle": "Tiếng Anh/Trung – PaddleOCR",
                     "ocr_vi": "Tiếng Việt – VietOCR"}
    MERGE_LABELS = {True: "Gộp trang (mặc định)", False: "Giữ nguyên trang"}

    def _engine_key(self) -> str:
        label = self._var("engine", self.ENGINE_LABELS["auto"]).get()
        return next((k for k, v in self.ENGINE_LABELS.items() if v == label), "auto")

    def __init__(self):
        super().__init__()
        self.title("OCR tiếng Nhật")
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

        self.nb = ttk.Notebook(page)
        self.nb.pack(fill="both", expand=True)
        self.tab_src = ttk.Frame(self.nb, style="Page.TFrame", padding=(12, 12))
        self.tab_proc = ttk.Frame(self.nb, style="Page.TFrame", padding=(12, 12))
        self.tab_rev = ttk.Frame(self.nb, style="Page.TFrame", padding=(12, 12))
        self.tab_res = ttk.Frame(self.nb, style="Page.TFrame", padding=(12, 12))
        self.nb.add(self.tab_src, text="  Tài liệu  ")
        self.tab_ai = ttk.Frame(self.nb, style="Page.TFrame", padding=(12, 12))
        self.nb.add(self.tab_proc, text="  Xử lý OCR  ")
        self.nb.add(self.tab_ai, text="  AI powered  ")
        self.nb.add(self.tab_rev, text="  Rà soát  ")
        self.nb.add(self.tab_res, text="  Kết quả  ")
        self._tab_sources()
        self._tab_process()
        self._tab_review()
        self._tab_results()

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
        self.btn = GradientButton(btns, text="▶  Chạy OCR", style="Run.TButton", command=self.start)
        self.btn.pack(side="left")
        self.stop = GradientButton(btns, text="Dừng", command=self.cancel.set, state="disabled", style="Danger.TButton", icon="stop")
        self.stop.pack(side="left", padx=8)
        self.find = GradientButton(btns, text="Tìm nhanh", command=self.find_output, icon="search")
        self.find.pack(side="left", padx=(0, 8))
        Tip(self.find, "Mở thư mục chứa file kết quả: kết quả đang chọn, không thì kết quả gần nhất, không thì thư mục lưu.")
        self.hw = tk.StringVar(value="Đang dò phần cứng…")
        ttk.Label(btns, textvariable=self.hw, style="Status.TLabel").pack(side="right")
        Tip(self.btn, "Bắt đầu OCR cho mọi file trong danh sách. Phím tắt: Ctrl+R hoặc F5.")
        Tip(self.stop, "Dừng sau trang đang xử lý. Các trang đã xong vẫn được lưu. Phím tắt: Esc.")
        self.pb = ttk.Progressbar(top, maximum=100, style="Accent.Horizontal.TProgressbar")
        self.pb.pack(fill="x", pady=(10, 4))
        self.status = tk.StringVar(value="Sẵn sàng.")
        ttk.Label(top, textvariable=self.status, style="Status.TLabel", wraplength=880, justify="left").pack(fill="x")

    def _shortcuts(self):
        self.bind("<Control-o>", lambda e: self.add_files())
        self.bind("<Control-r>", lambda e: self.start())
        self.bind("<F5>", lambda e: self.start())
        self.bind("<Escape>", lambda e: self.cancel.set() if self.worker and self.worker.is_alive() else None)
        self.tree.bind("<Delete>", lambda e: self.remove_selected())

    # ---------- các tab ----------

    def _tab_sources(self):
        src = self._card(self.tab_src, "Tài liệu nguồn")
        bar = ttk.Frame(src, style="Card.TFrame")
        bar.pack(fill="x", pady=(0, 8))
        b_add = GradientButton(bar, text="Thêm file…", command=self.add_files); b_add.pack(side="left")
        b_dir = GradientButton(bar, text="Thêm thư mục…", command=self.add_dir); b_dir.pack(side="left", padx=6)
        b_del = GradientButton(bar, text="Xóa mục đã chọn", command=self.remove_selected); b_del.pack(side="left")
        b_clr = GradientButton(bar, text="Xóa danh sách", command=self.clear); b_clr.pack(side="left", padx=6)
        Tip(b_add, "Chọn một hoặc nhiều file PDF hoặc ảnh (PNG, JPG, TIFF...). Phím tắt: Ctrl+O.")
        Tip(b_dir, "Lấy tất cả PDF và ảnh trong một thư mục.")
        Tip(b_del, "Bỏ file đang chọn khỏi danh sách (phím Delete). File gốc không bị xóa.")
        Tip(b_clr, "Bỏ hết file khỏi danh sách. File gốc trên máy không bị xóa.")
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
        self._row(out, 0, "Thư mục lưu", ttk.Entry(out, textvariable=self._var("out", ""), width=INPUT_W))
        b_out = GradientButton(out, text="Chọn…", command=self.pick_out); b_out.grid(row=0, column=2, sticky="w", padx=(8, 0), pady=4)
        Tip(b_out, "Chọn thư mục để lưu file kết quả. Để trống = thư mục chứa file gốc.")
        ttk.Label(out, text="Để trống = cạnh file gốc. Tên file: OCR_tên_không_dấu_trang_đầu_trang_cuối.", style="Hint.TLabel").grid(row=4, column=0, columnspan=3, sticky="w", pady=(6, 0))
        self._row(out, 1, "Trang", ttk.Entry(out, textvariable=self._var("pages", ""), width=INPUT_W))
        ttk.Label(out, text="ví dụ 1-5,8 · để trống = tất cả (chỉ áp dụng cho PDF)", style="Hint.TLabel").grid(row=1, column=2, sticky="w", padx=(8, 0))
        cb_mg = ttk.Combobox(out, textvariable=self._var("merge", self.MERGE_LABELS[True]), values=list(self.MERGE_LABELS.values()),
                             state="readonly", width=INPUT_W)
        self._row(out, 2, "Gộp trang", cb_mg)
        ttk.Label(out, text="Nối đoạn bị cắt giữa các trang; bỏ trang trống.", style="Hint.TLabel").grid(row=2, column=2, sticky="w", padx=(8, 0))
        Tip(cb_mg, "Gộp trang: khối văn bản liền mạch, không ngắt trang trong Word. Giữ nguyên trang: mỗi trang một trang Word.")
        checks = ttk.Frame(out, style="Card.TFrame")
        checks.grid(row=3, column=0, columnspan=3, sticky="w", pady=(6, 0))
        cb_m = self._check(checks, "marker", True, "Ghi số trang gốc 【原本 p.N】"); cb_m.pack(anchor="w", pady=2)
        cb_t = self._check(checks, "txt", True, "Ghi kèm file .txt"); cb_t.pack(anchor="w", pady=2)
        cb_r = self._check(checks, "ruby", False, "Giữ furigana thành ruby của Word"); cb_r.pack(anchor="w", pady=2)
        Tip(cb_m, "Mỗi trang trong Word có dòng 【原本 p.N】 để biết trang gốc trong sách.")
        Tip(cb_t, "Thêm file .txt thuần để dán vào công cụ khác và để xem trước ở tab Kết quả.")
        Tip(cb_r, "Chữ nhỏ (furigana) hiện phía trên chữ Hán bằng ruby của Word. Mặc định bỏ furigana.")
        out.columnconfigure(1, weight=1)

    def _tab_process(self):
        # mẫu tài liệu: đặt sẵn tùy chọn theo loại tài liệu
        pre = self._card(self.tab_proc, "Mẫu tài liệu")
        cb_p = ttk.Combobox(pre, textvariable=self._var("preset", next(iter(PRESETS))), values=list(PRESETS),
                            state="readonly", width=INPUT_W)
        self._row(pre, 0, "Loại tài liệu", cb_p)
        cb_p.bind("<<ComboboxSelected>>", lambda e: self._apply_preset())
        ttk.Label(pre, text="Đặt sẵn tùy chọn theo loại tài liệu.",
                  style="Hint.TLabel").grid(row=0, column=2, sticky="w", padx=(8, 0))

        proc = self._card(self.tab_proc, "Engine và thiết bị")
        self.engine_cb = ttk.Combobox(proc, textvariable=self._var("engine", self.ENGINE_LABELS["auto"]),
                                      values=[self.ENGINE_LABELS[k] for k in self.ENGINES],
                                      state="readonly", width=INPUT_W)
        self._row(proc, 0, "Engine", self.engine_cb)
        ttk.Label(proc, text="auto: tự chọn. ndlocr: engine chính.", style="Hint.TLabel").grid(row=0, column=2, sticky="w", padx=(8, 0))
        self._row(proc, 1, "Thiết bị", ttk.Combobox(proc, textvariable=self._var("dev", self.DEV_LABELS["auto"]),
                                                  values=list(self.DEV_LABELS.values()), state="readonly", width=INPUT_W))
        ttk.Label(proc, text="GPU tăng tốc NDLOCR ở bản GPU.", style="Hint.TLabel").grid(row=1, column=2, sticky="w", padx=(8, 0))
        self.lang_cb = ttk.Combobox(proc, textvariable=self._var("lang", self.LANG_LABELS["ja"]),
                                    values=list(self.LANG_LABELS.values()), state="readonly", width=INPUT_W)
        self._row(proc, 2, "Ngôn ngữ", self.lang_cb)
        ttk.Label(proc, text="Engine chỉ nhận các ngôn ngữ hợp lệ; “Mọi ngôn ngữ” chỉ với Chandra.", style="Hint.TLabel").grid(row=2, column=2, sticky="w", padx=(8, 0))
        self.engine_cb.bind("<<ComboboxSelected>>", lambda e: self._check_engine_choice())
        self._engine_sync = self._var("engine", self.ENGINE_LABELS["auto"]).trace_add("write", lambda *_: self._sync_lang())
        self._sync_lang()

        # mục Nâng cao: thu gọn, ít dùng
        self.adv_btn = GradientButton(self.tab_proc, text="▸ Nâng cao", command=self._toggle_adv)
        self.adv_btn.pack(anchor="w", pady=(0, 8))
        self.adv = self._card(self.tab_proc, "Nâng cao")
        self.adv_outer = self.adv.master.master
        self.adv_outer.pack_forget()
        self._row(self.adv, 0, "Phóng to", ttk.Entry(self.adv, textvariable=self._var("upscale", "1"), width=INPUT_W))
        ttk.Label(self.adv, text="1 = không phóng to · 2 = ảnh chữ nhỏ", style="Hint.TLabel").grid(row=0, column=2, sticky="w", padx=(8, 0))
        self._row(self.adv, 1, "Cắt vùng", ttk.Entry(self.adv, textvariable=self._var("crop", ""), width=INPUT_W))
        ttk.Label(self.adv, text="x0,y0,x1,y1 theo pixel · để trống = cả trang", style="Hint.TLabel").grid(row=1, column=2, sticky="w", padx=(8, 0))
        self._row(self.adv, 2, "Đọc bảng kana", ttk.Combobox(self.adv, textvariable=self._var("kana", self.KANA_LABELS[""]),
                                                            values=list(self.KANA_LABELS.values()), state="readonly", width=INPUT_W))
        cb_c = self._check(self.adv, "cell_reocr", True, "Nhận dạng lại ô bảng có dòng vượt đường kẻ")
        cb_c.grid(row=3, column=0, columnspan=3, sticky="w", pady=(6, 0))
        Tip(cb_c, "Cắt riêng từng ô bị engine nối chữ qua đường kẻ rồi đọc lại. Chậm hơn một chút; tắt nếu muốn nhanh hơn.")
        cb_k = self._check(self.adv, "use_cache", True, "Dùng cache kết quả OCR (chạy lại cùng file sẽ nhanh hơn)")
        cb_k.grid(row=4, column=0, columnspan=3, sticky="w", pady=2)
        Tip(cb_k, "Lưu kết quả từng trang trong thư mục đầu ra (.cache). Tắt nếu muốn OCR lại từ đầu.")
        self.adv.columnconfigure(1, weight=1)

        # engine AI: gói GPU và model Chandra, có thanh tiến trình tải
        self._ai_card()

    def _ai_card(self):
        ai = self._card(self.tab_ai, "Engine AI (tùy chọn, tải một lần)")
        self._model_card(ai)
        if not gpupack.installed():
            row = ttk.Frame(ai, style="Card.TFrame")
            row.pack(fill="x", pady=(0, 6))
            self.pack_btn = GradientButton(row, text="Cài gói GPU + Chandra (vài GB)", command=self.install_pack, width=BTN_W)
            self.pack_btn.pack(side="left")
            # thanh tiến trình chỉ hiện khi bắt đầu cài (xem install_pack)
            self.pack_pb = ttk.Progressbar(row, mode="indeterminate", length=220, style="Accent.Horizontal.TProgressbar")
            self.pack_status = tk.StringVar(value="Chỉ tăng tốc Chandra. Cần card NVIDIA, cần Internet. Sau khi cài, khởi động lại app.")
            ttk.Label(ai, textvariable=self.pack_status, style="Hint.TLabel", wraplength=760, justify="left").pack(anchor="w", pady=(0, 10))
        if "chandra" in self.ENGINES:
            from .engines.chandra import model_downloaded
            cb_l = self._check(ai, "chandra_license", False, "Tôi đã đọc và chấp nhận điều khoản OpenRAIL-M của trọng số Chandra")
            cb_l.pack(anchor="w")
            Tip(cb_l, "Trọng số Chandra theo OpenRAIL-M: miễn ngưỡng thương mại khi dùng cá nhân/nghiên cứu. Chi tiết trong NOTICE.md.")
            row = ttk.Frame(ai, style="Card.TFrame")
            row.pack(fill="x", pady=(6, 0))
            self.dl_btn = GradientButton(row, text="Tải model Chandra", command=self.download_chandra, width=BTN_W)
            self.dl_btn.pack(side="left")
            self.dl_pb = ttk.Progressbar(row, maximum=100, length=220, style="Accent.Horizontal.TProgressbar")
            self.dl_pb.pack(side="left", padx=10)
            ready = model_downloaded()
            self.dl_status = tk.StringVar(value="Đã có model Chandra trên máy." if ready else "Chưa có model Chandra (vài GB, chỉ tải một lần).")
            ttk.Label(ai, textvariable=self.dl_status, style="Hint.TLabel").pack(anchor="w", pady=(4, 0))

    def _model_card(self, parent):
        """Model PaddleOCR (tiếng Anh, Trung) tải tự động; model VietOCR phải xuất bằng scripts/export_vi.py."""
        from .engines.paddle import PaddleEngine
        row = ttk.Frame(parent, style="Card.TFrame")
        row.pack(fill="x", pady=(0, 6))
        need = not PaddleEngine.is_available()[0]
        self.pm_btn = GradientButton(row, text="Tải model OCR (PaddleOCR)", width=BTN_W, command=self.download_paddle,
                                 state="normal" if need else "disabled")
        self.pm_btn.pack(side="left")
        self.pm_spin = Spinner(row, size=20)
        self.pm_pb = ttk.Progressbar(row, maximum=100, length=200, style="Accent.Horizontal.TProgressbar")
        self.pm_pb.pack(side="left", padx=10)
        self.pm_pct = tk.StringVar(value="")
        ttk.Label(row, textvariable=self.pm_pct, width=12).pack(side="left")
        self.pm_status = tk.StringVar(value=self._model_status_text())
        ttk.Label(parent, textvariable=self.pm_status, style="Hint.TLabel", wraplength=760, justify="left").pack(anchor="w", pady=(0, 10))

    def _model_status_text(self) -> str:
        from .engines.paddle import PaddleEngine
        from .engines.viet import VietnameseEngine
        paddle_ok = PaddleEngine.is_available()[0]
        vi_ok = VietnameseEngine.is_available()[0]
        lines = ["Model PaddleOCR (tiếng Anh, Trung): " + ("đã có." if paddle_ok else "chưa có — bấm nút để tải (vài chục MB)."),
                 "Model VietOCR (tiếng Việt): " + ("đã có." if vi_ok else "chưa có — không tải từ đây được; chạy scripts/export_vi.py (cần torch).")]
        return "\n".join(lines)

    def download_paddle(self):
        self.pm_btn.config(state="disabled")
        self.pm_pb["value"] = 0
        self.pm_pct.set("0%")
        self.pm_status.set("Đang tải model PaddleOCR từ Hugging Face / GitHub…")
        self.pm_spin.pack(side="left", padx=(0, 4), before=self.pm_pb)
        self.pm_spin.start()
        threading.Thread(target=self._paddle_worker, daemon=True).start()

    def _paddle_worker(self):
        from .engines import models as mdl
        try:
            mdl.download_paddle(progress=lambda i, n, name, frac: self.q.put(("pm_prog", (i, n, name, frac))))
            ok, msg = True, "Đã tải xong model PaddleOCR. " + self._model_status_text().split("\n")[1]
        except Exception as e:
            log.exception("Lỗi tải model PaddleOCR")
            ok, msg = False, f"Tải model PaddleOCR lỗi: {e}"
        self.q.put(("pm_done", (ok, msg)))

    def _on_pm_progress(self, i, n, name, frac):
        overall = (i + frac) / max(1, n)
        self.pm_pb["value"] = 100 * overall
        self.pm_pct.set(f"{round(100 * overall)}%")
        self.pm_status.set(f"Đang tải {name} (tệp {min(i + 1, n)}/{n})…")

    def _on_pm_done(self, ok, msg):
        self.pm_spin.stop()
        self.pm_spin.pack_forget()
        self.pm_pb["value"] = 100 if ok else 0
        self.pm_pct.set("100%" if ok else "")
        self.pm_status.set(msg)
        self.pm_btn.config(state="normal" if not ok else "disabled")

    def _tab_review(self):
        rev = self._card(self.tab_rev, "Rà soát")
        cb_v = self._check(rev, "review", False, "Xuất file rà soát *_review.html (ảnh trang cạnh chữ, tô đỏ chỗ nghi ngờ)")
        cb_v.grid(row=0, column=0, columnspan=3, sticky="w", pady=2)
        Tip(cb_v, "Mở file .html bằng trình duyệt để so ảnh trang với chữ đã nhận dạng. Dòng nghi ngờ được tô đỏ.")
        self._row(rev, 1, "Ngưỡng tin cậy", ttk.Entry(rev, textvariable=self._var("conf", "0.8"), width=INPUT_W))
        ttk.Label(rev, text="Dòng có độ tin cậy dưới ngưỡng bị tô đỏ. Mặc định 0.8.", style="Hint.TLabel").grid(row=1, column=2, sticky="w", padx=(8, 0))
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
        self.b_rev = GradientButton(bar, text="Mở file rà soát", command=lambda: self._open_result("review"), state="disabled")
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
                messagebox.showwarning("Engine", f"Chưa dùng được {self.ENGINE_LABELS[key]}: {why}")
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

    def _redraw(self):
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
            messagebox.showerror("Tìm nhanh", f"Không mở được: {e}")

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
            raise ValueError("Ngưỡng độ tin cậy phải là số, ví dụ 0.8.") from None
        try:
            upscale = float(self._var("upscale", "1").get() or "1")
        except ValueError:
            raise ValueError("Phóng to phải là số, ví dụ 1 hoặc 2.") from None
        if upscale <= 0:
            raise ValueError("Phóng to phải lớn hơn 0.")
        try:
            crop = pipeline.parse_crop(self._var("crop", "").get())
        except ValueError as e:
            raise ValueError(f"Vùng cắt không hợp lệ: {e}") from None
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
            messagebox.showerror("OCR", "Khoảng trang không hợp lệ."); return
        try:
            opts = self._read_options()
        except ValueError as e:
            messagebox.showerror("OCR", str(e)); return
        self.statuses = ["Chờ"] * len(self.files)
        self._redraw()
        self.results = []
        self._t0 = time.time()
        self.cancel.clear(); self.btn.config(state="disabled"); self.stop.config(state="normal")
        out = self._var("out", "").get().strip()
        args = (list(self.files), Path(out) if out else None, pages, opts)
        self.worker = threading.Thread(target=self.run_job, args=args, daemon=True); self.worker.start()

    def run_job(self, files, out, pages, opts):
        reviews, errors = [], 0
        for i, f in enumerate(files):
            if self.cancel.is_set():
                break
            self.q.put(("file", (i, "Đang xử lý")))
            self.q.put(("status", f"Đang nạp model / xử lý {f.name} ({i + 1}/{len(files)})…"))
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
                log.exception("Lỗi khi xử lý %s", f)
                self.q.put(("file", (i, "Lỗi")))
        self.q.put(("results", list(self.results)))
        if self.cancel.is_set():
            msg = "Đã dừng."
        else:
            msg = f"Xong. Kết quả ở: {out}"
            if reviews:
                msg += "\nFile rà soát: " + ", ".join(reviews)
        if errors:
            msg += f"\nCó {errors} file lỗi. Chi tiết trong nhật ký: {LOG_FILE}"
        self.q.put(("done", msg))

    def _hardware_worker(self):
        from . import engines
        try:
            gpus = gpu.detect()
            gtxt = f"GPU: {gpus[0].name}" if gpus else "Không thấy GPU NVIDIA"
            eng, why = engines.resolve("auto")
            text = f"{gtxt} · Engine tự động: {eng} ({why})"
        except Exception:
            text = "Không dò được phần cứng"
        self.q.put(("hw", text))

    def install_pack(self):
        if not messagebox.askyesno("Gói GPU", "Tải torch CUDA và Chandra, khoảng vài GB. Tiếp tục?"):
            return
        self.pack_btn.config(state="disabled")
        self.pack_pb.pack(side="left", padx=10)
        self.pack_pb.start(12)
        threading.Thread(target=self._pack_worker, daemon=True).start()

    def _pack_worker(self):
        try:
            gpupack.install(progress=lambda m: self.q.put(("pack", m)))
            msg = "Đã cài gói GPU. Hãy khởi động lại OCR-Nhat để dùng Chandra."
        except Exception as e:
            log.exception("Lỗi cài gói GPU")
            msg = f"Cài gói GPU lỗi: {e}"
        self.q.put(("packdone", msg))

    def download_chandra(self):
        if not self._var("chandra_license", False).get():
            messagebox.showwarning("Chandra", "Hãy tick xác nhận điều khoản OpenRAIL-M trước khi tải model.")
            return
        self.dl_btn.config(state="disabled")
        self.dl_pb["value"] = 0
        self.dl_status.set("Đang tải model Chandra từ Hugging Face (vài GB, có thể mất nhiều phút)…")
        threading.Thread(target=self._download_worker, daemon=True).start()

    def _download_worker(self):
        from .engines.chandra import download_model
        try:
            download_model(progress=lambda d, t: self.q.put(("dl_prog", (d, t))))
            msg = "Đã tải xong model Chandra."
        except Exception as e:
            log.exception("Lỗi tải model Chandra")
            msg = f"Tải model lỗi: {e}"
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
                messagebox.showinfo("Rà soát", "Chưa có file rà soát. Bật “Xuất file rà soát” ở tab Rà soát rồi chạy lại.")
        except OSError as e:
            messagebox.showerror("Mở file", f"Không mở được: {e}")

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
            log.exception("Không vẽ được xem trước %s", f)
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
                    self.dl_status.set(f"Đang tải model Chandra: {d * 100 // max(1, t)}% ({d // 2**20} / {t // 2**20} MB)")
                elif k == "dl":
                    self.dl_status.set(v); self.dl_pb["value"] = 100 if "xong" in v else 0
                    self.dl_btn.config(state="normal")
                elif k == "pm_prog":
                    self._on_pm_progress(*v)
                elif k == "pm_done":
                    self._on_pm_done(*v)
                elif k == "pack":
                    self.pack_status.set(v)
                elif k == "packdone":
                    self.pack_pb.stop(); self.pack_pb.pack_forget()
                    self.pack_status.set(v); self.pack_btn.config(state="normal")
                else:   # done
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
