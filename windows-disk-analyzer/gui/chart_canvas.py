"""Interactive Treemap and Drive Health visual widgets built on native Tkinter Canvas."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable, Dict, List, Optional, Tuple

from disk_analyzer.formatters import format_bytes
from disk_analyzer.models import DriveInfo, DriveStatus, FolderNode
from gui.theme import Theme


class DriveCardsStrip(ttk.Frame):
    """Displays all logical drives with usage bars, alert badges, and 1-click scan actions."""

    def __init__(
        self,
        parent: tk.Misc,
        on_scan_drive: Callable[[str], None],
    ) -> None:
        super().__init__(parent, style="TFrame")
        self._on_scan_drive = on_scan_drive

    def update_drives(self, drives: List[DriveInfo]) -> None:
        for child in self.winfo_children():
            child.destroy()

        ready = [d for d in drives if d.is_ready]
        if not ready:
            ttk.Label(self, text="No ready logical drives detected.").pack(anchor=tk.W, pady=6)
            return

        for idx, drv in enumerate(ready):
            self.columnconfigure(idx, weight=1)
            card = tk.Frame(
                self,
                bg=Theme.BG_CARD,
                highlightbackground=Theme.BORDER,
                highlightthickness=1,
                padx=12,
                pady=10,
            )
            card.grid(row=0, column=idx, sticky="nsew", padx=(0 if idx == 0 else 8, 0))

            color = Theme.PRIMARY
            badge_text = "HEALTHY"
            if drv.status == DriveStatus.CRITICAL:
                color = Theme.CRITICAL
                badge_text = "CRITICAL"
            elif drv.status == DriveStatus.WARNING:
                color = Theme.WARNING
                badge_text = "WARNING"

            top_row = tk.Frame(card, bg=Theme.BG_CARD)
            top_row.pack(fill=tk.X)

            title = f"Drive {drv.letter} ({drv.label})"
            if drv.is_system_drive:
                title += " • System"
            tk.Label(
                top_row,
                text=title,
                bg=Theme.BG_CARD,
                fg=Theme.TEXT_MAIN,
                font=(Theme.FONT_FAMILY, 10, "bold"),
            ).pack(side=tk.LEFT)

            tk.Label(
                top_row,
                text=badge_text,
                bg=color,
                fg="#FFFFFF",
                font=(Theme.FONT_FAMILY, 8, "bold"),
                padx=7,
                pady=1,
            ).pack(side=tk.RIGHT)

            tk.Label(
                card,
                text=f"{drv.drive_type} ({drv.filesystem}) • Total: {format_bytes(drv.total_bytes)}",
                bg=Theme.BG_CARD,
                fg=Theme.TEXT_MUTED,
                font=(Theme.FONT_FAMILY, 8),
            ).pack(anchor=tk.W, pady=(3, 6))

            bar_canvas = tk.Canvas(card, height=10, bg="#E2E8F0", highlightthickness=0)
            bar_canvas.pack(fill=tk.X)
            bar_canvas.bind(
                "<Configure>",
                lambda ev, c=bar_canvas, pct=drv.used_percent, col=color: self._draw_bar(c, pct, col),
            )

            info_row = tk.Frame(card, bg=Theme.BG_CARD)
            info_row.pack(fill=tk.X, pady=(6, 0))

            tk.Label(
                info_row,
                text=f"Used: {format_bytes(drv.used_bytes)} ({drv.used_percent:.1f}%)",
                bg=Theme.BG_CARD,
                fg=Theme.TEXT_MAIN,
                font=(Theme.FONT_FAMILY, 9),
            ).pack(side=tk.LEFT)

            tk.Label(
                info_row,
                text=f"Free: {format_bytes(drv.free_bytes)} ({drv.free_percent:.1f}%)",
                bg=Theme.BG_CARD,
                fg=color if drv.status != DriveStatus.HEALTHY else Theme.SUCCESS,
                font=(Theme.FONT_FAMILY, 9, "bold"),
            ).pack(side=tk.RIGHT)

            btn_row = tk.Frame(card, bg=Theme.BG_CARD)
            btn_row.pack(fill=tk.X, pady=(6, 0))
            tk.Label(
                btn_row,
                text=f"Recycle Bin: {format_bytes(drv.recycle_bin_bytes)}",
                bg=Theme.BG_CARD,
                fg=Theme.TEXT_MUTED,
                font=(Theme.FONT_FAMILY, 8),
            ).pack(side=tk.LEFT)

            ttk.Button(
                btn_row,
                text=f"Scan {drv.letter}",
                style="Secondary.TButton",
                command=lambda p=drv.root_path: self._on_scan_drive(p),
            ).pack(side=tk.RIGHT)

    @staticmethod
    def _draw_bar(canvas: tk.Canvas, percent: float, color: str) -> None:
        canvas.delete("all")
        w = max(1, canvas.winfo_width())
        h = max(1, canvas.winfo_height())
        fill_w = max(2, int((max(0.0, min(100.0, percent)) / 100.0) * w))
        canvas.create_rectangle(0, 0, w, h, fill="#E2E8F0", outline="")
        canvas.create_rectangle(0, 0, fill_w, h, fill=color, outline="")


class TreemapCanvas(tk.Frame):
    """Interactive recursive treemap visualization for FolderNode hierarchies."""

    def __init__(
        self,
        parent: tk.Misc,
        on_select_node: Optional[Callable[[FolderNode], None]] = None,
    ) -> None:
        super().__init__(parent, bg=Theme.BG_CARD, highlightbackground=Theme.BORDER, highlightthickness=1)
        self._on_select_node = on_select_node
        self._current_node: Optional[FolderNode] = None
        self._history: List[FolderNode] = []
        self._rect_nodes: Dict[int, FolderNode] = {}
        self._hover_rect: Optional[int] = None

        nav = tk.Frame(self, bg=Theme.MUTED_BG, padx=8, pady=5)
        nav.pack(fill=tk.X)

        self._btn_up = ttk.Button(nav, text="<- Back", style="Secondary.TButton", command=self.go_back)
        self._btn_up.pack(side=tk.LEFT)
        self._btn_up.state(["disabled"])

        self._lbl_path = tk.Label(
            nav,
            text="No folder scan data yet",
            bg=Theme.MUTED_BG,
            fg=Theme.TEXT_MAIN,
            font=(Theme.FONT_FAMILY, 9, "bold"),
            anchor=tk.W,
        )
        self._lbl_path.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(10, 4))

        self._lbl_hover = tk.Label(
            nav,
            text="",
            bg=Theme.MUTED_BG,
            fg=Theme.PRIMARY,
            font=(Theme.FONT_FAMILY, 9),
        )
        self._lbl_hover.pack(side=tk.RIGHT)

        self._canvas = tk.Canvas(self, bg="#0F172A", highlightthickness=0, cursor="hand2")
        self._canvas.pack(fill=tk.BOTH, expand=True)
        self._canvas.bind("<Configure>", lambda _e: self._redraw())
        self._canvas.bind("<Motion>", self._on_motion)
        self._canvas.bind("<Leave>", self._on_leave)
        self._canvas.bind("<Button-1>", self._on_click)

    def set_node(self, node: Optional[FolderNode], push_history: bool = False) -> None:
        if push_history and self._current_node is not None and node is not self._current_node:
            self._history.append(self._current_node)
        elif not push_history:
            self._history.clear()

        self._current_node = node
        if self._history:
            self._btn_up.state(["!disabled"])
        else:
            self._btn_up.state(["disabled"])

        if node is None:
            self._lbl_path.configure(text="No folder scan data yet")
        else:
            self._lbl_path.configure(
                text=f"{node.path}  ({format_bytes(node.disk_bytes)} • {node.file_count:,} files)"
            )
        self._redraw()

    def go_back(self) -> None:
        if not self._history:
            return
        prev = self._history.pop()
        self._current_node = prev
        if not self._history:
            self._btn_up.state(["disabled"])
        self._lbl_path.configure(
            text=f"{prev.path}  ({format_bytes(prev.disk_bytes)} • {prev.file_count:,} files)"
        )
        self._redraw()
        if self._on_select_node:
            self._on_select_node(prev)

    def _redraw(self) -> None:
        self._canvas.delete("all")
        self._rect_nodes.clear()
        self._hover_rect = None

        w = self._canvas.winfo_width()
        h = self._canvas.winfo_height()
        if w < 40 or h < 40:
            return

        node = self._current_node
        if node is None:
            self._canvas.create_text(
                w / 2,
                h / 2,
                text="Select a drive or folder and click 'Scan Folder & Large Files' to view the storage treemap",
                fill="#94A3B8",
                font=(Theme.FONT_FAMILY, 10),
                width=max(200, w - 40),
                justify=tk.CENTER,
            )
            return

        items: List[Tuple[str, int, Optional[FolderNode]]] = []
        children_sum = 0
        for child in node.children:
            val = max(0, child.disk_bytes)
            if val > 0:
                items.append((child.name, val, child))
                children_sum += val

        direct_files_bytes = max(0, node.disk_bytes - children_sum)
        if direct_files_bytes > 0:
            items.append((f"[Files in {node.name}]", direct_files_bytes, None))

        if not items:
            self._canvas.create_text(
                w / 2,
                h / 2,
                text="This folder is empty or consumes 0 B on disk.",
                fill="#94A3B8",
                font=(Theme.FONT_FAMILY, 10),
            )
            return

        items.sort(key=lambda t: t[1], reverse=True)
        if len(items) > 24:
            other_sum = sum(t[1] for t in items[23:])
            items = items[:23] + [(f"Other ({len(items) - 23} items)", other_sum, None)]

        total = sum(t[1] for t in items) or 1
        rects = self._slice_and_dice(items, 4.0, 4.0, float(w - 8), float(h - 8))

        for idx, (rx, ry, rw, rh, label, val, ref_node) in enumerate(rects):
            if rw < 2 or rh < 2:
                continue
            color = Theme.TREEMAP_PALETTE[idx % len(Theme.TREEMAP_PALETTE)] if ref_node else "#475569"
            rid = self._canvas.create_rectangle(
                rx,
                ry,
                rx + rw,
                ry + rh,
                fill=color,
                outline="#0F172A",
                width=2,
            )
            if ref_node is not None:
                self._rect_nodes[rid] = ref_node

            pct = (val / total) * 100.0
            if rw >= 68 and rh >= 36:
                text = f"{label}\n{format_bytes(val)} ({pct:.1f}%)"
                self._canvas.create_text(
                    rx + 6,
                    ry + 6,
                    text=text,
                    anchor=tk.NW,
                    fill="#FFFFFF",
                    font=(Theme.FONT_FAMILY, 8, "bold"),
                    width=max(20, int(rw - 12)),
                )
            elif rw >= 42 and rh >= 20:
                self._canvas.create_text(
                    rx + 4,
                    ry + 4,
                    text=label[:14],
                    anchor=tk.NW,
                    fill="#FFFFFF",
                    font=(Theme.FONT_FAMILY, 7),
                )

    @staticmethod
    def _slice_and_dice(
        items: List[Tuple[str, int, Optional[FolderNode]]],
        x: float,
        y: float,
        w: float,
        h: float,
    ) -> List[Tuple[float, float, float, float, str, int, Optional[FolderNode]]]:
        """Recursive binary-split treemap layout keeping aspect ratios balanced."""
        if not items or w <= 0 or h <= 0:
            return []
        if len(items) == 1:
            name, val, node = items[0]
            return [(x, y, w, h, name, val, node)]

        total = sum(t[1] for t in items) or 1
        half = total / 2.0
        acc = 0
        split_idx = 1
        for idx in range(len(items) - 1):
            acc += items[idx][1]
            if acc >= half:
                split_idx = idx + 1
                break
            split_idx = idx + 1

        left = items[:split_idx]
        right = items[split_idx:]
        left_sum = sum(t[1] for t in left)
        ratio = left_sum / total

        if w >= h:
            lw = w * ratio
            return (
                TreemapCanvas._slice_and_dice(left, x, y, lw, h)
                + TreemapCanvas._slice_and_dice(right, x + lw, y, w - lw, h)
            )
        lh = h * ratio
        return (
            TreemapCanvas._slice_and_dice(left, x, y, w, lh)
            + TreemapCanvas._slice_and_dice(right, x, y + lh, w, h - lh)
        )

    def _find_rect_at(self, x: int, y: int) -> Optional[int]:
        overlapping = self._canvas.find_overlapping(x, y, x, y)
        for item_id in reversed(overlapping):
            if item_id in self._rect_nodes:
                return item_id
        return None

    def _on_motion(self, event: tk.Event) -> None:
        rid = self._find_rect_at(event.x, event.y)
        if self._hover_rect and self._hover_rect != rid:
            self._canvas.itemconfigure(self._hover_rect, outline="#0F172A", width=2)
        if rid:
            self._hover_rect = rid
            self._canvas.itemconfigure(rid, outline="#F8FAFC", width=2)
            node = self._rect_nodes[rid]
            parent_total = (self._current_node.disk_bytes if self._current_node else 0) or 1
            pct = (node.disk_bytes / parent_total) * 100.0
            self._lbl_hover.configure(
                text=f"{node.name}: {format_bytes(node.disk_bytes)} ({pct:.1f}%) - Click to drill down"
            )
        else:
            self._hover_rect = None
            self._lbl_hover.configure(text="")

    def _on_leave(self, _event: tk.Event) -> None:
        if self._hover_rect:
            self._canvas.itemconfigure(self._hover_rect, outline="#0F172A", width=2)
            self._hover_rect = None
        self._lbl_hover.configure(text="")

    def _on_click(self, event: tk.Event) -> None:
        rid = self._find_rect_at(event.x, event.y)
        if not rid:
            return
        node = self._rect_nodes.get(rid)
        if node and node.children:
            self.set_node(node, push_history=True)
            if self._on_select_node:
                self._on_select_node(node)
        elif node and self._on_select_node:
            self._on_select_node(node)
