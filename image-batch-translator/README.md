# Smart Batch Character Extractor & Renamer (Crop-Resilient)

Ứng dụng desktop hoàn chỉnh bằng Python (Tkinter GUI, chạy trên Windows/macOS/Linux) chuyên dụng để **lấy ký tự (OCR Text Extraction)**, **focus cận cảnh vị trí ký tự** và **tự động đổi tên file ảnh hàng loạt**. Ứng dụng giải quyết triệt để vấn đề ảnh bị cắt xén (crop), lệch góc hoặc mặt kính phản xạ/khắc laser mờ.

---

## 🏗️ Cấu Trúc Ứng Dụng Hoàn Chỉnh (Modular Architecture)

Mã nguồn đã được tách nhỏ thành kiến trúc gói module `app/` chuẩn production, sạch sẽ, dễ bảo trì và mở rộng:

```
image-batch-translator/
├── app/                                 # Gói module ứng dụng chính
│   ├── __init__.py                      # Khởi tạo gói và phiên bản
│   ├── config.py                        # Cấu hình, Theme giao diện, hằng số và kiểm tra thư viện
│   ├── utils.py                         # Sắp xếp tự nhiên, chuẩn hóa tên file, template đặt tên
│   ├── ocr_engine.py                    # Tiền xử lý ảnh (CLAHE, Otsu, Invert, Lanczos 2x) & OCR Runners
│   ├── extraction.py                    # Thuật toán trích xuất (Keyword, Regex, Box) & Định vị Bounding Box (ROI)
│   ├── ui/                              # Giao diện người dùng
│   │   ├── __init__.py                  # Xuất các thành phần UI
│   │   ├── preprocess_dialog.py         # Hộp thoại so sánh song song và test bộ lọc tiền xử lý
│   │   ├── review_focus_dialog.py       # Hộp thoại Soát Lỗi với TÍNH NĂNG FOCUS VÀO VỊ TRÍ
│   │   └── main_window.py               # Cửa sổ chính của ứng dụng
│   └── main.py                          # Khởi tạo và khởi động ứng dụng
├── main.py                              # Điểm khởi chạy chuẩn
├── image_batch_translator.py            # Điểm khởi chạy tương thích ngược
├── run_app.sh                           # Script khởi chạy nhanh trên Linux/macOS
├── run_app.bat                          # Script khởi chạy trên Windows
├── requirements.txt                     # Danh sách thư viện phụ thuộc
├── sample_images/                       # Bộ ảnh mẫu kiểm thử (Phiếu kho & Mặt kính GlassID)
└── README.md                            # Tài liệu hướng dẫn sử dụng
```

---

## 🎯 Tính Năng Focus Vào Vị Trí Ký Tự (ROI Auto-Focus & Zoom)

Trong các ảnh chụp thực tế (như tem phiếu kho hoặc mặt kính sản xuất), chữ cần đọc chỉ chiếm một góc nhỏ trên ảnh toàn cảnh. Khi ảnh được thu nhỏ để vừa màn hình, mắt người vận hành rất khó nhìn rõ các ký tự chi tiết (ví dụ: phân biệt `DLLLLLL1` với `DLLLLLL2`, `0` với `O`).

Tính năng **Focus Vào Vị Trí** giải quyết triệt để bài toán này:

1. **Tự Động Cắt & Phóng To Cận Cảnh (ROI Zoom)**:
   - Hệ thống tự động tính toán tọa độ bounding box của chuỗi ký tự được trích xuất (từ kết quả RapidOCR hoặc quy tắc vùng).
   - Tự động lấy thêm vùng đệm (padding context) xung quanh để người xem thấy cả phần ngữ cảnh.
   - Phóng to vùng chứa chữ lên mức tối đa vừa vặn màn hình canvas, hiển thị từng nét chữ to, rõ, sắc nét!
2. **Viền Highlight Neon Rực Rỡ (Neon Bounding Box)**:
   - Khung viền kép phát sáng: Viền ngoài Cyan Neon (`#0284c7`), viền trong Emerald Lime (`#10b981`).
   - Huy hiệu nổi (badge) hiển thị ngay phía trên khung chữ: `🎯 [Tên trường]: [Giá trị trích xuất]`.
3. **Auto-Focus Theo Con Trỏ Nhập Liệu (Keyboard-Driven)**:
   - Khi nhấp chuột hoặc nhấn **`Tab` / `Shift+Tab`** chuyển sang ô nhập liệu của trường nào, ảnh bên trái **tự động nhảy và phóng to ngay lập tức vào vị trí của trường đó**!
4. **Bộ Phím & Nút Điều Khiển Linh Hoạt**:
   - `[🎯 Focus Vào Vị Trí]`: Bật/tắt chế độ tự động focus cận cảnh ROI.
   - `[🖼️ Toàn Cảnh]`: Xem lại ảnh nguyên bản với khung viền highlight.
   - `[🔍 +]` / `[🔍 -]` / `[1:1]`: Phóng to thêm, thu nhỏ hoặc đưa về tỉ lệ 100%.

---

## 🌟 3 Phương Pháp Trích Xuất Ký Tự Linh Hoạt

1. **🎯 Keyword Anchor (Từ khóa neo) - Chống Lỗi Khi Ảnh Bị Crop 100%**:
   - Khai báo từ khóa dẫn trước giá trị cần lấy (ví dụ: `Mã phiếu`, `Tên hàng`, `Serial`, `Date`).
   - Dù ảnh chụp bị crop mất 4 góc, mất lề hay xê dịch, hệ thống vẫn tìm thấy từ khóa và trích xuất đúng chuỗi ký tự phía sau.
2. **🔢 Regex Pattern (Mẫu ký tự chính quy)**:
   - Dành cho các mã có định dạng cố định, ví dụ GlassID: `(?i)GlassID\s*([A-Za-z0-9]+)` hoặc phiếu xuất kho `PXK-\d{4}-\d{3}`.
   - Tự động bẫy chính xác nhóm ký tự cần lấy trong ngoặc đơn `(...)`.
3. **🔎 Nhận diện tự động ảnh mẫu & 1-Click tạo luật (Auto Detect Text)**:
   - Bấm nút **"🔎 Nhận Diện Text"** trên thanh công cụ ảnh mẫu.
   - Hệ thống tự động phân tích và liệt kê toàn bộ các dòng chữ có trên ảnh. Người dùng chỉ cần click chọn dòng chữ muốn lấy để tạo ngay quy tắc `{o1}`, `{o2}`!

---

## 🔬 Tiền Xử Lý Hình Ảnh Trước Khi Scan (Image Preprocessing)

Đặc biệt tối ưu cho **mặt kính, bề mặt kim loại bóng, chữ khắc laser mờ hoặc tem nhãn bị lóa sáng**:

1. **CLAHE (Khuyên dùng cho Mặt Kính / Chống Lóa)**: Cân bằng tương phản thích ứng cục bộ, làm nổi bật nét khắc mờ trên kính mà không bị cháy sáng vùng bóng lóa.
2. **Invert (Đảo màu)**: Biến chữ sáng nền tối thành chữ đen nền trắng, tăng độ nhạy nhận diện mã khắc laser.
3. **Binarize (Otsu Threshold)**: Nhị phân hóa đen trắng thuần túy, lọc sạch toàn bộ đổ bóng nền và vân hoa văn gây nhiễu.
4. **Enhance (Tự động cân bằng & Sắc nét)**: Kết hợp CLAHE và Unsharp Masking, phù hợp đa số tem nhãn thông dụng.
5. **Sharpen (Làm sắc nét)**: Khôi phục viền ký tự bị nhòe mờ do rung máy.
6. **Upscale 2x (Nội suy Lanczos)**: Phóng to gấp đôi độ phân giải giúp OCR nhận diện chuẩn xác các số serial cỡ chữ siêu nhỏ.

### 🧪 Hộp Thoại Test Xử Lý & Quét Thử (Preprocess Test Dialog):
- Bấm nút **"🧪 Test Xử lý & Quét thử..."** trong khung cấu hình.
- Xem so sánh trực quan song song (Side-by-side: Ảnh Gốc vs Ảnh Tiền Xử Lý).
- Bấm **"⚡ Quét Thử OCR"** để kiểm tra ngay kết quả nhận diện và thời gian phản hồi trước khi quét hàng loạt cả thư mục.

---

## ⌨️ Phím Tắt Soát Lỗi Siêu Tốc (Human-in-the-Loop Review)

Trong hộp thoại **🎯 Review Focus**:
- **Nhấn `Enter`**: Lưu dữ liệu trường hiện tại, cập nhật tên file mới và chuyển ngay sang ảnh tiếp theo!
- **Nhấn `Ctrl + ←` / `Alt + ←`**: Quay lại ảnh trước.
- **Nhấn `Ctrl + →` / `Alt + →`**: Chuyển sang ảnh sau.
- **Nhấn `Esc`**: Đóng hộp thoại.
- **Tùy chọn `⚠️ Chỉ duyệt ảnh có lỗi / rỗng`**: Bỏ qua 95% ảnh đã nhận diện đúng, chỉ dừng lại tại các ảnh bị trống hoặc nghi ngờ sai định dạng.

---

## 🚀 Hướng Dẫn Cài Đặt & Chạy Ứng Dụng

### 1. Cài đặt thư viện:
```bash
pip install -r requirements.txt
```
*(Hoàn toàn KHÔNG cần cài đặt tesseract-ocr binary từ hệ thống!)*

### 2. Khởi chạy:
```bash
python main.py
# hoặc:
python image_batch_translator.py
# hoặc:
./run_app.sh
```

### 3. Thử nghiệm với các bộ demo có sẵn:
- **Demo Nhãn Hàng**: Bấm nút **"✨ Demo Nhãn Hàng"** để tải 4 ảnh phiếu kho (gồm cả ảnh bị crop xén viền).
- **Demo Mặt Kính (GlassID)**: Bấm nút **"🔍 Demo GlassID"** để tải ảnh kính và ảnh khắc laser mờ (`faint_glass_demo.png`).
- Bấm **"🚀 Quét Ký Tự Hàng Loạt"** rồi bấm **"🎯 Review Focus"** để trải nghiệm tính năng Focus phóng to vị trí ký tự!
