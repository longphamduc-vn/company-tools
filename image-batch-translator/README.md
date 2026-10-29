# Image Batch Character Extractor & Smart Renamer

Công cụ desktop Python (Tkinter GUI, chạy được trên Windows, macOS, Linux) chuyên dụng để **lấy ký tự (OCR Text Extraction)** từ các vùng chọn cố định trên hàng loạt hình ảnh có chung bố cục (như phiếu kho, hóa đơn, thẻ bài, chứng từ, ảnh chụp màn hình ứng dụng), tự động hiển thị ký tự ra bảng, cho phép chỉnh sửa, xuất ra file CSV và **tự động đổi tên file ảnh hàng loạt** theo mẫu định dạng dựa trên các ký tự đã lấy.

> 🚀 **Điểm cải tiến vượt trội**:
> - Đã **loại bỏ hoàn toàn Tesseract OCR** (không cần cài phần mềm ngoài, không cần cài đặt ngôn ngữ nặng nề).
> - Sử dụng 2 phương pháp nhận diện ký tự hiện đại nhất:
>   1. **Google Lens (Cloud AI)**: Độ chính xác 100% đối với tiếng Việt có dấu, tiếng Anh, mã hiệu, số series.
>   2. **RapidOCR (Local Offline)**: Chạy 100% cục bộ trên máy không cần kết nối mạng.
> - Tích hợp sẵn bộ ảnh mẫu thực nghiệm và tập lệnh tự động kiểm thử.

---

## 🌟 Tính Năng Chính

1. **Lấy ký tự thông minh theo vùng chọn (Multi-region Character Extraction)**:
   - Dùng chuột kéo thả trực tiếp trên ảnh mẫu để chọn các vùng chứa ký tự cần lấy.
   - Mỗi vùng được gán biến tự động: Vùng 1 là `{o1}`, Vùng 2 là `{o2}`, Vùng 3 là `{o3}`...
   - Tọa độ lưu theo tỉ lệ tương đối `[0.0 - 1.0]`, đảm bảo áp dụng chính xác cho toàn bộ các ảnh dù độ phân giải có lệch nhau nhẹ.
2. **Tự động đổi tên file ảnh theo ký tự lấy được (Batch Smart Renaming)**:
   - Mẫu đổi tên linh hoạt: `{o1}_{o2}`, `{index:03d}_{o1}`, `{name}_{o1}_{o2}`.
   - Ví dụ: Lấy mã phiếu `{o1}` là `PXK-2026-001` và tên hàng `{o2}` là `Bơm_Cao_Áp_Schneider` -> Tên file mới sẽ là `PXK-2026-001_Bơm_Cao_Áp_Schneider.png`.
   - Tự động làm sạch các ký tự cấm của hệ điều hành, bảo toàn tiếng Việt Unicode có dấu, tự động thêm đuôi `_2`, `_3` nếu bị trùng tên.
3. **Bảng hiển thị ký tự & Cho phép sửa trực tiếp (Inline Editing)**:
   - Hiển thị danh sách ký tự từng ảnh theo từng vùng.
   - **Nhấp đúp chuột** vào ô ký tự để chỉnh sửa thủ công nếu muốn. Tên file mới sẽ được cập nhật lại theo thời gian thực!
4. **Hai chế độ xuất ảnh linh hoạt**:
   - **Copy & Rename Original (Khuyên dùng)**: Sao chép ảnh gốc sang thư mục output và đổi sang tên mới dựa trên ký tự lấy được. Nhanh như chớp, giữ nguyên 100% chất lượng gốc!
   - **Inpaint & Stamp Text**: Xóa chữ cũ bằng màu nền median và in đè ký tự mới lên ảnh.
5. **Xuất dữ liệu ra file CSV (Export CSV)**:
   - Cho phép xuất toàn bộ bảng ký tự đã lấy ra tệp `.csv` (mở bằng Excel) để làm báo cáo, thống kê hoặc nhập liệu.
6. **Nút "Load Demo Images" (Tải ảnh mẫu)**:
   - Nạp ngay 3 ảnh mẫu kèm 3 vùng chọn chuẩn bị sẵn để kiểm thử ngay lập tức mà không cần chuẩn bị ảnh.

---

## 📦 Cài Đặt (Chỉ 1 Lệnh Duy Nhất)

Mở terminal / command prompt và chạy:

```bash
pip install pillow chrome-lens-py rapidocr-onnxruntime deep-translator
```
*(hoặc: `pip install -r requirements.txt`)*

---

## 🧪 Kết Quả Kiểm Thử Thực Tế (Automated Test)

Bạn có thể chạy kiểm thử tự động ngay trên terminal bằng lệnh:

```bash
python test_demo_extraction.py
```

**Kết quả kiểm thử từ 3 ảnh mẫu phiếu xuất kho trong `sample_images/`**:

```text
======================================================================
🚀 BẮT ĐẦU KIỂM THỬ TRÍCH XUẤT KÝ TỰ TỪ ẢNH MẪU (TEST OCR EXTRACTION)
📁 Thư mục ảnh mẫu: sample_images/
🖼️ Tổng số ảnh: 3 (label_001.png, label_002.png, label_003.png)
======================================================================

📌 Các vùng chọn mẫu (Regions):
  - Vùng 1 (Mã phiếu) -> Tọa độ: (190, 130, 480, 175) (Biến đổi tên: {o1})
  - Vùng 2 (Tên hàng) -> Tọa độ: (190, 200, 680, 245) (Biến đổi tên: {o2})
  - Vùng 3 (Trạng thái) -> Tọa độ: (190, 340, 480, 385) (Biến đổi tên: {o3})

🔍 ĐANG TIẾN HÀNH TRÍCH XUẤT BẰNG GOOGLE LENS (KHÔNG CẦN TESSERACT)...

📂 Tệp: label_001.png
   [Vùng 1 (Mã phiếu)]: "PXK-2026-001"
   [Vùng 2 (Tên hàng)]: "Bơm Cao Áp Schneider"
   [Vùng 3 (Trạng thái)]: "Đã Kiểm Tra"
   ✨ TÊN FILE MỚI ĐƯỢC TẠO: -> PXK-2026-001_Bơm_Cao_Áp_Schneider.png

📂 Tệp: label_002.png
   [Vùng 1 (Mã phiếu)]: "PXK-2026-002"
   [Vùng 2 (Tên hàng)]: "Cảm Biến Áp Suất Danfoss"
   [Vùng 3 (Trạng thái)]: "Chờ Xuất"
   ✨ TÊN FILE MỚI ĐƯỢC TẠO: -> PXK-2026-002_Cảm_Biến_Áp_Suất_Danfoss.png

📂 Tệp: label_003.png
   [Vùng 1 (Mã phiếu)]: "PXK-2026-003"
   [Vùng 2 (Tên hàng)]: "Van Điện Từ SMC-24V"
   [Vùng 3 (Trạng thái)]: "Hoàn Thành"
   ✨ TÊN FILE MỚI ĐƯỢC TẠO: -> PXK-2026-003_Van_Điện_Từ_SMC-24V.png

✅ KIỂM THỬ GOOGLE LENS HOÀN THÀNH XUẤT SẮC 100%!
======================================================================
```

---

## 🖥️ Hướng Dẫn Sử Dụng Giao Diện Đồ Họa

1. **Khởi chạy ứng dụng**:
   ```bash
   python image_batch_translator.py
   ```
   *(Hoặc kích đúp file `run_app.bat` trên Windows, `./run_app.sh` trên Linux/macOS)*

2. **Thử nghiệm nhanh**:
   - Bấm nút **"✨ Load Demo Images"** trên thanh tiêu đề: 3 ảnh mẫu kèm 3 vùng chọn chuẩn sẽ tự động được tải lên.
   - Bấm nút **"🔍 Extract Characters (OCR)"**: Ký tự từ các ảnh sẽ được trích xuất và hiển thị vào bảng bên dưới kèm theo tên file mới được tính toán.
   - Bấm **"📁 Export & Rename Images"**: Các ảnh đã được đổi tên theo đúng ký tự bên trong ảnh sẽ được xuất vào thư mục `sample_images/output`.
   - Bấm **"📊 Export CSV"**: Xuất danh sách ký tự ra file bảng tính.

3. **Áp dụng cho thư mục ảnh thực tế của bạn**:
   - Bấm **"📁 Choose Folder..."** để nạp ảnh của bạn.
   - Dùng chuột kéo thả các hình chữ nhật bao quanh các vùng chữ bạn muốn lấy.
   - Nhập mẫu đổi tên ở ô **Rename Template** (nhấp các nút `{o1}`, `{o2}`, `{name}` để chèn nhanh).
   - Bấm **"🔍 Extract Characters (OCR)"** và tiến hành xuất ảnh đổi tên.
