"""Tiến trình con chạy OCR bằng GPU (xem gpu_pack.py). Không mở giao diện.

Chạy: `OCRNHAT_GPU_SITE=<thư mục gói> python -m ocrnhat.gpu_worker`, hoặc exe với tham số `--gpu-worker`.
Giao thức: đọc mỗi dòng stdin một JSON yêu cầu, ghi mỗi dòng stdout một JSON trả lời.
  {"op": "ping"}                                   -> {"ok": true, "providers": [...]}
  {"op": "ocr", "engine": "ndlocr", "npy": path}   -> {"ok": true, "page": {...}}
Log và in của engine đi vào stderr để không làm hỏng giao thức.
"""
from __future__ import annotations

import glob
import json
import os
import sys
import traceback
from dataclasses import asdict


def _setup_path() -> None:
    site = os.environ.get("OCRNHAT_GPU_SITE")
    if not site or not os.path.isdir(site):
        return
    if site not in sys.path:
        sys.path.insert(0, site)   # gói GPU đứng trước mọi onnxruntime khác
    if hasattr(os, "add_dll_directory"):
        # DLL CUDA/cuDNN nằm trong các thư mục nvidia/**/bin và onnxruntime/capi
        dirs = {os.path.dirname(p) for p in glob.glob(os.path.join(site, "**", "*.dll"), recursive=True)}
        for d in sorted(dirs):
            try:
                os.add_dll_directory(d)
            except OSError:
                pass


_engines: dict = {}


def _default_factory(name: str):
    from .engines import create
    return create(name, device="cuda")


def handle(req: dict, factory=None) -> dict:
    op = req.get("op")
    if op == "ping":
        import onnxruntime as ort
        if hasattr(ort, "preload_dlls"):
            ort.preload_dlls()
        return {"ok": True, "providers": ort.get_available_providers(), "ort": ort.__version__}
    if op == "ocr":
        import numpy as np
        name = req["engine"]
        if name not in _engines:
            _engines[name] = (factory or _default_factory)(name)
        img = np.load(req["npy"])
        page = _engines[name].ocr(img, req.get("name", "page.png"))
        return {"ok": True, "page": asdict(page)}
    return {"ok": False, "error": f"yêu cầu lạ: {op!r}"}


def main(factory=None) -> int:
    _setup_path()
    for st in (sys.stdin, sys.stdout):
        st.reconfigure(encoding="utf-8")
    proto = sys.stdout
    sys.stdout = sys.stderr    # print của engine không lẫn vào giao thức
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            resp = handle(json.loads(line), factory)
        except Exception as e:   # mọi lỗi trả về bên gọi, tiến trình vẫn sống cho yêu cầu sau
            traceback.print_exc()
            resp = {"ok": False, "error": f"{type(e).__name__}: {e}"}
        proto.write(json.dumps(resp, ensure_ascii=False, default=float) + "\n")
        proto.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
