"""Giao diện Tkinter đơn giản: chọn file/thư mục, chọn trang, chạy OCR nền."""
from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import pipeline
from .cli import collect


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("OCR tiếng Nhật")
        self.geometry("720x520")
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

    def start(self):
        if not self.files:
            messagebox.showinfo("OCR", "Chưa chọn file."); return
        try:
            pages = pipeline.parse_pages(self.pages.get())
        except ValueError:
            messagebox.showerror("OCR", "Khoảng trang không hợp lệ."); return
        self.cancel.clear(); self.btn.config(state="disabled"); self.stop.config(state="normal")
        args = (list(self.files), Path(self.out.get()), pages, self.marker.get(), self.txt.get())
        self.worker = threading.Thread(target=self.run_job, args=args, daemon=True); self.worker.start()

    def run_job(self, files, out, pages, marker, txt):
        try:
            for i, f in enumerate(files, 1):
                self.q.put(("status", f"Đang nạp model / xử lý {f.name} ({i}/{len(files)})…"))
                pipeline.process_file(
                    f, out, 200, pages if f.suffix.lower() == ".pdf" else None,
                    write_txt=txt, page_marker=marker,
                    progress=lambda d, t, m: self.q.put(("prog", (d, t, m))),
                    cancel=self.cancel.is_set)
                if self.cancel.is_set():
                    break
            self.q.put(("done", "Đã dừng." if self.cancel.is_set() else f"Xong. Kết quả ở: {out}"))
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
