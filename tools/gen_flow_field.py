#!/usr/bin/env python3
# =============================================================================
# tools/gen_flow_field.py -- turn an image into a Trix FLOW FIELD for the
# examples/amazing.trx flow-maze feature (--flow-image).
#
# A flow field is a grayscale heightmap that biases a weighted-Kruskal maze:
# amazing.trx carves the LOW-value walls first, so the maze's corridors align
# to the image's tonal structure at a macro scale while Kruskal still punches a
# valid PERFECT maze through it (and --flow-jitter dials the result from strict
# "flow art" toward an ordinary maze).  It is the image-sourced sibling of the
# built-in analytic fields (--flow radial|linear|spiral|sine).
#
# Trix has no image decoder (just as it has no SVG rasteriser or FreeType), so
# a .png/.jpg/.svg cannot become a field inside the VM.  This host-side tool
# samples the image ONCE, reduces it to a small 0..255 grayscale grid, and emits
# it as Trix data (examples/flow-fields/<name>.trx).  Only the derived field is
# ever committed -- never the source image; for your own images nothing is
# committed at all.  This mirrors the mask tooling (tools/gen_mask_svg.py): a
# host tool generates, the data is checked in, and the maze engine is
# source-agnostic.
#
# HOST TOOLS REQUIRED (none of this is needed to RUN amazing.trx -- the bundled
# logo field is already committed; you only need these to regenerate it or to
# sample your OWN image):
#   * Python 3.8+
#   * Pillow + NumPy:           sudo apt install python3-pil python3-numpy
#   * CairoSVG (.svg input only): sudo apt install python3-cairosvg
#
# DEFAULT (no args): regenerates the BUNDLED field from the in-repo logo SVG as
# the field used by `--flow-image logo`:
#   examples/flow-fields/logo.trx          (from assets/trix-logo.svg)
#
# BRING YOUR OWN IMAGE (for your own local mazes):
#   python3 tools/gen_flow_field.py photo.png --name photo --width 140
#   ./trix examples/amazing.trx --flow-image photo --size 70x70 --color turbo
#
# A flow field carries no colour and is not the source artwork -- sampling an
# image to a 0..255 grid for YOUR OWN local output is producing data, not
# redistributing the image.  The source's licence only matters if you intend to
# COMMIT / REDISTRIBUTE the generated field.  amazing.trx bundles only a field
# derived from the Trix logo (our own asset).
# =============================================================================

import argparse
import io
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_OUT = os.path.join(REPO, "examples", "flow-fields")
LOGO_SVG = os.path.join(REPO, "assets", "trix-logo.svg")


def _require_deps(need_svg):
    try:
        import numpy  # noqa: F401
        from PIL import Image  # noqa: F401
    except ImportError as exc:
        sys.exit(
            "gen_flow_field.py: missing host tool (%s).\n"
            "  install:  sudo apt install python3-pil python3-numpy" % exc.name
        )
    if need_svg:
        try:
            import cairosvg  # noqa: F401
        except ImportError:
            sys.exit(
                "gen_flow_field.py: .svg input needs CairoSVG.\n"
                "  install:  sudo apt install python3-cairosvg"
            )


def load_gray(path, supersample):
    """Load path as a float32 [h][w] grayscale array in [0,1] (1 = white)."""
    import numpy as np
    from PIL import Image

    if path.lower().endswith(".svg"):
        import cairosvg

        png = cairosvg.svg2png(
            url=path, output_width=supersample, background_color="white"
        )
        im = Image.open(io.BytesIO(png)).convert("L")
    else:
        im = Image.open(path).convert("L")
    return np.asarray(im, dtype=np.float32) / 255.0


def resize(a, target_w):
    """Area-average down to target_w (height follows the source aspect)."""
    import numpy as np
    from PIL import Image

    h0, w0 = a.shape
    target_h = max(1, round(target_w * h0 / w0))
    im = Image.fromarray((a * 255.0 + 0.5).astype(np.uint8))
    # LANCZOS gives a smooth field -- we WANT macro tones here, not the
    # thin-stroke preservation the mask tool needs.
    im = im.resize((target_w, target_h), Image.LANCZOS)
    return np.asarray(im, dtype=np.float32) / 255.0


def blur(a, radius):
    """Gaussian-smooth the field so corridors follow broad regions, not pixels."""
    import numpy as np
    from PIL import Image, ImageFilter

    if radius <= 0:
        return a
    im = Image.fromarray((a * 255.0 + 0.5).astype(np.uint8))
    im = im.filter(ImageFilter.GaussianBlur(radius))
    return np.asarray(im, dtype=np.float32) / 255.0


def gradient(a):
    """Replace tones with edge strength (normalised Sobel magnitude), so the
    flow aligns to the image's EDGES instead of its light/dark regions."""
    import numpy as np

    gy, gx = np.gradient(a)
    mag = np.hypot(gx, gy)
    hi = float(mag.max())
    if hi <= 0.0:
        return np.zeros_like(a)
    return mag / hi


def normalize(a):
    """Stretch the field to fill 0..1 (so the full carve-order range is used)."""
    import numpy as np

    lo = float(a.min())
    hi = float(a.max())
    if hi - lo < 1e-6:
        return np.full_like(a, 0.5)
    return (a - lo) / (hi - lo)


def emit(a, name):
    """Render the field as a Trix [w h [rows]] literal (rows are hex strings,
    one byte = one cell's 0..255 value)."""
    import numpy as np

    g = (a * 255.0 + 0.5).astype(np.uint8)
    h, w = g.shape
    lines = [
        "% Auto-generated by tools/gen_flow_field.py -- do not edit by hand.",
        f"% Flow field registered as '{name}'; format is [w h [rows]] where each",
        "% row is a w-byte hex string and each byte is the field value 0..255",
        "% (low = carved first).  Sampled by amazing.trx's --flow-image.",
        f"FLOW-FIELDS ({name}) [ {w} {h} [",
    ]
    for row in g:
        lines.append("  <" + "".join("%02x" % b for b in row) + ">")
    lines.append("] ] put")
    return "\n".join(lines) + "\n"


def build(path, target_w, supersample, gamma, do_blur, do_gradient,
          do_invert, do_normalize):
    a = load_gray(path, supersample)
    a = resize(a, target_w)
    if gamma != 1.0:
        a = a ** gamma
    a = blur(a, do_blur)
    if do_gradient:
        a = gradient(a)
    if do_normalize:
        a = normalize(a)
    if do_invert:
        a = 1.0 - a
    return a


def main():
    ap = argparse.ArgumentParser(
        description="Sample an image into a Trix flow field for amazing.trx.")
    ap.add_argument("image", nargs="?",
                    help="source image (.png/.jpg/.svg; default: the bundled logo)")
    ap.add_argument("--name", help="field name / output stem (default: from the file)")
    ap.add_argument("--width", type=int, default=128,
                    help="field width in cells (height follows aspect; default 128)")
    ap.add_argument("--gamma", type=float, default=1.0,
                    help="tone curve exponent (>1 darkens mids, <1 brightens; default 1)")
    ap.add_argument("--blur", type=float, default=0.0,
                    help="Gaussian smoothing radius in cells (default 0 = none)")
    ap.add_argument("--gradient", action="store_true",
                    help="use edge strength (Sobel) instead of tone -- flow aligns "
                         "to the image's edges")
    ap.add_argument("--invert", action="store_true",
                    help="flip the field (corridors carve the BRIGHT regions first)")
    ap.add_argument("--no-normalize", action="store_true",
                    help="keep raw tones (default stretches the field to fill 0..1)")
    ap.add_argument("--supersample", type=int, default=0,
                    help="SVG render width before downsampling (default: auto)")
    ap.add_argument("--out-dir", default=DEFAULT_OUT,
                    help="where to write <name>.trx (default examples/flow-fields)")
    args = ap.parse_args()

    if args.image is None:
        # Default: the bundled logo field consumed by `--flow-image logo`.  The
        # wordmark's slash-art is thin, so blur it into broad tonal regions that
        # actually steer the flow.  Left un-inverted, the dark ink is the
        # low-value (carved-first) valley, so the corridors pool into the
        # letterforms and the maze's flow traces the wordmark.
        args.image = LOGO_SVG
        if args.name is None:
            args.name = "logo"
        args.width = 160
        args.blur = 2.5

    _require_deps(args.image.lower().endswith(".svg"))

    name = args.name or os.path.splitext(os.path.basename(args.image))[0]
    ss = args.supersample or min(2400, max(1200, args.width * 8))

    a = build(args.image, args.width, ss, args.gamma, args.blur,
              args.gradient, args.invert, not args.no_normalize)

    os.makedirs(args.out_dir, exist_ok=True)
    out_path = os.path.join(args.out_dir, name + ".trx")
    with open(out_path, "w") as fh:
        fh.write(emit(a, name))

    import numpy as np
    g = (a * 255.0 + 0.5).astype(np.uint8)
    print("%s: %dx%d field, value range %d..%d (mean %d)%s%s"
          % (os.path.relpath(out_path, REPO), g.shape[1], g.shape[0],
             int(g.min()), int(g.max()), int(g.mean()),
             "  [gradient]" if args.gradient else "",
             "  [inverted]" if args.invert else ""))


if __name__ == "__main__":
    main()
