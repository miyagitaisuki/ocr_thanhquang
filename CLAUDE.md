# Dự án OCR-Nhat (project "ocr")

Phần mềm Windows (.exe) OCR file PDF scan và ảnh, **chỉ lấy tiếng Nhật**, xuất **Word (.docx)** (+ .txt). Miễn phí, offline, không cần GPU.
Chủ dự án: Nguyễn Thanh Quang. Repo: miyagitaisuki/ocr_thanhquang.

## Yêu cầu của chủ dự án
- Chỉ giữ tiếng Nhật (bỏ tiếng Việt/Anh, bỏ furigana).
- Đầu ra là .docx có **khối văn bản liền mạch** (gộp dòng thành đoạn), tiêu đề và bảng thật.
- Ưu tiên exe gọn, nhanh; chấp nhận tự dựng bảng thay vì dùng engine nặng.
- Ưu tiên công cụ miễn phí. Ưu tiên giấy phép thoáng (NDLOCR-Lite là CC BY 4.0).

## Kiến trúc (src/ocrnhat)
- `model.py`: Page/Block/Line chung cho mọi engine. `engines/`: `base.py` (giao diện `OcrEngine`), `__init__.py` (đăng ký, `--engine`), `ndlocr.py`, `chandra.py` (PLACEHOLDER, chưa cài đặt; ghi sẵn các bước làm). Thêm engine: kế thừa `OcrEngine`, thêm vào `_LOADERS` và `_engine_version` (pipeline.py).
- `engines/ndlocr.py`: bọc NDLOCR-Lite (ONNX), đọc XML trang -> Block/Line (text, table 表組, ruby ルビ, 柱, ノンブル). Commit ghim: xem `scripts/fetch_ndlocr.py`.
- `layout.py`: lọc tiếng Nhật, bỏ furigana, gộp đoạn, nhận tiêu đề, dựng bảng từ đường kẻ (OpenCV) kèm ô gộp; dự phòng theo cụm tọa độ.
- `docx_out.py`: xuất Word (font Yu Mincho, Heading, bảng) và txt.
- `pipeline.py` / `cli.py` / `gui.py`: PDF/ảnh -> kết quả; dòng lệnh; giao diện Tkinter.
- Mã NDLOCR-Lite KHÔNG nằm trong repo: tải bằng `python scripts/fetch_ndlocr.py` vào `vendor/ndlocr-lite` (đã gitignore). Ghi công trong `NOTICE.md`.

## Build / kiểm tra
- CI: `.github/workflows/build-exe.yml` (windows-latest, PyInstaller onedir). Có smoke test và bước chạy thử chính file exe. Chạy bằng workflow_dispatch.
- Cục bộ: `pip install -r requirements.txt && pip install -e .` rồi `ocrnhat file.pdf -o out --pages 1-5`.
- Không build được exe từ Linux; dùng GitHub Actions.

## Lưu ý kỹ thuật đã gặp
- Console Windows dùng cp1252: luôn `reconfigure(encoding="utf-8")` khi in tiếng Nhật/Việt.
- `gh workflow run` dùng GraphQL bị chặn: dùng `gh api -X POST repos/.../actions/workflows/build-exe.yml/dispatches -f ref=main`.
- Engine có thể đọc chữ hai ô liền kề thành một dòng xuyên qua đường kẻ; bảng thử tổng hợp trong smoke test chỉ kiểm tra đường ống, không kiểm tra nội dung ô.

## Kết quả thử trên sổ tay mẫu (136 trang)
~4–6 giây/trang CPU; 19 bảng; 11 trang rỗng (trang thuần Việt/trống). Lỗi còn lại: nhận sai chữ (私見→私覚), vài furigana sót trong ô bảng, thứ tự dòng đôi khi đảo, chữ dọc xuất theo chiều ngang.

## Hướng phát triển (đã bàn, chưa làm)
1. ~~Chế độ rà soát~~ ĐÃ LÀM: `ocrnhat --review [--conf 0.8]` -> `*_review.html` (`review.py`); chưa có trong GUI.
2. Xuất ruby furigana thật của Word thay vì bỏ.
3. Cache theo hash ĐÃ LÀM (`cache.py`, thư mục `<out>/.cache`, tắt bằng `--no-cache`). Chạy song song: chưa làm.
4. Tách dòng bị nối xuyên ô bảng bằng nhận dạng lại từng ô.
5. Tùy chọn engine thứ hai (YomiToku, chỉ phi thương mại) để đối chiếu.
6. Dò chữ sai bằng BERT/LLM (chỉ đánh dấu để duyệt, không tự sửa).
