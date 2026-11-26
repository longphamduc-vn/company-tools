# Kế hoạch sửa lỗi — outlook-rule-manager

Tài liệu này là chỉ dẫn cho agent thực hiện (Gemini). Sau mỗi phase, agent **dừng lại** để Claude review trước khi làm phase tiếp theo.

## Quy tắc chung

- Làm trên branch `fix/outlook-rule-manager-review` (tạo từ `main`). **Không** push, **không** merge.
- Mỗi phase = 1 commit riêng, message dạng `fix(outlook-rule-manager): <phase>`.
- Chỉ sửa trong `outlook-rule-manager/`. Không refactor/đổi tên/format lại code ngoài phạm vi task.
- Không đổi schema `rules.yaml` trừ khi task yêu cầu; file YAML cũ phải load được bình thường.
- **Test không được kết nối Outlook thật**: luôn dùng `MockOutlookClient` hoặc fake COM object tự viết.
- Môi trường test: `pip install pyyaml openpyxl pytest`, chạy `python -m pytest -q tests` từ thư mục `outlook-rule-manager/`.
- Cuối mỗi phase: toàn bộ test phải pass. Ghi vào cuối file này (mục *Nhật ký thực hiện*) những gì đã làm, những gì bỏ qua và lý do.

---

## Phase 0 — Hạ tầng test (làm trước tiên)

1. [core/yaml_manager.py:7](core/yaml_manager.py#L7): thêm `Optional` vào `from typing import ...` (app đang crash khi import).
2. [tests/test_rule_manager.py](tests/test_rule_manager.py): thay `get_outlook_client()` bằng `MockOutlookClient()`.
3. Tạo `tests/fakes.py` chứa fake COM tối thiểu để test `WindowsOutlookClient` mà không cần Outlook:
   - `FakeRules` (iterable, `Create(name, type)`, `Remove(index_or_name)`, `Save(ShowProgress=False)`, `Count`).
   - `FakeRule` có `Name`, `Enabled`, `Conditions.From` (Recipients: `Add/Remove/Count/ResolveAll`), `Conditions.SenderAddress.Address`, `Conditions.Subject.Text`, mỗi condition có `Enabled`; `Actions.MoveToFolder` (`Enabled`, `Folder`), `Actions.Stop.Enabled`.
   - `FakeStore` (`DisplayName`, `FilePath`, `GetRootFolder()`, `GetRules()`), `FakeFolder` (`Name`, `Folders` có `Add`, `FolderPath`).
   - `FakeNamespace` (`Stores`, `DefaultStore`).
   - Cho phép khởi tạo `WindowsOutlookClient` mà không gọi COM: thêm tham số `namespace=None` vào `__init__`; nếu có thì gán trực tiếp, `_connected=True`, bỏ qua `_init_com()`.
4. Thêm `.gitignore` trong `outlook-rule-manager/` với `config/backups/`, rồi `git rm --cached` các file backup đã commit (không xóa file trên đĩa).

**Tiêu chí xong:** `import core.yaml_manager` không lỗi; test hiện có chạy được.

---

## Phase 1 — Không để Outlook rule thiếu điều kiện (lỗi #2, nghiêm trọng nhất)

File: [core/outlook_client.py](core/outlook_client.py) `save_native_rules`, [core/sync_engine.py](core/sync_engine.py).

1. Với mỗi rule compile:
   - `emails` → `Conditions.From` (giữ như cũ).
   - `domains` → `Conditions.SenderAddress.Address = list(domains)`, `Enabled = True`.
   - `subject_keywords` → `Conditions.Subject.Text = list(keywords)`, `Enabled = True`.
   - Condition nào rỗng thì set `Enabled = False` và xóa hết giá trị cũ (Recipients/Address/Text) — để rule cũ không giữ sender lỗi thời.
2. **Chốt chặn an toàn**: nếu một rule không có email, domain lẫn keyword → **không** tạo/cập nhật nó trong Outlook; nếu đã tồn tại thì set `Enabled = False`. Ghi tên rule vào danh sách cảnh báo trả về trong message.
   - Kiểm tra ở cả `SyncEngine.push_to_outlook` (lọc trước) và `save_native_rules` (phòng thủ).
3. Lưu ý ngữ nghĩa Outlook: email OR domain OR keyword trong một rule Outlook sẽ thành **AND** giữa các condition. Để giữ ngữ nghĩa OR như YAML/dry-run, compile **mỗi loại condition thành sub-rule riêng**: `Name`, `Name (Domains)`, `Name (Keywords)` (chỉ tạo loại nào có dữ liệu). Splitting theo số lượng email vẫn áp dụng cho phần email.
4. Domain splitting: [core/rule_splitter.py](core/rule_splitter.py) — split cả domain theo cùng ngưỡng; `max_recipients <= 0` → dùng mặc định 40 (hoặc raise `ValueError` rõ ràng, chọn một và ghi lại).
5. [gui/triage_view.py:716](gui/triage_view.py#L716): bỏ heuristic hard-code (`"omron"`, `"corp"`, `"vendor"`...). Mặc định luôn là `"email"`; domain chỉ khi người dùng chọn.

**Test cần thêm** (dùng fakes):
- Rule chỉ có domain → Outlook rule có `SenderAddress` enabled, `From` disabled, không có rule nào thiếu condition.
- Rule không có gì → không được tạo, message có cảnh báo.
- Rule có cả email + domain → ra 2 Outlook rule riêng.
- Rule có email bị xóa hết → `From` disabled và Recipients rỗng.
- `split_rule_recipients` với 0, 1, 40, 41, 81 email và domain dài.

---

## Phase 2 — Sync quản lý vòng đời rule (lỗi #3)

1. **Đánh dấu rule do app quản lý**: mọi rule compile có tên dạng `[Companion] <Name>` (conflict detector đã giả định prefix này ở [conflict_detector.py:374](core/conflict_detector.py#L374)). Hằng số `MANAGED_PREFIX = "[Companion] "` đặt trong một chỗ (vd `core/models.py`).
2. `save_native_rules` thành **reconcile**:
   - Tạo/cập nhật các rule trong danh sách compile.
   - Rule trong Outlook có prefix nhưng **không** có trong danh sách compile → xóa (`rules_col.Remove`). Bao gồm phần `(Part N)` thừa, rule đã đổi tên/xóa.
   - Rule YAML có `enabled: false` → vẫn compile với `enabled=False` (không `continue` ở [sync_engine.py:203](core/sync_engine.py#L203)).
   - **Không bao giờ** đụng vào rule không có prefix.
   - Trả về số lượng created / updated / disabled / removed.
3. **Migration** từ tên cũ (không prefix): rule Outlook không prefix mà tên trùng một rule YAML hoặc `"<tên YAML> (Part N)"` → đưa vào danh sách "rule cũ cần dọn". Không tự xóa; `push_to_outlook` nhận tham số `remove_legacy: bool = False`. GUI ([gui/main_window.py:132](gui/main_window.py#L132)) hỏi người dùng một lần, liệt kê tên, rồi gọi với `remove_legacy=True` nếu đồng ý.
4. **Dry-run khớp Outlook**: set `Actions.Stop.Enabled = True` trên mọi rule managed, và sắp thứ tự rule trong Outlook theo đúng thứ tự ưu tiên của `match_message`: tất cả sub-rule email → domain → keyword → `_Unclassified` cuối cùng (dùng `rule.ExecutionOrder`). Cập nhật docstring `match_message` cho khớp.
5. [core/conflict_detector.py](core/conflict_detector.py): so khớp tên YAML với tên Outlook sau khi bỏ prefix và hậu tố `(Part N)`/`(Domains)`/`(Keywords)` — rule split không còn bị báo là LEGACY.

**Test cần thêm:**
- Rule giảm từ 3 part xuống 1 → Part 2, 3 bị xóa.
- Rule YAML bị xóa/đổi tên → rule Outlook cũ bị xóa.
- Rule disabled trong YAML → disabled trong Outlook.
- Rule Outlook do người dùng tự tạo (không prefix) → không bị thay đổi.
- Thứ tự `ExecutionOrder` và `Stop.Enabled`.
- Conflict detector không báo `(Part N)` là LEGACY.

---

## Phase 3 — Rollover an toàn (lỗi #4)

File: [core/outlook_client.py](core/outlook_client.py), [core/sync_engine.py](core/sync_engine.py), [gui/rollover_view.py](gui/rollover_view.py).

1. Tách `_find_store(identifier) -> Optional[store]`: so khớp **chính xác** (không phân biệt hoa thường) theo `os.path.normcase(os.path.normpath(FilePath))`, nếu không có thì theo `DisplayName` chính xác. Không tìm thấy → `None`. **Không fallback về `DefaultStore`.**
   - `move_message` và `save_native_rules` cũng dùng hàm này; không tìm thấy store → trả lỗi rõ ràng, không ghi vào mailbox chính.
   - Chỉ khi `identifier` rỗng mới dùng `DefaultStore` (giữ hành vi cũ có chủ đích).
2. `rollover_rules`:
   - Chỉ xử lý rule có prefix managed.
   - Giữ nguyên cây thư mục: tính đường dẫn tương đối của folder cũ so với root folder của store cũ, tạo lại cùng đường dẫn ở store mới bằng `get_or_create_folder`.
   - Cách đơn giản hơn được chấp nhận: rollover = cập nhật store trong YAML rồi gọi lại `push_to_outlook()` (vì YAML đã có `target_folder` đầy đủ). **Khuyến nghị cách này.**
3. `SyncEngine.perform_rollover`: kiểm tra store mới tồn tại **trước**; chỉ lưu YAML sau khi Outlook thành công. Nếu Outlook thất bại → khôi phục `name`/`file_path` cũ trong bộ nhớ và không save.

**Test cần thêm:**
- Đường dẫn sai → trả `False`, YAML không đổi, không rule nào bị trỏ sang mailbox chính.
- `"Archive 2025"` không khớp `"Archive 2025 Old"`.
- `Team\Part\Unit` giữ nguyên cấu trúc ở store mới.
- Rule không prefix không bị đổi folder.

---

## Phase 4 — Dữ liệu YAML & ID

1. **Backup** ([core/yaml_manager.py:89-138](core/yaml_manager.py#L89-L138)):
   - Tên file thêm microsecond: `%Y%m%d_%H%M%S_%f`. Sửa `_prune_backups` để vẫn sort đúng (glob `rules_*.yaml` vẫn ok).
   - Ghi atomic: ghi ra `rules.yaml.tmp` cùng thư mục, `flush` + `os.fsync`, rồi `os.replace`.
   - Ghi lại `store_id` trong `stores`.
2. **Xóa folder** (`delete_folder_hierarchy`): xóa tất cả rule bị ảnh hưởng trong một lượt, repool địa chỉ, **save đúng một lần**. Tách phần logic của `remove_rule_and_repool` thành hàm nội bộ không save.
3. **ID duy nhất**: thêm `YamlConfigManager.generate_rule_id(base: str) -> str` (slug hóa `base`, thêm `_1`, `_2`... đến khi không trùng). Dùng ở:
   - `duplicate_rule` ([yaml_manager.py:413](core/yaml_manager.py#L413))
   - Tạo rule mới trong [gui/rule_manager_view.py:1200](gui/rule_manager_view.py#L1200)
   - `resolve_import_to_yaml` ([conflict_detector.py:397](core/conflict_detector.py#L397))
   - Triage ([gui/triage_view.py:1050-1054](gui/triage_view.py#L1050-L1054)) — thay vòng lặp hiện có.
4. **Xóa group** ([gui/rule_manager_view.py:1496-1503](gui/rule_manager_view.py#L1496-L1503)): chuyển logic vào `YamlConfigManager.delete_group(g_id)` — gỡ `g_id` khỏi `groups` của mọi rule; hỏi người dùng có muốn repool email của group vào `unclassified_pool` không.
   - `add_sender_to_rule_or_group`: nếu `groups[0]` không tồn tại thì bỏ qua group đó (dùng group hợp lệ đầu tiên, hoặc ghi thẳng vào rule).
5. **Chuẩn hóa domain**: khi load và khi thêm, domain → `lower().strip()`, đảm bảo bắt đầu bằng `@`.

**Test cần thêm:**
- Nhiều lần save trong cùng một giây → mỗi lần có file backup riêng; backup đầu tiên chứa trạng thái trước khi xóa.
- Xóa folder có 5 rule → chỉ 1 file backup mới.
- Xóa rule rồi tạo/duplicate rule → ID không trùng.
- Xóa group → không rule nào còn tham chiếu; thêm sender vào rule từng dùng group đó không lỗi.
- `@Vendor.com` trong YAML khớp sender `x@vendor.com`.
- `store_id` giữ nguyên sau load → save.

---

## Phase 5 — Conflict dialog & import

1. `resolve_import_to_yaml`: giữ đường dẫn folder tương đối so với root của store (bỏ phần `\\<Tên store>\` đầu), không chỉ lấy phần cuối.
2. [gui/conflict_dialog.py:145-170](gui/conflict_dialog.py#L145-L170): tôn trọng lựa chọn của người dùng:
   - `IGNORE` → không làm gì với rule đó.
   - `IMPORT` → import vào YAML.
   - `OVERWRITE` / `MERGE` → chỉ có hiệu lực qua push.
   - Chỉ gọi `push_to_outlook()` nếu có ít nhất một mục `OVERWRITE`/`MERGE`/`IMPORT`. Thông báo kết quả đúng số lượng từng loại.
3. Không sửa phần nuốt lỗi `except Exception: pass` hàng loạt ở phase này; chỉ ở `save_native_rules`, gom các lỗi resolve recipient (`ResolveAll` trả False, hoặc recipient `.Resolved == False`) vào message trả về.

---

## Ngoài phạm vi (không làm)

- Viết lại GUI, đổi layout, đổi thư viện.
- Đổi định dạng `rules.yaml` ngoài các trường đã nêu.
- Thêm tính năng mới.

## Checkpoint review

Sau mỗi phase, agent báo lại: commit hash, danh sách file đổi, output `pytest -q`, và các điểm lệch so với plan. Claude sẽ review diff của commit đó trước khi sang phase tiếp theo.

---

## Nhật ký thực hiện

<!-- Agent ghi lại ở đây sau mỗi phase -->

### Phase 0 — Hạ tầng test
- **Đã làm:**
  - `core/yaml_manager.py`: thêm `Optional` vào `from typing import ...` để sửa lỗi `NameError` khi import.
  - `tests/test_rule_manager.py`: thay `get_outlook_client()` bằng `MockOutlookClient()` và đổi nguồn dữ liệu mẫu trong `setUp()` sang `tests/fixtures/rules_sample.yaml` (copy vào thư mục tạm).
  - `tests/fixtures/rules_sample.yaml`: tạo fixture YAML tối thiểu chứa `rule_executive`, `rule_engineering`, `rule_suppliers`, `rule_unclassified` với cấu trúc `target_folder` đúng theo kỳ vọng của các test hiện có.
  - `core/outlook_client.py`: thêm tham số `namespace=None` vào `WindowsOutlookClient.__init__`; khi có `namespace` thì gán trực tiếp, đặt `_connected=True` và bỏ qua `_init_com()`.
  - `tests/fakes.py`: tạo các lớp fake COM tối thiểu (`FakeRecipient`, `FakeRecipients`, `FakeFromCondition`, `FakeSenderAddressCondition`, `FakeSubjectCondition`, `FakeConditions`, `FakeMoveToFolderAction`, `FakeStopAction`, `FakeActions`, `FakeRule`, `FakeRules`, `FakeFolderCollection`, `FakeFolder`, `FakeStore`, `FakeCurrentUser`, `FakeNamespace`).
  - `.gitignore`: thêm `config/backups/` và chạy `git rm --cached -r outlook-rule-manager/config/backups` để gỡ tracking 17 file backup khỏi git mà vẫn giữ nguyên trên đĩa.
  - Cài dependency môi trường test (`pyyaml`, `openpyxl`, `pytest`) và chạy `python -m pytest -q tests`: `10 passed`.
- **Lệch plan & lý do:**
  - Tạo thêm `tests/fixtures/rules_sample.yaml` và sửa đường dẫn `sample_config` trong `tests/test_rule_manager.py` (thay vì giữ nguyên việc copy `config/rules.yaml`). Lý do: `config/rules.yaml` trên repo (từ commit `c9e7f62`) đã bị đổi `target_folder` (`PLC_Unit` thay vì `Engineering_Team\SCADA_Part\PLC_Unit`, `Management\Directors` thay vì `Management\Executive_Board\Directors`) làm 7/10 test fail. Theo xác nhận của user, test không được đọc/ghi `config/rules.yaml` và giữ nguyên `config/rules.yaml` không sửa trong phase này, đồng thời không sửa assertion của test.
  - Bổ sung thêm `StoreID`, `IsDataFileStore`, `CurrentUser`, `ExecutionOrder`, `GetDefaultFolder`, `GetItemFromID` vào các lớp trong `tests/fakes.py` để khớp toàn bộ thuộc tính `WindowsOutlookClient` truy cập (ngoài danh sách tối thiểu nêu trong plan).

### Tiền Phase 1 — Điều chỉnh fake COM (`1ca342f`)
- **Đã làm:**
  - `tests/fakes.py`: sửa `FakeRules.__iter__` để duyệt trực tiếp `self._rules` (không copy), và sửa `FakeFolderCollection.Add` để raise `ValueError` khi thêm folder trùng tên không phân biệt hoa thường.
  - `tests/test_fakes.py`: thêm 2 test xác nhận 2 hành vi trên (`12 passed`).

### Phase 1 — Không để Outlook rule thiếu điều kiện
- **Đã làm:**
  - `core/outlook_client.py` (`WindowsOutlookClient.save_native_rules` & `MockOutlookClient.save_native_rules`): hỗ trợ đầy đủ `From` (`emails`), `SenderAddress` (`domains`), `Subject` (`subject_keywords`); condition nào rỗng thì set `Enabled = False` và xóa giá trị cũ (`Recipients`/`Address`/`Text`). Nếu rule không có cả email, domain lẫn keyword thì bỏ qua (không tạo mới; nếu đã tồn tại thì set `Enabled = False`) và trả tên rule trong cảnh báo.
  - `core/sync_engine.py` (`SyncEngine.push_to_outlook`): lọc trước rule không có điều kiện và ghi cảnh báo vào message; biên dịch riêng từng loại điều kiện thành sub-rule `Name`, `Name (Domains)`, `Name (Keywords)` để giữ ngữ nghĩa OR trong Outlook.
  - `core/rule_splitter.py` (`split_rule_recipients`): tách riêng email và domain; split cả domain theo cùng ngưỡng `max_recipients` (`Name (Domains)` hoặc `Name (Domains) (Part N)`); `max_recipients <= 0` dùng mặc định `40`.
  - `gui/triage_view.py`: bỏ heuristic hard-code (`"omron"`, `"automation"`, `"partner"`, `"corp"`, `"vendor"`) ở cả `_stage_create_new_rule` (dòng 716) và dialog tạo rule (dòng 872-873), luôn mặc định `"email"`.
  - `tests/test_phase1_rules.py`: thêm test cho `split_rule_recipients` (0, 1, 40, 41, 81 email, domain dài, `max_recipients <= 0`), `WindowsOutlookClient(namespace=FakeNamespace(...))` + `SyncEngine` (chỉ có domain, rule rỗng, rule có cả email+domain+keyword, xóa hết email/domain/keyword cũ), và `TriageView` mặc định `"email"`.
- **Lệch plan & lý do:**
  - `split_rule_recipients` khi `emails` và `domains` đều rỗng trả về `[]` thay vì `[(rule_name, [], [])]`, giúp đồng bộ với quy tắc "chỉ tạo loại nào có dữ liệu" và tránh phát sinh sub-rule rỗng.
  - Ngoài dòng 716 ở `gui/triage_view.py`, bỏ thêm heuristic trùng lặp ở dòng 872-873 trong dialog tạo rule của cùng file để đảm bảo mặc định luôn là `"email"` ở mọi luồng tạo rule trên Triage.
  - Cập nhật thêm `MockOutlookClient.save_native_rules` để nhất quán chốt chặn an toàn và lưu đủ `domains`/`subject_keywords`.

### Tiền Phase 2 — Tolerance cho gán mảng rỗng (`4aef27a`)
- **Đã làm:**
  - `core/outlook_client.py` (`WindowsOutlookClient.save_native_rules`): giữ bắt buộc `Enabled = False` cho condition rỗng, bọc `sender_cond.Address = []` và `subj_cond.Text = []` trong `try/except` riêng để không làm hỏng cả lần sync nếu Outlook COM từ chối gán mảng rỗng.
  - `tests/test_phase1_rules.py`: thêm test `test_empty_array_assignment_error_does_not_fail_sync` (`26 passed`).

### Phase 2 — Sync quản lý vòng đời rule
- **Đã làm:**
  - `core/models.py`: thêm `MANAGED_PREFIX = "[Companion] "` và helper `extract_base_rule_name`.
  - `core/sync_engine.py`:
    - `SyncEngine.push_to_outlook(remove_legacy: bool = False)`: gắn `MANAGED_PREFIX` cho mọi rule compile; vẫn compile rule YAML có `enabled=False`; sắp xếp thứ tự sub-rule theo `email -> domain -> keyword -> _Unclassified` cuối cùng; truyền `legacy_base_names` để dọn/migration.
    - Thêm `SyncEngine.find_legacy_rules()` để liệt kê rule cũ không prefix trùng tên rule YAML (hoặc `(Part N)`).
    - Cập nhật `match_message` và docstring theo đúng thứ tự `ExecutionOrder` (gồm check `rule.enabled` cho `_Unclassified`).
  - `core/outlook_client.py` (`WindowsOutlookClient.save_native_rules` & `MockOutlookClient.save_native_rules`):
    - Reconcile rule managed: tạo/cập nhật rule trong `rules_data`, gom tên các rule `[Companion] ...` thừa trước rồi mới gọi `rules_col.Remove`, không đụng vào rule không prefix của người dùng, trả về đủ số lượng `Created / Updated / Disabled / Removed`.
    - Set `Actions.Stop.Enabled = True` và `ExecutionOrder` tăng dần trên mọi rule managed.
    - Migration rule không prefix trùng tên rule YAML (hoặc hậu tố split): giữ nguyên khi `remove_legacy=False` (chỉ xóa khi `remove_legacy=True`); riêng rule không prefix **không có condition nào bật** (`From`/`SenderAddress`/`Subject` đều `Enabled = False`) nhưng có `MoveToFolder` bật thì **tắt ngay (`Enabled = False`)** trong lần sync và nêu tên trong message.
  - `core/conflict_detector.py`: dùng `extract_base_rule_name` để khớp tên YAML với tên Outlook sau khi bỏ `MANAGED_PREFIX` và hậu tố `(Part N)`/`(Domains)`/`(Keywords)`.
  - `gui/main_window.py` (`_sync_to_outlook`): kiểm tra `find_legacy_rules()`, hỏi người dùng một lần kèm danh sách tên, rồi gọi `push_to_outlook(remove_legacy=True)` nếu đồng ý.
  - `tests/test_phase1_rules.py`: cập nhật tên kỳ vọng có `MANAGED_PREFIX` cho 2 test gọi `SyncEngine.push_to_outlook()`.
  - `tests/test_phase2_lifecycle.py`: thêm 8 test kiểm tra rút gọn part, xóa/đổi tên rule, rule `enabled=False`, rule người dùng tự tạo không bị đụng, `ExecutionOrder` + `Stop.Enabled`, tắt ngay rule legacy không condition + xóa qua `remove_legacy`, `ConflictDetector`, và prompt GUI `MainWindow._sync_to_outlook`.
- **Lệch plan & lý do:**
  - `extract_base_rule_name` xử lý đồng nhất cả `(Part N)`, `(Domains)`, `(Keywords)` khi nhận diện tên rule legacy và trong `ConflictDetector`, tránh bỏ sót sub-rule tách theo domain/keyword hoặc báo trùng lặp `SENDER_OVERLAP` ở `ConflictDetector`.
  - Ở `gui/main_window.py`, kiểm tra danh sách rule legacy qua `find_legacy_rules()` trước khi gọi `push_to_outlook(remove_legacy=...)` để chỉ chạy sync Outlook một lần thay vì hai lần (vẫn hỏi người dùng đúng một lần kèm danh sách tên).

### Phase 2 — Review fixes
- **Đã làm:**
  - `core/outlook_client.py` (`WindowsOutlookClient._is_conditionless_move_rule`): chuyển sang duyệt toàn bộ condition qua `rule.Conditions.Count` và `rule.Conditions.Item(i)` (1-based); chỉ coi là không có condition khi không có condition nào `Enabled`, và trả `False` (không tắt rule) nếu gặp exception khi đọc `Conditions`.
  - `core/outlook_client.py` (`WindowsOutlookClient.save_native_rules`): tính `ExecutionOrder = (số rule không prefix còn lại sau khi xóa) + thứ tự trong compiled list (bắt đầu từ 1)` để đặt rule managed sau các rule không prefix của người dùng mà không đụng tới `ExecutionOrder` của rule người dùng.
  - `core/sync_engine.py` (`match_message`): cập nhật docstring ghi rõ dry-run chỉ mô phỏng rule managed (`[Companion]`), không tính rule không prefix của người dùng.
  - `tests/fakes.py`: thêm `FakeSentToCondition`, `FakeBodyCondition` và hỗ trợ `Count` / `Item(i)` (1-based) cho `FakeConditions`.
  - `tests/test_phase2_lifecycle.py`: cập nhật test `ExecutionOrder` và thêm test cho rule người dùng đứng trước (`ExecutionOrder`), cũng như rule legacy trùng tên YAML có `SentTo` bật hoặc `Conditions` lỗi không bị tắt.
- **Lệch plan & lý do:** Không có.

### Phase 3 — Rollover an toàn
- **Đã làm:**
  - `core/outlook_client.py`:
    - Thay `_get_store_by_path_or_name` bằng `_find_store(identifier)` dùng helper `_match_store_exact`: so khớp chính xác `FilePath` đã `os.path.normcase(os.path.normpath(...))`, sau đó so khớp chính xác `DisplayName` (không phân biệt hoa thường); chỉ trả `DefaultStore` khi `identifier` rỗng, không khớp trả `None` (không fallback về `DefaultStore`).
    - Thêm `store_exists(identifier) -> bool` trên `BaseOutlookClient`, `WindowsOutlookClient`, và `MockOutlookClient` (trả `False` nếu rỗng hoặc không tìm thấy).
    - Cập nhật `save_native_rules` và `move_message` dùng `_find_store`: `save_native_rules` kiểm tra store trước khi sửa/xóa bất kỳ rule nào hoặc tạo folder; store không tồn tại thì trả lỗi rõ ràng / `False`, không ghi vào mailbox chính. Cập nhật tương ứng `MockOutlookClient.save_native_rules` và `MockOutlookClient.move_message`.
    - Xóa `rollover_rules` khỏi `BaseOutlookClient`, `WindowsOutlookClient`, và `MockOutlookClient` sau khi grep toàn repo xác nhận không còn nơi nào gọi.
  - `core/sync_engine.py` (`SyncEngine.perform_rollover`): kiểm tra store mới tồn tại bằng `store_exists(new_store_path)` trước; đổi `name`/`file_path` của `active_archive` trong bộ nhớ, gọi `push_to_outlook()`, chỉ `yaml_mgr.save()` khi thành công; nếu thất bại hoặc raise lỗi thì khôi phục `name`/`file_path` cũ trong bộ nhớ, không save và trả lỗi.
  - `tests/test_phase3_rollover.py`: thêm 6 test (dùng `WindowsOutlookClient(namespace=FakeNamespace(...))` và `MockOutlookClient`) cho so khớp chính xác `"Archive 2025"` vs `"Archive 2025 Old"`, rollover đường dẫn sai, rollback khi Outlook save lỗi, rollover giữ nguyên cây thư mục `Team\Part\Unit` và không đụng rule không prefix, `save_native_rules` với store không tồn tại, và `move_message` với store không tồn tại.
- **Lệch plan & lý do:**
  - Thực hiện rollover theo phương án khuyến nghị (cập nhật `active_archive` tạm trong bộ nhớ rồi gọi `push_to_outlook()`, chỉ `save()` khi thành công) và xóa `rollover_rules` khỏi cả 3 lớp client thay vì giữ lại phương thức không còn sử dụng (theo chỉ dẫn của user).

### Phase 3 — Review fixes
- **Đã làm:**
  - `core/outlook_client.py` (`MockOutlookClient`): bỏ kiểm tra store chặt trong `save_native_rules` và `move_message` để Mock mode vẫn chạy được với `config/rules.yaml` thật (`C:\Outlook_Data\...`), giữ nguyên `MockOutlookClient.store_exists` chặt và toàn bộ kiểm tra chặt của `WindowsOutlookClient`.
  - `tests/test_phase3_rollover.py`: thêm test dùng `MockOutlookClient` với bản copy `config/rules.yaml` trong thư mục tạm -> `push_to_outlook()` và `move_message()` đều trả `True`.
- **Lệch plan & lý do:** Không có.
