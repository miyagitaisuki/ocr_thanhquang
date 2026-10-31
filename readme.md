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
| `vi_text.py` | Hậu xử lý engine `ocr_vi` (chỉ `--lang vi`, tắt bằng `--no-vi-fix`): bỏ nhiễu dấu mộc (chữ thường ≤3 ký tự không phải âm tiết, dãy số ≥5 chữ số), sửa dấu theo tần suất trong tài liệu, chỉ khi cách viết thay thế hợp lệ theo `data/vi_words.txt` (pyvi, MIT), xuất hiện ≥3 lần và gấp ≥4 lần cách viết gốc. Cụm đã có trong từ điển được giữ. Tách đoạn có "Điều N." bị gộp giữa đoạn trước. Bỏ dãy chữ số lặp ("3 3 3"). Có ô "Sửa dấu và bỏ nhiễu dấu mộc" trong GUI (chỉ hiện khi chọn tiếng Việt). |
| `pdf_ops.py` | Xoay trang, nén PDF và theo dõi thư mục (`watch_folder`, quét định kỳ, không dùng watchdog). |
| `pdf_extract.py` | Công cụ PDF: trích xuất trang và tách file (pypdf): cú pháp `2,5-7,12-`, file riêng cho mỗi nhóm, ghi đè, nén, bỏ bookmark, phiên bản PDF. Lệnh `ocrnhat-pdf`. Các mục Tách PDF, Ghép PDF, Công cụ khác trong GUI. |
| `suspect.py` | `--suspect` (thử nghiệm, tắt mặc định): BERT tiếng Nhật đánh dấu ký tự nghi ngờ, không sửa văn bản. |
| `gpupack.py` | Gói GPU tùy chọn: chọn torch cu126 + torchvision từ chỉ mục PyTorch, cài Chandra bằng pip (có sẵn trong exe) vào `%LOCALAPPDATA%\OCR-Nhat\gpu`; `activate()` đưa vào đường dẫn import lúc khởi động. Tiến độ cài lấy từ số dòng `Collecting` rồi dung lượng thư mục đích (pip không in thanh tiến trình ra file); `SystemExit` của pip cũng thành `PackError`; cài dở xóa `.installed`. Cài lỗi thì GUI báo bằng tiếng Việt và mở được `install.log`; `ocrnhat --check-gpu-pack` kiểm tra pip đóng gói sẵn (CI chạy bước này trên cả hai exe). |
| `gpu.py` | Dò GPU NVIDIA (nvidia-smi, có đường dẫn dự phòng NVSMI), `gpu_selectable()` (ô Phần cứng có mục GPU khi có card NVIDIA hoặc onnxruntime CUDA), `resolve_device(pref, engine)`: Chandra xét CUDA của torch, engine ONNX xét CUDA của onnxruntime. |
| `cli.py` | Dòng lệnh `ocrnhat`. |
| `gui.py` | Giao diện chính PySide6: thanh bên 4 mục (OCR, Tách PDF, Ghép PDF, Công cụ khác), mục OCR đầy đủ, nhớ tùy chọn (`qt_ocr`), phím tắt, thu gọn khi cửa sổ hẹp. |
| `gui_pdf.py` | Ba mục Công cụ PDF: Tách PDF (trích xuất, tách file), Ghép PDF (ghép, xen kẽ, chèn trang lặp lại), Công cụ khác (xoay, nén, tự động theo thư mục). Danh sách kéo-thả sắp xếp được; chạy nền, hủy giữa các file; nhớ tùy chọn trong `qt_pdf`. Hàng nút dưới cùng mỗi tab: Chạy (xanh), Dừng (đỏ), Mở thư mục kết quả (vàng), ba nút cùng kích cỡ và co giãn theo cửa sổ. Thanh tiến trình động (`gui_progress.py`): phần trăm bên phải, tờ giấy minh hoạ bên trái, dải sáng khi đang chạy. |
| `gui_style.py` | Khuôn màu và kiểu (QSS) dùng chung: sáng/tối, thẻ bo góc, nút xanh, nhãn trạng thái file. Màu đạt WCAG AA (`contrast()`). Tên hiển thị **OCR-Thanh Quang**. |
| `gui_extra.py` | Kết quả và xem trước (ảnh và chữ, khung dòng), chọn vùng cắt bằng chuột, Tìm nhanh, mô hình AI (tải model, cài gói GPU, chạy nền), menu Hiển thị (áp dụng ngay). |
| `gui_about.py` | Menu **Trợ giúp** (cạnh Hiển thị): Giới thiệu và giấy phép (tác giả, liên hệ, giấy phép thành phần), Thông tin hệ thống (GPU, torch CUDA, Chandra, đường dẫn; nút Sao chép), Báo lỗi (mở thư mục `logs`). Hộp thoại Thông tin hệ thống cũng mở khi bấm ô "Trạng thái hệ thống" ở thanh bên. |
| `ui_logic.py` | Nhãn, ánh xạ nhãn -> khóa và đọc tùy chọn OCR. Không phụ thuộc giao diện (test được không cần cửa sổ). |

Mã NDLOCR-Lite **không nằm trong repo**: `python scripts/fetch_ndlocr.py` tải đúng commit đã ghim vào `vendor/ndlocr-lite` (đã gitignore). Ghi công trong `NOTICE.md`.

## Thư mục và file khác
- `scripts/`: `fetch_ndlocr.py` (tải engine), `fetch_models.py` (model PaddleOCR, kiểm SHA-256), `export_vi.py` (tạo lại `assets/vi-ocr/` từ VietOCR gốc, cần torch), `smoke_test.py` (OCR ảnh mẫu, dựng bảng), `compare_engines.py` (đối chiếu với YomiToku, chỉ để so sánh, không đóng gói vì giấy phép CC BY-NC-SA).
- `tests/`: pytest (`test_vi_text` không cần model, `test_pdf_extract` (PDF tạo trong test), `test_layout`, `test_output`, `test_pipeline`, `test_followups`, `test_suspect`, `test_engines_lang` không cần model, `test_engines_models` chạy khi có `models/`, `test_ui_logic` không cần cửa sổ; `test_gui`, `test_gui_pdf`, `test_gui_extra`, `test_gui_style` cần PySide6 (offscreen; trên Linux cần libEGL, bỏ qua nếu thiếu)).
- `tests/data/pretest_sample.pdf`: sổ tay tiếng Nhật thương mại 4 trang, file mẫu chính cho các test và đo độ chính xác từ nay.
- `.github/workflows/`: `qt-windows.yml` (mỗi push: test giao diện Qt trên Windows, `run_gui.py --selftest`), `test.yml` (mỗi push/PR), `build-exe.yml` (exe chính `OCR-Nhat` bằng PySide6, kèm bộ cài `OCR-Nhat-setup.exe` bằng Inno Setup từ `installer/OCR-Nhat.iss`; chạy thủ công), `build-exe-gpu.yml` (exe GPU: onnxruntime-gpu; chạy thủ công). Ô Thiết bị chỉ có "GPU (NVIDIA)" khi onnxruntime có CUDA, tức bản GPU. Gói GPU tùy chọn chỉ tăng tốc Chandra; NDLOCR trong bản CPU vẫn chạy CPU. Torch CUDA và Chandra KHÔNG nằm trong exe: `gpupack.py` tải về khi người dùng bấm "Cài gói GPU + Chandra".
- `requirements.txt`: nguồn duy nhất của dependency. `pyproject.toml` đọc từ đó. Extra: `test`, `suspect`.
- `.claude/agents/`: agent `developer` và `code-reviewer`.
- `run_gui.py`: điểm vào. Không tham số = mở giao diện; có tham số = dòng lệnh; `--selftest` kiểm cửa sổ rồi thoát.

## Trạng thái hiện tại
- Nhánh làm việc: `claude/tender-mayer-745l94`.
- Giao diện: chỉ còn PySide6 (`gui.py`, `run_gui.py`). Tkinter đã bỏ hoàn toàn (`gui.py`, `widgets.py`, `textview.py` cũ đã xóa; không còn `tkinterdnd2`). Exe chính `OCR-Nhat.exe` đóng gói PySide6; bộ cài `OCR-Nhat-setup.exe` giữ tên cũ.
- Mục OCR: danh sách file (kéo-thả, Ctrl+O), xem trước và chọn vùng đọc (`--crop`, nhiều vùng cách bằng `;`, DPI 150/200/300); "Loại tài liệu" đặt sẵn độ phóng to và đọc bảng (Sổ tay/sách, Ảnh chụp điện thoại, Chỉ văn bản; không lưu, đặt lại mỗi lần mở); cấu hình công cụ/ngôn ngữ/phần cứng; "Ghi kèm .txt" ở cấu hình; "Tùy chọn nâng cao" thu gọn (ghi số trang, ruby, cách ghép trang, trang); tiến trình, Dừng; kết quả với xem trước có khung dòng, Tìm nhanh; khối mô hình AI (tải PaddleOCR/VietOCR/Chandra, cài gói GPU, chạy nền). Ngưỡng nghi ngờ có chữ gợi ý hiển thị sẵn (không chỉ tooltip).
- Ba mục PDF (Tách PDF, Ghép PDF, Công cụ khác) đầy đủ; xem chi tiết tính năng bên dưới.
- Lưu tùy chọn trong `settings.json`: `qt_ocr`, `qt_pdf`, `qt_view`. Ghi khi đóng và khi bấm chạy.
- Menu Hiển thị: giao diện sáng/tối, cỡ chữ (Nhỏ/Vừa/Lớn/Rất lớn), độ trong suốt 90–100% (dưới 90% chữ khó đọc nên không cho chọn). Áp dụng ngay, không cần khởi động lại. Palette Qt lấy từ bảng màu của giao diện đã chọn, không theo chế độ Windows, nên menu, nền và ô danh sách luôn khớp với QSS.
- Phím tắt: Ctrl+O (thêm file), Ctrl+R/F5 (chạy), Esc (dừng, có hỏi), Ctrl+1..4 (đổi mục), Delete (bỏ mục). Đóng cửa sổ khi đang chạy: hỏi, dừng, chờ luồng nền xong.
- Bố cục mục OCR: nút **Dừng** nằm trên header cạnh "Bắt đầu xử lý" (bật khi đang chạy); khối "Tiến trình" ở đầu cột phải, có nút "Mở thư mục kết quả" khi xong. Gợi ý kéo thả luôn hiện (rút gọn khi đã có file). Tên file nằm trên mục danh sách (trình đọc màn hình đọc được).
- Bố cục cột trái co được: nút Thêm/Bỏ và Mở kết quả xếp lưới 2×2, nhãn gợi ý xuống dòng, xem trước tối thiểu 200 px; cột phải giữ đủ chiều rộng nội dung (381 px ở cửa sổ 1180 px).
- Responsive: cửa sổ < 980 px thu gọn thanh bên (nhãn hai dòng: "Tách/PDF", "Ghép/PDF", "Công cụ/khác") và xếp cột cấu hình xuống dưới danh sách file; tối thiểu 760×560. Hai cột ngăn bằng `QSplitter` (kéo được, cột cấu hình 300–560 px); cửa sổ hẹp đổi sang xếp dọc. Hằng số: `SIDEBAR_W`, `SIDEBAR_W_COMPACT`, `RIGHT_MIN_W`, `RIGHT_MAX_W` trong `gui.py`.
- Lỗi nhập (OCR và mục PDF) hiện ngay trong banner của mục, không mở hộp thoại; con trỏ về ô bị lỗi (`gui_style.show_banner`). Hộp thoại chỉ còn cho xác nhận dừng/thoát.
- Khi OCR đang chạy: khóa nút thêm/bỏ file, khối cấu hình và xem trước, có tooltip lý do (`OcrPage._locked_while_running`). Mục PDF khóa nút và danh sách như cũ.
- Trợ năng: mọi ô nhập có `accessibleName` (test `tests/test_gui.py::test_o_nhap_co_ten_truy_cap`); màu đạt WCAG AA, chữ phụ đậm hơn (≥5,4:1 trên mọi nền sáng, `tests/test_gui_ux.py`); palette tối lấy từ token chung `gui_style.PALETTES` (không còn bảng màu thứ hai); dòng nghi ngờ có ⚠ và nét đứt, không chỉ dựa vào màu. Khi OCR xong hoặc lỗi, banner được phát sự kiện Alert (`QAccessibleEvent`) cho trình đọc màn hình; trạng thái đang chạy không phát liên tục.
- Kiểm đã chạy: `pytest` 254 đạt, 2 bỏ qua (chưa có model; thêm `libegl1` để test Qt chạy trên Linux); `python run_gui.py --selftest` đạt (Linux, offscreen, cần libEGL/libxkbcommon). Chưa kiểm trên Windows thật và chưa thử NVDA/Narrator.
- Ô "Trạng thái hệ thống" (thanh bên): bấm hoặc Enter để mở Thông tin hệ thống; hiện Sẵn sàng / Đang xử lý / Đang tải mô hình (chấm đổi màu) và dòng phần cứng (tên card, VRAM; dò ở luồng nền).
- Tải mô hình (PaddleOCR, VietOCR, Chandra, gói GPU) dùng `AnimatedProgress` với phần trăm thật. Chandra: tiến độ lấy từ dung lượng `blobs` trong cache Hugging Face so với tổng dung lượng repo (tqdm theo byte không đáng tin với hf-xet).
- Lỗi đã sửa: ô Phần cứng không có mục GPU trên exe CPU dù máy có RTX (trước chỉ xét onnxruntime); `auto` trên exe CPU ra `cpu` và ép Chandra chạy CPU (`resolve_device` giờ theo engine). Chưa kiểm trên máy có GPU thật; log cài đặt người dùng dừng ở "Installing collected packages" (không có `Successfully installed`), nghi pip chưa xong hoặc bị ngắt khi giải nén torch ~2,6 GB, chưa xác nhận.
- Nhật ký lỗi: `%LOCALAPPDATA%\OCR-Nhat\logs\app.log`. Lỗi "pip thoát với mã 2" khi cài gói GPU: đầu ra pip ghi vào `%LOCALAPPDATA%\OCR-Nhat\gpu\install.log`.
- Công cụ PDF: "Trích xuất trang" (`pdf_extract.py`, pypdf >=6, BSD-3): ô "Trang cần lấy" (`2`, `5-23`, `2,5-7,12-`), "Một file riêng cho mỗi nhóm trang", "Phiên bản PDF" (1.4–1.7, mặc định 1.5), "Ghi đè", "Nén file đầu ra" (mặc định bật), "Bỏ bookmark" (mặc định tắt). Tên file: `extract_<tên gốc>_trang_<nhóm>.pdf`; không ghi đè thì thêm ` (2)`. "Tách PDF" (`split_pdf`): theo số trang, theo bookmark cấp 1 (trang trước bookmark đầu thành `split_<tên gốc>_phan_dau`; tên đầy đủ có tiền tố `split_`), theo dung lượng tối đa MB (ước lượng). Lệnh `ocrnhat-pdf file.pdf --split pages|bookmark|size --every N --max-mb X`. "Ghép nhiều file" (`merge_pdfs`): theo thứ tự danh sách, mỗi file có bookmark cấp 1 mang tên file, tên đầu ra `merge_<tên>.pdf`, mặc định `merge_ghep.pdf`; lệnh `--merge --name tong` cho `merge_tong.pdf`. "Ghép xen kẽ" (`interleave_pdfs`: A1 B1 A2 B2…; tùy chọn đảo file thứ hai cho scan mặt sau) và "Chèn trang lặp lại" (`insert_repeated`: B1 A B2 A B3 A, hoặc trước mỗi trang); lệnh `--interleave [--reverse-second]`, `--insert [--insert-page N] [--insert-before]`. Bookmark không giữ trong hai chế độ này. "Xoay trang" (`rotate_pdf`, 90/180/270 độ, chọn trang); "Nén PDF" (`compress_pdf`: gộp đối tượng trùng, nén nội dung, tùy chọn nén lại ảnh JPEG bằng Pillow; ảnh trong suốt giữ nguyên); "Tự động theo thư mục" (`watch_folder`: quét định kỳ, không dùng watchdog; file xử lý khi kích thước ổn định; kết quả vào `da_xu_ly`). Lệnh `--rotate`, `--compress [--image-quality N]`, `--watch THU_MUC`. Đã biết: file mẫu nén không mất dữ liệu gần như không giảm dung lượng (ảnh sẵn là JPEG). Tránh PyMuPDF (AGPL) và Ghostscript (AGPL) khi đóng gói.
- Gộp trang (mặc định): `layout.merge_pages` nối đoạn bị cắt giữa trang, bỏ trang trống, không ngắt trang trong Word. `--keep-pages` hoặc ô "Cách ghép trang" = Giữ nguyên trang để có một trang Word cho mỗi trang gốc.
- Engine theo ngôn ngữ: "Tiếng Nhật – NDLOCR/Chandra", "Tiếng Anh/Trung – PaddleOCR" (`paddle`), "Tiếng Việt – VietOCR" (`ocr_vi`). Chọn engine chưa có model sẽ báo thiếu gì và chỉ đến mục Mô hình AI.
- Ngôn ngữ: `--lang ja` (mặc định), `en`, `zh`, `vi`, `all` (chỉ Chandra). Mỗi ngôn ngữ chỉ giữ chữ của ngôn ngữ đó (`layout._script_keep`). `auto` chọn engine theo ngôn ngữ: en/zh -> paddle, vi -> ocr_vi. Ô Ngôn ngữ trong GUI chỉ liệt kê ngôn ngữ mà engine đang chọn hỗ trợ. Với en/vi, nối dòng bằng khoảng trắng và kết câu bằng `.!?:;`.
- PaddleOCR và VietOCR: model tải trong GUI (vào `%LOCALAPPDATA%\OCR-Nhat\models` khi chạy exe), không đóng vào exe. VietOCR không tải được từ GUI thì chạy `scripts/export_vi.py`. Chưa kiểm trên PDF scan thật, chưa đo tốc độ trên máy người dùng.
- Chandra: GUI có ô xác nhận OpenRAIL-M và nút "Tải mô hình Chandra" (chạy nền). `auto` chọn khi có NVIDIA đủ VRAM, đã cài `ocrnhat[chandra]` và torch có CUDA; AMD/Intel về NDLOCR. Ô Thiết bị = CPU ép Chandra chạy CPU. Batch: 6 GB -> 4 trang, từ 8 GB -> 8 trang (chỉ Chandra). CHƯA chạy model thật (môi trường không có GPU).
- Đầu ra: mặc định ghi cạnh file gốc, mọi chức năng đều có tiền tố theo chức năng (`ocr_`, `extract_`, `split_`, `merge_`, `interleave_`, `insert_`, `rotate_`, `compress_`) (CLI `-o` / ô "Thư mục lưu" để trống = thư mục gốc). Tên file: `ocr_<tên không dấu>_<trang đầu>_<trang cuối>.docx/.txt` (`pipeline.output_stem`, `ascii_name`). Cache `.cache` nằm trong thư mục đầu ra.
- GUI đã có đủ `--review`, `--crop`, `--upscale`, `--ruby`, `--kana-reader`.
- Chưa kiểm trên Windows thật: giao diện PySide6, exe và bộ cài sau khi bỏ Tkinter (build chỉ chạy được trên GitHub Actions). Chưa thử trình đọc màn hình thật.
- `ocr_vi` đã chạy trên PDF scan thật (quyết định 1196/QĐ-ĐHQN, 43 trang, CPU ~11 s/trang, có cache). Hậu xử lý `vi_text.py` giảm âm tiết ngoài từ điển từ 4,5% xuống 3,8% trên tài liệu này (đo bằng từ điển pyvi, chưa có bản đối chiếu chuẩn). Vẫn còn: nhiễu dấu mộc in hoa (ví dụ "INTERSING"), "Căn cử" (cặp không đủ bằng chứng để sửa), lỗi nhận dạng chữ không phải dấu (ví dụ "đôi" → "đối" đã sửa, nhưng "thi"/"thì" lẫn trong ngữ cảnh chưa chắc).
- Chưa làm: GPU chạy thật trong exe (exe dùng onnxruntime CPU); tùy chọn Loại tài liệu chưa lưu; xem trước kết quả tiếng Việt/Anh chưa kiểm trên tài liệu thật.

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
