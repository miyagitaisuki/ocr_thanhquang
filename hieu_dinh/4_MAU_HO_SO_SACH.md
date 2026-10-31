# MẪU 【HỒ SƠ SÁCH】
Mỗi cuốn sách/tài liệu điền một bản, dán vào ĐẦU cuộc trò chuyện (trước đoạn OCR đầu tiên). Mục nào chưa biết thì xóa dòng đó, đừng điền phỏng đoán. Hồ sơ càng ngắn càng tốt.

```
【HỒ SƠ SÁCH】
Tên tài liệu: …
Loại: giáo trình ngữ pháp / từ vựng / đề thi / bài đọc / khác
Ngôn ngữ OCR: Nhật (+ Việt / Anh nếu có)
Furigana: có ruby / không có / ghi chú trong ngoặc
Cấu trúc một mục chuẩn (theo thứ tự trong sách):
  1) …
  2) …
Ký hiệu đặc thù và cách OCR hay làm hỏng chúng: …
Bảng ánh xạ đã xác minh bằng sách gốc (chuỗi OCR → kết quả): …
Mẫu chân trang/đầu trang: …
Vùng hay hỏng nhất: …
Quy ước dấu câu cần giữ: …
Điều KHÔNG được động vào: …
```

# HỒ SƠ MẪU ĐÃ ĐIỀN – TRY! 日本語能力試験 N2 文法から伸ばす（bản tiếng Việt）
```
【HỒ SƠ SÁCH】
Tên tài liệu: TRY! 日本語能力試験 N2 文法から伸ばす (bản dịch tiếng Việt, OCR từ PDF)
Loại: giáo trình ngữ pháp
Furigana: bản in có furigana; OCR làm trôi thành dòng kana riêng
Cấu trúc một mục chuẩn:
  1) Số mục + mẫu ngữ pháp + ký hiệu sao (nếu OCR giữ được)
  2) どう使う？
  3) mẫu kết hợp (dòng có dấu + )
  4) 例文 ①②③…
  5) やってみよう！ (câu 1) 2) 3)… kèm dãy lựa chọn rời bên dưới) + 答え別冊N
  6) cuối bài: まとめの問題 (問題1 文法形式の判断 / 問題2 文の組み立て / 問題3 文章の文法 / 問題4 聴解)
Ký hiệu đặc thù: mức độ quan trọng (sao) bị OCR thành 大大大 / 大大ナ / 大火 / 大才 / 大大火 / ★オ. Chưa có bảng ánh xạ → dùng ⟦★?⟧.
  Chữ 大 thật: 大阪, 大学, 大きな, 大歓迎.
  ★ trong 文の組み立て là ô cần điền, không phải sao mức độ.
Mẫu chân trang: "1スタッフ募集のお知らせ●19" = số bài + tên bài + ●số trang
Vùng hay hỏng nhất: khung thông báo mở đầu mỗi bài, bảng 尊敬語/謙譲語 (bài kính ngữ), toàn bộ まとめの問題.
Điều KHÔNG được động vào: dãy lựa chọn của やってみよう (là bài tập của người học), số 答え別冊.
```

# LỖI MẪU CỦA CUỐN NÀY (để Gem hiểu loại lỗi; không phải bảng tra)
| OCR | Xử lý |
|---|---|
| `大大大6当店において` | `6 当店において ⟦★?: 大大大⟧` |
| `大にん転任のあいさつ(2)` | `転任のあいさつ（2）`, `にん` = cách đọc 任 (ghi Nhật ký), `大` → `⟦★?: 大⟧` |
| `(ばかりでなくに対してを問わず)` | `（ばかりでなく ／ に対して ／ を問わず）` |
| `2国籍を問わす` | `2 国籍を問わず` (căn cứ: を問わず ở các dòng sau) |
| `(4)エレベータードベーター` ngay trên `4)エレベーター点検中につき、` | XÓA, ghi Nhật ký |
| `乃ち刀` (không có dòng tương ứng) | `⟦?乃ち刀⟧` |
| `1,00円` | `⟦?1,00円⟧` |
