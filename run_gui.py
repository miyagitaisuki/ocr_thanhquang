"""Điểm vào cho PyInstaller (không có tham số = mở giao diện, có tham số = dòng lệnh)."""
import multiprocessing
import sys

if __name__ == "__main__":
    multiprocessing.freeze_support()
    if len(sys.argv) > 1:
        from ocrnhat.cli import main
        raise SystemExit(main())
    from ocrnhat.gui import run
    run()
