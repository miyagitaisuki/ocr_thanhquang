"""Gói GPU tải theo yêu cầu: onnxruntime-gpu + CUDA/cuDNN (wheel PyPI, ghim trong gpu_manifest.py).

- Cài vào %LOCALAPPDATA%\\OCR-Nhat\\gpu\\site (khoảng 1,3 GB tải về). Nút "Bật GPU" trong GUI gọi `install()`.
- Exe đóng gói onnxruntime CPU nên không nạp chung hai bản trong một tiến trình. Vì vậy OCR GPU chạy
  trong tiến trình con (`gpu_worker`) với sys.path trỏ vào gói GPU; hai bên trao đổi JSON qua stdin/stdout.
- Lỗi ở bất kỳ bước nào thì `remote_engine_for()` trả None và pipeline lùi về CPU.
"""
from __future__ import annotations

import atexit
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import zipfile
from pathlib import Path

import numpy as np

from . import gpu_manifest as M
from .appdir import app_dir
from .engines import models as mdl
from .engines.base import OcrEngine
from .model import Page, page_from_dict

log = logging.getLogger(__name__)
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def base_dir() -> Path:
    return app_dir() / "gpu"


def site_dir(base: Path | None = None) -> Path:
    return (base or base_dir()) / "site"


def _marker(base: Path | None = None) -> Path:
    return (base or base_dir()) / "installed.json"


def supported() -> tuple[bool, str]:
    """Gói GPU của bản này chỉ đóng cho Windows x64 Python 3.12 (khớp exe)."""
    if sys.platform != "win32":
        return False, "gói GPU chỉ có cho Windows"
    if sys.version_info[:2] != (3, 12):
        return False, f"gói GPU cần Python 3.12 (đang {sys.version_info[0]}.{sys.version_info[1]})"
    return True, ""


def installed(base: Path | None = None) -> bool:
    try:
        info = json.loads(_marker(base).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return info.get("version") == M.PACK_VERSION and site_dir(base).is_dir()


def nvidia_present() -> bool:
    from . import gpu
    return bool(gpu.detect())


def _safe_extract(zf: zipfile.ZipFile, dest: Path) -> None:
    root = dest.resolve()
    for m in zf.infolist():
        target = (root / m.filename).resolve()
        if root != target and root not in target.parents:
            raise RuntimeError(f"đường dẫn lạ trong gói: {m.filename}")
    zf.extractall(root)


def install(progress=None, wheels=None, base: Path | None = None, check: bool = True) -> str:
    """Tải, kiểm SHA-256, giải nén gói GPU. progress(chữ, tỷ lệ 0..1; -1 = không rõ).

    `wheels`/`base` để test. `check=True`: sau khi cài, thử nạp CUDA trong tiến trình con và báo kết quả.
    """
    wheels = M.WHEELS if wheels is None else wheels
    base = base or base_dir()
    base.mkdir(parents=True, exist_ok=True)
    wdir = base / "wheels"
    files = {name: (url, sha) for name, url, sha, _size in wheels}
    n = len(files)

    def rep(i, total, name, frac):
        if progress:
            progress(f"Đang tải {name} ({min(i + 1, total)}/{total})", (i + frac) / total)

    mdl.download_files(files, progress=rep, dest=wdir)
    if progress:
        progress("Đang giải nén gói GPU…", -1)
    staged = base / "site.new"
    shutil.rmtree(staged, ignore_errors=True)
    staged.mkdir()
    for name in files:
        with zipfile.ZipFile(wdir / name) as zf:
            _safe_extract(zf, staged)
    shutil.rmtree(site_dir(base), ignore_errors=True)
    staged.replace(site_dir(base))
    shutil.rmtree(wdir, ignore_errors=True)   # wheel đã giải nén, bỏ để tiết kiệm đĩa
    _marker(base).write_text(json.dumps({"version": M.PACK_VERSION, "wheels": n}), encoding="utf-8")
    msg = f"Đã cài gói GPU ({n} thành phần)."
    if check:
        ok, providers = probe(base)
        msg += (" CUDA sẵn sàng." if ok else
                " Nhưng chưa nạp được CUDA: kiểm driver NVIDIA (cần bản đủ mới cho CUDA 13). Đang dùng CPU.")
    return msg


def remove(base: Path | None = None) -> None:
    shutil.rmtree(base or base_dir(), ignore_errors=True)


def _worker_cmd() -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, "--gpu-worker"]
    return [sys.executable, "-m", "ocrnhat.gpu_worker"]


class _Worker:
    """Một tiến trình con. Giao thức: mỗi dòng stdin là JSON yêu cầu, mỗi dòng stdout là JSON trả lời."""

    def __init__(self, site: Path):
        env = dict(os.environ, OCRNHAT_GPU_SITE=str(site), PYTHONIOENCODING="utf-8")
        logdir = app_dir() / "logs"
        logdir.mkdir(parents=True, exist_ok=True)
        self.err = open(logdir / "gpu_worker.log", "a", encoding="utf-8", errors="replace")
        self.proc = subprocess.Popen(_worker_cmd(), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=self.err, env=env, text=True, encoding="utf-8", bufsize=1,
                                     creationflags=_NO_WINDOW)

    def call(self, req: dict) -> dict:
        if self.proc.poll() is not None:
            raise RuntimeError("tiến trình GPU đã dừng (xem logs/gpu_worker.log)")
        self.proc.stdin.write(json.dumps(req, ensure_ascii=False, default=float) + "\n")
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        if not line:
            raise RuntimeError("tiến trình GPU không trả lời (xem logs/gpu_worker.log)")
        resp = json.loads(line)
        if not resp.get("ok"):
            raise RuntimeError(resp.get("error", "lỗi GPU không rõ"))
        return resp

    def close(self) -> None:
        try:
            if self.proc.poll() is None:
                self.proc.stdin.close()
                self.proc.wait(timeout=10)
        except Exception:
            self.proc.kill()
        finally:
            self.err.close()


def probe(base: Path | None = None) -> tuple[bool, list[str]]:
    """Mở một tiến trình con, hỏi danh sách provider. (CUDA nạp được?, providers)."""
    try:
        w = _Worker(site_dir(base))
    except Exception as e:
        log.warning("Không mở được tiến trình GPU: %s", e)
        return False, []
    try:
        providers = w.call({"op": "ping"}).get("providers", [])
        return "CUDAExecutionProvider" in providers, providers
    except Exception as e:
        log.warning("Dò GPU lỗi: %s", e)
        return False, []
    finally:
        w.close()


class RemoteEngine(OcrEngine):
    """Engine chạy trong tiến trình con GPU. Giao diện giống OcrEngine nên pipeline dùng như engine thường."""

    needs_gpu = True

    def __init__(self, engine: str, base: Path | None = None, require_cuda: bool = True):
        self.engine = engine
        self.name = engine
        self._lock = threading.Lock()
        self._w = _Worker(site_dir(base))
        try:
            self.providers = self._w.call({"op": "ping"}).get("providers", [])
            if require_cuda and "CUDAExecutionProvider" not in self.providers:
                raise RuntimeError("onnxruntime trong gói GPU không nạp được CUDA")
        except Exception:
            self._w.close()
            raise

    def ocr(self, img_rgb: np.ndarray, name: str = "page.png") -> Page:
        with self._lock:   # một tiến trình con, các luồng OCR xếp hàng
            fd, path = tempfile.mkstemp(suffix=".npy")
            os.close(fd)
            try:
                np.save(path, img_rgb)
                resp = self._w.call({"op": "ocr", "engine": self.engine, "npy": path, "name": name})
            finally:
                os.unlink(path)
        return page_from_dict(resp["page"])

    def close(self) -> None:
        self._w.close()


_remote: dict[str, RemoteEngine | None] = {}
_remote_lock = threading.Lock()


def remote_engine_for(name: str) -> RemoteEngine | None:
    """Engine GPU dùng chung cho cả tiến trình (một tiến trình con cho mỗi engine). None nếu không dùng được."""
    if not installed():
        return None
    ok, why = supported()
    if not ok:
        return None
    with _remote_lock:
        if name not in _remote:
            try:
                _remote[name] = RemoteEngine(name)
            except Exception as e:
                log.warning("Không bật được GPU cho %s: %s", name, e)
                _remote[name] = None   # ghi nhận lỗi để không mở tiến trình lại ở mỗi luồng
        return _remote[name]


@atexit.register
def _close_all() -> None:
    for eng in list(_remote.values()):
        if eng is not None:
            eng.close()
