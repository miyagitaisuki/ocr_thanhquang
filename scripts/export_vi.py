"""Xuất model VietOCR sang ONNX int8 cho engine ocr_vi. Cần torch và vietocr (chỉ dùng khi xuất, không vào exe).

Chạy: pip install torch torchvision vietocr==0.3.13 --no-deps && pip install gdown==4.4.0 prefetch-generator einops lmdb scikit-image
      python scripts/export_vi.py [--dir DUONG_DAN]
Tạo: vi_cnn_int8.onnx, vi_enc_int8.onnx, vi_dec_int8.onnx, vi_vocab.txt trong models/.
Trọng số VietOCR (vgg_seq2seq.pth) và cấu hình tải từ vocr.vn; nạp bằng weights_only=True. Xem NOTICE.md.
"""
import argparse
import hashlib
import sys
import urllib.request
from pathlib import Path

import torch
import yaml
from onnxruntime.quantization import QuantType, quantize_dynamic
from vietocr.model.transformerocr import VietOCR
from vietocr.model.vocab import Vocab

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://vocr.vn/data/vietocr"
PTH = ("vgg_seq2seq.pth", "0921503a41375a0584268e23ef3d414ea478a8fe8777865c7745d38f2d0bc5db")


def fetch(url: str, dst: Path, want: str | None = None) -> Path:
    if not dst.is_file():
        urllib.request.urlretrieve(url, dst)
    if want and hashlib.sha256(dst.read_bytes()).hexdigest() != want:
        raise SystemExit(f"Sai SHA-256: {dst.name}")
    return dst


class _Cnn(torch.nn.Module):
    # chỉ phần tích chập; sắp xếp chiều làm bằng numpy trong engines/viet.py (perm âm không hợp lệ trong ONNX)
    def __init__(self, m):
        super().__init__()
        self.m = m

    def forward(self, x):
        return self.m.last_conv_1x1(self.m.dropout(self.m.features(x)))


class _Enc(torch.nn.Module):
    def __init__(self, t):
        super().__init__()
        self.t = t

    def forward(self, src):
        return self.t.encoder(src)


class _Dec(torch.nn.Module):
    def __init__(self, t):
        super().__init__()
        self.t = t

    def forward(self, tok, hid, enc):
        pred, hid, _ = self.t.decoder(tok, hid, enc)
        return pred, hid


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=str(ROOT / "models"))
    a = ap.parse_args()
    out = Path(a.dir)
    out.mkdir(parents=True, exist_ok=True)
    work = out / "_vi_src"
    work.mkdir(exist_ok=True)

    base = yaml.safe_load(fetch(f"{BASE}/config/base.yml", work / "base.yml").read_text(encoding="utf-8"))
    cfg = yaml.safe_load(fetch(f"{BASE}/config/vgg-seq2seq.yml", work / "vgg-seq2seq.yml").read_text(encoding="utf-8"))
    pth = fetch(f"{BASE}/{PTH[0]}", work / PTH[0], PTH[1])

    vocab = Vocab(base["vocab"])
    model = VietOCR(len(vocab), cfg["backbone"], dict(cfg["cnn"], pretrained=False), cfg["transformer"], cfg["seq_modeling"])
    model.load_state_dict(torch.load(pth, map_location="cpu", weights_only=True))
    model.eval()
    tr = model.transformer

    with torch.no_grad():
        dummy = torch.randn(1, 3, 32, 160)
        raw = work / "fp32"
        raw.mkdir(exist_ok=True)
        torch.onnx.export(_Cnn(model.cnn.model), dummy, raw / "cnn.onnx", input_names=["img"], output_names=["conv"],
                          dynamic_axes={"img": {0: "b", 3: "w"}, "conv": {0: "b", 3: "t"}}, opset_version=17, dynamo=False)
        feat = _Cnn(model.cnn.model)(dummy)
        feat = feat.permute(0, 1, 3, 2).flatten(2).permute(2, 0, 1)
        torch.onnx.export(_Enc(tr), (feat,), raw / "enc.onnx", input_names=["feat"], output_names=["enc", "hid"],
                          dynamic_axes={"feat": {0: "t", 1: "b"}, "enc": {0: "t", 1: "b"}, "hid": {0: "b"}},
                          opset_version=17, dynamo=False)
        enc_out, hid = tr.encoder(feat)
        torch.onnx.export(_Dec(tr), (torch.tensor([1]), hid, enc_out), raw / "dec.onnx",
                          input_names=["tok", "hid", "enc"], output_names=["pred", "hid_out"],
                          dynamic_axes={"enc": {0: "t", 1: "b"}, "hid": {0: "b"}, "tok": {0: "b"}},
                          opset_version=17, dynamo=False)

    for src, dst in [("cnn.onnx", "vi_cnn_int8.onnx"), ("enc.onnx", "vi_enc_int8.onnx"), ("dec.onnx", "vi_dec_int8.onnx")]:
        quantize_dynamic(str(raw / src), str(out / dst), weight_type=QuantType.QInt8)
    chars = vocab.chars
    (out / "vi_vocab.txt").write_text("\n".join(chars) + "\n", encoding="utf-8")
    print("Đã xuất vào", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
