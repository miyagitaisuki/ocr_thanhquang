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

PYTHON_TAG = "cp312"            # phải khớp Python của exe (build-exe*.yml dùng 3.12)

# Mỗi gói: bản CUDA, driver NVIDIA tối thiểu (Windows, dạng "major.minor"), compute capability tối thiểu,
# và các wheel ghim (tên PyPI, phiên bản, đuôi tên wheel).
# min_driver/min_cc là GIẢ ĐỊNH cần kiểm trên máy thật, xem readme.md mục "Gói GPU":
#   cu12: 576.02 = driver GA Windows của CUDA 12.9 (CUDA 12.9 release notes); 7.5 = sm_75 có trong build ORT CUDA 12.8.
#   cu13: 580 = mức sàn họ 13.x (CUDA 13.x release notes, chưa có số riêng cho Windows); 7.5 chưa kiểm.
PACKS = {
    "cu13": {
        "label": "CUDA 13",
        "min_driver": (580, 0),
        "min_cc": (7, 5),
        "pins": [
            ("onnxruntime-gpu", "1.31.1", "-cp312-cp312-win_amd64.whl"),
            ("nvidia-cuda-nvrtc", "13.4.92", "-py3-none-win_amd64.whl"),
            ("nvidia-cuda-runtime", "13.4.92", "-py3-none-win_amd64.whl"),
            ("nvidia-cufft", "12.4.0.43", "-py3-none-win_amd64.whl"),
            ("nvidia-curand", "10.4.4.72", "-py3-none-win_amd64.whl"),
            ("nvidia-cublas", "13.8.0.4", "-py3-none-win_amd64.whl"),
            ("nvidia-cudnn-cu13", "9.27.0.42", "-py3-none-win_amd64.whl"),
        ],
    },
    "cu12": {
        "label": "CUDA 12",
        "min_driver": (576, 2),
        "min_cc": (7, 5),
        "pins": [
            ("onnxruntime-gpu", "1.22.0", "-cp312-cp312-win_amd64.whl"),
            ("nvidia-cuda-nvrtc-cu12", "12.9.86", "-py3-none-win_amd64.whl"),
            ("nvidia-cuda-runtime-cu12", "12.9.79", "-py3-none-win_amd64.whl"),
            ("nvidia-cufft-cu12", "11.4.1.4", "-py3-none-win_amd64.whl"),
            ("nvidia-curand-cu12", "10.3.10.19", "-py3-none-win_amd64.whl"),
            ("nvidia-cublas-cu12", "12.9.2.10", "-py3-none-win_amd64.whl"),
            ("nvidia-cudnn-cu12", "9.27.0.42", "-py3-none-win_amd64.whl"),
        ],
    },
}

OUT = Path(__file__).resolve().parents[1] / "src" / "ocrnhat" / "gpu_manifest.py"


def fetch_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.load(r)


def main() -> None:
    out = [
        '"""SINH TỰ ĐỘNG bởi scripts/build_gpu_manifest.py. Không sửa tay."""',
        f'PYTHON_TAG = "{PYTHON_TAG}"',
        "# Gói GPU tải theo yêu cầu. Chọn gói theo driver/compute capability: gpu_pack.select_pack().",
        "PACKS = {",
    ]
    for pid, pk in PACKS.items():
        rows = []
        for name, ver, suffix in pk["pins"]:
            data = fetch_json(f"https://pypi.org/pypi/{name}/{ver}/json")
            files = [f for f in data["urls"] if f["filename"].endswith(suffix)]
            if len(files) != 1:
                raise SystemExit(f"{name} {ver}: cần đúng 1 wheel đuôi {suffix}, thấy {len(files)}")
            f = files[0]
            rows.append((f["filename"], f["url"], f["digests"]["sha256"], f["size"]))
            print(f"[{pid}] {f['filename']}  {f['size'] / 1e6:.1f} MB")
        total = sum(r[3] for r in rows)
        print(f"[{pid}] tổng {total / 1e9:.2f} GB")
        out += [
            f'    "{pid}": {{',
            f'        "label": {pk["label"]!r},',
            f'        "min_driver": {pk["min_driver"]!r},',
            f'        "min_cc": {pk["min_cc"]!r},',
            f'        "total_bytes": {total},',
            '        "wheels": [   # (tên file, URL, SHA-256, byte)',
        ]
        out += [f"            ({n!r}, {u!r}, {h!r}, {z})," for n, u, h, z in rows]
        out += ["        ],", "    },"]
    out.append("}")
    OUT.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"-> {OUT}")


if __name__ == "__main__":
    main()
