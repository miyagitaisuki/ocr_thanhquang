"""Điểm vào cho PyInstaller và chạy từ mã nguồn: không có tham số = mở giao diện, có tham số = dòng lệnh.

--selftest: dựng cửa sổ, kiểm bốn mục, thoát với mã 0 (CI kiểm exe mà không cần thao tác).
"""
import multiprocessing
import sys


def selftest() -> int:
    from PySide6.QtWidgets import QApplication
    from ocrnhat.gui import MainWindow
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
    if "--gpu-worker" in sys.argv:   # tiến trình con chạy OCR GPU (gpu_pack.py), không mở giao diện
        from ocrnhat.gpu_worker import main as gpu_worker_main
        raise SystemExit(gpu_worker_main())
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    if len(sys.argv) > 1:
        from ocrnhat.cli import main
        raise SystemExit(main())
    from ocrnhat.gui import run
    sys.exit(run())
