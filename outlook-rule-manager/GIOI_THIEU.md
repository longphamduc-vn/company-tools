# Outlook Rule Companion: giới thiệu chức năng

Outlook Rule Companion là ứng dụng đi kèm **Outlook Classic** để quản lý các rule tự động chuyển mail vào đúng thư mục trong file lưu trữ PST.

Bạn sắp xếp mail bằng cách kéo thả trên một cây thư mục. App ghi lại cách sắp xếp đó vào file `config/rules.yaml`, rồi đưa thành rule thật trong Outlook. Từ đó Outlook tự chạy rule 24/7, kể cả khi đã tắt app.

> Hướng dẫn thao tác từng bước: [HUONG_DAN.md](HUONG_DAN.md)

> Rule do app tạo trong Outlook luôn có tiền tố **`[Companion]`**. App không sửa hay xóa rule bạn tự tạo trong Outlook, trừ khi bạn đồng ý dọn các rule cũ trùng tên.

---

## 1. Màn hình chính

Màn hình có 3 cột:

| Cây thư mục & rule | Danh sách mail (Inbox) | Chi tiết |
|---|---|---|
| Thư mục trong PST, rule của từng thư mục, và các mail mà rule đó sẽ bắt | Mail trong Inbox và cột **Will go to** (mail sẽ vào đâu) | Nội dung mail đang chọn, hoặc thông tin rule / thư mục đang chọn |

Thanh trên cùng có các nút sau:
- **File**: xuất hoặc nhập rule để chia sẻ, đọc lại `rules.yaml`.
- **Check Rule Conflicts**: kiểm tra rule bị trùng hoặc xung đột với Outlook.
- **Yearly Rollover…**: chuyển sang file PST mới.
- **Sync to Outlook**: đưa rule vào Outlook.

Nếu không kết nối được Outlook, app chạy ở **chế độ giả lập** (dải đỏ "SIMULATION MODE"). Mọi thao tác vẫn thử được, nhưng Outlook không bị thay đổi gì.

## 2. Cây thư mục: một thư mục = một rule

```
📁 Engineering_Team
   📁 SCADA_Part
      📁 PLC_Unit  (rule: Engineering_Team_SCADA_Part_PLC_Unit)   2 senders, 1 domain
         ✉ Nguyen Van A — Báo cáo PLC tuần 47
         ✉ Tran Thi B — Lỗi cảm biến line 3
```

- **Tên rule tự đặt theo đường dẫn thư mục**, ví dụ `Engineering_Team\SCADA_Part\PLC_Unit` thành `Engineering_Team_SCADA_Part_PLC_Unit`. Bạn không cần nghĩ tên.
- **Mail trong Inbox hiện ngay dưới rule sẽ bắt nó**, nên nhìn là biết rule đang hoạt động ra sao. Mail có dấu `*` là mail đang chờ áp dụng.
- **Tạo, đổi tên, xóa thư mục:** dùng menu **New** (Rule / Folder / Subfolder), chuột phải, hoặc phím **F2** (đổi tên) và **Delete** (xóa).
- **Đổi vị trí rule hoặc thư mục:** kéo thả trong cây.
- **Filter:** ô tìm nhanh thư mục, rule hoặc người gửi.

## 3. Phân loại mail trong Inbox

Mỗi mail trong Inbox hiện cột **Will go to**, cho biết rule hiện tại sẽ đưa mail đó vào đâu. Tab **Needs Rule** lọc ra các mail chưa có rule nào bắt.

Có ba cách gán người gửi vào rule:

| Thao tác | Kết quả |
|---|---|
| **Kéo mail thả lên một thư mục** | Người gửi được thêm vào rule của thư mục đó. Thư mục chưa có rule thì rule mới được tạo. |
| **Ctrl + kéo thả** | Áp dụng cho **cả domain** (ví dụ `@omron.com`) thay vì một địa chỉ. |
| Chuột phải → **Add to Rule… / New Rule…** | Chọn rule có sẵn hoặc gõ đường dẫn thư mục mới. |

Một người gửi chỉ thuộc **một** thư mục. Chuyển người gửi sang rule khác thì app tự gỡ họ khỏi rule cũ, nên mail không bị chia đôi.

## 4. Hàng chờ, Apply và Undo

- **Hàng chờ:** các thay đổi từ Inbox chưa được ghi ngay. Chúng nằm ở thanh dưới cùng ("1 pending change").
  - **Review**: xem lại từng thay đổi, bỏ bớt nếu cần.
  - **Apply**: ghi tất cả vào `rules.yaml` và chuyển luôn các mail đó vào thư mục đích.
  - **Clear**: hủy hết.
- **Undo:** mọi thay đổi đã lưu đều hoàn tác được bằng **Ctrl + Z** hoặc nút **Undo**, tối đa 20 bước. Một lần Apply tính là một bước.
- **Backup:** mỗi lần lưu, app tự giữ một bản sao trong `config/backups/` (mặc định 30 bản gần nhất).

## 5. Chi tiết rule

Chọn một rule trên cây, cột bên phải hiện:
- **Thư mục đích**: nút **Change Folder…** để đổi. Tên rule đổi theo.
- **Tên rule trong Outlook**: `[Companion] <tên>`. Ô **Enabled** để bật hoặc tắt rule.
- **Dòng xanh**: cho biết khi Sync, rule thành bao nhiêu rule thật trong Outlook. Email, domain và từ khóa tiêu đề được tách thành các rule riêng, vì Outlook chỉ bắt mail khớp **tất cả** điều kiện trong một rule. Rule quá dài cũng tự chia thành `(Part 1)`, `(Part 2)`…
- **Emails / Domains / Subject Keywords**: mỗi dòng một giá trị. **Import CSV/Excel…** để nhập nhanh một danh sách địa chỉ.
- **Test Match**: gõ thử một email hoặc tiêu đề để xem mail đó sẽ vào rule nào.
- **Save Rule to YAML**: lưu. Outlook chỉ thay đổi sau khi bấm **Sync**.
- **Delete Rule**: người gửi của rule được giữ lại trong **Unclassified Pool**, không bị mất.

## 6. Sync to Outlook

Bấm **Sync to Outlook** để đưa toàn bộ rule trong `rules.yaml` vào Outlook:
- Tạo, cập nhật và xóa các rule `[Companion]` cho khớp với file.
- Tự tạo thư mục còn thiếu trong PST.
- Tìm các rule cũ bạn tự tạo trước đây mà trùng tên, rồi hỏi bạn có muốn dọn chúng không.

Góc trên bên phải luôn cho biết còn bao nhiêu thay đổi **chưa Sync**.

## 7. Check Rule Conflicts

Nút này so sánh rule trong file với rule đang có trong Outlook và chỉ ra:
- Rule cùng tên nhưng đi vào thư mục khác.
- Người gửi bị hai rule cùng bắt.
- Rule Outlook chưa được app quản lý. Bạn có thể **nhập (Import)** rule đó vào app.

## 8. Chia sẻ rule với đồng nghiệp (File)

- **Export rules for sharing…**: xuất một bản `rules.yaml` để gửi cho người khác. Đường dẫn PST cá nhân của bạn được xóa khỏi bản xuất.
- **Import rules…**: nhập file của người khác, chọn một trong hai cách:
  - **Merge**: gộp với rule của bạn. Cùng thư mục thì cộng thêm người gửi.
  - **Replace all**: thay toàn bộ rule của bạn bằng rule trong file.

  Cả hai cách đều giữ nguyên PST của bạn và hoàn tác được bằng Ctrl + Z.
- **Reload rules.yaml**: đọc lại file sau khi bạn sửa bằng tay.

## 9. Chuyển PST theo năm (Yearly Rollover)

Khi file PST đã quá lớn hoặc sang năm mới:
1. Mở **Yearly Rollover…**. Bảng trên cùng liệt kê mọi file dữ liệu đang mở trong Outlook, kèm dung lượng. App cảnh báo khi PST vượt 25 GB và 35 GB.
2. Chọn một PST đã mở sẵn, **hoặc** bấm **Create new PST…** để tạo file mới. App gợi ý `Archive_<năm>.pst`, tạo file rỗng, mở nó trong Outlook và chọn sẵn. App không ghi đè file có sẵn và từ chối lưu trên OneDrive hay ổ mạng.
3. Bấm **Execute 1-Click Rollover**: mọi rule chuyển sang gửi mail mới vào PST mới, giữ nguyên cây thư mục.

PST cũ vẫn mở bình thường trong Outlook để tra cứu.

## 10. File cấu hình `rules.yaml`

App lưu mọi thứ trong `config/rules.yaml`. File viết theo đúng cây thư mục, nên có thể đọc và sửa bằng tay:

```yaml
folders:
  Management: []                      # thư mục rỗng, chưa có rule
  Engineering:
    - em@company.com                  # → rule [Companion] Engineering
    - Pol_Process:                    # → rule [Companion] Engineering_Pol_Process
        - employees1@company.com
        - "@techpartner.com"          # bắt đầu bằng @ = cả domain
        - _subject: [PLC alarm]       # tùy chọn: từ khóa tiêu đề
        - _enabled: false             # tùy chọn: tạm tắt rule
unclassified:                         # người gửi đi vào _Unclassified
  - former.contractor@vendor.com
```

**Quy tắc khi sửa tay:**
- Mỗi người gửi một dòng, bắt đầu bằng `- `.
- Tên thư mục không bắt đầu bằng `_`.
- File sai định dạng thì app báo lỗi rõ ràng, kèm vị trí, và không chạy cho tới khi sửa xong.
- Ghi chú (`# …`) sẽ mất khi app lưu lại file.

---

**Yêu cầu:** Windows 10/11, Outlook Classic (2016–2021 / Microsoft 365 bản desktop) và Python 3. Chạy bằng `run_app.bat`.
