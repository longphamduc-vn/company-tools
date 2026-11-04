"""
Image annotation module for drawing click markers, highlight regions,
and step number badges onto screenshots.
"""

from typing import Tuple, Optional
from PIL import Image, ImageDraw, ImageFont


def hex_to_rgba(hex_color: str, alpha: int = 255) -> Tuple[int, int, int, int]:
    """Convert hex string (e.g. #FF3366) to RGBA tuple."""
    hex_color = hex_color.lstrip("#")
    if len(hex_color) == 6:
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        return (r, g, b, alpha)
    return (255, 51, 102, alpha)


def annotate_screenshot(
    image: Image.Image,
    cursor_pos: Optional[Tuple[int, int]] = None,
    step_id: Optional[int] = None,
    highlight_rect: Optional[Tuple[int, int, int, int]] = None,
    color_hex: str = "#FF3366",
    radius: int = 24,
    style: str = "ring",
    show_badge: bool = True
) -> Image.Image:
    """
    Draw highlight indicator, optional badge, or selection rectangle on a copy of the image.
    Returns a new PIL Image.
    """
    # Work on a copy with RGBA support for smooth translucent overlays
    img_rgba = image.convert("RGBA")
    overlay = Image.new("RGBA", img_rgba.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(overlay)

    main_color = hex_to_rgba(color_hex, 230)
    fill_color = hex_to_rgba(color_hex, 45)
    center_color = hex_to_rgba(color_hex, 255)

    # 1. Draw cursor click indicator if cursor_pos is provided
    if cursor_pos:
        cx, cy = cursor_pos
        # Constrain to image boundaries
        cx = max(0, min(img_rgba.width - 1, cx))
        cy = max(0, min(img_rgba.height - 1, cy))

        if style == "ring":
            # Outer translucent ripple
            draw.ellipse(
                [cx - (radius + 6), cy - (radius + 6), cx + (radius + 6), cy + (radius + 6)],
                outline=hex_to_rgba(color_hex, 90),
                width=2
            )
            # Main semi-transparent filled circle
            draw.ellipse(
                [cx - radius, cy - radius, cx + radius, cy + radius],
                fill=fill_color,
                outline=main_color,
                width=3
            )
            # Center precision dot
            dot_r = 4
            draw.ellipse(
                [cx - dot_r, cy - dot_r, cx + dot_r, cy + dot_r],
                fill=center_color
            )

        elif style == "crosshair":
            # Crosshair with center circle
            arm_len = radius + 10
            draw.line([(cx - arm_len, cy), (cx + arm_len, cy)], fill=main_color, width=2)
            draw.line([(cx, cy - arm_len), (cx, cy + arm_len)], fill=main_color, width=2)
            draw.ellipse(
                [cx - radius, cy - radius, cx + radius, cy + radius],
                fill=fill_color,
                outline=main_color,
                width=2
            )
            draw.ellipse([cx - 3, cy - 3, cx + 3, cy + 3], fill=center_color)

        elif style == "glow":
            # Multi-layered glow
            for i, r_step in enumerate([radius + 12, radius + 8, radius + 4, radius]):
                alpha = int(40 + (i * 45))
                draw.ellipse(
                    [cx - r_step, cy - r_step, cx + r_step, cy + r_step],
                    fill=hex_to_rgba(color_hex, alpha // 3),
                    outline=hex_to_rgba(color_hex, alpha),
                    width=2
                )
            draw.ellipse([cx - 4, cy - 4, cx + 4, cy + 4], fill=center_color)

        else:  # solid
            draw.ellipse(
                [cx - radius, cy - radius, cx + radius, cy + radius],
                fill=hex_to_rgba(color_hex, 160),
                outline=center_color,
                width=3
            )

        # Draw Step ID badge near marker if enabled
        if show_badge and step_id is not None:
            _draw_step_badge(draw, cx, cy, step_id, color_hex, radius)

    # 2. Draw user highlight rectangle if provided (e.g. from comment / region selection)
    if highlight_rect:
        rx1, ry1, rx2, ry2 = highlight_rect
        left = min(rx1, rx2)
        top = min(ry1, ry2)
        right = max(rx1, rx2)
        bottom = max(ry1, ry2)

        # Translucent fill + sharp dashed/solid border
        draw.rectangle(
            [left, top, right, bottom],
            fill=hex_to_rgba(color_hex, 35),
            outline=main_color,
            width=3
        )
        if show_badge and step_id is not None and not cursor_pos:
            _draw_step_badge(draw, left + 10, top + 10, step_id, color_hex, 0)

    # Composite overlay on original image
    result = Image.alpha_composite(img_rgba, overlay)
    return result.convert("RGB")


def _draw_step_badge(
    draw: ImageDraw.ImageDraw,
    cx: int,
    cy: int,
    step_id: int,
    color_hex: str,
    offset_r: int
) -> None:
    """Draw a clean numbered badge tag beside the click indicator."""
    badge_text = str(step_id)
    badge_x = cx + offset_r + 6
    badge_y = cy - offset_r - 12
    badge_w = max(24, len(badge_text) * 9 + 14)
    badge_h = 22

    # Badge background (dark pill with bright accent border)
    draw.rounded_rectangle(
        [badge_x, badge_y, badge_x + badge_w, badge_y + badge_h],
        radius=11,
        fill=(24, 24, 27, 235),
        outline=hex_to_rgba(color_hex, 255),
        width=2
    )

    # Badge text
    try:
        font = ImageFont.load_default()
    except Exception:
        font = None

    draw.text(
        (badge_x + (badge_w // 2), badge_y + (badge_h // 2)),
        badge_text,
        fill=(255, 255, 255, 255),
        font=font,
        anchor="mm"
    )

