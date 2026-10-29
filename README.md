# OCR-Nhat

OCR file PDF (bản scan) và ảnh, **chỉ lấy tiếng Nhật**, chạy offline, miễn phí.
Engine: RapidOCR (PP-OCR, model tiếng Nhật) + pypdfium2 + OpenCV.

- Bỏ tiếng Việt / tiếng Anh (lọc theo tỉ lệ ký tự Nhật).
- Bỏ furigana (nhận diện bằng kích thước chữ).
- Sắp xếp thứ tự đọc từ trên xuống, cùng hàng thì trái sang phải.
- Kết quả: `<tên>.txt` (có dòng `=== Trang N ===`) và `<tên>.jsonl` (từng dòng kèm tọa độ, độ tin cậy) để nạp vào công cụ khác.

## Dùng bản exe
Tab **Actions → Build Windows exe → Run workflow**, tải artifact `OCR-Nhat-windows`,
giải nén, chạy `OCR-Nhat.exe`. Model OCR (~31 MB) đã nằm trong gói, chạy hoàn toàn offline.

## Dùng từ Python
```
pip install -r requirements.txt
pip install -e .
ocrnhat file.pdf -o ketqua --pages 1-10
python -m ocrnhat          # mở giao diện
```

## Giới hạn đã biết
- Dòng lẫn Nhật–Việt trong cùng một dòng có thể bị bỏ hoặc giữ nguyên cả dòng.
- Ảnh mờ hoặc chữ rất nhỏ làm giảm chất lượng; nên rà lại kết quả.
