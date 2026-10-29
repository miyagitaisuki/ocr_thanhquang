# OCR-Nhat

OCR file PDF (bản scan) và ảnh, **chỉ lấy tiếng Nhật**, xuất **Word (.docx)** có đoạn văn liền mạch,
tiêu đề và bảng thật. Chạy offline, miễn phí, không cần GPU.

Engine: [NDLOCR-Lite](https://github.com/ndl-lab/ndlocr-lite) (Thư viện Quốc hội Nhật Bản, CC BY 4.0).
Phần dựng đoạn/bảng/loại furigana và xuất Word là của dự án này (xem `src/ocrnhat/layout.py`).

- Bỏ tiếng Việt / tiếng Anh, bỏ furigana.
- Gộp các dòng ngắt theo trang thành đoạn văn; nhận tiêu đề.
- Bảng: dò đường kẻ trên ảnh để dựng lưới ô (kể cả ô gộp), dự phòng theo tọa độ nếu bảng không có đường kẻ.
- Kết quả: `<tên>.docx` (+ `<tên>.txt` để nạp vào công cụ khác). Mỗi trang gốc có dòng `【原本 p.N】`.

## Dùng bản exe
Tab **Actions → Build Windows exe → Run workflow**, tải artifact `OCR-Nhat-windows`, giải nén,
chạy `OCR-Nhat.exe` (giao diện) hoặc `ocrnhat-cli.exe` (dòng lệnh). Model nằm sẵn trong gói, chạy offline.

## Dùng từ Python
```
python scripts/fetch_ndlocr.py        # tải NDLOCR-Lite vào vendor/
pip install -r requirements.txt
pip install -e .
ocrnhat file.pdf -o ketqua --pages 1-10
python -m ocrnhat                     # mở giao diện
```

## Giới hạn đã biết
- Furigana đọc sai thành chữ khác (hiếm) hoặc nằm lẫn trong ô bảng có thể còn sót.
- Bảng không có đường kẻ chỉ dựng được gần đúng theo cột.
- Chữ dọc được đọc đúng nội dung nhưng xuất ra Word theo chiều ngang.
- Lỗi nhận dạng chữ (ví dụ 私見 → 私覚) vẫn có; nên rà soát kết quả.
