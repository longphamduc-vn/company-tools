# Kế hoạch sửa giao diện (UI/UX) — outlook-rule-manager

Tài liệu này là chỉ dẫn cho agent thực hiện (Gemini). Sau mỗi phase, agent **dừng lại** để Claude review (đọc diff + chụp màn hình app) trước khi làm phase tiếp theo.

## Quy tắc chung

- Tạo branch `fix/outlook-rule-manager-ui` **từ `fix/outlook-rule-manager-review`** (branch đó chứa các bản sửa logic, chưa merge). **Không** push, **không** merge.
- **Không** `git add` / commit `config/rules.yaml` — file này đang có thay đổi riêng của người dùng. Dùng `git add <đường dẫn cụ thể>`, không dùng `git add -A` hay `git add .`.
- Mỗi phase = 1 commit: `fix(outlook-rule-manager): ui phase <N> - <tên>`.
- Giữ nguyên Tkinter/ttk, không thêm thư viện mới. Không viết lại toàn bộ view; chỉ sửa đúng phần được nêu.
- Logic mới (ID, theo dõi trạng thái sync, tính quota…) đặt trong `core/` và **phải có unit test**. Phần thuần hiển thị không bắt buộc test, nhưng nếu widget có thể kiểm tra được (text, trạng thái `disabled`, `winfo_ismapped()`) thì nên viết.
- Test không được kết nối Outlook thật (dùng `MockOutlookClient` hoặc fakes trong `tests/fakes.py`). Chạy: `python -m pytest -q tests` trong `outlook-rule-manager/`. Tất cả phải pass.
- Văn bản trên giao diện giữ bằng **tiếng Anh** như hiện tại (không dịch).
- Cuối mỗi phase: ghi vào mục *Nhật ký thực hiện* cuối file này (đã làm gì, lệch plan chỗ nào, lý do), rồi báo commit hash + output pytest.

---

## Phase UI-1 — Dữ liệu & trạng thái (làm trước)

### 1.1 ID group bị trùng → ghi đè group (lỗi mất dữ liệu)
[gui/rule_manager_view.py:1457](gui/rule_manager_view.py#L1457) `_add_group` sinh `group_{len(groups)+1}`; sau khi xóa một group, ID mới có thể trùng group đang có và phép gán dict sẽ **thay thế** group đó.
- Thêm `YamlConfigManager.generate_group_id(base: str) -> str` (cùng quy tắc với `generate_rule_id`, tiền tố `group_`, so trùng với `self.groups`).
- Dùng nó trong `_add_group`. Grep thêm mọi chỗ khác tạo group.
- Test: tạo 3 group, xóa group thứ 2, tạo group mới → cả 2 group cũ còn nguyên, ID mới không trùng.

### 1.2 Rule inspector hiển thị và sửa được group
`_build_rule_inspector` / `_populate_rule_inspector` ([gui/rule_manager_view.py:178](gui/rule_manager_view.py#L178), [:622](gui/rule_manager_view.py#L622)) không hiển thị `rule.groups`, nên rule chỉ dùng group trông như rỗng.
- Thêm khu vực **"Linked Groups"** phía trên Direct Emails: danh sách group đang gắn (tên + số email/domain), nút **Link Group…** (chọn từ các group chưa gắn) và **Unlink**.
- Gắn/gỡ group đi qua `_save_rule_changes` như các trường khác (xem 3.6 về cơ chế lưu).
- Dòng quota (mục 2.4) tính cả địa chỉ từ group — đã đúng hiện tại, giữ nguyên.

### 1.3 Cảnh báo rõ khi đang ở Mock mode
Khi không kết nối được Outlook, `get_outlook_client()` rơi về `MockOutlookClient` và chỉ có 1 dòng chữ nhỏ màu vàng ([gui/main_window.py:55-58](gui/main_window.py#L55-L58)).
- Thêm `BaseOutlookClient.is_simulated() -> bool` (Mock = True, Windows = False).
- Khi `is_simulated()`: hiển thị **banner nền đỏ nhạt, chữ đậm** ngay dưới header, toàn chiều rộng: `SIMULATION MODE — Outlook is not connected. Sync, Move and Rollover do NOT change Outlook.` Kèm nút **Retry Connection** (thử `get_outlook_client()` lại; nếu kết nối được thì thay client cho mọi view + SyncEngine và ẩn banner, nếu không thì báo lỗi).
- Nút Sync đổi chữ thành `Sync (Simulated)` khi ở Mock mode. Các hộp thoại kết quả của Sync / Triage commit / Rollover thêm dòng đầu `[SIMULATION] No changes were made to Outlook.`
- Test: MainWindow với Mock → banner `winfo_ismapped()` True và text nút Sync chứa "Simulated"; với `WindowsOutlookClient(namespace=FakeNamespace())` → banner ẩn.
  - MainWindow hiện tự gọi `get_outlook_client()`; thêm tham số tùy chọn `outlook_client=None` vào `MainWindow.__init__` để inject trong test.

### 1.4 Chỉ báo "có thay đổi chưa sync"
Mọi thao tác tự lưu YAML, nhưng Outlook chỉ cập nhật khi bấm Sync; người dùng không biết hai bên đang lệch.
- Trong `YamlConfigManager`: thêm cơ chế listener (`add_change_listener(callback)`), gọi sau mỗi `save()` thành công; thêm bộ đếm `unsynced_changes` (tăng mỗi lần save).
- Trong `SyncEngine.push_to_outlook`: nếu thành công **và không phải simulated** → đặt `yaml_mgr.unsynced_changes = 0` và gọi listener.
- Header `MainWindow`: label trạng thái cạnh nút Sync:
  - `> 0`: `● N unsynced change(s)` màu cam, nút Sync dùng style nhấn mạnh (nền xanh, chữ trắng).
  - `= 0`: `✓ Outlook in sync` màu xanh lá.
  - Lúc mở app (chưa sync lần nào trong phiên): `Not synced this session` màu xám.
- `Reload YAML` không reset bộ đếm.
- Test (core): save 3 lần → `unsynced_changes == 3`; push thành công với fakes → 0; push thất bại → giữ nguyên; push ở Mock → giữ nguyên.

---

## Phase UI-2 — Tính năng thiếu & hiển thị sai

### 2.1 Sửa được subject keywords trong GUI
YAML và engine đã hỗ trợ `subject_keywords` nhưng rule inspector không có ô nhập.
- Thêm khu vực **"Subject Keywords"** dưới Domains, dùng cùng kiểu với Domains (Visual Chips: ô nhập + Add + Remove Selected; Bulk Text Editor: mỗi dòng 1 keyword).
- Lưu qua `_save_rule_changes`: strip, bỏ rỗng, bỏ trùng (không phân biệt hoa thường, giữ cách viết đầu tiên).
- `Test Match` ([gui/rule_manager_view.py:1359](gui/rule_manager_view.py#L1359)) hiện chỉ test địa chỉ: thêm ô Subject tùy chọn để test keyword.
- Test: lưu rule với `["SCADA", " scada ", "", "Alarm"]` → `["SCADA", "Alarm"]`.

### 2.2 Footer bị che & không cập nhật
[gui/main_window.py:99-111](gui/main_window.py#L99-L111): notebook pack trước với `expand=True` nên footer bị đẩy ra ngoài cửa sổ.
- Pack footer (và separator của nó) với `side=tk.BOTTOM` **trước** khi pack notebook.
- Tách `_refresh_footer()`; gọi sau Reload YAML, sau rollover thành công, sau khi đổi client (1.3). Footer hiển thị: `Active archive: <name> (<path>)` + trạng thái tồn tại của store (`found in Outlook` / `NOT found in Outlook`) dùng `outlook.store_exists`.
- Test: sau `update()`, footer `winfo_ismapped()` True ở kích thước 1120x720.

### 2.3 Tab Rollover
[gui/rollover_view.py:133-191](gui/rollover_view.py#L133-L191):
- **Bỏ giá trị hard-code** `..._Archive_2025` và `C:\Outlook_Data\...`. Gợi ý tên = tên store hiện tại với năm được +1 nếu tên có chứa năm 4 chữ số (vd `Archive 2025` → `Archive 2026`); gợi ý đường dẫn = cùng thư mục với `file_path` hiện tại, tên file thay năm tương tự. Không có năm → để trống. Logic gợi ý đặt trong hàm thuần (vd `core/rollover_suggest.py`) và có test.
- `refresh_view` **không** ghi đè ô nhập nếu người dùng đã sửa chúng (chỉ điền gợi ý khi ô trống hoặc lần đầu).
- **Health Status**: nếu `file_path` không tồn tại trên đĩa → `[MISSING] File not found on disk` (màu đỏ); nếu tồn tại nhưng `store_exists` False → `[NOT MOUNTED] File exists but is not open in Outlook` (màu cam). Bỏ chữ "File managed by Outlook".
- Nút **Execute 1-Click Rollover** chỉ bật khi đường dẫn trong ô khớp một store đang mount (`outlook.store_exists`), và khác store hiện tại. Kiểm tra lại mỗi khi ô đường dẫn thay đổi. Kèm dòng chữ nhỏ giải thích lý do khi bị tắt.
- Thêm dòng hướng dẫn: `Tip: open the new PST in Outlook first (File > Open > Outlook Data File), then select it in the table above.`
- Test: hàm gợi ý (`Archive 2025` → `Archive 2026`, đường dẫn D:\...\x_2025.pst → D:\...\x_2026.pst, không có năm → rỗng); trạng thái nút Execute với Mock (đường dẫn store mock → bật; đường dẫn lạ → tắt).

### 2.4 Dòng quota sai sau khi tách sub-rule
[gui/rule_manager_view.py:634-650](gui/rule_manager_view.py#L634-L650) luôn ghi "(1 native sub-rule)".
- Thêm hàm thuần trong `core/` (vd `SyncEngine.preview_compiled_rules(rule) -> List[str]` trả danh sách tên sub-rule sẽ tạo, dùng chung logic với `push_to_outlook` — **không** nhân bản logic split).
- Dòng quota: `Outlook: N senders, M domains, K keywords → X native rule(s)`; liệt kê tên sub-rule trong tooltip hoặc label nhỏ bên dưới. Rule không có điều kiện → `⚠ No conditions — will be skipped on sync` (màu cam). Rule không có target folder → cảnh báo tương tự.
- Test: preview cho rule 41 email + 1 domain + 1 keyword → 4 tên đúng thứ tự.

---

## Phase UI-3 — Bố cục, chữ, tính nhất quán

### 3.1 Tab Triage: tỷ lệ cột
[gui/triage_view.py:118-252](gui/triage_view.py#L118-L252): panel trái và danh sách mail quá hẹp, khung đọc chiếm gần nửa.
- Weight paned: trái 3, giữa 5, phải 3. Tăng width cột `#0` của tree_rules (≥ 220) và cột Sender/Subject của tree_inbox.
- Drop zone: chữ không được tràn/cắt — dùng `wraplength` theo chiều rộng (bind `<Configure>`), nội dung ngắn: `Drop an email here to create a new rule`. Bỏ chữ "Instant staging (0ms)".
- Ô tìm kiếm: thêm nhãn `Search:` đứng trước.
- Nút `Assign to Rule… ▼ ▼` bị lặp mũi tên: chỉ còn một.

### 3.2 Nhãn kỹ thuật trong cây (cả Triage và Rules)
- Bỏ tiền tố `[L1]`/`[L2]`/`[L3]` trên tên folder (thụt lề đã thể hiện cấp). Cột "Level / Senders" giữ nguyên.
- Thay `[ON]`/`[OFF]` bằng ký hiệu + màu qua tag Treeview: rule bật chữ thường; rule tắt chữ xám nghiêng + hậu tố ` (disabled)`.
- Tiêu đề viết hoa dài (`HIERARCHICAL FOLDERS & RULES`, `DYNAMIC FOLDER HIERARCHY & RULES NAVIGATOR`) → `Folders & Rules`, `Shared Address Groups`, `Unclassified Pool`.
- Rule `[Unclassified]` đang ghi `0 senders` dù pool có địa chỉ: tính cả `unclassified_pool` cho rule unclassified (dùng chung hàm đếm với 2.4).

### 3.3 Dòng tip bị cắt ở tab Rules
Label tip trên toolbar ([gui/rule_manager_view.py:935](gui/rule_manager_view.py#L935) và nơi tạo label) bị cắt chữ đầu ("ip: …"). Chuyển tip xuống thanh trạng thái/toast dưới cây hoặc dùng `wraplength`; chữ không được cắt ở 1120x720.

### 3.4 Nút trùng chức năng
- Tab Rules: bỏ cặp nút "Delete Selected"/"Duplicate Rule" dưới cây **hoặc** cặp trong inspector — giữ **một** chỗ (khuyến nghị: giữ trong inspector, dưới cây chỉ giữ thao tác cho mục đang chọn qua menu chuột phải đã có).
- Chuyển nút "Check Rule Conflicts" từ toolbar Triage lên header MainWindow, cạnh "Sync to Outlook".

### 3.5 Checkbox "Active in Outlook"
Đổi thành `Enabled` + chú thích nhỏ `(applies to Outlook on next Sync)`.

### 3.6 Cơ chế lưu nhất quán trong inspector
Hiện kéo-thả/đổi tên/tạo mới tự lưu, nhưng sửa email/domain trong inspector phải bấm "Save Rule to YAML"; chọn rule khác thì thay đổi bị mất không cảnh báo.
- Theo dõi "dirty" cho rule inspector và group inspector (so giá trị trên form với dữ liệu đã lưu).
- Khi dirty: nút Save đổi thành `Save Changes ●` và được nhấn mạnh.
- Khi người dùng chọn mục khác / đổi tab / đóng app mà form đang dirty → hỏi `Save changes to '<name>'?` với Yes / No / Cancel (Cancel = giữ nguyên lựa chọn cũ).
- Test: sửa domain trên form rồi chọn rule khác, patch messagebox trả Yes → đã lưu; No → không lưu; Cancel → vẫn ở rule cũ.

---

## Ngoài phạm vi (không làm)

- Đổi framework GUI, đổi theme toàn cục, thêm dark mode.
- Dịch giao diện sang tiếng Việt.
- Thay đổi logic sync/rollover/import đã sửa ở `FIX_PLAN.md` (trừ khi task nêu rõ).

## Checkpoint review

Sau mỗi phase, agent báo: commit hash, danh sách file đổi, output `pytest -q`, các điểm lệch plan. Claude sẽ review diff và chụp lại màn hình app (Mock mode, 1120x720) để so với trước khi sửa.

---

## Nhật ký thực hiện

<!-- Agent ghi lại ở đây sau mỗi phase -->

### Phase UI-1 (2026-11-26)
- **1.1 (Group ID uniqueness):** Tách helper `_generate_unique_id(prefix, base, existing_ids)` trong `core/yaml_manager.py` dùng chung cho `generate_rule_id` và `generate_group_id` (tiền tố `grp_`); cập nhật `RuleManagerView._add_group` trong `gui/rule_manager_view.py` để dùng `self.yaml_mgr.generate_group_id(g_name)`.
- **1.2 (Linked Groups editor):** Bổ sung khung **Linked Groups** (`lst_rule_groups`, `Link Group...`, `Unlink`) trong Inspector của `RuleManagerView` (`gui/rule_manager_view.py`) cùng state tạm `_editing_rule_group_ids`, chỉ ghi nhận vào `selected_rule.groups` khi nhấn `Save Rule to YAML` (`_save_rule_changes`).
- **1.3 (Simulation mode visibility & retry):** Thêm `is_simulated()` trên `BaseOutlookClient`, `WindowsOutlookClient`, `MockOutlookClient` (`core/outlook_client.py`); hỗ trợ truyền `outlook_client` vào `MainWindow.__init__`; thêm banner đỏ `SIMULATION MODE` kèm nút `Retry Connection` (`_retry_outlook_connection` gọi `get_outlook_client()` và cập nhật lại `outlook` cho các tab khi kết nối thật thành công), nhãn nút `Sync (Simulated)` trong Mock mode, và tiền tố `[SIMULATION] No changes were made to Outlook.` trên các hộp thoại kết quả của `MainWindow._sync_to_outlook`, `TriageView._move_selected_now`, `TriageView._apply_all_staged`, `RolloverView._execute_rollover`, và `ConflictDialog._execute_resolutions`.
- **1.4 (Unsynced status tracking):** Thêm `unsynced_changes`, `has_synced`, `add_change_listener`, `_notify_change_listeners`, `mark_synced` trong `YamlConfigManager` (`core/yaml_manager.py`) — tăng bộ đếm khi `save()` thành công và giữ nguyên qua `load()`. Cập nhật `SyncEngine.push_to_outlook` (`core/sync_engine.py`) gọi `mark_synced()` khi sync với Outlook thật thành công. Hiển thị `lbl_sync_status` và đổi style `btn_sync` (`SyncPending.TButton` / `Accent.TButton`) trên header `MainWindow`.
- **Kiểm thử & sai khác:** Tạo `tests/test_ui_phase1.py`; chạy `python -m pytest -q tests` -> `73 passed in 5.35s`. Trong quá trình kiểm thử giữ nguyên cơ chế `get_outlook_client()` ở `_retry_outlook_connection()` và patch trực tiếp `gui.main_window.get_outlook_client`. Không phát sinh sai khác ngoài kế hoạch Phase UI-1.

### Phase UI-1 — Review Fixes (2026-11-26)
- **Rule & Group Inspector layout (`gui/rule_manager_view.py`):** Pack thanh nút hành động (`btn_bar_rule` và `btn_bar_grp`, kèm `tester_strip` trong rule inspector) với `side=tk.BOTTOM` trước phần nội dung mở rộng; bọc vùng điều kiện rule (`Linked Groups`, `Visual`/`Bulk` emails/domains) và vùng thành viên group (`txt_group_emails`, `txt_group_domains`) vào helper dùng chung `_create_scrollable_section` (`Canvas` + `ttk.Scrollbar` + `_on_scrollable_mousewheel` khi con trỏ ở trong vùng). Đặt lại vị trí cuộn về đầu khi chọn rule/group khác.
- **Rollover sync status (`core/sync_engine.py`):** Sau `self.yaml_mgr.save()` thành công trong `SyncEngine.perform_rollover()`, gọi `self.yaml_mgr.mark_synced()` nếu `not self.outlook.is_simulated()`.
- **Header sync status label (`gui/main_window.py`):** Chuyển `lbl_sync_status` từ `tk.Label` sang `ttk.Label` và cập nhật tham số màu `foreground=...` để khớp màu nền thanh header theo theme `clam`.
- **Kiểm thử bổ sung (`tests/test_ui_phase1.py`):** Thêm test hiển thị nút `Save` ở `1120x720` và `920x460` kèm cuộn con lăn chuột (`test_inspector_save_button_visible_and_scrollable_at_1120x720`), test `perform_rollover` đưa `unsynced_changes == 0` với client thật (`test_rollover_resets_unsynced_changes_for_real_client`), và kiểm tra `isinstance(win.lbl_sync_status, ttk.Label)`.
