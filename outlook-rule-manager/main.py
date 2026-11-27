"""Main entry point for Outlook Rule Companion."""
import os
import sys
import argparse

# Ensure outlook-rule-manager root is in sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from gui.main_window import MainWindow


def parse_args():
    parser = argparse.ArgumentParser(description="Outlook Rule Companion & Automation Assistant")
    parser.add_argument(
        "--config",
        default=os.path.join(BASE_DIR, "config", "rules.yaml"),
        help="Path to rules.yaml configuration file"
    )
    return parser.parse_args()


def main():
    args = parse_args()
    config_file = os.path.abspath(args.config)

    if not os.path.exists(config_file):
        print(f"Error: Configuration file not found at {config_file}")
        sys.exit(1)

    # Check the file first: a hand-edit mistake must give a clear message, not a window that closes
    from core.yaml_manager import YamlConfigManager
    try:
        YamlConfigManager(config_file)
    except ValueError as exc:
        show_config_error(config_file, exc)
        sys.exit(1)

    app = MainWindow(config_path=config_file)
    app.mainloop()


def show_config_error(config_file: str, exc: Exception) -> None:
    message = f"{config_file}\n\n{exc}\n\nFix the file (or restore a copy from config/backups) and start again."
    print(f"Error: {message}")
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("rules.yaml has an error", message, parent=root)
        root.destroy()
    except Exception:
        pass


if __name__ == "__main__":
    main()

