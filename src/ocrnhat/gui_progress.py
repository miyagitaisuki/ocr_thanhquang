"""Thanh tiến trình động dùng chung (OCR và các mục PDF).

Số phần trăm nằm riêng bên phải nên không bị cắt khi cửa sổ đổi tỉ lệ; bên trái là tờ giấy minh hoạ:
khi đang chạy, một tờ lật qua lại; xong thì hiện dấu tích. Trên thanh có dải sáng chạy khi đang làm việc.
Kế thừa QProgressBar nên vẫn dùng setValue/setRange như cũ.
"""
from __future__ import annotations

import math

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QApplication, QProgressBar

from .gui_style import PALETTES

FRAME_MS = 33          # khoảng 30 khung hình/giây
EASE = 0.18            # tốc độ thanh chạy tới giá trị mới


class AnimatedProgress(QProgressBar):
    def __init__(self):
        super().__init__()
        self.setRange(0, 100)
        self.setTextVisible(False)
        self.setObjectName("animProgress")
        self._shown = 0.0          # vị trí đang vẽ, trượt dần về value()
        self._phase = 0.0          # pha hoạt hoạ, 0..1
        self._active = False       # đang chạy một tác vụ (kể cả khi giá trị chưa đổi)
        self._timer = QTimer(self)
        self._timer.setInterval(FRAME_MS)
        self._timer.timeout.connect(self._tick)

    def setValue(self, value: int):
        super().setValue(value)
        if not self._timer.isActive():
            self._timer.start()

    def setActive(self, active: bool):
        self._active = active
        if active and not self._timer.isActive():
            self._timer.start()

    def _busy(self) -> bool:
        return self._active or 0 < self.value() < 100

    def _tick(self):
        target = float(self.value())
        self._shown += (target - self._shown) * EASE
        self._phase = (self._phase + 0.03) % 1.0
        if not self._busy() and abs(target - self._shown) < 0.3:
            self._shown = target
            self._timer.stop()
        self.update()

    def paintEvent(self, _event):
        theme = QApplication.instance().property("ocr_theme")
        t = PALETTES.get(theme, PALETTES["sáng"])
        w, h = self.width(), self.height()
        icon_w = h
        pct_w = max(58, int(h * 1.6))
        gap = 10
        bar_x = icon_w + gap
        bar_w = max(0, w - bar_x - pct_w - gap)
        bar_h = max(10.0, h * 0.34)
        bar_y = (h - bar_h) / 2
        radius = bar_h / 2

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._paint_page(p, QRectF(0, 0, icon_w, h), t)

        track = QRectF(bar_x, bar_y, bar_w, bar_h)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(t["border"]))
        p.drawRoundedRect(track, radius, radius)

        fill_w = bar_w * self._shown / 100
        if fill_w > 0:
            fill = QRectF(bar_x, bar_y, max(fill_w, bar_h), bar_h)
            grad = QLinearGradient(fill.topLeft(), fill.topRight())
            grad.setColorAt(0, QColor(t["accent_hi"]))
            grad.setColorAt(1, QColor(t["accent_lo"]))
            path = QPainterPath()
            path.addRoundedRect(fill, radius, radius)
            p.fillPath(path, grad)
            if self._busy():
                p.save()
                p.setClipPath(path)
                x = fill.left() - bar_h + ((self._phase * 2) % 1.0) * (fill.width() + bar_h)
                p.setBrush(QColor(255, 255, 255, 70))
                p.drawRect(QRectF(x, bar_y, bar_h * 0.7, bar_h))
                p.restore()

        font = QFont(self.font())
        font.setBold(True)
        font.setPixelSize(max(12, int(h * 0.36)))
        p.setFont(font)
        p.setPen(QColor(t["text"]))
        p.drawText(QRectF(w - pct_w, 0, pct_w, h), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                   f"{self.value()}%")
        p.end()

    def _paint_page(self, p: QPainter, r: QRectF, t: dict):
        """Tờ giấy minh hoạ: đang chạy thì một tờ lật co dần; xong thì hiện dấu tích."""
        page = QRectF(r.left() + r.width() * 0.18, r.top() + r.height() * 0.08,
                      r.width() * 0.64, r.height() * 0.84)
        p.setPen(QPen(QColor(t["ctl_border"]), 1.2))
        p.setBrush(QColor(t["card"]))
        p.drawRoundedRect(page, 4, 4)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(t["muted"]))
        for i in range(3):
            y = page.top() + page.height() * (0.26 + 0.2 * i)
            p.drawRect(QRectF(page.left() + page.width() * 0.2, y, page.width() * 0.6, max(1.5, page.height() * 0.06)))
        if self._busy():
            flip = abs(math.cos(self._phase * math.pi))
            sheet = QRectF(page.left(), page.top(), page.width() * flip, page.height())
            p.setBrush(QColor(t["accent_hi"]))
            p.setOpacity(0.55)
            p.drawRoundedRect(sheet, 4, 4)
            p.setOpacity(1.0)
        elif self.value() >= 100:
            pen = QPen(QColor(t["accent"]), max(2.0, page.height() * 0.08))
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            cx, cy, s = page.center().x(), page.center().y(), page.height() * 0.22
            check = QPainterPath()
            check.moveTo(cx - s, cy)
            check.lineTo(cx - s * 0.3, cy + s * 0.7)
            check.lineTo(cx + s, cy - s * 0.6)
            p.drawPath(check)
