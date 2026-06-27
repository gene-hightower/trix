# Flow fields

Image-field data for [`examples/amazing.trx`](../amazing.trx)'s flow-maze
feature (`--flow-image NAME`). Each `*.trx` file registers one `[w h rows]`
grayscale grid into the `FLOW-FIELDS` registry and is loaded lazily on first
use. It is the image-sourced sibling of the built-in analytic fields
(`--flow radial|linear|spiral|sine`).

A flow field is a small 0..255 heightmap. `amazing.trx` runs a weighted-Kruskal
MST that carves the **low-value walls first**, so the corridors align to the
image's tones at a macro scale while Kruskal still punches a valid **perfect
maze** through it. `--flow-jitter` dials the result from strict "flow art" (0)
toward an ordinary maze (higher).

Trix has no image decoder, so a `.png`/`.svg` cannot be sampled inside the VM.
Instead a host tool reduces the image **once** to Trix data here — **only the
derived 0..255 grid is committed, never the source image.** The grid carries no
colour and is not the artwork, so the maze engine is source-agnostic.

| File       | Used by             | Source                                            |
| ---------- | ------------------- | ------------------------------------------------- |
| `logo.trx` | `--flow-image logo` | the in-repo `assets/trix-logo.svg` (our own logo) |

`logo` is the wordmark blurred into broad tonal regions: the dark ink is the
low-value valley, so the corridors pool into the letterforms and the maze's flow
traces the Trix wordmark.

## Regenerate / add a field

The host tool is [`tools/gen_flow_field.py`](../../tools/gen_flow_field.py).
Install the dependencies (Debian/Ubuntu):

```bash
sudo apt install python3-pil python3-numpy        # raster (.png/.jpg) input
sudo apt install python3-cairosvg                 # only for .svg input
```

```bash
# regenerate the bundled logo field from assets/trix-logo.svg
python3 tools/gen_flow_field.py

# sample any image you have, for your own local mazes (not committed)
python3 tools/gen_flow_field.py photo.png --name photo --width 140
./trix --vm-size=64M examples/amazing.trx --flow-image photo --size 70x70 --color turbo --out photo.png
```

It reduces the image to a small grayscale grid (`--width`), with optional
`--blur` (smooth into broad regions), `--gamma` (tone curve), `--gradient` (align
to edges instead of tones), and `--invert` (carve the bright regions first). The
field is sampled in normalized coordinates, so **match `--size` to the image's
aspect ratio** to avoid stretching. See `--help` for the full set.

## Licensing

A flow field is a 0..255 grayscale grid — no colour or artwork — and sampling an
image for **your own** local output is producing data, not redistributing the
image. The source image's license only matters if you intend to **commit /
redistribute** the generated field. This project bundles only a field derived
from the Trix logo (our own asset, Apache-2.0); see the root
[`NOTICE.md`](../../NOTICE.md).
