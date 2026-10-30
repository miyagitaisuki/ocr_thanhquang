"""Mở giao diện PySide6 (thử nghiệm, bước 2). Giao diện mặc định vẫn là run_gui.py (Tkinter)."""
import multiprocessing
import sys

if __name__ == "__main__":
    multiprocessing.freeze_support()
    from ocrnhat.gui_qt import run
    sys.exit(run())
