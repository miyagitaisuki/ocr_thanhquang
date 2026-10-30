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
| `engines/paddle.py` | Engine `paddle` (tiếng Anh và tiếng Trung, dùng chung): PP-OCRv4 det + rec ONNX, CTC. Model: `scripts/fetch_models.py`. |
| `engines/viet.py` | Engine `ocr_vi` (tiếng Việt): dò dòng PP-OCRv4 + VietOCR (seq2seq, ONNX int8, giải mã greedy). Model: `scripts/export_vi.py`. |
| `engines/ocr_onnx.py` | Thành phần chung ONNX: hậu xử lý DB bằng OpenCV (không pyclipper), sắp thứ tự đọc, nắn phối cảnh, CTC, ghép Page. |
| `engines/models.py` | Tìm và tải model: `OCRNHAT_MODELS`, `models/` cạnh exe/gốc repo, `%LOCALAPPDATA%\OCR-Nhat\models`. `download_paddle()` tải PaddleOCR có báo tiến độ, kiểm SHA-256 (GUI và `scripts/fetch_models.py` dùng chung). |
| `engines/chandra.py` | Engine Chandra 2 (tùy chọn, cần GPU, không trong exe): `parse_chandra_html` (HTML -> Page, có test) + `ChandraEngine` gọi `chandra-ocr` (HF cục bộ, hoặc vLLM). Giấy phép: xem NOTICE.md. |
| `pipeline.py` | `process_file`: OCR song song (ThreadPool, cửa sổ trượt, giữ thứ tự trang), cache, gọi layout, ghi file. |
| `layout.py` | Lõi dựng văn bản: lọc tiếng Nhật, bỏ furigana, gộp đoạn (ngắt theo khoảng trống dọc bất thường so với khoảng thông thường của khối), nhận tiêu đề (dòng ngắn đứng riêng, kể cả cùng cỡ chữ), dò đường kẻ bảng (OpenCV), ô gộp, nhận dạng lại ô vượt kẻ, sửa số khoanh tròn, ruby. |
| `docx_out.py` | Xuất Word (font Yu Mincho, Heading, bảng, ruby) và txt. |
| `cache.py` | Cache kết quả OCR theo hash file, dpi, crop/upscale, engine và version. Lưu ở `<out>/.cache`. |
| `review.py` | `--review`: HTML đối chiếu ảnh trang với text, tô đỏ dòng độ tin cậy thấp. |
| `suspect.py` | `--suspect` (thử nghiệm, tắt mặc định): BERT tiếng Nhật đánh dấu ký tự nghi ngờ, không sửa văn bản. |
| `gpupack.py` | Gói GPU tùy chọn: chọn torch cu126 + torchvision từ chỉ mục PyTorch, cài Chandra bằng pip (có sẵn trong exe) vào `%LOCALAPPDATA%\OCR-Nhat\gpu`; `activate()` đưa vào đường dẫn import lúc khởi động. |
| `gpu.py` | Dò GPU NVIDIA, chọn thiết bị cho NDLOCR (cuda chỉ khi onnxruntime có CUDA provider). |
| `cli.py` | Dòng lệnh `ocrnhat`. |
| `gui.py` | Giao diện Tkinter, kéo-thả file. |

Mã NDLOCR-Lite **không nằm trong repo**: `python scripts/fetch_ndlocr.py` tải đúng commit đã ghim vào `vendor/ndlocr-lite` (đã gitignore). Ghi công trong `NOTICE.md`.

## Thư mục và file khác
- `scripts/`: `fetch_ndlocr.py` (tải engine), `fetch_models.py` (model PaddleOCR, kiểm SHA-256), `export_vi.py` (VietOCR sang ONNX int8, cần torch), `smoke_test.py` (OCR ảnh mẫu, dựng bảng), `compare_engines.py` (đối chiếu với YomiToku, chỉ để so sánh, không đóng gói vì giấy phép CC BY-NC-SA).
- `tests/`: pytest (`test_layout`, `test_output`, `test_pipeline`, `test_followups`, `test_suspect`, `test_engines_lang` không cần model, `test_engines_models` chạy khi có `models/`).
- `tests/data/pretest_sample.pdf`: sổ tay tiếng Nhật thương mại 4 trang, file mẫu chính cho các test và đo độ chính xác từ nay.
- `.github/workflows/`: `test.yml` (mỗi push/PR), `build-exe.yml` (exe CPU, kèm bộ cài `OCR-Nhat-setup.exe` bằng Inno Setup từ `installer/OCR-Nhat.iss`), `build-exe-gpu.yml` (exe GPU: onnxruntime-gpu; chạy thủ công). Ô Thiết bị chỉ có "GPU (NVIDIA)" khi onnxruntime có CUDA, tức bản GPU. Gói GPU tùy chọn chỉ tăng tốc Chandra; NDLOCR trong bản CPU vẫn chạy CPU. Torch CUDA và Chandra KHÔNG nằm trong exe: `gpupack.py` tải về khi người dùng bấm "Cài gói GPU + Chandra".
- `requirements.txt`: nguồn duy nhất của dependency. `pyproject.toml` đọc từ đó. Extra: `test`, `suspect`.
- `.claude/agents/`: agent `developer` và `code-reviewer`.
- `run_gui.py`: mở giao diện.

## Trạng thái hiện tại
- Nhánh làm việc: `claude/adoring-cerf-t2dmxp`.
- Đã làm: rà soát ruby (`--ruby`), cache, OCR song song, nhận dạng lại ô, đối chiếu YomiToku (script), dò chữ nghi ngờ (thử nghiệm), GUI kiểu PDFsam.
- GUI: thanh đầu có Chạy OCR (xanh lá), Dừng, tiến trình, ước lượng thời gian và trạng thái phần cứng. Bốn tab: Tài liệu (trạng thái từng file, xóa mục), Xử lý OCR (mẫu tài liệu, Nâng cao thu gọn, Engine AI có thanh tiến trình tải), Rà soát, Kết quả (danh sách, mở file, xem trước trang). Phím tắt: Ctrl+O, Ctrl+R/F5, Esc, Delete. Menu Hiển thị: giao diện tối/sáng và cỡ chữ (áp dụng sau khi khởi động lại). Nhật ký lỗi: `%LOCALAPPDATA%\OCR-Nhat\logs\app.log`. Module `textview.py` tách chữ theo trang cho khung xem trước.
- Lỗi "pip thoát với mã 2" khi cài gói GPU: bản --windowed có stdout = None; đầu ra pip nay ghi vào `%LOCALAPPDATA%\OCR-Nhat\gpu\install.log`.
- Gộp trang (mặc định): `layout.merge_pages` nối đoạn bị cắt giữa trang, bỏ trang trống, không ngắt trang trong Word. `--keep-pages` hoặc ô "Gộp trang" = Giữ nguyên trang để có một trang Word cho mỗi trang gốc.
- Engine theo ngôn ngữ: "Tiếng Nhật – NDLOCR/Chandra", "Tiếng Anh/Trung – PaddleOCR" (`paddle`), "Tiếng Việt – VietOCR" (`ocr_vi`). Chọn engine chưa có model sẽ báo thiếu gì. Engine AI nằm ở tab "AI powered".
- Ngôn ngữ: `--lang ja` (mặc định), `en`, `zh`, `vi`, `all` (chỉ Chandra). Mỗi ngôn ngữ chỉ giữ chữ của ngôn ngữ đó (`layout._script_keep`). `auto` chọn engine theo ngôn ngữ: en/zh -> paddle, vi -> ocr_vi. Ô Ngôn ngữ trong GUI chỉ liệt kê ngôn ngữ mà engine đang chọn hỗ trợ. Với en/vi, nối dòng bằng khoảng trắng và kết câu bằng `.!?:;`. Heuristic ngắt đoạn vẫn thiên về tiếng Nhật (dấu 。, hạt).
- Chandra: GUI có ô xác nhận OpenRAIL-M và nút "Tải model Chandra" (tải trọng số từ Hugging Face vào cache, chạy nền). Đã nối vào `--engine chandra` và GUI; `auto` chọn khi có NVIDIA đủ VRAM, đã cài `ocrnhat[chandra]` và torch có CUDA; AMD/Intel về NDLOCR. Ô Thiết bị = CPU ép Chandra chạy CPU. Batch: 6 GB -> 4 trang, từ 8 GB -> 8 trang (chỉ Chandra; một luồng OCR). CHƯA chạy model thật (môi trường không có GPU), chưa biết chất lượng đầu ra.
- PaddleOCR + VietOCR (nhánh `claude/ocr-vi-engine`): đã chạy thật trên mẫu tổng hợp (tiếng Anh, Việt, Trung) qua CLI; test model thật chạy khi có `models/`. Chưa kiểm trên PDF scan thật, chưa đo tốc độ trên máy người dùng.
- Chưa làm: GPU chạy thật trong exe (exe CI dùng onnxruntime CPU). Model PaddleOCR/VietOCR KHÔNG đóng vào exe. Tab "AI powered" có nút "Tải model OCR (PaddleOCR)" (thanh % và spinner; lưu vào `%LOCALAPPDATA%\OCR-Nhat\models` khi chạy exe). VietOCR không tải được từ GUI: chạy `scripts/export_vi.py`.
- GUI: nút chức năng là `GradientButton` (gradient dọc, `gui.py`). Menu Hiển thị có "Độ trong suốt cửa sổ" (100–80%, lưu trong settings.json, áp dụng ngay). Trong suốt chỉ áp dụng cho cả cửa sổ; không điều khiển được taskbar của Windows.
- Đầu ra: mặc định ghi cạnh file gốc (CLI `-o` / ô "Thư mục lưu" để trống = thư mục gốc). Tên file: `OCR_<tên không dấu>_<trang đầu>_<trang cuối>.docx/.txt` (`pipeline.output_stem`, `ascii_name`). GUI có nút "Tìm nhanh" bên cạnh Dừng: mở thư mục của kết quả đang chọn, kết quả gần nhất, hoặc thư mục lưu. Cache `.cache` nằm trong thư mục đầu ra (có thể là thư mục gốc).
- GUI đã có đủ `--review`, `--crop`, `--upscale`, `--ruby`, `--kana-reader`.

## Lỗi và giới hạn đã biết
- PaddleOCR/VietOCR: engine có thể bỏ khoảng trắng trong câu tiếng Anh (ví dụ "agreementis"); chữ dọc chưa hỗ trợ; dò dòng dùng cạnh dài tối đa 960 px nên ảnh rất lớn có thể mất chữ nhỏ.
- VietOCR: giấy phép trong gói `vietocr` 0.3.13 (file LICENSE ghi Apache-2.0, metadata ghi MIT) và giấy phép trọng số `vgg_seq2seq.pth` CHƯA được xác minh. Cần xác minh trước khi phân phối exe.
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
python scripts/fetch_models.py            # PaddleOCR (tiếng Anh, Trung) vào models/
python scripts/export_vi.py               # VietOCR (tiếng Việt), cần torch + vietocr
ocrnhat file.pdf -o out --lang en         # hoặc zh, vi
```
Build exe chỉ chạy được trên GitHub Actions (workflow_dispatch). Không build từ Linux.

## Quy tắc làm việc
- Đọc file này trước; chỉ mở file cụ thể khi cần, không quét toàn bộ thư mục gốc.
- Sửa mã: đọc `CLAUDE.md` để biết quy ước (ngôn ngữ comment, cấu trúc engine, cache).
- Thêm engine: kế thừa `OcrEngine`, thêm tên vào `_NAMES` và nhánh vào `_cls`.
- Chỉ thêm dependency mà đường chạy thật sự import.
- Chỉ commit và push khi được yêu cầu.
