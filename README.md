# Company Tools 🛠️

Kho lưu trữ tập trung (Monorepo) các công cụ, tiện ích phần mềm nội bộ chuyên dụng phục vụ tối ưu hóa sản xuất, xử lý dữ liệu hệ thống SCADA/MES và tự động hóa quy trình công việc.

---

## 📁 Danh Mục Các Dự Án Con (Sub-projects)

| Dự án | Thư mục | Mô tả | Công nghệ |
| :--- | :--- | :--- | :--- |
| **SCADA-TraceLog** | [`scada-tracelog/`](./scada-tracelog) | Giám sát & tạo nhật ký thay đổi thông số máy SCADA (Change Log), bẫy lỗi mất dữ liệu do giới hạn 256 cột của Excel .xls cũ. | Python, Tkinter/TTK, Pandas |
| **EMS Nexacro Extension** | [`ems-nexacro-extension/`](./ems-nexacro-extension) | Tiện ích mở rộng trình duyệt (Browser Extension) hỗ trợ tự động hóa và tối ưu giao diện EMS Nexacro. | JavaScript, Chrome Extensions API |
| **Google Keep Transfer Extension** | [`google-keep-transfer-extension/`](./google-keep-transfer-extension) | Tự động chia nhỏ (chunk) và truyền tải/tải xuống file văn bản qua Google Keep. | JavaScript, Chrome Extensions API |
| **Google Forms Collector Extension** | [`google-forms-collector-extension/`](./google-forms-collector-extension) | Tự động thu thập câu hỏi, đáp án, điểm số từ Google Forms, hỗ trợ gom nhiều trang và xuất ra Word, Markdown, Excel/CSV, JSON, Aiken. | JavaScript, Chrome Extensions API |
| **Image Batch Translator** | [`image-batch-translator/`](./image-batch-translator) | Nhận diện chữ (Google Lens OCR), dịch thuật hàng loạt (Google Translate), xóa chữ cũ với màu nền median, vẽ chữ dịch và tự động đổi tên file. | Python, Tkinter, Pillow, Chrome-Lens-Py, Deep-Translator |
| **Drawing Vault** | [`drawing-vault/`](./drawing-vault) | Tìm kiếm, tải hàng loạt và duyệt xem bản vẽ kỹ thuật (Batch Image Viewer) từ Vault nội bộ (FDM/Windchill) qua SSO. | Python, Tkinter, Pillow, Requests |
| **Python Step Recorder** | [`step-recorder/`](./step-recorder) | Công cụ thay thế Windows Steps Recorder (PSR) mã nguồn mở: ghi lại từng bước thao tác chuột, bàn phím, chụp màn hình gắn chỉ điểm, xuất báo cáo HTML/Markdown/ZIP. | Python, Tkinter, Pillow, MSS, Pynput, Jinja2 |
| **Outlook Rule Companion** | [`outlook-rule-manager/`](./outlook-rule-manager) | Quản lý, cấu hình tập trung và tự động hóa Rules cho Microsoft Outlook qua YAML: hỗ trợ tách file PST theo năm, kéo thả gán rule, không lo đầy quota. | Python, Tkinter, PyYAML, pywin32, openpyxl |

---

## 🚀 Hướng Dẫn Sử Dụng Từng Dự Án

Mỗi dự án con được tổ chức độc lập trong thư mục riêng kèm theo tài liệu hướng dẫn và môi trường thực thi:

### 1. SCADA-TraceLog (Chuyển đổi dữ liệu SCADA)
- Di chuyển vào thư mục:
  ```bash
  cd scada-tracelog
  ```
- Khởi chạy trên Linux / WSL:
  ```bash
  ./run_app.sh
  # hoặc: python main.py
  ```
- Khởi chạy trên Windows: Kích đúp vào file `run_app.bat`.

### 2. EMS Nexacro Extension (Tiện ích trình duyệt)
- Mở trình duyệt Chrome / Edge và truy cập `chrome://extensions/`.
- Bật **Developer mode** (Chế độ dành cho nhà phát triển).
- Chọn **Load unpacked** (Tải tiện ích đã giải nén) và trỏ tới thư mục `ems-nexacro-extension/`.

### 3. Google Forms Collector Extension (Thu thập câu hỏi Google Form)
- Mở trình duyệt Chrome / Edge và truy cập `chrome://extensions/`.
- Bật **Developer mode** (Chế độ dành cho nhà phát triển).
- Chọn **Load unpacked** (Tải tiện ích đã giải nén) và trỏ tới thư mục `google-forms-collector-extension/`.
- Mở bất kỳ Google Form nào, bấm **"Thu thập trang này"** hoặc **"Duyệt mọi trang"** để trích xuất đề thi.

### 4. Image Batch Translator (Dịch thuật ảnh & Đổi tên hàng loạt)
- Di chuyển vào thư mục:
  ```bash
  cd image-batch-translator
  ```
- Cài đặt thư viện:
  ```bash
  pip install -r requirements.txt
  ```
- Khởi chạy ứng dụng:
  ```bash
  python image_batch_translator.py
  ```

### 5. Drawing Vault (Tải & Xem Bản Vẽ Tự Động)
- Di chuyển vào thư mục:
  ```bash
  cd drawing-vault
  ```
- Cài đặt thư viện:
  ```bash
  pip install -r requirements.txt
  ```
- Khởi chạy Desktop Drawing Viewer GUI:
  ```bash
  ./run_app.sh
  # hoặc: python main.py gui
  ```
- Tải bản vẽ nhanh qua CLI:
  ```bash
  python main.py download --qcode QCAK09691 --name "Machine_2018021GC26"
  ```
- Tải hàng loạt từ file danh sách:
  ```bash
  python main.py batch --file sample_data/sample_qcodes.txt
  ```

### 6. Python Step Recorder (Thay thế Windows Steps Recorder)
- Di chuyển vào thư mục:
  ```bash
  cd step-recorder
  ```
- Cài đặt thư viện:
  ```bash
  pip install -r requirements.txt
  ```
- Khởi chạy thanh công cụ ghi hình nổi (Floating GUI):
  ```bash
  python run.py
  ```
- Hoặc ghi hình nhanh bằng dòng lệnh (CLI):
  ```bash
  python run.py --cli --title "Kiem thu quy trinh" --output ./recordings
  ```

### 7. Outlook Rule Companion (Quản lý Rule Outlook & Tách File Theo Năm)
- Di chuyển vào thư mục:
  ```bash
  cd outlook-rule-manager
  ```
- Cài đặt thư viện:
  ```bash
  pip install -r requirements.txt
  ```
- Khởi chạy ứng dụng trên Windows: Kích đúp vào file `run_app.bat` hoặc chạy `python main.py`.
- Khởi chạy ứng dụng trên Linux/WSL (chế độ mô phỏng): `./run_app.sh`.

---

## 🛠️ Môi Trường Phát Triển Khuyến Nghị (WSL / Conda)

Khuyến nghị sử dụng môi trường Conda `company-env` trên WSL Ubuntu:
```bash
conda activate company-env
```
