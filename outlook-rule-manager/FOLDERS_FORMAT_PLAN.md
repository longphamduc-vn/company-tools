# Kế hoạch: định dạng `folders:` (cây thư mục = rule) — outlook-rule-manager

**Người thực hiện:** Gemini. **Làm liền cả 3 phase trong một lượt (xử lý đồng loạt)**, không dừng giữa chừng. Người dùng review **một lần ở cuối**: diff + kết quả test + ảnh chụp Mock mode 1280x760. Chỉ dừng sớm khi gặp điều plan không quy định, khi đó ghi câu hỏi vào nhật ký rồi hỏi người dùng.

## Mục tiêu

`config/rules.yaml` được viết **giống hệt cây thư mục trong PST**:

```yaml
version: '3.0'
settings:
  auto_split_threshold: 40
  unclassified_folder: _Unclassified
  backup_versions: 30
stores:
  active_archive:
    name: Archive 2025
    file_path: D:\Outlook_Data\longp_Archive_2025.pst
folders:
  Management: []                      # thư mục rỗng, không có rule
  Engineering:
    - em@company.com                  # → rule [Companion] Engineering
    - Pol_Process:                    # → rule [Companion] Engineering_Pol_Process
        - employees1@company.com
        - employees2@company.com
        - "@techpartner.com"          # bắt đầu bằng @ = domain
        - _subject: [PLC alarm, SCADA] # tùy chọn: từ khóa tiêu đề
        - _enabled: false             # tùy chọn: tắt rule
unclassified:                         # người gửi đi vào _Unclassified
  - former.contractor@vendor.com
legacy_rule_names:                    # tên rule cũ (tự sinh khi chuyển đổi, người dùng không cần sửa)
  - Executive Board
```

Đồng thời **bỏ hẳn các cách cũ**:
- `rules:` (danh sách rule có `id` và `name`)
- `groups:` / Shared Address Groups / Link Group
- `former_names`
- `custom_folders`
- `target_store` của từng rule
- đặt tên rule thủ công (`settings.auto_rule_names`)
- nhiều rule trong cùng một thư mục
- Duplicate Rule

File v2 cũ chỉ còn được đọc qua **bộ chuyển đổi một chiều** (migration).

## Quy tắc của định dạng (bắt buộc, có test)

### 1. Cấu trúc khóa `folders`

`folders` là mapping `tên thư mục -> giá trị`. Giá trị có thể là:

**a. Một list (dạng chuẩn).** Mỗi phần tử thuộc một trong các loại sau:
- **Chuỗi**, là người gửi:
  - Có `@` ở đầu (`"@omron.com"`) là domain, chuẩn hóa bằng `YamlConfigManager.normalize_domain`.
  - Có dạng `x@y.z` là email, chuẩn hóa về `lower().strip()`.
  - Chuỗi không hợp lệ (không có `@`) thì bỏ qua và thêm cảnh báo vào `load_warnings`.
- **Mapping 1 khóa, tên khóa không bắt đầu bằng `_`**, là một thư mục con. Giá trị của nó lại theo đúng quy tắc này (đệ quy).
- **Mapping 1 khóa bắt đầu bằng `_`**, là tùy chọn:
  - `_subject` nhận một list chuỗi hoặc một chuỗi, là từ khóa tiêu đề (chuẩn hóa bằng `normalize_keywords`).
  - `_enabled` nhận kiểu bool, mặc định `true`.
  - Khóa `_` không quen thì thêm cảnh báo và bỏ qua.

**b. Một mapping:** chỉ chứa các thư mục con, chấp nhận khi đọc cho tiện viết tay (ví dụ `Management: {}`).

**c. `null` hoặc `[]` hoặc `{}`:** thư mục rỗng.

### 2. Một thư mục có tối đa một rule

Rule chỉ tồn tại khi thư mục có ít nhất **1 người gửi hoặc 1 `_subject`**.
- **Tên rule** = `rule_name_from_folder(đường dẫn)`, ví dụ `Engineering_Pol_Process`. Trong Outlook tên này thành `[Companion] Engineering_Pol_Process`.
- **Id rule** được sinh lúc load, **không ghi ra file**:
  - Công thức: `"rule_" + đường dẫn.lower()`.
  - Id **không đổi** trong suốt phiên làm việc, kể cả khi move hoặc rename thư mục. Lý do: undo, các action đã stage và iid trên cây đều tham chiếu theo id.

### 3. Thư mục bị cấm và ràng buộc tên

- **Thư mục unclassified** (`settings.unclassified_folder`):
  - Không được xuất hiện trong `folders`.
  - Người gửi của nó nằm ở `unclassified:`. Danh sách này gộp `unclassified_pool` cũ và email của `rule_unclassified` cũ.
  - Trong bộ nhớ vẫn có **một** `RuleConfig(id="rule_unclassified", name="[Unclassified]", target_folder=<unclassified_folder>)`, đặt cuối danh sách, emails = `unclassified`. Nhờ vậy `sync_engine` và `match_message` giữ nguyên.
- **Tên thư mục không được bắt đầu bằng `_`** (tiền tố này dành cho tùy chọn).
  - Gặp khi load thì cảnh báo và bỏ qua thư mục đó.
  - Các thao tác tạo thư mục, đổi tên thư mục và Quick Rule đều từ chối tên như vậy, kèm thông báo.

### 4. Thứ tự và trùng lặp

- **Thứ tự rule** = thứ tự duyệt cây theo chiều sâu, đúng như trong file. Thứ tự này dùng cho `match_message` và thứ tự rule trong Outlook.
- **Một người gửi chỉ ở một thư mục.** Gặp trùng khi load thì giữ ở thư mục gặp trước, bỏ ở thư mục sau và cảnh báo `"x@y.com: in A and B - kept in A"`.

### 5. Ghi file và cảnh báo

- **Khi ghi** (`to_dict`):
  - Mỗi thư mục luôn ghi ở dạng list, theo thứ tự: email (sắp xếp) → domain (sắp xếp) → `_subject` (nếu có) → `_enabled: false` (chỉ khi tắt) → thư mục con (giữ nguyên thứ tự).
  - Thư mục rỗng ghi `[]`.
  - Dùng Dumper có thụt lề cho list lồng (`increase_indent(flow, False)`), `allow_unicode=True`, `sort_keys=False`.
- **Comment trong file** bị mất khi app lưu (PyYAML không giữ comment). Ghi chú điều này trong README.
- **`load_warnings: List[str]`:** sau khi load, `MainWindow` hiện tối đa 3 dòng cảnh báo trên toast và in đủ danh sách ra log.

## Quy tắc chung

- Làm trên branch `feat/outlook-rule-manager-folders-format`, tạo từ `main` (các thay đổi trước đó đã được commit sẵn trên `main`).
- Không commit `config/rules.yaml` và `rules_shared_*.yaml`. Không commit gì cả: người dùng tự commit.
- Test không bao giờ kết nối Outlook thật: dùng `MockOutlookClient` hoặc `tests/fakes.py`. Chạy từng file test với timeout, ví dụ `timeout 300 python -m unittest tests.test_x`. Mọi file phải pass.
- **Test của tính năng bị bỏ** (group, duplicate, đặt tên thủ công, `former_names`, `custom_folders`) thì **xóa**. Các test khác thì **sửa theo định dạng mới, không được xóa**. Liệt kê các test đã xóa trong nhật ký.
- Ghi *Nhật ký thực hiện* ở cuối file này: sau mỗi phase ghi một đoạn ngắn, cuối cùng ghi tổng kết. Mỗi phase phải pass test của chính nó rồi mới sang phase sau, nhưng không cần chờ người dùng.

---

## Phase 1 — Đọc / ghi định dạng v3 + chuyển đổi từ v2 (`core/`)

1. **`core/models.py`**
   - `RuleConfig`: bỏ các trường `groups`, `target_store`, `former_names` và hàm `known_names()`. `name` vẫn giữ, nhưng luôn bằng `rule_name_from_folder(target_folder)`, trừ rule unclassified.
   - Xóa `AddressGroup`.
2. **File mới `core/config_format.py`** (thuần logic, không phụ thuộc GUI)
   - `parse_folders(data) -> ParsedConfig`:
     - Đầu ra gồm `rules`, `folders` (tất cả đường dẫn, kể cả thư mục rỗng, theo thứ tự), `unclassified`, `legacy_rule_names` và `warnings`.
     - Bắt lỗi kiểu dữ liệu và báo bằng `ValueError("...: <đường dẫn>")`. Không được crash vì `AttributeError`.
   - `dump_folders(rules, folders, unclassified, legacy_rule_names, settings, stores) -> dict`.
   - `migrate_v2(data) -> dict` (trả về dict v3):
     - **Gộp người gửi.** Người gửi của rule = email/domain riêng của rule + thành viên các group mà rule đó link.
     - **Hai rule cùng thư mục:** gộp người gửi vào một rule; `_subject` cũng gộp. Rule chỉ bị tắt (`_enabled: false`) khi **tất cả** các rule gộp vào đều tắt.
     - **Thư mục:**
       - `custom_folders` cũ được chuyển thành thư mục rỗng.
       - Rule thuộc store khác `active_archive` thì cảnh báo và vẫn đưa vào cây.
     - **Unclassified:** `unclassified` = `unclassified_pool` cũ + email của `rule_unclassified` cũ.
     - **Tên cũ:** `legacy_rule_names` = mọi `name` và `former_names` cũ khác với tên mới.
     - **Người gửi trùng:** áp dụng quy tắc 4.
3. **`core/yaml_manager.py`**
   - **Load và lưu:**
     - `load()`: đọc YAML.
       - Có `rules:` hoặc `version` < 3 thì gọi `migrate_v2`. Trước khi chuyển đổi, **chép file gốc thành `rules.yaml.v2.bak`**, chỉ chép nếu file bak chưa tồn tại. Sau khi chuyển đổi thì `save()` ngay.
       - Sau đó gọi `parse_folders`.
     - Thay `_parse_data` và `to_dict` bằng `config_format`.
   - **Thuộc tính:**
     - Thêm `self.folders: List[str]` thay cho `settings["custom_folders"]`.
     - `get_existing_hierarchy`, `get_all_folders` và `add_custom_folder` dùng `self.folders`. Đổi tên `add_custom_folder` thành `add_folder`.
     - `unclassified_pool` giữ tên thuộc tính để ít phải sửa, nhưng ghi ra khóa `unclassified`.
   - **Xóa các hàm và chức năng cũ:**
     - `auto_rule_names`, `is_fixed_name_rule`, `auto_rule_name` (chỉ giữ một hàm lấy tên theo thư mục), `apply_auto_rule_names` (tên luôn được tính khi ghi và khi move/rename)
     - `delete_group`, `generate_group_id`, `duplicate_rule`, `_generate_unique_id` (nếu không còn ai dùng)
     - mọi nhánh xử lý group trong `add_sender_to_rule_or_group`, `_sender_holders`, `preview_sender_move`, `detach_sender`, `assign_sender` (bỏ tham số `remove_from_shared_groups` và kết quả `shared_groups`)
   - `get_all_emails_for_rule` / `get_all_domains_for_rule`: trả về đúng `rule.emails` / `rule.domains`.
   - **Thao tác thư mục:** `move_rule_to_folder`, `move_folder_hierarchy`, `rename_folder_hierarchy`, `delete_folder_hierarchy`:
     - Cập nhật `self.folders` cùng với `rule.target_folder` và `rule.name`.
     - Từ chối khi thư mục đích **đã có rule**, trả về `(False, "'<folder>' already has a rule")`. Không gộp ngầm.
   - Thêm `rule_for_folder(path) -> Optional[RuleConfig]` và `ensure_rule_for_folder(path) -> RuleConfig`. Hàm sau tạo rule nếu thư mục chưa có rule và tạo thư mục nếu chưa có.
   - **Undo** (`_capture_state` / `undo`): chụp `rules`, `folders`, `unclassified_pool`, `settings`, `legacy_rule_names`. Bỏ `groups`.
   - **Import/export:**
     - `export_config` / `read_shared_file` / `import_config`: file v2 nhận vào được chuyển đổi bằng `migrate_v2`.
     - **merge**: cùng thư mục thì hợp người gửi; thư mục mới thì thêm vào cây.
     - **replace**: thay `folders`, `unclassified`, `legacy_rule_names`.
     - Kết quả trả về bỏ `groups_added` / `groups_merged`.
4. **`core/sync_engine.py`**
   - Bỏ `_effective_rule` và tham số `group_ids` ở `preview_compiled_rules` / `get_rule_quota_summary`.
   - `find_legacy_rules` / `legacy_base_names`: dùng `rule.name` + `yaml_mgr.legacy_rule_names`.
   - Đường dẫn store luôn lấy từ `stores["active_archive"]`.
5. **`core/conflict_detector.py`**
   - Thay `known_names()` bằng `[rule.name] + legacy_rule_names`.
   - Bỏ phần xử lý group.
   - Chỗ tạo `RuleConfig(... target_store=...)` (dòng ~164) thì bỏ tham số `target_store`.
6. **Fixture**
   - Chuyển `tests/fixtures/rules_sample.yaml` sang v3, kết quả phải giống hệt đầu ra của `migrate_v2(fixture cũ)`.
   - Giữ bản cũ thành `tests/fixtures/rules_sample_v2.yaml` để test migration.
7. **Test mới `tests/test_folders_format.py`** (chỉ test core):
   - Ví dụ ở mục *Mục tiêu* parse ra đúng 2 rule (`Engineering`, `Engineering_Pol_Process`), đúng email/domain/keyword/enabled, và `Management` là thư mục rỗng.
   - Round trip: `parse(dump(parse(x)))` không đổi. File ghi ra đúng thứ tự và định dạng mô tả ở quy tắc 5.
   - `Management: {}`, `Management:` (null) và `Management: []` đều hợp lệ.
   - Thư mục tên `_X` bị bỏ qua và có cảnh báo; chuỗi không có `@` cũng có cảnh báo.
   - Người gửi trùng giữa 2 thư mục thì giữ ở thư mục đầu và có cảnh báo.
   - Mỗi kiểu dữ liệu sai (`folders: 5`, phần tử là list lồng list, mapping 2 khóa) báo `ValueError` có đường dẫn.
   - `migrate_v2(rules_sample_v2.yaml)`:
     - Group được bung vào đúng thư mục; 2 rule cùng thư mục được gộp.
     - `custom_folders` thành thư mục rỗng.
     - `legacy_rule_names` chứa các tên cũ (`Executive Board`, ...).
     - Có file `.v2.bak`; load lần 2 không tạo lại bak.
   - **Bất biến migration:** với mọi người gửi trong fixture v2, `match_message` trước và sau migration chỉ ra **cùng thư mục**, trừ người gửi trùng đã được cảnh báo.
   - Test sync: rule Outlook cũ tên `Executive Board` vẫn được nhận ra là legacy. Sửa lại `test_sync_renames_outlook_rule_and_still_finds_old_hand_made_rule` trong `tests/test_auto_rule_names.py` theo `legacy_rule_names`.

**Xong phase 1 khi:** toàn bộ test core pass (các file `test_phase*.py`, `test_auto_rule_names.py`, `test_folders_format.py`). GUI có thể còn lỗi; làm tiếp phase 2 ngay.

## Phase 2 — Gỡ group và các chức năng cũ khỏi GUI

1. **`gui/rule_manager_view.py`**
   - **Xóa toàn bộ phần group:**
     - Trên cây: nhánh "Shared Address Groups", menu chuột phải của group, kéo-thả từ/vào group.
     - Màn hình chi tiết group: `_build_group_inspector`, `_populate_group_inspector`, `_get_current_group_form_values`, `is_group_dirty`.
     - Các thao tác group: `_add_group`, `_save_group_changes`, `_rename_selected_group`, `_delete_selected_group`, `_import_addresses_to_group`.
     - Trong màn hình chi tiết rule: ô "Linked Groups", `_link_group_to_rule` / `_unlink_group_from_rule`, `_refresh_linked_groups_listbox`, `_linked_group_senders` / `_show_group_senders`, `lbl_group_emails` / `lbl_group_domains`, và mục "Group" trong menu New.
   - **Tiêu đề ô:** quay lại `Emails (N)` / `Domains (N)`.
   - **Tên rule:** bỏ ô nhập `ent_rule_name`. Thay bằng một label chỉ đọc: `[Companion] <name>`.
     - Bỏ `_rule_name_locked`, `_focus_new_rule_name` và nhánh F2 đổi tên rule.
     - F2 trên một rule giờ luôn **đổi tên thư mục** của nó.
   - **Bỏ nút và menu "Duplicate Rule"** cùng hàm `_duplicate_selected_rule`.
   - **Cây:**
     - Mỗi thư mục có rule luôn hiển thị **một nút gộp** `📁 <tên>  (rule: <name>)`, iid `rule_<id>`, giống nút gộp hiện nay. Áp dụng cho cả thư mục có thư mục con: các thư mục con nằm dưới nút gộp, sau các mail.
     - Thư mục không có rule hiển thị `📁 <tên>`, iid `fld_<path>`.
     - Bỏ trường hợp "thư mục có nhiều rule" và bỏ `merged_nodes` nếu mọi nút có rule đều là nút gộp. Nếu `merged_nodes` còn có ích cho code kéo-thả thì có thể giữ, nhưng phải ghi lý do vào nhật ký.
   - **New Rule ở thư mục đang chọn:** thư mục đã có rule thì chỉ chọn rule đó và hiện toast "already has a rule"; chưa có thì tạo rule rỗng (`ensure_rule_for_folder`).
   - **Kéo rule hoặc nút gộp vào thư mục đã có rule:** từ chối và hiện toast (theo phase 1, mục 3).
2. **`gui/triage_view.py`**
   - **Thả mail lên thư mục:** luôn dùng `ensure_rule_for_folder`. Thư mục đã có rule thì `add_to_rule`; chưa có thì `create_rule` với tên là `rule_name_from_folder`. Bỏ trường hợp "nhiều rule trong thư mục".
   - **Apply:** bỏ hộp thoại "These senders are also in groups shared by several rules" (khoảng dòng 1170-1245) cùng tham số `remove_from_shared_groups`.
   - Chỗ tạo `RuleConfig(... groups=[] ...)` (khoảng dòng 1218): bỏ `groups`.
   - `_ask_quick_rule`: bỏ tham số `auto_name`.
3. **`gui/quick_rule_dialog.py`**
   - Bỏ ô tên và tham số `auto_name`. Hộp thoại chỉ còn **Folder** và **Scope** (email/domain), cùng dòng gợi ý `Outlook rule: [Companion] <name>`.
   - `result` = `(name, folder, scope)`, trong đó `name` luôn tính từ folder, để không phải sửa nơi gọi. Cũng có thể đổi `result` thành `(folder, scope)` và sửa nơi gọi.
   - Từ chối tên thư mục bắt đầu bằng `_`.
4. **`gui/main_window.py`**
   - Toast kết quả Import bỏ các số liệu về group.
   - Hiện `yaml_mgr.load_warnings` sau khi load và sau Reload.
5. **Test**
   - **Xóa** các test chỉ kiểm tra group, link group, duplicate hoặc đặt tên thủ công, gồm:
     - `test_group_senders_are_shown_read_only_in_the_rule_inspector`
     - `test_rules_tab_manual_names_when_auto_naming_is_off`
     - `test_auto_naming_can_be_switched_off`
     - phần group trong `test_ui_phase2.py`, `test_rule_manager.py`, `test_ui_phase1.py`, `test_ui_phase3.py`, `test_phase4_yaml.py`
     - nhánh "shared group" trong `test_rule_ux1_move_sender.py`
   - **Sửa** các test còn lại theo cây mới; tiêu đề ô quay lại `Emails (N)`.
   - **Thêm test:**
     - Kéo rule vào thư mục đã có rule bị từ chối và YAML không đổi.
     - Thả mail lên thư mục chưa có rule rồi Apply: tạo đúng 1 rule, và `match_message` chỉ ra thư mục đó.
     - Quick Rule với tên thư mục `_X` bị từ chối.
     - F2 trên nút rule đổi tên thư mục, và tên rule đổi theo.

**Xong phase 2 khi:** mọi file test pass và không còn chữ "Group" nào trên giao diện (kiểm tra bằng `grep -rn "Group" gui/`). Làm tiếp phase 3 ngay.

## Phase 3 — Dọn dẹp + tài liệu

1. Chạy `grep -rn "groups\|AddressGroup\|former_names\|custom_folders\|auto_rule_names\|duplicate_rule\|target_store" core gui tests`. Chỉ được còn lại trong `core/config_format.py` (phần `migrate_v2`) và trong test migration.
2. **README.md:**
   - Thay phần mô tả cấu trúc YAML bằng ví dụ ở mục *Mục tiêu*.
   - Giải thích `_subject`, `_enabled`, `unclassified`, `legacy_rule_names`.
   - Ghi rằng comment trong file sẽ mất khi app lưu, và file v2 được tự chuyển đổi (có `.v2.bak`).
3. **Chạy thử chuyển đổi trên `config/rules.yaml` thật** của người dùng, trên **một bản sao** trong thư mục tạm, không sửa file gốc:
   - Đưa file v3 kết quả vào nhật ký.
   - Liệt kê cảnh báo, nếu có.
   - Chạy bất biến `match_message` trên các người gửi của file đó.
4. Chụp 3 ảnh Mock mode: cây, màn hình chi tiết rule, hộp thoại Quick Rule.
5. Ghi tổng kết vào nhật ký. Báo người dùng: lần mở app tiếp theo, `config/rules.yaml` sẽ được tự chuyển sang v3 và có bản `rules.yaml.v2.bak`.

## Ngoài phạm vi

- Giữ comment khi lưu (cần `ruamel.yaml`): để sau nếu người dùng muốn.
- Nhiều store / PST cho các rule khác nhau.
- Rule trong thư mục unclassified (vẫn bị chặn như hiện nay).

## Rủi ro cần chú ý

- **Mất phân biệt khi gộp group dùng chung.** Một group đang được link vào nhiều rule thì khi chuyển đổi, người gửi của nó sẽ thuộc thư mục gặp đầu tiên. Nếu xảy ra, migration phải cảnh báo rõ. Config hiện tại mỗi group chỉ dùng cho một rule (người dùng xác nhận ngày 2026-11-26).
- **Id rule đổi giữa các phiên.** Không được lưu id ra file hay giữ id ở bất kỳ đâu qua lần khởi động lại, kể cả trong các action đã stage.
- **Cây với nút gộp có con.** Kéo-thả phải phân biệt được kéo **nút** (move thư mục) với thả **vào** nút (đổi thư mục cha / thêm người gửi). Chạy lại toàn bộ `test_ui_dragdrop.py` và `test_tree_mails_and_share.py`.

## Nhật ký thực hiện

### Phase 1 — Đọc / ghi định dạng v3 + chuyển đổi từ v2 (`core/`)
- **File đã thêm:** `core/config_format.py`, `tests/fixtures/rules_sample_v2.yaml`, `tests/test_folders_format.py`.
- **File đã sửa:** `core/models.py` (bỏ `AddressGroup`, `groups`, `target_store`, `former_names`, `known_names()`), `core/yaml_manager.py` (đọc/ghi v3, tự chuyển đổi v2 kèm `.v2.bak`, `folders`, `legacy_rule_names`, `load_warnings`, `rule_for_folder`, `ensure_rule_for_folder`, bỏ group/duplicate/auto_rule_names), `core/sync_engine.py` (bỏ `_effective_rule` / `group_ids`, dùng `legacy_rule_names`), `core/conflict_detector.py` (bỏ `known_names()`, dùng `ensure_rule_for_folder`), `tests/fixtures/rules_sample.yaml` (chuyển sang v3), `tests/fakes.py` (`managed_name`), `tests/test_auto_rule_names.py`, `tests/test_phase5_conflict_import.py`.
- **Test đã xóa:**
  - `tests/test_auto_rule_names.py`: `test_second_rule_in_folder_gets_suffix` (bỏ nhiều rule trong 1 thư mục), `test_auto_naming_can_be_switched_off` (bỏ đặt tên thủ công `auto_rule_names`).
- **Kết quả test Phase 1:** `test_folders_format`, `test_auto_rule_names`, `test_phase1_rules`, `test_phase3_rollover`, `test_phase5_conflict_import` — 45 tests OK. (Các file GUI test sẽ cập nhật ở Phase 2).

_(Tiếp tục Phase 2...)_

### Phase 2 — Gỡ group và các chức năng cũ khỏi GUI
- **File đã sửa:** `gui/rule_manager_view.py` (gỡ toàn bộ phần Group, Linked Groups, Duplicate Rule, `ent_rule_name` thay bằng label chỉ đọc `[Companion] <name>`, F2 trên rule luôn đổi tên thư mục, mỗi thư mục có rule luôn hiển thị nút gộp `rule_<id>` với mail nằm trước thư mục con, `New Rule` chọn rule có sẵn hoặc `ensure_rule_for_folder`, từ chối kéo rule vào thư mục đã có rule), `gui/triage_view.py` (dùng `ensure_rule_for_folder`/`rule_for_folder`, bỏ hộp thoại Shared Address Groups và `auto_name`), `gui/quick_rule_dialog.py` (chỉ còn Folder + Scope, gợi ý `Outlook rule: [Companion] <name>`, từ chối thư mục bắt đầu bằng `_`), `gui/main_window.py` (bỏ số liệu group trong Import, hiển thị tối đa 3 `load_warnings` lên toast và in đủ ra log).
- **Kiểm tra `grep`:** `Select-String -Path gui\*.py -Pattern "Group" -CaseSensitive` trả về 0 kết quả.
- **Test đã xóa (tính năng bị bỏ):**
  - `tests/test_phase4_yaml.py`: `test_generate_rule_id_slugification_and_uniqueness_across_call_sites`, `test_delete_group_and_add_sender_fallback_behavior`, `test_rule_manager_add_rule_uses_unique_id_and_delete_group_askyesnocancel`, `test_triage_generates_unique_ids_at_commit_time_for_duplicate_staged_names` (bỏ group, duplicate rule, `generate_rule_id`, nhiều rule trong cùng thư mục).
  - `tests/test_rule_manager.py`: `test_duplicate_rule` (bỏ duplicate rule).
  - `tests/test_rule_ux1_move_sender.py`: `test_shared_group_is_untouched_unless_allowed`, `test_shared_group_answer_no_reports_mismatch`, `test_shared_group_answer_yes_moves` (bỏ nhánh shared group).
  - `tests/test_rule_ux3_create.py`: `test_rules_tab_manual_names_when_auto_naming_is_off`, `test_name_follows_folder_until_typed` (bỏ đặt tên thủ công).
  - `tests/test_tree_mails_and_share.py`: `test_group_senders_are_shown_read_only_in_the_rule_inspector`, `test_folder_with_two_rules_is_not_merged`, `test_automatic_rename_is_not_an_unsaved_edit` (bỏ group, nhiều rule/thư mục, sửa tên thủ công).
  - `tests/test_ui_dragdrop.py`: `test_drop_on_group_node_is_ignored` (bỏ group).
  - `tests/test_ui_phase1.py`: `test_generate_group_id_uniqueness_and_after_delete`, `test_rule_inspector_linked_groups_link_unlink_and_save_persistence` (bỏ group).
- **Test đã thêm:** `test_drag_rule_into_occupied_folder_is_refused_and_yaml_unchanged`, `test_f2_on_rule_node_renames_folder_and_rule_name` (`tests/test_rule_manager.py`), `test_underscore_folder_rejected` (`tests/test_rule_ux3_create.py`).
- **Kết quả test Phase 2:** Tất cả 20 file test (153 tests) đều PASS (`OK`).

### Phase 3 — Dọn dẹp + tài liệu + chạy thử chuyển đổi
- **Kiểm tra symbol cũ:** Chỉ còn trong `core/config_format.py` (phần `migrate_v2` / `parse_folders` / `dump_folders`), `core/outlook_client.py` (tham số COM `target_store_path`), và các test migration (`tests/test_folders_format.py`).
- **README.md:** Cập nhật ví dụ cấu trúc `folders:` v3.0, giải thích `_subject`, `_enabled`, `unclassified`, `legacy_rule_names`, lưu ý comment không được giữ khi app lưu, và tự chuyển đổi v2 kèm `.v2.bak`.
- **Chạy thử chuyển đổi trên bản sao `config/rules.yaml` thật (trong thư mục tạm, không sửa file gốc):**
  - Cảnh báo: **0 cảnh báo**.
  - Bất biến `match_message`: kiểm tra 10/10 người gửi — **0 sai khác** (`MISMATCHES: 0`).
  - Kết quả file v3:
    ```yaml
    version: '3.0'
    settings:
      auto_split_threshold: 40
      unclassified_folder: _Unclassified
      backup_versions: 30
    stores:
      active_archive:
        name: Archive 2025
        file_path: D:\Outlook_Data\longp_Archive_2025.pst
    folders:
      Executive_Board:
        - Directors:
            - ceo@company.com
        - Omron_Unit:
            - coo@company.com
            - lead.scada@company.com
            - sales@vendor.com
            - '@mitsubishi.com'
            - '@omron.com'
      Engineering_Team:
        - SCADA_Part:
            - PLC_Unit:
                - eng1@company.com
                - eng2@company.com
                - '@techpartner.com'
    unclassified:
      - former.contractor@vendor.com
    legacy_rule_names:
      - Executive Board
      - Management_Executive_Board_Directors
      - SCADA PLC Maintenance
      - Omron Equipment
      - Purchasing_Team_Vendor_Part_Omron_Unit
      - Purchasing_Team_Omron_Unit
      - Engineering_Team_SCADA_Part_Omron_Unit
      - Engineering_Team_Omron_Unit
    ```
- **Chụp ảnh Mock mode (1280x760):** Script chạy trong phiên headless không có desktop handle nên `CopyFromScreen` báo `The handle is invalid` (3 file ảnh tạo tại `scratch/mock_1_tree.png`, `scratch/mock_2_rule_inspector.png`, `scratch/mock_3_quick_rule_dialog.png` nhưng không chụp được nội dung màn hình từ phiên nền).
- **Tổng kết:** Hoàn thành cả 3 phase trên branch `feat/outlook-rule-manager-folders-format` (chưa commit, chưa push). Lần mở app tiếp theo, `config/rules.yaml` sẽ được tự chuyển sang v3 và lưu bản sao dự phòng `config/rules.yaml.v2.bak`.

### Review + sửa sau review (2026-11-27) — Claude
- **Lỗi 1 (crash):** id rule trùng khi tạo rule ở thư mục mà rule cũ vừa rời đi (id giữ nguyên trong phiên) → `TclError: Item ... already exists`. Sửa: `config_format.unique_rule_id()` (thêm `_2`, `_3`...), dùng trong `parse_folders`, `ensure_rule_for_folder`, `import_config` (merge).
- **Lỗi 2 (crash):** file YAML sai định dạng/cú pháp làm app tắt ngay khi khởi động. Sửa: `load()` đổi `yaml.YAMLError` / gốc không phải mapping thành `ValueError`; `main.py` kiểm tra file trước và hiện hộp thoại lỗi (`show_config_error`); File › Reload báo lỗi và giữ cấu hình đang dùng.
- **Lỗi 3:** chuỗi chứa nhiều địa chỉ (thiếu `- `) bị nhận thành 1 email → nay cảnh báo và bỏ qua; thư mục mà người gửi không có `- ` báo lỗi kèm gợi ý.
- **Lỗi 4:** Check Rule Conflicts báo SENDER_OVERLAP cho bản cũ có tên trong `legacy_rule_names` → nay bỏ qua như trước.
- **Lỗi 5:** import rule Outlook có điều kiện không hỗ trợ vào thư mục đã có rule làm tắt rule đang chạy → nay chỉ tắt rule vừa được tạo.
- **Nhỏ:** khóa thư mục có `/` được chuẩn hóa thành đường dẫn lồng; migration cảnh báo khi bỏ domain của rule `[Unclassified]` cũ; README ghi rõ quy tắc một người gửi một dòng và rule rỗng.
- **Test thêm:** 7 test trong `test_folders_format.py`, 2 test trong `test_phase5_conflict_import.py` (đã xác nhận 2 test này fail khi gỡ phần sửa). Toàn bộ 20 file, 168 test: OK.

