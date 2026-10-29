"""Hồi quy: engine không được dùng chung giữa các luồng (không cần model thật)."""
import threading

from ocrnhat import engines, pipeline


class _FakeEngine:
    created = 0

    def __init__(self, device="cpu"):
        type(self).created += 1


def _get_in_thread():
    box = {}
    t = threading.Thread(target=lambda: box.update(e=pipeline.get_engine("ndlocr", "cpu")))
    t.start()
    t.join()
    return box["e"]


def test_moi_luong_co_engine_rieng(monkeypatch):
    monkeypatch.setattr(engines, "create", lambda name, device="cpu": _FakeEngine(device))
    monkeypatch.setattr(engines, "resolve", lambda name=None: (name or "ndlocr", "test"))
    monkeypatch.setattr(pipeline, "_tls", threading.local())
    main_a = pipeline.get_engine("ndlocr", "cpu")
    main_b = pipeline.get_engine("ndlocr", "cpu")
    other = _get_in_thread()
    assert main_a is main_b          # cùng luồng: dùng lại
    assert other is not main_a       # khác luồng: engine riêng
