# Dự án OCR-Nhat (project "ocr")

Phần mềm Windows (.exe) OCR file PDF scan và ảnh, **chỉ lấy tiếng Nhật**, xuất **Word (.docx)** (+ .txt). Miễn phí, offline, không cần GPU.
Chủ dự án: Nguyễn Thanh Quang. Repo: miyagitaisuki/ocr_thanhquang.

## Yêu cầu của chủ dự án
- Chỉ giữ tiếng Nhật (bỏ tiếng Việt/Anh, bỏ furigana).
- Đầu ra là .docx có **khối văn bản liền mạch** (gộp dòng thành đoạn), tiêu đề và bảng thật.
- Ưu tiên exe gọn, nhanh; chấp nhận tự dựng bảng thay vì dùng engine nặng.
- Ưu tiên công cụ miễn phí. Ưu tiên giấy phép thoáng (NDLOCR-Lite là CC BY 4.0).

## Kiến trúc (src/ocrnhat)
- `model.py`: Page/Block/Line chung cho mọi engine. `engines/`: `base.py` (giao diện `OcrEngine`), `__init__.py` (đăng ký, `--engine`), `ndlocr.py`, `chandra.py` (PLACEHOLDER, chưa cài đặt; ghi sẵn các bước làm). Thêm engine: kế thừa `OcrEngine`, thêm tên vào `_NAMES` và nhánh vào `_cls` (engines/__init__.py); phiên bản đọc từ thuộc tính `version` của lớp (khóa cache).
- `gpu.py`: dò card NVIDIA bằng nvidia-smi (đã bỏ AMD theo quyết định chủ dự án). `--engine auto` (mặc định) chọn chandra chỉ khi có GPU đủ VRAM và Chandra dùng được; hiện Chandra là placeholder và đã TẠM DỪNG phát triển nên auto luôn ra ndlocr. `ocrnhat --gpu-info` để xem.
- Thiết bị NDLOCR: `--device auto|cpu|cuda` (GUI: ô "Thiết bị"). `gpu.resolve_device` chọn cuda chỉ khi onnxruntime có CUDAExecutionProvider; không thì lùi về CPU và in lý do. Exe trong CI dùng onnxruntime CPU nên GPU chưa chạy được trong exe: cần bản build dùng onnxruntime-gpu + CUDA/cuDNN (chưa làm; chưa thử trên máy có GPU). Bản GPU: `.github/workflows/build-exe-gpu.yml` (workflow_dispatch) cài onnxruntime-gpu, tạo `OCR-Nhat-GPU` và `ocrnhat-cli-gpu`; bản CPU `build-exe.yml` giữ nguyên.
- `engines/ndlocr.py`: bọc NDLOCR-Lite (ONNX), đọc XML trang -> Block/Line (text, table 表組, ruby ルビ, 柱, ノンブル). Commit ghim: xem `scripts/fetch_ndlocr.py`.
- `layout.py`: lọc tiếng Nhật, bỏ furigana, gộp đoạn, nhận tiêu đề, dựng bảng từ đường kẻ (OpenCV) kèm ô gộp; dự phòng theo cụm tọa độ.
- `docx_out.py`: xuất Word (font Yu Mincho, Heading, bảng) và txt.
- `pipeline.py` / `cli.py` / `gui.py`: PDF/ảnh -> kết quả; dòng lệnh; giao diện Tkinter.
- Mã NDLOCR-Lite KHÔNG nằm trong repo: tải bằng `python scripts/fetch_ndlocr.py` vào `vendor/ndlocr-lite` (đã gitignore). Ghi công trong `NOTICE.md`.

## Build / kiểm tra
- CI: `.github/workflows/build-exe.yml` (windows-latest, PyInstaller onedir). Có smoke test và bước chạy thử chính file exe. Chạy bằng workflow_dispatch.
- CI: `.github/workflows/test.yml` (ubuntu, chạy mỗi push/PR): `pytest` (test không cần model) + smoke test.
- Cục bộ: `pip install -r requirements.txt && pip install -e ".[test]"` rồi `pytest` và `ocrnhat file.pdf -o out --pages 1-5`.
- Dependency: `requirements.txt` là nguồn duy nhất (`pyproject.toml` đọc từ đó). Chỉ thêm gói mà đường chạy thật sự import.
- Không build được exe từ Linux; dùng GitHub Actions.

## Lưu ý kỹ thuật đã gặp
- Console Windows dùng cp1252: luôn `reconfigure(encoding="utf-8")` khi in tiếng Nhật/Việt.
- `gh workflow run` dùng GraphQL bị chặn: dùng `gh api -X POST repos/.../actions/workflows/build-exe.yml/dispatches -f ref=main`.
- Số khoanh tròn ①②③ trong cột đầu bảng bị engine đọc thành '(1', '19', 'O1'; nhận dạng lại ô không ổn định nên `layout._fix_circled` ánh xạ theo thứ tự hàng, chỉ khi cả cột là mã ngắn và có ô mở ngoặc.
- Engine có thể đọc chữ hai ô liền kề thành một dòng xuyên qua đường kẻ; bảng thử tổng hợp trong smoke test chỉ kiểm tra đường ống, không kiểm tra nội dung ô.

- Ảnh chụp màn hình/chữ nhỏ: `--crop x0,y0,x1,y1` cắt vùng trang trước OCR, `--upscale 2` phóng to. Trang 38 (ảnh chụp điện thoại 1290x2796): không có hai tùy chọn này chỉ ra được tiêu đề; có thì đọc được 17 dòng (độ tin cậy 0,65–0,94). Ruby/furigana chưa được giữ trong trường hợp này. Chưa có trong GUI. Khóa cache đã gồm crop/upscale.

- Furigana trong ô bảng: `layout._kana_core` bỏ ký tự rác engine gộp vào dòng furigana (ví dụ 'きょう OC', '$ ちょうしつ'); dòng có dấu chấm/hai chấm hoặc nhiều chữ Latin (nhãn 'b. いつ') không bị coi là rác. Đã kiểm trên bảng mẫu trang 7 (quiz.jpg): hết furigana trong ô. Còn lỗi: số khoanh tròn ①②③ đọc thành '(1', '19'.

## Kết quả thử trên sổ tay mẫu (136 trang)
~4–6 giây/trang CPU; 19 bảng; 11 trang rỗng (trang thuần Việt/trống). Lỗi còn lại: nhận sai chữ (私見→私覚), vài furigana sót trong ô bảng, thứ tự dòng đôi khi đảo, chữ dọc xuất theo chiều ngang.

## Hướng phát triển (đã bàn, chưa làm)
1. ~~Chế độ rà soát~~ ĐÃ LÀM: `ocrnhat --review [--conf 0.8]` -> `*_review.html` (`review.py`); chưa có trong GUI.
2. ĐÃ LÀM (opt-in `--ruby`): furigana ghép vào dòng chữ Hán bên dưới theo tọa độ ngang, xuất `w:ruby` thật (`layout._line_ruby`, `docx_out._add_ruby`). Gần đúng: ký tự chia đều theo bề ngang dòng; cụm có nhiều chữ Hán thì chia cách đọc theo số chữ. Chưa hỗ trợ ruby trong ô bảng và chữ dọc; .txt không có ruby. Mặc định vẫn bỏ furigana. Chưa thử trên trang thật.
3. Cache theo hash ĐÃ LÀM (`cache.py`, thư mục `<out>/.cache`, tắt bằng `--no-cache`). ĐÃ LÀM: OCR song song trong ThreadPool (`pipeline.process_file`, tham số `workers`; mặc định 2 với GPU, 1..4 với CPU); dựng layout và ghi file vẫn tuần tự theo thứ tự trang. Cửa sổ trượt 2*workers trang để không giữ cả file trong RAM. Đo trên engine giả 10 trang: 5,1s -> 1,5s, kết quả giống hệt chạy tuần tự. Chưa đo trên NDLOCR thật.
4. ĐÃ LÀM (mặc định bật; `--no-cell-reocr` để tắt): ô bảng có dòng vượt đường kẻ (`layout._crosses_grid`) được cắt ảnh riêng và nhận dạng lại qua engine (`pipeline.reocr`); kết quả cũ chỉ được thay khi nhận dạng lại có chữ. Kết quả thử với engine giả đúng; CHƯA kiểm chứng trên bảng thật vì ảnh bảng thử không được NDLOCR nhận là khối bảng. Kết quả nhận dạng lại không được cache.
5. Tùy chọn engine thứ hai (YomiToku, chỉ phi thương mại) để đối chiếu.
6. Dò chữ sai bằng BERT/LLM (chỉ đánh dấu để duyệt, không tự sửa).
