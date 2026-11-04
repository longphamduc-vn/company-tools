# 📸 Python Step Recorder

> **Giải pháp mã nguồn mở thay thế toàn diện cho Windows Steps Recorder (Problem Steps Recorder - `psr.exe`) được viết bằng Python.**

---

## 🌟 Giới thiệu

Từ Windows 11 bản cập nhật mới, Microsoft đã chính thức thông báo khai tử (deprecated) công cụ **Steps Recorder (PSR)**. Để giải quyết vấn đề này trong công việc kiểm thử phần mềm (QA), ghi lại bug (Bug Reporting), tạo tài liệu hướng dẫn quy trình (SOP), hoặc đào tạo người dùng, **Python Step Recorder** ra đời với kiến trúc hiện đại, đa nền tảng và nhiều cải tiến vượt bậc so với công cụ gốc của Windows.

### ✨ So sánh với Windows Steps Recorder gốc:

| Tính năng | Windows Steps Recorder (PSR) | Python Step Recorder (Dự án này) |
| :--- | :--- | :--- |
| **Hệ điều hành** | Chỉ Windows (đang bị xóa bỏ) | **Windows, Linux, macOS** (Đa nền tảng) |
| **Giới hạn số bước** | Mặc định chỉ 25 bước | **Tùy biến không giới hạn** (mặc định 200+) |
| **Định dạng báo cáo** | MHTML cũ kỹ (khó mở trên Chrome/Edge) | **HTML hiện đại** (Responsive, Dark/Light mode, Lightbox Zoom) |
| **Tệp tin báo cáo** | Phải giải nén zip để xem ảnh | **Self-contained HTML (Base64)**: 1 file duy nhất gửi qua Slack/Mail xem được ngay |
| **Xuất Markdown** | ❌ Không hỗ trợ | ✅ **Tự động tạo `report.md`** để dán thẳng vào Jira / GitHub Issue / GitLab PR |
| **Đóng gói xuất file** | Chỉ file ZIP chứa MHTML | **HTML, Markdown, JSON metadata, file ZIP** chứa ảnh gốc PNG |
| **Tùy biến chỉ điểm (Click Marker)** | Chỉ có vòng tròn xanh/đỏ cố định | **4 phong cách** (Ring, Crosshair, Glow, Solid) + Chọn màu HEX bất kỳ + Đánh số Badge |
| **Bảo vệ ứng dụng** | Hay bị ghi đè click chính nó | **Tự động nhận diện toạ độ Toolbar để bỏ qua click trên app** |
| **Chế độ dòng lệnh (CLI)** | Hạn chế | ✅ Hỗ trợ đầy đủ cờ CLI `--cli` cho headless / automation |

---

## 📂 Cấu trúc dự án

```text
step-recorder/
├── run.py                          # Launcher khởi chạy ứng dụng chính
├── pyproject.toml                  # Cấu hình đóng gói dự án
├── requirements.txt                # Thư viện phụ thuộc
├── README.md                       # Hướng dẫn chi tiết
├── tests/
│   └── test_all.py                 # Bộ kiểm thử tự động (Unit & Integration tests)
└── step_recorder/
    ├── __init__.py
    ├── config.py                   # Quản lý cài đặt (load/save json)
    ├── models.py                   # Data models (Step, SessionMetadata)
    ├── window_info.py              # Nhận diện cửa sổ & tiến trình đang kích hoạt (Win/Linux/Mac)
    ├── capture.py                  # Chụp màn hình đa màn hình với mss & Pillow
    ├── annotator.py                # Vẽ chỉ điểm chuột (Ring, Glow, Badge, Selection Box)
    ├── recorder.py                 # Core engine bắt sự kiện mouse & keyboard (pynput)
    ├── exporter.py                 # Xuất báo cáo HTML, Markdown, JSON, ZIP
    ├── cli.py                      # Giao diện dòng lệnh CLI
    ├── templates/
    │   └── report_template.html    # Giao diện báo cáo HTML hiện đại tích hợp sẵn
    └── ui/
        ├── __init__.py
        ├── main_window.py          # Thanh công cụ nổi (Floating Toolbar)
        ├── comment_dialog.py       # Cửa sổ thêm ghi chú / ghi nhận lỗi tại bước
        └── settings_dialog.py      # Cửa sổ cấu hình thông số
```

---

## 🚀 Cài đặt

### 1. Yêu cầu hệ thống
- Python `>= 3.9`
- Hệ điều hành: Windows, Linux (X11 / Wayland), hoặc macOS.

### 2. Cài đặt thư viện
```bash
cd step-recorder
pip install -r requirements.txt
```

*(Các thư viện chính gồm: `pillow`, `mss`, `pynput`, `jinja2`, `python-xlib` trên Linux / `pywin32` trên Windows).*

---

## 🖥️ Hướng dẫn sử dụng

### 1. Khởi chạy giao diện thanh công cụ nổi (GUI)

Chạy lệnh sau trong terminal hoặc double click vào `run.py`:

```bash
python run.py
```

Thanh công cụ nhỏ gọn nổi trên màn hình sẽ xuất hiện:
- **`⏺ Start Record`**: Bắt đầu ghi lại các thao tác chuột và phím.
- **`⏸ Pause` / `▶ Resume`**: Tạm dừng hoặc tiếp tục phiên ghi hình.
- **`💬 Comment`**: Thêm ghi chú mô tả lỗi hoặc ghi chú quan trọng tại màn hình hiện tại.
- **`⏹ Stop`**: Dừng phiên ghi hình, tự động kết xuất báo cáo và mở trong trình duyệt web.
- **`⚙ Settings`**: Mở cửa sổ cấu hình (màu sắc điểm nhấn, kiểu marker, thư mục lưu, v.v.).

---

### 2. Sử dụng chế độ dòng lệnh (CLI Headless)

Thích hợp khi muốn chạy trên server, máy ảo, hoặc tích hợp script:

```bash
# Ghi lại với tiêu đề tùy ý và xuất vào thư mục chỉ định
python run.py --cli --title "Kiem thu chuc nang Dang nhap" --output ./recordings
```

Nhấn phím **Enter** trên terminal bất cứ lúc nào để dừng và xuất báo cáo!

Các tham số hỗ trợ:
```text
options:
  -h, --help            Trợ giúp
  --cli                 Chạy ở chế độ dòng lệnh (không cần giao diện GUI)
  --output, -o OUTPUT   Đường dẫn thư mục lưu kết quả
  --title, -t TITLE     Tiêu đề phiên ghi hình
  --max-steps, -m MAX   Giới hạn số bước tối đa
```

---

## 📊 Báo cáo đầu ra (Generated Report)

Sau khi nhấn **Stop**, công cụ sẽ tạo ra 1 thư mục chứa đầy đủ các định dạng:

1. **`report.html`**:
   - Tệp HTML độc lập (**Standalone**), toàn bộ ảnh chụp màn hình được mã hoá Base64 nhúng trực tiếp.
   - Không cần mạng Internet để mở.
   - Hỗ trợ chế độ **Sáng / Tối (Dark/Light mode)**.
   - Tính năng **Bộ lọc nhanh**: Xem tất cả, chỉ xem Clicks, chỉ xem Phím bấm, chỉ xem Ghi chú.
   - Tìm kiếm nội dung bước hoặc tên cửa sổ theo thời gian thực.
   - Trình xem ảnh phóng to (**Fullscreen Lightbox Modal**) với các phím mũi tên `←` / `→` và `Esc`.
   - Nút **Print / PDF** được tối ưu sẵn CSS `@media print`.

2. **`report.md`**:
   - Tệp Markdown chuẩn để dán trực tiếp vào **Jira, GitHub Issues, Confluence hoặc Notion**.

3. **`session.json`**:
   - Dữ liệu dạng JSON chứa đầy đủ toạ độ chuột `(x, y)`, thời gian, tên tiến trình, tiêu đề cửa sổ cho các hệ thống phân tích tự động.

4. **`rec_XXXXXXXX.zip`**:
   - Gói nén chứa toàn bộ ảnh chụp PNG chất lượng cao và các tệp báo cáo.

---

## 🧪 Chạy kiểm thử tự động (Unit Tests)

Dự án đi kèm bộ test toàn diện:

```bash
python -m unittest tests/test_all.py
```

Kết quả: Toàn bộ 8 bài test về Config, Screen Capture, Marker Annotations, Cross-platform Window Info, Jinja2 Template rendering và Lifecycle State đều vượt qua 100%.

---

## 🔒 Bảo mật & Tối ưu

- **Bỏ qua thao tác gõ văn bản nhạy cảm**: Mặc định chỉ ghi nhận các phím điều khiển chức năng (`Enter`, `Tab`, `Escape`, phím tắt) để không vô tình lưu mật khẩu người dùng.
- **Chống spam sự kiện**: Tự động nhận diện double-click và loại trừ các cú click vào chính thanh công cụ của Step Recorder.
- **Tiến trình ngầm (Background Threading)**: Chụp và xử lý ảnh trên luồng riêng biệt, không làm lag hoặc khựng con trỏ chuột khi người dùng thao tác nhanh.

