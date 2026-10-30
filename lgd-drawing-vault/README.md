# LGD Drawing Vault - Trình Tải & Xem Hàng Loạt Bản Vẽ Kỹ Thuật 📐

Phần mềm chuyên dụng phục vụ kỹ sư: **Tìm kiếm, tải xuống hàng loạt (Batch Downloader) và duyệt xem bản vẽ kỹ thuật trực quan (Batch Image & Blueprint Viewer)** từ hệ thống Vault nội bộ LG Display (FDM / Windchill), tự động kết nối qua SSO Local Agent.

---

## 🌟 Tính Năng Chính

1. **Bảng Nhập Liệu Dạng Excel (Excel-like Input Grid)**:
   - Giao diện bảng tương tác trực quan với các cột: `#`, `Mã QCode`, `Tên Thiết Bị / Alias`, `Trạng Thái`.
   - **Copy & Paste trực tiếp từ Microsoft Excel / Google Sheets**:
     - Người dùng chỉ cần copy một hoặc nhiều cột trong file Excel rồi bấm `Ctrl+V` (hoặc nút "📋 Dán từ Excel"), hệ thống sẽ tự động bóc tách từng dòng và phân tách cột (hỗ trợ tab-delimited và comma-delimited).
     - Hỗ trợ dán đồng thời hàng chục đến hàng trăm mã bản vẽ chỉ trong 1 giây.
     - Tự động phát hiện và bỏ qua dòng tiêu đề (Header).
   - **Chỉnh sửa ô trực tiếp (In-place Cell Editing)**:
     - Kích đúp (Double-click) hoặc nhấn `Enter` vào bất kỳ ô nào để sửa trực tiếp.
     - Bấm `Tab` để hoàn thành ô hiện tại và tự động chuyển sang chỉnh sửa ô kế tiếp hoặc tự động thêm dòng mới như Excel.
   - Các nút thao tác nhanh: `➕ Thêm dòng`, `➖ Xóa dòng`, `📁 Nhập file (.xlsx, .xls, .csv, .txt)`, `🗑️ Xóa hết`.
2. **Đa Chế Độ Xem Bản Vẽ & Danh Sách Ảnh (Dual View Modes)**:
   - **Chế độ 1: 🖼️ Xem Chi Tiết (Interactive Blueprint Canvas)**:
     - Xem bản vẽ kỹ thuật phóng to/thu nhỏ độ phân giải cao.
     - Thu phóng bằng con lăn chuột (Mouse Wheel), kéo rê (Pan) chuột trái, Căn vừa (`Fit`), Xem gốc (`100%`).
     - Tích hợp **Dải xem nhanh ảnh thu nhỏ (Bottom Filmstrip)** ngay dưới chân bản vẽ giúp click chuyển đổi nhanh giữa các bản vẽ đã tải.
   - **Chế độ 2: 📑 Danh Sách Ảnh Thu Nhỏ (Thumbnail Card Gallery)**:
     - Hiển thị toàn bộ bản vẽ đã tải dưới dạng lưới các thẻ ảnh thu nhỏ (Image Cards Grid).
     - Mỗi thẻ hiển thị: Ảnh preview thu nhỏ, mã QCode in đậm, tên thiết bị, độ phân giải thực (`3840x2160`), dung lượng file (`1.4 MB`), trạng thái.
     - Kích đúp hoặc chọn thẻ bất kỳ để mở sang chế độ soi chi tiết.
3. **Điều Hướng Duyệt Ảnh Hàng Loạt Nhanh**:
   - Nút `⏮ Đầu`, `◀ Trước`, đếm số thứ tự `[ 5 / 42 ]`, `Sau ▶`, `Cuối ⏭`.
   - Phím tắt bàn phím: Mũi tên Trái `◀` / Phải `▶` chuyển ảnh tức thời.
   - Mở nhanh file gốc bằng trình xem ảnh Windows/Linux hoặc mở thư mục lưu trữ.
4. **Tải Hàng Loạt Tự Động (Batch Downloader)**:
   - Tải toàn bộ danh sách trong bảng Excel với thanh tiến trình trực quan (`Đang tải 12/45 (27%)`).
   - Cập nhật trạng thái từng dòng trong bảng Excel theo thời gian thực (`Chờ` -> `Đang tải...` -> `✅ Tải xong` / `❌ Lỗi`).
   - Nút `⏹ Dừng` tải khi cần.
   - Xuất toàn bộ báo cáo danh sách kết quả ra file `.csv`.
4. **Tự Động Kết Nối SSO Local Agent**:
   - Kết nối WebSocket cục bộ `ws://127.0.0.1:28083/`.
   - Trao đổi token tại `http://im.lgdisplay.com:8088/pdadmin/eai/eai.jsp`.
   - Quản lý phiên `session.json` với cơ chế TTL (2 giờ).
5. **Chính Sách Lọc Bản Vẽ (Non-CAD Policy)**:
   - Tự động bỏ qua các bản vẽ 3D CAD nặng (`typeName == "CAD"`).
   - Chỉ thu thập các định dạng ảnh trực quan 2D raster (JPG, PNG, GIF, BMP, TIFF, WebP).
6. **Tự Động Phục Hồi Lỗi**:
   - Tự động phát hiện tải lỗi `CORRUPT_PAYLOAD` (trả về HTML login thay vì binary) -> xóa session và thử lại.
   - Thông báo hướng dẫn bật SSO Agent trên cổng 28083 khi chưa khởi chạy.

---

## 📁 Cấu Trúc Thư Mục

```
lgd-drawing-vault/
├── lgd_vault/
│   ├── __init__.py
│   ├── config.py              # URL, cổng SSO 28083, TTL session
│   ├── models.py              # Schema dữ liệu (DrawingItem, DownloadResult, BatchDownloadSummary)
│   ├── exceptions.py          # Bảng mã lỗi phục hồi (WS_CONN_REFUSED, HTTP_401, CORRUPT_PAYLOAD, ...)
│   ├── session_manager.py     # Quản lý file session.json & kiểm tra TTL
│   ├── sso_client.py          # WebSocket client port 28083 & Token exchange
│   ├── drawing_service.py     # Tìm kiếm FDM, lọc CAD, scrape JSP, tải ảnh nhị phân & batch
│   └── viewer_app.py          # Giao diện Trình xem ảnh hàng loạt (Tkinter + Pillow)
├── sample_data/
│   ├── sample_qcodes.txt      # Mẫu danh sách QCode dạng text/csv
│   └── sample_batch.json      # Mẫu danh sách QCode dạng JSON
├── tests/
│   ├── test_session.py        # Kiểm thử TTL và lưu trữ cookie
│   ├── test_sso_client.py     # Kiểm thử WebSocket SSO & mock EAI
│   └── test_drawing_service.py# Kiểm thử tìm kiếm, lọc CAD, scrape & batch progress
├── main.py                    # Điểm khởi chạy CLI và GUI
├── run_app.sh                 # Script chạy nhanh trên Linux / WSL
├── run_app.bat                # Script chạy nhanh trên Windows
├── requirements.txt           # Thư viện phụ thuộc
└── README.md                  # Tài liệu hướng dẫn
```

---

## 🚀 Hướng Dẫn Sử Dụng

### 1. Kích hoạt môi trường Conda và cài đặt thư viện
```bash
conda activate company-env
cd lgd-drawing-vault
pip install -r requirements.txt
```

### 2. Khởi chạy Giao Diện Xem Ảnh Hàng Loạt (Desktop GUI)
- **Trên Linux / WSL**:
  ```bash
  ./run_app.sh
  # hoặc:
  python main.py gui
  ```
- **Trên Windows**:
  Kích đúp vào file `run_app.bat` hoặc chạy:
  ```cmd
  python main.py gui
  ```

### 3. Phím Tắt Khi Xem Ảnh Trên Giao Diện
| Phím Tắt | Chức Năng |
| :--- | :--- |
| `◀` (Mũi tên Trái) | Xem ảnh trước trong danh sách |
| `▶` (Mũi tên Phải) | Xem ảnh kế tiếp trong danh sách |
| `Home` / `End` | Nhảy về ảnh đầu tiên / ảnh cuối cùng |
| `Cuộn chuột` | Phóng to / Thu nhỏ ảnh tại vị trí chuột |
| `Kéo chuột trái` | Rê ảnh (Pan) qua lại khi đang zoom |
| `+` / `-` | Phóng to / Thu nhỏ |
| `F` | Căn ảnh vừa màn hình (Fit to Screen) |
| `0` | Trả về tỉ lệ gốc 100% |

### 4. Sử Dụng Dòng Lệnh (CLI)

- **Tải nhanh một bản vẽ theo QCode**:
  ```bash
  python main.py download --qcode QCAK09691 --name "Machine_2018021GC26"
  ```

- **Tải hàng loạt từ file danh sách**:
  ```bash
  python main.py batch --file sample_data/sample_qcodes.txt --dir downloaded_images
  ```

- **Kiểm tra trạng thái SSO**:
  ```bash
  python main.py auth
  python main.py auth --force
  ```

---

## 🧪 Chạy Bộ Kiểm Thử (Unit Tests)

```bash
cd lgd-drawing-vault
python -m unittest discover -s tests -p "test_*.py" -v
```
Toàn bộ các test cases cho Session TTL, WebSocket SSO, CAD Filter, Scraper Regex và Batch Download Progress đều chạy tự động và độc lập mà không cần kết nối mạng nội bộ thực tế khi chạy test.
