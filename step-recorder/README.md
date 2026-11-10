# 📸 Python Step Recorder

> **Giải pháp mã nguồn mở thay thế toàn diện cho Windows Steps Recorder (Problem Steps Recorder - `psr.exe`) được viết bằng Python.**

---

## 🌟 Giới thiệu

Từ Windows 11 bản cập nhật mới, Microsoft đã chính thức thông báo khai tử (deprecated) công cụ **Steps Recorder (PSR)**. Để giải quyết vấn đề này trong công việc kiểm thử phần mềm (QA), ghi lại bug (Bug Reporting), tạo tài liệu hướng dẫn quy trình (SOP), hoặc đào tạo người dùng, **Python Step Recorder** ra đời với kiến trúc hiện đại, đa nền tảng và nhiều cải tiến vượt bậc so với công cụ gốc của Windows.

### ✨ So sánh với Windows Steps Recorder gốc:

| Tính năng | Windows Steps Recorder (PSR) | Python Step Recorder (Dự án này) |
| :--- | :--- | :--- |
| **Hệ điều hành** | Chỉ Windows (đang bị xóa bỏ) | **Windows, Linux, macOS** (Đa nền tảng) |
| **Ngôn ngữ** | Đơn ngữ (theo ngôn ngữ Windows) | 🌐 **Song ngữ hoàn chỉnh (Bilingual: Tiếng Việt 🇻🇳 & English 🇬🇧)** |
| **Chỉnh sửa sau khi ghi (Review & Editor)** | ❌ Không thể sửa, xóa hay sắp xếp bước | ✅ **Trình duyệt & chỉnh sửa toàn diện**: Xóa, di chuyển, vẽ lại vùng Focus/Highlight, sửa ghi chú |
| **Công cụ bảo mật Che mờ / Bôi đen (Blur / Redact)** | ❌ Không hỗ trợ | 🛡️ **Che thông tin nhạy cảm**: Làm mờ Gaussian Blur (`💧`), Bôi đen Redact Blackout (`⬛`), Khung đỏ (`🔴`), Hoàn tác (`↺`) |
| **Cắt xén ảnh chụp (Crop Screenshot)** | ❌ Không hỗ trợ | ✂️ **Cắt xén tức thì**: Kéo chuột để crop ảnh về vùng quan tâm của ứng dụng |
| **Chụp 2 lần khi nhấp chuột (Dual Capture)** | ❌ Chỉ chụp 1 lần duy nhất | ⚡ **Chụp kép Action & Result (Unified)**: Chụp trước thao tác + sau thao tác; tự động gộp thành 1 bước duy nhất kèm nút bấm **Chuyển Trước/Sau (Before/After Toggle)** |
| **Kéo và Thả (Drag & Drop)** | ❌ Coi như cú click thông thường, không có hướng kéo | 🏹 **Quỹ đạo Kéo Thả (Drag & Drop Arrow)**: Nhận diện Mouse Up state machine, phân loại $d \ge 10\text{px}$, vẽ mũi tên chỉ hướng quỹ đạo kèm toạ độ đầu-cuối `(x1, y1) ➔ (x2, y2)` |
| **Thu phóng Tiêu điểm (Focus Spotlight Zoom)** | ❌ Chỉ có ảnh toàn màn hình | 🔍 **Dual-View Focus Spotlight**: Tự động trích xuất ảnh zoom cận cảnh quanh toạ độ thao tác đặt cạnh ảnh toàn cảnh, người xem nhận biết ngay điểm thao tác |
| **Gõ phím thông minh & Chụp sớm (Smart Keystroke)** | ❌ Bỏ qua text nhập liệu hoặc phân mảnh | ⌨️ **Early Snapshot & Keystroke Aggregator**: Chụp ngay ảnh trạng thái form ở phím đầu tiên, gom chuỗi gõ phím vào đúng ô nhập liệu thành 1 bước hoàn chỉnh |
| **Thao tác Cuộn & Định kỳ (Scroll & Interval Capture)** | ❌ Không hỗ trợ | 📜 **Tự động bắt sự kiện Cuộn trang & Chụp định kỳ**: Ghi nhận thao tác scroll debounced và chụp chu kỳ theo thời gian khi giao diện thay đổi |
| **Phím tắt toàn cục (Global Hotkeys)** | Hạn chế phím tắt | ⌨️ **Hands-free Hotkeys**: F7 (Ghi/Dừng), F8 (Tạm dừng), F9 (Ghi chú), F10 (Phân đoạn), F11 (Chỉnh sửa) |
| **Mở & Chèn tài liệu cũ (Open & Insert)** | ❌ Không hỗ trợ | 📂 **Quản lý đa phiên**: Mở phiên cũ chỉnh sửa tiếp, Chèn gộp nhiều tài liệu lại thành 1 bộ SOP |
| **Giới hạn số bước** | Mặc định chỉ 25 bước | **Tùy biến không giới hạn** (mặc định 200+) |
| **Định dạng báo cáo** | MHTML cũ kỹ (khó mở trên Chrome/Edge) | **HTML hiện đại** (Responsive, Dark/Light mode, Lightbox Zoom, nút đổi ngôn ngữ trực tiếp) |
| **Cấu trúc SOP & Phân đoạn (Chapters)** | ❌ Danh sách phẳng, không phân chương mục | 📑 **Phân đoạn / Chương mục SOP chuyên nghiệp**: Đánh dấu tiêu đề phần, mục tiêu, tạo thẻ Section Banner |
| **Mục lục điều hướng (Table of Contents)** | ❌ Không có mục lục | 🧭 **Mục lục 2 cột (Sticky TOC Sidebar)**: Nhảy nhanh theo chương, Scrollspy tự động theo dõi vị trí cuộn |
| **In ấn / Xuất file PDF (SOP Manual)** | Bị vỡ trang, không có mục lục trang đầu | 🖨️ **Tối ưu in ấn xuất sắc**: Trang 1 in Mục lục riêng biệt, tự động sang trang mới (`page-break`) cho từng chương |
| **Tệp tin báo cáo** | Phải giải nén zip để xem ảnh | **Self-contained HTML (Base64)**: 1 file duy nhất gửi qua Slack/Mail xem được ngay |
| **Xuất Markdown** | ❌ Không hỗ trợ | ✅ **Tự động tạo `report.md`** song ngữ có Mục Lục TOC & Anchor links nhảy trực tiếp |
| **Đóng gói xuất file** | Chỉ file ZIP chứa MHTML | **HTML, Markdown, JSON metadata, file ZIP** chứa ảnh gốc PNG |
| **Chống che khuất màn hình** | Dễ bị dính giao diện vào ảnh chụp | 🫥 **Windows API WDA_EXCLUDEFROMCAPTURE**: Tự động tàng hình thanh công cụ khỏi ảnh chụp |
| **Gom cụm thao tác gõ (Smart Keystroke)** | ❌ Bỏ qua text nhập liệu hoặc phân mảnh | ⌨️ **Smart Keystroke Aggregator**: Tự động gom chuỗi gõ phím vào đúng ô nhập liệu thành 1 bước hoàn chỉnh |
| **Nhận diện UI hiện đại (UIA)** | Chỉ dùng Win32 API cũ, không đọc được Chrome/Electron | 🔍 **Microsoft UI Automation (UIA)**: Đọc sâu tên nút bấm, loại control (Button, Edit, Tab, Menu) trên Chromium, Edge, Office |
| **Trình chiếu tương tác (Walkthrough Player)** | ❌ Không hỗ trợ | 🎮 **Interactive Guide Player**: Trình chiếu từng bước như Scribe/Tango với Radar Pulse Hotspot và chế độ Nhấp chuột chuyển bước (Click-to-advance) |
| **Vòng đời ảnh & Tối ưu RAM (Tiered Storage)** | ❌ Lưu ảnh thô trong RAM, tốn dung lượng | 🚀 **L2 Disk Spooling & WebP**: Giảm 96% RAM khi ghi (chỉ lưu Thumbnail 30KB trong RAM), chụp thông minh theo màn hình chứa chuột, xuất file WebP siêu nhẹ (giảm 80% dung lượng HTML) |
| **Tùy biến chỉ điểm (Click Marker)** | Chỉ có vòng tròn xanh/đỏ cố định | **4 phong cách** (Ring, Crosshair, Glow, Solid) + Chọn màu HEX bất kỳ + Đánh số Badge |
| **Bảo vệ ứng dụng** | Hay bị ghi đè click chính nó | **Tự động nhận diện toạ độ Toolbar để bỏ qua click trên app** |
| **Chế độ dòng lệnh (CLI)** | Hạn chế | ✅ Hỗ trợ đầy đủ cờ CLI `--cli` cho headless / automation |

---

## 📂 Cấu trúc dự án

```text
step-recorder/
├── run.py                          # Launcher khởi chạy ứng dụng chính (auto-bridge Windows Host)
├── run_app.bat                     # File chạy nhanh trên Windows
├── pyproject.toml                  # Cấu hình đóng gói dự án
├── requirements.txt                # Thư viện phụ thuộc
├── README.md                       # Hướng dẫn chi tiết
├── tests/
│   └── test_all.py                 # Bộ kiểm thử tự động (Unit & Integration tests)
└── step_recorder/
    ├── __init__.py
    ├── i18n.py                         # Quản lý đa ngôn ngữ Song ngữ (VI & EN)
    ├── config.py                   # Quản lý cài đặt (load/save json nguyên tử)
    ├── models.py                   # Data models (Step, SessionMetadata)
    ├── window_info.py              # Nhận diện cửa sổ, tiến trình, PID, UI Control & API Exclude Capture
    ├── capture.py                  # Chụp màn hình đa màn hình với mss & Pillow
    ├── annotator.py                # Vẽ chỉ điểm chuột (Ring, Glow, Badge, Blur, Redact, Crop)
    ├── hotkeys.py                  # Lắng nghe phím tắt toàn cục Global Hotkeys (F7..F11)
    ├── recorder.py                 # Core engine bắt sự kiện mouse & keyboard (pynput)
    ├── exporter.py                 # Xuất báo cáo HTML, Markdown song ngữ, JSON, ZIP
    ├── cli.py                      # Giao diện dòng lệnh CLI
    ├── templates/
    │   └── report_template.html    # Giao diện báo cáo HTML hiện đại tích hợp bộ chuyển ngữ VI/EN
    └── ui/
        ├── __init__.py
        ├── main_window.py          # Thanh công cụ nổi với nút ghim, ngôn ngữ & 6 nút chức năng
        ├── step_editor.py          # Cửa sổ Chỉnh sửa, Xóa, Sắp xếp bước & Vẽ lại Highlight
        ├── comment_dialog.py       # Cửa sổ thêm ghi chú / khoanh vùng lỗi tại bước
        ├── snipper.py              # Công cụ đóng băng màn hình kéo chọn vùng Focus/Highlight
        └── settings_dialog.py      # Cửa sổ cấu hình thông số song ngữ (Scrollable & Responsive)
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
- **`🇻🇳 VI` / `🇬🇧 EN`**: Nút chuyển đổi nhanh ngôn ngữ (Tiếng Việt & English) tức thì trên toàn bộ ứng dụng.
- **`📌 On Top` / `📍 Normal`**: Nút ghim thanh công cụ luôn trên cùng hoặc hạ xuống cửa sổ bình thường.
- **`⏺ Bắt đầu (Start)`**: Bắt đầu ghi lại các thao tác chuột và bàn phím.
- **`⏸ Tạm dừng (Pause)` / `▶ Tiếp tục (Resume)`**: Tạm dừng hoặc tiếp tục phiên ghi hình.
- **`💬 Ghi chú (Comment)`**: Mở hộp thoại thêm ghi chú lỗi và khoanh vùng Focus/Highlight trên màn hình.
- **`📝 Chỉnh sửa (Review)`**: Mở cửa sổ quản lý bước, xóa bước thừa, sắp xếp, vẽ lại vùng highlight và cập nhật mô tả.
- **`⏹ Dừng lại (Stop)`**: Dừng phiên ghi và tự động chuyển sang màn hình Review để kiểm tra trước khi xuất báo cáo.
- **`⚙ Cài đặt (Settings)`**: Cấu hình ngôn ngữ, thư mục lưu, kiểu chỉ điểm click, giới hạn bước, độ trễ và tùy chọn xuất file.

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
   - **Giao diện tài liệu 2 cột (Documentation Layout)** với thanh **Mục Lục (Table of Contents - TOC)** dính ở cạnh trái (`sticky`), tự động Scrollspy theo dõi vị trí đọc.
   - Thẻ phân đoạn **Section Banner Cards** nổi bật với nhãn chương mục, tiêu đề và mục tiêu thực hiện SOP.
   - Không cần mạng Internet để mở.
   - Hỗ trợ chế độ **Sáng / Tối (Dark/Light mode)** và nút chuyển đổi ngôn ngữ trực tiếp `🌐 Tiếng Việt / English`.
   - Tính năng **Bộ lọc nhanh**: Xem tất cả, chỉ xem Clicks, chỉ xem Phím bấm, chỉ xem Ghi chú.
   - Tìm kiếm nội dung bước, tiêu đề chương hoặc tên cửa sổ theo thời gian thực.
   - Trình xem ảnh phóng to (**Fullscreen Lightbox Modal**) với các phím mũi tên `←` / `→` và `Esc`.
   - Nút **Print / PDF** được tối ưu hóa cho SOP: Trang 1 in Mục lục riêng, mỗi chương tự động ngắt sang trang mới sạch đẹp.

2. **`report.md`**:
   - Tệp Markdown chuẩn có sẵn **Mục Lục (Table of Contents)** và các thẻ liên kết Anchor để dán trực tiếp vào **Jira, GitHub Issues, Confluence, Notion hoặc Obsidian**.

3. **`session.json`**:
   - Dữ liệu dạng JSON chứa đầy đủ toạ độ chuột `(x, y)`, thông tin chương mục (`is_section_header`, `section_title`), thời gian, tên tiến trình, tiêu đề cửa sổ cho các hệ thống phân tích tự động.

4. **`rec_XXXXXXXX.zip`**:
   - Gói nén chứa toàn bộ ảnh chụp PNG chất lượng cao và các tệp báo cáo.

---

## 🧪 Chạy kiểm thử tự động (Unit Tests)

Dự án đi kèm bộ test toàn diện:

```bash
python -m unittest tests/test_all.py
```

Kết quả: Toàn bộ **33** bài test tự động bao quát toàn bộ hệ thống (Config, Screen Capture, Marker Annotations, Drag Arrow, Focus Spotlight Crop, Cross-platform Window Info, Section Headers, Table of Contents, Jinja2 Template rendering, Mouse Up state machine, Unified Dual Capture, L2 Disk Spooling, Keystroke Aggregator và Lifecycle State) đều vượt qua **100% OK** trên cả Linux và Windows.

---

## 🔒 Bảo mật & Tối ưu

- **Bỏ qua thao tác gõ văn bản nhạy cảm**: Mặc định chỉ ghi nhận các phím điều khiển chức năng (`Enter`, `Tab`, `Escape`, phím tắt) để không vô tình lưu mật khẩu người dùng.
- **Chống spam sự kiện**: Tự động nhận diện double-click và loại trừ các cú click vào chính thanh công cụ của Step Recorder.
- **Tiến trình ngầm (Background Threading)**: Chụp và xử lý ảnh trên luồng riêng biệt, không làm lag hoặc khựng con trỏ chuột khi người dùng thao tác nhanh.

