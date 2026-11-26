# Kế hoạch đơn giản hóa giao diện — outlook-rule-manager

Tài liệu này là chỉ dẫn cho agent thực hiện (Gemini). Sau mỗi phase, agent **dừng lại** để Claude review (đọc diff + chụp màn hình app) trước khi làm phase tiếp theo.

## Mục tiêu

Giao diện hiện có quá nhiều khái niệm và nhiều cách làm cùng một việc. Đích đến:

- **2 tab**: `Inbox` (phân loại mail hằng ngày) và `Rules` (sửa rule/group).
- **1 luồng phân loại**: chọn mail → `Add to Rule…` hoặc `New Rule…` → hàng chờ → `Apply`.
- **1 chế độ nhập** trong inspector: ô text, mỗi dòng một giá trị.
- Rollover thành **hộp thoại**; Dry-Run thành **một cột** trong danh sách mail.
- **Một style**: ttk cho mọi widget tương tác; khung trên gọn hơn để nội dung có chỗ.

**Không thay đổi**: định dạng `rules.yaml`, toàn bộ logic trong `core/` (sync, reconcile, rollover, import, ID, backup). Address groups và unclassified pool **được giữ nguyên** (chỉ đơn giản hóa cách hiển thị).

## Quy tắc chung

- Tạo branch `fix/outlook-rule-manager-simplify` **từ `fix/outlook-rule-manager-ui`**. **Không** push, **không** merge.
- **Không** `git add` / commit `config/rules.yaml` (thay đổi riêng của người dùng). Chỉ `git add` từng file đã sửa; không dùng `git add .` / `git add -A`.
- Mỗi phase = 1 commit: `refactor(outlook-rule-manager): simplify <N> - <tên>`.
- Giữ Tkinter/ttk, không thêm thư viện. Văn bản giao diện giữ **tiếng Anh**.
- **Không sửa file trong `core/`** trừ khi plan nêu rõ. Test trong `tests/test_phase*.py` (logic) **không được sửa hay xóa**.
- Test GUI cũ (`tests/test_rule_manager.py`, `tests/test_ui_phase*.py`) tham chiếu widget bị bỏ thì được cập nhật cho khớp giao diện mới, **giữ nguyên ý nghĩa** của test (vd: test kéo-thả trong Triage → chuyển thành test luồng `Add to Rule…`). Không xóa test chỉ để cho qua; ghi rõ trong nhật ký test nào đã đổi và vì sao.
- Không kết nối Outlook thật trong test. Chạy `python -m pytest -q tests` trong `outlook-rule-manager/`; tất cả phải pass.
- Cuối mỗi phase: ghi *Nhật ký thực hiện* cuối file này, báo commit hash + danh sách file đổi + output pytest.

---

## Phase S1 — Một luồng phân loại trong tab Inbox

File chính: [gui/triage_view.py](gui/triage_view.py).

1. **Bỏ cây rule ở panel trái** (`tree_rules`, drop zone "Drop an email here…", nút Expand/Collapse Tree) và **bỏ kéo-thả** mail (`_on_drag_start/_motion/_release` và các bind `<ButtonPress-1>`/`<B1-Motion>`/`<ButtonRelease-1>` trên `tree_inbox`). Bố cục còn 2 cột: **danh sách mail (trái, rộng)** | **khung đọc mail (phải)**.
2. **Hành động trên mail đang chọn** (thanh nút trong khung đọc + menu chuột phải trên danh sách, cùng một tập lệnh):
   - `Add to Rule…` — mở hộp thoại chọn rule: ô tìm kiếm lọc theo tên/đường dẫn folder, danh sách rule (tên + folder), lựa chọn phạm vi `This sender` / `Whole domain (@x.com)` (mặc định `This sender`). OK → stage action `add_to_rule` (dùng logic stage hiện có).
   - `New Rule…` — dùng hộp thoại tạo rule hiện có (`_open_create_hierarchical_rule_dialog`).
   - `Move Now` — giữ chức năng `_move_selected_now`, nhưng chọn rule qua cùng hộp thoại `Add to Rule…` thay vì yêu cầu chọn trên cây (vì cây đã bỏ).
   - Bỏ `Assign to Rule…` menubutton (trùng với `Add to Rule…`).
3. **Hàng chờ (staged)**: hiển thị bằng thanh mỏng ở đáy tab Inbox: `N pending change(s) — [Review] [Clear] [Apply]`, ẩn khi N = 0.
   - `Review` mở hộp thoại liệt kê các action (mail, rule, phạm vi) và cho xóa từng dòng.
   - `Apply` giữ nguyên logic `_apply_all_staged`.
   - Mail đã stage hiển thị trạng thái trong cột Status của danh sách (đã có).
4. **Cột "Will go to"** (thay tab Dry-Run): thêm cột vào `tree_inbox`, giá trị = folder đích theo `SyncEngine.match_message` (hoặc `Inbox (no rule)`); tooltip hoặc cột ẩn không bắt buộc. Mail đã stage hiển thị folder đích của action đã stage, có dấu `*`. Bộ lọc `All / Needs Rule / Staged` giữ nguyên.
5. Test: chọn mail → `Add to Rule…` (patch dialog trả rule + phạm vi) → 1 action staged; thanh pending hiện `1 pending change`; `Apply` → YAML có địa chỉ; cột "Will go to" của mail khớp rule đúng như `match_message`.

## Phase S2 — Gọn tab và inspector

1. **Bỏ tab Dry-Run**: gỡ `DryRunView` khỏi `MainWindow` (và mọi tham chiếu `tab_dryrun`). Xóa `gui/dryrun_view.py` nếu không còn ai dùng (grep để chắc chắn).
2. **Rollover thành hộp thoại**: bỏ tab `PST Rollover`; thêm nút `Yearly Rollover…` trên header (cạnh `Check Rule Conflicts`). Nút mở `Toplevel` modal chứa `RolloverView` hiện có (không viết lại logic). Đóng hộp thoại sau rollover thành công; footer + trạng thái sync cập nhật như hiện tại. `_retry_outlook_connection` cập nhật client cho hộp thoại nếu đang mở (hoặc tạo hộp thoại mới mỗi lần mở với client hiện tại — khuyến nghị cách này).
3. **Inspector rule: một chế độ nhập**. Bỏ nút `Visual Chips` / `Bulk Text Editor` và các listbox chip. Mỗi trường là một `tk.Text` (mỗi dòng một giá trị):
   - `Emails`, `Domains`, `Subject Keywords` — kèm nhãn số lượng (vd `Emails (12)`), cập nhật khi gõ.
   - Giữ `Linked Groups`, `Import CSV/Excel…` (ghi thêm vào ô Emails), `Test Match`, dòng quota, dirty tracking (so sánh nội dung các ô với dữ liệu đã lưu — cập nhật `_get_current_rule_form_values`).
   - Chiều cao ô: Emails ≥ 6 dòng, Domains và Keywords ≥ 3 dòng; ở 1120x720 phải thấy được ít nhất 4 dòng của ô Emails mà không cần cuộn vùng ngoài (đo bằng test nếu làm được, nếu không thì ghi chú để Claude kiểm bằng ảnh chụp).
4. **Gộp toolbar tab Rules**: một hàng gồm `New ▾` (menu: Rule, Folder, Subfolder, Group) · `Expand` · `Collapse` · ô `Filter:`. Bỏ các nút riêng lẻ tương ứng.
5. Test: cập nhật test inspector theo ô text; dirty → `Save Changes ●`; `MainWindow` chỉ còn 2 tab; nút `Yearly Rollover…` mở hộp thoại có `RolloverView` dùng đúng client hiện tại.

## Phase S3 — Style thống nhất & khung trên gọn

1. **Một style**: thay các `tk.Button` tự vẽ (filter `All/Needs Rule/Staged`, các nút màu trong inspector/triage) bằng ttk (`ttk.Radiobutton` style `Toolbutton` cho bộ lọc; `ttk.Button` cho phần còn lại). Định nghĩa tập style trong **một chỗ** (`MainWindow._apply_style`): `Accent.TButton`, `SyncPending.TButton`, `DirtySave.TButton`, `Danger.TButton` (cho Delete). Không thêm theme mới.
2. **Màu nền**: dùng nền theme ttk thống nhất cho các panel; bỏ việc trộn card trắng kiểu web với nền xám. Giữ màu nhấn cho: banner Mock mode, trạng thái sync, footer status, cảnh báo quota.
3. **Khung trên gọn**:
   - Banner Mock mode: **1 dòng**, padding nhỏ (pady ≤ 3), chữ 9pt; nút `Retry` cùng dòng.
   - Header: tiêu đề + engine trên 1 dòng; các nút bên phải giữ nguyên.
   - Mục tiêu: ở 1120x720 trong Mock mode, tổng chiều cao header + banner + thanh tab + footer **≤ 130 px** (đo bằng `winfo_height()` trong test).
4. **Tên tab**: `Inbox`, `Rules`. Bỏ khoảng trắng đệm trong text tab.
5. Bỏ các dòng mô tả dài không cần thiết (vd mô tả đầu RolloverView "Scan all Outlook data files… account-tagged filenames…") — rút còn 1 câu.
6. Test: đo chiều cao khung trên; không còn `tk.Button` trong `gui/` trừ khi có lý do ghi trong nhật ký (grep trong test hoặc kiểm tra thủ công).

---

## Ngoài phạm vi (không làm)

- Bỏ address groups hoặc unclassified pool (thay đổi mô hình dữ liệu — cần quyết định riêng).
- Sửa logic trong `core/`, định dạng `rules.yaml`.
- Đổi framework GUI, dark mode, dịch giao diện.

## Checkpoint review

Sau mỗi phase, agent báo: commit hash, danh sách file đổi, output `pytest -q`, test GUI nào đã cập nhật và vì sao, các điểm lệch plan. Claude sẽ review diff và chụp lại màn hình (Mock mode, 1120x720).

---

## Nhật ký thực hiện

<!-- Agent ghi lại ở đây sau mỗi phase -->

### Phase S1 (2026-11-26)
- **Tái cấu trúc tab Inbox (`gui/triage_view.py`):**
  - Bỏ panel cây rule bên trái (`tree_rules`, `drop_new_zone`, `refresh_rules_tree`, nút `Expand Tree` / `Collapse Tree`) và bỏ toàn bộ cơ chế kéo-thả mail (`_on_drag_start`/`_motion`/`_release` và các binding `<ButtonPress-1>`/`<B1-Motion>`/`<ButtonRelease-1>` trên `tree_inbox`). Bố cục còn 2 pane: danh sách mail bên trái (`frame_left`, weight=6) và khung đọc mail + hành động bên phải (`frame_right`, weight=4).
  - Bỏ nút `Assign to Rule...` menubutton trùng lặp (`mb_assign_rule`/`_update_assign_menu`). Thanh hành động ở khung đọc và menu chuột phải `menu_inbox` cùng có một tập lệnh thống nhất: `Add to Rule...`, `New Rule...`, `Move Now`.
  - Tạo hộp thoại chọn rule (`_build_rule_picker_dialog` / `_prompt_rule_selection`) có ô lọc theo tên rule hoặc đường dẫn folder, danh sách rule, và lựa chọn phạm vi `This sender` (mặc định) / `Whole domain (@x.com)` khi chạy `Add to Rule...`. Hàm `_stage_add_to_existing_rule` nhận thêm `match_mode="email"` (mặc định giữ tương thích ngược) và `_move_selected_now` tái sử dụng cùng hộp thoại chọn rule với `allow_scope=False`.
  - Thay dock dưới đáy bằng thanh mỏng `pending_bar`: `N pending change(s) — [Review] [Clear] [Apply]`, tự động ẩn (`pack_forget`) khi `N = 0`. Nút `Review` mở `_build_review_staged_dialog` / `_open_review_staged_dialog` hiển thị email, hành động, rule, phạm vi, folder đích và cho phép xóa từng dòng.
  - Bổ sung cột `WillGoTo` (`Will go to`) vào `tree_inbox`: lấy `target_folder` từ `SyncEngine.match_message` (hoặc `Inbox (no rule)`), và hiển thị `* <target_folder>` cho email đã stage. Giữ nguyên `_stage_create_new_rule`, `_apply_all_staged` và các bộ lọc `All / Needs Rule / Staged / Search:`.
- **Test GUI đã cập nhật & bổ sung:**
  - `tests/test_ui_phase1.py` (`test_simulation_prefix_in_dialogs`): cập nhật bước `_move_selected_now` từ chọn node trên `tree_rules` (đã bỏ ở S1) sang patch `_prompt_rule_selection` trả về `rule_executive`, giữ nguyên mục đích kiểm tra tiền tố `[SIMULATION]` khi Move Now.
  - `tests/test_ui_phase3.py`: (1) `test_triage_layout_header_conflicts_and_footer_colors` cập nhật kiểm tra `tab_triage` từ 3 pane + `tree_rules`/`drop_new_zone`/`mb_assign_rule` sang 2 pane + thanh nút `Add to Rule...` / `New Rule...` / `Move Now` và kiểm tra nhãn `Search:` nằm trong `frame_left`; (2) `test_tree_labels_unclassified_count_tip_bar_and_enabled_checkbox` bỏ kiểm tra trên `tab_triage.tree_rules` đã gỡ bỏ, giữ nguyên toàn bộ kiểm tra cây trên `tab_rules.tree`.
  - Thêm `tests/test_ui_simplify1.py`: kiểm tra bố cục 2 pane, xóa bỏ drag-and-drop & widget cũ, cột `Will go to` (khớp rule / `Inbox (no rule)` / `* <staged folder>`), thanh `pending_bar` ẩn/hiện & số ít/số nhiều, lọc trong hộp thoại `Add to Rule...` + phạm vi `This sender` / `Whole domain`, hộp thoại `Review` (xóa từng dòng), `Clear`, `Apply` ghi vào YAML, và `Move Now`.
- **Kiểm thử & sai khác:** Không sửa file trong `core/` hay `tests/test_phase*.py`. Chạy `python -m pytest -q tests` → `87 passed in 10.09s`. Không có sai khác ngoài kế hoạch Phase S1.
