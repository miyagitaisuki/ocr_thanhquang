"""Test logic giao diện không cần cửa sổ: nhãn, ánh xạ nhãn -> khóa, đọc tùy chọn, kiểm tra engine."""
import pytest

from ocrnhat import ui_logic as L


def _get(values):
    """Giả lập ô nhập: trả giá trị đã đặt, nếu không có thì trả mặc định (như _var(...).get())."""
    return lambda name, default: values.get(name, default)


def test_key_for_tra_mac_dinh_khi_nhan_la():
    assert L.key_for(L.ENGINE_LABELS, "Nhãn đã đổi tên", "auto") == "auto"
    assert L.key_for(L.ENGINE_LABELS, L.ENGINE_LABELS["ndlocr"], "auto") == "ndlocr"


def test_engine_key_nhan_cu_luu_trong_settings_khong_gay_loi():
    assert L.engine_key("") == "auto"
    assert L.engine_key(L.ENGINE_LABELS["paddle"]) == "paddle"


def test_dev_labels_chi_co_gpu_khi_co_cuda():
    assert "cuda" not in L.dev_labels(False)
    assert L.dev_labels(True)["cuda"] == "GPU (NVIDIA)"


def test_read_options_mac_dinh():
    opts = L.read_options(_get({}))
    assert opts["lang"] == "ja" and opts["engine"] == "auto" and opts["device"] == "auto"
    assert opts["merge_pages"] is True and opts["kana_reader"] == ""
    assert opts["conf_threshold"] == 0.8 and opts["upscale"] == 1.0 and opts["crop"] is None


def test_read_options_loi_kiem_tra_bang_tieng_viet():
    with pytest.raises(ValueError, match="Ngưỡng"):
        L.read_options(_get({"conf": "abc"}))
    with pytest.raises(ValueError, match="phải lớn hơn 0"):
        L.read_options(_get({"upscale": "0"}))
    with pytest.raises(ValueError, match="Vùng cắt"):
        L.read_options(_get({"crop": "300,20,10,400"}))


def test_engine_problem_bao_thieu_model_va_ngon_ngu_sai():
    class Missing:
        @staticmethod
        def is_available():
            return False, "thiếu model"

    opts = L.read_options(_get({"engine": L.ENGINE_LABELS["paddle"], "lang": L.LANG_LABELS["en"]}))
    assert L.engine_problem(opts, {"paddle": Missing}.get) == "Chưa dùng được Tiếng Anh, Trung – PaddleOCR vì thiếu model"

    opts = L.read_options(_get({"engine": L.ENGINE_LABELS["ndlocr"], "lang": L.LANG_LABELS["en"]}))
    assert "không đọc được" in L.engine_problem(opts, {}.get)


def test_engine_problem_ndlocr_khong_can_model():
    opts = L.read_options(_get({"engine": L.ENGINE_LABELS["ndlocr"]}))
    assert L.engine_problem(opts, {}.get) is None


def test_split_value_theo_kieu_tach():
    assert L.split_value("pages", "3") == 3
    assert L.split_value("pages", "") == 1
    assert L.split_value("size", "2.5") == 2.5
    assert L.split_value("bookmark", "abc") is None
    with pytest.raises(ValueError, match="phải là số"):
        L.split_value("size", "abc")


def test_image_quality_gioi_han_1_den_95():
    assert L.image_quality(False, "abc") is None   # tắt nén ảnh thì không kiểm tra
    assert L.image_quality(True, "75") == 75
    for bad in ("0", "96", "x"):
        with pytest.raises(ValueError, match="từ 1 đến 95"):
            L.image_quality(True, bad)


def test_name_or_dung_mac_dinh_khi_trong():
    assert L.name_or("  ", "ghep") == "ghep"
    assert L.name_or(" tong ", "ghep") == "tong"


def test_yomitoku_chi_nhan_tieng_nhat_va_bao_thieu_thu_vien():
    assert L.ENGINE_LANGS["yomitoku"] == ("ja",)
    assert L.engine_key(L.ENGINE_LABELS["yomitoku"]) == "yomitoku"
    opts = L.read_options(_get({"engine": L.ENGINE_LABELS["yomitoku"]}))
    assert opts["engine"] == "yomitoku" and opts["lang"] == "ja"

    class Missing:
        @classmethod
        def is_available(cls):
            return False, "chưa cài yomitoku"
    why = L.engine_problem(opts, {"yomitoku": Missing}.get)
    assert why and "YomiToku" in why and "chưa cài" in why
