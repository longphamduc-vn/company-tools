"""
AI Copilot & SOP Intelligence for Python Step Recorder.
Provides automated natural SOP action phrasing, auto-chaptering,
executive summary generation, and prerequisites drafting.
Supports both zero-cost offline Smart Heuristics and Cloud LLMs (Gemini / OpenAI).
"""

import re
import json
import urllib.request
import urllib.error
from typing import List, Tuple, Optional, Dict, Any

from .models import Step, SessionMetadata
from .config import RecorderConfig


class AICopilot:
    """Intelligent Copilot for polishing recording sessions into professional SOPs."""

    def __init__(self, config: Optional[RecorderConfig] = None):
        self.config = config or RecorderConfig()
        self.lang = getattr(self.config, "language", "vi")

    def polish_steps(
        self,
        steps: List[Step],
        metadata: Optional[SessionMetadata] = None
    ) -> Tuple[List[Step], Optional[SessionMetadata]]:
        """
        Polish step descriptions, organize chapters, and generate session summary.
        Uses Cloud LLM if API key is configured, otherwise uses built-in Smart Heuristics.
        """
        if not steps:
            return steps, metadata

        # Try LLM first if configured with API key
        provider = getattr(self.config, "ai_provider", "smart_heuristic")
        api_key = getattr(self.config, "ai_api_key", "").strip()

        if provider in ("gemini", "openai") and api_key:
            try:
                success = self._polish_with_llm(steps, metadata, provider, api_key)
                if success:
                    return steps, metadata
            except Exception as e:
                print(f"[AICopilot] LLM API call error, falling back to Smart Heuristics: {e}")

        # Fallback / Default: Built-in Smart Heuristic Polisher (100% offline, zero-cost)
        self._polish_with_smart_heuristics(steps, metadata)
        return steps, metadata

    def _polish_with_smart_heuristics(
        self,
        steps: List[Step],
        metadata: Optional[SessionMetadata] = None
    ) -> None:
        """Rule-based semantic parser for professional SOP wording, auto-chaptering, and summary."""
        is_vi = self.lang == "vi"

        # 1. Polish individual step descriptions
        for s in steps:
            polished = self._enrich_single_step(s, is_vi)
            s.ai_description = polished
            s.description = polished

        # 2. Auto-chaptering if enabled and no section headers already exist
        if getattr(self.config, "ai_auto_chaptering", True):
            existing_headers = sum(1 for s in steps if s.is_section_header)
            if existing_headers == 0 and len(steps) >= 3:
                self._apply_auto_chapters(steps, is_vi)

        # 3. Generate Executive Summary & Prerequisites
        if metadata and getattr(self.config, "ai_generate_summary", True):
            apps = metadata.apps_used or list({s.process_name for s in steps if s.process_name and s.process_name != "Unknown"})
            apps_str = ", ".join(apps) if apps else ("Các phần mềm nghiệp vụ" if is_vi else "Business Applications")
            total = len(steps)

            if is_vi:
                metadata.executive_summary = (
                    f"Tài liệu quy trình chuẩn (SOP) gồm {total} bước thao tác trên các ứng dụng: {apps_str}. "
                    f"Tài liệu hướng dẫn chi tiết từ giai đoạn thiết lập ban đầu, thao tác dữ liệu nghiệp vụ, "
                    f"đến khi hoàn tất và kiểm tra kết quả."
                )
                metadata.prerequisites = [
                    f"Đã cài đặt, cấu hình và khởi chạy các ứng dụng: {apps_str}.",
                    "Đảm bảo tài khoản người dùng có đầy đủ quyền thao tác trên hệ thống.",
                    "Chuẩn bị sẵn sàng các thông tin hoặc dữ liệu mẫu cần nhập trước khi thực hiện quy trình."
                ]
            else:
                metadata.executive_summary = (
                    f"Standard Operating Procedure (SOP) containing {total} steps performed across: {apps_str}. "
                    f"Provides comprehensive walkthrough covering setup, core transaction execution, and outcome verification."
                )
                metadata.prerequisites = [
                    f"Installed, configured, and running applications: {apps_str}.",
                    "Ensure user account has appropriate permissions for all target functions.",
                    "Prepare required input parameters and data prior to executing the procedure."
                ]

    def _enrich_single_step(self, step: Step, is_vi: bool) -> str:
        """Turn raw coordinate/action logs into clean, active-voice SOP sentences."""
        # Preserve user comments with clean header
        if step.action_type == "comment":
            return step.description

        win = step.window_title or ("Ứng dụng" if is_vi else "Application")
        ctrl = step.ui_control or ""
        
        # Parse control name and type e.g. "'Submit' [Button]" or "'Search' (Edit)"
        ctrl_name = ""
        ctrl_type = ""
        if ctrl:
            m = re.match(r"['\"]?([^'\"]+)['\"]?\s*[\(\[]([^\)\]]+)[\)\]]", ctrl)
            if m:
                ctrl_name = m.group(1).strip()
                ctrl_type = m.group(2).strip().lower()
            else:
                ctrl_name = ctrl.strip()

        # 1. Click Actions
        if step.action_type in ("left_click", "click"):
            if ctrl_name:
                if any(k in ctrl_type for k in ("button", "nút")):
                    return f"Nhấn nút **{ctrl_name}** trên giao diện {win}." if is_vi else f"Click the **{ctrl_name}** button on {win}."
                elif any(k in ctrl_type for k in ("edit", "text", "textbox", "input", "ô")):
                    return f"Nhấp vào ô nhập liệu **{ctrl_name}** trên giao diện {win}." if is_vi else f"Click on the **{ctrl_name}** input field on {win}."
                elif any(k in ctrl_type for k in ("tab", "menu", "item")):
                    return f"Chọn mục/thẻ **{ctrl_name}** trên giao diện {win}." if is_vi else f"Select **{ctrl_name}** tab/menu item on {win}."
                elif any(k in ctrl_type for k in ("check", "checkbox", "hộp kiểm")):
                    return f"Tích chọn hộp kiểm **{ctrl_name}** trên {win}." if is_vi else f"Toggle checkbox **{ctrl_name}** on {win}."
                elif any(k in ctrl_type for k in ("link", "hyperlink", "liên kết")):
                    return f"Nhấp vào liên kết **{ctrl_name}** trên {win}." if is_vi else f"Click on hyperlink **{ctrl_name}** on {win}."
                elif any(k in ctrl_type for k in ("combo", "dropdown", "danh sách")):
                    return f"Mở danh sách lựa chọn **{ctrl_name}** trên {win}." if is_vi else f"Open dropdown list **{ctrl_name}** on {win}."
                else:
                    return f"Nhấp chuột vào đối tượng **{ctrl_name}** trên giao diện {win}." if is_vi else f"Click on **{ctrl_name}** on {win}."
            else:
                if step.cursor_x is not None and step.cursor_y is not None:
                    return f"Nhấp chuột trái tại tọa độ ({step.cursor_x}, {step.cursor_y}) trên [{win}]." if is_vi else f"Left click at ({step.cursor_x}, {step.cursor_y}) on [{win}]."
                return f"Nhấp chuột trái trên giao diện [{win}]." if is_vi else f"Left click on [{win}]."

        # 2. Double Click
        elif step.action_type == "double_click":
            if ctrl_name:
                return f"Nhấp đúp chuột vào **{ctrl_name}** trên giao diện {win} để kích hoạt." if is_vi else f"Double-click on **{ctrl_name}** on {win} to activate."
            return f"Nhấp đúp chuột trên giao diện [{win}]." if is_vi else f"Double click on [{win}]."

        # 3. Right Click
        elif step.action_type == "right_click":
            if ctrl_name:
                return f"Nhấp chuột phải vào **{ctrl_name}** trên giao diện {win} để mở menu ngữ cảnh." if is_vi else f"Right-click on **{ctrl_name}** on {win} to open context menu."
            return f"Nhấp chuột phải trên giao diện [{win}] để mở menu thao tác." if is_vi else f"Right click on [{win}] to open context menu."

        # 4. Text Input
        elif step.action_type == "type_text":
            text = step.typed_text or ""
            if ctrl_name:
                return f"Nhập nội dung \"{text}\" vào trường **{ctrl_name}** trên {win}." if is_vi else f"Enter \"{text}\" into **{ctrl_name}** field on {win}."
            return f"Nhập văn bản \"{text}\" trên giao diện [{win}]." if is_vi else f"Type text \"{text}\" on [{win}]."

        # 5. Key Press
        elif step.action_type == "key_press":
            # Extract key name if formatted like "action_key_press"
            m = re.search(r"\[([A-Z0-9_\+\-]+)\]", step.description)
            key_name = m.group(1) if m else "phím"
            return f"Nhấn phím **{key_name}** trên bàn phím." if is_vi else f"Press **{key_name}** key."

        # 6. Click Result
        elif step.action_type == "click_result":
            return f"Hệ thống xử lý và hiển thị kết quả tương ứng trên giao diện [{win}]." if is_vi else f"System updates and displays result on [{win}]."

        return step.description

    def _apply_auto_chapters(self, steps: List[Step], is_vi: bool) -> None:
        """Automatically divide recording steps into 2-3 logical SOP chapters."""
        n = len(steps)
        if n < 3:
            return

        # Chapter 1 at step 0
        steps[0].is_section_header = True
        steps[0].section_title = "Phần 1: Khởi động & Mở ứng dụng" if is_vi else "Phase 1: Setup & Initialization"
        steps[0].section_description = (
            "Khởi chạy các công cụ, chuẩn bị môi trường và điều hướng tới màn hình làm việc chính."
            if is_vi else "Launch target applications, verify environment, and navigate to main workspace."
        )

        # Chapter 2 at roughly 1/3 or 1/2
        mid_idx = max(1, n // 3 if n >= 6 else n // 2)
        if mid_idx < n:
            steps[mid_idx].is_section_header = True
            steps[mid_idx].section_title = "Phần 2: Thực hiện nghiệp vụ chính" if is_vi else "Phase 2: Core Process Execution"
            steps[mid_idx].section_description = (
                "Nhập liệu các trường thông tin, thực hiện các thao tác xử lý nghiệp vụ trọng tâm."
                if is_vi else "Input parameters, execute primary functions, and configure required data."
            )

        # Chapter 3 if session has >= 7 steps
        if n >= 7:
            end_idx = int(n * 0.75)
            if end_idx > mid_idx and end_idx < n:
                steps[end_idx].is_section_header = True
                steps[end_idx].section_title = "Phần 3: Xác nhận & Hoàn tất quy trình" if is_vi else "Phase 3: Verification & Completion"
                steps[end_idx].section_description = (
                    "Kiểm tra tính chính xác của dữ liệu, lưu thay đổi và đóng phiên làm việc."
                    if is_vi else "Verify data integrity, save changes, and finalize workflow."
                )

    def _polish_with_llm(
        self,
        steps: List[Step],
        metadata: Optional[SessionMetadata],
        provider: str,
        api_key: str
    ) -> bool:
        """Call Gemini or OpenAI-compatible API to polish SOP with LLM intelligence."""
        is_vi = self.lang == "vi"
        target_lang = "Vietnamese" if is_vi else "English"

        # Build compact step list representation for prompt
        compact_steps = []
        for s in steps:
            compact_steps.append({
                "step_id": s.step_id,
                "action": s.action_type,
                "window": s.window_title,
                "control": s.ui_control,
                "text": s.typed_text,
                "note": s.user_comment
            })

        system_prompt = (
            f"You are a Senior Technical Writer and QA Lead specializing in creating Standard Operating Procedures (SOPs). "
            f"Given a list of recorded UI steps, refine them into professional, concise, active-voice SOP instructions in {target_lang}. "
            f"Provide an Executive Summary, Prerequisites, and divide the steps into 2-3 logical Chapters. "
            f"Return ONLY valid JSON matching this schema:\n"
            f'{{"summary": "...", "prerequisites": ["...", "..."], "steps": [{{"step_id": 1, "description": "...", "is_section": false, "section_title": "", "section_desc": ""}}]}}'
        )

        user_content = json.dumps({"session_title": metadata.title if metadata else "", "steps": compact_steps}, ensure_ascii=False)

        # 1. Google Gemini API
        if provider == "gemini":
            model = getattr(self.config, "ai_model", "gemini-2.5-flash") or "gemini-2.5-flash"
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
            payload = {
                "contents": [
                    {"parts": [{"text": f"{system_prompt}\n\nInput Data:\n{user_content}"}]}
                ],
                "generationConfig": {"responseMimeType": "application/json"}
            }
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=18) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                text_out = data["candidates"][0]["content"]["parts"][0]["text"]
                return self._apply_llm_json_result(text_out, steps, metadata)

        # 2. OpenAI / Local Ollama API
        elif provider == "openai":
            base_url = getattr(self.config, "ai_api_base", "https://api.openai.com/v1").rstrip("/")
            model = getattr(self.config, "ai_model", "gpt-4o-mini") or "gpt-4o-mini"
            url = f"{base_url}/chat/completions"
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content}
                ],
                "response_format": {"type": "json_object"}
            }
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=18) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                text_out = data["choices"][0]["message"]["content"]
                return self._apply_llm_json_result(text_out, steps, metadata)

        return False

    def _apply_llm_json_result(
        self,
        json_text: str,
        steps: List[Step],
        metadata: Optional[SessionMetadata]
    ) -> bool:
        """Parse LLM JSON response and apply polished metadata and step descriptions."""
        try:
            # Strip markdown fences if present
            cleaned = json_text.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            if cleaned.startswith("```"):
                cleaned = cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            parsed = json.loads(cleaned.strip())

            # Update Metadata
            if metadata:
                if parsed.get("summary"):
                    metadata.executive_summary = parsed["summary"]
                if parsed.get("prerequisites"):
                    metadata.prerequisites = parsed["prerequisites"]

            # Update Steps
            step_map = {item.get("step_id"): item for item in parsed.get("steps", [])}
            for s in steps:
                item = step_map.get(s.step_id)
                if item:
                    if item.get("description"):
                        s.ai_description = item["description"]
                        s.description = item["description"]
                    if item.get("is_section") and item.get("section_title"):
                        s.is_section_header = True
                        s.section_title = item["section_title"]
                        s.section_description = item.get("section_desc", "")
            return True
        except Exception as e:
            print(f"[AICopilot] Failed to apply LLM result: {e}")
            return False

