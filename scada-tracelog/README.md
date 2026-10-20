# SCADA-TraceLog 🚀
### *Industrial SCADA Recipe Change Tracker & 256-Column Data Loss Guard*

[![Python Version](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)]()
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey.svg)]()

**SCADA-TraceLog** là giải pháp phần mềm Python hoàn chỉnh được thiết kế dành riêng cho các kỹ sư tự động hóa, kỹ sư dữ liệu nhà máy và quản lý sản xuất. Ứng dụng tự động hóa việc đọc dữ liệu xuất hàng ngang từ máy SCADA, giám sát lỗi mất cột do giới hạn 256 cột của Excel cũ (`.xls`), và chuyển đổi thành **Nhật ký thay đổi** (Change Log / Audit Trail) dạng hàng dọc chuẩn hóa phục vụ công tác kiểm toán và truy vết công thức (**RECIPE**).

---

## 🎯 Điểm Nổi Bật

1. **Giao diện Tiếng Anh 100% Chuyên Nghiệp (Tkinter/TTK)**:
   - Giao diện người dùng đồ họa hiện đại, siêu nhẹ, không phụ thuộc vào các framework nặng nề.
   - Cơ chế đa luồng (**Multi-threading**): Xử lý file lớn hoàn toàn ở luồng ngầm (Background Worker), không làm đơ giao diện.
   - Tự động ghi nhớ cấu hình (**Preference Persistence**): Tự lưu thư mục làm việc và các tùy chọn vào file cấu hình để tiện cho các phiên làm việc tiếp theo.

2. **Cơ Chế Bảo Vệ Dữ Liệu 256 Cột (256-Column Limit Guard)**:
   - File Excel `.xls` cũ (BIFF8) chỉ hỗ trợ tối đa 256 cột. Trong khi đó, mỗi thông số SCADA đòi hỏi đủ bộ 3 cột liên tiếp: `[VALUE, Giá trị dưới, Giá trị trên]`.
   - Thuật toán tự động kiểm tra số dư modulo: `(Tổng số cột - Số cột metadata) % 3`.
   - Nếu phát hiện thông số cuối cùng bị cắt cụt (thiếu 1 hoặc 2 cột): **Lập tức dừng xử lý file** và bắn hộp thoại cảnh báo:
     ```text
     DATA LOSS WARNING: File [Tên_File] is missing column data due to Excel 256-column limit at parameter [Tên_Thông_Số]!
     ```

3. **Lõi Xử Lý Pandas Vectorized Hiệu Năng Cao**:
   - Reshape (xoay ma trận) từ ngang sang dọc trong tích tắc nhờ vectorization.
   - So sánh biến động giá trị `VALUE` với mốc thời gian liền kề trước đó của cùng một `RECIPE ID` bằng toán tử `shift(1)`.
   - Hỗ trợ linh hoạt: Chỉ ghi nhận các lần đổi giá trị (**Strict Transitions**) hoặc kèm cả giá trị ban đầu (**Initial Baseline**).

4. **Xuất File CSV Tương Thích Excel Tuyệt Đối**:
   - File CSV kết quả được mã hóa **`utf-8-sig`** (UTF-8 with BOM): Người dùng chỉ cần click đúp là mở trực tiếp bằng Microsoft Excel, không lỗi font Tiếng Việt, hiển thị đúng các cột để quét chuột sao chép / dán (Copy-Paste) linh hoạt.

---

## 📁 Cấu Trúc Thư Mục Dự Án (Project Structure)

```text
company-tools/
│
├── scada_tracelog/                   # Package chính của dự án
│   ├── __init__.py                   # Khởi tạo package và metadata
│   ├── app.py                        # Khởi động ứng dụng Tkinter
│   │
│   ├── core/                         # Lõi thuật toán & xử lý dữ liệu
│   │   ├── __init__.py
│   │   ├── exceptions.py             # Custom Exception: Excel256ColumnLimitError
│   │   ├── validator.py              # Kiểm tra cấu trúc & bẫy lỗi 256 cột
│   │   ├── transformer.py            # Vectorized Unpivot từ ngang sang dọc
│   │   ├── change_detector.py        # Dò tìm bước nhảy giá trị VALUE
│   │   └── processor.py              # Điều phối toàn bộ quy trình ETL
│   │
│   ├── gui/                          # Giao diện đồ họa (Tkinter / TTK)
│   │   ├── __init__.py
│   │   ├── app_window.py             # Cửa sổ ứng dụng chính (100% Tiếng Anh)
│   │   └── theme.py                  # Bảng màu, High-DPI Windows, định dạng widget
│   │
│   └── utils/                        # Tiện ích bổ trợ
│       ├── __init__.py
│       ├── config_manager.py         # Lưu và tải cấu hình người dùng
│       └── file_helpers.py           # Mở thư mục / file đa nền tảng
│
├── tests/                            # Bộ kiểm thử tự động (Unit Tests)
│   ├── __init__.py
│   ├── test_validator.py             # Kiểm tra bắt lỗi 256 cột
│   ├── test_transformer.py           # Kiểm tra trích xuất tên thông số
│   └── test_change_detector.py       # Kiểm tra thuật toán phát hiện thay đổi
│
├── samples/                          # Dữ liệu mẫu kiểm thử
│   ├── sample_valid.xlsx             # File dữ liệu mẫu hợp lệ
│   └── sample_256_truncated.xlsx     # File dữ liệu mẫu bị cụt cột 256
│
├── scripts/                          # Script hỗ trợ vận hành & đóng gói
│   ├── build_exe.bat                 # Đóng gói thành file .exe độc lập
│   └── run_tests.bat                 # Chạy toàn bộ test suite
│
├── main.py                           # File khởi chạy chính từ thư mục gốc
├── run_app.bat                       # Kích đúp là chạy ngay trên Windows
├── scada_converter.py                # Alias tương thích ngược
├── requirements.txt                  # Danh sách thư viện cần thiết
├── pyproject.toml                    # Cấu hình đóng gói chuẩn PEP 621
├── setup.py                          # Cài đặt dạng package (`pip install -e .`)
├── .gitignore                        # Cấu hình bỏ qua file tạm, cache, lock
└── README.md                         # Tài liệu hướng dẫn chi tiết
```

---

## 🛠️ Hướng Dẫn Cài Đặt

### 1. Yêu cầu hệ thống
- **Python**: Phiên bản 3.9 trở lên (đã kiểm thử ổn định trên Python 3.10, 3.11, 3.12, 3.13).
- **Hệ điều hành**: Windows 10/11, Linux (Ubuntu, Debian, RHEL) hoặc macOS.

### 2. Cài đặt thư viện
Tại thư mục gốc của dự án, mở Terminal / PowerShell và thực thi:
```bash
pip install -r requirements.txt
```

*(Tùy chọn) Cài đặt dự án dưới dạng Python CLI Package:*
```bash
pip install -e .
```
Sau lệnh này, bạn có thể gõ lệnh `scada-tracelog` ở bất kỳ đâu trong Command Prompt để mở ứng dụng!

---

## 🚀 Hướng Dẫn Sử Dụng

### Khởi chạy ứng dụng
- **Cách 1 (Nhanh nhất)**: Nhấp đúp chuột trái vào file **`run_app.bat`**.
- **Cách 2**: Chạy qua lệnh:
  ```bash
  python main.py
  ```

### Các bước thao tác trên giao diện
1. **1. Input Mode & Source**:
   - Chọn `Process Single File` (1 file đơn lẻ) hoặc `Process Entire Folder` (quét toàn bộ thư mục).
   - Nhấn nút **`Browse...`** để chọn file hoặc thư mục nguồn.
2. **2. Conversion Settings**:
   - **Parameter Name Format**:
     - `Description Only (inside [...])`: Lấy phần mô tả chức năng trong ngoặc (Ví dụ: `OuterPeel_FILM_Peel_BLOW_TIME`).
     - `Full Original Tag Name`: Giữ nguyên tên gốc (Ví dụ: `29TF01_ZR8450[...]`).
     - `Device Code + Description`: Tách thành dạng `29TF01_ZR8450 - OuterPeel...`.
   - **Include Initial Baseline**: Tích chọn nếu muốn xuất cả mốc thiết lập ban đầu của từng Recipe ID. Bỏ chọn nếu chỉ muốn xuất các mốc thực sự biến động giá trị.
   - **Auto-open CSV output when completed**: Tự động mở file kết quả sau khi hoàn thành.
3. **3. Action & Execution Console**:
   - Nhấn **`START CONVERSION`** để thực thi.
   - Theo dõi tiến trình qua thanh tiến độ và hộp thoại Console log thời gian thực.
   - Nhấn **`Open Output Directory`** để mở nhanh thư mục chứa file CSV kết quả.

---

## 🧪 Kiểm Thử Tự Động (Automated Testing)

Dự án đi kèm bộ kiểm thử toàn diện bảo vệ mọi tính năng cốt lõi. Để chạy test:

```bash
python -m unittest discover tests
```
*Hoặc nhấp đúp vào `scripts/run_tests.bat` trên Windows.*

---

## 📦 Đóng Gói Thành File `.exe` Độc Lập (Standalone Windows Executable)

Nếu bạn muốn chuyển giao công cụ cho các kỹ sư vận hành nhà máy mà **không yêu cầu máy tính của họ phải cài đặt Python**:
1. Nhấp đúp vào file **`scripts/build_exe.bat`**.
2. Script sẽ tự động đóng gói toàn bộ mã nguồn, thư viện `pandas` và `openpyxl` vào một file duy nhất:
   ```text
   dist/SCADA-TraceLog/SCADA-TraceLog.exe
   ```
3. Copy toàn bộ thư mục `dist/SCADA-TraceLog` sang bất kỳ máy tính Windows nào để chạy trực tiếp!
