"""
Report exporter: Generates self-contained HTML reports, Markdown summaries,
JSON metadata, and ZIP packages.
"""

import os
import json
import zipfile
from pathlib import Path
from typing import List
from jinja2 import Environment, FileSystemLoader

from .models import Step, SessionMetadata
from .config import RecorderConfig
from .ui.icon_utils import get_favicon_base64


class ReportExporter:
    """Exports recorded sessions into various document formats."""

    def __init__(self, config: RecorderConfig):
        self.config = config
        template_dir = Path(__file__).parent / "templates"
        self.jinja_env = Environment(
            loader=FileSystemLoader(str(template_dir)),
            autoescape=True
        )

    def export(
        self,
        steps: List[Step],
        metadata: SessionMetadata,
        output_dir: str
    ) -> dict:
        """
        Export recording session to disk according to config.
        Returns a dict of created file paths.
        """
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        images_dir = out_path / "images"
        images_dir.mkdir(parents=True, exist_ok=True)

        results = {}

        # 1. Save individual image files (WebP or PNG based on config)
        fmt = getattr(self.config, "image_format", "WEBP").upper()
        ext = "webp" if fmt == "WEBP" else "png"
        for step in steps:
            img_filename = f"step_{step.step_id:03d}_{step.action_type}.{ext}"
            dest_img_path = images_dir / img_filename

            if not step.annotated_image_path or not os.path.exists(step.annotated_image_path):
                ann_data = step.get_annotated_bytes()
                if ann_data:
                    with open(dest_img_path, "wb") as f:
                        f.write(ann_data)
                    step.annotated_image_path = str(dest_img_path)

            if getattr(self.config, "save_raw_screenshots", True):
                raw_filename = f"raw_step_{step.step_id:03d}_{step.action_type}.{ext}"
                raw_dest_path = images_dir / raw_filename
                if not step.raw_image_path or not os.path.exists(step.raw_image_path):
                    raw_data = step.get_raw_bytes()
                    if raw_data:
                        with open(raw_dest_path, "wb") as f:
                            f.write(raw_data)
                        step.raw_image_path = str(raw_dest_path)

        # 2. Render & Save HTML Report
        is_vi = getattr(self.config, "language", "vi") == "vi"
        sections = self._group_sections(steps, is_vi=is_vi)

        template = self.jinja_env.get_template("report_template.html")
        html_content = template.render(
            session=metadata,
            steps=steps,
            sections=sections,
            config=self.config,
            favicon_base64=get_favicon_base64()
        )
        html_file = out_path / "report.html"
        with open(html_file, "w", encoding="utf-8") as f:
            f.write(html_content)
        results["html"] = str(html_file)

        # 3. Generate Markdown Report
        md_file = out_path / "report.md"
        md_content = self._generate_markdown(steps, metadata)
        with open(md_file, "w", encoding="utf-8") as f:
            f.write(md_content)
        results["markdown"] = str(md_file)

        # 4. Save JSON metadata
        json_file = out_path / "session.json"
        json_data = {
            "session": {
                "id": metadata.session_id,
                "title": metadata.title,
                "description": metadata.description,
                "start_time": metadata.start_time.isoformat(),
                "end_time": metadata.end_time.isoformat() if metadata.end_time else None,
                "duration": metadata.duration_str,
                "os": metadata.os_name,
                "screen_resolution": metadata.screen_resolution,
                "total_steps": len(steps),
                "apps_used": metadata.apps_used,
            },
            "steps": [s.to_dict() for s in steps]
        }
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(json_data, f, indent=2, ensure_ascii=False)
        results["json"] = str(json_file)

        # 5. Create ZIP Package if enabled
        if self.config.create_zip_package:
            zip_file = out_path / f"{metadata.session_id}.zip"
            with zipfile.ZipFile(zip_file, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                zf.write(html_file, arcname="report.html")
                zf.write(md_file, arcname="report.md")
                zf.write(json_file, arcname="session.json")
                for img_file in list(images_dir.glob("*.png")) + list(images_dir.glob("*.webp")):
                    zf.write(img_file, arcname=f"images/{img_file.name}")
            results["zip"] = str(zip_file)

        return results

    def _group_sections(self, steps: List[Step], is_vi: bool = True) -> List[dict]:
        """Group steps into chapters/sections for TOC generation."""
        sections = []
        if not steps:
            return sections

        has_custom = any(s.is_section_header for s in steps)
        if not has_custom:
            sections.append({
                "index": 1,
                "title": "Tổng quan các bước" if is_vi else "All Recorded Steps",
                "description": "",
                "first_step_id": steps[0].step_id,
                "steps": steps,
            })
            return sections

        sec_idx = 0
        current_sec = None
        for step in steps:
            if step.is_section_header:
                sec_idx += 1
                current_sec = {
                    "index": sec_idx,
                    "title": step.section_title or (f"Phần {sec_idx}" if is_vi else f"Section {sec_idx}"),
                    "description": step.section_description or "",
                    "first_step_id": step.step_id,
                    "steps": [step],
                }
                sections.append(current_sec)
            else:
                if current_sec is None:
                    sec_idx += 1
                    current_sec = {
                        "index": sec_idx,
                        "title": "Khởi đầu & Chuẩn bị" if is_vi else "Initial & Preparation",
                        "description": "",
                        "first_step_id": step.step_id,
                        "steps": [step],
                    }
                    sections.append(current_sec)
                else:
                    current_sec["steps"].append(step)
        return sections

    def _generate_markdown(self, steps: List[Step], metadata: SessionMetadata) -> str:
        """Generate a GitHub/GitLab-friendly Markdown summary in active language with TOC."""
        is_vi = getattr(self.config, "language", "vi") == "vi"
        sections = self._group_sections(steps, is_vi=is_vi)
        has_custom_sections = any(s.is_section_header for s in steps)

        title_steps = "Các Bước Đã Ghi Hình" if is_vi else "Recorded Steps"
        lbl_date = "Ngày" if is_vi else "Date"
        lbl_duration = "Thời lượng" if is_vi else "Duration"
        lbl_total = "Tổng số bước" if is_vi else "Total Steps"
        lbl_time = "Thời điểm" if is_vi else "Time"
        lbl_window = "Cửa sổ" if is_vi else "Window"
        lbl_coords = "Tọa độ" if is_vi else "Coordinates"
        lbl_action = "Thao tác" if is_vi else "Action"
        lbl_note = "Ghi chú người dùng" if is_vi else "User Comment"
        step_word = "Bước" if is_vi else "Step"
        toc_title = "Mục Lục Hướng Dẫn" if is_vi else "Table of Contents"

        lines = [
            f"# 📋 {metadata.title}",
            "",
            f"> **{lbl_date}**: {metadata.start_time.strftime('%Y-%m-%d %H:%M')} | "
            f"**{lbl_duration}**: {metadata.duration_str} | "
            f"**{lbl_total}**: {len(steps)} | "
            f"**OS**: {metadata.os_name}",
            "",
        ]

        if metadata.description:
            lines.append(f"{metadata.description}")
            lines.append("")

        # Generate Table of Contents
        if len(steps) > 0:
            lines.append(f"## 📑 {toc_title}")
            lines.append("")
            if has_custom_sections:
                for sec in sections:
                    anchor_sec = f"section-{sec['first_step_id']}"
                    lines.append(f"- [**{sec['title']}**](#{anchor_sec}) ({len(sec['steps'])} {step_word.lower()})")
                    for s in sec["steps"]:
                        anchor_step = f"step-{s.step_id}"
                        s_desc = (s.description[:45] + "...") if len(s.description) > 45 else s.description
                        badge_str = " `[🔀 Y/N]`" if s.is_decision_point else ""
                        lines.append(f"  - [{step_word} {s.step_id}: {s_desc}](#{anchor_step}){badge_str}")
            else:
                for s in steps:
                    anchor_step = f"step-{s.step_id}"
                    s_desc = (s.description[:45] + "...") if len(s.description) > 45 else s.description
                    badge_str = " `[🔀 Y/N]`" if s.is_decision_point else ""
                    lines.append(f"- [{step_word} {s.step_id}: {s_desc}](#{anchor_step}){badge_str}")
            lines.append("")

        lines.append(f"## 📌 {title_steps}")
        lines.append("")

        sec_counter = 0
        for step in steps:
            if step.is_section_header:
                sec_counter += 1
                sec_title = step.section_title or (f"Phần {sec_counter}" if is_vi else f"Section {sec_counter}")
                lines.append(f"<a id=\"section-{step.step_id}\"></a>")
                lines.append("---")
                lines.append(f"## 📑 {sec_title}")
                if step.section_description:
                    lines.append(f"> 🎯 **Mục tiêu**: {step.section_description}\n")
                lines.append("")

            lines.append(f"<a id=\"step-{step.step_id}\"></a>")
            lines.append(f"### {step_word} {step.step_id}: {step.action_type.replace('_', ' ').title()}")
            lines.append(f"- **{lbl_time}**: `{step.time_str}`")
            lines.append(f"- **{lbl_window}**: `{step.window_title}` (`{step.process_name}`)")
            if step.cursor_x is not None and step.cursor_y is not None:
                lines.append(f"- **{lbl_coords}**: `({step.cursor_x}, {step.cursor_y})`")
            if step.drag_start and step.drag_end:
                drag_lbl = "Quỹ đạo Kéo Thả" if is_vi else "Drag Trajectory"
                lines.append(f"- **{drag_lbl}**: `({step.drag_start[0]}, {step.drag_start[1]}) ➔ ({step.drag_end[0]}, {step.drag_end[1]})`")
            lines.append(f"- **{lbl_action}**: {step.description}")

            if step.user_comment:
                lines.append(f"\n> 💬 **{lbl_note}**: {step.user_comment}\n")

            if step.is_decision_point:
                lines.append("")
                dp_title = "ĐIỂM RẼ NHÁNH ĐIỀU KIỆN (YES / NO)" if is_vi else "CONDITIONAL DECISION POINT (YES / NO)"
                lines.append(f"> 🔀 **{dp_title}**")
                if step.condition_question:
                    q_label = "Câu hỏi điều kiện" if is_vi else "Condition Question"
                    lines.append(f"> **{q_label}**: *{step.condition_question}*")
                lines.append(">")
                yes_txt = step.yes_branch_text or ("Tiếp tục thực hiện bước tiếp theo" if is_vi else "Continue to next step")
                if step.yes_next_step:
                    lines.append(f"> - ✅ **YES / ĐÚNG**: {yes_txt} ➔ [**{step_word} {step.yes_next_step}**](#step-{step.yes_next_step})")
                else:
                    lines.append(f"> - ✅ **YES / ĐÚNG**: {yes_txt}")
                no_txt = step.no_branch_text or ("Xử lý ngoại lệ hoặc dừng quy trình" if is_vi else "Handle exception or stop workflow")
                if step.no_next_step:
                    lines.append(f"> - ❌ **NO / SAI**: {no_txt} ➔ [**{step_word} {step.no_next_step}**](#step-{step.no_next_step})")
                else:
                    lines.append(f"> - ❌ **NO / SAI**: {no_txt}")
                lines.append("")

            if step.annotated_image_path:
                rel_img_path = f"images/{os.path.basename(step.annotated_image_path)}"
                lines.append(f"\n![{step_word} {step.step_id}]({rel_img_path})\n")

            lines.append("---")
            lines.append("")

        return "\n".join(lines)

