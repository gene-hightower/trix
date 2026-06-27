#!/usr/bin/env python3
# =============================================================================
# tools/gen_mask_font.py -- generate hi-res BITMAP-font atlases for the
# examples/amazing.trx masking feature (--mask-text / --mask logo / --font).
#
# Trix has no FreeType, so a font cannot be rasterised inside the VM.  This
# host-side tool renders a glyph atlas ONCE from a TrueType face and emits it as
# Trix data (examples/mask-fonts/<name>.trx).  Only the generated atlas is ever
# committed -- never the .ttf.  This mirrors how the colormap data in
# amazing.trx is produced from matplotlib: a host tool generates, the data is
# checked in.  (Hershey stroke fonts use the companion tools/gen_hershey_font.py
# and render in pure Trix; this tool is for outline faces via Pillow.)
#
# HOST TOOLS REQUIRED (none of this is needed to RUN amazing.trx -- only to
# regenerate a font):
#   * Python 3.8+
#   * Pillow            pip install pillow      (PIL: TrueType rasteriser)
#   * NumPy             pip install numpy       (thresholding)
#   * network access    (to download Roboto; or pass --ttf for a local font)
#
# DEFAULT (no args): downloads the two BUNDLED Apache-2.0 faces and writes
#   examples/mask-fonts/roboto-bold.trx
#   examples/mask-fonts/roboto-mono-bold.trx
#
# -----------------------------------------------------------------------------
# A NOTE ON FONT LICENSING  (informational -- not legal advice; verify yourself)
# -----------------------------------------------------------------------------
# In the US a typeface DESIGN -- and the pixels it renders -- is not
# copyrightable; only the font *program* (the .ttf) is, and the font *name* may
# be a trademark.  So rendering glyphs to a bitmap for YOUR OWN local output
# (masking a maze) is unencumbered regardless of the source font's license:
# you are producing pixels, not shipping the font.  The license only matters if
# you intend to COMMIT / REDISTRIBUTE the generated atlas.  Pick accordingly:
#
#   Font(s)                              License        Commit the atlas?
#   -----------------------------------  -------------  -----------------------
#   Roboto, Roboto Mono, Open Sans, Droid Apache-2.0    yes -- same as Trix
#   Hershey (PD designs, re-encoded)     public domain  yes -- credit only
#   Liberation, Noto, most Google Fonts  OFL-1.1        no -- reserved names +
#                                                       can't-sell-standalone
#   DejaVu / Bitstream Vera              Vera           no -- can't-sell-standalone
#   GNU FreeFont, Unifont                GPL            no -- copyleft
#
# amazing.trx BUNDLES only Apache-2.0 (Roboto) and PD (Hershey) glyph data.
# Use --ttf to render ANY font you have for your own local mazes -- that atlas
# is yours and is not committed here.
#
# Examples:
#   tools/gen_mask_font.py                          # download + both bundled faces
#   tools/gen_mask_font.py --ttf /path/Foo-Bold.ttf --name foo-bold   # any local font
#   tools/gen_mask_font.py --height 60              # taller cells (thicker strokes)
# =============================================================================

import argparse
import io
import os
import sys
from urllib.request import urlopen

# Bundled Apache-2.0 faces: output atlas name -> (download URL, display label).
BUNDLED = {
    "roboto-bold": (
        "https://github.com/googlefonts/roboto-2/raw/main/src/hinted/Roboto-Bold.ttf",
        "Roboto Bold (Apache-2.0)",
    ),
    "roboto-mono-bold": (
        "https://github.com/googlefonts/RobotoMono/raw/main/fonts/ttf/RobotoMono-Bold.ttf",
        "Roboto Mono Bold (Apache-2.0)",
    ),
}

# Printable ASCII 0x20..0x7E -- full flexibility for --mask-text.
GLYPHS = [chr(c) for c in range(0x20, 0x7F)]

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(REPO_ROOT, "examples", "mask-fonts")


def die(msg):
    print(f"gen_mask_font: {msg}", file=sys.stderr)
    sys.exit(1)


def trix_key(ch):
    """A Trix one-char string literal usable as a dict key (escape ( ) \\)."""
    return "(\\" + ch + ")" if ch in "()\\" else "(" + ch + ")"


def render_face(ttf_bytes, height):
    """Render every glyph onto a common baseline, then crop the whole face to
    the global vertical ink extent (so the mask is tight to cap-height +
    descender, not the font's full leading).  Returns (cellH, {ch: (advance,
    packed_bytes)})."""
    try:
        from PIL import Image, ImageFont, ImageDraw
        import numpy as np
    except ImportError as e:
        die(f"missing host dependency: {e.name} (pip install pillow numpy)")

    font = ImageFont.truetype(io.BytesIO(ttf_bytes), height)
    ascent, descent = font.getmetrics()
    line_h = ascent + descent
    raw = {}                       # ch -> (advance, line_h x advance uint8 array)
    top, bot = line_h, 0           # global ink extent across all glyphs
    for ch in GLYPHS:
        adv = round(font.getlength(ch))
        if adv <= 0:
            raw[ch] = (1, None)
            continue
        img = Image.new("L", (adv, line_h), 0)
        ImageDraw.Draw(img).text((0, 0), ch, fill=255, font=font)
        bits = (np.array(img) > 110).astype(np.uint8)
        raw[ch] = (adv, bits)
        ys = np.where(bits.any(axis=1))[0]
        if len(ys):
            top, bot = min(top, int(ys[0])), max(bot, int(ys[-1]))
    if bot < top:
        top, bot = 0, line_h - 1
    cell_h = bot - top + 1
    glyphs = {}
    for ch in GLYPHS:
        adv, bits = raw[ch]
        if bits is None:
            glyphs[ch] = (adv, b"")
            continue
        sub = bits[top:bot + 1]
        row_bytes = (adv + 7) // 8
        packed = bytearray(cell_h * row_bytes)
        for gy in range(cell_h):
            for gx in range(adv):
                if sub[gy, gx]:
                    packed[gy * row_bytes + (gx >> 3)] |= 0x80 >> (gx & 7)
        glyphs[ch] = (adv, bytes(packed))
    return cell_h, glyphs


def emit_trix(name, label, line_h, glyphs):
    out = ["% " + "=" * 75,
           "%  GENERATED by tools/gen_mask_font.py -- DO NOT EDIT BY HAND.",
           f"%  Font:    {label}",
           "%  Kind:    bitmap atlas (see tools/gen_mask_font.py for regeneration)",
           f"%  Cell height: {line_h} px   Glyphs: {len(glyphs)} (printable ASCII 0x20-0x7E)",
           "%",
           "%  Registers itself into MASK-FONTS (created by amazing.trx).  (kind) is",
           "%  (bitmap); each glyph is [advance <packed-bits>]: `advance` cells wide,",
           "%  `h` rows tall, row-major, bit 7 of byte 0 = top-left; rowBytes = ceil(adv/8).",
           "% " + "=" * 75,
           f"MASK-FONTS ({name}) <<",
           "    (kind) (bitmap)",
           f"    (h) {line_h}",
           "    (glyphs) <<"]
    for ch in GLYPHS:
        adv, packed = glyphs[ch]
        hexbits = "<" + packed.hex() + ">" if packed else "<>"
        out.append(f"        {trix_key(ch):8} [ {adv} {hexbits} ]")
    out += ["    >>", ">> put", ""]
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description="Generate Trix bitmap mask-font atlases.")
    ap.add_argument("--height", type=int, default=52, help="font pixel size / cell height (default 52)")
    ap.add_argument("--ttf", help="render a single local TTF instead of the bundled Roboto faces")
    ap.add_argument("--name", help="output atlas name for --ttf (e.g. foo-bold)")
    ap.add_argument("--out-dir", default=OUT_DIR)
    args = ap.parse_args()
    os.makedirs(args.out_dir, exist_ok=True)

    if args.ttf:
        if not args.name:
            die("--ttf requires --name")
        ttf = open(args.ttf, "rb").read()
        line_h, glyphs = render_face(ttf, args.height)
        path = os.path.join(args.out_dir, f"{args.name}.trx")
        open(path, "w").write(emit_trix(args.name, os.path.basename(args.ttf), line_h, glyphs))
        print(f"wrote {path} (cell height {line_h})")
        return

    for name, (url, label) in BUNDLED.items():
        print(f"downloading {label} ...", file=sys.stderr)
        ttf = urlopen(url, timeout=60).read()
        line_h, glyphs = render_face(ttf, args.height)
        path = os.path.join(args.out_dir, f"{name}.trx")
        open(path, "w").write(emit_trix(name, label, line_h, glyphs))
        print(f"wrote {path} (cell height {line_h}, {len(glyphs)} glyphs)")


if __name__ == "__main__":
    main()
