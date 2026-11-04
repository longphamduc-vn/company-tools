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
from step_recorder.annotator import annotate_screenshot, hex_to_rgba
from step_recorder.capture import ScreenCapture
from step_recorder.window_info import get_active_window_info
from step_recorder.exporter import ReportExporter
from step_recorder.recorder import RecordingEngine


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
                create_zip_package=True
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


if __name__ == "__main__":
    unittest.main()

