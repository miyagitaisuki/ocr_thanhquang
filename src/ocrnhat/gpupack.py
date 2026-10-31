"""Gói GPU tùy chọn: torch CUDA + Chandra, tải về sau khi người dùng bấm nút trong GUI.

Exe CPU không chứa torch. Khi người dùng bấm "Cài gói GPU", pip (đóng gói sẵn trong exe) cài vào
thư mục riêng (`%LOCALAPPDATA%\\OCR-Nhat\\gpu`). Lần khởi động sau, `activate()` đưa thư mục đó vào
đường dẫn import trước khi nạp torch. Trọng số Chandra vẫn tải riêng từ Hugging Face.
"""
from __future__ import annotations

import contextlib
import importlib
import os
import re
import sys
import threading
import traceback
import urllib.request
from pathlib import Path

CU_INDEX = "https://download.pytorch.org/whl/cu126"
PYPI_INDEX = "https://pypi.org/simple"
CHANDRA_SPEC = "chandra-ocr[hf]==0.2.0"
MARKER = ".installed"
EXPECTED_PACKAGES = 55          # số dòng "Collecting" thường thấy (log cài thật: 54), để ước tiến độ giai đoạn tải
EXPECTED_BYTES = 6 * 2**30      # dung lượng gói sau khi giải nén (torch cu126 + CUDA + transformers), ước lượng


def pack_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".local" / "share")
    return Path(base) / "OCR-Nhat" / "gpu"


def installed() -> bool:
    d = pack_dir()
    return (d / MARKER).is_file() and (d / "torch").is_dir() and (d / "chandra").is_dir()


def activate() -> bool:
    """Đưa gói GPU vào đường dẫn import (gọi trước khi nạp torch hoặc chandra). Trả về có kích hoạt không."""
    if not installed():
        return False
    d = pack_dir()
    if str(d) not in sys.path:
        sys.path.insert(0, str(d))
    if os.name == "nt" and hasattr(os, "add_dll_directory"):
        # DLL của torch và CUDA nằm trong torch/lib và nvidia/*/bin
        for sub in [d / "torch" / "lib", *sorted((d / "nvidia").glob("*/bin"))]:
            if sub.is_dir():
                os.add_dll_directory(str(sub))
    return True


_WHEEL = r"{pkg}-(\d+\.\d+\.\d+)(?:%2B|\+)cu126-cp312-cp312-win_amd64\.whl"


def _latest_cu126(pkg: str, minor_prefix: str | None = None) -> str:
    """Phiên bản cu126 mới nhất có wheel Windows cp312 trên chỉ mục PyTorch (tùy chọn: lọc theo minor)."""
    from pip._vendor.packaging.version import Version

    with urllib.request.urlopen(f"{CU_INDEX}/{pkg}/", timeout=60) as r:
        html = r.read().decode("utf-8", "replace")
    found = {m.group(1) for m in re.finditer(_WHEEL.format(pkg=re.escape(pkg)), html)}
    if minor_prefix:
        found = {v for v in found if v.startswith(minor_prefix)}
    if not found:
        raise RuntimeError(f"Không thấy wheel {pkg} cu126 cho Windows cp312 trên {CU_INDEX}")
    return max(found, key=Version)


def cuda_pins() -> list[str]:
    """Ghim torch và torchvision cu126 khớp nhau: torch 2.X đi với torchvision 0.(X+15)."""
    torch_v = _latest_cu126("torch")
    minor = int(torch_v.split(".")[1])
    tv_v = _latest_cu126("torchvision", minor_prefix=f"0.{minor + 15}.")
    return [f"torch=={torch_v}+cu126", f"torchvision=={tv_v}+cu126"]


def pip_args(pins: list[str], target: Path) -> list[str]:
    return ["install", "--no-input", "--disable-pip-version-check", "--upgrade", "--target", str(target),
            "--index-url", PYPI_INDEX, "--extra-index-url", CU_INDEX, *pins, CHANDRA_SPEC]


class PackError(RuntimeError):
    """Cài gói GPU thất bại. Thông báo gửi cho người dùng; chi tiết kỹ thuật nằm trong install.log."""


PACK_FAILED_MSG = "Không cài được tăng tốc GPU. Phần mềm vẫn chạy bình thường bằng CPU."


def log_file() -> Path:
    return pack_dir() / "install.log"


def _register_frozen_finder() -> None:
    """Trong exe PyInstaller, distlib không nhận loader của PyInstaller nên báo
    "Unable to locate finder for 'pip._vendor.distlib'" khi pip import module cài đặt.
    Đăng ký loader đó dùng ResourceFinder, giống module thường (đường dẫn file đã có trong thư mục exe)."""
    if not getattr(sys, "frozen", False):
        return
    from pip._vendor.distlib import resources

    loader = getattr(importlib.import_module("pip._vendor.distlib"), "__loader__", None)
    if loader is not None and type(loader) not in resources._finder_registry:
        resources.register_finder(loader, resources.ResourceFinder)


def check_pip() -> None:
    """Kiểm tra pip đóng gói sẵn import được module mà lệnh cài dùng. Ném lỗi nếu không.

    Hàm này import đúng module `pip._internal.operations.install.wheel` (nơi lỗi distlib xảy ra)
    để lỗi lộ ra sớm, kể cả trong CI.
    """
    _register_frozen_finder()
    from pip._internal.cli.main import main  # noqa: F401
    from pip._internal.operations.install import wheel  # noqa: F401


def dir_bytes(d: Path) -> int:
    """Tổng dung lượng file trong thư mục (bỏ qua file đang bị khóa hoặc vừa xóa)."""
    total = 0
    for root, _dirs, files in os.walk(d):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(root, name))
            except OSError:
                pass
    return total


class _PipStream:
    """Luồng thay stdout/stderr của pip: ghi vào file log và đọc từng dòng để báo tiến độ.
    pip không in thanh tiến trình khi đầu ra không phải terminal, nên tiến độ lấy từ số dòng "Collecting"
    (giai đoạn tải, 5-40%) rồi từ dung lượng thư mục đích (giai đoạn giải nén, 40-98%)."""

    def __init__(self, f, progress, target: Path):
        self.f, self.progress, self.target = f, progress, target
        self.buf = ""
        self.collected = 0
        self.installing = threading.Event()
        self.done = threading.Event()
        self.poller = threading.Thread(target=self._poll, daemon=True)

    def write(self, text: str) -> int:
        self.f.write(text)
        self.f.flush()   # log đọc được ngay cả khi pip chưa xong
        self.buf += text
        *lines, self.buf = self.buf.split("\n")
        for line in lines:
            self._line(line.strip())
        return len(text)

    def flush(self) -> None:
        self.f.flush()

    def isatty(self) -> bool:
        return False

    def _line(self, line: str) -> None:
        if line.startswith("Collecting "):
            self.collected += 1
            frac = 0.05 + 0.35 * min(1.0, self.collected / EXPECTED_PACKAGES)
            self.progress(f"Đang tải gói {self.collected}: {line[11:].split(' ')[0]}", frac)
        elif line.startswith("Downloading "):
            self.progress("Đang tải " + line[12:].split(" ")[0] + " " + line.split(" ", 2)[-1][:20], -2)
        elif line.startswith("Installing collected packages") and not self.installing.is_set():
            self.installing.set()
            self.poller.start()

    def _poll(self) -> None:
        base = dir_bytes(self.target)
        while not self.done.wait(1.5):
            frac = min(1.0, max(0, dir_bytes(self.target) - base) / EXPECTED_BYTES)
            self.progress("Đang giải nén và cài đặt (torch lớn, vài phút)…", 0.40 + 0.58 * frac)

    def close(self) -> None:
        self.done.set()


def install(progress=lambda text, frac=-1: print(text)) -> None:
    """Cài gói GPU bằng pip trong cùng tiến trình (pip đóng gói sẵn trong exe). Ném PackError nếu thất bại.
    progress(chữ, tỷ lệ 0..1; -1 = không xác định; -2 = chỉ đổi chữ, giữ tỷ lệ cũ)."""
    d = pack_dir()
    d.mkdir(parents=True, exist_ok=True)
    marker = d / MARKER
    marker.unlink(missing_ok=True)   # cài dở thì không được tính là đã cài (installed() cần MARKER)
    failed = False
    # bản --windowed có sys.stdout/stderr = None: pip ghi log vào đó và thoát mã 2. Mọi đầu ra vào file log.
    with open(log_file(), "w", encoding="utf-8") as f:
        stream = _PipStream(f, progress, d)
        with contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
            try:
                check_pip()
                from pip._internal.cli.main import main as pip_main

                progress("Đang chọn phiên bản torch CUDA…", 0.02)
                pins = cuda_pins()
                progress(f"Đang tải {', '.join(pins)} và Chandra (có thể mất nhiều phút)…", 0.05)
                code = pip_main(pip_args(pins, d))
                if code != 0:
                    raise RuntimeError(f"pip thoát với mã {code}")
                marker.write_text("\n".join(pins), encoding="utf-8")
                print("Hoàn tất: gói GPU đã cài xong.")
            except BaseException:   # pip có thể gọi sys.exit; không bắt thì luồng nền chết im lặng, GUI kẹt ở "Đang tải"
                traceback.print_exc()
                failed = True
            finally:
                stream.close()
    if failed:
        raise PackError(PACK_FAILED_MSG)
    progress("Đã cài xong.", 1.0)
    activate()
