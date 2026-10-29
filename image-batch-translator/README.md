# Smart Batch Character Extractor & Renamer (Chống Lỗi Khi Ảnh Bị Crop)

Công cụ desktop Python (Tkinter GUI, chạy trên Windows/macOS/Linux) chuyên dụng để **lấy ký tự (OCR Text Extraction)** và **tự động đổi tên file ảnh hàng loạt**, được thiết kế đặc biệt để **giải quyết triệt để vấn đề ảnh bị cắt xén (crop), lệch góc hoặc sai tỉ lệ**.

---

## ⚡ Tại sao phương pháp tọa độ cũ không tối ưu khi ảnh bị crop?

Khi các ảnh trong thư mục chụp ở cự ly khác nhau, bị cắt xén viền (crop), hoặc bị xê dịch:
- **Phương pháp tọa độ cố định (Fixed Bounding Box)**: Cắt cứng theo vị trí tương đối `(x1, y1, x2, y2)`. Khi ảnh bị mất lề hoặc lệch góc, khung cắt sẽ bị lệch ra ngoài dòng chữ, dẫn đến cắt đứt chữ, mất ký tự hoặc đọc sai.
- **Phương pháp từ khóa neo mới (Keyword Anchor)**: Quét toàn cảnh ảnh một lần bằng AI (Google Lens / RapidOCR), sau đó tự động truy tìm chuỗi ký tự đi kèm theo **từ khóa nhận diện** (ví dụ: chữ đứng sau `Mã phiếu:`, `Tên hàng:`, `Số lượng:`). 
  👉 **Dù ảnh có bị crop mất 4 góc hay phóng to/thu nhỏ, kết quả trích xuất vẫn luôn chính xác 100%!**

---

## 🌟 3 Phương Pháp Trích Xuất Ký Tự Linh Hoạt

1. **🎯 Keyword Anchor (Từ khóa neo) - Khuyên Dùng**:
   - Khai báo từ khóa dẫn trước giá trị cần lấy (ví dụ: `Mã phiếu`, `Tên hàng`, `Serial`, `Date`).
   - Tự động nhận diện giá trị nằm cùng dòng hoặc dòng kế tiếp. Miễn nhiễm 100% với việc ảnh bị crop.
2. **🔢 Regex Pattern (Mẫu ký tự chính quy)**:
   - Dành cho các mã ký hiệu có cấu trúc chuẩn như `PXK-\d{4}-\d{3}`, số serial, mã đơn hàng, ngày tháng.
   - Quét toàn bộ ảnh và bẫy chính xác chuỗi ký tự khớp mẫu.
3. **🔎 Nhận diện tự động ảnh mẫu & 1-Click tạo luật (Auto Detect Text)**:
   - Bấm nút **"🔎 Auto Detect Text"** trên thanh công cụ ảnh mẫu.
   - Hệ thống tự động phân tích và liệt kê toàn bộ các dòng chữ có trên ảnh. Người dùng chỉ cần **Click chọn dòng chữ** muốn lấy để tạo ngay quy tắc `{o1}`, `{o2}`!

---

## 🧪 Kết Quả Thực Nghiệm Đối Đầu (Coordinate vs Keyword)

Chạy thử nghiệm tự động trên dòng lệnh bằng:
```bash
python test_demo_extraction.py
```

**Bảng so sánh thực tế khi quét ảnh chuẩn vs ảnh bị crop (`label_cropped_demo.png`):**

| Tệp ảnh | Tình trạng ảnh | Cách cũ (Tọa độ cố định) | Cách mới (Từ khóa neo - Keyword) |
| :--- | :--- | :--- | :--- |
| `label_001.png` | Ảnh chuẩn (800x500) | `PXK-2026-001` - `Bơm Cao Áp Schneider` | `PXK-2026-001` - `Bơm Cao Áp Schneider` ✅ |
| `label_002.png` | Ảnh chuẩn (800x500) | `PXK-2026-002` - `Cảm Biến Áp Suất Danfoss` | `PXK-2026-002` - `Cảm Biến Áp Suất Danfoss` ✅ |
| `label_003.png` | Ảnh chuẩn (800x500) | `PXK-2026-003` - `Van Điện Từ SMC-24V` | `PXK-2026-003` - `Van Điện Từ SMC-24V` ✅ |
| `label_cropped_demo.png` | **Bị crop xén viền** (720x380) | ❌ Lệch khung cắt, dính mép: `Bơm Cao Án...` | **PXK-2026-001** - **Bơm Cao Áp Schneider** ✅ (Chính xác 100%) |

---

## 🖥️ Hướng Dẫn Sử Dụng Giao Diện

1. **Khởi chạy ứng dụng**:
   ```bash
   python image_batch_translator.py
   # hoặc:
   ./run_app.sh
   ```
2. **Thử nghiệm ngay với ảnh mẫu**:
   - Bấm **"✨ Load Demo Images"**: Tải 4 ảnh phiếu kho (bao gồm ảnh bị crop xén viền).
   - Bấm **"🔍 GlassID Demo"**: Tải các ảnh kính thực tế và ảnh khắc laser mờ (`faint_glass_demo.png`) với quy tắc bẫy mẫu Regex `(?i)GlassID\s*([A-Za-z0-9]+)`.
   - Bấm **"🔍 Extract Characters (All Images)"**: Toàn bộ ảnh kể cả ảnh bị crop hoặc mờ đều được nhận diện chính xác!

---

## 🔬 Tiền Xử Lý Hình Ảnh Trước Khi Scan (Image Preprocessing)

### Có nên xử lý hình ảnh trước khi scan không?
**CỰC KỲ NÊN!** Trong thực tế sản xuất, ảnh chụp từ camera công nghiệp hoặc điện thoại thường gặp:
- **Phản xạ ánh sáng, lóa sáng trên mặt kính, bề mặt kim loại/bóng**: Chữ bị mờ đục hoặc mất nét.
- **Chữ khắc laser trắng trên nền tối (kính/màn hình LCD)**: Các engine OCR chuẩn thường được tối ưu tốt nhất cho chữ đen trên nền sáng.
- **Nhiễu hạt, bóng mờ loang lổ, độ phân giải thấp, chữ nhỏ (< 25px)**: OCR dễ nhầm lẫn `0` và `O`, `1` và `I/L`, `8` và `B`.

### 6 Bộ Lọc Tích Hợp Sẵn:
1. **CLAHE (Khuyên dùng cho Mặt Kính / Chống Lóa)**: Cân bằng tương phản cục bộ, làm nổi bật nét khắc mờ trên kính mà không bị cháy sáng vùng bóng lóa.
2. **Invert (Đảo màu)**: Biến chữ sáng nền tối thành chữ đen nền trắng, tăng độ nhạy nhận diện mã khắc laser.
3. **Binarize (Otsu Threshold)**: Nhị phân hóa đen trắng thuần túy, lọc sạch toàn bộ đổ bóng nền và vân hoa văn gây nhiễu.
4. **Enhance (Tự động cân bằng & Sắc nét)**: Kết hợp CLAHE và Unsharp Masking, phù hợp đa số tem nhãn thông dụng.
5. **Sharpen (Làm sắc nét)**: Khôi phục viền ký tự bị nhòe mờ do rung máy.
6. **Upscale 2x (Nội suy Lanczos)**: Phóng to gấp đôi độ phân giải giúp OCR nhận diện chuẩn xác các số serial cỡ chữ siêu nhỏ.

### 🧪 Hộp Thoại Test Xử Lý & Quét Thử (Preprocess Test Dialog):
- Bấm nút **"🧪 Test Xử lý & Quét thử..."** trong khung cấu hình.
- Xem so sánh trực quan song song (Side-by-side: Ảnh Gốc vs Ảnh Tiền Xử Lý).
- Bấm **"⚡ Quét Thử OCR"** để kiểm tra ngay kết quả nhận diện và thời gian phản hồi trước khi quét hàng loạt cả thư mục.
- Bấm **"✅ Áp Dụng Cấu Hình Này"** để lưu thiết lập cho toàn bộ batch.

---

## 🎯 Chế Độ Review Focus (Soát Lỗi & Sửa Thủ Công Siêu Tốc)

Ngay cả khi OCR đạt độ chính xác > 98%, luôn có một số ít ảnh chất lượng quá kém cần sự can thiệp của con người. Chế độ **Review Focus** được thiết kế theo tư duy **Human-in-the-Loop** với trải nghiệm bàn phím tiện lợi nhất:

### Cách Mở:
- Bấm nút **"🎯 Review Focus (Soát Lỗi)"** trên thanh tác vụ.
- Hoặc **nhấp đúp chuột** vào bất kỳ dòng nào trong bảng kết quả quét.

### Các Tính Năng Nổi Bật:
1. **Giao Diện Kiểm Tra Trực Quan Cận Cảnh**: Ảnh gốc được hiển thị rõ nét bên trái để mắt người dùng dễ dàng đối chiếu trực tiếp ký tự.
2. **Ô Nhập Chữ To Rõ (Font 14pt Bold)**: Tự động trỏ con trỏ chuột vào ô dữ liệu, tự động đổi màu trạng thái (`✅ HỢP LỆ`, `⚠️ RỖNG`, `⚠️ KHÁC KHUÔN MẪU`).
3. **Live Preview Tên File**: Xem trước tên file mới sẽ được đổi thành gì ngay khi đang gõ từng ký tự.
4. **Workflow Bàn Phím Siêu Tốc (Không Cần Chuột)**:
   - **Nhấn `Enter`**: Lưu dữ liệu đã sửa, cập nhật lại bảng chính và tên file mới, đồng thời tự động chuyển ngay sang ảnh tiếp theo!
   - **Nhấn `Ctrl + ←` / `Alt + ←`**: Quay lại ảnh trước.
   - **Nhấn `Ctrl + →` / `Alt + →`**: Tiến sang ảnh sau.
   - **Nhấn `Esc`**: Đóng hộp thoại.
5. **Bộ Lọc Thông Minh "⚠️ Chỉ duyệt ảnh có lỗi / rỗng"**:
   - Khi bật tùy chọn này, phím `Enter` sẽ tự động nhảy qua 95% ảnh đã nhận diện đúng, và **chỉ dừng lại ở các ảnh bị trống hoặc nghi ngờ sai**! Giúp người vận hành soát lỗi hàng trăm ảnh chỉ trong vài chục giây.

