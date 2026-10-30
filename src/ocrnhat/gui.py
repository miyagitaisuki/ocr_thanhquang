"""Giao diện Tkinter: chọn file/thư mục, chọn trang và tùy chọn, chạy OCR nền.

Bố cục kiểu PDFsam: nền sáng, mỗi nhóm tùy chọn nằm trong một khối có tiêu đề,
bảng file có cột, nút chính nổi bật, tiến trình và trạng thái ở dưới cùng.
"""
from __future__ import annotations

import importlib.util
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, font as tkfont, messagebox, ttk

from . import pipeline
from .cli import collect

try:  # kéo-thả file: cần tkinterdnd2 (tkdnd); không có thì giao diện vẫn chạy với nút bấm
    from tkinterdnd2 import DND_FILES, TkinterDnD
    _Base, HAS_DND = TkinterDnD.Tk, True
except ImportError:
    DND_FILES, _Base, HAS_DND = None, tk.Tk, False

BG = "#F4F5F7"        # nền cửa sổ
CARD = "#FFFFFF"      # nền khối tùy chọn
TEXT = "#1F2328"
MUTED = "#6B7280"
ACCENT = "#1F6FEB"    # nút chính
ACCENT_DARK = "#1858BF"
LINE = "#D8DCE3"


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


class App(_Base):
    DEV_LABELS = {"auto": "Tự động", "cpu": "CPU", "cuda": "GPU (NVIDIA)"}
    KANA_LABELS = {"": "Tắt", "template": "Mẫu IPAGothic (thử nghiệm)", "tesseract": "Tesseract (thử nghiệm)"}
    # chandra chỉ hiện khi bản này có đóng gói Chandra (exe GPU hoặc máy đã cài ocrnhat[chandra])
    ENGINES = ("auto", "ndlocr") + (("chandra",) if importlib.util.find_spec("chandra") else ())

    def __init__(self):
        super().__init__()
        self.title("OCR tiếng Nhật")
        self.geometry("920x820")
        self.minsize(820, 600)
        self.configure(background=BG)
        self.files: list[Path] = []
        self.q: queue.Queue = queue.Queue()
        self.cancel = threading.Event()
        self.worker: threading.Thread | None = None
        self._vars: dict = {}
        self._style()

        # nội dung cuộn dọc để vừa mọi màn hình (kể cả laptop 768px)
        canvas = tk.Canvas(self, background=BG, highlightthickness=0, borderwidth=0)
        vbar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vbar.set)
        vbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        page = ttk.Frame(canvas, style="Page.TFrame", padding=(20, 16))
        win = canvas.create_window((0, 0), window=page, anchor="nw")
        page.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(win, width=e.width))
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-e.delta / 120), "units"))

        # --- tài liệu nguồn ---
        src = self._card(page, "Tài liệu nguồn")
        bar = ttk.Frame(src, style="Card.TFrame")
        bar.pack(fill="x", pady=(0, 8))
        b_add = ttk.Button(bar, text="Thêm file…", command=self.add_files); b_add.pack(side="left")
        b_dir = ttk.Button(bar, text="Thêm thư mục…", command=self.add_dir); b_dir.pack(side="left", padx=6)
        b_clr = ttk.Button(bar, text="Xóa danh sách", command=self.clear); b_clr.pack(side="left")
        Tip(b_add, "Chọn một hoặc nhiều file PDF hoặc ảnh (PNG, JPG, TIFF...).")
        Tip(b_dir, "Lấy tất cả PDF và ảnh trong một thư mục.")
        Tip(b_clr, "Bỏ hết file khỏi danh sách. File gốc trên máy không bị xóa.")
        self.count = tk.StringVar(value="Chưa có file nào")
        ttk.Label(bar, textvariable=self.count, style="Muted.TLabel").pack(side="right")
        ttk.Label(src, style="Hint.TLabel", wraplength=800, justify="left", text=(
            "Thêm file: chọn một hoặc nhiều PDF/ảnh. Thêm thư mục: lấy mọi PDF/ảnh trong thư mục. "
            "Xóa danh sách: bỏ các file khỏi danh sách, không xóa file gốc trên máy.")).pack(anchor="w", pady=(0, 6))

        table = ttk.Frame(src, style="Card.TFrame")
        table.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(table, columns=("name", "folder"), show="headings", height=7, selectmode="extended")
        self.tree.heading("name", text="Tên file", anchor="w")
        self.tree.heading("folder", text="Thư mục", anchor="w")
        self.tree.column("name", width=300, anchor="w")
        self.tree.column("folder", width=520, anchor="w")
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

        # --- đầu ra và trang ---
        out = self._card(page, "Đầu ra")
        self._row(out, 0, "Thư mục lưu", ttk.Entry(out, textvariable=self._var("out", str(Path.home() / "ocr_output")), width=52))
        b_out = ttk.Button(out, text="Chọn…", command=self.pick_out); b_out.grid(row=0, column=2, padx=(8, 0), pady=4)
        Tip(b_out, "Chọn thư mục để lưu file kết quả (.docx và .txt).")
        ttk.Label(out, text="Nơi lưu file Word (.docx) và văn bản (.txt) kết quả.", style="Hint.TLabel").grid(row=3, column=0, columnspan=3, sticky="w", pady=(0, 2))
        self._row(out, 1, "Trang", ttk.Entry(out, textvariable=self._var("pages", ""), width=24))
        ttk.Label(out, text="ví dụ 1-5,8 · để trống = tất cả (chỉ áp dụng cho PDF)", style="Hint.TLabel").grid(row=1, column=2, sticky="w", padx=(8, 0))
        checks = ttk.Frame(out, style="Card.TFrame")
        checks.grid(row=2, column=0, columnspan=3, sticky="w", pady=(6, 0))
        cb_m = self._check(checks, "marker", True, "Ghi số trang gốc 【原本 p.N】"); cb_m.pack(anchor="w", pady=2)
        cb_t = self._check(checks, "txt", True, "Ghi kèm file .txt"); cb_t.pack(anchor="w", pady=2)
        cb_r = self._check(checks, "ruby", False, "Giữ furigana thành ruby của Word"); cb_r.pack(anchor="w", pady=2)
        Tip(cb_m, "Mỗi trang trong Word có dòng 【原本 p.N】 để biết trang gốc trong sách.")
        Tip(cb_t, "Thêm file .txt thuần để dán vào công cụ khác.")
        Tip(cb_r, "Chữ nhỏ (furigana) hiện phía trên chữ Hán bằng ruby của Word. Mặc định bỏ furigana.")
        out.columnconfigure(1, weight=1)

        # --- xử lý OCR ---
        proc = self._card(page, "Xử lý OCR")
        ttk.Label(proc, text="auto: tự chọn engine phù hợp. ndlocr: engine OCR chính.", style="Hint.TLabel").grid(row=0, column=2, sticky="w", padx=(8, 0))
        self._row(proc, 0, "Engine", ttk.Combobox(proc, textvariable=self._var("engine", "auto"), values=list(self.ENGINES), state="readonly", width=14))
        self._row(proc, 1, "Thiết bị", ttk.Combobox(proc, textvariable=self._var("dev", self.DEV_LABELS["auto"]), values=list(self.DEV_LABELS.values()), state="readonly", width=24))
        ttk.Label(proc, text="GPU chỉ dùng được với NVIDIA và onnxruntime-gpu + CUDA; không có thì tự lùi về CPU.",
                  style="Hint.TLabel", wraplength=640, justify="left").grid(row=2, column=0, columnspan=3, sticky="w", pady=(4, 0))
        self._row(proc, 3, "Phóng to", ttk.Entry(proc, textvariable=self._var("upscale", "1"), width=8))
        ttk.Label(proc, text="1 = không phóng to · 2 = ảnh chữ nhỏ", style="Hint.TLabel").grid(row=3, column=2, sticky="w", padx=(8, 0))
        self._row(proc, 4, "Cắt vùng", ttk.Entry(proc, textvariable=self._var("crop", ""), width=24))
        ttk.Label(proc, text="x0,y0,x1,y1 theo pixel · để trống = cả trang", style="Hint.TLabel").grid(row=4, column=2, sticky="w", padx=(8, 0))
        cb_c = self._check(proc, "cell_reocr", True, "Nhận dạng lại ô bảng có dòng vượt đường kẻ")
        cb_c.grid(row=5, column=0, columnspan=3, sticky="w", pady=(6, 0))
        Tip(cb_c, "Cắt riêng từng ô bị engine nối chữ qua đường kẻ rồi đọc lại. Chậm hơn một chút; tắt nếu muốn nhanh hơn.")
        cb_k = self._check(proc, "use_cache", True, "Dùng cache kết quả OCR (chạy lại cùng file sẽ nhanh hơn)")
        cb_k.grid(row=6, column=0, columnspan=3, sticky="w", pady=2)
        Tip(cb_k, "Lưu kết quả từng trang trong thư mục đầu ra (.cache). Tắt nếu muốn OCR lại từ đầu.")
        self._row(proc, 7, "Đọc bảng kana", ttk.Combobox(proc, textvariable=self._var("kana", self.KANA_LABELS[""]), values=list(self.KANA_LABELS.values()), state="readonly", width=34))
        if "chandra" in self.ENGINES:
            from .engines.chandra import model_downloaded
            dl = ttk.Frame(proc)
            dl.grid(row=8, column=0, columnspan=3, sticky="w", pady=(8, 0))
            cb_l = self._check(dl, "chandra_license", False, "Tôi đã đọc và chấp nhận điều khoản OpenRAIL-M của trọng số Chandra")
            cb_l.pack(anchor="w")
            Tip(cb_l, "Trọng số Chandra theo OpenRAIL-M: miễn ngưỡng thương mại khi dùng cá nhân/nghiên cứu. Chi tiết trong NOTICE.md.")
            row = ttk.Frame(dl)
            row.pack(anchor="w", pady=(4, 0))
            self.dl_btn = ttk.Button(row, text="Tải model Chandra", command=self.download_chandra)
            self.dl_btn.pack(side="left")
            ready = model_downloaded()
            self.dl_status = tk.StringVar(value="Đã có model Chandra trên máy." if ready else "Chưa có model Chandra (vài GB, chỉ tải một lần).")
            ttk.Label(row, textvariable=self.dl_status, style="Hint.TLabel").pack(side="left", padx=(10, 0))
        Tip(proc.grid_slaves(row=7, column=1)[0], "Thử nghiệm. Đọc ô bảng chữ kana (trang 13–16, 19). Mẫu IPAGothic cho kết quả tốt hơn; ô không chắc để trống. Luôn xuất file *_kana_review.html để đối chiếu.")
        proc.columnconfigure(1, weight=1)

        # --- rà soát ---
        rev = self._card(page, "Rà soát")
        cb_v = self._check(rev, "review", False, "Xuất file rà soát *_review.html (ảnh trang cạnh chữ, tô đỏ chỗ nghi ngờ)")
        cb_v.grid(row=0, column=0, columnspan=3, sticky="w", pady=2)
        Tip(cb_v, "Mở file .html bằng trình duyệt để so ảnh trang với chữ đã nhận dạng. Dòng nghi ngờ được tô đỏ.")
        self._row(rev, 1, "Ngưỡng tin cậy", ttk.Entry(rev, textvariable=self._var("conf", "0.8"), width=8))
        ttk.Label(rev, text="Dòng có độ tin cậy dưới ngưỡng này bị tô đỏ. Mặc định 0.8; cao hơn thì đánh dấu nhiều dòng hơn.", style="Hint.TLabel", wraplength=520, justify="left").grid(row=1, column=2, sticky="w", padx=(8, 0))
        rev.columnconfigure(1, weight=1)

        # --- hành động ---
        bar2 = ttk.Frame(page, style="Page.TFrame")
        bar2.pack(fill="x", pady=(14, 0))
        self.btn = ttk.Button(bar2, text="▶  Chạy OCR", style="Accent.TButton", command=self.start)
        self.btn.pack(side="left")
        self.stop = ttk.Button(bar2, text="Dừng", command=self.cancel.set, state="disabled")
        self.stop.pack(side="left", padx=8)
        Tip(self.btn, "Bắt đầu OCR cho mọi file trong danh sách.")
        Tip(self.stop, "Dừng sau trang đang xử lý. Các trang đã xong vẫn được lưu.")
        ttk.Label(page, style="Hint.TLabel", wraplength=860, justify="left", text=(
            "Chạy OCR: xử lý mọi file trong danh sách theo các tùy chọn ở trên. "
            "Dừng: dừng sau trang đang làm; các trang đã xong vẫn được lưu.")).pack(fill="x", pady=(6, 0))
        self.pb = ttk.Progressbar(page, maximum=100, style="Accent.Horizontal.TProgressbar")
        self.pb.pack(fill="x", pady=(14, 4))
        self.status = tk.StringVar(value="Sẵn sàng.")
        ttk.Label(page, textvariable=self.status, style="Status.TLabel", wraplength=860, justify="left").pack(fill="x")
        self.after(150, self.poll)

    # ---------- giao diện ----------

    def _style(self):
        base = tkfont.nametofont("TkDefaultFont")
        base.configure(size=10)
        tkfont.nametofont("TkHeadingFont").configure(size=10, weight="bold")
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure(".", background=BG, foreground=TEXT, font=base)
        s.configure("Page.TFrame", background=BG)
        s.configure("Card.TFrame", background=CARD)
        s.configure("CardTitle.TLabel", background=CARD, foreground=TEXT, font=("TkDefaultFont", 11, "bold"))
        s.configure("Card.TLabel", background=CARD, foreground=TEXT)
        s.configure("Card.TCheckbutton", background=CARD, foreground=TEXT)
        s.configure("Muted.TLabel", background=CARD, foreground=MUTED)
        s.configure("Hint.TLabel", background=CARD, foreground=MUTED)
        s.configure("Status.TLabel", background=BG, foreground=TEXT)
        s.configure("TButton", padding=(12, 6), background=CARD, bordercolor=LINE, focusthickness=0)
        s.map("TButton", background=[("active", "#EEF1F6"), ("disabled", CARD)],
              foreground=[("disabled", "#A0A6B1")])
        s.configure("Accent.TButton", background=ACCENT, foreground="#FFFFFF", bordercolor=ACCENT, padding=(18, 8))
        s.map("Accent.TButton", background=[("active", ACCENT_DARK), ("disabled", "#A9C5F2")],
              foreground=[("disabled", "#FFFFFF")])
        s.configure("TEntry", fieldbackground=CARD, bordercolor=LINE, padding=4)
        s.configure("TCombobox", fieldbackground=CARD, bordercolor=LINE, padding=3)
        s.configure("Treeview", background=CARD, fieldbackground=CARD, rowheight=24, bordercolor=LINE)
        s.configure("Treeview.Heading", background="#EEF1F6", foreground=TEXT, relief="flat", padding=(8, 4))
        s.map("Treeview", background=[("selected", "#DCE8FB")], foreground=[("selected", TEXT)])
        s.configure("Accent.Horizontal.TProgressbar", background=ACCENT, troughcolor="#E3E7EE", bordercolor=BG)

    def _card(self, parent, title: str) -> ttk.Frame:
        """Khối tùy chọn: nền trắng, viền mảnh, tiêu đề đậm ở đầu."""
        outer = tk.Frame(parent, background=LINE)
        outer.pack(fill="x", pady=(0, 12))
        box = ttk.Frame(outer, style="Card.TFrame", padding=(16, 12))
        box.pack(fill="both", expand=True, padx=1, pady=1)
        ttk.Label(box, text=title, style="CardTitle.TLabel").pack(anchor="w", pady=(0, 8))
        body = ttk.Frame(box, style="Card.TFrame")   # phần thân dùng grid, tách khỏi tiêu đề dùng pack
        body.pack(fill="both", expand=True)
        return body

    def _var(self, name: str, default):
        """Biến Tk theo tên, tạo một lần."""
        if name not in self._vars:
            self._vars[name] = tk.StringVar(value=default) if isinstance(default, str) else tk.BooleanVar(value=default)
        return self._vars[name]

    def _row(self, parent, row: int, label: str, widget):
        """Hàng nhãn + ô nhập. Bố cục dùng grid nên mọi khối cùng một cột nhãn."""
        ttk.Label(parent, text=label, style="Card.TLabel", width=14, anchor="w").grid(row=row, column=0, sticky="w", pady=4, padx=(0, 8))
        widget.grid(row=row, column=1, sticky="w", pady=4)
        return widget

    def _check(self, parent, name: str, default: bool, text: str) -> ttk.Checkbutton:
        return ttk.Checkbutton(parent, text=text, variable=self._var(name, default), style="Card.TCheckbutton")

    # ---------- danh sách file ----------

    def _refresh_list(self):
        n = len(self.files)
        self.count.set(f"{n} file" if n else "Chưa có file nào")
        if n:
            self.empty.place_forget()
        else:
            self.empty.place(relx=0.5, rely=0.5, anchor="center")

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
                self.files.append(f)
                self.tree.insert("", "end", values=(f.name, str(f.parent)))
        self._refresh_list()

    def clear(self):
        self.files.clear()
        self.tree.delete(*self.tree.get_children())
        self._refresh_list()

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
        return dict(write_txt=self._var("txt", True).get(), page_marker=self._var("marker", True).get(),
                    device=dev, ruby=self._var("ruby", False).get(),
                    review=self._var("review", False).get(), conf_threshold=conf,
                    engine=self._var("engine", "auto").get(), crop=crop, upscale=upscale,
                    cell_reocr=self._var("cell_reocr", True).get(), use_cache=self._var("use_cache", True).get(),
                    kana_reader=next(k for k, v in self.KANA_LABELS.items() if v == self._var("kana", "").get()))

    def start(self):
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
        self.cancel.clear(); self.btn.config(state="disabled"); self.stop.config(state="normal")
        args = (list(self.files), Path(self._var("out", "").get()), pages, opts)
        self.worker = threading.Thread(target=self.run_job, args=args, daemon=True); self.worker.start()

    def run_job(self, files, out, pages, opts):
        reviews = []
        try:
            for i, f in enumerate(files, 1):
                self.q.put(("status", f"Đang nạp model / xử lý {f.name} ({i}/{len(files)})…"))
                r = pipeline.process_file(
                    f, out, 200, pages if f.suffix.lower() == ".pdf" else None,
                    progress=lambda d, t, m: self.q.put(("prog", (d, t, m))),
                    cancel=self.cancel.is_set, **opts)
                if r.get("review"):
                    reviews.append(r["review"])
                if self.cancel.is_set():
                    break
            if self.cancel.is_set():
                msg = "Đã dừng."
            else:
                msg = f"Xong. Kết quả ở: {out}"
                if reviews:
                    msg += "\nFile rà soát: " + ", ".join(reviews)
            self.q.put(("done", msg))
        except Exception as e:  # hiển thị lỗi thay vì chết im lặng
            self.q.put(("done", f"Lỗi: {e}"))

    def download_chandra(self):
        if not self._var("chandra_license", False).get():
            messagebox.showwarning("Chandra", "Hãy tick xác nhận điều khoản OpenRAIL-M trước khi tải model.")
            return
        self.dl_btn.config(state="disabled")
        self.dl_status.set("Đang tải model Chandra từ Hugging Face (vài GB, có thể mất nhiều phút)…")
        threading.Thread(target=self._download_worker, daemon=True).start()

    def _download_worker(self):
        from .engines.chandra import download_model
        try:
            download_model()
            msg = "Đã tải xong model Chandra."
        except Exception as e:
            msg = f"Tải model lỗi: {e}"
        self.q.put(("dl", msg))

    def poll(self):
        try:
            while True:
                k, v = self.q.get_nowait()
                if k == "prog":
                    d, t, m = v; self.pb["value"] = 100 * d / max(1, t); self.status.set(f"[{d}/{t}] {m}")
                elif k == "status":
                    self.status.set(v)
                elif k == "dl":
                    self.dl_status.set(v); self.dl_btn.config(state="normal")
                else:
                    self.status.set(v); self.btn.config(state="normal"); self.stop.config(state="disabled")
        except queue.Empty:
            pass
        self.after(150, self.poll)


def run():
    App().mainloop()
