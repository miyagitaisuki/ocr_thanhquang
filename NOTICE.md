# Ghi công / giấy phép bên thứ ba

Ứng dụng này dùng **NDLOCR-Lite** của Thư viện Quốc hội Nhật Bản (NDL Lab),
phát hành theo giấy phép **CC BY 4.0** — https://github.com/ndl-lab/ndlocr-lite
(mã nguồn và mô hình được tải về lúc build, đúng commit ghim trong `scripts/fetch_ndlocr.py`;
không sao chép vào repo này). Mô hình phát hiện bố cục dùng backbone DINOv3 chưng cất, xem
giấy phép DINOv3 trong repo NDLOCR-Lite.

## Chandra OCR 2 (engine tùy chọn, `--engine chandra`)

Engine này dùng **Chandra OCR 2** của Datalab (`datalab-to/chandra-ocr-2`, gói `chandra-ocr`).
- **Mã nguồn** gói `chandra-ocr`: Apache-2.0 — https://github.com/datalab-to/chandra
- **Trọng số mô hình** theo giấy phép OpenRAIL-M sửa đổi (file LICENSE trên Hugging Face). Điều khoản chính:
  - Không dùng cho mục đích thương mại khi doanh thu gộp năm trước vượt 2 triệu USD, hoặc tổng vốn/nợ đã huy động vượt 2 triệu USD. Không áp dụng cho sử dụng cá nhân hoặc nghiên cứu.
  - Không dùng để cung cấp sản phẩm hoặc dịch vụ cạnh tranh với sản phẩm của Datalab.
  - Phải ghi công Datalab, đưa link tới mô hình gốc, kèm bản giấy phép và nêu rõ thay đổi nếu có.
  - Dẫn xuất (lượng tử hóa, tinh chỉnh) phải giữ cùng giấy phép.
- Trọng số **không được đóng vào exe và không nằm trong repo**: người dùng tự cài `pip install ".[chandra]"`, mô hình tải về từ Hugging Face.
- Nếu vượt ngưỡng hoặc cần dùng thương mại rộng hơn, phải xin giấy phép thương mại từ Datalab.
- Gói GPU (tải khi người dùng bấm nút trong GUI, không đóng vào exe) gồm torch và torchvision (BSD-3, PyTorch), `chandra-ocr` (Apache-2.0) và các phụ thuộc. Trọng số Chandra vẫn tải riêng từ Hugging Face khi người dùng bấm, và người dùng phải chấp nhận điều khoản OpenRAIL-M của trọng số. Gói GPU có thể kèm thư viện CUDA của NVIDIA theo giấy phép của NVIDIA.
- **Phạm vi sử dụng hiện tại: chỉ cá nhân chủ dự án, không phân phối.** Theo điều khoản, sử dụng cá nhân/nghiên cứu được miễn ngưỡng thương mại. Nếu chia sẻ exe, đưa cho người khác, hoặc dùng cho mục đích có doanh thu, phải xem lại điều khoản trên trước.

## PaddleOCR (engine `paddle`: tiếng Anh và tiếng Trung)

Dùng mô hình PP-OCRv4 (dò dòng `ch_PP-OCRv4_det_infer`, nhận dạng `ch_PP-OCRv4_rec_infer`) và từ điển `ppocr_keys_v1.txt` của **PaddleOCR** (PaddlePaddle), giấy phép **Apache-2.0**: https://github.com/PaddlePaddle/PaddleOCR
- File ONNX lấy từ Hugging Face `SWHL/RapidOCR` (đóng gói lại, Apache-2.0). Từ điển lấy từ mã nguồn PaddleOCR (nhánh release/2.7).
- Model không đóng vào exe; `scripts/fetch_models.py` tải về `models/` và kiểm SHA-256.

## VietOCR (engine `ocr_vi`: tiếng Việt)

Dùng kiến trúc và trọng số `vgg_seq2seq.pth` của **VietOCR** (pbcquoc/vietocr, phiên bản 0.3.13), giấy phép **Apache-2.0**, xuất sang ONNX int8 (`assets/vi-ocr/`, bằng `scripts/export_vi.py`).
- Chủ dự án xác nhận Apache-2.0 cho gói này. Ghi chú: file LICENSE trong gói ghi Apache-2.0, còn metadata ghi MIT.
- Các file ONNX và từ điển được tải trong GUI (tab AI powered) từ chính repo này, kiểm SHA-256.

## PySide6 (giao diện Qt, `OCR-Nhat-Qt.exe`)

**PySide6** (Qt for Python) theo giấy phép **LGPL-3.0** (Qt Company / Qt Project). Dùng dạng thư viện động, không sửa Qt; người dùng có thể thay thế thư viện Qt trong thư mục exe. Gói dùng: PySide6-Essentials.

## Thành phần đóng gói trong bộ cài `OCR-Nhat-setup.exe`

Bộ cài (exe CPU) chứa các thành phần sau. Mỗi thành phần theo giấy phép riêng; xem file LICENSE của dự án gốc.
- **Python** và thư viện chuẩn, gồm Tkinter (Python Software Foundation License).
- **PyInstaller** (đóng gói exe; GPL-2.0-or-later với ngoại lệ cho phép đóng gói chương trình không phải GPL).
- **pip** (MIT): dùng để cài gói GPU tùy chọn ngay trong app.
- **onnxruntime** (MIT), **OpenCV** (Apache-2.0), **pypdfium2** (Apache-2.0 / BSD-3-Clause), **python-docx** (MIT), **NumPy** (BSD-3-Clause), **Pillow** (MIT-CMU), **tkinterdnd2** (MIT), **PyYAML**, **lxml**, **tqdm**, **networkx** (BSD).

Công cụ **Inno Setup** chỉ dùng để tạo bộ cài trong CI, không đóng gói vào bộ cài.

Các thư viện khác: NumPy, Pillow (giấy phép riêng của từng thư viện).
