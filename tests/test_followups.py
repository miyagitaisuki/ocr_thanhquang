"""Test cho các điểm còn mở của PR #2: --crop sai, lý do chọn engine, xử lý ảnh trước OCR, ký tự rác và ①②③."""
import numpy as np
import pytest

from ocrnhat import cli, engines, gpu, pipeline
from ocrnhat.layout import Cell, _fix_circled, _kana_core


def test_parse_crop_hop_le_va_sai():
    assert pipeline.parse_crop("10,20,300,400") == (10, 20, 300, 400)
    assert pipeline.parse_crop("") is None
    with pytest.raises(ValueError):
        pipeline.parse_crop("300,20,10,400")      # x1 <= x0
    with pytest.raises(ValueError):
        pipeline.parse_crop("1,2,3")              # thiếu số


def test_cli_crop_sai_bao_loi_cach_dung(capsys):
    with pytest.raises(SystemExit) as e:
        cli.main(["x.pdf", "--crop", "5,5,1,1"])
    assert e.value.code == 2
    assert "--crop" in capsys.readouterr().err


def test_preprocess_cat_roi_phong_to():
    img = np.zeros((100, 200, 3), np.uint8)
    out = pipeline.preprocess(img, crop=(10, 20, 110, 70), upscale=2.0)
    assert out.shape == (100, 200, 3)            # cắt 100x50 rồi phóng to 2 lần
    assert out.flags["C_CONTIGUOUS"]


def test_resolve_khong_co_gpu_ghi_ly_do(monkeypatch):
    monkeypatch.setattr(gpu, "best_gpu", lambda: None)
    assert engines.resolve("auto") == ("ndlocr", "không có GPU rời đủ VRAM")


def test_resolve_device_cpu_va_cuda_thieu_provider(monkeypatch):
    assert gpu.resolve_device("cpu") == ("cpu", "chọn CPU")
    monkeypatch.setattr(gpu, "ort_cuda_available", lambda: False)
    dev, why = gpu.resolve_device("cuda")
    assert dev == "cpu" and "onnxruntime" in why


def test_resolve_device_chandra_theo_torch_khong_theo_onnxruntime(monkeypatch):
    monkeypatch.setattr(gpu, "ort_cuda_available", lambda: False)   # exe CPU: onnxruntime không có CUDA
    monkeypatch.setattr(gpu, "torch_cuda_available", lambda: True)
    assert gpu.resolve_device("auto", "chandra")[0] == "cuda"       # trước đây ra "cpu" và ép Chandra chạy CPU
    assert gpu.resolve_device("cuda", "chandra")[0] == "cuda"
    assert gpu.resolve_device("cpu", "chandra")[0] == "cpu"
    monkeypatch.setattr(gpu, "torch_cuda_available", lambda: False)
    dev, why = gpu.resolve_device("cuda", "chandra")
    assert dev == "cpu" and "torch" in why


def test_gpu_selectable_khi_co_card_nvidia_du_onnxruntime_cpu(monkeypatch):
    monkeypatch.setattr(gpu, "ort_cuda_available", lambda: False)
    monkeypatch.setattr(gpu, "detect", lambda: [gpu.Gpu("NVIDIA GeForce RTX 3060", 12288)])
    assert gpu.gpu_selectable() is True
    monkeypatch.setattr(gpu, "detect", lambda: [])
    assert gpu.gpu_selectable() is False


def test_kana_core_bo_rac_va_giu_nhan():
    assert _kana_core("きょう OC") == "きょう"
    assert _kana_core("$ ちょうしつ") == "ちょうしつ"
    assert _kana_core("b. いつ") == ""          # nhãn có dấu chấm: không coi là rác


def test_fix_circled_doi_ma_thanh_so_khoanh():
    cells = [Cell(0, 0, text="項目"), Cell(1, 0, text="(1"), Cell(2, 0, text="19"), Cell(3, 0, text="O1")]
    _fix_circled(cells)
    assert [c.text for c in cells[1:]] == ["①", "②", "③"]


def test_fix_circled_giu_nguyen_neu_khong_chac():
    cells = [Cell(0, 0, text="項目"), Cell(1, 0, text="(1)"), Cell(2, 0, text="19")]   # có ')' -> giữ nguyên
    _fix_circled(cells)
    assert [c.text for c in cells[1:]] == ["(1)", "19"]
