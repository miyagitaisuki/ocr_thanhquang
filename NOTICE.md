# Ghi công / giấy phép bên thứ ba

Ứng dụng này dùng **NDLOCR-Lite** của Thư viện Quốc hội Nhật Bản (NDL Lab),
phát hành theo giấy phép **CC BY 4.0** — https://github.com/ndl-lab/ndlocr-lite
(mã nguồn và mô hình được tải về lúc build, đúng commit ghim trong `scripts/fetch_ndlocr.py`;
không sao chép vào repo này). Mô hình phát hiện bố cục dùng backbone DINOv3 chưng cất, xem
giấy phép DINOv3 trong repo NDLOCR-Lite.

## PaddleOCR (engine `paddle`: tiếng Anh và tiếng Trung)

Dùng mô hình PP-OCRv4 (dò dòng `ch_PP-OCRv4_det_infer`, nhận dạng `ch_PP-OCRv4_rec_infer`) và từ điển `ppocr_keys_v1.txt` của **PaddleOCR** (PaddlePaddle), giấy phép **Apache-2.0**: https://github.com/PaddlePaddle/PaddleOCR
- File ONNX lấy từ Hugging Face `SWHL/RapidOCR` (đóng gói lại, Apache-2.0). Từ điển lấy từ mã nguồn PaddleOCR (nhánh release/2.7).
- Model không đóng vào exe; `scripts/fetch_models.py` tải về `models/` và kiểm SHA-256.

## VietOCR (engine `ocr_vi`: tiếng Việt)

Dùng kiến trúc và trọng số `vgg_seq2seq.pth` của **VietOCR** (pbcquoc/vietocr, phiên bản 0.3.13), giấy phép **Apache-2.0**, xuất sang ONNX int8 (`assets/vi-ocr/`, bằng `scripts/export_vi.py`).
- Chủ dự án xác nhận Apache-2.0 cho gói này. Ghi chú: file LICENSE trong gói ghi Apache-2.0, còn metadata ghi MIT.
- Các file ONNX và từ điển được tải trong GUI (tab AI powered) từ chính repo này, kiểm SHA-256.

## pyvi (hậu xử lý tiếng Việt, `src/ocrnhat/data/vi_words.txt`)

Danh sách cụm âm tiết tiếng Việt lấy từ gói **pyvi** 0.1.1 (Viet-Trung Tran), giấy phép **MIT**: https://github.com/trungtv/pyvi (file `pyvi/models/words.txt` trong gói). Dùng để kiểm tra âm tiết hợp lệ khi sửa dấu của engine `ocr_vi`.

## PySide6 (giao diện chính, `OCR-Nhat.exe`)

**PySide6** (Qt for Python) theo giấy phép **LGPL-3.0** (Qt Company / Qt Project). Dùng dạng thư viện động, không sửa Qt; người dùng có thể thay thế thư viện Qt trong thư mục exe. Gói dùng: PySide6-Essentials.

## Thành phần đóng gói trong bộ cài `OCR-Nhat-setup.exe`

Bộ cài (exe CPU) chứa các thành phần sau. Mỗi thành phần theo giấy phép riêng; xem file LICENSE của dự án gốc.
- **Python** và thư viện chuẩn (Python Software Foundation License).
- **PyInstaller** (đóng gói exe; GPL-2.0-or-later với ngoại lệ cho phép đóng gói chương trình không phải GPL).
- **Thư viện CUDA/cuDNN của NVIDIA** (gói `nvidia-*` của onnxruntime-gpu, chỉ trong bản exe GPU): theo giấy phép NVIDIA riêng.
- **onnxruntime** (MIT), **OpenCV** (Apache-2.0), **pypdfium2** (Apache-2.0 / BSD-3-Clause), **python-docx** (MIT), **NumPy** (BSD-3-Clause), **Pillow** (MIT-CMU), **PyYAML**, **lxml**, **tqdm**, **networkx** (BSD).

Công cụ **Inno Setup** chỉ dùng để tạo bộ cài trong CI, không đóng gói vào bộ cài.

Các thư viện khác: NumPy, Pillow (giấy phép riêng của từng thư viện).
