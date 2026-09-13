"""
Trợ Lý Tra Cứu Tài Liệu (NotebookLM Style) — Streamlit + Gemini File API.

Chạy:  streamlit run app.py
"""

import io
import os
import re
import shutil
import tempfile
import time
import uuid

import streamlit as st
from dotenv import load_dotenv
from google import genai
from google.genai import types

from document_processor import (
    DOCS_DIR,
    PROCESSED_DOCS_DIR,
    SUPPORTED_EXTS,
    list_documents,
    list_folders,
    processed_path,
    scan_and_process_documents,
)
from pdf_to_docx_module import convert_pdf_to_docx

load_dotenv(override=True)


def read_api_key():
    """
    Lấy API key theo thứ tự: biến môi trường / .env -> st.secrets.
    """
    key = (os.getenv("GEMINI_API_KEY") or "").strip()
    if not key:
        try:
            key = (st.secrets.get("GEMINI_API_KEY") or "").strip()
        except Exception:
            pass
    return key


API_KEY = read_api_key()

# --------------------------------------------------------------------- BẢO MẬT

def is_safe_path(base_dir, target_path):
    """
    [BẢO MẬT] Ngăn chặn tấn công Path Traversal (vượt quyền thư mục).
    Đảm bảo đường dẫn đích hoàn toàn nằm bên trong thư mục gốc cho phép.
    """
    base_abs = os.path.abspath(base_dir)
    target_abs = os.path.abspath(target_path)
    return target_abs.startswith(base_abs + os.sep) or target_abs == base_abs


MODELS = {
    "Gemini 2.5 Flash — nhanh, tiết kiệm": "gemini-2.5-flash",
    "Gemini 2.5 Pro — phân tích sâu": "gemini-2.5-pro",
}
UPLOAD_TYPES = sorted(ext.lstrip(".") for ext in SUPPORTED_EXTS)
FILE_ACTIVE_TIMEOUT = 300  # giây, chờ Gemini xử lý xong file lớn
ROOT_LABEL = "(Thư mục gốc)"
VIEW_MODES = ["📦 Tất cả", "⭐ Đã đánh dấu", "🕒 Gần đây"]

BASE_INSTRUCTION = (
    "Bạn là Trợ lý phân tích và tra cứu tài liệu chuyên sâu, chuẩn xác và khách quan.\n"
    "Nguyên tắc 1: Trả lời TUYỆT ĐỐI dựa trên các tài liệu được đính kèm. Nếu tài liệu "
    "không đề cập hoặc thông tin không rõ ràng, phải nói rõ: 'Tài liệu không đề cập nội "
    "dung này'. Nghiêm cấm tự suy diễn hoặc bịa đặt.\n"
    "Nguyên tắc 2: BẮT BUỘC TRÍCH DẪN NGUỒN sau mỗi luận điểm, dữ kiện hoặc số liệu, ghi "
    "trong ngoặc vuông theo đúng tên tài liệu đã cung cấp, ví dụ: "
    "[Ten_Tai_Lieu.pdf, Trang X] hoặc [Bao_Cao.xlsx, Sheet 'Chi Phí'].\n"
    "Nguyên tắc 3: Tự động đối chiếu chéo giữa các tài liệu, nêu rõ điểm thống nhất và "
    "điểm mâu thuẫn nếu có.\n"
    "Nguyên tắc 4: Trình bày bằng tiếng Việt, có cấu trúc rõ ràng (tiêu đề, gạch đầu dòng, "
    "bảng khi cần)."
)
LOOSE_SUFFIX = (
    "\nNgoại lệ: khi người dùng hỏi kiến thức chung ngoài tài liệu, bạn được phép trả lời "
    "nhưng phải ghi rõ '(Ngoài phạm vi tài liệu)' ở đầu phần đó."
)

st.set_page_config(
    page_title="Trợ Lý Tra Cứu Tài Liệu",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Cập nhật màu sắc chủ đạo theo yêu cầu: Xanh lá, Vàng, Đỏ cảnh báo, Nền tối.
st.markdown(
    """
<style>
/* Tăng kích cỡ chữ toàn cục */
html, body, [class*="st-"] {
    font-size: 16px;
}
p {
    font-size: 16px !important;
}

/* Sidebar Text */
[data-testid="stSidebar"] div[data-testid="stMarkdownContainer"] p,
[data-testid="stSidebar"] div[data-testid="stMarkdownContainer"] h2,
[data-testid="stSidebar"] label p,
[data-testid="stSidebar"] button p {
    color: #e2e8f0 !important;
    font-size: 16px !important;
}
[data-testid="stSidebar"] div[data-testid="stMetricValue"] { 
    color: #f8fafc !important; 
    font-size: 26px !important;
}
[data-testid="stSidebar"] div[data-testid="stMetricLabel"] p { 
    font-size: 14px !important; 
    color: #94a3b8 !important;
}

.sidebar-header {
    font-size: 15px;
    font-weight: 700;
    letter-spacing: 1px;
    text-transform: uppercase;
    color: #22c55e; /* Màu xanh lá chủ đạo */
    margin-top: 25px;
    margin-bottom: 12px;
}

/* Tiêu đề chính */
.app-title { color: #e8ecf8; font-size: 36px; margin-bottom: 4px; }
.app-subtitle { color: #94a3b8; font-size: 18px; }

/* Banners */
.welcome-banner {
    background-color: #0f291e;
    border: 1px solid #22c55e; /* Xanh lá */
    padding: 18px 24px;
    border-radius: 10px;
    margin-bottom: 24px;
}
.welcome-banner strong { color: #4ade80; font-size: 18px; }
.welcome-banner span { color: #bbf7d0; font-size: 16px; }

.warning-banner {
    background-color: #2e2411;
    border: 1px solid #eab308; /* Vàng */
    padding: 18px 24px;
    border-radius: 10px;
    margin-bottom: 30px;
    display: flex;
    justify-content: space-between;
    align-items: center;
}
.warning-banner strong { color: #fde047; font-size: 18px; }
.warning-banner span { color: #fef08a; font-size: 16px; }

/* Các cảnh báo lỗi nguy hiểm sẽ giữ màu đỏ mặc định của Streamlit (st.error) */

/* Style cho các nút Gợi ý (Pills) */
[data-testid="stBaseButton-secondary"] {
    border-radius: 20px !important;
    border: 1px solid #334155 !important;
    background-color: #1e293b !important;
    padding: 10px 18px !important;
    box-shadow: 0 1px 2px rgba(0,0,0,0.1) !important;
}
[data-testid="stBaseButton-secondary"]:hover {
    background-color: #334155 !important;
    border-color: #eab308 !important; /* Vàng khi hover */
}
[data-testid="stBaseButton-secondary"] p {
    font-size: 16px !important;
    color: #e2e8f0 !important;
}
/* Cac nut trong sidebar khong dung style pill */
[data-testid="stSidebar"] [data-testid="stBaseButton-secondary"] {
    border-radius: 8px !important;
    background-color: transparent !important;
    border-color: #2c3550 !important;
    box-shadow: none !important;
}

/* 📱 Tối ưu hoá cho Điện thoại (Mobile Responsive) */
@media (max-width: 768px) {
    .app-title { font-size: 26px !important; }
    .app-subtitle { font-size: 15px !important; }
    
    .welcome-banner, .warning-banner {
        padding: 12px 16px !important;
    }
    .warning-banner {
        flex-direction: column;
        align-items: flex-start;
        gap: 10px;
    }
    
    /* Gợi ý câu hỏi trên điện thoại nên dàn ra một chút để dễ bấm */
    [data-testid="stBaseButton-secondary"] {
        padding: 12px 16px !important;
        width: 100% !important;
    }
    [data-testid="stBaseButton-secondary"] p {
        font-size: 15px !important;
    }
}

#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
</style>
""",
    unsafe_allow_html=True,
)

DEFAULTS = {
    "uploaded_files_registry": {},  # name -> {gemini_file, mtime, size, folder, synced_at}
    "active_docs": set(),           # tài liệu nằm trong phạm vi hỏi đáp
    "sent_docs": set(),             # tài liệu đã gửi vào phiên chat hiện tại
    "starred": set(),
    "messages": [],
    "chat": None,
    "pre_filled_query": "",
    "uploader_key": 0,
    "model_label": next(iter(MODELS)),
    "temperature": 0.2,
    "strict_mode": True,
    "view_mode": VIEW_MODES[0],
    "folder_filter": "Tất cả",
    "applied_config": None,
    "confirm_purge": False,
    "last_skipped": [],
}
for key, value in DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = value.copy() if isinstance(value, (dict, set, list)) else value


# ------------------------------------------------------------------ helpers

def human_size(num_bytes):
    for unit in ("B", "KB", "MB", "GB"):
        if num_bytes < 1024 or unit == "GB":
            return f"{num_bytes:.0f} {unit}" if unit == "B" else f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024.0


def file_state(gemini_file):
    """Chuẩn hoá trạng thái file về chuỗi: ACTIVE / PROCESSING / FAILED."""
    state = getattr(gemini_file, "state", None)
    name = getattr(state, "name", None) or str(state)
    return name.upper().rsplit(".", 1)[-1]


def wait_until_active(client, gemini_file):
    """
    Gemini xử lý file bất đồng bộ; gửi file ở trạng thái PROCESSING sẽ bị lỗi 400.
    Vì vậy phải chờ tới khi ACTIVE.
    """
    deadline = time.time() + FILE_ACTIVE_TIMEOUT
    while file_state(gemini_file) == "PROCESSING":
        if time.time() > deadline:
            raise TimeoutError("Gemini xử lý file quá lâu (>5 phút)")
        time.sleep(2)
        gemini_file = client.files.get(name=gemini_file.name)
    if file_state(gemini_file) == "FAILED":
        detail = getattr(gemini_file, "error", "") or ""
        raise RuntimeError(f"Gemini không xử lý được file. {detail}")
    return gemini_file


def upload_document(client, doc):
    """Nạp một tài liệu lên Gemini và chờ tới khi sẵn sàng."""
    ext = os.path.splitext(doc["path"])[1].lower() or ".txt"
    # Sao chép ra thư mục tạm của hệ thống (KHÔNG để trong docs/ như bản cũ,
    # vì file tạm sẽ bị chính bộ quét nhặt lại thành "tài liệu"),
    # đồng thời tránh lỗi tên file có dấu tiếng Việt.
    with tempfile.TemporaryDirectory() as tmp_dir:
        safe_path = os.path.join(tmp_dir, uuid.uuid4().hex + ext)
        shutil.copy2(doc["path"], safe_path)
        gemini_file = client.files.upload(
            file=safe_path,
            config=types.UploadFileConfig(
                display_name=doc["original_name"][:250],
                mime_type=doc["mime_type"],
            ),
        )
    return wait_until_active(client, gemini_file)


def delete_remote(client, gemini_file):
    if gemini_file is None:
        return
    try:
        client.files.delete(name=gemini_file.name)
    except Exception:
        pass  # file có thể đã hết hạn hoặc bị xoá trước đó


def system_instruction():
    return BASE_INSTRUCTION if st.session_state.strict_mode else BASE_INSTRUCTION + LOOSE_SUFFIX


def current_config():
    """Cấu hình đang chọn; đổi giá trị này thì phải tạo lại phiên chat."""
    return (
        st.session_state.model_label,
        round(float(st.session_state.temperature), 4),
        bool(st.session_state.strict_mode),
    )


def build_history():
    """Giữ lại lịch sử hội thoại dạng văn bản khi phải tạo lại phiên chat."""
    history = []
    for message in st.session_state.messages:
        role = "user" if message["role"] == "user" else "model"
        history.append(types.Content(role=role, parts=[types.Part(text=message["content"])]))
    return history


def build_chat(client, keep_history=True):
    """Tạo phiên chat mới; tài liệu sẽ được gửi lại ở lượt hỏi kế tiếp."""
    chat = client.chats.create(
        model=MODELS[st.session_state.model_label],
        config=types.GenerateContentConfig(
            temperature=st.session_state.temperature,
            system_instruction=system_instruction(),
        ),
        history=build_history() if keep_history else [],
    )
    st.session_state.sent_docs = set()
    st.session_state.applied_config = current_config()
    return chat


def ordered_active():
    """Tài liệu trong phạm vi hỏi đáp, theo thứ tự đã nạp."""
    return [n for n in st.session_state.uploaded_files_registry if n in st.session_state.active_docs]


def prune_registry(client):
    """Bỏ khỏi bộ nhớ những tài liệu đã bị xoá khỏi ổ đĩa."""
    on_disk = {doc["name"] for doc in list_documents()}
    for gone in set(st.session_state.uploaded_files_registry) - on_disk:
        entry = st.session_state.uploaded_files_registry.pop(gone)
        delete_remote(client, entry.get("gemini_file"))
        st.session_state.active_docs.discard(gone)
        st.session_state.sent_docs.discard(gone)
        st.session_state.starred.discard(gone)


def sync_documents(client, only_names=None):
    """
    Quét docs/, chuyển đổi và nạp các tài liệu mới hoặc vừa thay đổi.
    Trả về (danh sách đã nạp, danh sách lỗi).
    """
    registry = st.session_state.uploaded_files_registry
    baseline = registry if only_names is None else {
        k: v for k, v in registry.items() if k not in set(only_names)
    }
    pending, skipped = scan_and_process_documents(baseline)
    if only_names is not None:
        wanted = set(only_names)
        pending = [p for p in pending if p["original_name"] in wanted]
    st.session_state.last_skipped = skipped

    synced, errors = [], []
    bar = st.progress(0.0, text="Đang nạp tài liệu...") if pending else None
    for idx, doc in enumerate(pending, start=1):
        name = doc["original_name"]
        if bar is not None:
            bar.progress((idx - 1) / len(pending), text=f"Đang nạp: {name}")
        try:
            gemini_file = upload_document(client, doc)
            delete_remote(client, (registry.get(name) or {}).get("gemini_file"))
            registry[name] = {
                "gemini_file": gemini_file,
                "mtime": doc["mtime"],
                "size": doc["size"],
                "folder": doc["folder"],
                "synced_at": time.time(),
            }
            st.session_state.active_docs.add(name)
            st.session_state.sent_docs.discard(name)
            synced.append(name)
        except Exception as exc:
            errors.append((name, str(exc)))
    if bar is not None:
        bar.empty()

    prune_registry(client)
    return synced, errors


def remove_document(client, name):
    """Xoá một tài liệu: file trên đĩa, bản chuyển đổi và bản trên Gemini."""
    entry = st.session_state.uploaded_files_registry.pop(name, None)
    if entry:
        delete_remote(client, entry.get("gemini_file"))
    st.session_state.active_docs.discard(name)
    st.session_state.sent_docs.discard(name)
    st.session_state.starred.discard(name)

    local_path = os.path.join(DOCS_DIR, *name.split("/"))
    
    # KIỂM TRA BẢO MẬT: Ngăn chặn xoá nhầm file ngoài thư mục docs/ (Path Traversal)
    if not is_safe_path(DOCS_DIR, local_path):
        st.error(f"Bảo mật: Từ chối xoá đường dẫn không an toàn ({name})")
        return

    try:
        if os.path.isfile(local_path):
            os.remove(local_path)
    except OSError as exc:
        st.warning(f"Không xoá được file trên đĩa ({name}): {exc}")

    converted = processed_path(name)
    if os.path.isfile(converted):
        try:
            os.remove(converted)
        except OSError:
            pass


def purge_everything(client):
    for entry in st.session_state.uploaded_files_registry.values():
        delete_remote(client, entry.get("gemini_file"))
    for folder in (DOCS_DIR, PROCESSED_DOCS_DIR):
        if os.path.exists(folder):
            shutil.rmtree(folder, ignore_errors=True)
        os.makedirs(folder, exist_ok=True)
    st.session_state.uploaded_files_registry = {}
    st.session_state.active_docs = set()
    st.session_state.sent_docs = set()
    st.session_state.starred = set()
    st.session_state.messages = []
    st.session_state.chat = None
    st.session_state.last_skipped = []
    st.session_state.uploader_key += 1


def safe_folder_name(raw):
    cleaned = re.sub(r"[^0-9A-Za-zÀ-ỹ \-_.]+", "", (raw or "").strip())
    cleaned = cleaned.strip(" .")
    return cleaned[:60]


def is_expired_file_error(exc):
    text = str(exc).lower()
    file_hint = "file" in text or "files/" in text
    return file_hint and any(
        token in text
        for token in ("permission_denied", "not found", "not_found", "403", "404", "expired")
    )


def friendly_error(exc):
    """Diễn giải lỗi API thành thông báo tiếng Việt dễ hiểu."""
    text = str(exc)
    low = text.lower()
    if is_transient_error(exc):
        return (
            "Máy chủ Gemini đang quá tải (lỗi 503 phía Google, không phải lỗi của app "
            "hay tài liệu). App đã tự thử lại nhưng vẫn chưa được. Hãy đợi một lát rồi hỏi "
            "lại, hoặc đổi sang mô hình khác trong ⚙️ Cài đặt hệ thống."
        )
    if "resource_exhausted" in low or "429" in low:
        match = re.search(r"retry in ([\d.]+)s", text)
        wait = f" Hãy thử lại sau khoảng {float(match.group(1)):.0f} giây." if match else ""
        return (
            "Đã hết hạn mức Gemini API (tài khoản miễn phí bị giới hạn số lượt mỗi ngày "
            "cho từng mô hình)." + wait + " Bạn có thể đổi mô hình trong ⚙️ Cài đặt hệ thống "
            "hoặc nâng cấp gói tính phí."
        )
    if "api key not valid" in low or "unauthenticated" in low or "api_key_invalid" in low:
        return "GEMINI_API_KEY không hợp lệ hoặc đã hết hiệu lực. Hãy cập nhật lại file .env."
    if "permission_denied" in low or "403" in low:
        return "Không có quyền truy cập (403). Kiểm tra lại API key và quyền với tệp đã nạp."
    if "unsupported mime type" in low:
        return "Gemini không đọc được định dạng tệp này. Hãy chuyển sang PDF, DOCX, XLSX, TXT, CSV hoặc MD."
    if "deadline" in low or "timeout" in low or "504" in low:
        return "Gemini phản hồi quá lâu. Thử lại, hoặc bỏ chọn một số tài liệu để giảm tải."
    if "safety" in low or "blocked" in low:
        return "Nội dung bị bộ lọc an toàn của Gemini chặn. Hãy diễn đạt lại câu hỏi."
    return text


def build_parts(pending, prompt):
    """
    Ghép nội dung gửi lên: danh mục tên tài liệu -> các tệp -> câu hỏi.

    Danh mục là cần thiết vì Gemini không thấy tên file gốc (tệp được nạp bằng
    tên tạm), nếu thiếu thì phần trích dẫn nguồn sẽ không đúng tên tài liệu.
    """
    registry = st.session_state.uploaded_files_registry
    parts = []
    if pending:
        listing = "\n".join(f"{i}. {name}" for i, name in enumerate(pending, start=1))
        parts.append(
            "Các tài liệu sau được đính kèm ngay dưới đây, theo đúng thứ tự:\n"
            + listing
            + "\nKhi trích dẫn nguồn, hãy dùng chính xác các tên tài liệu ở trên."
        )
        parts.extend(registry[name]["gemini_file"] for name in pending)
    parts.append(prompt)
    return parts


def is_transient_error(exc):
    """Lỗi tạm thời phía máy chủ Gemini — thử lại là được, không phải lỗi cấu hình."""
    text = str(exc).lower()
    return any(
        token in text
        for token in ("503", "unavailable", "high demand", "overloaded", "internal error")
    )


def stream_answer(parts, placeholder, progress=None):
    """Phát trực tiếp câu trả lời; trả về (văn bản, usage)."""
    answer, usage = "", None
    for chunk in st.session_state.chat.send_message_stream(parts):
        try:
            piece = chunk.text
        except Exception:
            piece = None
        if piece:
            answer += piece
            if progress is not None:
                progress["emitted"] = True
            placeholder.markdown(answer + " ▌")
        if getattr(chunk, "usage_metadata", None):
            usage = chunk.usage_metadata
    placeholder.markdown(answer if answer else "_(Mô hình không trả về nội dung nào.)_")
    return answer, usage


def send_with_retry(parts, placeholder, attempts=5):
    """
    Tự thử lại khi Gemini báo quá tải (503). Chỉ thử lại nếu chưa chữ nào được
    phát ra, để không nối hai câu trả lời vào nhau.
    """
    for attempt in range(attempts):
        progress = {"emitted": False}
        try:
            return stream_answer(parts, placeholder, progress)
        except Exception as exc:
            last_try = attempt == attempts - 1
            if last_try or progress["emitted"] or not is_transient_error(exc):
                raise
            delay = 2 * (2 ** attempt)  # 2s, 4s
            placeholder.markdown(
                f"_Mô hình đang quá tải. Tự thử lại sau {delay} giây "
                f"(lần {attempt + 2}/{attempts})..._"
            )
            time.sleep(delay)


def transcript_markdown():
    lines = ["# Biên bản trò chuyện — Trợ Lý Tra Cứu Tài Liệu", ""]
    scope = ordered_active()
    if scope:
        lines += ["**Phạm vi tài liệu:**"] + [f"- {n}" for n in scope] + [""]
    for message in st.session_state.messages:
        who = "🧑 Người dùng" if message["role"] == "user" else "🤖 Trợ lý"
        lines += [f"## {who}", "", message["content"], ""]
    return "\n".join(lines)


# ------------------------------------------------------------------ sidebar

def render_sidebar(client):
    disk_docs = list_documents()
    registry = st.session_state.uploaded_files_registry

    with st.sidebar:
        st.markdown(
            '<h2>📚 Trợ Lý Tra Cứu Tài Liệu<br>'
            '<span style="font-size:12px;color:#63739a;font-weight:normal">NotebookLM Style</span></h2>',
            unsafe_allow_html=True,
        )

        if st.button("➕ Tạo cuộc trò chuyện mới", type="primary", use_container_width=True):
            st.session_state.messages = []
            st.session_state.chat = build_chat(client, keep_history=False)
            st.rerun()

        st.markdown('<div class="sidebar-header">Kho tài liệu</div>', unsafe_allow_html=True)
        m1, m2, m3 = st.columns(3)
        m1.metric("Trên đĩa", len(disk_docs))
        m2.metric("Đã nạp", len(registry))
        m3.metric("Đang chọn", len(st.session_state.active_docs))

        pending_count = sum(
            1
            for d in disk_docs
            if d["supported"] and (registry.get(d["name"]) or {}).get("mtime") != d["mtime"]
        )
        if pending_count:
            st.warning(f"{pending_count} tài liệu chưa nạp / vừa thay đổi.", icon="⚠️")

        if st.button("☁️ Đồng bộ & Nạp tài liệu", type="primary", use_container_width=True):
            with st.spinner("Đang xử lý và đồng bộ tài liệu..."):
                synced, errors = sync_documents(client)
            for name, err in errors:
                st.error(f"Lỗi khi nạp {name}: {friendly_error(err)}")
            if synced:
                st.success(f"Đã nạp {len(synced)} tài liệu.")
            elif not errors:
                st.info("Không có tài liệu mới nào cần đồng bộ.")
            if synced or errors:
                time.sleep(1.2)
            st.rerun()

        # ---- bộ lọc hiển thị
        st.markdown('<div class="sidebar-header">Bộ lọc</div>', unsafe_allow_html=True)
        # Dùng key= để Streamlit tự đồng bộ session_state; nếu vừa gán giá trị
        # trả về vừa truyền index= thì hai nguồn trạng thái sẽ lệch nhau.
        st.radio(
            "Chế độ xem",
            VIEW_MODES,
            key="view_mode",
            label_visibility="collapsed",
        )

        folders = list_folders()
        folder_options = ["Tất cả"] + [
            (ROOT_LABEL if f == "" else f) for f in sorted(folders, key=lambda x: (x != "", x))
        ]
        # Thư mục có thể vừa bị xoá -> phải làm sạch trước khi tạo widget,
        # nếu không Streamlit sẽ báo lỗi vì giá trị không nằm trong options.
        if st.session_state.folder_filter not in folder_options:
            st.session_state.folder_filter = "Tất cả"
        st.markdown('<div class="sidebar-header">Thư mục</div>', unsafe_allow_html=True)
        st.selectbox(
            "Thư mục",
            folder_options,
            key="folder_filter",
            format_func=lambda opt: (
                opt
                if opt == "Tất cả"
                else f"📁 {opt} ({folders.get('' if opt == ROOT_LABEL else opt, 0)})"
            ),
            label_visibility="collapsed",
        )

        render_document_list(client, disk_docs)

        # ---- tải lên
        st.markdown('<div class="sidebar-header">Tải tài liệu lên</div>', unsafe_allow_html=True)
        folder_choices = [ROOT_LABEL] + sorted(f for f in folders if f) + ["➕ Thư mục mới..."]
        target = st.selectbox("Thư mục đích", folder_choices)
        new_folder = ""
        if target == "➕ Thư mục mới...":
            new_folder = safe_folder_name(st.text_input("Tên thư mục mới", key="new_folder_name"))

        uploaded = st.file_uploader(
            "Chọn tệp",
            accept_multiple_files=True,
            type=UPLOAD_TYPES,
            key=f"uploader_{st.session_state.uploader_key}",
            help="Hỗ trợ: " + ", ".join(UPLOAD_TYPES).upper(),
        )
        st.caption("⚠️ Riêng PDF: Gemini chỉ nhận tối đa 50 MB hoặc 1000 trang mỗi file.")
        if uploaded:
            if target == "➕ Thư mục mới..." and not new_folder:
                st.warning("Hãy nhập tên thư mục mới trước khi tải lên.")
            else:
                sub = "" if target == ROOT_LABEL else (new_folder or target)
                dest_dir = os.path.join(DOCS_DIR, sub) if sub else DOCS_DIR
                os.makedirs(dest_dir, exist_ok=True)
                saved = 0
                for item in uploaded:
                    # [BẢO MẬT] Làm sạch tên file để loại bỏ ký tự điều khiển
                    safe_name = re.sub(r'[\x00-\x1f\x7f-\x9f/:*?"<>|]', '', os.path.basename(item.name))
                    if not safe_name:
                        continue
                    
                    dest = os.path.join(dest_dir, safe_name)
                    
                    # [BẢO MẬT] Chống ghi đè hoặc tạo file ngoài thư mục docs/
                    if not is_safe_path(DOCS_DIR, dest):
                        st.error(f"Bảo mật: Tệp {safe_name} không an toàn!")
                        continue
                        
                    with open(dest, "wb") as out:
                        out.write(item.getbuffer())
                    saved += 1
                # Đổi key để widget tự xoá danh sách, tránh việc file vừa xoá
                # bị ghi lại ở lần rerun sau.
                st.session_state.uploader_key += 1
                st.toast(f"Đã lưu {saved} tệp vào kho. Bấm 'Đồng bộ & Nạp tài liệu'.", icon="📥")
                st.rerun()

        # ---- công cụ
        st.markdown('<div class="sidebar-header">Công cụ</div>', unsafe_allow_html=True)
        if st.button("📄 Làm đoạn trích chuyên sâu", use_container_width=True):
            st.session_state.pre_filled_query = (
                "Hãy rút trích các đoạn nguyên văn quan trọng nhất trong phạm vi tài liệu "
                "đang chọn. Với mỗi đoạn: (1) trích nguyên văn trong dấu ngoặc kép, "
                "(2) ghi rõ nguồn và vị trí, (3) giải thích ngắn ý nghĩa và tình huống áp dụng."
            )
        if st.button("📊 Phân tích tài liệu", use_container_width=True):
            st.session_state.pre_filled_query = (
                "Hãy phân tích tài liệu đang chọn theo cấu trúc: 1) Mục đích và phạm vi áp dụng; "
                "2) Các nội dung/nghĩa vụ chính; 3) Mốc thời gian và con số quan trọng; "
                "4) Rủi ro và điểm chưa rõ ràng; 5) Khuyến nghị hành động. "
                "Mỗi ý phải có trích dẫn nguồn."
            )

        with st.expander("⚙️ Cài đặt hệ thống"):
            st.selectbox(
                "Mô hình", list(MODELS), key="model_label",
                help="Tài khoản Gemini miễn phí giới hạn số lượt/ngày riêng cho từng mô hình.",
            )
            st.slider(
                "Độ sáng tạo (temperature)", 0.0, 1.0, step=0.05, key="temperature",
                help="Càng thấp càng sát tài liệu. Khuyến nghị 0.0 – 0.3 cho tra cứu.",
            )
            st.toggle(
                "Chỉ trả lời trong phạm vi tài liệu",
                key="strict_mode",
                help="Tắt để cho phép bổ sung kiến thức chung, có ghi chú rõ ràng.",
            )
            # Model / temperature / system prompt nằm trong cấu hình của phiên chat,
            # nên khi đổi phải tạo lại phiên (lịch sử được giữ, tài liệu gửi lại).
            if st.session_state.applied_config != current_config():
                st.session_state.chat = build_chat(client)
                st.toast("Đã áp dụng cài đặt mới.", icon="⚙️")
                st.rerun()
            st.caption(f"Kho: `{os.path.abspath(DOCS_DIR)}`")

        st.markdown('<div class="sidebar-header">Vùng nguy hiểm</div>', unsafe_allow_html=True)
        if not st.session_state.confirm_purge:
            if st.button("🗑️ Đổ rác (xoá toàn bộ tài liệu)", use_container_width=True):
                st.session_state.confirm_purge = True
                st.rerun()
        else:
            st.error("Xoá vĩnh viễn mọi tệp trong kho và trên Gemini?")
            c1, c2 = st.columns(2)
            if c1.button("Xoá hết", type="primary", use_container_width=True):
                purge_everything(client)
                st.session_state.confirm_purge = False
                st.toast("Đã xoá sạch kho tài liệu.", icon="✅")
                st.rerun()
            if c2.button("Huỷ", use_container_width=True):
                st.session_state.confirm_purge = False
                st.rerun()


def render_document_list(client, disk_docs):
    registry = st.session_state.uploaded_files_registry
    folder_filter = st.session_state.folder_filter
    view_mode = st.session_state.view_mode

    docs = disk_docs
    if folder_filter != "Tất cả":
        wanted = "" if folder_filter == ROOT_LABEL else folder_filter
        docs = [d for d in docs if (d["folder"].split("/")[0] if d["folder"] else "") == wanted]
    if view_mode == "⭐ Đã đánh dấu":
        docs = [d for d in docs if d["name"] in st.session_state.starred]
    elif view_mode == "🕒 Gần đây":
        docs = sorted(
            [d for d in docs if d["name"] in registry],
            key=lambda d: registry[d["name"]].get("synced_at", 0),
            reverse=True,
        )[:10]

    with st.expander(f"📑 Danh sách tài liệu ({len(docs)})", expanded=True):
        if not docs:
            st.caption("Chưa có tài liệu nào khớp bộ lọc.")
            return

        scope_changes = {}
        for doc in docs:
            name = doc["name"]
            entry = registry.get(name)
            if not doc["supported"]:
                status = "⛔"
            elif entry is None:
                status = "⬜"
            elif entry.get("mtime") != doc["mtime"]:
                status = "🔄"
            else:
                status = "✅"

            c1, c2, c3 = st.columns([0.66, 0.17, 0.17])
            label = f"{status} {name}"
            if entry is not None and doc["supported"]:
                scope_changes[name] = c1.checkbox(
                    label,
                    value=name in st.session_state.active_docs,
                    key=f"scope::{name}",
                    help=f"{human_size(doc['size'])} — bỏ chọn để loại khỏi phạm vi hỏi đáp",
                )
            else:
                c1.markdown(
                    f"<span style='color:#94a3b8;font-size:14px'>{label}</span>",
                    unsafe_allow_html=True,
                )
                if doc["reason"]:
                    c1.caption(doc["reason"])

            starred = name in st.session_state.starred
            if c2.button("⭐" if starred else "☆", key=f"star::{name}", help="Đánh dấu"):
                st.session_state.starred.discard(name) if starred else st.session_state.starred.add(name)
                st.rerun()
            if c3.button("🗑", key=f"del::{name}", help="Xoá tài liệu này"):
                remove_document(client, name)
                st.toast(f"Đã xoá {name}", icon="🗑️")
                st.rerun()

        for name, in_scope in scope_changes.items():
            if in_scope:
                st.session_state.active_docs.add(name)
            else:
                st.session_state.active_docs.discard(name)

        st.caption("✅ đã nạp · 🔄 đã sửa, cần nạp lại · ⬜ chưa nạp · ⛔ không hỗ trợ")

    if st.session_state.last_skipped:
        with st.expander(f"⚠️ Bỏ qua ({len(st.session_state.last_skipped)})"):
            for item in st.session_state.last_skipped:
                st.caption(f"• {item['name']} — {item['reason']}")

    st.markdown('<div class="sidebar-header">🛠 CÔNG CỤ PHỤ</div>', unsafe_allow_html=True)
    with st.expander("📄 Chuyển đổi PDF sang DOCX"):
        st.write("Tải file PDF lên để chuyển sang định dạng Word (.docx).")
        uploaded_pdf = st.file_uploader("Chọn file PDF", type=["pdf"], key="pdf_to_docx_uploader")
        if uploaded_pdf:
            if st.button("Chuyển đổi ngay", use_container_width=True, type="primary"):
                with st.spinner("Đang chuyển đổi... quá trình này có thể mất vài phút."):
                    # Save uploaded file to a temporary file
                    import tempfile
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_pdf:
                        tmp_pdf.write(uploaded_pdf.getvalue())
                        tmp_pdf_path = tmp_pdf.name
                    
                    try:
                        out_docx_path = tmp_pdf_path.replace(".pdf", ".docx")
                        convert_pdf_to_docx(tmp_pdf_path, out_docx_path)
                        
                        with open(out_docx_path, "rb") as docx_file:
                            docx_bytes = docx_file.read()
                            
                        # Offer download
                        download_name = uploaded_pdf.name.replace(".pdf", ".docx")
                        st.download_button(
                            label=f"⬇️ Tải xuống {download_name}",
                            data=docx_bytes,
                            file_name=download_name,
                            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                            use_container_width=True,
                            type="primary"
                        )
                        st.success("Chuyển đổi thành công!")
                    except Exception as e:
                        st.error(f"Lỗi: {e}")
                    finally:
                        # Clean up
                        if os.path.exists(tmp_pdf_path):
                            os.remove(tmp_pdf_path)
                        if 'out_docx_path' in locals() and os.path.exists(out_docx_path):
                            os.remove(out_docx_path)


# --------------------------------------------------------------------- main

def render_main(client):
    st.markdown(
        '<h1 class="app-title">📚 Trợ Lý Tra Cứu Tài Liệu (NotebookLM Style)</h1>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<p class="app-subtitle">Trợ lý AI giúp bạn tìm hiểu, phân tích và '
        'trả lời chuyên sâu dựa trên tài liệu của bạn.</p>',
        unsafe_allow_html=True,
    )
    st.markdown(
        """
    <div class="welcome-banner">
        <strong style="font-size: 17px;">ℹ️ Chào mừng bạn đến với Trợ Lý Tra Cứu Tài Liệu</strong><br>
        <span>Hãy tải tài liệu lên hoặc bấm “Đồng bộ &amp; Nạp
        tài liệu” ở thanh bên để bắt đầu tra cứu với câu trả lời có trích dẫn nguồn.</span>
    </div>
    """,
        unsafe_allow_html=True,
    )

    scope = ordered_active()
    if not st.session_state.uploaded_files_registry:
        st.markdown(
            """
        <div class="warning-banner">
            <strong style="font-size: 17px;">💡 Chưa có tài liệu nào được nạp</strong><br>
            <span>Vui lòng tải lên hoặc đồng bộ tài liệu
            để hệ thống có thể trả lời câu hỏi của bạn.</span>
        </div>
        """,
            unsafe_allow_html=True,
        )
    elif not scope:
        st.warning("Bạn đã bỏ chọn toàn bộ tài liệu. Hãy chọn lại ít nhất một tài liệu ở thanh bên.", icon="⚠️")
    else:
        head = ", ".join(scope[:3]) + (f" và {len(scope) - 3} tài liệu khác" if len(scope) > 3 else "")
        st.caption(f"🎯 Phạm vi hỏi đáp: **{len(scope)}** tài liệu — {head}")

    st.markdown("**Gợi ý câu hỏi phổ biến**")
    suggestions = [
        ("📝 Tóm tắt nội dung chính", "Hãy tóm tắt nội dung chính của các tài liệu đang chọn, có trích dẫn nguồn."),
        ("⭐ Các điểm quan trọng", "Các điểm quan trọng cần lưu ý trong tài liệu là gì? Nêu kèm trích dẫn nguồn."),
        ("⚖️ Phân tích ưu/nhược", "Phân tích ưu điểm và hạn chế của các văn bản này, kèm trích dẫn nguồn."),
        ("🔍 Tài liệu so sánh", "Hãy so sánh điểm giống và khác nhau giữa các tài liệu đang chọn, kèm trích dẫn nguồn."),
    ]
    cols = st.columns(len(suggestions))
    for col, (label, query) in zip(cols, suggestions):
        if col.button(label, use_container_width=True, key=f"sug::{label}"):
            st.session_state.pre_filled_query = query

    st.divider()

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if st.session_state.messages:
        st.download_button(
            "⬇️ Tải biên bản trò chuyện (.md)",
            data=io.BytesIO(transcript_markdown().encode("utf-8")),
            file_name="bien-ban-tra-cuu.md",
            mime="text/markdown",
        )

    prompt = st.chat_input("Nhập câu hỏi của bạn về nội dung tài liệu...")
    if st.session_state.pre_filled_query:
        prompt = st.session_state.pre_filled_query
        st.session_state.pre_filled_query = ""

    if not prompt:
        return

    if not scope:
        st.error("Chưa có tài liệu nào trong phạm vi hỏi đáp. Hãy đồng bộ hoặc chọn tài liệu trước.")
        return

    # Bỏ tài liệu khỏi phạm vi => phải tạo lại phiên chat, vì nội dung cũ
    # vẫn còn trong lịch sử của phiên hiện tại.
    dropped = st.session_state.sent_docs - st.session_state.active_docs
    if dropped:
        st.session_state.chat = build_chat(client)
        st.info(f"Đã thu hẹp phạm vi, khởi tạo lại ngữ cảnh ({len(dropped)} tài liệu bị loại).", icon="🔄")

    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    registry = st.session_state.uploaded_files_registry
    pending = [n for n in scope if n not in st.session_state.sent_docs]
    parts = build_parts(pending, prompt)

    with st.chat_message("assistant"):
        placeholder = st.empty()
        placeholder.markdown("_Đang đọc tài liệu và phân tích..._")
        try:
            try:
                answer, usage = send_with_retry(parts, placeholder)
            except Exception as exc:
                if not is_expired_file_error(exc):
                    raise
                # Tệp trên Gemini File API hết hạn sau 48 giờ -> nạp lại rồi thử lại.
                placeholder.markdown("_Tệp trên Gemini đã hết hạn, đang nạp lại tài liệu..._")
                for name in scope:
                    registry.pop(name, None)
                sync_documents(client, only_names=scope)
                st.session_state.chat = build_chat(client)
                retry_scope = [n for n in scope if n in registry]
                if not retry_scope:
                    raise RuntimeError("Không nạp lại được tài liệu, hãy bấm 'Đồng bộ' lại.")
                parts = build_parts(retry_scope, prompt)
                pending = retry_scope
                answer, usage = send_with_retry(parts, placeholder)

            st.session_state.sent_docs.update(pending)
            st.session_state.messages.append({"role": "assistant", "content": answer})
            if usage is not None:
                st.caption(
                    f"Token: vào {getattr(usage, 'prompt_token_count', '?')} · "
                    f"ra {getattr(usage, 'candidates_token_count', '?')}"
                )
        except Exception as exc:
            placeholder.empty()
            st.session_state.messages.pop()  # tránh lịch sử lệch vai user/model
            st.error(f"Đã xảy ra lỗi: {friendly_error(exc)}")
            with st.expander("Chi tiết lỗi (kỹ thuật)"):
                st.code(str(exc))


def main():
    if not API_KEY or API_KEY in ("your_key_here", "AIza_dan_key_cua_ban_vao_day"):
        st.error("⚠️ Chưa cấu hình GEMINI_API_KEY.")
        st.markdown(
            """
- **Chạy trên máy cá nhân:** thêm key vào file `.env` ở thư mục dự án
- **Streamlit Community Cloud:** vào *App settings → Secrets* rồi dán key vào đó
"""
        )
        st.code('GEMINI_API_KEY = "AIza..."', language="toml")
        st.stop()

    if "client" not in st.session_state:
        try:
            st.session_state.client = genai.Client(api_key=API_KEY)
        except Exception as exc:
            st.error(f"Không khởi tạo được Gemini client: {exc}")
            st.stop()
    client = st.session_state.client

    if st.session_state.chat is None:
        st.session_state.chat = build_chat(client)

    render_sidebar(client)
    render_main(client)


if __name__ == "__main__":
    main()
