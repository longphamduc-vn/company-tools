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

        # 1. Save individual PNG image files if requested or if images are in memory
        for step in steps:
            img_filename = f"step_{step.step_id:03d}_{step.action_type}.png"
            dest_img_path = images_dir / img_filename

            if step.annotated_image_bytes and not step.annotated_image_path:
                with open(dest_img_path, "wb") as f:
                    f.write(step.annotated_image_bytes)
                step.annotated_image_path = str(dest_img_path)

        # 2. Render & Save HTML Report
        template = self.jinja_env.get_template("report_template.html")
        html_content = template.render(
            session=metadata,
            steps=steps,
            config=self.config
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
                for img_file in images_dir.glob("*.png"):
                    zf.write(img_file, arcname=f"images/{img_file.name}")
            results["zip"] = str(zip_file)

        return results

    def _generate_markdown(self, steps: List[Step], metadata: SessionMetadata) -> str:
        """Generate a GitHub/GitLab-friendly Markdown summary."""
        lines = [
            f"# 📋 {metadata.title}",
            "",
            f"> **Date**: {metadata.start_time.strftime('%Y-%m-%d %H:%M')} | "
            f"**Duration**: {metadata.duration_str} | "
            f"**Total Steps**: {len(steps)} | "
            f"**OS**: {metadata.os_name}",
            "",
        ]

        if metadata.description:
            lines.append(f"{metadata.description}")
            lines.append("")

        lines.append("## 📌 Recorded Steps")
        lines.append("")

        for step in steps:
            lines.append(f"### Step {step.step_id}: {step.action_type.replace('_', ' ').title()}")
            lines.append(f"- **Time**: `{step.time_str}`")
            lines.append(f"- **Window**: `{step.window_title}` (`{step.process_name}`)")
            if step.cursor_x is not None and step.cursor_y is not None:
                lines.append(f"- **Coordinates**: `({step.cursor_x}, {step.cursor_y})`")
            lines.append(f"- **Action**: {step.description}")

            if step.user_comment:
                lines.append(f"\n> 💬 **User Comment**: {step.user_comment}\n")

            if step.annotated_image_path:
                rel_img_path = f"images/{os.path.basename(step.annotated_image_path)}"
                lines.append(f"\n![Step {step.step_id}]({rel_img_path})\n")

            lines.append("---")
            lines.append("")

        return "\n".join(lines)

