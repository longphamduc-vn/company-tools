# Hướng dẫn sử dụng Outlook Rule Companion

Tài liệu này hướng dẫn từng bước thao tác với app. Muốn xem tổng quan các chức năng, đọc [GIOI_THIEU.md](GIOI_THIEU.md).

**Mục lục**
1. [Cài đặt và mở app](#1-cài-đặt-và-mở-app)
2. [Thiết lập lần đầu](#2-thiết-lập-lần-đầu)
3. [Phân loại mail hằng ngày](#3-phân-loại-mail-hằng-ngày)
4. [Sắp xếp thư mục và rule](#4-sắp-xếp-thư-mục-và-rule)
5. [Sửa một rule](#5-sửa-một-rule)
6. [Đưa rule vào Outlook (Sync)](#6-đưa-rule-vào-outlook-sync)
7. [Sang năm mới: đổi file PST](#7-sang-năm-mới-đổi-file-pst)
8. [Chia sẻ rule với đồng nghiệp](#8-chia-sẻ-rule-với-đồng-nghiệp)
9. [Lỡ tay thì sao](#9-lỡ-tay-thì-sao)
10. [Phím tắt và thao tác chuột](#10-phím-tắt-và-thao-tác-chuột)
11. [Câu hỏi thường gặp](#11-câu-hỏi-thường-gặp)

---

## 1. Cài đặt và mở app

**Cần có:**
- Windows 10/11
- **Outlook Classic** (bản cài trên máy, không phải "New Outlook" hay bản web)
- Python 3.10 trở lên

**Cài đặt (chỉ làm một lần):** mở Command Prompt trong thư mục `outlook-rule-manager` rồi chạy:

```
pip install -r requirements.txt
```

**Mở app:**
1. Mở Outlook trước và để Outlook chạy.
2. Nhấp đúp file **`run_app.bat`**.

Góc trên bên trái cho biết app đang chạy ở chế độ nào:
- **Outlook Classic** (chữ xanh): đã kết nối Outlook. Sync và chuyển mail sẽ thay đổi Outlook thật.
- **Simulated** (dải đỏ "SIMULATION MODE"): không kết nối được Outlook. Bạn vẫn tập thao tác được, nhưng Outlook không bị thay đổi gì. Mở Outlook rồi bấm **Retry** trên dải đỏ để kết nối lại.

> Nếu `rules.yaml` bị viết sai, app sẽ hiện thông báo lỗi kèm vị trí và không mở. Sửa file theo thông báo, hoặc chép lại một bản trong `config/backups/`, rồi mở lại.

## 2. Thiết lập lần đầu

Làm theo thứ tự sau, chỉ một lần.

### Bước 1: Tạo file PST lưu trữ cho năm nay
1. Bấm **Yearly Rollover…** trên thanh trên cùng.
2. Bấm **Create new PST…**. App gợi ý tên `Archive_<năm>.pst` và đặt file cạnh các PST bạn đang có. Bạn có thể đổi tên và chỗ lưu. **Không lưu trong OneDrive hay ổ mạng.**
3. Xác nhận **Yes**. File mới hiện trong bảng và được chọn sẵn.
4. **Chưa bấm Execute vội.** Đóng hộp thoại bằng **Close**, làm Bước 2 trước.

Nếu bạn đã có sẵn PST cho năm nay đang mở trong Outlook, bỏ qua nút Create và chỉ cần chọn dòng đó trong bảng.

### Bước 2: Dựng cây thư mục và rule
Có ba cách, kết hợp được với nhau:
- **Từ mail trong Inbox** (dễ nhất): xem [mục 3](#3-phân-loại-mail-hằng-ngày). Kéo mail thả lên thư mục, app tự tạo rule.
- **Nhập rule cũ đang có trong Outlook:**
  1. Bấm **Check Rule Conflicts**. Các rule bạn tự tạo trước đây hiện ra.
  2. Chọn từng dòng, bấm **Set Action: Import to YAML**.
  3. Bấm **Execute Resolutions & Sync**.
- **Nhận file rule của đồng nghiệp:** **File › Import rules…**, xem [mục 8](#8-chia-sẻ-rule-với-đồng-nghiệp).

### Bước 3: Chuyển rule sang PST mới và Sync
1. Mở lại **Yearly Rollover…** và chọn dòng PST ở Bước 1.
2. Bấm **Execute 1-Click Rollover**, rồi **Yes**.

App ghi PST mới vào cấu hình và Sync toàn bộ rule vào Outlook. Từ giờ mail mới tự vào đúng thư mục trong PST mới.

## 3. Phân loại mail hằng ngày

Cột giữa là các mail trong Inbox. Cột **Will go to** cho biết mail đó sẽ vào thư mục nào theo rule hiện tại:
- Có đường dẫn: đã có rule bắt.
- `_Unclassified`: người gửi nằm trong danh sách chưa phân loại.
- Trống: chưa có rule nào bắt. Tab **Needs Rule** lọc riêng các mail này.

### Cách 1: Kéo thả (nhanh nhất)
1. Nhấn giữ chuột trái trên một mail ở cột giữa.
2. Kéo sang cây thư mục bên trái và thả lên thư mục muốn mail vào. Thư mục đang trỏ tới sẽ được tô sáng.
   - Thư mục **đã có rule**: người gửi được thêm vào rule đó.
   - Thư mục **chưa có rule**: một rule mới được tạo, tên theo đường dẫn thư mục.
3. Muốn áp dụng cho **cả công ty gửi** (ví dụ mọi địa chỉ `@omron.com`): giữ **Ctrl** trong khi thả.

Chọn nhiều mail (Ctrl + nhấp hoặc Shift + nhấp) rồi kéo một lần cũng được.

### Cách 2: Chuột phải lên mail
- **Add to Rule…**: chọn một rule có sẵn trong danh sách, chọn phạm vi (chỉ người gửi này, hoặc cả domain), rồi bấm **Add to Queue**.
- **New Rule…**: gõ hoặc chọn thư mục, ví dụ `Purchasing\Omron`. Thư mục chưa có sẽ được tạo. Tên rule tự đặt theo thư mục.
- **Move Now**: chỉ chuyển **riêng mail này** vào thư mục của một rule, ngay lập tức, không thay đổi rule.

### Xem lại và áp dụng
Thay đổi từ cách 1 và cách 2 chưa được ghi ngay. Chúng vào **hàng chờ**: mail có dấu `*` và thanh dưới cùng hiện "N pending changes".
- **Review**: xem từng thay đổi; chọn một dòng rồi bấm **Remove Selected** để bỏ.
- **Clear**: bỏ hết.
- **Apply**: ghi tất cả vào rule và **chuyển luôn các mail đó** vào thư mục đích.

Sau khi Apply, nhớ **Sync** ([mục 6](#6-đưa-rule-vào-outlook-sync)) để Outlook tự làm việc này với mail mới đến.

> Kéo một mail sang rule khác cũng chính là **chuyển người gửi** sang rule đó. App tự gỡ người gửi khỏi rule cũ, nên mail của họ không bị chia ra hai nơi.

## 4. Sắp xếp thư mục và rule

Cây bên trái hiện các thư mục trong PST. Thư mục có rule hiện dạng `📁 Tên  (rule: …)`, và các mail mà rule đó sẽ bắt nằm ngay bên dưới.

| Muốn làm | Thao tác |
|---|---|
| Tạo thư mục cấp 1 | **New › Folder** |
| Tạo thư mục con | Chọn thư mục cha → **New › Subfolder**, hoặc chuột phải → **+ Add Subfolder** |
| Tạo rule cho thư mục đang chọn | **New › Rule** (mỗi thư mục chỉ có một rule) |
| Đổi tên thư mục | Chọn thư mục → **F2**, hoặc chuột phải → **Rename Folder…** (tên rule tự đổi theo) |
| Chuyển thư mục / rule sang chỗ khác | **Kéo thả** lên thư mục đích, hoặc chuột phải → **Move to Folder…** |
| Đưa thư mục lên cấp 1 | Kéo thả lên dòng **Folders & Rules** trên cùng, hoặc **Move to Top Level** |
| Lên một cấp | Chuột phải → **Move Up 1 Level** |
| Tạm tắt rule | Chuột phải → **Toggle Active / Disabled** |
| Xóa | Chọn rồi bấm **Delete**, hoặc chuột phải → **Delete…** |
| Tìm nhanh | Gõ vào ô **Filter** (tên thư mục, rule hoặc địa chỉ email) |
| Mở / đóng toàn bộ cây | **Expand** / **Collapse**; nhấp đúp để mở hoặc đóng một nhánh |

**Lưu ý:**
- Tên thư mục **không được bắt đầu bằng `_`**. Thư mục `_Unclassified` là của app.
- Không thể chuyển rule vào thư mục **đã có rule** khác; app sẽ báo trên thanh thông báo.
- Xóa rule hay thư mục thì các địa chỉ email của nó được giữ lại trong **Unclassified Pool**. Mở mục này trên cây, chọn địa chỉ, rồi bấm **Assign Selected to Rule…** để gán lại.

## 5. Sửa một rule

Chọn rule trên cây. Cột phải hiện chi tiết rule:

1. **Emails**: mỗi dòng một địa chỉ (`ten@congty.com`).
2. **Domains**: mỗi dòng một domain (`@congty.com`), nghĩa là mọi người của công ty đó.
3. **Subject Keywords**: mỗi dòng một từ khóa. Mail có tiêu đề chứa từ này cũng vào rule.
4. **Import CSV/Excel…**: nhập nhanh danh sách địa chỉ từ file `.csv` hoặc `.xlsx`.
5. **Enabled**: bỏ tích để tạm tắt rule.
6. Khi có chỗ chưa lưu, nút đổi thành **Save Changes ●**. Bấm để lưu.

**Kiểm tra trước khi lưu:** ở ô **Test Match**, gõ một email và/hoặc tiêu đề rồi bấm **Check**. App cho biết mail đó có vào rule này không và vì sao.

**Đổi thư mục đích:** bấm **Change Folder…** ở góc trên. Tên rule tự đổi theo.

> Rời khỏi rule khi còn thay đổi chưa lưu, app sẽ hỏi lưu hay bỏ.

## 6. Đưa rule vào Outlook (Sync)

Mọi thay đổi ở mục 3–5 mới chỉ nằm trong file `rules.yaml`. Outlook chỉ thay đổi khi bạn Sync:

1. Bấm **Sync to Outlook** ở góc trên bên phải. Bên cạnh nút có số thay đổi chưa Sync (ví dụ "● 3 unsynced changes").
2. Xác nhận **Yes**.
3. Nếu app tìm thấy **rule cũ bạn tự tạo** có cùng tên với rule trong app, nó sẽ hỏi có xóa các bản cũ đó không. Chọn **Yes** để tránh mail bị hai rule xử lý.

App chỉ tạo, sửa và xóa các rule có tiền tố `[Companion]`. Các rule khác của bạn được giữ nguyên.

**Nên bấm Check Rule Conflicts trước khi Sync lần đầu** để xem:
- Rule trùng tên nhưng đi vào thư mục khác.
- Một người gửi bị hai rule cùng bắt.
- Rule Outlook chưa có trong app.

Với mỗi dòng, chọn cách xử lý:
- **Set Action: Overwrite Outlook**: lấy theo app.
- **Set Action: Import to YAML**: đưa rule Outlook vào app.
- **Set Action: Ignore / Skip**: bỏ qua.

Cuối cùng bấm **Execute Resolutions & Sync**.

## 7. Sang năm mới: đổi file PST

1. Bấm **Yearly Rollover…**. Mục **Current Archive** cho biết PST đang dùng và tình trạng:
   - `[OK]`: bình thường.
   - `[WARNING]`: file trên 25 GB.
   - `[CRITICAL]`: file trên 35 GB, nên đổi PST.
   - `[MISSING]`: không thấy file.
   - `[NOT MOUNTED]`: có file nhưng chưa mở trong Outlook.
2. Chọn PST mới: chọn một dòng trong bảng, hoặc bấm **Create new PST…** để tạo mới.
3. Bấm **Execute 1-Click Rollover** → **Yes**.

Toàn bộ rule chuyển sang gửi mail mới vào PST mới, giữ nguyên cây thư mục. PST cũ vẫn mở trong Outlook để tra cứu; khi nào không cần nữa, bạn tự đóng nó trong Outlook.

## 8. Chia sẻ rule với đồng nghiệp

**Gửi rule của bạn:**
1. **File › Export rules for sharing…**
2. Chọn chỗ lưu (mặc định `rules_shared_<ngày>.yaml`) rồi gửi file cho đồng nghiệp. Đường dẫn PST cá nhân của bạn **không** có trong file này.

**Nhận rule của người khác:**
1. **File › Import rules…** và chọn file nhận được.
2. Chọn một trong hai:
   - **Merge**: gộp vào rule của bạn. Thư mục trùng tên thì cộng thêm người gửi; thư mục mới thì thêm vào cây.
   - **Replace all**: thay toàn bộ rule của bạn bằng rule trong file.
3. Kiểm tra cây thư mục. Thanh thông báo báo nếu có người gửi bị hai rule cùng bắt.
4. **Sync** để áp dụng vào Outlook.

PST của bạn luôn được giữ nguyên. Không ưng ý thì **Ctrl + Z** để hoàn tác lần nhập.

## 9. Lỡ tay thì sao

- **Ctrl + Z** hoặc nút **Undo** dưới cây thư mục: hoàn tác thay đổi gần nhất, tối đa 20 bước. Nút ghi rõ sẽ hoàn tác việc gì. Một lần **Apply** hay **Import** tính là một bước. Khi đang gõ trong ô văn bản, Ctrl + Z chỉ hoàn tác chữ trong ô đó.
- **Bản sao tự động:** mỗi lần lưu, app giữ một bản cũ trong `config/backups/` (30 bản gần nhất). Muốn quay về một thời điểm: đóng app, chép bản backup đè lên `config/rules.yaml`, mở lại app.
- **Đã Sync rồi mới phát hiện sai:** Undo hoặc sửa lại, rồi **Sync** lần nữa. Outlook sẽ được cập nhật theo.
- **Mail lỡ chuyển sai thư mục:** app không xóa mail. Mở thư mục trong Outlook và kéo mail về chỗ đúng như bình thường.

## 10. Phím tắt và thao tác chuột

| Phím / thao tác | Tác dụng |
|---|---|
| **Ctrl + Z** | Hoàn tác thay đổi gần nhất |
| **F2** (trên cây) | Đổi tên thư mục đang chọn |
| **Delete** (trên cây) | Xóa thư mục hoặc rule đang chọn (Ctrl + Z để lấy lại) |
| **Kéo thả mail → thư mục** | Thêm người gửi vào rule của thư mục |
| **Ctrl + kéo thả mail** | Thêm cả domain của người gửi |
| **Kéo thả thư mục / rule** | Chuyển sang thư mục khác |
| **Esc** khi đang kéo | Hủy kéo |
| **Chuột phải** | Menu thao tác cho mail, thư mục, rule |
| **Nhấp đúp** (trên cây) | Mở / đóng nhánh |

## 11. Câu hỏi thường gặp

**Tắt app thì rule còn chạy không?**
Còn. Rule nằm trong Outlook sau khi Sync. App chỉ dùng để quản lý rule.

**Vì sao một rule của tôi thành 2–3 rule trong Outlook?**
Outlook chỉ bắt mail khớp **tất cả** điều kiện trong cùng một rule. Vì vậy app tách email, domain và từ khóa thành các rule riêng (`… (Domains)`, `… (Keywords)`). Danh sách quá dài cũng được chia thành `(Part 1)`, `(Part 2)`. Dòng xanh trong chi tiết rule cho biết sẽ thành mấy rule.

**Tôi có rule tự tạo trong Outlook, app có xóa không?**
Không, trừ khi rule đó trùng tên với rule trong app và bạn bấm **Yes** khi Sync hỏi dọn rule cũ.

**Mail đến rồi mà không vào thư mục?**
Kiểm tra lần lượt:
1. Đã **Sync** chưa? Xem số "unsynced changes".
2. Ô **Test Match** của rule có báo khớp không?
3. Rule có đang **Enabled** không?
4. **Yearly Rollover** có báo PST `[MISSING]` hay `[NOT MOUNTED]` không?

**Sửa file `rules.yaml` bằng tay được không?**
Được: mỗi người gửi một dòng bắt đầu bằng `- `, và tên thư mục không bắt đầu bằng `_` (xem ví dụ trong [GIOI_THIEU.md](GIOI_THIEU.md#10-file-cấu-hình-rulesyaml)). Sửa xong bấm **File › Reload rules.yaml**. Nếu file sai, app báo lỗi và giữ nguyên rule đang dùng.
