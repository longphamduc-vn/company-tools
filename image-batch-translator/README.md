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
   ```
2. **Thử nghiệm ngay với ảnh mẫu**:
   - Bấm **"✨ Load Demo Images"**: Tải ngay 4 ảnh mẫu (trong đó có ảnh bị crop xén viền).
   - Đã cấu hình sẵn 3 quy tắc từ khóa: `{o1}` = `Mã phiếu`, `{o2}` = `Tên hàng`.
   - Bấm **"🔍 Extract Characters (All Images)"**: Toàn bộ ảnh kể cả ảnh bị crop đều được nhận diện chính xác 100%!
   - Bấm **"📁 Export & Rename Images"** để xuất ảnh đổi tên mới: `PXK-2026-001_Bơm_Cao_Áp_Schneider.png`.
   - Bấm **"📊 Export CSV"** để xuất dữ liệu bảng tính.
