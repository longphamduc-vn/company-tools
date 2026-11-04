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
from step_recorder.window_info import get_active_window_info
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


if __name__ == "__main__":
    unittest.main()

