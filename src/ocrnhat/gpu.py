"""Phát hiện card đồ họa rời (NVIDIA/AMD) để quyết định có dùng engine VLM (Chandra) hay không."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass

MIN_VRAM_MB = 6000   # Chandra ~4-5B: cỡ 6 GB khi lượng tử 8-bit (ước lượng từ nguồn ngoài, chưa tự đo)


@dataclass
class Gpu:
    name: str
    vendor: str              # nvidia | amd | intel | other
    vram_mb: int | None      # None = không biết
    discrete: bool
    backend: str             # cuda | rocm | directml | none

    def usable_for_vlm(self, min_vram_mb: int = MIN_VRAM_MB) -> bool:
        # VRAM không rõ thì không tự chọn (người dùng vẫn ép được bằng --engine chandra)
        return self.discrete and self.vram_mb is not None and self.vram_mb >= min_vram_mb


def _run(cmd: list[str], timeout: float = 8) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return r.stdout if r.returncode == 0 else ""
    except Exception:
        return ""


def _vendor(name: str) -> str:
    n = name.lower()
    if "nvidia" in n or "geforce" in n or "quadro" in n or "rtx" in n:
        return "nvidia"
    if "amd" in n or "radeon" in n or "advanced micro" in n:
        return "amd"
    if "intel" in n:
        return "intel"
    return "other"


def _backend(vendor: str) -> str:
    if vendor == "nvidia":
        return "cuda"
    if vendor == "amd":
        return "directml" if sys.platform == "win32" else "rocm"
    return "none"


def _nvidia() -> list[Gpu]:
    exe = shutil.which("nvidia-smi")
    if not exe:
        return []
    out = _run([exe, "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"])
    gpus = []
    for line in out.splitlines():
        name, _, mem = line.partition(",")
        if name.strip():
            gpus.append(Gpu(name.strip(), "nvidia", int(mem) if mem.strip().isdigit() else None, True, "cuda"))
    return gpus


def _amd_vram_linux() -> int | None:
    exe = shutil.which("rocm-smi")
    out = _run([exe, "--showmeminfo", "vram", "--json"]) if exe else ""
    try:
        for card in json.loads(out).values():
            for k, v in card.items():
                if "Total" in k and str(v).isdigit():
                    return int(v) // (1024 * 1024)
    except Exception:
        pass
    return None


def _windows_adapters() -> list[Gpu]:
    # AdapterRAM của WMI bị cắt ở 4 GB nên VRAM AMD để None nếu không có nguồn chính xác hơn
    out = _run(["powershell", "-NoProfile", "-Command",
                "Get-CimInstance Win32_VideoController | Select-Object Name | ConvertTo-Json"])
    try:
        data = json.loads(out)
    except Exception:
        return []
    names = [d["Name"] for d in (data if isinstance(data, list) else [data]) if d.get("Name")]
    return [Gpu(n, _vendor(n), None, _vendor(n) in ("nvidia", "amd") and not re.search(r"graphics$", n, re.I), _backend(_vendor(n)))
            for n in names]


def _linux_adapters() -> list[Gpu]:
    out = _run(["lspci"]) if shutil.which("lspci") else ""
    gpus = []
    for line in out.splitlines():
        if re.search(r"VGA|3D controller|Display controller", line):
            name = line.split(": ", 1)[-1]
            v = _vendor(name)
            gpus.append(Gpu(name, v, _amd_vram_linux() if v == "amd" else None, v in ("nvidia", "amd"), _backend(v)))
    return gpus


def detect() -> list[Gpu]:
    """Danh sách GPU; thông tin VRAM chính xác từ nvidia-smi (NVIDIA) hoặc rocm-smi (AMD/Linux)."""
    found = _nvidia()
    others = _windows_adapters() if sys.platform == "win32" else _linux_adapters()
    for g in others:
        if g.vendor == "nvidia" and found:
            continue   # đã có số liệu từ nvidia-smi
        found.append(g)
    return found


def best_gpu(gpus: list[Gpu] | None = None) -> Gpu | None:
    gpus = detect() if gpus is None else gpus
    ok = [g for g in gpus if g.usable_for_vlm()]
    return max(ok, key=lambda g: g.vram_mb or 0) if ok else None
