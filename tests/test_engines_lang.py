"""Engine PaddleOCR/VietOCR và lọc ngôn ngữ: hậu xử lý DB, CTC, định tuyến engine. Không cần model."""
import numpy as np
import pytest

from ocrnhat import engines, layout
from ocrnhat.engines import models
from ocrnhat.engines.ocr_onnx import boxes_to_page, crop_quad, ctc_greedy, db_boxes, sort_boxes
from ocrnhat.engines.paddle import PaddleEngine
from ocrnhat.engines.viet import VietnameseEngine


def _prob(shape, rects):
    p = np.zeros(shape, dtype=np.float32)
    for x0, y0, x1, y1 in rects:
        p[y0:y1, x0:x1] = 0.9
    return p


def test_db_tim_hop_va_nới_theo_ti_le():
    boxes = db_boxes(_prob((100, 200), [(20, 30, 80, 50), (120, 60, 170, 75)]), 100, 200, unclip=1.5)
    assert len(boxes) == 2
    xs = sorted(b[:, 0].min() for b in boxes)
    assert xs[0] < 20 and xs[1] < 120            # hộp đã nới ra ngoài vùng sáng
    assert all(b.shape == (4, 2) for b in boxes)


def test_db_tu_choi_vung_nhieu_yeu():
    p = _prob((50, 50), [(10, 10, 30, 20)])
    p[10:20, 10:30] = 0.4                        # trên ngưỡng nhị phân nhưng dưới ngưỡng điểm hộp
    assert db_boxes(p, 50, 50, thresh=0.3, box_thresh=0.6) == []


def test_db_scale_ve_anh_goc():
    boxes = db_boxes(_prob((100, 100), [(10, 10, 40, 40)]), 200, 400, unclip=0)
    assert 150 <= boxes[0][:, 0].max() <= 165 and 76 <= boxes[0][:, 1].max() <= 82   # nhân 4x ngang, 2x dọc


def test_sort_boxes_theo_thu_tu_doc():
    def box(x, y):
        return np.array([[x, y], [x + 10, y], [x + 10, y + 10], [x, y + 10]], dtype=np.float32)
    got = sort_boxes([box(50, 100), box(0, 102), box(0, 0)])
    assert [tuple(b[0]) for b in got] == [(0.0, 0.0), (0.0, 102.0), (50.0, 100.0)]


def test_ctc_bo_blank_va_lap():
    chars = ["blank", "a", "b", " "]
    T = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 1, 0, 0], [1, 0, 0, 0], [0, 0, 1, 0]]   # a a _ b -> "ab"
    text, conf = ctc_greedy(np.array(T, dtype=np.float32), chars)
    assert text == "ab" and conf == pytest.approx(1.0)


def test_crop_quad_xoay_dong_dung():
    img = np.zeros((200, 200, 3), dtype=np.uint8)
    pts = np.array([[10, 10], [20, 10], [20, 110], [10, 110]], dtype=np.float32)   # dọc 10x100
    out = crop_quad(img, pts)
    assert out.shape[1] > out.shape[0]            # đã xoay thành ngang


def test_boxes_to_page_gom_khoi():
    def box(x, y, w=100, h=20):
        return np.array([[x, y], [x + w, y], [x + w, y + h], [x, y + h]], dtype=np.float32)
    page = boxes_to_page([(box(0, 0), "一", 0.9), (box(0, 25), "二", 0.8), (box(0, 500), "三", 0.7)], 300, 600)
    assert [len(b.lines) for b in page.blocks] == [2, 1]
    assert page.blocks[0].lines[1].order == 1


@pytest.mark.parametrize("text,lang,keep", [
    ("Invoice No. 2024", "en", True),
    ("中华人民共和国", "en", False),
    ("中华人民共和国", "zh", True),
    ("Hợp đồng số 12", "vi", True),
    ("Hợp đồng số 12", "en", False),
    ("2024-0153", "en", True),
    ("2024-0153", "zh", False),
    ("", "en", False),
])
def test_loc_theo_chu_cua_ngon_ngu(text, lang, keep):
    assert layout._script_keep(text, lang) is keep


def test_dinh_tuyen_engine_theo_ngon_ngu():
    assert engines.resolve_for_lang("auto", "en")[0] == "paddle"
    assert engines.resolve_for_lang("auto", "zh")[0] == "paddle"
    assert engines.resolve_for_lang("auto", "vi")[0] == "ocr_vi"
    assert engines.resolve_for_lang("ndlocr", "ja")[0] == "ndlocr"
    with pytest.raises(ValueError):
        engines.resolve_for_lang("ndlocr", "vi")
    with pytest.raises(ValueError):
        engines.resolve_for_lang("paddle", "vi")


def test_engine_da_dang_ky():
    assert "paddle" in engines.available() and "ocr_vi" in engines.available()
    assert "ocr_en" not in engines.available()
    assert engines.engine_version("paddle") and engines.engine_version("ocr_vi")


def test_thieu_model_bao_ro(monkeypatch, tmp_path):
    monkeypatch.setenv("OCRNHAT_MODELS", str(tmp_path))
    monkeypatch.setattr(models, "model_dirs", lambda: [tmp_path])
    ok, why = PaddleEngine.is_available()
    assert ok is False and models.DET in why
    with pytest.raises(FileNotFoundError):
        VietnameseEngine()
