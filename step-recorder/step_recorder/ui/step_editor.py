"""
Interactive Step Reviewer and Editor window.
Allows user to review, edit descriptions, add/edit comments, delete accidental steps,
reorder steps, and adjust highlight/focus regions before exporting.
"""

import io
import os
import sys
import webbrowser
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional, List, Callable, Tuple
from pathlib import Path
from PIL import Image, ImageTk

from ..models import Step, SessionMetadata
from ..annotator import annotate_screenshot
from ..capture import ScreenCapture
from ..config import RecorderConfig
from ..exporter import ReportExporter
from ..window_info import exclude_window_from_capture


class StepEditorWindow:
    """Window for reviewing, editing, reordering, and deleting recorded steps."""

    def __init__(
        self,
        parent: tk.Tk,
        steps: List[Step],
        metadata: SessionMetadata,
        config: RecorderConfig,
        exporter: ReportExporter,
        on_export_complete: Optional[Callable[[dict], None]] = None
    ):
        self.parent = parent
        self.steps = list(steps)  # copy
        self.metadata = metadata
        self.config = config
        self.exporter = exporter
        self.on_export_complete = on_export_complete

        self.current_index = 0 if self.steps else -1
        self.preview_photo = None
        self.drag_start_x = 0
        self.drag_start_y = 0
        self.preview_scale_x = 1.0
        self.preview_scale_y = 1.0
        self.new_highlight_rect = None

        self.window = tk.Toplevel(parent)
        self.window.title("Step Recorder - Review & Edit Steps (Chỉnh sửa / Xóa bước)")
        self.window.attributes("-topmost", True)
        self.window.configure(bg="#0f172a")

        # Set spacious comfortable geometry
        self.window.geometry("1000x680+60+40")
        self.window.minsize(850, 580)

        self._build_ui()
        self._populate_list()
        if self.steps:
            self._select_step(0)

        self.window.after(50, lambda: exclude_window_from_capture(self.window))
        self.window.focus_force()

    def _build_ui(self) -> None:
        main_frame = tk.Frame(self.window, bg="#0f172a", padx=12, pady=12)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Top Header
        header_frame = tk.Frame(main_frame, bg="#0f172a")
        header_frame.pack(fill=tk.X, pady=(0, 10))

        title_lbl = tk.Label(
            header_frame,
            text="📋 Review & Edit Steps (Chỉnh sửa & Xóa bước ghi hình)",
            font=("Segoe UI", 13, "bold"),
            bg="#0f172a",
            fg="#f8fafc"
        )
        title_lbl.pack(side=tk.LEFT)

        self.total_lbl = tk.Label(
            header_frame,
            text=f"Tổng số: {len(self.steps)} bước",
            font=("Segoe UI", 10),
            bg="#0f172a",
            fg="#94a3b8"
        )
        self.total_lbl.pack(side=tk.RIGHT)

        # Split content: Left list, Right editor
        content_frame = tk.Frame(main_frame, bg="#0f172a")
        content_frame.pack(fill=tk.BOTH, expand=True)
        content_frame.columnconfigure(0, weight=4)  # Left list
        content_frame.columnconfigure(1, weight=7)  # Right editor
        content_frame.rowconfigure(0, weight=1)

        # === LEFT COLUMN: Step List ===
        left_frame = tk.Frame(content_frame, bg="#1e293b", padx=10, pady=10)
        left_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        list_header = tk.Label(
            left_frame, text="Danh sách các bước:",
            font=("Segoe UI", 10, "bold"), bg="#1e293b", fg="#cbd5e1"
        )
        list_header.pack(anchor="w", pady=(0, 6))

        # Listbox with scrollbar
        list_container = tk.Frame(left_frame, bg="#1e293b")
        list_container.pack(fill=tk.BOTH, expand=True)

        scrollbar = tk.Scrollbar(list_container, orient=tk.VERTICAL)
        self.step_listbox = tk.Listbox(
            list_container,
            yscrollcommand=scrollbar.set,
            bg="#0f172a",
            fg="#f8fafc",
            selectbackground="#0284c7",
            selectforeground="#ffffff",
            font=("Segoe UI", 9),
            relief=tk.FLAT,
            activestyle="none",
            highlightthickness=1,
            highlightcolor="#38bdf8"
        )
        scrollbar.config(command=self.step_listbox.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.step_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.step_listbox.bind("<<ListboxSelect>>", self._on_list_select)

        # List Action Buttons (Delete, Move Up, Move Down)
        list_btn_frame = tk.Frame(left_frame, bg="#1e293b")
        list_btn_frame.pack(fill=tk.X, pady=(8, 0))

        del_btn = tk.Button(
            list_btn_frame,
            text="🗑️ Xóa Step",
            command=self._delete_current_step,
            bg="#dc2626", fg="#ffffff",
            activebackground="#ef4444",
            font=("Segoe UI", 9, "bold"),
            relief=tk.FLAT, padx=8, pady=4, cursor="hand2"
        )
        del_btn.pack(side=tk.LEFT, padx=(0, 4))

        up_btn = tk.Button(
            list_btn_frame,
            text="⬆️ Lên",
            command=self._move_step_up,
            bg="#334155", fg="#f8fafc",
            font=("Segoe UI", 9),
            relief=tk.FLAT, padx=8, pady=4, cursor="hand2"
        )
        up_btn.pack(side=tk.LEFT, padx=(0, 4))

        down_btn = tk.Button(
            list_btn_frame,
            text="⬇️ Xuống",
            command=self._move_step_down,
            bg="#334155", fg="#f8fafc",
            font=("Segoe UI", 9),
            relief=tk.FLAT, padx=8, pady=4, cursor="hand2"
        )
        down_btn.pack(side=tk.LEFT)

        # === RIGHT COLUMN: Step Editor & Preview ===
        right_frame = tk.Frame(content_frame, bg="#1e293b", padx=12, pady=10)
        right_frame.grid(row=0, column=1, sticky="nsew")

        # Step meta header
        self.step_header_lbl = tk.Label(
            right_frame,
            text="Chi tiết bước:",
            font=("Segoe UI", 11, "bold"),
            bg="#1e293b", fg="#38bdf8"
        )
        self.step_header_lbl.pack(anchor="w", pady=(0, 4))

        # Description Edit
        desc_lbl = tk.Label(
            right_frame, text="Mô tả hành động (Description):",
            font=("Segoe UI", 9, "bold"), bg="#1e293b", fg="#cbd5e1"
        )
        desc_lbl.pack(anchor="w", pady=(4, 2))

        self.desc_var = tk.StringVar()
        self.desc_entry = tk.Entry(
            right_frame,
            textvariable=self.desc_var,
            bg="#0f172a", fg="#f8fafc",
            insertbackground="#38bdf8",
            font=("Segoe UI", 9), relief=tk.FLAT
        )
        self.desc_entry.pack(fill=tk.X, ipady=4, pady=(0, 6))

        # Comment Edit
        comment_lbl = tk.Label(
            right_frame, text="Ghi chú / Lưu ý lỗi (User Comment):",
            font=("Segoe UI", 9, "bold"), bg="#1e293b", fg="#cbd5e1"
        )
        comment_lbl.pack(anchor="w", pady=(2, 2))

        self.comment_var = tk.StringVar()
        self.comment_entry = tk.Entry(
            right_frame,
            textvariable=self.comment_var,
            bg="#0f172a", fg="#f8fafc",
            insertbackground="#38bdf8",
            font=("Segoe UI", 9), relief=tk.FLAT
        )
        self.comment_entry.pack(fill=tk.X, ipady=4, pady=(0, 8))

        # Screenshot Preview Area with Canvas
        prev_lbl_frame = tk.Frame(right_frame, bg="#1e293b")
        prev_lbl_frame.pack(fill=tk.X, pady=(2, 4))

        preview_title = tk.Label(
            prev_lbl_frame, text="Ảnh chụp màn hình (Kéo chuột trên ảnh để vẽ Focus/Highlight):",
            font=("Segoe UI", 8, "bold"), bg="#1e293b", fg="#94a3b8"
        )
        preview_title.pack(side=tk.LEFT)

        reset_marker_btn = tk.Button(
            prev_lbl_frame,
            text="↺ Reset Highlight",
            command=self._reset_highlight,
            bg="#334155", fg="#cbd5e1",
            font=("Segoe UI", 8),
            relief=tk.FLAT, padx=6, pady=1, cursor="hand2"
        )
        reset_marker_btn.pack(side=tk.RIGHT)

        self.preview_canvas = tk.Canvas(
            right_frame,
            bg="#000000",
            highlightthickness=1,
            highlightbackground="#334155",
            cursor="cross"
        )
        self.preview_canvas.pack(fill=tk.BOTH, expand=True, pady=(0, 8))
        self.preview_canvas.bind("<ButtonPress-1>", self._on_canvas_press)
        self.preview_canvas.bind("<B1-Motion>", self._on_canvas_drag)
        self.preview_canvas.bind("<ButtonRelease-1>", self._on_canvas_release)

        # Apply edit button
        update_step_btn = tk.Button(
            right_frame,
            text="✓ Cập nhật thay đổi cho bước này",
            command=self._apply_current_step_edits,
            bg="#0284c7", fg="#ffffff",
            font=("Segoe UI", 9, "bold"),
            relief=tk.FLAT, padx=12, pady=5, cursor="hand2"
        )
        update_step_btn.pack(anchor="e")

        # === BOTTOM ACTION BAR ===
        bottom_bar = tk.Frame(main_frame, bg="#0f172a")
        bottom_bar.pack(fill=tk.X, pady=(12, 0))

        cancel_btn = tk.Button(
            bottom_bar,
            text="✕ Đóng",
            command=self.window.destroy,
            bg="#334155", fg="#f8fafc",
            font=("Segoe UI", 9),
            relief=tk.FLAT, padx=14, pady=6, cursor="hand2"
        )
        cancel_btn.pack(side=tk.RIGHT, padx=(8, 0))

        export_btn = tk.Button(
            bottom_bar,
            text="💾 Lưu & Xuất Báo Cáo (Export Report)",
            command=self._export_final_report,
            bg="#059669", fg="#ffffff",
            activebackground="#10b981",
            font=("Segoe UI", 10, "bold"),
            relief=tk.FLAT, padx=18, pady=6, cursor="hand2"
        )
        export_btn.pack(side=tk.RIGHT)

    # --- Step List Management ---
    def _populate_list(self) -> None:
        """Refresh Listbox items with current steps."""
        self.step_listbox.delete(0, tk.END)
        for s in self.steps:
            icon = s.action_icon
            desc_short = (s.description[:42] + "...") if len(s.description) > 42 else s.description
            comment_tag = " [💬]" if s.user_comment else ""
            self.step_listbox.insert(tk.END, f"#{s.step_id} {icon} {desc_short}{comment_tag}")

        self.total_lbl.configure(text=f"Tổng số: {len(self.steps)} bước")

    def _on_list_select(self, event=None) -> None:
        selected = self.step_listbox.curselection()
        if selected:
            idx = selected[0]
            self._select_step(idx)

    def _select_step(self, index: int) -> None:
        if index < 0 or index >= len(self.steps):
            return

        self.current_index = index
        step = self.steps[index]

        # Update fields
        self.step_header_lbl.configure(
            text=f"Bước #{step.step_id} - {step.action_type.replace('_', ' ').title()} ({step.time_str})"
        )
        self.desc_var.set(step.description)
        self.comment_var.set(step.user_comment or "")

        # Highlight in listbox
        self.step_listbox.selection_clear(0, tk.END)
        self.step_listbox.selection_set(index)
        self.step_listbox.activate(index)

        # Render preview image
        self._render_step_preview(step)

    def _render_step_preview(self, step: Step) -> None:
        """Render screenshot of step inside the preview canvas."""
        self.preview_canvas.delete("all")

        # Load image bytes
        img_bytes = step.annotated_image_bytes
        if not img_bytes and step.annotated_image_path and os.path.exists(step.annotated_image_path):
            with open(step.annotated_image_path, "rb") as f:
                img_bytes = f.read()

        if not img_bytes:
            self.preview_canvas.create_text(
                200, 100, text="Không có ảnh chụp màn hình",
                fill="#94a3b8", font=("Segoe UI", 10)
            )
            return

        try:
            pil_img = Image.open(io.BytesIO(img_bytes))
            self.active_raw_pil = pil_img.copy()

            # Scale to fit canvas
            self.window.update_idletasks()
            cw = max(200, self.preview_canvas.winfo_width())
            ch = max(150, self.preview_canvas.winfo_height())

            orig_w, orig_h = pil_img.size
            ratio = min(cw / orig_w, ch / orig_h)
            disp_w = int(orig_w * ratio)
            disp_h = int(orig_h * ratio)

            self.preview_scale_x = orig_w / disp_w
            self.preview_scale_y = orig_h / disp_h

            scaled_img = pil_img.resize((disp_w, disp_h), Image.Resampling.LANCZOS)
            self.preview_photo = ImageTk.PhotoImage(scaled_img)

            # Center on canvas
            offset_x = (cw - disp_w) // 2
            offset_y = (ch - disp_h) // 2
            self.canvas_img_offset = (offset_x, offset_y)

            self.preview_canvas.create_image(
                offset_x, offset_y, image=self.preview_photo, anchor="nw"
            )
        except Exception as e:
            self.preview_canvas.create_text(
                200, 100, text=f"Lỗi hiển thị ảnh: {e}",
                fill="#ef4444", font=("Segoe UI", 9)
            )

    # --- Interactive Highlighting on Preview Canvas ---
    def _on_canvas_press(self, event) -> None:
        self.drag_start_x = event.x
        self.drag_start_y = event.y

    def _on_canvas_drag(self, event) -> None:
        self.preview_canvas.delete("highlight_box")
        self.preview_canvas.create_rectangle(
            self.drag_start_x, self.drag_start_y, event.x, event.y,
            outline="#38bdf8", width=2, dash=(4, 2), tags="highlight_box"
        )

    def _on_canvas_release(self, event) -> None:
        ox, oy = getattr(self, "canvas_img_offset", (0, 0))

        # Map canvas coordinates back to original full screenshot coordinates
        x1 = int((min(self.drag_start_x, event.x) - ox) * self.preview_scale_x)
        y1 = int((min(self.drag_start_y, event.y) - oy) * self.preview_scale_y)
        x2 = int((max(self.drag_start_x, event.x) - ox) * self.preview_scale_x)
        y2 = int((max(self.drag_start_y, event.y) - oy) * self.preview_scale_y)

        if (x2 - x1) > 15 and (y2 - y1) > 15 and 0 <= self.current_index < len(self.steps):
            step = self.steps[self.current_index]
            self.new_highlight_rect = (x1, y1, x2, y2)
            step.highlight_rect = self.new_highlight_rect

            # Re-render annotation on raw image if available
            base_bytes = step.raw_image_bytes or step.annotated_image_bytes
            if base_bytes:
                base_img = Image.open(io.BytesIO(base_bytes))
                annotated = annotate_screenshot(
                    base_img,
                    cursor_pos=(step.cursor_x, step.cursor_y) if step.cursor_x is not None else None,
                    step_id=step.step_id,
                    highlight_rect=self.new_highlight_rect,
                    color_hex=self.config.highlight_color,
                    style=self.config.highlight_style
                )
                step.annotated_image_bytes = ScreenCapture.image_to_bytes(annotated)
                step.thumbnail_bytes = ScreenCapture.image_to_bytes(ScreenCapture.create_thumbnail(annotated))
                self._render_step_preview(step)

    def _reset_highlight(self) -> None:
        """Reset highlight back to original or click marker."""
        if 0 <= self.current_index < len(self.steps):
            step = self.steps[self.current_index]
            step.highlight_rect = None
            if step.raw_image_bytes:
                base_img = Image.open(io.BytesIO(step.raw_image_bytes))
                annotated = annotate_screenshot(
                    base_img,
                    cursor_pos=(step.cursor_x, step.cursor_y) if step.cursor_x is not None else None,
                    step_id=step.step_id,
                    highlight_rect=None,
                    color_hex=self.config.highlight_color,
                    style=self.config.highlight_style
                )
                step.annotated_image_bytes = ScreenCapture.image_to_bytes(annotated)
                step.thumbnail_bytes = ScreenCapture.image_to_bytes(ScreenCapture.create_thumbnail(annotated))
                self._render_step_preview(step)

    # --- Edit, Delete, and Reorder Actions ---
    def _apply_current_step_edits(self) -> None:
        """Save text description and comment changes for selected step."""
        if 0 <= self.current_index < len(self.steps):
            step = self.steps[self.current_index]
            step.description = self.desc_var.get().strip() or step.description
            step.user_comment = self.comment_var.get().strip() or None

            # Refresh list item text
            self._populate_list()
            self.step_listbox.selection_set(self.current_index)
            messagebox.showinfo("Đã cập nhật", f"Đã lưu thay đổi cho Bước #{step.step_id}!")

    def _delete_current_step(self) -> None:
        """Delete currently selected step and renumber remaining steps."""
        if not self.steps or self.current_index < 0 or self.current_index >= len(self.steps):
            return

        del_id = self.steps[self.current_index].step_id
        if messagebox.askyesno("Xóa bước", f"Bạn có chắc muốn xóa Bước #{del_id} không?"):
            self.steps.pop(self.current_index)

            # Renumber remaining steps smoothly #1, #2, #3...
            for i, s in enumerate(self.steps):
                s.step_id = i + 1

            self._populate_list()

            if self.steps:
                new_idx = min(self.current_index, len(self.steps) - 1)
                self._select_step(new_idx)
            else:
                self.current_index = -1
                self.desc_var.set("")
                self.comment_var.set("")
                self.preview_canvas.delete("all")
                self.step_header_lbl.configure(text="Không còn bước nào.")

    def _move_step_up(self) -> None:
        """Move selected step up in sequence."""
        idx = self.current_index
        if idx > 0:
            self.steps[idx - 1], self.steps[idx] = self.steps[idx], self.steps[idx - 1]
            # Renumber
            for i, s in enumerate(self.steps):
                s.step_id = i + 1
            self._populate_list()
            self._select_step(idx - 1)

    def _move_step_down(self) -> None:
        """Move selected step down in sequence."""
        idx = self.current_index
        if idx >= 0 and idx < len(self.steps) - 1:
            self.steps[idx + 1], self.steps[idx] = self.steps[idx], self.steps[idx + 1]
            # Renumber
            for i, s in enumerate(self.steps):
                s.step_id = i + 1
            self._populate_list()
            self._select_step(idx + 1)

    # --- Final Export ---
    def _export_final_report(self) -> None:
        """Export edited steps into HTML, Markdown, and ZIP archive."""
        if not self.steps:
            messagebox.showwarning("Cảnh báo", "Không có bước nào để xuất báo cáo!")
            return

        # Ensure current active inputs are applied
        if 0 <= self.current_index < len(self.steps):
            cur = self.steps[self.current_index]
            cur.description = self.desc_var.get().strip() or cur.description
            cur.user_comment = self.comment_var.get().strip() or None

        session_folder = Path(self.config.output_dir) / self.metadata.session_id
        session_folder.mkdir(parents=True, exist_ok=True)

        self.metadata.total_steps = len(self.steps)

        results = self.exporter.export(
            steps=self.steps,
            metadata=self.metadata,
            output_dir=str(session_folder)
        )

        html_path = results.get("html")
        if html_path:
            try:
                webbrowser.open(f"file://{os.path.abspath(html_path)}")
            except Exception:
                pass

        if self.on_export_complete:
            self.on_export_complete(results)

        msg = (
            f"✅ Xuất báo cáo thành công!\n\n"
            f"Tổng số bước: {len(self.steps)}\n"
            f"Thời gian: {self.metadata.duration_str}\n"
            f"Thư mục lưu: {session_folder}\n\n"
            f"Bạn có muốn mở thư mục chứa báo cáo không?"
        )
        if messagebox.askyesno("Thành công", msg):
            self._open_folder(str(session_folder))

        self.window.destroy()

    def _open_folder(self, path: str) -> None:
        try:
            if sys.platform == "win32":
                os.startfile(path)
            elif sys.platform == "darwin":
                import subprocess
                subprocess.run(["open", path])
            else:
                import subprocess
                subprocess.run(["xdg-open", path])
        except Exception:
            pass

