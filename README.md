# Trợ Lý Tra Cứu Tài Liệu (NotebookLM Style)

Ứng dụng Streamlit hỏi đáp trên kho tài liệu nội bộ, dùng Gemini File API. Câu trả lời
bắt buộc có trích dẫn nguồn và không được suy diễn ngoài tài liệu.

## Cài đặt

```bash
pip install -r requirements.txt
```

Tạo file `.env` (xem mẫu `.env.example`):

```
GEMINI_API_KEY=AIza...
```

## Chạy

```bash
streamlit run app.py
```

## Cách dùng

1. Đặt tài liệu vào thư mục `docs/` (có thể dùng thư mục con: `Hop dong/`, `Bieu mau/`…),
   hoặc tải lên trực tiếp ở thanh bên.
2. Bấm **☁️ Đồng bộ & Nạp tài liệu**. App sẽ chuyển đổi định dạng cần thiết, nạp lên
   Gemini và chờ tới khi tệp sẵn sàng.
3. Đặt câu hỏi. Bỏ tick một tài liệu trong danh sách để loại nó khỏi phạm vi hỏi đáp.

Ký hiệu trạng thái: `✅` đã nạp · `🔄` đã sửa, cần nạp lại · `⬜` chưa nạp · `⛔` không hỗ trợ.

## Định dạng hỗ trợ

| Định dạng | Cách xử lý |
|---|---|
| `.pdf`, `.txt`, `.md`, `.csv` | nạp trực tiếp lên Gemini |
| `.docx` | chuyển sang Markdown (giữ tiêu đề và bảng) |
| `.xlsx` | chuyển sang Markdown, mỗi sheet một mục |

`.doc`, `.xls`, `.ppt`, `.pptx` chưa hỗ trợ — hãy lưu lại thành định dạng mới.

## Cấu trúc

```
app.py                  giao diện Streamlit, quản lý phiên chat và nạp tệp
document_processor.py    quét docs/, chuyển đổi định dạng, xác định MIME type
docs/                    kho tài liệu gốc
processed_docs/          bản Markdown trung gian (tự sinh, có thể xoá)
.streamlit/config.toml   theme và giới hạn dung lượng tải lên
```

## Lưu ý vận hành

- Tệp trên Gemini File API **hết hạn sau 48 giờ**. App tự phát hiện và nạp lại khi cần,
  nhưng ngữ cảnh hội thoại sẽ được khởi tạo lại ở lượt đó.
- Đổi mô hình / temperature / chế độ nghiêm ngặt sẽ tạo phiên chat mới; lịch sử dạng
  văn bản được giữ lại, tài liệu được gửi lại.
- Giới hạn dung lượng mỗi tệp tải lên qua web đang đặt 200 MB trong
  `.streamlit/config.toml`.
- Mọi file cấu hình phải lưu bằng **UTF-8**. Trên PowerShell, `>` và `Out-File` mặc định
  ghi UTF-16 khiến `requirements.txt` và `config.toml` không đọc được — dùng
  `Set-Content -Encoding utf8`.
