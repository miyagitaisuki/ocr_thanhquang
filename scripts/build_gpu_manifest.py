#!/usr/bin/env python3
"""Sinh src/ocrnhat/gpu_manifest.py: danh sách wheel ghim cho gói GPU (onnxruntime-gpu + CUDA/cuDNN, Windows x64).

Dữ liệu (URL, SHA-256, dung lượng) lấy từ JSON API của PyPI tại thời điểm chạy; phiên bản thì ghim ở PINS.
Đổi phiên bản: sửa PINS, chạy lại script, commit cả gpu_manifest.py.

    python scripts/build_gpu_manifest.py
"""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path

PACK_VERSION = "2026.10-cu13"   # đổi khi đổi PINS; app so với installed.json để biết có cần cài lại không
PYTHON_TAG = "cp312"            # phải khớp Python của exe (build-exe*.yml dùng 3.12)

# (tên PyPI, phiên bản, mẫu tên wheel cần lấy)
PINS = [
    ("onnxruntime-gpu", "1.31.1", f"-{PYTHON_TAG}-{PYTHON_TAG}-win_amd64.whl"),
    ("nvidia-cuda-nvrtc", "13.4.92", "-py3-none-win_amd64.whl"),
    ("nvidia-cuda-runtime", "13.4.92", "-py3-none-win_amd64.whl"),
    ("nvidia-cufft", "12.4.0.43", "-py3-none-win_amd64.whl"),
    ("nvidia-curand", "10.4.4.72", "-py3-none-win_amd64.whl"),
    ("nvidia-cublas", "13.8.0.4", "-py3-none-win_amd64.whl"),
    ("nvidia-cudnn-cu13", "9.27.0.42", "-py3-none-win_amd64.whl"),
]

OUT = Path(__file__).resolve().parents[1] / "src" / "ocrnhat" / "gpu_manifest.py"


def fetch_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.load(r)


def main() -> None:
    rows = []
    for name, ver, suffix in PINS:
        data = fetch_json(f"https://pypi.org/pypi/{name}/{ver}/json")
        files = [f for f in data["urls"] if f["filename"].endswith(suffix)]
        if len(files) != 1:
            raise SystemExit(f"{name} {ver}: cần đúng 1 wheel đuôi {suffix}, thấy {len(files)}")
        f = files[0]
        rows.append((f["filename"], f["url"], f["digests"]["sha256"], f["size"]))
        print(f"{f['filename']}  {f['size'] / 1e6:.1f} MB")
    total = sum(r[3] for r in rows)
    lines = [
        '"""SINH TỰ ĐỘNG bởi scripts/build_gpu_manifest.py. Không sửa tay."""',
        f'PACK_VERSION = "{PACK_VERSION}"',
        f'PYTHON_TAG = "{PYTHON_TAG}"',
        f"TOTAL_BYTES = {total}",
        "# (tên file wheel, URL, SHA-256, dung lượng byte)",
        "WHEELS = [",
    ]
    lines += [f"    ({n!r}, {u!r}, {s!r}, {z})," for n, u, s, z in rows]
    lines.append("]")
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"-> {OUT} (tổng {total / 1e9:.2f} GB)")


if __name__ == "__main__":
    main()
