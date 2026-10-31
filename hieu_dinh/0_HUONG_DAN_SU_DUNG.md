# Bộ Gem hiệu đính OCR tiếng Nhật – dùng cho mọi tài liệu

## Lập Gem một lần
1. Ô Hướng dẫn của Gem: dán `1_GEM_INSTRUCTIONS.md`.
2. Mục Kiến thức: tải `2_GEM_KNOWLEDGE_vi_du_mau.md` và `4_MAU_HO_SO_SACH.md`. Không tải file OCR lên đây.

## Mỗi tài liệu mới
1. `python tools/chia_doan.py ocr.docx doan.txt` (nhận .docx hoặc .txt; chỉnh `--size`, `--heading` nếu cần).
2. Điền 【HỒ SƠ SÁCH】 theo mẫu (5–10 dòng là đủ), dán vào đầu cuộc trò chuyện mới.
3. Dán từng đoạn, mỗi lượt một đoạn. Cứ 5–6 đoạn mở cuộc trò chuyện mới và dán lại hồ sơ.
4. Sau mỗi lượt: lưu câu trả lời của Gem thành file, chạy
   `python tools/kiem_tra_mat_chu.py doan_goc.txt tra_ve.txt`
   để biết Gem có lược hoặc bịa chữ không. Mất/thêm nhiều bất thường thì yêu cầu làm lại đoạn đó.
5. Chỗ nào còn `⟦…⟧` thì đối chiếu sách gốc hoặc gửi ảnh trang cho Gem.
