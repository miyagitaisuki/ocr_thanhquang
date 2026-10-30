"""Test phần dò chữ nghi ngờ KHÔNG cần tải mô hình: đánh dấu và lọc dòng ngắn."""
from ocrnhat import pipeline, suspect
from ocrnhat.layout import Para


def test_mark_chen_dau_sau_ky_tu_nghi_ngo():
    s = [suspect.Suspect(index=3, char="覚", prob=0.00005, alternatives="意見論")]
    assert suspect.mark("私見は覚", s) == "私見は覚〔?〕"  # chỉ ký tự ở vị trí 3 có dấu


def test_mark_khong_co_nghi_ngo_giu_nguyen():
    assert suspect.mark("日本語", []) == "日本語"


def test_dong_ngan_bi_bo_qua(monkeypatch):
    calls = []
    monkeypatch.setattr(suspect, "scan_line", lambda t, thr=0: calls.append(t) or [])
    items = [Para("短い"), Para("これは十二文字以上の長い文章です。")]
    pipeline._suspect_rows(items, 0.0005)
    assert calls == ["これは十二文字以上の長い文章です。"]


def test_dong_nghi_ngo_duoc_bao_cao(monkeypatch):
    s = [suspect.Suspect(index=3, char="覚", prob=0.00002, alternatives="見意論")]
    monkeypatch.setattr(suspect, "scan_line", lambda t, thr=0: s)
    rows = pipeline._suspect_rows([Para("これは私覚です文章長い。")], 0.0005)
    assert len(rows) == 1 and "〔?〕" in rows[0] and "見意論" in rows[0]
