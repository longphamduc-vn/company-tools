"""
Comprehensive test suite for Python Step Recorder.
"""

import os
import sys
import tempfile
import unittest
from datetime import datetime
from PIL import Image

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from step_recorder.config import RecorderConfig
from step_recorder.models import Step, SessionMetadata
from step_recorder.annotator import (
    annotate_screenshot,
    hex_to_rgba,
    apply_blur_region,
    apply_redact_region,
    crop_image,
    draw_box_annotation
)
from step_recorder.capture import ScreenCapture
from step_recorder.window_info import get_active_window_info, WindowDetails
from step_recorder.exporter import ReportExporter
from step_recorder.recorder import RecordingEngine
from step_recorder.hotkeys import GlobalHotkeyManager


class TestStepRecorder(unittest.TestCase):

    def test_config_defaults_and_save_load(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg_path = os.path.join(tmpdir, "config.json")
            cfg = RecorderConfig(
                output_dir=tmpdir,
                max_steps=150,
                highlight_color="#00FFCC",
                highlight_style="crosshair"
            )
            cfg.save(cfg_path)
            self.assertTrue(os.path.exists(cfg_path))

            loaded = RecorderConfig.load(cfg_path)
            self.assertEqual(loaded.output_dir, tmpdir)
            self.assertEqual(loaded.max_steps, 150)
            self.assertEqual(loaded.highlight_color, "#00FFCC")
            self.assertEqual(loaded.highlight_style, "crosshair")

    def test_hex_to_rgba(self):
        rgba = hex_to_rgba("#FF3366", 200)
        self.assertEqual(rgba, (255, 51, 102, 200))
        rgba_invalid = hex_to_rgba("xyz", 100)
        self.assertEqual(rgba_invalid, (255, 51, 102, 100))

    def test_annotator_all_styles(self):
        base_img = Image.new("RGB", (640, 480), color=(50, 50, 50))

        for style in ["ring", "crosshair", "glow", "solid"]:
            annotated = annotate_screenshot(
                base_img,
                cursor_pos=(200, 150),
                step_id=1,
                color_hex="#38BDF8",
                radius=20,
                style=style,
                show_badge=True
            )
            self.assertEqual(annotated.size, (640, 480))
            self.assertEqual(annotated.mode, "RGB")

    def test_annotator_highlight_rect(self):
        base_img = Image.new("RGB", (640, 480), color=(20, 20, 20))
        annotated = annotate_screenshot(
            base_img,
            highlight_rect=(50, 50, 300, 250),
            step_id=2,
            color_hex="#10B981"
        )
        self.assertEqual(annotated.size, (640, 480))

    def test_capture_and_thumbnails(self):
        capture = ScreenCapture()
        test_img = Image.new("RGB", (1920, 1080), color=(100, 150, 200))
        thumb = capture.create_thumbnail(test_img, max_size=(300, 200))
        self.assertLessEqual(thumb.width, 300)
        self.assertLessEqual(thumb.height, 200)

        raw_bytes = capture.image_to_bytes(thumb, format="PNG")
        self.assertGreater(len(raw_bytes), 0)

    def test_window_info(self):
        title, proc = get_active_window_info()
        self.assertIsInstance(title, str)
        self.assertIsInstance(proc, str)
        self.assertGreater(len(title), 0)

    def test_exporter_html_markdown_zip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = RecorderConfig(
                output_dir=tmpdir,
                create_zip_package=True,
                language="en"
            )
            exporter = ReportExporter(config)

            # Create mock steps
            test_img = Image.new("RGB", (400, 300), color=(30, 40, 50))
            capture = ScreenCapture()
            img_bytes = capture.image_to_bytes(test_img)

            step1 = Step(
                step_id=1,
                timestamp=datetime.now(),
                action_type="left_click",
                description="User Left Click on [Chrome]",
                window_title="Google Chrome - Google Search",
                process_name="chrome",
                cursor_x=250,
                cursor_y=180,
                annotated_image_bytes=img_bytes
            )

            step2 = Step(
                step_id=2,
                timestamp=datetime.now(),
                action_type="comment",
                description="User Comment: Verification step",
                window_title="Visual Studio Code",
                process_name="code",
                user_comment="Notice the button does not trigger any network request",
                annotated_image_bytes=img_bytes
            )

            metadata = SessionMetadata(
                session_id="test_session_001",
                title="E2E Problem Steps Test",
                description="Unit test recording session",
                start_time=datetime.now(),
                end_time=datetime.now(),
                os_name="Linux TestOS",
                screen_resolution="1920x1080",
                apps_used=["chrome", "code"]
            )

            results = exporter.export([step1, step2], metadata, tmpdir)

            # Verify generated files
            self.assertIn("html", results)
            self.assertIn("markdown", results)
            self.assertIn("json", results)
            self.assertIn("zip", results)

            self.assertTrue(os.path.exists(results["html"]))
            self.assertTrue(os.path.exists(results["markdown"]))
            self.assertTrue(os.path.exists(results["json"]))
            self.assertTrue(os.path.exists(results["zip"]))

            # Inspect HTML contents
            with open(results["html"], "r", encoding="utf-8") as f:
                html_text = f.read()
                self.assertIn("E2E Problem Steps Test", html_text)
                self.assertIn("Google Chrome - Google Search", html_text)
                self.assertIn("Notice the button does not trigger any network request", html_text)
                self.assertIn("data:image/png;base64,", html_text)

            # Inspect Markdown contents
            with open(results["markdown"], "r", encoding="utf-8") as f:
                md_text = f.read()
                self.assertIn("# 📋 E2E Problem Steps Test", md_text)
                self.assertIn("Step 1: Left Click", md_text)
                self.assertIn("Step 2: Comment", md_text)

    def test_recorder_engine_state_lifecycle(self):
        config = RecorderConfig(
            capture_clicks=False,  # don't hook OS inputs in test
            capture_keys=False
        )
        engine = RecordingEngine(config)
        self.assertEqual(engine.state, "idle")

        states = []
        engine.on_state_changed = lambda s: states.append(s)

        engine.start_recording(title="Lifecycle Test")
        self.assertEqual(engine.state, "recording")
        self.assertIn("recording", states)

        engine.pause_recording()
        self.assertEqual(engine.state, "paused")

        engine.resume_recording()
        self.assertEqual(engine.state, "recording")

        # Test ignore bounds
        engine.set_ignore_bounds([(10, 10, 100, 100)])
        self.assertTrue(engine.is_in_ignored_region(50, 50))
        self.assertFalse(engine.is_in_ignored_region(200, 200))

        engine.stop_recording()
        self.assertEqual(engine.state, "stopped")

    def test_settings_dialog_save_logic(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg_file = os.path.join(tmpdir, "test_cfg.json")
            cfg = RecorderConfig(output_dir=tmpdir)
            cfg.save(cfg_file)

            # Test modify & save
            cfg.max_steps = 320
            cfg.highlight_style = "glow"
            cfg.highlight_color = "#10B981"
            cfg.screenshot_delay_ms = 120
            cfg.save(cfg_file)

            reloaded = RecorderConfig.load(cfg_file)
            self.assertEqual(reloaded.max_steps, 320)
            self.assertEqual(reloaded.highlight_style, "glow")
            self.assertEqual(reloaded.highlight_color, "#10B981")
            self.assertEqual(reloaded.screenshot_delay_ms, 120)

    def test_i18n_and_step_editor_renumbering(self):
        from step_recorder.i18n import t, I18nManager
        
        # Test Vietnamese
        I18nManager.set_language("vi")
        self.assertEqual(t("btn_start"), "⏺ Bắt đầu")
        self.assertEqual(t("btn_settings"), "⚙ Cài đặt")
        self.assertIn("Sẵn sàng", t("status_ready"))

        # Test English
        I18nManager.set_language("en")
        self.assertEqual(t("btn_start"), "⏺ Start")
        self.assertEqual(t("btn_settings"), "⚙ Settings")
        self.assertIn("Ready", t("status_ready"))

        # Test renumbering on Step models
        steps = [
            Step(step_id=1, timestamp=datetime.now(), action_type="click", description="Step 1"),
            Step(step_id=2, timestamp=datetime.now(), action_type="click", description="Step 2"),
            Step(step_id=3, timestamp=datetime.now(), action_type="click", description="Step 3"),
        ]
        # Simulate deleting Step 2
        steps.pop(1)
        for i, s in enumerate(steps):
            s.step_id = i + 1

        self.assertEqual(len(steps), 2)
        self.assertEqual(steps[0].step_id, 1)
        self.assertEqual(steps[1].step_id, 2)
        self.assertEqual(steps[1].description, "Step 3")

    def test_step_section_fields_and_serialization(self):
        step = Step(
            step_id=1,
            timestamp=datetime(2026, 11, 4, 10, 0, 0),
            action_type="comment",
            description="Start of section",
            is_section_header=True,
            section_title="Chương 1: Cài đặt môi trường",
            section_description="Hướng dẫn thiết lập các thông số ban đầu"
        )
        self.assertTrue(step.is_section_header)
        self.assertEqual(step.section_title, "Chương 1: Cài đặt môi trường")

        data = step.to_dict()
        self.assertTrue(data["is_section_header"])
        self.assertEqual(data["section_title"], "Chương 1: Cài đặt môi trường")
        self.assertEqual(data["section_description"], "Hướng dẫn thiết lập các thông số ban đầu")

        reconstructed = Step.from_dict(data)
        self.assertTrue(reconstructed.is_section_header)
        self.assertEqual(reconstructed.section_title, "Chương 1: Cài đặt môi trường")
        self.assertEqual(reconstructed.section_description, "Hướng dẫn thiết lập các thông số ban đầu")
        self.assertEqual(reconstructed.step_id, 1)

    def test_section_grouping_and_toc_export(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = RecorderConfig(
                output_dir=tmpdir,
                create_zip_package=False,
                language="vi"
            )
            exporter = ReportExporter(config)

            steps = [
                Step(
                    step_id=1,
                    timestamp=datetime.now(),
                    action_type="comment",
                    description="Bước mở đầu",
                    is_section_header=True,
                    section_title="Phần 1: Chuẩn Bị",
                    section_description="Mục tiêu cài đặt các thành phần phụ trợ"
                ),
                Step(
                    step_id=2,
                    timestamp=datetime.now(),
                    action_type="left_click",
                    description="Nhấp chuột vào nút Start"
                ),
                Step(
                    step_id=3,
                    timestamp=datetime.now(),
                    action_type="comment",
                    description="Bước cấu hình hệ thống",
                    is_section_header=True,
                    section_title="Phần 2: Cấu Hình",
                    section_description="Thiết lập các thông số nâng cao"
                ),
                Step(
                    step_id=4,
                    timestamp=datetime.now(),
                    action_type="key_press",
                    description="Nhấn phím Enter"
                ),
            ]

            metadata = SessionMetadata(
                session_id="test_toc_session",
                title="Tài Liệu Hướng Dẫn Thao Tác SOP",
                description="Mô tả quy trình chi tiết",
                os_name="Windows 11 Test",
                total_steps=4
            )

            # Check _group_sections
            sections = exporter._group_sections(steps, is_vi=True)
            self.assertEqual(len(sections), 2)
            self.assertEqual(sections[0]["title"], "Phần 1: Chuẩn Bị")
            self.assertEqual(len(sections[0]["steps"]), 2)
            self.assertEqual(sections[1]["title"], "Phần 2: Cấu Hình")
            self.assertEqual(len(sections[1]["steps"]), 2)

            results = exporter.export(steps, metadata, tmpdir)
            html_path = results["html"]
            md_path = results["markdown"]

            self.assertTrue(os.path.exists(html_path))
            self.assertTrue(os.path.exists(md_path))

            with open(html_path, "r", encoding="utf-8") as f:
                html_text = f.read()

            self.assertIn("toc-sidebar", html_text)
            self.assertIn("section-banner", html_text)
            self.assertIn("Phần 1: Chuẩn Bị", html_text)
            self.assertIn("Phần 2: Cấu Hình", html_text)
            self.assertIn("data-i18n=\"toc_title\"", html_text)

            with open(md_path, "r", encoding="utf-8") as f:
                md_text = f.read()

            self.assertIn("## 📑 Mục Lục Hướng Dẫn", md_text)
            self.assertIn("Phần 1: Chuẩn Bị", md_text)
            self.assertIn("Phần 2: Cấu Hình", md_text)
            self.assertIn("## 📑 Phần 1: Chuẩn Bị", md_text)
            self.assertIn("## 📑 Phần 2: Cấu Hình", md_text)

    def test_annotator_blur_redact_crop_and_box(self):
        base_img = Image.new("RGB", (400, 300), color=(100, 150, 200))

        # 1. Test Privacy Blur
        blurred = apply_blur_region(base_img, (50, 50, 200, 150), radius=16)
        self.assertEqual(blurred.size, (400, 300))
        self.assertEqual(blurred.mode, "RGB")

        # 2. Test Privacy Redact Blackout
        redacted = apply_redact_region(base_img, (60, 60, 250, 160), fill_color=(0, 0, 0), draw_label=True)
        self.assertEqual(redacted.size, (400, 300))
        # Center of redaction should be filled with black
        self.assertEqual(redacted.getpixel((65, 65)), (0, 0, 0))

        # 3. Test Crop Image
        cropped = crop_image(base_img, (100, 80, 300, 250))
        self.assertEqual(cropped.size, (200, 170))

        # 4. Test Red Attention Box
        boxed = draw_box_annotation(base_img, (20, 20, 180, 140), color_hex="#EF4444", width=3)
        self.assertEqual(boxed.size, (400, 300))

    def test_global_hotkeys_manager_lifecycle(self):
        hotkeys = GlobalHotkeyManager(
            on_start_stop=lambda: None,
            on_pause_resume=lambda: None,
            on_comment=lambda: None,
            on_mark_section=lambda: None,
            on_open_review=lambda: None,
            on_open_saved=lambda: None
        )
        # Verify starting and stopping is safe across any environment
        hotkeys.start()
        hotkeys.stop()
        self.assertFalse(hotkeys._running)

    def test_saved_session_open_and_insert_logic(self):
        import json
        with tempfile.TemporaryDirectory() as tmpdir:
            sess_file = os.path.join(tmpdir, "session.json")
            sample_data = {
                "session": {
                    "id": "saved_test_session",
                    "title": "Tài Liệu Đã Lưu",
                    "description": "Kiểm tra chèn bước"
                },
                "steps": [
                    {
                        "step_id": 1,
                        "timestamp": "2026-11-04 12:00:00.000",
                        "action_type": "left_click",
                        "description": "Thao tác từ file cũ",
                        "window_title": "App 1",
                        "process_name": "app.exe"
                    }
                ]
            }
            with open(sess_file, "w", encoding="utf-8") as f:
                json.dump(sample_data, f)

            # Re-read and parse
            with open(sess_file, "r", encoding="utf-8") as f:
                loaded = json.load(f)

            steps_imported = [Step.from_dict(s) for s in loaded["steps"]]
            self.assertEqual(len(steps_imported), 1)
            self.assertEqual(steps_imported[0].description, "Thao tác từ file cũ")

            # Test inserting into existing steps
            existing_steps = [
                Step(step_id=1, timestamp=datetime.now(), action_type="click", description="Step A"),
                Step(step_id=2, timestamp=datetime.now(), action_type="click", description="Step B")
            ]
            insert_idx = 1
            for i, s in enumerate(steps_imported):
                existing_steps.insert(insert_idx + i, s)

            # Renumber sequentially
            for i, s in enumerate(existing_steps):
                s.step_id = i + 1

            self.assertEqual(len(existing_steps), 3)
            self.assertEqual(existing_steps[0].description, "Step A")
            self.assertEqual(existing_steps[1].description, "Thao tác từ file cũ")
            self.assertEqual(existing_steps[1].step_id, 2)
            self.assertEqual(existing_steps[2].description, "Step B")
            self.assertEqual(existing_steps[2].step_id, 3)

    def test_dual_capture_on_click(self):
        from pynput.mouse import Button
        from PIL import ImageDraw
        config = RecorderConfig(
            capture_clicks=False,
            capture_keys=False,
            dual_capture_on_click=True,
            second_capture_delay_ms=20,
            dual_capture_smart_detect=False,
            language="vi"
        )
        engine = RecordingEngine(config)
        engine.start_recording("Test Dual Capture")

        dummy_img = Image.new("RGB", (300, 200), color=(50, 60, 70))
        engine.capture.capture_full_screen = lambda: (dummy_img, 0, 0)

        # 1. Trigger unconditional dual capture click event
        engine._process_click_event(100, 100, Button.left, is_double_click=False, click_id=1)

        # Verify 2 steps were recorded: Immediate click + Result after delay
        self.assertEqual(len(engine.steps), 2)
        step1 = engine.steps[0]
        step2 = engine.steps[1]

        self.assertEqual(step1.step_id, 1)
        self.assertEqual(step1.action_type, "left_click")
        self.assertEqual(step1.cursor_x, 100)
        self.assertEqual(step1.cursor_y, 100)

        self.assertEqual(step2.step_id, 2)
        self.assertEqual(step2.action_type, "click_result")
        self.assertIn("Giao diện kết quả", step2.description)
        self.assertIn("20ms", step2.description)
        self.assertEqual(step2.action_icon, "⚡")
        self.assertEqual(step2.badge_class, "badge-success")

        # 2. Test Smart Auto-Detection mode
        config.dual_capture_smart_detect = True
        
        # Scenario A: Screen does NOT change -> only 1 step added
        engine._process_click_event(120, 120, Button.left, is_double_click=False, click_id=2)
        self.assertEqual(len(engine.steps), 3)

        # Scenario B: Screen changes (modal / dropdown appears) -> 2 steps added
        changed_img = dummy_img.copy()
        ImageDraw.Draw(changed_img).rectangle((50, 50, 200, 150), fill=(255, 255, 255))
        
        shots = [dummy_img, changed_img]
        engine.capture.capture_full_screen = lambda: (shots.pop(0) if shots else changed_img, 0, 0)
        engine._process_click_event(130, 130, Button.left, is_double_click=False, click_id=3)
        self.assertEqual(len(engine.steps), 5)  # 3 + 2 = 5 steps!

        # 3. Test single-capture mode (dual_capture_on_click=False)
        config.dual_capture_on_click = False
        config.screenshot_delay_ms = 0
        engine._process_click_event(150, 150, Button.right, is_double_click=False, click_id=4)

        # Only 1 additional step should be added
        self.assertEqual(len(engine.steps), 6)
        self.assertEqual(engine.steps[5].step_id, 6)
        self.assertEqual(engine.steps[5].action_type, "right_click")

        engine.stop_recording()

    def test_smart_ui_change_detection_algorithm(self):
        from step_recorder.annotator import has_ui_changed
        from PIL import ImageDraw

        base = Image.new("RGB", (640, 480), color=(40, 50, 60))

        # 1. Identical screenshots -> False
        self.assertFalse(has_ui_changed(base, base.copy(), click_pos=(100, 100)))

        # 2. Blinking 1px text cursor -> False (filtered out)
        blink = base.copy()
        ImageDraw.Draw(blink).line([(100, 100), (100, 114)], fill=(255, 255, 255), width=1)
        self.assertFalse(has_ui_changed(base, blink, click_pos=(100, 100)))

        # 3. Checkbox toggled -> True
        chk = base.copy()
        ImageDraw.Draw(chk).rectangle([(90, 90), (110, 110)], fill=(14, 165, 233))
        self.assertTrue(has_ui_changed(base, chk, click_pos=(100, 100)))

        # 4. Dropdown menu opened -> True
        menu = base.copy()
        ImageDraw.Draw(menu).rectangle([(80, 80), (300, 250)], fill=(240, 240, 240))
        self.assertTrue(has_ui_changed(base, menu, click_pos=(100, 100)))

        # 5. Window title switched -> True
        self.assertTrue(has_ui_changed(base, base.copy(), win1="App", win2="Save As Dialog"))

    def test_step_decision_point_serialization(self):
        """Test Step model with Yes/No conditional branching serialization and deserialization."""
        step = Step(
            step_id=5,
            timestamp=datetime(2026, 11, 5, 14, 0, 0),
            action_type="left_click",
            description="Nhấp chọn nút Đăng Nhập",
            is_decision_point=True,
            condition_question="Hệ thống có hiển thị mã OTP qua SMS không?",
            yes_branch_text="Nhập mã OTP 6 số nhận được trên điện thoại",
            yes_next_step=6,
            no_branch_text="Đăng nhập trực tiếp vào trang chủ thành công",
            no_next_step=8
        )

        d = step.to_dict()
        self.assertTrue(d["is_decision_point"])
        self.assertEqual(d["condition_question"], "Hệ thống có hiển thị mã OTP qua SMS không?")
        self.assertEqual(d["yes_branch_text"], "Nhập mã OTP 6 số nhận được trên điện thoại")
        self.assertEqual(d["yes_next_step"], 6)
        self.assertEqual(d["no_branch_text"], "Đăng nhập trực tiếp vào trang chủ thành công")
        self.assertEqual(d["no_next_step"], 8)

        restored = Step.from_dict(d)
        self.assertTrue(restored.is_decision_point)
        self.assertEqual(restored.condition_question, step.condition_question)
        self.assertEqual(restored.yes_branch_text, step.yes_branch_text)
        self.assertEqual(restored.yes_next_step, 6)
        self.assertEqual(restored.no_branch_text, step.no_branch_text)
        self.assertEqual(restored.no_next_step, 8)

    def test_exporter_decision_point_branching(self):
        """Test HTML and Markdown export of Decision Point cards with Y/N branches."""
        config = RecorderConfig(language="vi")
        exporter = ReportExporter(config)

        with tempfile.TemporaryDirectory() as tmpdir:
            steps = [
                Step(
                    step_id=1,
                    timestamp=datetime.now(),
                    action_type="left_click",
                    description="Nhấp vào nút Lưu thay đổi",
                    is_decision_point=True,
                    condition_question="Cửa sổ thông báo xác nhận có xuất hiện không?",
                    yes_branch_text="Nhấp Đồng ý để tiếp tục lưu dữ liệu",
                    yes_next_step=2,
                    no_branch_text="Kiểm tra lại thông tin đầu vào chưa hợp lệ",
                    no_next_step=5
                ),
                Step(
                    step_id=2,
                    timestamp=datetime.now(),
                    action_type="left_click",
                    description="Nhấp nút Đồng ý"
                ),
                Step(
                    step_id=5,
                    timestamp=datetime.now(),
                    action_type="left_click",
                    description="Kiểm tra thông tin"
                )
            ]

            metadata = SessionMetadata(
                session_id="test_decision_session",
                title="Quy Trình Xử Lý Đơn Hàng Có Điều Kiện",
                description="Hướng dẫn phân nhánh Yes/No",
                os_name="Linux / Windows Test",
                total_steps=3
            )

            results = exporter.export(steps, metadata, tmpdir)
            html_path = results["html"]
            md_path = results["markdown"]

            self.assertTrue(os.path.exists(html_path))
            self.assertTrue(os.path.exists(md_path))

            with open(html_path, "r", encoding="utf-8") as f:
                html_content = f.read()

            # Verify HTML contains decision card elements
            self.assertIn("decision-card", html_content)
            self.assertIn("Cửa sổ thông báo xác nhận có xuất hiện không?", html_content)
            self.assertIn("branch-yes", html_content)
            self.assertIn("branch-no", html_content)
            self.assertIn("Nhấp Đồng ý để tiếp tục lưu dữ liệu", html_content)
            self.assertIn("href=\"#step-2\"", html_content)
            self.assertIn("href=\"#step-5\"", html_content)
            self.assertIn("Nhánh Y/N", html_content)
            # Verify TOC has branch icon
            self.assertIn("🔀", html_content)

            with open(md_path, "r", encoding="utf-8") as f:
                md_content = f.read()

            # Verify Markdown contains decision block and anchor links
            self.assertIn("ĐIỂM RẼ NHÁNH ĐIỀU KIỆN (YES / NO)", md_content)
            self.assertIn("Cửa sổ thông báo xác nhận có xuất hiện không?", md_content)
            self.assertIn("YES / ĐÚNG", md_content)
            self.assertIn("NO / SAI", md_content)
            self.assertIn("[**Bước 2**](#step-2)", md_content)
            self.assertIn("[**Bước 5**](#step-5)", md_content)
            self.assertIn("[🔀 Y/N]", md_content)

    def test_fast_delete_and_async_badge_renumbering(self):
        """Test that deleting steps is instant, renumbers in memory, and preserves custom privacy edits."""
        import tkinter as tk
        from step_recorder.ui.step_editor import StepEditorWindow

        root = tk.Tk()
        root.withdraw()

        cfg = RecorderConfig(show_step_badge_on_screenshot=True)
        img = Image.new("RGB", (200, 100), color=(80, 80, 80))
        img_bytes = ScreenCapture.image_to_bytes(img)

        steps = [
            Step(step_id=1, timestamp=datetime.now(), action_type="left_click", description="Step 1", raw_image_bytes=img_bytes, annotated_image_bytes=img_bytes),
            Step(step_id=2, timestamp=datetime.now(), action_type="left_click", description="Step 2 (to delete)", raw_image_bytes=img_bytes, annotated_image_bytes=img_bytes),
            Step(step_id=3, timestamp=datetime.now(), action_type="left_click", description="Step 3 (custom edited)", raw_image_bytes=img_bytes, annotated_image_bytes=b"CUSTOM_EDITED_BLUR_BYTES"),
            Step(step_id=4, timestamp=datetime.now(), action_type="left_click", description="Step 4", raw_image_bytes=img_bytes, annotated_image_bytes=img_bytes),
        ]
        # Mark step 3 as custom edited
        steps[2]._is_custom_edited = True

        metadata = SessionMetadata(session_id="test_fast_del", title="Fast Delete Test")
        editor = StepEditorWindow(root, steps, metadata, cfg, ReportExporter(cfg))

        # Delete step 2 directly
        editor.steps.pop(1)
        editor._renumber_steps(from_index=1)

        # 1. Step IDs should be sequentially renumbered instantly (1, 2, 3)
        self.assertEqual(len(editor.steps), 3)
        self.assertEqual(editor.steps[0].step_id, 1)
        self.assertEqual(editor.steps[1].step_id, 2)
        self.assertEqual(editor.steps[2].step_id, 3)

        # 2. Custom edited bytes must NOT be overwritten!
        self.assertEqual(editor.steps[1].annotated_image_bytes, b"CUSTOM_EDITED_BLUR_BYTES")

        # 3. Wait for background badge thread if active
        if editor._active_badge_thread and editor._active_badge_thread.is_alive():
            editor._active_badge_thread.join(timeout=2.0)

        # Custom edits still preserved after thread finishes
        self.assertEqual(editor.steps[1].annotated_image_bytes, b"CUSTOM_EDITED_BLUR_BYTES")

        root.destroy()

    def test_batch_delete_and_undo_deletion(self):
        """Test selecting multiple steps, batch deletion, and full undo restoration."""
        import tkinter as tk
        from step_recorder.ui.step_editor import StepEditorWindow

        root = tk.Tk()
        root.withdraw()

        cfg = RecorderConfig()
        img = Image.new("RGB", (100, 100), color=(50, 50, 50))
        img_bytes = ScreenCapture.image_to_bytes(img)

        steps = [
            Step(step_id=1, timestamp=datetime.now(), action_type="left_click", description="Step 1", raw_image_bytes=img_bytes),
            Step(step_id=2, timestamp=datetime.now(), action_type="left_click", description="Step 2", raw_image_bytes=img_bytes),
            Step(step_id=3, timestamp=datetime.now(), action_type="left_click", description="Step 3", raw_image_bytes=img_bytes),
            Step(step_id=4, timestamp=datetime.now(), action_type="left_click", description="Step 4", raw_image_bytes=img_bytes),
            Step(step_id=5, timestamp=datetime.now(), action_type="left_click", description="Step 5", raw_image_bytes=img_bytes),
            Step(step_id=6, timestamp=datetime.now(), action_type="left_click", description="Step 6", raw_image_bytes=img_bytes),
        ]

        metadata = SessionMetadata(session_id="test_batch_del", title="Batch Delete & Undo")
        editor = StepEditorWindow(root, steps, metadata, cfg, ReportExporter(cfg))

        # 1. Test Select All
        editor._toggle_select_all()
        selected = editor.step_listbox.curselection()
        self.assertEqual(len(selected), 6)
        self.assertIn("6", editor.del_btn.cget("text"))

        # Test Deselect All
        editor._toggle_select_all()
        self.assertEqual(len(editor.step_listbox.curselection()), 0)

        # 2. Select specific batch: Step 2, Step 4, Step 5 (indices 1, 3, 4)
        for idx in (1, 3, 4):
            editor.step_listbox.selection_set(idx)
        editor._on_list_select()

        self.assertEqual(len(editor.step_listbox.curselection()), 3)
        self.assertIn("3", editor.del_btn.cget("text"))

        # 3. Perform batch deletion
        real_indices = [1, 3, 4]
        deleted_items = [(i, editor.steps[i]) for i in real_indices]
        editor.action_history.append({
            "type": "delete_steps",
            "items": deleted_items
        })
        for i in reversed(real_indices):
            editor.steps.pop(i)

        editor._renumber_steps(from_index=1)
        editor._on_filter_changed()

        # Verify only 3 steps remain: Step 1, Step 3, Step 6
        self.assertEqual(len(editor.steps), 3)
        self.assertEqual(editor.steps[0].description, "Step 1")
        self.assertEqual(editor.steps[0].step_id, 1)
        self.assertEqual(editor.steps[1].description, "Step 3")
        self.assertEqual(editor.steps[1].step_id, 2)
        self.assertEqual(editor.steps[2].description, "Step 6")
        self.assertEqual(editor.steps[2].step_id, 3)

        # 4. Perform Undo
        editor._undo_last_action()

        # All 6 steps must be restored in exact original sequence!
        self.assertEqual(len(editor.steps), 6)
        expected_descs = ["Step 1", "Step 2", "Step 3", "Step 4", "Step 5", "Step 6"]
        for i, desc in enumerate(expected_descs):
            self.assertEqual(editor.steps[i].description, desc)
            self.assertEqual(editor.steps[i].step_id, i + 1)

        root.destroy()

    def test_smart_keystroke_aggregator(self):
        """Test that typing buffer aggregates consecutive keystrokes into a single type_text step."""
        config = RecorderConfig(
            capture_clicks=False,
            capture_keys=False,
            enable_keystroke_aggregator=True
        )
        engine = RecordingEngine(config)
        engine.state = "recording"

        # Simulate typing "Hello" and flushing with trigger_key="enter"
        engine._text_buffer = ["H", "e", "l", "l", "o"]
        mock_win = WindowDetails(
            title="Search Portal",
            process_name="chrome.exe",
            ui_control="'Query Box' [Edit]",
            control_rect=(100, 200, 300, 40)
        )
        engine._typing_win_details = mock_win
        engine._typing_cursor_pos = (150, 220)

        # Flush buffer
        engine.flush_text_buffer(trigger_key="enter")

        # Wait briefly for worker thread
        import time
        time.sleep(0.3)

        self.assertEqual(len(engine.steps), 1)
        step = engine.steps[0]
        self.assertEqual(step.action_type, "type_text")
        self.assertEqual(step.typed_text, "Hello")
        self.assertIn("Hello (ENTER)", step.description)
        self.assertEqual(step.control_rect, (100, 200, 300, 40))

    def test_uia_window_info_details(self):
        """Test WindowDetails data structure and unpackability with UIA fields."""
        details = WindowDetails(
            title="Google Chrome - Order Form",
            process_name="chrome.exe",
            pid=1234,
            ui_control="'Submit' [Button]",
            control_type="Button",
            control_name="Submit",
            automation_id="btn-submit",
            control_rect=(100, 200, 80, 35),
            is_password=False
        )
        self.assertEqual(details.ui_control, "'Submit' [Button]")
        self.assertEqual(details.control_type, "Button")
        self.assertEqual(details.control_rect, (100, 200, 80, 35))

        # Backward compatibility tuple unpacking
        title, proc = details
        self.assertEqual(title, "Google Chrome - Order Form")
        self.assertEqual(proc, "chrome.exe")

    def test_interactive_guide_player_export(self):
        """Test that HTML export includes full offline Interactive Guide Player."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = RecorderConfig(output_dir=tmpdir, language="vi")
            exporter = ReportExporter(config)

            step = Step(
                step_id=1,
                timestamp=datetime.now(),
                action_type="left_click",
                description="Nhấn nút Xác nhận",
                window_title="Browser",
                cursor_x=450,
                cursor_y=320,
                annotated_image_bytes=b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
            )

            metadata = SessionMetadata(
                session_id="rec_player_test",
                title="Interactive Guide SOP Test"
            )

            results = exporter.export([step], metadata, tmpdir)
            self.assertTrue(os.path.exists(results["html"]))

            with open(results["html"], "r", encoding="utf-8") as f:
                html = f.read()
                # Verify Interactive Guide Player DOM elements
                self.assertIn('id="interactivePlayerModal"', html)
                self.assertIn('id="playerHotspot"', html)
                self.assertIn('id="playerInstructionBar"', html)
                self.assertIn('id="playerFilmstrip"', html)
                self.assertIn('openInteractivePlayer', html)
                self.assertIn('allStepData', html)
                self.assertIn('playerLaunchBtn', html)

    def test_webp_and_image_lifecycle_capture(self):
        """Test WebP byte encoding, disk file saving, and scope dispatching."""
        capture = ScreenCapture()
        test_img = Image.new("RGB", (320, 240), color=(30, 144, 255))

        # Test WebP vs PNG conversion
        webp_bytes = capture.image_to_bytes(test_img, format="WEBP", quality=80)
        png_bytes = capture.image_to_bytes(test_img, format="PNG")
        self.assertGreater(len(webp_bytes), 0)
        self.assertGreater(len(png_bytes), 0)

        # WebP header starts with RIFF and contains WEBP
        self.assertTrue(webp_bytes.startswith(b"RIFF"))
        self.assertIn(b"WEBP", webp_bytes[:16])

        # Test save to file
        with tempfile.TemporaryDirectory() as tmpdir:
            dest_webp = os.path.join(tmpdir, "test_shot.webp")
            capture.save_image_to_file(test_img, dest_webp, format="WEBP", quality=85)
            self.assertTrue(os.path.exists(dest_webp))
            self.assertGreater(os.path.getsize(dest_webp), 0)

        # Test capture_for_event dispatcher with window rect
        img, l, t = capture.capture_for_event(cursor_pos=(100, 100), scope="cursor_monitor")
        self.assertIsInstance(img, Image.Image)

        capture.close()

    def test_tiered_storage_l2_disk_spooling(self):
        """Test that L2 disk spooling frees RAM by storing raw/annotated full images on SSD and loading lazily."""
        with tempfile.TemporaryDirectory() as spool_base:
            config = RecorderConfig(
                capture_clicks=False,
                capture_keys=False,
                enable_disk_spooling=True,
                disk_spool_dir=spool_base,
                image_format="WEBP",
                dual_capture_on_click=False
            )
            engine = RecordingEngine(config)
            engine.start_recording("Spooling Test Session")

            dummy = Image.new("RGB", (400, 300), color=(100, 120, 140))
            engine.capture.capture_full_screen = lambda: (dummy, 0, 0)

            from pynput.mouse import Button
            engine._process_click_event(150, 150, Button.left, is_double_click=False, click_id=1)

            self.assertEqual(len(engine.steps), 1)
            step = engine.steps[0]

            # In RAM: full bytes are None (freed to save 96% RAM footprint)
            self.assertIsNone(step.raw_image_bytes)
            self.assertIsNone(step.annotated_image_bytes)

            # Thumbnail bytes remain in RAM for fast list scrolling
            self.assertIsNotNone(step.thumbnail_bytes)

            # Disk spool paths are populated and files exist on SSD
            self.assertIsNotNone(step.spool_raw_path)
            self.assertIsNotNone(step.spool_annotated_path)
            self.assertTrue(os.path.exists(step.spool_raw_path))
            self.assertTrue(os.path.exists(step.spool_annotated_path))

            # Lazy loading methods successfully read from disk
            ann_bytes = step.get_annotated_bytes()
            self.assertIsNotNone(ann_bytes)
            self.assertTrue(ann_bytes.startswith(b"RIFF"))

            raw_bytes = step.get_raw_bytes()
            self.assertIsNotNone(raw_bytes)
            self.assertTrue(raw_bytes.startswith(b"RIFF"))

            # Base64 and data URI are correctly generated
            self.assertIsNotNone(step.base64_image)
            self.assertTrue(step.image_data_uri.startswith("data:image/webp;base64,"))
            self.assertEqual(step.image_filename, "step_001_left_click.webp")

            # Cleanup spool removes temporary folder
            spool_dir = engine._spool_dir
            self.assertTrue(os.path.exists(spool_dir))
            engine.cleanup_spool()
            self.assertFalse(os.path.exists(spool_dir))
            engine.close()

    def test_webp_html_and_markdown_exporter(self):
        """Test ReportExporter exports WebP files, generates optimized HTML with lazy/async decoding and correct markdown links."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = RecorderConfig(
                output_dir=tmpdir,
                image_format="WEBP",
                save_raw_screenshots=True
            )
            exporter = ReportExporter(config)

            dummy = Image.new("RGB", (200, 150), color=(20, 80, 120))
            capture = ScreenCapture()
            webp_data = capture.image_to_bytes(dummy, format="WEBP")

            step = Step(
                step_id=1,
                timestamp=datetime.now(),
                action_type="left_click",
                description="Click Test Button",
                window_title="Test App",
                annotated_image_bytes=webp_data,
                raw_image_bytes=webp_data,
                image_mime_type="image/webp"
            )

            metadata = SessionMetadata(
                session_id="rec_webp_export_test",
                title="WebP SOP Report"
            )

            results = exporter.export([step], metadata, tmpdir)
            self.assertTrue(os.path.exists(results["html"]))
            self.assertTrue(os.path.exists(results["markdown"]))

            # Verify exported image file is .webp
            images_dir = os.path.join(tmpdir, "images")
            webp_file = os.path.join(images_dir, "step_001_left_click.webp")
            raw_webp_file = os.path.join(images_dir, "raw_step_001_left_click.webp")
            self.assertTrue(os.path.exists(webp_file))
            self.assertTrue(os.path.exists(raw_webp_file))

            # Verify HTML contains data:image/webp;base64, and loading="lazy" decoding="async"
            with open(results["html"], "r", encoding="utf-8") as f:
                html = f.read()
                self.assertIn("data:image/webp;base64,", html)
                self.assertIn('loading="lazy"', html)
                self.assertIn('decoding="async"', html)

            # Verify Markdown links to .webp
            with open(results["markdown"], "r", encoding="utf-8") as f:
                md = f.read()
                self.assertIn("step_001_left_click.webp", md)

            capture.close()

    def test_all_type_hints_resolved(self):
        """Verify all functions and methods across the package have valid, resolvable type annotations (catches missing typing imports like Any on Python 3.10-3.13)."""
        import importlib
        import pkgutil
        import typing
        import inspect
        import step_recorder

        errors = []
        for modinfo in pkgutil.walk_packages(step_recorder.__path__, 'step_recorder.'):
            mod = importlib.import_module(modinfo.name)
            for name, obj in inspect.getmembers(mod):
                if inspect.isfunction(obj):
                    try:
                        typing.get_type_hints(obj)
                    except Exception as e:
                        errors.append(f"{modinfo.name}.{name}: {e}")
                elif inspect.isclass(obj) and obj.__module__ == mod.__name__:
                    for m_name, m_obj in inspect.getmembers(obj, inspect.isfunction):
                        try:
                            typing.get_type_hints(m_obj)
                        except Exception as e:
                            errors.append(f"{modinfo.name}.{obj.__name__}.{m_name}: {e}")

        self.assertEqual(errors, [], f"Found unresolved type annotations: {errors}")


if __name__ == "__main__":
    unittest.main()

