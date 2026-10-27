# Google Keep Text File Transfer (Chrome Extension - Manifest V3)

Extension cho trình duyệt (Chrome, Brave, Edge, Cốc Cốc) hỗ trợ **tải lên (upload)** và **tải xuống (download)** các file text dung lượng lớn qua **Google Keep** (`keep.google.com`) bằng cơ chế tự động chia nhỏ (chunking) và ghép nối dữ liệu (reassembly).

---

## 🌟 Tính năng chính

1. **📤 Tách nhỏ & Tải lên Google Keep (Upload)**:
   - Hỗ trợ mọi loại file văn bản: `.txt`, `.json`, `.csv`, `.md`, `.js`, `.py`, `.xml`, `.yml`, `.log`, hoặc dán trực tiếp đoạn text dài.
   - Tự động chia nhỏ nội dung thành các phần an toàn (mặc định 10.000 ký tự/ghi chú để đảm bảo không vượt giới hạn lưu trữ của Google Keep).
   - Đặt tiêu đề ghi chú tự động theo cấu trúc chuẩn:
     `[KeepTransfer] <tên_file> | Part <số_thứ_tự>/<tổng_số_phần> | ID:<mã_file>`
   - Tự động điền dữ liệu vào ô soạn thảo của Keep (`contenteditable`), kích hoạt lưu và đóng ghi chú tuần tự với độ trễ tối ưu (chống lag / rate limit).
   - Thanh tiến trình trực quan (% hoàn thành, số ghi chú đã tạo, nhật ký hoạt động trực tiếp).

2. **📥 Tự động quét & Ghép lại file gốc (Download & Reassembly)**:
   - **Quét nhanh (Quick Scan)**: Quét các thẻ ghi chú đang hiển thị trên giao diện Keep.
   - **Quét toàn diện (Deep Scan - Cuộn không sót)**: Tự động cuộn trang Keep xuống cuối và mở chi tiết từng ghi chú để trích xuất 100% nội dung (kế thừa thuật toán `extractAllKeepNotesNoOmission`).
   - Tự động phân tích tiêu đề, nhóm các phần thuộc cùng 1 file, kiểm tra tính toàn vẹn (đủ X/X phần hay còn thiếu phần nào).
   - Ghép đúng thứ tự các phần (`Part 1 -> Part 2 -> ... -> Part N`) và tải xuống trực tiếp dưới tên file gốc.
   - Cho phép xem trước (Preview) và sao chép nhanh (Copy to Clipboard).

3. **📑 Gộp thủ công (Manual Merger)**:
   - Cho phép chọn bất kỳ ghi chú nào đã quét trong Keep.
   - Tùy chọn dấu ngắt dòng khi ghép: Nối liền, Xuống dòng (`\n`), Cách đoạn (`\n\n`), hoặc Dấu phân cách (`---`).
   - Xuất dữ liệu thành file text hoặc file JSON đầy đủ.

4. **⚙️ Tùy biến linh hoạt**:
   - Tùy chỉnh kích thước mỗi phần: 5.000 / 10.000 / 15.000 / 18.000 ký tự.
   - Tùy chỉnh độ trễ giữa các ghi chú: 400ms / 800ms / 1.200ms / 2.000ms.
   - Đổi tiền tố nhận diện (`[KeepTransfer]`, `[MyDrop]`, v.v.).

---

## 📂 Cấu trúc thư mục dự án

```
google-keep-transfer-extension/
├── manifest.json       # Cấu hình Manifest V3
├── background.js      # Service Worker xử lý tải file & tab
├── content.js         # Tương tác trực tiếp với DOM Google Keep (Tạo & Trích xuất ghi chú)
├── popup.html         # Giao diện người dùng
├── popup.css          # CSS thiết kế Dark Mode hiện đại
├── popup.js           # Logic chia tách, ghép nối và điều khiển
├── icons/             # Bộ icon chuẩn Chrome Extension (16, 32, 48, 128)
└── README.md          # Tài liệu hướng dẫn
```

---

## 🚀 Hướng dẫn cài đặt

1. Mở trình duyệt Chrome hoặc trình duyệt nhân Chromium bất kỳ (Brave, Edge, Cốc Cốc).
2. Truy cập vào trang quản lý tiện ích:
   ```
   chrome://extensions/
   ```
3. Bật công tắc **"Chế độ dành cho nhà phát triển" (Developer mode)** ở góc trên bên phải.
4. Bấm nút **"Tải tiện ích đã giải nén" (Load unpacked)**.
5. Chọn thư mục dự án:
   ```
   /home/longp/projects/company-tools/google-keep-transfer-extension
   ```
6. Tiện ích **Google Keep Text File Transfer** sẽ xuất hiện trên thanh công cụ của trình duyệt!

---

## 📖 Hướng dẫn sử dụng

### 1. Upload file văn bản lên Keep:
1. Mở trang [https://keep.google.com/](https://keep.google.com/) trên trình duyệt.
2. Bấm vào icon tiện ích trên thanh công cụ.
3. Kéo thả file text hoặc bấm để chọn file từ máy tính.
4. Xem trước số lượng ghi chú dự kiến được tách.
5. Bấm nút **"Tách file & Tải lên Google Keep"**. Tiện ích sẽ tự động tạo từng ghi chú trên Google Keep theo đúng thứ tự.

### 2. Ghép và Tải file gốc về máy:
1. Mở trang [https://keep.google.com/](https://keep.google.com/).
2. Mở popup tiện ích, chuyển sang tab **"Ghép & Tải xuống"**.
3. Bấm **"Quét nhanh"** (nếu ghi chú đang ở đầu trang) hoặc **"Quét toàn diện"** (để cuộn toàn bộ trang nạp tất cả ghi chú).
4. Tiện ích sẽ tự động nhận diện các file đã được chia nhỏ, hiển thị trạng thái `Đủ X/X phần ✅`.
5. Bấm nút **"📥 Tải xuống (.txt)"** để tải về file đã ghép hoàn chỉnh.
