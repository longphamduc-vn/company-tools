# Kế hoạch sửa lỗi Sync — "Target store not found"

Tài liệu này là chỉ dẫn cho agent thực hiện (Gemini). Sau mỗi phase, agent **dừng lại** để Claude review trước khi làm phase tiếp theo.

## Lỗi người dùng gặp

```
Sync Failed
Target store not found: D:\Outlook_Data\longp_Archive_2025.pst
Warning - skipped rules with no conditions: [Unclassified]
```

## Nguyên nhân (đã kiểm tra trong code)

1. `config/rules.yaml` có `stores.active_archive.file_path = D:\Outlook_Data\longp_Archive_2025.pst`, nhưng PST đó **không đang mở trong Outlook** (chưa mount, hoặc file đã bị đổi tên/xóa).
   - [core/outlook_client.py:435-437](core/outlook_client.py#L435-L437) `save_native_rules` gọi `_find_store(target_store_path)` → `None` → trả lỗi và **hủy toàn bộ sync**.
   - Người dùng chỉ biết lỗi **sau khi** đã bấm xác nhận Sync ([gui/main_window.py:543-573](gui/main_window.py#L543-L573)). Không có bước kiểm tra trước, và thông báo lỗi không nói cách sửa.
   - File export để chia sẻ (`export_config`) xóa `file_path` → `''`. Đó là hành vi đúng; `import_config` không động tới `stores`, nên import **không phải** nguyên nhân. Không sửa phần này.
2. Cảnh báo `[Unclassified]` là cảnh báo nhiễu: khi `unclassified: []` thì rule `[Unclassified]` không có điều kiện, và [core/sync_engine.py:164-166](core/sync_engine.py#L164-L166) coi đó là "skipped rule". Đây là trạng thái bình thường, không nên báo.
3. Trong lúc lỗi, các cảnh báo vẫn được nối vào message lỗi ([core/sync_engine.py:198-201](core/sync_engine.py#L198-L201)), khiến người dùng tưởng có hai lỗi.

## Quy tắc chung

- Làm trên branch `fix/sync-store-not-found` (tạo từ `main`). **Không** push, **không** merge.
- Mỗi phase = 1 commit riêng, message dạng `fix(outlook-rule-manager): <phase>`.
- Chỉ sửa trong `outlook-rule-manager/`. Không refactor, đổi tên hay format lại code ngoài phạm vi.
- **Không** đổi schema `rules.yaml`. **Không** sửa `config/rules.yaml` của người dùng bằng tay.
- **Test không được kết nối Outlook thật**: dùng `MockOutlookClient` hoặc `tests/fakes.py` (`WindowsOutlookClient(namespace=FakeNamespace(...))`).
- Chạy test: `python -m pytest -q tests` từ thư mục `outlook-rule-manager/`. Cuối mỗi phase toàn bộ test phải pass.
- Ghi vào mục *Nhật ký thực hiện* cuối file này: đã làm gì, bỏ qua gì và lý do.

---

## Phase 1 — Bỏ cảnh báo nhiễu của `[Unclassified]`

File: [core/sync_engine.py](core/sync_engine.py) `push_to_outlook`.

1. Trong vòng lặp, khi `skip_reason == "no_conditions"` **và** `self._is_unclassified_rule(rule)` → `continue` mà **không** thêm vào `skipped_empty_rules`.
2. Chỉ nối các dòng `Warning - ...` vào `msg` khi `success` là True. Khi lỗi, chỉ trả message lỗi gốc.
3. `save_native_rules` (cả `WindowsOutlookClient` và `MockOutlookClient`) không cần sửa: rule unclassified rỗng sẽ không còn được gửi xuống.

**Test cần thêm** (`tests/test_sync_store.py`, file mới):
- `unclassified` rỗng và các rule khác hợp lệ → sync thành công, message **không** chứa `[Unclassified]`.
- Một rule thường (không phải unclassified) không có sender → vẫn có cảnh báo `skipped rules with no conditions: <tên>`.
- Store không tìm thấy → message lỗi **không** chứa dòng `Warning -`.

---

## Phase 2 — Thông báo lỗi rõ ràng và có hướng sửa

Files: [core/outlook_client.py](core/outlook_client.py), [core/sync_engine.py](core/sync_engine.py).

1. Thêm vào `BaseOutlookClient` và cài cho cả hai client:
   ```python
   def diagnose_store(self, identifier: str) -> Dict[str, Any]:
       """{'status': 'ok' | 'default' | 'not_open' | 'missing_file', 'path': str, 'mounted': [{'name','file_path'}]}"""
   ```
   - `default`: identifier rỗng (dùng mailbox mặc định).
   - `ok`: `_find_store` tìm thấy store.
   - `not_open`: không tìm thấy store, nhưng `os.path.isfile(path)` là True.
   - `missing_file`: không tìm thấy store và file cũng không có trên đĩa.
   - `mounted`: danh sách store đang mở, lấy từ `get_stores()`, để GUI gợi ý.
   - `MockOutlookClient`: dùng `self._stores` và `os.path.isfile`. Test có thể monkeypatch `os.path.isfile`.
2. Thêm `SyncEngine.check_active_store() -> Tuple[bool, str]`. Hàm trả `(True, "")` khi status là `ok` hoặc `default`. Nếu không, hàm trả `(False, <message tiếng Anh>)` theo đúng giọng văn các message hiện có:
   - `not_open`: `"The active archive PST exists but is not open in Outlook:\n<path>\n\nOpen it in Outlook (File > Open & Export > Open Outlook Data File), or use 'Open PST now'."`
   - `missing_file`: `"The active archive PST was not found on disk:\n<path>\n\nUse 'Yearly Rollover...' to pick an open store or create a new PST."` Liệt kê thêm tối đa 5 store đang mở (`name — file_path`).
3. `push_to_outlook` gọi `check_active_store()` **trước** khi compile. Nếu lỗi thì return ngay message đó, không gọi `save_native_rules`.
4. Giữ nguyên check trong `save_native_rules` làm lớp phòng thủ, chỉ đổi text thành `"Target store not found in Outlook: <path>"` để thống nhất với `perform_rollover`.

**Test cần thêm:**
- `diagnose_store` cho cả 4 trạng thái (Mock + Fake COM).
- `push_to_outlook` với PST không mở → `success=False`, message chứa `"not open in Outlook"`, và `save_native_rules` **không** được gọi (spy/monkeypatch).
- `file_path=''` → sync vào DefaultStore như cũ (không regression).

---

## Phase 3 — Mở PST ngay từ app + kiểm tra trước khi Sync

Files: [core/outlook_client.py](core/outlook_client.py), [gui/main_window.py](gui/main_window.py).

1. Thêm `open_pst(file_path) -> Tuple[bool, str]` vào `BaseOutlookClient`:
   - Windows: nếu đã mở → `(True, path)`. Nếu file không tồn tại → `(False, msg)`. Còn lại gọi `self.namespace.AddStore(path)` (**không** dùng `AddStoreEx`, vì hàm đó có thể tạo file mới), rồi `_find_store(path)` để xác nhận.
   - Mock: thêm store vào `self._stores` giống `create_pst`, nhưng yêu cầu file đã tồn tại.
   - Bổ sung `AddStore` vào `FakeNamespace` trong [tests/fakes.py](tests/fakes.py) nếu chưa có.
2. `_sync_to_outlook` trong [gui/main_window.py:543](gui/main_window.py#L543): gọi `self.sync_engine.check_active_store()` **trước** hộp thoại "Proceed?".
   - `not_open`: `askyesno("Archive PST Not Open", msg + "\n\nOpen it now?")`. Yes → `open_pst`. Mở thành công thì gọi `_refresh_footer()` rồi tiếp tục luồng sync, thất bại thì `showerror` và dừng.
   - `missing_file`: `askyesno(..., "Open Yearly Rollover to choose another store?")`. Yes → `_open_rollover_dialog()`, sau đó dừng (không tự sync).
3. Không đổi hành vi của `conflict_dialog.py` và `triage_view.py`. Chúng vẫn nhận message lỗi rõ ràng từ Phase 2.

**Test cần thêm:**
- `open_pst` với Fake COM: file có → store xuất hiện. File không có → lỗi, `AddStore` không được gọi. Đã mở → không gọi lại.
- GUI (theo kiểu các test `test_ui_*` hiện có, monkeypatch `messagebox`): store `not_open` + Yes → `open_pst` được gọi rồi sync chạy. No → không sync.

---

## Tiêu chí hoàn thành chung

- Với cấu hình như của người dùng (PST có trên đĩa nhưng chưa mở): app hỏi "Open it now?". Chọn Yes thì sync chạy bình thường.
- Không còn cảnh báo `[Unclassified]` khi pool rỗng.
- Toàn bộ test cũ và mới pass.
- Cập nhật mục xử lý lỗi trong [HUONG_DAN.md](HUONG_DAN.md) (tiếng Việt, 3–5 dòng): lỗi "PST not open/not found" và cách xử lý.

---

## Nhật ký thực hiện

Claude làm cả 3 phase trong một commit, theo yêu cầu của người dùng.

- **Phase 1**: `push_to_outlook` không còn báo rule unclassified rỗng. Khi sync lỗi, message chỉ còn lỗi gốc, không kèm cảnh báo. Test cũ `test_phase1_rules.py::test_empty_rule_is_not_created_and_warns_in_message` đang khẳng định hành vi cũ, nên đã được sửa: rule thường rỗng vẫn được cảnh báo, `[Unclassified]` thì không.
- **Phase 2**: thêm `diagnose_store` (Windows + Mock, dùng chung helper `_diagnose_store`) và `SyncEngine.active_store_status()` / `check_active_store()`.
  - Khác plan: ở chế độ giả lập (`is_simulated()`), `check_active_store` luôn trả `(True, "")`. Lý do: `MockOutlookClient.save_native_rules` vốn không kiểm tra store, và fixture trỏ tới `C:\Outlook_Data\...` không có thật, nên nếu kiểm tra thì mọi test sync giả lập sẽ hỏng.
  - Message `not_open` kết thúc bằng "then sync again". GUI tự thêm câu "Open it now?", nên không nhắc tới nút "Open PST now" vốn không tồn tại.
- **Phase 3**: thêm `open_pst` (Windows dùng `Namespace.AddStore` và từ chối nếu file không tồn tại; Mock thêm vào danh sách store), `FakeNamespace.AddStore`, và `MainWindow._ensure_active_store_ready()` chạy trước hộp thoại xác nhận Sync. `conflict_dialog.py` và `triage_view.py` giữ nguyên.
- Test mới: [tests/test_sync_store.py](tests/test_sync_store.py) (15 test). Toàn bộ: 195 passed.
- Đã cập nhật [HUONG_DAN.md](HUONG_DAN.md) mục 6.
