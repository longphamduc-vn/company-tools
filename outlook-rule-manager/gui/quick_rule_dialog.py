"""Quick New Rule dialog: pick an existing folder or type a new path."""
import re
import tkinter as tk
from tkinter import ttk
from typing import List, Optional, Tuple

from core.models import rule_name_from_folder, outlook_rule_name  # noqa: F401  (re-exported)


def normalize_folder_path(path: str) -> str:
    return "\\".join(s.strip() for s in re.split(r"[\\/]", path or "") if s.strip())


class QuickRuleDialog(tk.Toplevel):
    """Modal dialog. After it closes, `result` is (name, folder, scope) or None.

    `name` is always derived from `folder` via rule_name_from_folder(folder).
    scope is "email" or "domain" when sender info is given, otherwise "email".
    """

    def __init__(
        self,
        parent: tk.Misc,
        folders: List[str],
        default_name: str = "",
        default_folder: str = "",
        sender_email: str = "",
        sender_domain: str = "",
        blocked_folder: str = "_Unclassified",
        title: str = "New Rule",
    ):
        super().__init__(parent)
        self.title(title)
        self.transient(parent.winfo_toplevel())
        self.resizable(True, False)
        self.result: Optional[Tuple[str, str, str]] = None
        self._folders = [f for f in folders if f]
        self._blocked = (blocked_folder or "").lower()

        frm = ttk.Frame(self, padding=14)
        frm.pack(fill=tk.BOTH, expand=True)
        frm.columnconfigure(1, weight=1)

        if sender_email:
            ttk.Label(frm, text=f"From: {sender_email}", foreground="#475569").grid(
                row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 8)
            )

        ttk.Label(frm, text="Folder:").grid(row=1, column=0, sticky=tk.W, pady=3)
        self.var_folder = tk.StringVar(value=default_folder)
        self.cbo_folder = ttk.Combobox(frm, textvariable=self.var_folder, values=self._folders, width=40)
        self.cbo_folder.grid(row=1, column=1, sticky=tk.EW, padx=(8, 0), pady=3)
        self.cbo_folder.bind("<KeyRelease>", self._on_folder_typed)
        self.cbo_folder.bind("<<ComboboxSelected>>", lambda e: self._update_folder_hint())

        self.lbl_folder_hint = ttk.Label(frm, text="", foreground="#64748b", font=("", 8))
        self.lbl_folder_hint.grid(row=2, column=1, sticky=tk.W, padx=(8, 0))

        self.var_scope = tk.StringVar(value="email")
        if sender_email:
            scope_row = ttk.Frame(frm)
            scope_row.grid(row=3, column=0, columnspan=2, sticky=tk.W, pady=(8, 0))
            ttk.Radiobutton(scope_row, text="This sender", value="email", variable=self.var_scope).pack(side=tk.LEFT)
            if sender_domain:
                ttk.Radiobutton(
                    scope_row, text=f"Whole domain ({sender_domain})", value="domain", variable=self.var_scope
                ).pack(side=tk.LEFT, padx=(12, 0))

        btns = ttk.Frame(frm)
        btns.grid(row=4, column=0, columnspan=2, sticky=tk.E, pady=(12, 0))
        ttk.Button(btns, text="Cancel", command=self.cancel).pack(side=tk.RIGHT)
        self.btn_ok = ttk.Button(btns, text="Create", style="Accent.TButton", command=self.ok)
        self.btn_ok.pack(side=tk.RIGHT, padx=(0, 6))

        self.bind("<Return>", lambda e: self.ok())
        self.bind("<Escape>", lambda e: self.cancel())
        self.protocol("WM_DELETE_WINDOW", self.cancel)

        self._update_folder_hint()
        self.cbo_folder.focus_set()

    # -- folder field ---------------------------------------------------
    def _on_folder_typed(self, event=None):
        typed = self.var_folder.get().strip().lower()
        matches = [f for f in self._folders if typed in f.lower()] if typed else self._folders
        self.cbo_folder.configure(values=matches)
        self._update_folder_hint()

    def _update_folder_hint(self):
        path = normalize_folder_path(self.var_folder.get())
        if not path:
            self.lbl_folder_hint.config(text="Pick a folder or type a new path (A\\B\\C).", foreground="#64748b")
        elif self._has_underscore_segment(path):
            self.lbl_folder_hint.config(text="Folder names cannot start with '_'.", foreground="#b91c1c")
        elif self._is_blocked(path):
            self.lbl_folder_hint.config(text="Rules cannot be created in the Unclassified folder.", foreground="#b91c1c")
        elif path.lower() in {f.lower() for f in self._folders}:
            self.lbl_folder_hint.config(text="Existing folder." + self._outlook_note(path), foreground="#16a34a")
        else:
            self.lbl_folder_hint.config(text="New folder will be created." + self._outlook_note(path), foreground="#ea580c")

    @staticmethod
    def _outlook_note(path: str) -> str:
        return f"  Outlook rule: {outlook_rule_name(rule_name_from_folder(path))}"

    @staticmethod
    def _has_underscore_segment(path: str) -> bool:
        return any(seg.startswith("_") for seg in path.split("\\") if seg)

    def _is_blocked(self, path: str) -> bool:
        low = path.lower()
        return bool(self._blocked) and (low == self._blocked or low.startswith(self._blocked + "\\"))

    # -- result ---------------------------------------------------------
    def ok(self):
        folder = normalize_folder_path(self.var_folder.get())
        if not folder or self._is_blocked(folder) or self._has_underscore_segment(folder):
            self._update_folder_hint()
            self.cbo_folder.focus_set()
            return
        name = rule_name_from_folder(folder)
        self.result = (name, folder, self.var_scope.get())
        self.destroy()

    def cancel(self):
        self.result = None
        self.destroy()

    @classmethod
    def ask(cls, parent: tk.Misc, **kwargs) -> Optional[Tuple[str, str, str]]:
        dlg = cls(parent, **kwargs)
        try:
            dlg.grab_set()
        except tk.TclError:
            pass
        parent.wait_window(dlg)
        return dlg.result
