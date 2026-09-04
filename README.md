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

### Giới hạn dung lượng

| Tầng | Giới hạn | Ghi chú |
|---|---|---|
| `maxUploadSize` (config.toml) | 200 MB | tự đặt được, mặc định của Streamlit cũng là 200 |
| **Gemini — PDF** | **50 MB hoặc 1000 trang** | giới hạn cứng; app chặn sẵn và báo lý do |
| Gemini — định dạng khác | 2 GB/tệp, 20 GB/project | tệp tự xoá sau 48 giờ |
| RAM Streamlit Cloud (free) | ~1 GB đảm bảo, tối đa ~2,7 GB | tải tệp quá lớn sẽ làm app restart |
| GitHub (nếu commit vào `docs/`) | 100 MB/tệp | vượt là bị chặn push |

`.docx` và `.xlsx` được chuyển sang Markdown **trước khi** nạp lên Gemini, nên tệp nguồn
lớn vẫn dùng được — giới hạn 50 MB chỉ áp cho PDF. Nút thắt của chúng là RAM lúc đọc file.

Muốn nâng ngưỡng tải lên, sửa `.streamlit/config.toml`:

```toml
[server]
maxUploadSize = 500
```

Nhưng nâng quá 50 MB không giúp được gì cho PDF, và trên gói miễn phí thì tệp vài trăm MB
sẽ làm app hết RAM. Với PDF lớn, cách đúng là tách nhỏ file.

## Cấu trúc

```
app.py                  giao diện Streamlit, quản lý phiên chat và nạp tệp
document_processor.py    quét docs/, chuyển đổi định dạng, xác định MIME type
docs/                    kho tài liệu gốc
processed_docs/          bản Markdown trung gian (tự sinh, có thể xoá)
.streamlit/config.toml   theme và giới hạn dung lượng tải lên
```

## Triển khai (Deploy)

### Streamlit Community Cloud — khuyến nghị

1. Push code lên GitHub (repo này: `nhuphiphc-ops/NotebookLM-Clone`).
2. Vào [share.streamlit.io](https://share.streamlit.io) → **Create app** → **Deploy a public
   app from GitHub**.
3. Chọn repo, branch `main`, main file `app.py`.
4. Mở **Advanced settings → Secrets** và dán:

   ```toml
   GEMINI_API_KEY = "AIza..."
   ```

5. **Deploy**. App tự deploy lại mỗi lần push lên `main`.

App đọc key theo thứ tự: biến môi trường / `.env` → `st.secrets`. Nhờ vậy cùng một code
chạy được cả ở máy cá nhân và trên cloud, không cần sửa gì.

### Không deploy được lên Vercel

Vercel chạy serverless function: stateless, giới hạn thời gian thực thi, không giữ
WebSocket. Streamlit cần một process sống liên tục và một kết nối WebSocket cho mỗi phiên.
Muốn lên Vercel phải viết lại thành ứng dụng web thường (ví dụ Next.js + API route).

Các lựa chọn khác chạy được: Hugging Face Spaces, Render, Railway, Fly.io (Docker).

### Giới hạn khi chạy trên cloud

- **Ổ đĩa là tạm.** Tài liệu người dùng tải lên qua web sẽ mất khi app restart hoặc thức
  dậy sau khi sleep. Chỉ những file đã commit trong `docs/` là còn. Muốn lưu lâu dài phải
  gắn thêm object storage (S3 / GCS) — hiện chưa có.
- **RAM khoảng 1 GB** trên gói miễn phí. `maxUploadSize = 200` (MB) trong
  `.streamlit/config.toml` là quá cao cho môi trường này; nên hạ xuống 25–50 MB khi deploy.
- App miễn phí sẽ **sleep** nếu không có ai truy cập; lần vào đầu tiên sau đó sẽ chậm.
- Hạn mức Gemini free tier (ví dụ 20 lượt/ngày cho `gemini-2.5-flash`) là của **API key**,
  nên mọi người dùng app đều tiêu vào cùng một hạn mức đó.

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
