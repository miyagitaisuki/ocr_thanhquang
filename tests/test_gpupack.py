"""Gói GPU tùy chọn: chọn phiên bản cu126, đối số pip, trạng thái cài. Không tải mạng thật."""
import io
import sys
from pathlib import Path

from ocrnhat import gpupack

INDEX = (
    '<a href="torch-2.13.0%2Bcu126-cp312-cp312-win_amd64.whl#sha256=aa">x</a>'
    '<a href="torch-2.14.1%2Bcu126-cp312-cp312-win_amd64.whl#sha256=bb">x</a>'
    '<a href="torch-2.14.1%2Bcu126-cp313-cp313-win_amd64.whl">x</a>'
    '<a href="torch-2.14.1-cp312-cp312-win_amd64.whl">x</a>'
)


def _fake_urlopen(html):
    def opener(url, timeout=60):
        return io.BytesIO(html.encode("utf-8"))
    return opener


def test_chon_ban_cu126_moi_nhat_cho_windows_cp312(monkeypatch):
    monkeypatch.setattr(gpupack.urllib.request, "urlopen", _fake_urlopen(INDEX))
    assert gpupack._latest_cu126("torch") == "2.14.1"


def test_torchvision_theo_quy_tac_minor_cong_15(monkeypatch):
    html = ('<a href="torchvision-0.28.0%2Bcu126-cp312-cp312-win_amd64.whl">x</a>'
            '<a href="torchvision-0.29.1%2Bcu126-cp312-cp312-win_amd64.whl">x</a>'
            '<a href="torchvision-0.30.0%2Bcu126-cp312-cp312-win_amd64.whl">x</a>')
    monkeypatch.setattr(gpupack.urllib.request, "urlopen", _fake_urlopen(html))
    assert gpupack._latest_cu126("torchvision", minor_prefix="0.29.") == "0.29.1"


def test_pip_args_ghim_cuda_va_chandra(tmp_path):
    args = gpupack.pip_args(["torch==2.14.1+cu126"], tmp_path)
    assert "--extra-index-url" in args and gpupack.CU_INDEX in args
    assert "torch==2.14.1+cu126" in args and args[-1] == gpupack.CHANDRA_SPEC


def test_chua_cai_thi_khong_kich_hoat(monkeypatch, tmp_path):
    monkeypatch.setattr(gpupack, "pack_dir", lambda: tmp_path)
    assert gpupack.installed() is False
    assert gpupack.activate() is False


def test_co_du_thu_muc_nhung_thieu_dau_hieu_thi_chua_cai(monkeypatch, tmp_path):
    (tmp_path / "torch").mkdir()
    (tmp_path / "chandra").mkdir()
    monkeypatch.setattr(gpupack, "pack_dir", lambda: tmp_path)
    assert gpupack.installed() is False        # thiếu tệp đánh dấu: cài dở
    (tmp_path / gpupack.MARKER).write_text("ok", encoding="utf-8")
    assert gpupack.installed() is True


def test_cai_that_bai_bao_loi_than_thien_va_ghi_log(monkeypatch, tmp_path):
    monkeypatch.setattr(gpupack, "pack_dir", lambda: tmp_path)

    def hong(): raise ImportError("distlib finder")
    monkeypatch.setattr(gpupack, "check_pip", hong)
    try:
        gpupack.install(progress=lambda m: None)
    except gpupack.PackError as e:
        assert str(e) == gpupack.PACK_FAILED_MSG
    else:
        raise AssertionError("phải ném PackError")
    log = (tmp_path / "install.log").read_text(encoding="utf-8")
    assert "distlib finder" in log and not (tmp_path / gpupack.MARKER).exists()


def test_exe_dong_goi_dang_ky_finder_cho_distlib(monkeypatch):
    from pip._vendor.distlib import resources

    fake = type("PyiFrozenImporter", (), {})()
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(gpupack.importlib, "import_module", lambda name: type("M", (), {"__loader__": fake})())
    monkeypatch.setattr(resources, "_finder_registry", dict(resources._finder_registry))
    gpupack._register_frozen_finder()
    assert resources._finder_registry[type(fake)] is resources.ResourceFinder
