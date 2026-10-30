# Tổng quan dự án OCR-Nhat (ngữ cảnh cho phiên làm việc)

File này tóm tắt dự án để nắm ngữ cảnh nhanh. Đọc file này trước khi khám phá mã nguồn;
không quét toàn bộ thư mục gốc khi đã có tổng quan này. Chi tiết quy ước và ghi chép kỹ thuật nằm trong `CLAUDE.md`,
hướng dẫn dùng nằm trong `README.md`.

## Mục tiêu
- Công cụ OCR file PDF scan và ảnh, **chỉ giữ tiếng Nhật**, xuất **.docx** (kèm .txt).
- Đoạn văn liền mạch, có tiêu đề và bảng thật. Bỏ tiếng Việt, tiếng Anh và furigana (mặc định).
- Chạy offline, miễn phí, không cần GPU. Đóng gói Windows .exe.
- Chủ dự án: Nguyễn Thanh Quang. Repo: `miyagitaisuki/ocr_thanhquang`.

## Luồng xử lý
```
PDF/ảnh -> render trang (pypdfium2, 200 dpi) -> crop/upscale tùy chọn
        -> engine OCR (NDLOCR-Lite, ONNX, CPU)  -> Page (Block -> Line, tọa độ pixel)
        -> layout.build_page()                   -> Para | Table
        -> docx_out (Word) / txt  [+ review.html, _suspect.txt tùy chọn]
```

## Bản đồ mã nguồn (`src/ocrnhat`)
| File | Vai trò |
|---|---|
| `model.py` | `Line`, `Block`, `Page`: cấu trúc trung gian chung cho mọi engine. |
| `engines/base.py` | Giao diện `OcrEngine`. Thuộc tính `version` là khóa cache. |
| `engines/__init__.py` | Đăng ký engine, `resolve("auto")`, `create()`. |
| `engines/ndlocr.py` | Bọc NDLOCR-Lite, đọc XML trang và ánh xạ loại khối (表組, ルビ, 柱, ノンブル…). |
| `engines/chandra.py` | Engine Chandra 2 (tùy chọn, cần GPU, không trong exe): `parse_chandra_html` (HTML -> Page, có test) + `ChandraEngine` gọi `chandra-ocr` (HF cục bộ, hoặc vLLM). Giấy phép: xem NOTICE.md. |
| `pipeline.py` | `process_file`: OCR song song (ThreadPool, cửa sổ trượt, giữ thứ tự trang), cache, gọi layout, ghi file. |
| `layout.py` | Lõi dựng văn bản: lọc tiếng Nhật, bỏ furigana, gộp đoạn (ngắt theo khoảng trống dọc bất thường so với khoảng thông thường của khối), nhận tiêu đề (dòng ngắn đứng riêng, kể cả cùng cỡ chữ), dò đường kẻ bảng (OpenCV), ô gộp, nhận dạng lại ô vượt kẻ, sửa số khoanh tròn, ruby. |
| `docx_out.py` | Xuất Word (font Yu Mincho, Heading, bảng, ruby) và txt. |
| `cache.py` | Cache kết quả OCR theo hash file, dpi, crop/upscale, engine và version. Lưu ở `<out>/.cache`. |
| `review.py` | `--review`: HTML đối chiếu ảnh trang với text, tô đỏ dòng độ tin cậy thấp. |
| `suspect.py` | `--suspect` (thử nghiệm, tắt mặc định): BERT tiếng Nhật đánh dấu ký tự nghi ngờ, không sửa văn bản. |
| `gpu.py` | Dò GPU NVIDIA, chọn thiết bị cho NDLOCR (cuda chỉ khi onnxruntime có CUDA provider). |
| `cli.py` | Dòng lệnh `ocrnhat`. |
| `gui.py` | Giao diện Tkinter, kéo-thả file. |

Mã NDLOCR-Lite **không nằm trong repo**: `python scripts/fetch_ndlocr.py` tải đúng commit đã ghim vào `vendor/ndlocr-lite` (đã gitignore). Ghi công trong `NOTICE.md`.

## Thư mục và file khác
- `scripts/`: `fetch_ndlocr.py` (tải engine), `smoke_test.py` (OCR ảnh mẫu, dựng bảng), `compare_engines.py` (đối chiếu với YomiToku, chỉ để so sánh, không đóng gói vì giấy phép CC BY-NC-SA).
- `tests/`: pytest (`test_layout`, `test_output`, `test_pipeline`, `test_followups`, `test_suspect`).
- `tests/data/pretest_sample.pdf`: sổ tay tiếng Nhật thương mại 4 trang, file mẫu chính cho các test và đo độ chính xác từ nay.
- `.github/workflows/`: `test.yml` (mỗi push/PR), `build-exe.yml` (exe CPU, kèm bộ cài `OCR-Nhat-setup.exe` bằng Inno Setup từ `installer/OCR-Nhat.iss`), `build-exe-gpu.yml` (exe GPU: NDLOCR trên CUDA + Chandra có sẵn, torch CUDA; chạy thủ công; trọng số Chandra không đóng vào, người dùng tải lần đầu).
- `requirements.txt`: nguồn duy nhất của dependency. `pyproject.toml` đọc từ đó. Extra: `test`, `suspect`.
- `.claude/agents/`: agent `developer` và `code-reviewer`.
- `run_gui.py`: mở giao diện.

## Trạng thái hiện tại
- Nhánh làm việc: `claude/adoring-cerf-t2dmxp`.
- Đã làm: rà soát ruby (`--ruby`), cache, OCR song song, nhận dạng lại ô, đối chiếu YomiToku (script), dò chữ nghi ngờ (thử nghiệm), GUI kiểu PDFsam.
- Chandra: đã nối vào `--engine chandra` và GUI; `auto` chọn khi có NVIDIA đủ VRAM, đã cài `ocrnhat[chandra]` và torch có CUDA; AMD/Intel về NDLOCR. Ô Thiết bị = CPU ép Chandra chạy CPU. CHƯA chạy model thật (môi trường không có GPU), chưa biết chất lượng đầu ra.
- Chưa làm: GPU chạy thật trong exe (exe CI dùng onnxruntime CPU).
- GUI đã có đủ `--review`, `--crop`, `--upscale`, `--ruby`, `--kana-reader`.

## Lỗi và giới hạn đã biết
- Số khoanh tròn ①②③ trong cột đầu bảng đọc thành `(1`, `19`, `O1`. `layout._fix_circled` chỉ vá một phần.
- Bảng dày (trang 10 sổ tay mẫu): NDLOCR bỏ sót nhiều dòng. Nhận dạng lại ô giúp một phần. Còn nhầm chữ (稟議書→實識書, 私見→私覚).
- Furigana có thể còn sót trong ô bảng. Ruby chưa hỗ trợ trong ô bảng và chữ dọc.
- Chữ dọc xuất thành chiều ngang trong Word.
- Ảnh chụp chữ nhỏ cần `--crop` và `--upscale` (ví dụ trang 38).
- Dòng lệnh Windows dùng cp1252: luôn `reconfigure(encoding="utf-8")` khi in tiếng Nhật/Việt.

## Lệnh thường dùng
```bash
pip install -r requirements.txt && pip install -e ".[test]"
python scripts/fetch_ndlocr.py
pytest -q
python scripts/smoke_test.py
ocrnhat file.pdf -o out --pages 1-5
```
Build exe chỉ chạy được trên GitHub Actions (workflow_dispatch). Không build từ Linux.

## Quy tắc làm việc
- Đọc file này trước; chỉ mở file cụ thể khi cần, không quét toàn bộ thư mục gốc.
- Sửa mã: đọc `CLAUDE.md` để biết quy ước (ngôn ngữ comment, cấu trúc engine, cache).
- Thêm engine: kế thừa `OcrEngine`, thêm tên vào `_NAMES` và nhánh vào `_cls`.
- Chỉ thêm dependency mà đường chạy thật sự import.
- Chỉ commit và push khi được yêu cầu.
