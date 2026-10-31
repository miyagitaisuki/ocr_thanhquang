"""Phát hiện card NVIDIA (nvidia-smi) và chọn thiết bị chạy NDLOCR: cpu hoặc cuda.

Chủ dự án chốt chỉ hỗ trợ NVIDIA; AMD/Intel bị bỏ qua. Chạy GPU cần onnxruntime-gpu + CUDA/cuDNN trên máy.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass


@dataclass
class Gpu:
    name: str
    vram_mb: int | None
    backend: str = "cuda"
    driver: tuple[int, ...] | None = None   # phiên bản driver NVIDIA, ví dụ (581, 57)
    cc: tuple[int, ...] | None = None       # compute capability, ví dụ (8, 6)


def _nvidia_smi() -> str | None:
    """Đường dẫn nvidia-smi. Driver mới đặt ở System32 (có trong PATH); driver cũ chỉ ở thư mục NVSMI."""
    exe = shutil.which("nvidia-smi")
    if exe:
        return exe
    for base in (os.environ.get("ProgramFiles"), os.environ.get("SystemRoot")):
        for sub in ("NVIDIA Corporation/NVSMI", "System32"):
            cand = os.path.join(base or "", sub, "nvidia-smi.exe")
            if base and os.path.isfile(cand):
                return cand
    return None


# Thử từ đầy đủ đến tối thiểu: driver cũ có thể không hỗ trợ compute_cap.
_QUERIES = ("name,memory.total,driver_version,compute_cap", "name,memory.total,driver_version", "name,memory.total")


def parse_version(text: str) -> tuple[int, ...] | None:
    """'581.57' -> (581, 57); '8.6' -> (8, 6). Chuỗi không hợp lệ -> None."""
    parts = (text or "").strip().split(".")
    if not parts or not all(p.isdigit() for p in parts):
        return None
    return tuple(int(p) for p in parts)


def _parse_rows(out: str, fields: list[str]) -> list[Gpu]:
    gpus = []
    for line in out.splitlines():
        vals = [v.strip() for v in line.rsplit(",", len(fields) - 1)]
        if len(vals) != len(fields) or not vals[0]:
            continue
        row = dict(zip(fields, vals))
        mem = row.get("memory.total", "")
        gpus.append(Gpu(
            row["name"], int(mem) if mem.isdigit() else None,
            driver=parse_version(row.get("driver_version", "")),
            cc=parse_version(row.get("compute_cap", ""))))
    return gpus


def detect() -> list[Gpu]:
    exe = _nvidia_smi()
    if not exe:
        return []
    for q in _QUERIES:
        try:
            r = subprocess.run([exe, f"--query-gpu={q}", "--format=csv,noheader,nounits"],
                               capture_output=True, text=True, timeout=8,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except Exception:
            return []
        if r.returncode == 0 and r.stdout.strip():
            return _parse_rows(r.stdout, q.split(","))
    return []


DEVICES = ("auto", "cpu", "cuda")


def ensure_ort_cuda_libs() -> None:
    """Nạp thư viện CUDA/cuDNN (gói nvidia-* pip) cho onnxruntime-gpu. Phải gọi trước khi tạo InferenceSession.

    Không làm vậy thì CUDAExecutionProvider vẫn có trong danh sách nhưng không nạp được
    (thiếu libcublasLt.so.13) và ONNX Runtime lặng lẽ chạy trên CPU.
    """
    try:
        import onnxruntime
        if hasattr(onnxruntime, "preload_dlls"):
            onnxruntime.preload_dlls()
    except Exception:
        pass


def ort_cuda_available() -> bool:
    """onnxruntime-gpu nạp được CUDA thật (không chỉ có tên trong danh sách provider)."""
    try:
        import onnxruntime
    except Exception:
        return False
    ensure_ort_cuda_libs()
    return "CUDAExecutionProvider" in onnxruntime.get_available_providers()


def gpu_selectable() -> bool:
    """Ô Phần cứng có mục GPU không: có card NVIDIA hoặc onnxruntime có CUDA."""
    return ort_cuda_available() or bool(detect())


def pack_ready() -> bool:
    """Gói GPU tải theo yêu cầu (nút "Bật GPU") đã cài. Xem gpu_pack.py."""
    try:
        from .gpu_pack import installed
        return installed()
    except Exception:
        return False


def resolve_device(pref: str = "auto") -> tuple[str, str]:
    """'auto'|'cpu'|'cuda' -> ('cpu'|'cuda', lý do). "cuda" dùng được khi onnxruntime có CUDA sẵn hoặc đã cài gói GPU."""
    if pref == "cpu":
        return "cpu", "chọn CPU"
    ort_ok = ort_cuda_available()
    pack = (not ort_ok) and pack_ready()
    if pref == "cuda":
        if ort_ok:
            return "cuda", "chọn GPU"
        if pack:
            return "cuda", "chọn GPU (gói GPU đã cài)"
        return "cpu", "đã chọn GPU nhưng onnxruntime chưa có CUDA: bấm \"Bật GPU\" để tải gói CUDA; dùng CPU"
    gpus = detect()
    if gpus and (ort_ok or pack):
        return "cuda", f"tự động: {gpus[0].name}" + ("" if ort_ok else " (gói GPU)")
    return "cpu", "tự động: " + ("có NVIDIA nhưng onnxruntime không có CUDA" if gpus else "không thấy GPU NVIDIA")
