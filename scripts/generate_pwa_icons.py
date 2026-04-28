#!/usr/bin/env python3
"""Generate PWA icons for the Monogatari reader.

Produces three PNGs in static/icons/:
  - icon-192.png        (Android home screen)
  - icon-512.png        (splash screen + PWA install promotion)
  - icon-512-maskable.png (per W3C maskable-icon spec, 80% safe area)
  - apple-touch-icon.png (180x180, iOS home screen, no rounded corners
                          because iOS adds them automatically)

The motif is a single kanji 物 (the first character of 物語 / "story",
matching the nav-logo in +layout.svelte) reversed out of a brand-red
rounded square. Brand colour matches manifest.theme_color (#c0392b).

Re-run after any brand colour or motif change. Output is checked in
because (a) icons are read by the manifest, not built, and (b) a
deterministic PIL renderer is friendlier than a binary asset that
appears out of the void.

Usage:
    source .venv/bin/activate
    python3 scripts/generate_pwa_icons.py
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "static" / "icons"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Brand colours pulled directly from vite.config.ts manifest defaults.
BG = (192, 57, 43)        # #c0392b
FG = (250, 248, 244)      # #faf8f4 — slight warm off-white for contrast

# macOS path for Hiragino Mincho ProN (W6 weight is the bold variant).
# This is shipped with macOS so any local generator run will work.
JP_FONT_PATH = "/System/Library/Fonts/ヒラギノ明朝 ProN.ttc"
JP_GLYPH = "物"


def render(size: int, *, mask_safe_area: bool, corner_radius_ratio: float) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    if mask_safe_area:
        # Per W3C maskable-icon spec, the OS may crop up to 20% off each
        # edge to fit any device's icon mask (squircle, circle, square).
        # Fill the FULL canvas with the background colour and draw the
        # glyph centered within an 80% safe area.
        draw.rectangle((0, 0, size, size), fill=BG + (255,))
    else:
        # Standard icon: a rounded-rect badge. The OS will not mask it,
        # so the visual frame must match the brand.
        radius = int(size * corner_radius_ratio)
        draw.rounded_rectangle(
            (0, 0, size - 1, size - 1),
            radius=radius,
            fill=BG + (255,),
        )

    # Glyph sizing. For maskable, target 60% of the canvas (sits inside
    # the 80% safe area with breathing room). For standard, target 70%
    # of the canvas (a bit tighter because there's no crop risk).
    target_glyph_h = int(size * (0.60 if mask_safe_area else 0.70))

    # PIL's anchor system needs a font sized in pixels; iterate to fit
    # because Hiragino's metric height differs from cap height.
    font_size = target_glyph_h
    font = ImageFont.truetype(JP_FONT_PATH, font_size, index=2)  # W6 (bold)
    bbox = draw.textbbox((0, 0), JP_GLYPH, font=font, anchor="lt")
    glyph_w = bbox[2] - bbox[0]
    glyph_h = bbox[3] - bbox[1]
    # Re-target by glyph_h ratio so it fills the intended height.
    if glyph_h > 0:
        font_size = int(font_size * (target_glyph_h / glyph_h))
        font = ImageFont.truetype(JP_FONT_PATH, font_size, index=2)
        bbox = draw.textbbox((0, 0), JP_GLYPH, font=font, anchor="lt")
        glyph_w = bbox[2] - bbox[0]
        glyph_h = bbox[3] - bbox[1]

    cx = size / 2 - glyph_w / 2 - bbox[0]
    cy = size / 2 - glyph_h / 2 - bbox[1]
    draw.text((cx, cy), JP_GLYPH, fill=FG + (255,), font=font)

    return img


def write(name: str, img: Image.Image) -> None:
    out = OUT_DIR / name
    img.save(out, format="PNG", optimize=True)
    print(f"  wrote {out.relative_to(ROOT)} ({out.stat().st_size:,} bytes)")


def main() -> int:
    print(f"Generating PWA icons in {OUT_DIR.relative_to(ROOT)}/")

    # Standard 192/512 — rounded-rect badge for browsers that don't mask.
    write("icon-192.png", render(192, mask_safe_area=False, corner_radius_ratio=0.20))
    write("icon-512.png", render(512, mask_safe_area=False, corner_radius_ratio=0.20))

    # Maskable 512 — full-bleed background, glyph in 80% safe area.
    # Per W3C, a single maskable variant covers every Android launcher.
    write(
        "icon-512-maskable.png",
        render(512, mask_safe_area=True, corner_radius_ratio=0.0),
    )

    # Apple touch icon — 180x180, square (iOS adds its own corner radius).
    write(
        "apple-touch-icon.png",
        render(180, mask_safe_area=True, corner_radius_ratio=0.0),
    )

    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
