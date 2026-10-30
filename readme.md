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
| `engines/viet.py` | Engine `ocr_vi` (tiếng Việt): dò dòng PP-OCRv4 + VietOCR (seq2seq, ONNX int8, giải mã greedy). Model: `assets/vi-ocr/` (tải trong GUI). |
| `engines/ocr_onnx.py` | Thành phần chung ONNX: hậu xử lý DB bằng OpenCV (không pyclipper), sắp thứ tự đọc, nắn phối cảnh, CTC, ghép Page. |
| `engines/models.py` | Tìm và tải model: `OCRNHAT_MODELS`, `models/` cạnh exe/gốc repo, `%LOCALAPPDATA%\OCR-Nhat\models`. `download_paddle()` tải PaddleOCR có báo tiến độ, kiểm SHA-256 (GUI và `scripts/fetch_models.py` dùng chung). |
| `engines/chandra.py` | Engine Chandra 2 (tùy chọn, cần GPU, không trong exe): `parse_chandra_html` (HTML -> Page, có test) + `ChandraEngine` gọi `chandra-ocr` (HF cục bộ, hoặc vLLM). Giấy phép: xem NOTICE.md. |
| `pipeline.py` | `process_file`: OCR song song (ThreadPool, cửa sổ trượt, giữ thứ tự trang), cache, gọi layout, ghi file. |
| `layout.py` | Lõi dựng văn bản: lọc tiếng Nhật, bỏ furigana, gộp đoạn (ngắt theo khoảng trống dọc bất thường so với khoảng thông thường của khối), nhận tiêu đề (dòng ngắn đứng riêng, kể cả cùng cỡ chữ), dò đường kẻ bảng (OpenCV), ô gộp, nhận dạng lại ô vượt kẻ, sửa số khoanh tròn, ruby. |
| `docx_out.py` | Xuất Word (font Yu Mincho, Heading, bảng, ruby) và txt. |
| `cache.py` | Cache kết quả OCR theo hash file, dpi, crop/upscale, engine và version. Lưu ở `<out>/.cache`. |
| `review.py` | `--review`: HTML đối chiếu ảnh trang với text, tô đỏ dòng độ tin cậy thấp. |
| `pdf_ops.py` | Xoay trang, nén PDF và theo dõi thư mục (`watch_folder`, quét định kỳ, không dùng watchdog). |
| `pdf_extract.py` | Công cụ PDF: trích xuất trang và tách file (pypdf): cú pháp `2,5-7,12-`, file riêng cho mỗi nhóm, ghi đè, nén, bỏ bookmark, phiên bản PDF. Lệnh `ocrnhat-pdf`. Tab "Công cụ PDF" trong GUI. |
| `suspect.py` | `--suspect` (thử nghiệm, tắt mặc định): BERT tiếng Nhật đánh dấu ký tự nghi ngờ, không sửa văn bản. |
| `gpupack.py` | Gói GPU tùy chọn: chọn torch cu126 + torchvision từ chỉ mục PyTorch, cài Chandra bằng pip (có sẵn trong exe) vào `%LOCALAPPDATA%\OCR-Nhat\gpu`; `activate()` đưa vào đường dẫn import lúc khởi động. |
| `gpu.py` | Dò GPU NVIDIA, chọn thiết bị cho NDLOCR (cuda chỉ khi onnxruntime có CUDA provider). |
| `cli.py` | Dòng lệnh `ocrnhat`. |
| `gui.py` | Giao diện Tkinter: các tab, Công cụ PDF (danh sách thao tác bên trái), xem trước có Trước/Sau và giữ PDF đã mở, kéo-thả file. Đóng khi đang chạy: hỏi, dừng, chờ luồng nền xong rồi mới đóng. |
| `gui_qt.py` | Giao diện PySide6 (bước 2, thử nghiệm, `run_gui_qt.py`, extra `[qt]`): thanh bên 4 mục (OCR, Tách PDF, Ghép PDF, Công cụ khác). Mục OCR đầy đủ; ba mục PDF (`gui_qt_pdf.py`) đã có. Chưa đóng gói vào exe. |
| `gui_qt_pdf.py` | Ba mục Công cụ PDF của bản Qt: Tách PDF (trích xuất, tách file), Ghép PDF (ghép, xen kẽ, chèn trang lặp lại), Công cụ khác (xoay, nén, tự động theo thư mục). Danh sách kéo-thả sắp xếp được; chạy ở luồng nền, hủy giữa các file; nhớ tùy chọn trong `qt_pdf`. |
| `gui_qt_style.py` | Giao diện chung của bản Qt (tên hiển thị **OCR-Thanh Quang**): QSS sáng/tối, thẻ bo góc, nút xanh, nhãn trạng thái file (pill). Áp dụng qua menu Hiển thị. |
| `gui_qt_extra.py` | Phần còn thiếu của bản Qt (bước 4): bảng kết quả, xem trước trang (ảnh và chữ), Tìm nhanh, mục mô hình AI (tải PaddleOCR/VietOCR/Chandra, cài gói GPU, chạy nền), menu Hiển thị (sáng/tối, cỡ chữ, trong suốt; áp dụng ngay). |
| `ui_logic.py` | Nhãn, ánh xạ nhãn -> khóa và đọc tùy chọn OCR. Không import Tkinter (test được không cần cửa sổ; chuẩn bị cho bản giao diện mới). |
| `widgets.py` | Widget dùng chung: `GradientButton` (có tiêu điểm bàn phím: Tab, Enter, Space), `GradientNotebook`, `Tip`, `Spinner`, mèo tiến trình; `_sc()` đổi px theo DPI. |

Mã NDLOCR-Lite **không nằm trong repo**: `python scripts/fetch_ndlocr.py` tải đúng commit đã ghim vào `vendor/ndlocr-lite` (đã gitignore). Ghi công trong `NOTICE.md`.

## Thư mục và file khác
- `scripts/`: `fetch_ndlocr.py` (tải engine), `fetch_models.py` (model PaddleOCR, kiểm SHA-256), `export_vi.py` (tạo lại `assets/vi-ocr/` từ VietOCR gốc, cần torch), `smoke_test.py` (OCR ảnh mẫu, dựng bảng), `compare_engines.py` (đối chiếu với YomiToku, chỉ để so sánh, không đóng gói vì giấy phép CC BY-NC-SA).
- `tests/`: pytest (`test_pdf_extract` (PDF tạo trong test), `test_layout`, `test_output`, `test_pipeline`, `test_followups`, `test_suspect`, `test_engines_lang` không cần model, `test_engines_models` chạy khi có `models/`, `test_ui_logic` không cần tkinter, `test_gui_qt` cần PySide6 (bỏ qua nếu thiếu), `test_gui_options` cần tkinter nên bị bỏ qua khi thiếu).
- `tests/data/pretest_sample.pdf`: sổ tay tiếng Nhật thương mại 4 trang, file mẫu chính cho các test và đo độ chính xác từ nay.
- `.github/workflows/`: `qt-windows.yml` (mỗi push: test Qt trên Windows, `run_gui_qt.py --selftest`), `build-exe-qt.yml` (exe Qt `OCR-Nhat-Qt`, thử nghiệm, chạy thủ công), `test.yml` (mỗi push/PR), `build-exe.yml` (exe CPU, kèm bộ cài `OCR-Nhat-setup.exe` bằng Inno Setup từ `installer/OCR-Nhat.iss`), `build-exe-gpu.yml` (exe GPU: onnxruntime-gpu; chạy thủ công). Ô Thiết bị chỉ có "GPU (NVIDIA)" khi onnxruntime có CUDA, tức bản GPU. Gói GPU tùy chọn chỉ tăng tốc Chandra; NDLOCR trong bản CPU vẫn chạy CPU. Torch CUDA và Chandra KHÔNG nằm trong exe: `gpupack.py` tải về khi người dùng bấm "Cài gói GPU + Chandra".
- `requirements.txt`: nguồn duy nhất của dependency. `pyproject.toml` đọc từ đó. Extra: `test`, `suspect`.
- `.claude/agents/`: agent `developer` và `code-reviewer`.
- `run_gui.py`: mở giao diện.

## Trạng thái hiện tại
- Nhánh làm việc: `claude/adoring-cerf-t2dmxp`.
- Đã làm: rà soát ruby (`--ruby`), cache, OCR song song, nhận dạng lại ô, đối chiếu YomiToku (script), dò chữ nghi ngờ (thử nghiệm), GUI kiểu PDFsam.
- GUI: thanh đầu có Chạy OCR (xanh lá), Dừng, tiến trình, ước lượng thời gian và trạng thái phần cứng. Tab Công cụ PDF: thẻ "Tệp PDF" ở trên, các thao tác chọn ở danh sách bên trái (một thao tác hiện một lúc). Tab "Cơ bản" (mở đầu): thêm file, ngôn ngữ, thư mục lưu, Chạy. Các tab còn lại: Tài liệu (trạng thái từng file, xóa mục), Tùy chọn (mẫu tài liệu, Nâng cao thu gọn), AI powered (tải mô hình có thanh tiến trình), Kiểm tra, Kết quả (danh sách, mở file, xem trước trang), Công cụ PDF. Ô tùy chọn được lưu vào `settings.json` (mục `vars`) khi đóng và khi bấm Chạy. Trước khi chạy, công cụ thiếu model hoặc không đọc được ngôn ngữ đã chọn sẽ được báo rõ. Cỡ chữ, khoảng cách và kích thước theo DPI màn hình (`_sc`). Phím tắt: Ctrl+O, Ctrl+R/F5, Esc, Delete. Menu Hiển thị: giao diện tối/sáng và cỡ chữ (áp dụng sau khi khởi động lại). Nhật ký lỗi: `%LOCALAPPDATA%\OCR-Nhat\logs\app.log`. Module `textview.py` tách chữ theo trang cho khung xem trước.
- Lỗi "pip thoát với mã 2" khi cài gói GPU: bản --windowed có stdout = None; đầu ra pip nay ghi vào `%LOCALAPPDATA%\OCR-Nhat\gpu\install.log`.
- Công cụ PDF: ĐÃ CÓ "Trích xuất trang" (`pdf_extract.py`, pypdf >=6, BSD-3): tab "Công cụ PDF" có danh sách PDF (Thêm/Bỏ, số trang), ô "Trang cần lấy" (`2`, `5-23`, `2,5-7,12-`), "Một file riêng cho mỗi nhóm trang", "Thư mục lưu", "Phiên bản PDF" (1.4–1.7, mặc định 1.5), "Ghi đè", "Nén file đầu ra" (mặc định bật), "Bỏ bookmark" (mặc định tắt: giữ bookmark trỏ tới trang được chọn). Tên file: `<tên gốc>_trang_<nhóm>.pdf`; không ghi đè thì thêm ` (2)`. ĐÃ CÓ "Tách PDF" (`split_pdf`): theo số trang (mặc định 1), theo bookmark cấp 1 (trang trước bookmark đầu thành `_phan_dau`), theo dung lượng tối đa MB (gộp trang liên tiếp; ước lượng vì mỗi trang đo riêng, file thật thường nhỏ hơn). Lệnh `ocrnhat-pdf file.pdf --split pages|bookmark|size --every N --max-mb X`. ĐÃ CÓ "Ghép nhiều file" (`merge_pdfs`): ghép theo thứ tự danh sách (nút Lên/Xuống), mỗi file có bookmark cấp 1 mang tên file, tên kết quả mặc định `ghep.pdf`. Lệnh `ocrnhat-pdf a.pdf b.pdf --merge --name tong`. ĐÃ CÓ "Ghép xen kẽ" (`interleave_pdfs`: A1 B1 A2 B2…, file hết trang thì bỏ qua; tùy chọn đảo file thứ hai cho scan mặt sau) và "Chèn trang lặp lại" (`insert_repeated`: B1 A B2 A B3 A, hoặc trước mỗi trang; chọn trang chèn). Lệnh `--interleave [--reverse-second]`, `--insert [--insert-page N] [--insert-before]`. Bookmark không giữ trong hai chế độ này. ĐÃ CÓ "Xoay trang" (`rotate_pdf`, 90/180/270 độ, chọn trang), "Nén PDF" (`compress_pdf`: gộp đối tượng trùng, nén nội dung, tùy chọn nén lại ảnh JPEG bằng Pillow; ảnh trong suốt giữ nguyên) và "Tự động theo thư mục" (`watch_folder`: quét định kỳ, không dùng watchdog; file được xử lý khi kích thước ổn định; kết quả vào thư mục con `da_xu_ly`). Lệnh `--rotate`, `--compress [--image-quality N]`, `--watch THU_MUC`. Đã biết: với file mẫu, nén không mất dữ liệu gần như không giảm dung lượng (ảnh sẵn là JPEG); ghi lại ảnh ở chất lượng 30 giảm ~6%. Không còn nút khóa trong công cụ PDF.0). Tránh PyMuPDF (AGPL) và Ghostscript (AGPL) khi đóng gói. Chưa kiểm trên GUI thật: môi trường không có tkinter.
- Gộp trang (mặc định): `layout.merge_pages` nối đoạn bị cắt giữa trang, bỏ trang trống, không ngắt trang trong Word. `--keep-pages` hoặc ô "Gộp trang" = Giữ nguyên trang để có một trang Word cho mỗi trang gốc.
- Engine theo ngôn ngữ: "Tiếng Nhật – NDLOCR/Chandra", "Tiếng Anh/Trung – PaddleOCR" (`paddle`), "Tiếng Việt – VietOCR" (`ocr_vi`). Chọn engine chưa có model sẽ báo thiếu gì. Engine AI nằm ở tab "AI powered".
- Ngôn ngữ: `--lang ja` (mặc định), `en`, `zh`, `vi`, `all` (chỉ Chandra). Mỗi ngôn ngữ chỉ giữ chữ của ngôn ngữ đó (`layout._script_keep`). `auto` chọn engine theo ngôn ngữ: en/zh -> paddle, vi -> ocr_vi. Ô Ngôn ngữ trong GUI chỉ liệt kê ngôn ngữ mà engine đang chọn hỗ trợ. Với en/vi, nối dòng bằng khoảng trắng và kết câu bằng `.!?:;`. Heuristic ngắt đoạn vẫn thiên về tiếng Nhật (dấu 。, hạt).
- Chandra: GUI có ô xác nhận OpenRAIL-M và nút "Tải model Chandra" (tải trọng số từ Hugging Face vào cache, chạy nền). Đã nối vào `--engine chandra` và GUI; `auto` chọn khi có NVIDIA đủ VRAM, đã cài `ocrnhat[chandra]` và torch có CUDA; AMD/Intel về NDLOCR. Ô Thiết bị = CPU ép Chandra chạy CPU. Batch: 6 GB -> 4 trang, từ 8 GB -> 8 trang (chỉ Chandra; một luồng OCR). CHƯA chạy model thật (môi trường không có GPU), chưa biết chất lượng đầu ra.
- PaddleOCR + VietOCR (nhánh `claude/ocr-vi-engine`): đã chạy thật trên mẫu tổng hợp (tiếng Anh, Việt, Trung) qua CLI; test model thật chạy khi có `models/`. Chưa kiểm trên PDF scan thật, chưa đo tốc độ trên máy người dùng.
- Chưa làm: GPU chạy thật trong exe (exe CI dùng onnxruntime CPU). Model PaddleOCR/VietOCR KHÔNG đóng vào exe. Tab "AI powered" có nút "Tải mô hình OCR (PaddleOCR)" và "Tải mô hình tiếng Việt (VietOCR)" (thanh % và spinner; lưu vào `%LOCALAPPDATA%\OCR-Nhat\models` khi chạy exe). VietOCR không tải được từ GUI: chạy `scripts/export_vi.py`.
- GUI: thanh tab là `GradientNotebook` (tab bo tròn, gradient xanh như Chạy OCR; tab đang chọn đậm hơn). Nút chức năng là `GradientButton` (gradient dọc, `gui.py`). Menu Hiển thị có "Độ trong suốt cửa sổ" (100–80%, lưu trong settings.json, áp dụng ngay). Trong suốt chỉ áp dụng cho cả cửa sổ; không điều khiển được taskbar của Windows.
- Đầu ra: mặc định ghi cạnh file gốc (CLI `-o` / ô "Thư mục lưu kết quả" để trống = thư mục gốc). Tên file: `OCR_<tên không dấu>_<trang đầu>_<trang cuối>.docx/.txt` (`pipeline.output_stem`, `ascii_name`). GUI có nút "Tìm nhanh" bên cạnh Dừng: mở thư mục của kết quả đang chọn, kết quả gần nhất, hoặc thư mục lưu. Cache `.cache` nằm trong thư mục đầu ra (có thể là thư mục gốc).
- GUI đã có đủ `--review`, `--crop`, `--upscale`, `--ruby`, `--kana-reader`.
- Bước 2 (PySide6, thử nghiệm): `gui_qt.py` + `run_gui_qt.py`, cài bằng `pip install -e ".[qt]"`. Mục OCR đầy đủ (danh sách file kéo-thả, công cụ/ngôn ngữ/phần cứng, nâng cao, chạy/dừng, nhớ tùy chọn trong settings.json mục `qt_ocr`). Bước 3: ba mục PDF đầy đủ (`gui_qt_pdf.py`, nhớ tùy chọn trong `qt_pdf`), test PDF thật trong `tests/test_gui_qt_pdf.py`. Giao diện Qt theo hình mẫu (thanh bên trắng, nút "Bắt đầu xử lý" ở góc phải, hai cột: danh sách + xem trước bên trái, cấu hình bên phải). Tên hiển thị: OCR-Thanh Quang (tên gói `ocrnhat` và tên exe `OCR-Nhat-Qt` giữ nguyên). Bước 4 (Qt): đã có kết quả và xem trước, Tìm nhanh, tùy chọn Kiểm tra (ngưỡng, file so sánh), mô hình AI, menu Hiển thị (`gui_qt_extra.py`, `tests/test_gui_qt_extra.py`). Đã có thêm: chọn vùng cắt bằng chuột (khối Nâng cao, kéo trên ảnh trang mẫu) và rà soát trong cửa sổ xem trước (khung dòng, dòng nghi ngờ tô đỏ, bấm dòng để xem vị trí; `PageView` trong `gui_qt_extra.py`). `pipeline.process_file` trả thêm `page_lines`, `crop`, `upscale`, `conf_threshold` để vẽ khung. Chưa kiểm trên OCR thật vì môi trường không có NDLOCR. Bước 3: CI Windows cho Qt (`qt-windows.yml`) và exe Qt thử nghiệm (`build-exe-qt.yml`, tự kiểm `--selftest`); bản Tkinter vẫn là exe chính, chưa xóa. Chưa làm: chọn vùng cắt bằng chuột, rà soát trong cửa sổ xem trước, xem trước kết quả và tải model/gói GPU trong bản Qt (các phần này còn ở Tkinter). Đã test offscreen (`tests/test_gui_qt.py`, `tests/test_gui_qt_pdf.py`; cần libEGL trên Linux). Chưa đóng gói vào exe, chưa kiểm trên Windows. Bản Tkinter vẫn là mặc định (`run_gui.py`).
- Bước 1 chuyển sang PySide6 (đã thống nhất): ĐÃ LÀM trên Tkinter: tách nhãn/đọc tùy chọn sang `ui_logic.py`; đóng khi đang chạy có hỏi và chờ luồng nền dừng; Esc hỏi xác nhận; thêm/xóa khi đang OCR báo trên thanh trạng thái; file trùng được báo số lượng; "Chèn trang lặp lại" giữ lựa chọn file khi danh sách đổi; xem trước render đúng cỡ khung. CHƯA làm: lưu nhãn combobox trong settings.json vẫn là nhãn tiếng Việt (đổi nhãn thì giá trị cũ tự rơi về mặc định, chưa chuyển sang khóa); chưa kiểm GUI thật (môi trường không có tkinter).

## Lỗi và giới hạn đã biết
- PaddleOCR/VietOCR: engine có thể bỏ khoảng trắng trong câu tiếng Anh (ví dụ "agreementis"); chữ dọc chưa hỗ trợ; dò dòng dùng cạnh dài tối đa 960 px nên ảnh rất lớn có thể mất chữ nhỏ.
- VietOCR: đã xác nhận Apache-2.0 (chủ dự án). Metadata gói ghi MIT, không khớp file LICENSE; không ảnh hưởng việc phân phối.
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
python scripts/fetch_models.py            # PaddleOCR và VietOCR vào models/
ocrnhat-pdf file.pdf --pages 2,5-7,12- --separate -o out   # trích xuất trang (không cần OCR)
ocrnhat-pdf file.pdf --split size --max-mb 5 -o out          # tách file
ocrnhat file.pdf -o out --lang en         # hoặc zh, vi
```
Build exe chỉ chạy được trên GitHub Actions (workflow_dispatch). Không build từ Linux.

## Quy tắc làm việc
- Đọc file này trước; chỉ mở file cụ thể khi cần, không quét toàn bộ thư mục gốc.
- Sửa mã: đọc `CLAUDE.md` để biết quy ước (ngôn ngữ comment, cấu trúc engine, cache).
- Thêm engine: kế thừa `OcrEngine`, thêm tên vào `_NAMES` và nhánh vào `_cls`.
- Chỉ thêm dependency mà đường chạy thật sự import.
- Chỉ commit và push khi được yêu cầu.
