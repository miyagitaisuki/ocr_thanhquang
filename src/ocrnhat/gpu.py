"""Phát hiện card NVIDIA (nvidia-smi) và chọn thiết bị chạy NDLOCR: cpu hoặc cuda.

Chủ dự án chốt chỉ hỗ trợ NVIDIA; AMD/Intel bị bỏ qua. Chạy GPU cần onnxruntime-gpu + CUDA/cuDNN trên máy.
"""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass

MIN_VRAM_MB = 6000   # Chandra ~4-5B: cỡ 6 GB khi lượng tử 8-bit (ước lượng từ nguồn ngoài, chưa tự đo)


@dataclass
class Gpu:
    name: str
    vram_mb: int | None
    backend: str = "cuda"

    def usable_for_vlm(self, min_vram_mb: int = MIN_VRAM_MB) -> bool:
        return self.vram_mb is not None and self.vram_mb >= min_vram_mb


def detect() -> list[Gpu]:
    exe = shutil.which("nvidia-smi")
    if not exe:
        return []
    try:
        r = subprocess.run([exe, "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                           capture_output=True, text=True, timeout=8,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception:
        return []
    gpus = []
    for line in (r.stdout if r.returncode == 0 else "").splitlines():
        name, _, mem = line.partition(",")
        if name.strip():
            gpus.append(Gpu(name.strip(), int(mem) if mem.strip().isdigit() else None))
    return gpus


def best_gpu(gpus: list[Gpu] | None = None) -> Gpu | None:
    ok = [g for g in (detect() if gpus is None else gpus) if g.usable_for_vlm()]
    return max(ok, key=lambda g: g.vram_mb or 0) if ok else None


DEVICES = ("auto", "cpu", "cuda")


def ort_cuda_available() -> bool:
    """onnxruntime đang cài có CUDAExecutionProvider không (bản CPU thì không)."""
    try:
        import onnxruntime
        return "CUDAExecutionProvider" in onnxruntime.get_available_providers()
    except Exception:
        return False


def resolve_device(pref: str = "auto") -> tuple[str, str]:
    """'auto'|'cpu'|'cuda' -> ('cpu'|'cuda', lý do). Yêu cầu cuda mà không dùng được thì lùi về cpu và nói rõ."""
    if pref == "cpu":
        return "cpu", "chọn CPU"
    ort_ok = ort_cuda_available()
    if pref == "cuda":
        if ort_ok:
            return "cuda", "chọn GPU"
        return "cpu", "đã chọn GPU nhưng onnxruntime không có CUDA (cần onnxruntime-gpu + CUDA/cuDNN); dùng CPU"
    gpus = detect()
    if gpus and ort_ok:
        return "cuda", f"tự động: {gpus[0].name}"
    return "cpu", "tự động: " + ("có NVIDIA nhưng onnxruntime không có CUDA" if gpus else "không thấy GPU NVIDIA")
