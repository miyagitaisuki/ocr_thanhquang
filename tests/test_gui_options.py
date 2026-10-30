"""Test ánh xạ tùy chọn GUI -> pipeline.process_file (không mở cửa sổ; cần tkinter, bỏ qua nếu không có)."""
import inspect

import pytest

tkinter = pytest.importorskip("tkinter")
gui = pytest.importorskip("ocrnhat.gui")

from ocrnhat import pipeline  # noqa: E402


class _Var:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


class _Form:
    """Thay cho App: chỉ giữ biến và nhãn thiết bị, để gọi trực tiếp App._read_options."""
    DEV_LABELS = gui.App.DEV_LABELS

    def __init__(self, **values):
        self.values = {"dev": gui.App.DEV_LABELS["auto"], **values}   # giá trị mặc định như khi mở GUI

    def _var(self, name, default):
        return _Var(self.values.get(name, default))


def _read(**values):
    return gui.App._read_options(_Form(**values))


def test_tuy_chon_mac_dinh_khop_voi_process_file():
    opts = _read()
    params = inspect.signature(pipeline.process_file).parameters
    assert set(opts) <= set(params), set(opts) - set(params)
    assert opts["cell_reocr"] is True and opts["use_cache"] is True


def test_checkbox_tat_duoc_truyen_xuong():
    opts = _read(cell_reocr=False, use_cache=False)
    assert opts["cell_reocr"] is False
    assert opts["use_cache"] is False


def test_crop_va_upscale_duoc_doc_dung():
    opts = _read(crop="10,20,300,400", upscale="2")
    assert opts["crop"] == (10, 20, 300, 400)
    assert opts["upscale"] == 2.0


def test_crop_sai_bao_loi_tieng_viet():
    with pytest.raises(ValueError, match="Vùng cắt"):
        _read(crop="300,20,10,400")


def test_upscale_khong_phai_so_bao_loi():
    with pytest.raises(ValueError, match="Phóng to"):
        _read(upscale="abc")
