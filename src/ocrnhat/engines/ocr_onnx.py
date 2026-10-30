"""Thành phần ONNX chung cho PaddleOCR và VietOCR: dò dòng DB (OpenCV), cắt dòng, giải mã CTC và greedy."""
from __future__ import annotations

import cv2
import numpy as np

from ..model import Block, Line, Page

MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


def session(path):
    import onnxruntime as ort
    return ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])


class DbDetector:
    """PP-OCRv4 det (DB). Hậu xử lý bằng OpenCV: ngưỡng, contour, minAreaRect, nới hộp (unclip) theo tỉ lệ DB."""

    def __init__(self, path, limit_side: int = 960, thresh: float = 0.3, box_thresh: float = 0.6,
                 unclip: float = 1.5, min_size: int = 3):
        self.sess = session(path)
        self.inp = self.sess.get_inputs()[0].name
        self.limit_side = limit_side
        self.thresh, self.box_thresh, self.unclip, self.min_size = thresh, box_thresh, unclip, min_size

    def _resize(self, img):
        h, w = img.shape[:2]
        ratio = min(1.0, self.limit_side / max(h, w))
        nh = max(32, int(round(h * ratio / 32)) * 32)
        nw = max(32, int(round(w * ratio / 32)) * 32)
        return cv2.resize(img, (nw, nh)), nh, nw

    def detect(self, img_rgb: np.ndarray) -> list[np.ndarray]:
        """Trả về danh sách hộp 4 đỉnh (4,2) float32 theo tọa độ ảnh gốc."""
        h0, w0 = img_rgb.shape[:2]
        r, nh, nw = self._resize(img_rgb)
        x = ((r.astype(np.float32) / 255.0 - MEAN) / STD).transpose(2, 0, 1)[None]
        prob = self.sess.run(None, {self.inp: x.astype(np.float32)})[0][0, 0]
        return db_boxes(prob, h0, w0, self.thresh, self.box_thresh, self.unclip, self.min_size)


def order_quad(pts: np.ndarray) -> np.ndarray:
    """Đưa 4 đỉnh về thứ tự trên-trái, trên-phải, dưới-phải, dưới-trái (cần cho nắn phối cảnh)."""
    s = pts.sum(1)
    d = pts[:, 1] - pts[:, 0]
    return np.stack([pts[np.argmin(s)], pts[np.argmin(d)], pts[np.argmax(s)], pts[np.argmax(d)]]).astype(np.float32)


def db_boxes(prob: np.ndarray, src_h: int, src_w: int, thresh=0.3, box_thresh=0.6, unclip=1.5,
             min_size=3, max_candidates=1000) -> list[np.ndarray]:
    """Hậu xử lý DB: prob (H,W) có giá trị 0..1 -> hộp 4 đỉnh theo tọa độ ảnh gốc (src_h, src_w)."""
    ph, pw = prob.shape
    bitmap = (prob > thresh).astype(np.uint8) * 255
    contours, _ = cv2.findContours(bitmap, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    sx, sy = src_w / pw, src_h / ph
    boxes = []
    for c in contours[:max_candidates]:
        if len(c) < 3:
            continue
        (cx, cy), (bw, bh), ang = cv2.minAreaRect(c)
        if min(bw, bh) < min_size:
            continue
        x0, y0, cw, ch = cv2.boundingRect(c)
        m = np.zeros((ch, cw), dtype=np.uint8)
        cv2.drawContours(m, [c - [x0, y0]], -1, 1, -1)
        if prob[y0:y0 + ch, x0:x0 + cw][m > 0].mean() < box_thresh:
            continue
        # unclip (DB): nới mỗi cạnh một khoảng d = diện tích * ratio / chu vi. Với hộp chữ nhật, nới hai chiều.
        d = bw * bh * unclip / (2 * (bw + bh))
        pts = cv2.boxPoints(((cx, cy), (bw + 2 * d, bh + 2 * d), ang)).astype(np.float32)
        pts[:, 0] = np.clip(pts[:, 0], 0, pw - 1) * sx
        pts[:, 1] = np.clip(pts[:, 1], 0, ph - 1) * sy
        boxes.append(order_quad(pts))
    return boxes


def sort_boxes(boxes: list[np.ndarray]) -> list[np.ndarray]:
    """Thứ tự đọc: từ trên xuống, cùng dòng (lệch dưới 10 px) thì từ trái sang phải (như PaddleOCR)."""
    boxes = sorted(boxes, key=lambda b: (round(b[0, 1]), b[0, 0]))
    for i in range(len(boxes) - 1):
        for j in range(i, -1, -1):
            a, b = boxes[j], boxes[j + 1]
            if abs(b[0, 1] - a[0, 1]) < 10 and b[0, 0] < a[0, 0]:
                boxes[j], boxes[j + 1] = b, a
            else:
                break
    return boxes


def crop_quad(img: np.ndarray, pts: np.ndarray) -> np.ndarray:
    """Cắt hộp 4 đỉnh thành ảnh chữ nhật (nắn phối cảnh). Dòng đứng cao hơn 1,5 lần chiều rộng được xoay."""
    w = int(max(np.linalg.norm(pts[0] - pts[1]), np.linalg.norm(pts[2] - pts[3])))
    h = int(max(np.linalg.norm(pts[0] - pts[3]), np.linalg.norm(pts[1] - pts[2])))
    w, h = max(w, 1), max(h, 1)
    dst = np.array([[0, 0], [w, 0], [w, h], [0, h]], dtype=np.float32)
    m = cv2.getPerspectiveTransform(pts.astype(np.float32), dst)
    out = cv2.warpPerspective(img, m, (w, h), borderMode=cv2.BORDER_REPLICATE)
    if h >= 1.5 * w:
        out = np.rot90(out)
    return np.ascontiguousarray(out)


def ctc_greedy(probs: np.ndarray, chars: list[str]) -> tuple[str, float]:
    """Giải mã CTC tham lam. probs (T, C), chỉ số 0 là blank. Trả về (chữ, độ tin cậy trung bình)."""
    idx = probs.argmax(-1)
    best = probs.max(-1)
    out, confs, prev = [], [], 0
    for t, i in enumerate(idx):
        if i != 0 and i != prev and i < len(chars):
            out.append(chars[i])
            confs.append(float(best[t]))
        prev = i
    return "".join(out), (sum(confs) / len(confs) if confs else 0.0)


def boxes_to_page(lines: list[tuple[np.ndarray, str, float]], width: int, height: int) -> Page:
    """Ghép các dòng (hộp, chữ, độ tin cậy) đã sắp thứ tự đọc thành Page. Gom khối khi các dòng sát nhau."""
    if not lines:
        return Page(width, height, [])
    H = float(np.median([np.linalg.norm(b[0] - b[3]) for b, _, _ in lines])) or 1.0
    blocks: list[Block] = []
    prev: Line | None = None
    for order, (pts, text, conf) in enumerate(lines):
        x, y = float(pts[:, 0].min()), float(pts[:, 1].min())
        w, h = float(pts[:, 0].max() - x), float(pts[:, 1].max() - y)
        ln = Line(text, x, y, w, h, conf, "", order)
        if prev is not None and blocks and abs(ln.x - prev.x) < 3 * H and -0.5 * H < ln.y - prev.y1 < 1.5 * H:
            blocks[-1].lines.append(ln)
            blocks[-1].w = max(blocks[-1].w, ln.x1 - blocks[-1].x)
            blocks[-1].h = max(blocks[-1].h, ln.y1 - blocks[-1].y)
        else:
            blocks.append(Block("text", x, y, w, h, [ln]))
        prev = ln
    return Page(width, height, blocks)
