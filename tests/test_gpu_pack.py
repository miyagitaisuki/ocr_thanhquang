"""Gói GPU tải theo yêu cầu: cài từ wheel cục bộ, kiểm SHA, chặn đường dẫn lạ, giao thức tiến trình con.

Không cần GPU hay CUDA: CUDA thật chỉ kiểm được trên máy Windows có card NVIDIA.
"""
import hashlib
import json
import subprocess
import sys
import zipfile
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pytest

from ocrnhat import gpu_pack, gpu_worker
from ocrnhat.model import Block, Line, Page, page_from_dict, page_to_dict


def _wheel(path: Path, members: dict[str, bytes]) -> tuple[str, str, str, int]:
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    return path.name, path.as_uri(), sha, path.stat().st_size


def _wheels(tmp: Path, extra: dict | None = None):
    src = tmp / "src"
    src.mkdir()
    a = _wheel(src / "onnxruntime_gpu-1.0-py3-none-any.whl",
               {"onnxruntime/__init__.py": b"x = 1\n", "onnxruntime/capi/a.dll": b"MZ"})
    b = _wheel(src / "nvidia_cudnn-1.0-py3-none-any.whl", {"nvidia/cudnn/bin/c.dll": b"MZ"})
    return [a, b] + (extra or [])


def test_cai_tu_wheel_cuc_bo(tmp_path):
    seen = []
    msg = gpu_pack.install(progress=lambda t, f: seen.append((t, f)), wheels=_wheels(tmp_path),
                           base=tmp_path / "gpu", pack="cu12", check=False)
    assert "Đã cài" in msg
    assert gpu_pack.installed(tmp_path / "gpu")
    site = gpu_pack.site_dir(tmp_path / "gpu")
    assert (site / "onnxruntime" / "__init__.py").read_text() == "x = 1\n"
    assert (site / "nvidia" / "cudnn" / "bin" / "c.dll").is_file()
    assert not (tmp_path / "gpu" / "wheels").exists()          # wheel đã giải nén thì bỏ
    assert any(f == pytest.approx(1.0) for _, f in seen)   # tiến trình báo đủ 100%


def test_sai_sha_thi_khong_cai(tmp_path):
    w = _wheels(tmp_path)
    bad = (w[0][0], w[0][1], "0" * 64, w[0][3])
    with pytest.raises(RuntimeError, match="SHA-256"):
        gpu_pack.install(wheels=[bad, w[1]], base=tmp_path / "gpu", pack="cu12", check=False)
    assert not gpu_pack.installed(tmp_path / "gpu")


def test_duong_dan_lạ_bi_chan(tmp_path):
    evil = _wheel(tmp_path / "evil.whl", {"../../escape.txt": b"no"})
    base = tmp_path / "gpu"
    with pytest.raises(RuntimeError, match="đường dẫn lạ"):
        gpu_pack.install(wheels=[evil], base=base, pack="cu12", check=False)
    assert not (tmp_path / "escape.txt").exists()
    assert not (base / "escape.txt").exists()


def test_marker_sai_phien_ban_thi_chua_cai(tmp_path):
    gpu_pack.install(wheels=_wheels(tmp_path), base=tmp_path / "gpu", pack="cu12", check=False)
    (tmp_path / "gpu" / "installed.json").write_text(json.dumps({"pack": "cu-cũ"}), encoding="utf-8")
    assert not gpu_pack.installed(tmp_path / "gpu")


def test_go_bo(tmp_path):
    gpu_pack.install(wheels=_wheels(tmp_path), base=tmp_path / "gpu", pack="cu12", check=False)
    gpu_pack.remove(tmp_path / "gpu")
    assert not gpu_pack.installed(tmp_path / "gpu")


def test_page_chuyen_qua_json_khong_mat_gi():
    p = Page(width=100, height=200, blocks=[
        Block("text", 1, 2, 30, 40, [Line("本文", 1.5, 2.5, 10.0, 12.0, 0.91, "", 3)], label="x")])
    d = json.loads(json.dumps(page_to_dict(p), ensure_ascii=False, default=float))
    assert page_from_dict(d) == p


def test_worker_xu_ly_ping_va_ocr_bang_engine_gia(tmp_path):
    class Fake:
        def ocr(self, img, name="page.png"):
            h, w = img.shape[:2]
            return Page(width=w, height=h, blocks=[Block("text", 0, 0, w, h, [Line(name, 0, 0, w, h, 0.5)])])

    ping = gpu_worker.handle({"op": "ping"})
    assert ping["ok"] and "providers" in ping

    npy = tmp_path / "img.npy"
    np.save(npy, np.zeros((7, 9, 3), dtype=np.uint8))
    resp = gpu_worker.handle({"op": "ocr", "engine": "fake", "npy": str(npy), "name": "p1.png"},
                             factory=lambda n: Fake())
    page = page_from_dict(json.loads(json.dumps(resp, default=float))["page"])
    assert (page.width, page.height) == (9, 7)
    assert page.blocks[0].lines[0].text == "p1.png"


def test_remote_engine_qua_tien_trinh_con_that(tmp_path, monkeypatch):
    """Chạy worker thật trong tiến trình con, engine giả. require_cuda=False vì máy kiểm không có CUDA."""
    code = ("import sys; from ocrnhat import gpu_worker\n"
            "from ocrnhat.model import Page, Block, Line\n"
            "class F:\n"
            "    def ocr(self, img, name='page.png'):\n"
            "        h, w = img.shape[:2]\n"
            "        return Page(width=w, height=h, blocks=[Block('text',0,0,w,h,[Line('ok',0,0,w,h,0.9)])])\n"
            "raise SystemExit(gpu_worker.main(factory=lambda n: F()))\n")
    monkeypatch.setattr(gpu_pack, "_worker_cmd", lambda: [sys.executable, "-c", code])
    eng = gpu_pack.RemoteEngine("fake", base=tmp_path, require_cuda=False)
    try:
        page = eng.ocr(np.zeros((4, 5, 3), dtype=np.uint8), "a.png")
        assert page.blocks[0].lines[0].text == "ok"
        assert (page.width, page.height) == (5, 4)
        page2 = eng.ocr(np.zeros((2, 2, 3), dtype=np.uint8), "b.png")   # tiến trình con sống qua nhiều yêu cầu
        assert (page2.width, page2.height) == (2, 2)
    finally:
        eng.close()


def test_chua_cai_thi_khong_co_engine_gpu(tmp_path, monkeypatch):
    monkeypatch.setattr(gpu_pack, "base_dir", lambda: tmp_path / "none")
    assert gpu_pack.remote_engine_for("ndlocr") is None


def _g(driver, cc, name="RTX test"):
    from ocrnhat.gpu import Gpu
    return Gpu(name, 8192, driver=driver, cc=cc)


def test_chon_goi_theo_driver_va_compute(monkeypatch):
    # cu13 cần driver >= 580.0 và compute >= 7.5; cu12 cần driver >= 576.2
    assert gpu_pack.select_pack([_g((581, 57), (8, 6))])[0] == "cu13"
    assert gpu_pack.select_pack([_g((577, 10), (8, 6))])[0] == "cu12"   # driver đủ cu12, chưa đủ cu13
    assert gpu_pack.select_pack([_g((570, 65), (8, 6))])[0] is None     # driver thấp hơn mọi gói
    assert "driver" in gpu_pack.select_pack([_g((570, 65), (8, 6))])[1]
    assert gpu_pack.select_pack([_g((581, 57), (6, 1))])[0] is None     # card đời cũ
    assert "compute" in gpu_pack.select_pack([_g((581, 57), (6, 1))])[1]


def test_khong_doc_duoc_driver_hoac_cc(monkeypatch):
    assert gpu_pack.select_pack([_g(None, (8, 6))])[0] is None
    assert gpu_pack.select_pack([_g((581, 57), None)])[0] is None
    monkeypatch.setattr(gpu_pack, "detect_gpus", lambda: [])
    assert gpu_pack.select_pack()[0] is None


def test_parse_nvidia_smi_cac_muc_thieu(monkeypatch):
    from ocrnhat import gpu
    out = "NVIDIA GeForce RTX 3060 Laptop GPU, 6144, 581.57, 8.6\n"
    g = gpu._parse_rows(out, ["name", "memory.total", "driver_version", "compute_cap"])[0]
    assert (g.name, g.vram_mb, g.driver, g.cc) == ("NVIDIA GeForce RTX 3060 Laptop GPU", 6144, (581, 57), (8, 6))
    g2 = gpu._parse_rows("RTX X, 4096, 560.10\n", ["name", "memory.total", "driver_version"])[0]
    assert g2.cc is None and g2.driver == (560, 10)
    assert gpu.parse_version("abc") is None


def test_marker_luu_ma_goi(tmp_path):
    gpu_pack.install(wheels=_wheels(tmp_path), pack="cu13", base=tmp_path / "gpu", check=False)
    assert gpu_pack.installed_pack(tmp_path / "gpu") == "cu13"


def test_manifest_hop_le():
    from ocrnhat import gpu_manifest as M
    assert set(M.PACKS) == {"cu12", "cu13"}
    for pid, pk in M.PACKS.items():
        assert pk["wheels"] and pk["total_bytes"] == sum(z for _, _, _, z in pk["wheels"])
        for name, url, sha, size in pk["wheels"]:
            assert len(sha) == 64 and url.startswith("https://files.pythonhosted.org/"), (pid, name)
