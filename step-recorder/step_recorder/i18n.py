"""
Internationalization (i18n) module for Python Step Recorder.
Provides full bilingual support: Tiếng Việt (Vietnamese) and English.
"""

from typing import Dict, Any, Optional

TRANSLATIONS: Dict[str, Dict[str, str]] = {
    # === Main Toolbar ===
    "app_title": {
        "vi": "Python Step Recorder - Trình Ghi Lại Bước Thao Tác",
        "en": "Python Step Recorder - Problem Steps Recorder"
    },
    "status_ready": {
        "vi": "Sẵn sàng",
        "en": "Ready"
    },
    "status_recording": {
        "vi": "Đang ghi hình...",
        "en": "Recording..."
    },
    "status_paused": {
        "vi": "Đã tạm dừng",
        "en": "Paused"
    },
    "status_stopped": {
        "vi": "Đã dừng",
        "en": "Stopped"
    },
    "steps_count": {
        "vi": "Số bước: {count} / {max}",
        "en": "Steps: {count} / {max}"
    },
    "btn_start": {
        "vi": "⏺ Bắt đầu",
        "en": "⏺ Start"
    },
    "btn_pause": {
        "vi": "⏸ Tạm dừng",
        "en": "⏸ Pause"
    },
    "btn_resume": {
        "vi": "▶ Tiếp tục",
        "en": "▶ Resume"
    },
    "btn_comment": {
        "vi": "💬 Ghi chú",
        "en": "💬 Comment"
    },
    "btn_review": {
        "vi": "📝 Chỉnh sửa",
        "en": "📝 Review"
    },
    "btn_stop": {
        "vi": "⏹ Dừng lại",
        "en": "⏹ Stop"
    },
    "btn_settings": {
        "vi": "⚙ Cài đặt",
        "en": "⚙ Settings"
    },
    "btn_open": {
        "vi": "📂 Mở tệp",
        "en": "📂 Open"
    },
    "hotkey_bar_hint": {
        "vi": "Phím tắt: F7: Bắt đầu/Dừng | F8: Tạm dừng | F9: Ghi chú | F10: Phân đoạn | F11: Chỉnh sửa",
        "en": "Hotkeys: F7: Start/Stop | F8: Pause | F9: Note | F10: Section | F11: Review"
    },
    "pin_on_top": {
        "vi": "📌 Ghim trên",
        "en": "📌 On Top"
    },
    "pin_normal": {
        "vi": "📍 Thường",
        "en": "📍 Normal"
    },
    "settings_saved": {
        "vi": "Đã lưu cài đặt! ✓",
        "en": "Settings Saved! ✓"
    },
    "step_recorded_flash": {
        "vi": "Bước #{id} đã ghi! 📸",
        "en": "Step #{id} captured! 📸"
    },
    "no_steps_to_review": {
        "vi": "Chưa có bước nào được ghi lại để chỉnh sửa.",
        "en": "No steps have been recorded yet to review."
    },
    "no_steps_recorded": {
        "vi": "Không có bước nào được ghi lại.",
        "en": "No steps were recorded."
    },

    # === Step Review & Editor Window ===
    "editor_title": {
        "vi": "Step Recorder - Chỉnh Sửa & Quản Lý Bước (Step Review & Editor)",
        "en": "Step Recorder - Step Review & Editor"
    },
    "editor_header": {
        "vi": "📋 Chỉnh Sửa & Xóa Bước Ghi Hình",
        "en": "📋 Review, Edit & Manage Recorded Steps"
    },
    "total_steps": {
        "vi": "Tổng số: {count} bước",
        "en": "Total: {count} steps"
    },
    "step_list_title": {
        "vi": "Danh sách các bước:",
        "en": "Recorded Steps List:"
    },
    "btn_delete_step": {
        "vi": "🗑️ Xóa bước",
        "en": "🗑️ Delete Step"
    },
    "btn_delete_multi": {
        "vi": "🗑️ Xóa ({count})",
        "en": "🗑️ Delete ({count})"
    },
    "btn_undo_delete": {
        "vi": "↩ Hoàn tác xóa",
        "en": "↩ Undo Delete"
    },
    "btn_select_all": {
        "vi": "Chọn tất cả",
        "en": "Select All"
    },
    "btn_deselect_all": {
        "vi": "Bỏ chọn",
        "en": "Deselect"
    },
    "status_selected_count": {
        "vi": "Đã chọn: {selected} / {total} bước",
        "en": "Selected: {selected} / {total} steps"
    },
    "btn_move_up": {
        "vi": "⬆️ Lên",
        "en": "⬆️ Move Up"
    },
    "btn_move_down": {
        "vi": "⬇️ Xuống",
        "en": "⬇️ Move Down"
    },
    "step_detail_title": {
        "vi": "Bước #{id} - {action} ({time})",
        "en": "Step #{id} - {action} ({time})"
    },
    "desc_label": {
        "vi": "Mô tả hành động (Description):",
        "en": "Action Description:"
    },
    "comment_label": {
        "vi": "Ghi chú / Lưu ý lỗi (User Comment):",
        "en": "User Note / Observation Comment:"
    },
    "preview_label": {
        "vi": "Ảnh chụp màn hình (Kéo chuột trên ảnh để vẽ Focus/Highlight):",
        "en": "Screenshot (Drag mouse over image to adjust Focus/Highlight):"
    },
    "sec_group_title": {
        "vi": "📑 Phân Đoạn & Tiêu Đề Chương (SOP Section)",
        "en": "📑 Section & Chapter Header (SOP Section)"
    },
    "chk_section_header": {
        "vi": "Đặt bước này làm Mở Đầu Phần / Chương mới",
        "en": "Mark this step as New Section / Chapter Header"
    },
    "lbl_section_title": {
        "vi": "Tiêu đề phần / chương (Section Title):",
        "en": "Section / Chapter Title:"
    },
    "lbl_section_desc": {
        "vi": "Mục tiêu / Tóm tắt nội dung (Objective & Summary):",
        "en": "Objective & Section Summary:"
    },
    "placeholder_section_title": {
        "vi": "Ví dụ: Phần 1: Đăng nhập & Khởi tạo dữ liệu...",
        "en": "e.g. Chapter 1: Initial Login & Setup..."
    },
    "placeholder_section_desc": {
        "vi": "Ví dụ: Hướng dẫn người dùng đăng nhập tài khoản phân quyền quản trị...",
        "en": "e.g. Guide the administrator through the setup wizard..."
    },
    "chk_decision_point": {
        "vi": "🔀 Đặt bước này làm Điểm Rẽ Nhánh Điều Kiện (Yes / No Workflow)",
        "en": "🔀 Mark as Conditional Decision Point (Yes / No Workflow)"
    },
    "lbl_condition_question": {
        "vi": "Câu hỏi điều kiện kiểm tra (Condition Question):",
        "en": "Condition Question:"
    },
    "placeholder_condition_question": {
        "vi": "Ví dụ: Hệ thống có hiển thị thông báo lỗi / cảnh báo không?",
        "en": "e.g. Does the system display an error or confirmation prompt?"
    },
    "lbl_yes_branch": {
        "vi": "✅ Trường hợp ĐÚNG / CÓ (YES):",
        "en": "✅ If TRUE / YES:"
    },
    "placeholder_yes_branch": {
        "vi": "Ví dụ: Bấm 'Đồng ý' và tiếp tục sang bước tiếp theo...",
        "en": "e.g. Click 'Confirm' and proceed to next step..."
    },
    "lbl_no_branch": {
        "vi": "❌ Trường hợp SAI / KHÔNG (NO / Ngoại lệ):",
        "en": "❌ If FALSE / NO (Exception):"
    },
    "placeholder_no_branch": {
        "vi": "Ví dụ: Bấm 'Hủy bỏ', kiểm tra quyền truy cập hoặc làm theo Phụ lục B...",
        "en": "e.g. Click 'Cancel', check credentials or refer to Appendix B..."
    },
    "lbl_jump_step": {
        "vi": "Nhảy tới Bước:",
        "en": "Jump to Step:"
    },
    "decision_badge": {
        "vi": "🔀 Rẽ nhánh Y/N",
        "en": "🔀 Decision Y/N"
    },
    "decision_card_title": {
        "vi": "🔀 ĐIỂM RẼ NHÁNH QUY TRÌNH (WORKFLOW DECISION POINT)",
        "en": "🔀 WORKFLOW DECISION POINT (YES / NO BRANCH)"
    },
    "toc_title": {
        "vi": "Mục Lục Tài Liệu",
        "en": "Table of Contents"
    },
    "toc_overview": {
        "vi": "Tổng Quan Quy Trình",
        "en": "Overview & Summary"
    },
    "toc_steps_badge": {
        "vi": "{count} bước",
        "en": "{count} steps"
    },
    "section_tag": {
        "vi": "PHẦN",
        "en": "SECTION"
    },
    "btn_toggle_toc": {
        "vi": "📑 Mục Lục",
        "en": "📑 Contents"
    },
    "tool_highlight": {
        "vi": "🎯 Focus",
        "en": "🎯 Focus"
    },
    "tool_blur": {
        "vi": "💧 Làm Mờ",
        "en": "💧 Blur"
    },
    "tool_redact": {
        "vi": "⬛ Bôi Đen",
        "en": "⬛ Redact"
    },
    "tool_red_box": {
        "vi": "🔴 Khung Đỏ",
        "en": "🔴 Red Box"
    },
    "tool_crop": {
        "vi": "✂️ Cắt Ảnh",
        "en": "✂️ Crop"
    },
    "btn_undo": {
        "vi": "↺ Hoàn tác",
        "en": "↺ Undo"
    },
    "btn_reset_raw": {
        "vi": "🔄 Gốc",
        "en": "🔄 Reset"
    },
    "btn_open_session": {
        "vi": "📂 Mở tài liệu",
        "en": "📂 Open Doc"
    },
    "btn_insert_steps": {
        "vi": "➕ Chèn bước...",
        "en": "➕ Insert..."
    },
    "open_session_title": {
        "vi": "Chọn tệp session.json của tài liệu đã lưu",
        "en": "Select saved session.json file"
    },
    "open_confirm_title": {
        "vi": "Mở tài liệu mới",
        "en": "Open Saved Document"
    },
    "open_confirm_msg": {
        "vi": "Mở tài liệu mới sẽ thay thế phiên làm việc hiện tại. Bạn có chắc không?",
        "en": "Opening a new document will replace current working steps. Proceed?"
    },
    "insert_success": {
        "vi": "Đã chèn thành công {count} bước vào tài liệu!",
        "en": "Successfully inserted {count} steps into document!"
    },
    "insert_failed": {
        "vi": "Không thể chèn bước: {err}",
        "en": "Failed to insert steps: {err}"
    },
    "crop_confirm_title": {
        "vi": "Xác nhận cắt ảnh",
        "en": "Confirm Crop"
    },
    "crop_confirm_msg": {
        "vi": "Cắt ảnh bước này về khung đã chọn ({w}x{h} px)?",
        "en": "Crop this step screenshot to selected region ({w}x{h} px)?"
    },
    "drag_hint_highlight": {
        "vi": "Kéo chuột trên ảnh để vẽ Highlight Focus",
        "en": "Drag mouse over image to draw Focus Highlight"
    },
    "drag_hint_blur": {
        "vi": "Kéo chuột qua vùng dữ liệu nhạy cảm để Làm Mờ (Blur)",
        "en": "Drag mouse over sensitive area to Blur"
    },
    "drag_hint_redact": {
        "vi": "Kéo chuột qua vùng cần Bôi Đen bảo mật (Redact)",
        "en": "Drag mouse over area to Black out (Redact)"
    },
    "drag_hint_red_box": {
        "vi": "Kéo chuột để vẽ Khung Chú Ý Màu Đỏ",
        "en": "Drag mouse to draw Red Attention Box"
    },
    "drag_hint_crop": {
        "vi": "Kéo chuột chọn vùng muốn Cắt Xén Ảnh (Crop)",
        "en": "Drag mouse to select region to Crop"
    },
    "btn_reset_highlight": {
        "vi": "↺ Đặt lại Highlight",
        "en": "↺ Reset Highlight"
    },
    "btn_apply_step": {
        "vi": "✓ Cập nhật thay đổi cho bước này",
        "en": "✓ Apply Changes for This Step"
    },
    "step_updated_msg": {
        "vi": "Đã lưu thay đổi cho Bước #{id}!",
        "en": "Changes saved for Step #{id}!"
    },
    "confirm_delete_title": {
        "vi": "Xác nhận xóa bước",
        "en": "Confirm Step Deletion"
    },
    "confirm_delete_msg": {
        "vi": "Bạn có chắc muốn xóa Bước #{id} không?\nCác bước tiếp theo sẽ tự động được đánh số lại (nhấn Ctrl+Z để hoàn tác).",
        "en": "Are you sure you want to delete Step #{id}?\nRemaining steps will be automatically renumbered (press Ctrl+Z to undo)."
    },
    "confirm_delete_multi_msg": {
        "vi": "Bạn có chắc muốn xóa {count} bước đã chọn không?\nCác bước còn lại sẽ tự động được đánh số lại (nhấn Ctrl+Z để hoàn tác).",
        "en": "Are you sure you want to delete {count} selected steps?\nRemaining steps will be automatically renumbered (press Ctrl+Z to undo)."
    },
    "no_steps_left": {
        "vi": "Không còn bước nào.",
        "en": "No steps remaining."
    },
    "btn_export_report": {
        "vi": "💾 Lưu & Xuất Báo Cáo (Export Report)",
        "en": "💾 Save & Export Final Report"
    },
    "btn_close_editor": {
        "vi": "✕ Đóng",
        "en": "✕ Close"
    },
    "export_empty_warning": {
        "vi": "Không có bước nào để xuất báo cáo!",
        "en": "No steps available to export!"
    },
    "export_success_title": {
        "vi": "Xuất Báo Cáo Thành Công",
        "en": "Report Exported Successfully"
    },
    "export_success_msg": {
        "vi": "✅ Xuất báo cáo thành công!\n\nTổng số bước: {steps}\nThời gian ghi: {duration}\nThư mục lưu trữ: {folder}\n\nBạn có muốn mở thư mục chứa báo cáo không?",
        "en": "✅ Report exported successfully!\n\nTotal steps: {steps}\nDuration: {duration}\nOutput directory: {folder}\n\nWould you like to open the output folder?"
    },
    "no_screenshot_available": {
        "vi": "Không có ảnh chụp màn hình",
        "en": "No screenshot available"
    },
    "image_render_error": {
        "vi": "Lỗi hiển thị ảnh: {err}",
        "en": "Error displaying image: {err}"
    },

    # === Comment Dialog ===
    "comment_win_title": {
        "vi": "Thêm Ghi Chú & Highlight Vùng Lỗi",
        "en": "Add Note & Highlight Focus Area"
    },
    "comment_heading": {
        "vi": "💬 Thêm Ghi Chú / Mô Tả Lỗi (Comment)",
        "en": "💬 Add Observation Note / Comment"
    },
    "comment_subheading": {
        "vi": "Nhập mô tả vấn đề hoặc khoanh vùng khu vực cần Focus:",
        "en": "Enter problem description or select a screen area to highlight:"
    },
    "btn_launch_snipper": {
        "vi": "🎯 Khoanh vùng Focus / Highlight trên màn hình",
        "en": "🎯 Select Focus / Highlight area on screen"
    },
    "btn_snip_selected": {
        "vi": "✓ Đã khoanh vùng (Nhấn để chọn lại)",
        "en": "✓ Region Selected (Click to re-select)"
    },
    "region_fullscreen": {
        "vi": "Khu vực: Toàn màn hình",
        "en": "Region: Full Screen"
    },
    "region_custom": {
        "vi": "Đã chọn: ({x1}, {y1}) - {w}x{h} px",
        "en": "Selected: ({x1}, {y1}) - {w}x{h} px"
    },
    "btn_save_comment": {
        "vi": "✓ Lưu Bước Ghi Chú (Ctrl+Enter)",
        "en": "✓ Save Note Step (Ctrl+Enter)"
    },
    "btn_cancel": {
        "vi": "Hủy (Esc)",
        "en": "Cancel (Esc)"
    },
    "default_comment_text": {
        "vi": "Ghi chú người dùng / User flagged observation",
        "en": "User observation note"
    },
    "comment_chk_section": {
        "vi": "Đồng thời đặt làm Tiêu đề Phần / Chương mới (Section Header)",
        "en": "Also mark as New Section / Chapter Header"
    },
    "comment_lbl_section_title": {
        "vi": "Tên tiêu đề phần mới (tùy chọn):",
        "en": "New section title (optional):"
    },
    "snipper_overlay_instructions": {
        "vi": "🎯 Kéo chuột để chọn vùng Focus / Highlight (Nhấn Esc để hủy)",
        "en": "🎯 Drag mouse to select Focus / Highlight region (Press Esc to cancel)"
    },

    # === Settings Dialog ===
    "settings_win_title": {
        "vi": "Step Recorder - Cài Đặt (Settings)",
        "en": "Step Recorder - Settings"
    },
    "settings_heading": {
        "vi": "⚙️ Cài Đặt Ứng Dụng (Settings)",
        "en": "⚙️ Application Settings"
    },
    "sec_language": {
        "vi": "🌐 Ngôn Ngữ Giao Diện (Language)",
        "en": "🌐 Application Language"
    },
    "lang_vietnamese": {
        "vi": "Tiếng Việt (Vietnamese)",
        "en": "Tiếng Việt (Vietnamese)"
    },
    "lang_english": {
        "vi": "English (Tiếng Anh)",
        "en": "English"
    },
    "sec_output_dir": {
        "vi": "📁 Thư Mục Lưu Báo Cáo (Output Directory)",
        "en": "📁 Output Directory"
    },
    "btn_browse_folder": {
        "vi": "📂 Chọn Thư Mục...",
        "en": "📂 Browse Folder..."
    },
    "sec_click_indicator": {
        "vi": "🎨 Hiệu Ứng Con Trỏ Chuột (Click Indicator)",
        "en": "🎨 Click Indicator Style & Color"
    },
    "lbl_style": {
        "vi": "Kiểu hiển thị:",
        "en": "Indicator Style:"
    },
    "lbl_color": {
        "vi": "Màu sắc highlight:",
        "en": "Highlight Color:"
    },
    "btn_pick_color": {
        "vi": "Chọn Màu...",
        "en": "Choose Color..."
    },
    "lbl_radius": {
        "vi": "Bán kính vòng tròn (px):",
        "en": "Circle Radius (px):"
    },
    "sec_limits_delays": {
        "vi": "⏱️ Giới Hạn & Độ Trễ Ghi Hình (Limits & Delay)",
        "en": "⏱️ Capture Limits & Delay"
    },
    "lbl_max_steps": {
        "vi": "Số bước tối đa (Max steps):",
        "en": "Max Steps (steps):"
    },
    "lbl_delay_ms": {
        "vi": "Độ trễ chụp ảnh (Screenshot delay ms):",
        "en": "Screenshot Delay (ms):"
    },
    "sec_dual_capture": {
        "vi": "📸 Chế Độ Chụp Kép (Dual Capture: Chụp Ngay + Chụp Sau ms)",
        "en": "📸 Dual Capture Mode (Immediate Click + Result Capture after ms)"
    },
    "opt_dual_capture": {
        "vi": "Chụp ngay sau khi click và chụp sau ms (Chụp 2 lần cho mỗi cú nhấp chuột)",
        "en": "Capture immediately after click and capture after ms (Capture twice per click)"
    },
    "opt_smart_detect": {
        "vi": "🧠 Tự động nhận biết thông minh (Chỉ chụp lần 2 khi giao diện có biến đổi)",
        "en": "🧠 Smart Auto-Detection (Only capture 2nd shot if UI genuinely changes)"
    },
    "hint_smart_detect": {
        "vi": "• Tự động so sánh điểm ảnh & cửa sổ: Nếu màn hình không đổi (click text, click vùng trống), chỉ giữ 1 ảnh duy nhất để tránh rác tài liệu.",
        "en": "• Automatic visual diff: If screen did not change (e.g. clicking text, empty areas), keeps only 1 clean screenshot."
    },
    "hint_dual_capture_1": {
        "vi": "• Lần 1: Chụp ngay lập tức vị trí nhấp chuột và đối tượng thao tác.",
        "en": "• Shot 1: Immediate capture of the click target and cursor position."
    },
    "hint_dual_capture_2": {
        "vi": "• Lần 2: Chụp sau khoảng trễ ms để lưu kết quả giao diện thay đổi (menu, modal, chuyển trang).",
        "en": "• Shot 2: Capture after delay ms to capture the resulting UI state change (menus, modals, page transitions)."
    },
    "lbl_second_delay_ms": {
        "vi": "Thời gian trễ chụp lần 2 (ms):",
        "en": "Second capture delay (ms):"
    },
    "btn_preset_fast": {
        "vi": "⚡ 200ms (Nhanh)",
        "en": "⚡ 200ms (Fast)"
    },
    "btn_preset_std": {
        "vi": "🎯 500ms (Chuẩn)",
        "en": "🎯 500ms (Standard)"
    },
    "btn_preset_slow": {
        "vi": "⏳ 1000ms (Chậm)",
        "en": "⏳ 1000ms (Slow)"
    },
    "lbl_single_delay_ms": {
        "vi": "Độ trễ khi chụp đơn (ms):",
        "en": "Single capture delay (ms):"
    },
    "sec_options": {
        "vi": "⚙️ Tùy Chọn Sự Kiện & Xuất File (Options)",
        "en": "⚙️ Event Capture & Export Options"
    },
    "opt_capture_keys": {
        "vi": "Ghi lại các phím đặc biệt (Enter, Tab, Esc, Hotkey)",
        "en": "Capture special keys (Enter, Tab, Esc, Hotkeys)"
    },
    "opt_double_clicks": {
        "vi": "Tự động phân biệt Double Click",
        "en": "Detect double-click events automatically"
    },
    "opt_step_badge": {
        "vi": "Hiển thị huy hiệu số bước (#1, #2...) góc ảnh",
        "en": "Show step number badge (#1, #2...) on screenshots"
    },
    "opt_dark_mode": {
        "vi": "Báo cáo HTML mặc định giao diện Dark Mode",
        "en": "Default HTML report to Dark Mode"
    },
    "opt_embed_images": {
        "vi": "Nhúng toàn bộ ảnh trực tiếp vào 1 file HTML duy nhất (Base64)",
        "en": "Embed images directly into standalone HTML (Base64)"
    },
    "opt_zip_package": {
        "vi": "Đóng gói toàn bộ báo cáo + ảnh vào file .ZIP",
        "en": "Package report and images into a .ZIP archive"
    },
    "opt_auto_open": {
        "vi": "Tự động mở báo cáo trong trình duyệt web sau khi lưu",
        "en": "Auto-open report in web browser after saving"
    },
    "opt_exclude_capture": {
        "vi": "Tự động ẩn thanh công cụ khỏi ảnh chụp màn hình (Windows API)",
        "en": "Exclude toolbar from screenshots (Windows API)"
    },
    "opt_always_on_top": {
        "vi": "Ghim thanh công cụ luôn hiển thị trên cùng (Always on top)",
        "en": "Keep toolbar always on top of other windows"
    },
    "opt_auto_minimize": {
        "vi": "Tự động thu nhỏ thanh công cụ khi bắt đầu ghi hình (Auto-minimize)",
        "en": "Auto-minimize toolbar to taskbar when recording"
    },
    "sec_image_lifecycle": {
        "vi": "🖼️ Vòng Đời Hình Ảnh & Tối Ưu Bộ Nhớ (Image Lifecycle & Optimization)",
        "en": "🖼️ Image Lifecycle & Memory Optimization"
    },
    "lbl_capture_scope": {
        "vi": "Phạm vi chụp màn hình:",
        "en": "Capture Scope:"
    },
    "scope_cursor_monitor": {
        "vi": "🎯 Màn hình chứa chuột (Khuyên dùng - Tiết kiệm 50% pixel)",
        "en": "🎯 Display at Cursor (Recommended - Saves 50% pixels)"
    },
    "scope_active_window": {
        "vi": "🪟 Cửa sổ đang thao tác (+24px viền ngữ cảnh)",
        "en": "🪟 Active Window (+24px Context Padding)"
    },
    "scope_all_monitors": {
        "vi": "🖥️ Toàn bộ màn hình ảo (Tất cả màn hình)",
        "en": "🖥️ All Virtual Displays (Combined)"
    },
    "lbl_image_format": {
        "vi": "Định dạng lưu ảnh & nén:",
        "en": "Image Format & Compression:"
    },
    "format_webp": {
        "vi": "⚡ WebP (Siêu nhẹ, giảm 80% dung lượng HTML, khuyên dùng)",
        "en": "⚡ WebP (High-efficiency, 80% smaller HTML, Recommended)"
    },
    "format_png": {
        "vi": "🖼️ PNG (Chất lượng gốc không nén lossy)",
        "en": "🖼️ PNG (Uncompressed Lossless)"
    },
    "opt_disk_spooling": {
        "vi": "💾 Lưu đệm đĩa SSD (L2 Spooling: Giảm 96% RAM, an toàn khi crash)",
        "en": "💾 L2 SSD Disk Spooling (Drops RAM by 96%, Crash-resilient)"
    },
    "btn_save_settings": {
        "vi": "✓ Lưu Cài Đặt (Save)",
        "en": "✓ Save Settings"
    },
    "btn_cancel_settings": {
        "vi": "Hủy (Cancel)",
        "en": "Cancel"
    },
    "hotkey_save_hint": {
        "vi": "Ctrl+S: Lưu cấu hình | Esc: Hủy",
        "en": "Ctrl+S: Save settings | Esc: Cancel"
    },
    "choose_folder_title": {
        "vi": "Chọn Thư Mục Lưu Báo Cáo",
        "en": "Select Output Folder for Reports"
    },
    "choose_color_title": {
        "vi": "Chọn Màu Highlight",
        "en": "Choose Highlight Color"
    },

    # === Action Descriptions for Steps ===
    "action_left_click": {
        "vi": "Người dùng Nhấp chuột trái tại ({x}, {y}) trên [{window}]",
        "en": "User Left Click at ({x}, {y}) on [{window}]"
    },
    "action_left_click_control": {
        "vi": "Người dùng Nhấp chuột trái vào {control} tại ({x}, {y}) trong [{window}]",
        "en": "User Left Click on {control} at ({x}, {y}) in [{window}]"
    },
    "action_right_click": {
        "vi": "Người dùng Nhấp chuột phải tại ({x}, {y}) trên [{window}]",
        "en": "User Right Click at ({x}, {y}) on [{window}]"
    },
    "action_right_click_control": {
        "vi": "Người dùng Nhấp chuột phải vào {control} tại ({x}, {y}) trong [{window}]",
        "en": "User Right Click on {control} at ({x}, {y}) in [{window}]"
    },
    "action_double_click": {
        "vi": "Người dùng Nhấp đúp chuột tại ({x}, {y}) trên [{window}]",
        "en": "User Double Click at ({x}, {y}) on [{window}]"
    },
    "action_double_click_control": {
        "vi": "Người dùng Nhấp đúp chuột vào {control} tại ({x}, {y}) trong [{window}]",
        "en": "User Double Click on {control} at ({x}, {y}) in [{window}]"
    },
    "action_key_press": {
        "vi": "Người dùng nhấn phím [{key}] trong [{window}]",
        "en": "User pressed [{key}] key in [{window}]"
    },
    "action_comment": {
        "vi": "Ghi chú người dùng: {comment}",
        "en": "User note: {comment}"
    },
    "action_click_result": {
        "vi": "Giao diện kết quả sau khi nhấp chuột (sau {delay}ms) trên [{window}]",
        "en": "Result UI state after click (+{delay}ms) on [{window}]"
    },
    "action_click_result_switched": {
        "vi": "Giao diện kết quả (sau {delay}ms): Chuyển sang [{window}]",
        "en": "Result UI state (+{delay}ms): Switched to [{window}]"
    },
    "action_name_click_result": {
        "vi": "Kết quả thao tác",
        "en": "Click Result"
    },
    "action_name_left_click": {
        "vi": "Nhấp chuột trái",
        "en": "Left Click"
    },
    "action_name_right_click": {
        "vi": "Nhấp chuột phải",
        "en": "Right Click"
    },
    "action_name_double_click": {
        "vi": "Nhấp đúp chuột",
        "en": "Double Click"
    },
    "action_name_key_press": {
        "vi": "Nhấn phím",
        "en": "Key Press"
    },
    "action_name_comment": {
        "vi": "Ghi chú",
        "en": "Comment"
    },
    "action_name_type_text": {
        "vi": "Nhập văn bản",
        "en": "Type Text"
    },
    "action_type_text": {
        "vi": "Người dùng Nhập \"{text}\" trên [{window}]",
        "en": "User typed \"{text}\" on [{window}]"
    },
    "action_type_text_control": {
        "vi": "Người dùng Nhập \"{text}\" vào ô [{control}] trên [{window}]",
        "en": "User typed \"{text}\" into [{control}] on [{window}]"
    },
    "opt_keystroke_aggregator": {
        "vi": "Tự động gom chuỗi gõ phím vào ô nhập liệu (Keystroke Aggregator)",
        "en": "Automatically aggregate typed text into input fields"
    },
    "opt_enable_uia": {
        "vi": "Nhận diện sâu nút bấm & ô nhập qua UI Automation (UIA)",
        "en": "Deep control inspection via Windows UI Automation (UIA)"
    },
    "btn_interactive_guide": {
        "vi": "🎮 Chế độ Trình chiếu tương tác",
        "en": "🎮 Interactive Guide"
    }
}


class I18nManager:
    """Manages active language and string lookup."""

    _current_lang: str = "vi"  # Default Vietnamese

    @classmethod
    def set_language(cls, lang: str) -> None:
        """Set active language ('vi' or 'en')."""
        if lang in ("vi", "en"):
            cls._current_lang = lang
        elif lang.startswith("en"):
            cls._current_lang = "en"
        else:
            cls._current_lang = "vi"

    @classmethod
    def get_language(cls) -> str:
        """Get current active language."""
        return cls._current_lang

    @classmethod
    def t(cls, key: str, **kwargs: Any) -> str:
        """Lookup localized string by key with fallback and string formatting."""
        item = TRANSLATIONS.get(key)
        if not item:
            return key
        text = item.get(cls._current_lang) or item.get("vi") or item.get("en") or key
        if kwargs:
            try:
                return text.format(**kwargs)
            except Exception:
                return text
        return text


# Convenient top-level helper function
def t(key: str, **kwargs: Any) -> str:
    """Convenient alias for I18nManager.t."""
    return I18nManager.t(key, **kwargs)

