"""Phát hiện card NVIDIA (nvidia-smi) và chọn thiết bị chạy NDLOCR: cpu hoặc cuda.

Chủ dự án chốt chỉ hỗ trợ NVIDIA; AMD/Intel bị bỏ qua. Chạy GPU cần onnxruntime-gpu + CUDA/cuDNN trên máy.
"""
from __future__ import annotations

import os
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


def detect() -> list[Gpu]:
    exe = _nvidia_smi()
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


def gpu_selectable() -> bool:
    """Ô Phần cứng có mục GPU không: có card NVIDIA (Chandra dùng qua torch) hoặc onnxruntime có CUDA (NDLOCR).
    Trước đây chỉ xét onnxruntime nên exe CPU không bao giờ cho chọn GPU dù máy có RTX."""
    return ort_cuda_available() or bool(detect())


def torch_cuda_available() -> bool:
    """torch đang cài (gói GPU) có CUDA không. Không import torch nếu chưa có."""
    try:
        import torch
        return bool(torch.cuda.is_available())
    except Exception:
        return False


def resolve_device(pref: str = "auto", engine: str = "ndlocr") -> tuple[str, str]:
    """'auto'|'cpu'|'cuda' -> ('cpu'|'cuda', lý do). Yêu cầu cuda mà không dùng được thì lùi về cpu và nói rõ.
    Chandra chạy bằng torch nên xét CUDA của torch; các engine ONNX xét CUDA của onnxruntime.
    (Trước đây mọi engine xét onnxruntime: exe CPU luôn ra 'cpu' và ép Chandra chạy CPU dù có RTX.)"""
    if pref == "cpu":
        return "cpu", "chọn CPU"
    if engine == "chandra":
        if torch_cuda_available():
            return "cuda", "chọn GPU" if pref == "cuda" else "tự động: torch có CUDA"
        return "cpu", "torch không có CUDA (chưa cài gói GPU hoặc cần khởi động lại sau khi cài)"
    ort_ok = ort_cuda_available()
    if pref == "cuda":
        if ort_ok:
            return "cuda", "chọn GPU"
        return "cpu", "đã chọn GPU nhưng onnxruntime không có CUDA (cần onnxruntime-gpu + CUDA/cuDNN); dùng CPU"
    gpus = detect()
    if gpus and ort_ok:
        return "cuda", f"tự động: {gpus[0].name}"
    return "cpu", "tự động: " + ("có NVIDIA nhưng onnxruntime không có CUDA" if gpus else "không thấy GPU NVIDIA")
