# Company Tools 🛠️

Kho lưu trữ tập trung (Monorepo) các công cụ, tiện ích phần mềm nội bộ chuyên dụng phục vụ tối ưu hóa sản xuất, xử lý dữ liệu hệ thống SCADA/MES và tự động hóa quy trình công việc.

---

## 📁 Danh Mục Các Dự Án Con (Sub-projects)

| Dự án | Thư mục | Mô tả | Công nghệ |
| :--- | :--- | :--- | :--- |
| **SCADA-TraceLog** | [`scada-tracelog/`](./scada-tracelog) | Giám sát & tạo nhật ký thay đổi thông số máy SCADA (Change Log), bẫy lỗi mất dữ liệu do giới hạn 256 cột của Excel .xls cũ. | Python, Tkinter/TTK, Pandas |
| **EMS Nexacro Extension** | [`ems-nexacro-extension/`](./ems-nexacro-extension) | Tiện ích mở rộng trình duyệt (Browser Extension) hỗ trợ tự động hóa và tối ưu giao diện EMS Nexacro. | JavaScript, Chrome Extensions API |
| **Image Batch Translator** | [`image-batch-translator/`](./image-batch-translator) | Nhận diện chữ (Google Lens OCR), dịch thuật hàng loạt (Google Translate), xóa chữ cũ với màu nền median, vẽ chữ dịch và tự động đổi tên file. | Python, Tkinter, Pillow, Chrome-Lens-Py, Deep-Translator |
| **LGD Drawing Vault** | [`lgd-drawing-vault/`](./lgd-drawing-vault) | Tìm kiếm, tải hàng loạt và duyệt xem bản vẽ kỹ thuật (Batch Image Viewer) từ Vault nội bộ LGD (FDM/Windchill) qua SSO. | Python, Tkinter, Pillow, Requests |

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

### 3. Image Batch Translator (Dịch thuật ảnh & Đổi tên hàng loạt)
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

### 4. LGD Drawing Vault (Tải & Xem Bản Vẽ Tự Động)
- Di chuyển vào thư mục:
  ```bash
  cd lgd-drawing-vault
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

---

## 🛠️ Môi Trường Phát Triển Khuyến Nghị (WSL / Conda)

Khuyến nghị sử dụng môi trường Conda `company-env` trên WSL Ubuntu:
```bash
conda activate company-env
```
