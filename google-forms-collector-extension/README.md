# Google Forms Question Collector (Chrome Extension - Manifest V3)

> Extension Chrome / Chromium tự động thu thập câu hỏi, các phương án lựa chọn, điểm số, hình ảnh và đáp án từ **Google Forms** (`docs.google.com/forms/*`). Hỗ trợ biểu mẫu nhiều trang, tự động duyệt trang và xuất ra các định dạng chuẩn: **Word/Văn bản, Markdown, Excel/CSV, JSON, Aiken (Moodle/LMS), và Đề thi in (HTML)**.

---

## 🌟 Tính Năng Nổi Bật

1. **📥 Thu Thập Nhanh 1 Click**:
   - Trích xuất toàn bộ câu hỏi trên trang hiện tại của Google Form chỉ với một nút bấm.
   - Hỗ trợ tất cả các dạng câu hỏi:
     - Trắc nghiệm 1 đáp án (`radio`)
     - Hộp kiểm nhiều đáp án (`checkbox`)
     - Tự luận ngắn (`short answer`) & Tự luận dài (`paragraph`)
     - Trình đơn thả xuống (`dropdown`)
     - Thang đo tuyến tính (`linear scale`) & Ma trận (`grid`)
   - Tự động nhận diện: Tiêu đề biểu mẫu, Chủ đề/Phần/Bài học (`Section`), Số điểm (`Points`), Câu hỏi bắt buộc (`*`), Hình ảnh đính kèm, Đáp án đúng & Giải thích (nếu ở chế độ xem lại bài thi).

2. **⚡ Tự Động Thu Thập Tất Cả Các Trang (1 Click Auto-Crawl)**:
   - Tích hợp thành **1 nút bấm duy nhất**: Bấm **"⚡ Tự động thu thập tất cả các trang"**, hệ thống sẽ tự động quét trang 1 -> điền câu hỏi bắt buộc -> bấm "Tiếp" -> chờ tải trang 2 -> quét tiếp tục tuần tự đến tận trang cuối cùng.
   - Khi đang chạy, nút chuyển sang trạng thái: **"⏹ Đang thu thập... Bấm dừng"** để người dùng có thể tạm dừng bất cứ lúc nào.
   - **Tự động điền & tick phương án thông minh (`Smart Async Bypass`)**: Tự động trả lời câu hỏi bắt buộc (Họ tên, mã số, radio, checkbox) với khoảng nghỉ hợp lý để Google Forms xác nhận hợp lệ mà không chặn nút "Tiếp".
   - **Nhận diện chuyển trang chính xác (`Visible Page Signature`)**: Chỉ căn cứ vào các phần tử hiển thị thực tế trên màn hình, nhận diện ngay khi trang kế tiếp vừa tải xong.
   - **An toàn tuyệt đối**: Hệ thống tự động nhận biết trang cuối cùng và dừng lại trước nút "Gửi" (`Submit`), tuyệt đối không tự ý nộp bài.

3. **✨ Widget Nổi Tiện Lợi Ngay Trên Google Form (In-Page Floating Widget)**:
   - Nút tròn nổi tinh tế ở góc dưới màn hình Google Form.
   - Hiển thị số lượng câu hỏi đã thu thập trong thời gian thực.
   - Thao tác nhanh với 1 nút bấm: **"⚡ Tự động thu thập tất cả các trang"**.
   - Có thể thu nhỏ hoặc ẩn nếu không muốn vướng tầm nhìn.

5. **📤 Đa Dạng Định Dạng Xuất File**:
   - **Văn bản chuẩn đề thi (`.txt` / `.doc`)**: Định dạng Câu 1, Câu 2... A, B, C, D rõ ràng, phân mục theo bài.
   - **Markdown (`.md`)**: Chuẩn tài liệu Markdown với heading, in đậm, danh sách hộp kiểm.
   - **Excel / CSV (`.csv`)**: Phân cột chi tiết (`STT, Phần/Bài, Nội dung câu hỏi, Điểm, Loại, Đáp án A, B, C, D..., Đáp án đúng, Ghi chú`). Hỗ trợ chuẩn **UTF-8 with BOM** giúp mở tiếng Việt không bao giờ bị lỗi font trên Microsoft Excel!
   - **JSON (`.json`)**: Dữ liệu có cấu trúc đầy đủ phục vụ lập trình viên hoặc import hệ thống.
   - **Aiken format (`.txt`)**: Định dạng chuẩn quốc tế để import trực tiếp đề thi trắc nghiệm vào **Moodle, Canvas, Blackboard**.
   - **HTML in đề thi (`.html`)**: Trang đề thi trình bày chuẩn, hỗ trợ in ấn (Print to PDF / In ra giấy A4).

6. **🔍 Quản Lý & Tìm Kiếm Câu Hỏi Trực Quan**:
   - Tìm kiếm nhanh câu hỏi theo từ khóa trong tiêu đề hoặc nội dung đáp án.
   - Lọc câu hỏi theo từng Phần / Bài học.
   - Xem trước các thẻ câu hỏi trực quan với các huy hiệu (Loại câu hỏi, Điểm số, Bắt buộc).
   - Xóa từng câu hoặc sao chép riêng từng câu dễ dàng.
   - Quản lý lịch sử các biểu mẫu đã từng quét và chuyển đổi qua lại.

---

## 📂 Cấu Trúc Thư Mục

```
google-forms-collector-extension/
├── manifest.json       # Cấu hình Manifest V3 của Chrome Extension
├── background.js      # Service worker xử lý badge icon và tải file
├── content.js         # Engine quét DOM, chuyển ảnh Base64, khử tiền tố, tích lũy dữ liệu, widget nổi và auto-crawl
├── content.css        # Giao diện widget nổi và thông báo toast trên trang Google Form
├── popup.html         # Giao diện chính của Extension Popup
├── popup.css          # Styling hiện đại với tông màu Google Forms Purple
├── popup.js           # Xử lý sự kiện popup, tìm kiếm, lọc, tạo preview, xuất file và tạo prompt Gemini
├── quiz_app.html      # Trang web tĩnh ôn tập trắc nghiệm toàn diện (Ôn tập, Thi thử, Flashcard, Đề in)
├── quiz_app.js        # Logic điều khiển ôn tập, tính giờ, flashcard và import/export đề thi
├── icons/             # Bộ icon độ phân giải cao 16x16, 32x32, 48x48, 128x128
├── test-data/         # Dữ liệu mẫu Google Form để kiểm thử
└── README.md          # Hướng dẫn chi tiết
```

---

## 🎓 Tính Năng Nâng Cao: Ôn Tập & Kết Hợp Trí Tuệ Nhân Tạo (Gemini)

### 1. Chuyển Toàn Bộ Hình Ảnh Thành Mã Base64 (Không Dùng Link Ngoài)
- Tất cả hình ảnh trong câu hỏi và trong phương án lựa chọn đều được chuyển đổi tự động thành mã **Base64 Data URL** (`data:image/png;base64,...`).
- Đảm bảo đề thi tự chứa 100% tài nguyên, xem offline hoàn toàn không lo ảnh bị hết hạn hay chết link từ máy chủ Google.

### 2. Thuật Toán Chống Trùng Khi Refresh / Xáo Trộn Thứ Tự (Shuffle Invariant)
- Nhiều đề thi Google Forms bật tính năng xáo trộn thứ tự câu hỏi và xáo trộn thứ tự đáp án mỗi khi tải lại trang.
- Extension sử dụng mã định danh mục gốc (`Google Forms Entry ID`) từ thuộc tính `data-params` để nhận diện chính xác từng câu hỏi dù vị trí bị hoán đổi.
- Khi làm mới trang, hệ thống tự động nhận diện và cập nhật câu hỏi đã có, không bao giờ bị trùng lặp.

### 3. Tự Động Khử Tiền Tố Đáp Án
- Tự động lọc bỏ các tiền tố như `A. `, `B) `, `1. ` trong văn bản câu trả lời để dữ liệu sạch sẽ, chuẩn hóa.
- Giữ nguyên các lựa chọn chỉ là một ký tự duy nhất (`A`, `B`, `C`, `D`).

### 4. Trang Web Tĩnh Ôn Tập Độc Lập (`quiz_app.html`)
- Mở trực tiếp từ Extension hoặc chạy offline độc lập trên mọi trình duyệt mà không cần cài đặt server hay NodeJS.
- Hỗ trợ **4 chế độ học tập chuyên sâu**:
  - **Luyện tập tương tác**: Làm bài đến đâu biết ngay đúng/sai đến đó kèm giải thích chi tiết.
  - **Thi thử chuẩn thời gian**: Có đồng hồ đếm ngược, nộp bài chấm điểm và xem bảng tổng kết.
  - **Thẻ ghi nhớ (Flashcards 3D)**: Lật thẻ ghi nhớ kiến thức phản xạ nhanh.
  - **Bản in tổng hợp (Study Sheet)**: Dễ dàng xem toàn bộ đề thi kèm đáp án và in ra tài liệu học tập.
- Tự động lưu tiến độ làm bài vào `localStorage` của trình duyệt.

### 5. Quy Trình Phối Hợp Thủ Công Với Gemini Chat Box (Không Cần API Key)
1. **Bước 1**: Quét đề thi bằng Extension trên Google Forms.
2. **Bước 2**: Bấm nút **"Copy Prompt cho Gemini"** (trên Popup hoặc trên Web Ôn Tập). Extension sẽ tự động tạo một câu lệnh hoàn chỉnh kèm danh sách câu hỏi sạch (đã nén để tiết kiệm token) và lưu vào Clipboard.
3. **Bước 3**: Mở [Gemini Chat](https://gemini.google.com/) và bấm `Ctrl + V` để gửi câu hỏi. Gemini sẽ giải từng câu, điền đáp án chuẩn vào `correctAnswer` và giải thích lý do vào `explanation`.
4. **Bước 4**: Copy khối mã JSON kết quả từ câu trả lời của Gemini.
5. **Bước 5**: Mở **Web Ôn Tập** (`quiz_app.html`), bấm **"Import JSON"** và dán vào. Hệ thống sẽ tự động ghép nối đáp án và lời giải thích vào toàn bộ câu hỏi (vẫn giữ nguyên hình ảnh Base64 gốc) để bạn bắt đầu luyện tập!

---

## 🚀 Hướng Dẫn Cài Đặt Vào Trình Duyệt

1. Mở trình duyệt Chrome, Edge, Brave, Cốc Cốc hoặc trình duyệt nhân Chromium bất kỳ.
2. Truy cập vào trang quản lý tiện ích:
   - Chrome: `chrome://extensions/`
   - Edge: `edge://extensions/`
   - Cốc Cốc: `coccoc://extensions/`
3. Bật công tắc **"Chế độ dành cho nhà phát triển" (Developer mode)** ở góc trên bên phải màn hình.
4. Bấm vào nút **"Tải tiện ích đã giải nén" (Load unpacked)** ở góc trên bên trái.
5. Chọn thư mục:
   ```
   /home/longp/projects/company-tools/google-forms-collector-extension
   ```
6. Tiện ích **Google Forms Question Collector** sẽ xuất hiện trên thanh công cụ của trình duyệt. Bấm vào biểu tượng mảnh ghép (Extensions) và ghim (Pin) tiện ích lên thanh địa chỉ để tiện sử dụng.

---

## 💡 Hướng Dẫn Sử Dụng

### Cách 1: Sử dụng Extension Popup
1. Mở bất kỳ trang Google Form nào (ví dụ biểu mẫu bài thi, bài trắc nghiệm).
2. Bấm vào biểu tượng **Forms Collector** trên thanh tiện ích của trình duyệt.
3. Bấm nút **"Thu thập trang này"** để quét các câu hỏi đang hiển thị.
4. Nếu biểu mẫu có nhiều trang (ví dụ Trang 1/7, Trang 2/7...):
   - Bạn có thể bấm **"Duyệt mọi trang"** để extension tự động quét và lật trang đến cuối cùng.
   - Hoặc bạn tự bấm "Tiếp" trên trang web, extension sẽ tự động thu thập tích lũy thêm các câu hỏi mới.
5. Chuyển sang tab **"Xuất dữ liệu"**, chọn định dạng mong muốn (**Văn bản, Markdown, Excel/CSV, JSON, Aiken, HTML**) và bấm **"Sao chép vào Clipboard"** hoặc **"Tải file xuống"**.

### Cách 2: Sử dụng Nút Nổi Trực Tiếp Trên Trang
1. Khi bạn đang mở trang Google Form, một nút tròn nổi màu tím với biểu tượng câu hỏi sẽ hiển thị ở góc dưới bên phải màn hình.
2. Bấm vào nút nổi để mở bảng điều khiển nhanh:
   - Xem số lượng câu hỏi hiện tại.
   - Bấm **"Thu thập trang này"** hoặc **"Sao chép nhanh đề thi"** mà không cần mở popup trình duyệt!
