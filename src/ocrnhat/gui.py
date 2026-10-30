"""Giao diện Tkinter đơn giản: chọn file/thư mục, chọn trang và tùy chọn, chạy OCR nền."""
from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import engines, gpu, pipeline
from .cli import collect


class App(tk.Tk):
    DEV_LABELS = {"auto": "Tự động", "cpu": "CPU", "cuda": "GPU (NVIDIA)"}
    # chandra còn là placeholder (chưa cài đặt) nên không đưa lên giao diện; dòng lệnh vẫn có
    ENGINES = ("auto", "ndlocr")

    def __init__(self):
        super().__init__()
        self.title("OCR tiếng Nhật")
        self.geometry("720x720")
        self.files: list[Path] = []
        self.q: queue.Queue = queue.Queue()
        self.cancel = threading.Event()
        self.worker: threading.Thread | None = None

        top = ttk.Frame(self, padding=8); top.pack(fill="x")
        ttk.Button(top, text="Thêm file…", command=self.add_files).pack(side="left")
        ttk.Button(top, text="Thêm thư mục…", command=self.add_dir).pack(side="left", padx=4)
        ttk.Button(top, text="Xóa danh sách", command=self.clear).pack(side="left")

        self.lb = tk.Listbox(self, height=8); self.lb.pack(fill="both", expand=False, padx=8)

        opt = ttk.Frame(self, padding=8); opt.pack(fill="x")
        ttk.Label(opt, text="Thư mục lưu:").grid(row=0, column=0, sticky="w")
        self.out = tk.StringVar(value=str(Path.home() / "ocr_output"))
        ttk.Entry(opt, textvariable=self.out, width=50).grid(row=0, column=1, padx=4)
        ttk.Button(opt, text="Chọn…", command=self.pick_out).grid(row=0, column=2)
        ttk.Label(opt, text="Trang (vd 1-5,8; để trống = tất cả):").grid(row=1, column=0, sticky="w", pady=4)
        self.pages = tk.StringVar()
        ttk.Entry(opt, textvariable=self.pages, width=20).grid(row=1, column=1, sticky="w", padx=4)
        self.marker = tk.BooleanVar(value=True)
        self.txt = tk.BooleanVar(value=True)
        ttk.Checkbutton(opt, text="Ghi số trang gốc 【原本 p.N】", variable=self.marker).grid(row=2, column=0, sticky="w")
        ttk.Checkbutton(opt, text="Ghi kèm file .txt", variable=self.txt).grid(row=2, column=1, sticky="w")

        ttk.Label(opt, text="Engine:").grid(row=3, column=0, sticky="w", pady=4)
        self.engine = tk.StringVar(value="auto")
        ttk.Combobox(opt, textvariable=self.engine, values=list(self.ENGINES), state="readonly",
                     width=12).grid(row=3, column=1, sticky="w", padx=4)

        ttk.Label(opt, text="Thiết bị:").grid(row=4, column=0, sticky="w", pady=4)
        self.dev = tk.StringVar(value=self.DEV_LABELS["auto"])
        ttk.Combobox(opt, textvariable=self.dev, values=list(self.DEV_LABELS.values()), state="readonly",
                     width=28).grid(row=4, column=1, sticky="w", padx=4)
        ttk.Label(opt, text="GPU: chỉ NVIDIA, cần onnxruntime-gpu + CUDA", foreground="#666").grid(row=4, column=2, sticky="w")

        self.ruby = tk.BooleanVar(value=False)
        ttk.Checkbutton(opt, text="Giữ furigana thành ruby của Word", variable=self.ruby).grid(row=5, column=0, columnspan=2, sticky="w")
        self.review = tk.BooleanVar(value=False)
        ttk.Checkbutton(opt, text="Xuất file rà soát *_review.html (ảnh trang cạnh chữ, tô đỏ chỗ nghi ngờ)",
                        variable=self.review).grid(row=6, column=0, columnspan=2, sticky="w")
        ttk.Label(opt, text="Ngưỡng độ tin cậy rà soát:").grid(row=7, column=0, sticky="w", pady=4)
        self.conf = tk.StringVar(value="0.8")
        ttk.Entry(opt, textvariable=self.conf, width=8).grid(row=7, column=1, sticky="w", padx=4)

        ttk.Label(opt, text="Cắt vùng x0,y0,x1,y1 (pixel; để trống = cả trang):").grid(row=8, column=0, sticky="w")
        self.crop = tk.StringVar()
        ttk.Entry(opt, textvariable=self.crop, width=24).grid(row=8, column=1, sticky="w", padx=4)
        ttk.Label(opt, text="Phóng to trước OCR (1 = không, 2 = ảnh chữ nhỏ):").grid(row=9, column=0, sticky="w", pady=4)
        self.upscale = tk.StringVar(value="1")
        ttk.Entry(opt, textvariable=self.upscale, width=8).grid(row=9, column=1, sticky="w", padx=4)

        bar = ttk.Frame(self, padding=8); bar.pack(fill="x")
        self.btn = ttk.Button(bar, text="Bắt đầu OCR", command=self.start); self.btn.pack(side="left")
        self.stop = ttk.Button(bar, text="Dừng", command=self.cancel.set, state="disabled"); self.stop.pack(side="left", padx=4)
        self.pb = ttk.Progressbar(self, maximum=100); self.pb.pack(fill="x", padx=8)
        self.status = tk.StringVar(value="Sẵn sàng.")
        ttk.Label(self, textvariable=self.status, wraplength=690).pack(fill="x", padx=8, pady=4)
        self.after(150, self.poll)

    def add_files(self):
        fs = filedialog.askopenfilenames(filetypes=[("PDF / ảnh", "*.pdf *.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp")])
        self._add(collect(list(fs)))

    def add_dir(self):
        d = filedialog.askdirectory()
        if d:
            self._add(collect([d]))

    def _add(self, fs):
        for f in fs:
            if f not in self.files:
                self.files.append(f); self.lb.insert("end", str(f))

    def clear(self):
        self.files.clear(); self.lb.delete(0, "end")

    def pick_out(self):
        d = filedialog.askdirectory()
        if d:
            self.out.set(d)

    def _options(self) -> dict:
        """Đọc và kiểm tra các ô nhập. Ném ValueError với thông báo tiếng Việt nếu sai."""
        try:
            conf = float(self.conf.get())
        except ValueError:
            raise ValueError("Ngưỡng độ tin cậy phải là số, ví dụ 0.8.") from None
        try:
            upscale = float(self.upscale.get() or "1")
        except ValueError:
            raise ValueError("Phóng to phải là số, ví dụ 1 hoặc 2.") from None
        if upscale <= 0:
            raise ValueError("Phóng to phải lớn hơn 0.")
        try:
            crop = pipeline.parse_crop(self.crop.get())
        except ValueError as e:
            raise ValueError(f"Vùng cắt không hợp lệ: {e}") from None
        dev = next(k for k, v in self.DEV_LABELS.items() if v == self.dev.get())
        return dict(write_txt=self.txt.get(), page_marker=self.marker.get(), device=dev, ruby=self.ruby.get(),
                    review=self.review.get(), conf_threshold=conf, engine=self.engine.get(),
                    crop=crop, upscale=upscale)

    def start(self):
        if not self.files:
            messagebox.showinfo("OCR", "Chưa chọn file."); return
        try:
            pages = pipeline.parse_pages(self.pages.get())
        except ValueError:
            messagebox.showerror("OCR", "Khoảng trang không hợp lệ."); return
        try:
            opts = self._options()
        except ValueError as e:
            messagebox.showerror("OCR", str(e)); return
        self.cancel.clear(); self.btn.config(state="disabled"); self.stop.config(state="normal")
        args = (list(self.files), Path(self.out.get()), pages, opts)
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

    def poll(self):
        try:
            while True:
                k, v = self.q.get_nowait()
                if k == "prog":
                    d, t, m = v; self.pb["value"] = 100 * d / max(1, t); self.status.set(f"[{d}/{t}] {m}")
                elif k == "status":
                    self.status.set(v)
                else:
                    self.status.set(v); self.btn.config(state="normal"); self.stop.config(state="disabled")
        except queue.Empty:
            pass
        self.after(150, self.poll)


def run():
    App().mainloop()
