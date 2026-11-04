"""
Command-line interface for Step Recorder.
Supports both GUI mode and headless/terminal recording mode.
"""

import sys
import time
import argparse
from pathlib import Path

from .config import RecorderConfig
from .recorder import RecordingEngine
from .exporter import ReportExporter


def main():
    parser = argparse.ArgumentParser(
        description="Python Step Recorder - Modern Problem Steps Recorder alternative"
    )
    parser.add_argument(
        "--cli",
        action="store_true",
        help="Run in headless terminal mode without Tkinter GUI"
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default=None,
        help="Output directory to save recording"
    )
    parser.add_argument(
        "--title", "-t",
        type=str,
        default="Problem Steps Recording",
        help="Session title"
    )
    parser.add_argument(
        "--max-steps", "-m",
        type=int,
        default=None,
        help="Maximum number of steps before stopping"
    )

    args = parser.parse_args()

    config = RecorderConfig.load()
    if args.output:
        config.output_dir = args.output
    if args.max_steps:
        config.max_steps = args.max_steps

    if args.cli:
        run_cli_mode(config, args.title)
    else:
        run_gui_mode(config)


def run_gui_mode(config: RecorderConfig):
    from .ui.main_window import MainWindow
    app = MainWindow()
    app.config = config
    app.run()


def run_cli_mode(config: RecorderConfig, title: str):
    print("=" * 60)
    print(f"🎬 Python Step Recorder (CLI Mode)")
    print(f"Title: {title}")
    print(f"Output: {config.output_dir}")
    print("=" * 60)
    print("Instructions:")
    print(" - Clicks and actions will be automatically recorded.")
    print(" - Press Enter in this terminal at any time to STOP recording.")
    print("=" * 60)

    engine = RecordingEngine(config)
    exporter = ReportExporter(config)

    def on_step(step):
        print(f"  [+] Step {step.step_id}: {step.description}")

    engine.on_step_added = on_step
    engine.start_recording(title=title)

    try:
        input("\n>>> Recording started! Press [Enter] to STOP... <<<\n")
    except KeyboardInterrupt:
        pass

    print("\nStopping recording...")
    engine.stop_recording()

    if not engine.steps:
        print("No steps were captured. Exiting.")
        return

    session_folder = Path(config.output_dir) / engine.metadata.session_id
    session_folder.mkdir(parents=True, exist_ok=True)

    print(f"Exporting {len(engine.steps)} steps to {session_folder}...")
    results = exporter.export(engine.steps, engine.metadata, str(session_folder))

    print("\n✅ Successfully exported:")
    for k, v in results.items():
        print(f"  - {k.upper()}: {v}")
    print("=" * 60)


if __name__ == "__main__":
    main()

