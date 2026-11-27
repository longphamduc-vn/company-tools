# Kế hoạch: tạo & di chuyển rule nhanh — outlook-rule-manager

Plan này thay cho đề xuất P0–P3 trước đó (đã tự đánh giá lại, xem mục cuối). Người thực hiện (Claude hoặc Gemini) **dừng sau mỗi phase** để review: diff + test + chụp màn hình Mock mode 1120x720.

## Mục tiêu đo được

| Việc | Hiện tại | Đích |
|---|---|---|
| Thêm người gửi vào rule có sẵn | 1 lần thả | 1 lần thả **hoặc** gõ tên rule + Enter |
| Chuyển người gửi sang rule khác | **Hỏng** (người gửi ở cả 2 rule, mail vẫn vào rule cũ) | 1 lần thả, và sau Apply mail thật sự vào rule mới |
| Tạo rule mới từ mail | Hộp thoại 5 ô + phạm vi | 1 lần thả lên folder, hoặc thả lên "+ New rule…" → Enter |
| Tạo rule ở tab Rules | 5 bước, sinh "New Rule 7" | Hộp thoại 2 ô (tên, folder) → Enter |
| Di chuyển rule/folder | Kéo, không hoàn tác được | Kéo, **Ctrl+Z / nút Undo** hoàn tác được |
| Apply hàng chờ | 1–2 hộp thoại xác nhận | Đúng 1 hộp thoại |

**Bất biến bắt buộc (có test):** sau khi Apply, với mọi mail đã stage, `SyncEngine.match_message(sender, subject)` trả về đúng rule/folder mà cột "Will go to" đã hiển thị lúc stage.

## Quy tắc chung

- Phase 0 do người dùng quyết định; các phase sau làm trên branch `fix/outlook-rule-manager-simplify` (sau khi commit phần kéo-thả đang có, nếu người dùng đồng ý).
- Không commit `config/rules.yaml` (thay đổi của người dùng). Chỉ `git add` file đã sửa.
- Được sửa `core/` khi phase yêu cầu, **kèm test logic mới**. Không sửa/xóa test logic cũ (`tests/test_phase*.py`) trừ khi hành vi cũ chính là lỗi đang sửa — khi đó ghi rõ lý do trong nhật ký.
- Không kết nối Outlook thật trong test. `python -m pytest -q tests` phải pass.
- Không commit (người dùng commit sau). Ghi *Nhật ký thực hiện* cuối file sau mỗi phase.

---

## Phase 0 — Chuẩn bị (đã chốt 2026-11-26)

1. Người dùng sẽ tự commit sau → các phase dưới **không commit**, để nguyên working tree.
2. `config/rules.yaml`: *Executive Board* đã trả về `Management\Executive_Board\Directors` (người dùng xác nhận vị trí cũ là do test thử).

## Phase 1 — Chuyển người gửi đúng nghĩa (sửa lỗi)

**Nguyên tắc:** chỉ gỡ khi trùng **cùng cấp khớp**. Email riêng thắng domain (cấp 1 trước cấp 2, cả ở dry-run lẫn thứ tự rule trong Outlook), nên thêm email vào rule B **không cần** gỡ domain của rule A.

1. `core/yaml_manager.py`: thêm `assign_sender(email, rule_id, as_domain=False, save=True) -> AssignResult`:
   - Email: gỡ email khỏi `emails` riêng của **mọi rule khác** và khỏi `unclassified_pool`; rồi thêm vào rule đích (vào group đầu tiên của rule như hiện tại, hoặc vào rule nếu không có group).
   - Domain: gỡ domain khỏi `domains` riêng của mọi rule khác; rồi thêm vào rule đích.
   - Nếu địa chỉ/domain đến từ **group** của rule khác: group chỉ được **đúng một rule** dùng → tự gỡ khỏi group (người dùng xác nhận 2026-11-26: config dùng mỗi group cho một rule). Group được **nhiều rule** dùng chung → không tự sửa, trả về `blocked_by_groups=[(group, rules)]`.
   - `AssignResult` gồm: `moved_from` (tên rule đã gỡ), `blocked_by_groups`.
   - Giữ `add_sender_to_rule_or_group` cho tương thích, gọi sang `assign_sender`.
2. Hàng chờ: action `add_to_rule` tính trước `moved_from` để hiển thị "Move: A → B" trong Review và trong cột "Will go to" (vd `* B (from A)`).
3. Apply (`_apply_all_staged`): dùng `assign_sender`. Chỉ khi có `blocked_by_groups` (group dùng chung) → **một** hộp thoại liệt kê: "Remove <email> from group <G> (used by <rules>)? Yes / Skip". Yes → gỡ khỏi group.
4. Test:
   - Bất biến: stage chuyển `lead.scada@company.com` (đang nằm trong group engineering) sang Omron Equipment → sau Apply + trả lời Yes, `match_message` → Omron Equipment.
   - Email riêng ở rule A → thả sang B → chỉ còn ở B.
   - Domain: Ctrl+thả `@omron.com` sang rule khác → gỡ khỏi rule cũ.
   - Email riêng thắng domain: thêm `x@omron.com` vào rule B trong khi `@omron.com` vẫn ở rule A → match B, không gỡ domain.
   - Trả lời Skip cho group → báo rõ người gửi vẫn đi vào rule cũ.

## Phase 2 — Hoàn tác & an toàn cho tab Rules

1. `core/yaml_manager.py`: undo stack trong bộ nhớ (tối đa 20): `snapshot(label)` lưu bản sao sâu của `rules`, `groups`, `unclassified_pool`, `settings`; `undo() -> Optional[str]` khôi phục bản gần nhất rồi `save()`. Không đọc lại file backup (tránh hoàn tác lẫn thay đổi khác).
2. Gọi `snapshot` trước mọi thao tác cấu trúc ở tab Rules: kéo-thả rule/folder, đổi tên, xóa, tạo folder, Move to Top Level, Move Up, Change Folder, và trước Apply ở tab Inbox.
3. Thanh tip/toast ở tab Rules: sau thao tác hiện `Moved 'Management' → '_Unclassified'  [Undo]`; phím **Ctrl+Z** trong cửa sổ chính = Undo. Sau Undo làm mới cả hai tab.
4. Chặn thả vào `_Unclassified` (và vào chính folder unclassified cấu hình trong settings) — hiện cảnh báo ngắn trên thanh tip, không mở hộp thoại.
5. Test: kéo folder → undo → cây và YAML trở lại như cũ; 21 thao tác → chỉ giữ 20; thả vào `_Unclassified` bị từ chối; undo khi stack rỗng không làm gì.

## Phase 3 — Tạo rule nhanh

1. **Thả lên dòng folder** trong panel Rules (tab Inbox) = stage `create_rule` ngay trong folder đó, không hộp thoại:
   - Tên rule = tên hiển thị người gửi đã làm sạch (bỏ phần trong ngoặc); không có thì phần trước `@`. Ctrl khi thả → match domain, tên = domain viết hoa chữ đầu.
   - Nếu folder đó đã có rule cùng tên → thêm vào rule đó thay vì tạo trùng.
   - Thanh hint trong panel cập nhật: "Drop on a rule to add the sender · on a folder to create a rule there · Ctrl = whole domain".
2. **Hộp thoại Quick New Rule** (dùng chung cho "+ New rule…" ở Inbox và `New ▾ → Rule` ở tab Rules) — thay hộp thoại Team/Part/Unit:
   - 2 ô: **Name** (điền sẵn) và **Folder** (combobox có thể gõ, lọc theo chuỗi con trên các folder có sẵn; gõ đường dẫn mới = tạo folder mới, hiện nhãn nhỏ "New folder will be created").
   - Từ Inbox có thêm lựa chọn phạm vi This sender / Whole domain (mặc định This sender).
   - Folder mặc định: folder của rule hiện đang khớp domain người gửi → nếu không có thì folder dùng lần gần nhất → nếu không có thì để trống. **Bỏ** việc tự bịa `Vendor_Team\Suppliers_Part\…` trong `suggest_rule_and_folder`.
   - Enter = OK, Esc = Cancel. Tab Rules: OK tạo rule (có snapshot để Undo) và chọn nó trong cây; không còn "New Rule 7".
3. Test: thả lên folder → 1 action create_rule đúng folder + tên; thả lên folder có rule trùng tên → add_to_rule; Quick New Rule: gợi ý folder theo thứ tự ưu tiên, gõ đường dẫn mới hiện nhãn, Enter tạo rule; `suggest_rule_and_folder` không còn trả về đường dẫn bịa.

## Phase 4 — Tăng tốc thao tác lặp lại

1. **Recent** ở đầu panel Rules: 5 rule được thả/gán gần nhất trong phiên (ngay dưới "+ New rule…").
2. **Bàn phím**: trong ô Filter của panel, mũi tên lên/xuống chọn rule, **Enter** = gán mail đang chọn vào rule đó (Ctrl+Enter = cả domain). Phím **/** khi đang ở danh sách mail = nhảy vào ô Filter.
3. **Nhãn folder gọn**: dòng folder hiển thị 2 cấp cuối (`Executive_Board\Directors`); đường dẫn đủ xem ở thanh trạng thái nhỏ dưới panel khi di chuột/chọn.
4. **Rule trong panel thao tác như mail** (người dùng yêu cầu 2026-11-26: "kéo mail cũng như kéo rule"):
   - Kéo rule thả lên dòng folder trong panel = di chuyển rule sang folder đó (có snapshot → Undo). Thả rule lên rule khác = di chuyển vào folder của rule đó.
   - Phím **Delete** trên rule đang chọn = xóa rule (người gửi về Unclassified Pool như hiện tại), **không hỏi**, hiện `Deleted 'X' [Undo]`.
   - Phím **F2** = đổi tên rule tại chỗ (ô nhập nhỏ đè lên dòng).
   - Chuột phải rule: `Rename (F2)`, `Move to folder…`, `Delete (Del)`.
   - Kéo mail và kéo rule dùng chung cơ chế ghost + tô sáng đích thả.
5. **Apply 1 bước**: gộp thành một hộp thoại tóm tắt (số rule tạo / gán / chuyển, số mail sẽ move). Bỏ hỏi conflict mỗi lần Apply; chỉ cảnh báo trong tóm tắt nếu `detect_conflicts` có SENDER_OVERLAP liên quan tới người gửi đang stage.
6. Test: Recent cập nhật đúng thứ tự, giới hạn 5; Enter/Ctrl+Enter trong Filter stage đúng; Apply chỉ gọi đúng 1 lần `askyesno`.

---

## Ngoài phạm vi

- Gỡ bỏ address groups / unclassified pool; đổi định dạng `rules.yaml`.
- Sync Outlook tự động sau Apply (giữ nguyên hành vi hiện tại).

## Tự đánh giá — thay đổi so với đề xuất trước

1. **Chuyển người gửi:** đề xuất cũ "gỡ khỏi mọi rule khác" quá tay — gỡ domain là sai khi chỉ chuyển 1 email (email riêng vốn đã thắng domain). Nay chỉ gỡ khi trùng cùng cấp; group dùng chung thì hỏi gom **một lần** lúc Apply, không hỏi mỗi lần thả. Thêm bất biến "preview = kết quả thật" vì chính cột "Will go to" đã che lỗi này.
2. **Undo:** đề xuất cũ khôi phục từ file backup — có thể hoàn tác lẫn thay đổi khác và không làm nhiều bước được. Nay dùng undo stack trong bộ nhớ.
3. **Tạo rule bằng thả lên folder:** bổ sung xử lý trùng tên (gán vào rule sẵn có thay vì tạo bản sao) — tránh rule nhân bản khi thả nhiều mail cùng người gửi.
4. **Hộp thoại 2 ô:** bỏ lựa chọn riêng "New subfolder under…" — ô Folder gõ được đã đủ, ít điều khiển hơn. Folder mặc định lấy từ dữ liệu thật, không bịa.
5. **Di chuyển rule trong panel bằng kéo-thả:** từng bỏ để tránh trùng cách làm, nhưng người dùng yêu cầu rõ thao tác rule nhanh như mail → đưa lại vào Phase 4, kèm Delete/F2 và Undo (Phase 2) làm lưới an toàn.
6. **Bổ sung điều đề xuất cũ bỏ sót:** đường bàn phím (Filter + Enter) cho người xử lý nhiều mail; Apply chỉ còn 1 xác nhận; lỗi dữ liệu hiện tại tách thành Phase 0 chờ người dùng.
7. **Group:** đã chốt — group chỉ thuộc một rule thì tự gỡ, chỉ hỏi khi group dùng chung.

## Nhật ký thực hiện

<!-- Ghi lại sau mỗi phase -->

### Phase 0–3 + gộp màn hình (2026-11-26/27) — Claude thực hiện, chưa commit
- **Phase 0:** `config/rules.yaml` — Executive Board trả về `Management\Executive_Board\Directors` (người dùng xác nhận vị trí cũ do test).
- **Phase 1 (chuyển người gửi):** `core/yaml_manager.py` thêm `preview_sender_move`, `detach_sender`, `assign_sender`. Chỉ gỡ khi trùng cùng cấp; group chỉ một rule dùng → tự gỡ; group dùng chung → hỏi **một lần** lúc Apply. Hàng chờ hiện "from <rule cũ>"; sau Apply tự kiểm tra và báo mail nào vẫn đi sai chỗ (`last_apply_mismatches`). Test: `tests/test_rule_ux1_move_sender.py`.
- **Phase 2 (Undo):** undo stack trong bộ nhớ (20 bước) ghi tự động trước mỗi lần lưu, có nhãn mô tả; Ctrl+Z (trừ khi đang gõ trong ô text) và nút Undo ở thanh trạng thái navigator. Không cho chuyển rule/folder vào `_Unclassified` (báo trên thanh trạng thái, không mở hộp thoại). Test: `tests/test_rule_ux2_undo.py`.
- **Phase 3 (tạo rule nhanh):** thả mail lên folder = tạo rule mới trong folder đó (tên theo người gửi; Ctrl = theo công ty/domain; trùng tên trong folder → gộp). Hộp thoại `gui/quick_rule_dialog.py` chỉ 2 ô (Name, Folder gõ/lọc được), gợi ý folder từ rule đang xử lý domain đó hoặc folder dùng gần nhất — bỏ đường dẫn tự bịa. Tab Rules: New → Rule đặt sẵn con trỏ vào ô Name, Enter = lưu. Test: `tests/test_rule_ux3_create.py`.
- **Gộp 2 màn hình (người dùng yêu cầu, chọn bố cục "Cây rule | Mail | Chi tiết"):** bỏ tab. `MainWindow._build_workspace` dựng 3 cột; `RuleManagerView` và `TriageView` dựng widget vào các vùng do cửa sổ cung cấp (`nav_host`, `inbox_host`, `reader_host`, `inspector_host`, `bottom_host`). Kéo mail thả thẳng lên cây rule (rule / folder / gốc "Folders & Rules" = New rule). Bấm mail → cột phải hiện mail; bấm rule/folder/group → cột phải hiện form sửa (hỏi lưu nếu đang sửa dở). Phím Delete (xóa rule, không hỏi — có Undo), F2 (đổi tên). Panel thả riêng ở tab Inbox đã xóa. Apply chỉ còn 1 hộp thoại xác nhận. Cửa sổ mặc định 1280x760, tối thiểu 1040x620.
- **Test GUI cũ đã cập nhật** cho bố cục mới (không còn `notebook`, đích thả là cây rule, kích thước 1280x760): `test_ui_phase1/2/3.py`, `test_ui_simplify1/2/3.py`, viết lại `test_ui_dragdrop.py`. Không sửa test logic `tests/test_phase*.py`.
- **Kết quả:** `python -m pytest -q tests` → **138 passed**.
- **Chưa làm (Phase 4 còn lại):** mục Recent, gõ tên rule + Enter để gán, nhãn folder gọn, "Move to folder…" từ menu chuột phải.
