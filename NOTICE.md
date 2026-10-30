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
- Bản exe GPU (`OCR-Nhat-GPU`) đóng gói mã Chandra (Apache-2.0) và torch CUDA, KHÔNG đóng gói trọng số. Lần đầu dùng Chandra, phần mềm tải trọng số từ Hugging Face về máy người dùng; người dùng phải chấp nhận điều khoản OpenRAIL-M của trọng số.
- **Phạm vi sử dụng hiện tại: chỉ cá nhân chủ dự án, không phân phối.** Theo điều khoản, sử dụng cá nhân/nghiên cứu được miễn ngưỡng thương mại. Nếu chia sẻ exe, đưa cho người khác, hoặc dùng cho mục đích có doanh thu, phải xem lại điều khoản trên trước.

Các thư viện khác: onnxruntime, OpenCV, pypdfium2, python-docx, NumPy, Pillow (giấy phép riêng của từng thư viện).
