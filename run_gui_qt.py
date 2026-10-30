"""Mở giao diện PySide6 (thử nghiệm). Giao diện Tkinter vẫn có ở run_gui.py.

--selftest: dựng cửa sổ, kiểm bốn mục, thoát với mã 0 (dùng trong CI để kiểm exe mà không cần thao tác).
"""
import multiprocessing
import sys


def selftest() -> int:
    from PySide6.QtWidgets import QApplication
    from ocrnhat.gui_qt import MainWindow
    app = QApplication.instance() or QApplication([])
    win = MainWindow()
    win.show()
    app.processEvents()
    ok = win.stack.count() == 4 and win.nav.count() == 4
    win.close()
    print("selftest:", "ok" if ok else "lỗi", flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    multiprocessing.freeze_support()
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    from ocrnhat.gui_qt import run
    sys.exit(run())
