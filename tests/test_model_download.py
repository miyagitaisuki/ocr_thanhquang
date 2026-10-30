"""Tải model PaddleOCR: báo tiến độ, bỏ qua tệp đã đúng, lỗi khi sai SHA-256. Không cần mạng."""
import io

import pytest

from ocrnhat.engines import models


class _Resp(io.BytesIO):
    def __init__(self, data):
        super().__init__(data)
        self.headers = {"Content-Length": str(len(data))}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _fake(monkeypatch, payloads):
    """payloads: tên -> bytes. Đặt SHA-256 đúng với bytes đó."""
    import hashlib
    table = {}
    for name, data in payloads.items():
        table[name] = ("http://x/" + name, hashlib.sha256(data).hexdigest())
    monkeypatch.setattr(models, "PADDLE_FILES", table)
    monkeypatch.setattr(models.urllib.request, "urlopen", lambda url, timeout=60: _Resp(payloads[url.rsplit("/", 1)[1]]))
    return table


def test_tai_du_va_bao_tien_do(monkeypatch, tmp_path):
    data = {"a.onnx": b"x" * 200_000, "b.onnx": b"y" * 10, "c.txt": b"z"}
    _fake(monkeypatch, data)
    seen = []
    names = models.download_paddle(progress=lambda i, n, name, f: seen.append((i, n, name, round(f, 2))), dest=tmp_path)
    assert names == list(data)
    assert all((tmp_path / n).read_bytes() == data[n] for n in data)
    assert seen[0][2] == "a.onnx" and 0 < seen[0][3] < 1
    assert any(s[2] == "a.onnx" and 0 < s[3] < 1 for s in seen)     # có mốc giữa chừng
    assert seen[-1][0] == len(data)                                  # kết thúc với i = n


def test_bo_qua_tep_da_dung(monkeypatch, tmp_path):
    data = {"a.onnx": b"abc"}
    _fake(monkeypatch, data)
    (tmp_path / "a.onnx").write_bytes(b"abc")
    called = []
    monkeypatch.setattr(models.urllib.request, "urlopen", lambda *a, **k: called.append(1) or _Resp(b""))
    models.download_paddle(dest=tmp_path)
    assert called == []


def test_sai_sha_bao_loi_va_khong_de_file(monkeypatch, tmp_path):
    _fake(monkeypatch, {"a.onnx": b"abc"})
    monkeypatch.setattr(models.urllib.request, "urlopen", lambda *a, **k: _Resp(b"hong"))
    with pytest.raises(RuntimeError, match="SHA-256"):
        models.download_paddle(dest=tmp_path)
    assert not (tmp_path / "a.onnx").exists()
    assert not (tmp_path / "a.onnx.part").exists()
