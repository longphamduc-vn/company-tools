"""
Image annotation module for drawing click markers, highlight regions,
and step number badges onto screenshots.
"""

from typing import Tuple, Optional
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageChops, ImageStat


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


def apply_blur_region(
    image: Image.Image,
    rect: Tuple[int, int, int, int],
    radius: int = 18
) -> Image.Image:
    """
    Apply heavy Gaussian blur to the specified (x1, y1, x2, y2) region
    to hide sensitive privacy information (passwords, bank data, PII).
    """
    x1, y1, x2, y2 = rect
    left, top, right, bottom = min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)
    left = max(0, min(image.width - 1, left))
    top = max(0, min(image.height - 1, top))
    right = max(left + 2, min(image.width, right))
    bottom = max(top + 2, min(image.height, bottom))

    result = image.copy()
    cropped = result.crop((left, top, right, bottom))
    blurred = cropped.filter(ImageFilter.GaussianBlur(radius=radius))
    result.paste(blurred, (left, top))

    draw = ImageDraw.Draw(result)
    draw.rectangle([left, top, right, bottom], outline=(148, 163, 184), width=1)
    return result


def apply_redact_region(
    image: Image.Image,
    rect: Tuple[int, int, int, int],
    fill_color: Tuple[int, int, int] = (15, 23, 42),
    draw_label: bool = True
) -> Image.Image:
    """
    Fill the specified region with solid blackout color and an optional [REDACTED] label.
    Completely obfuscates sensitive corporate credentials, API keys, and personal data.
    """
    x1, y1, x2, y2 = rect
    left, top, right, bottom = min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)
    left = max(0, min(image.width - 1, left))
    top = max(0, min(image.height - 1, top))
    right = max(left + 2, min(image.width, right))
    bottom = max(top + 2, min(image.height, bottom))

    result = image.copy()
    draw = ImageDraw.Draw(result)
    draw.rectangle([left, top, right, bottom], fill=fill_color, outline=(51, 65, 85), width=1)

    if draw_label and (right - left) >= 55 and (bottom - top) >= 16:
        try:
            font = ImageFont.load_default()
        except Exception:
            font = None
        label = "REDACTED"
        cx = (left + right) // 2
        cy = (top + bottom) // 2
        draw.text((cx, cy), label, fill=(148, 163, 184), font=font, anchor="mm")

    return result


def crop_image(
    image: Image.Image,
    rect: Tuple[int, int, int, int]
) -> Image.Image:
    """Crop image to the specified bounding box."""
    x1, y1, x2, y2 = rect
    left, top, right, bottom = min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)
    left = max(0, min(image.width - 1, left))
    top = max(0, min(image.height - 1, top))
    right = max(left + 10, min(image.width, right))
    bottom = max(top + 10, min(image.height, bottom))
    return image.crop((left, top, right, bottom))


def draw_box_annotation(
    image: Image.Image,
    rect: Tuple[int, int, int, int],
    color_hex: str = "#EF4444",
    width: int = 3,
    fill: bool = False
) -> Image.Image:
    """Draw a colored attention/highlight rectangle box on the image."""
    x1, y1, x2, y2 = rect
    left, top, right, bottom = min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)
    img_rgba = image.convert("RGBA")
    overlay = Image.new("RGBA", img_rgba.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(overlay)

    main_rgba = hex_to_rgba(color_hex, 255)
    fill_rgba = hex_to_rgba(color_hex, 40) if fill else None
    draw.rectangle([left, top, right, bottom], fill=fill_rgba, outline=main_rgba, width=width)
    result = Image.alpha_composite(img_rgba, overlay)
    return result.convert("RGB")


def has_ui_changed(
    image1: Image.Image,
    image2: Image.Image,
    click_pos: Optional[Tuple[int, int]] = None,
    win1: str = "",
    win2: str = "",
    threshold_global: float = 0.0006,
    threshold_local: float = 0.0018
) -> bool:
    """
    Intelligently detect whether meaningful UI changes occurred between two screenshots.

    Checks:
    1. Active window title change (e.g. modal opened, tab switched, app changed).
    2. Global screen difference via downsampled pixel comparison (ignores tiny 1-pixel noise).
    3. Local click-area difference within 120px radius around cursor (detects checkboxes,
       toggle switches, radio buttons, dropdown clicks).
    """
    if win1 and win2 and win1 != win2:
        return True

    try:
        # 1. Global downsampled difference
        s1 = image1.resize((160, 90))
        s2 = image2.resize((160, 90))
        diff_global = ImageChops.difference(s1, s2)
        stat_global = ImageStat.Stat(diff_global)
        global_ratio = sum(stat_global.mean) / (3.0 * 255.0)

        if global_ratio > threshold_global:
            return True

        # 2. Local click-region difference (e.g. checkbox, toggle switch)
        if click_pos:
            cx, cy = click_pos
            w, h = image1.size
            r = 120
            box = (max(0, cx - r), max(0, cy - r), min(w, cx + r), min(h, cy + r))
            crop1 = image1.crop(box)
            crop2 = image2.crop(box)
            diff_local = ImageChops.difference(crop1, crop2)
            stat_local = ImageStat.Stat(diff_local)
            local_ratio = sum(stat_local.mean) / (3.0 * 255.0)
            if local_ratio > threshold_local:
                return True

    except Exception:
        # Fallback to True if any error occurs to ensure no critical screen state is lost
        return True

    return False


