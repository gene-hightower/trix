# Maze gallery

Sample output from [`examples/amazing.trx`](../amazing.trx) — a ~6,600-line
pure-Trix maze generator (homage to Steve Capps' *Amazing* on the 128K Mac).
Every image here is a real PNG whose format `amazing.trx` assembles itself in
Trix -- no libpng, over the engine's native `deflate`/`crc32`/`adler32` ops --
holding twelve maze algorithms across five grid topologies, distance-colored with
ten colormaps.

This directory is otherwise generated output and git-ignored; the handful below
is curated and tracked for the project README and docs. To render the full set
(grids × algorithms × colormaps, plus solve/braid/weave feature shots), run:

```sh
examples/gallery.sh
```

| Image | Shows |
| --- | --- |
| [`grid-upsilon-viridis.png`](grid-upsilon-viridis.png) | **Upsilon** grid (octagons + squares), viridis shading |
| [`grid-theta-viridis.png`](grid-theta-viridis.png) | Concentric **polar** grid (theta), viridis distance shading — the README topology hero |
| [`grid-hex-magma.png`](grid-hex-magma.png) | **Hex** grid (pointy-top, odd-r offset), magma colormap |
| [`grid-triangle-inferno.png`](grid-triangle-inferno.png) | **Triangle** grid (alternating up/down), inferno colormap |
| [`compare-4-algos.png`](compare-4-algos.png) | Four algorithms side by side (backtracker, Kruskal, Wilson, Eller) |
| [`algo-division-magma.png`](algo-division-magma.png) | **Recursive division** (wall-adding), magma heatmap — the color bands trace its nested-room subdivision |
| [`algo-division-grayscale.png`](algo-division-grayscale.png) | **Recursive division** (wall-adding), grayscale heatmap — the README algorithm hero; nested gray blocks trace the subdivision |
| [`algo-origin-shift-turbo.png`](algo-origin-shift-turbo.png) | **Origin Shift** (CaptainLuma 2023, `--algo origin-shift`) — the one edge-reversal generator; turbo heatmap shows its organic near-unbiased texture (the warm blob is the final origin) |
| [`flow-spiral-turbo.png`](flow-spiral-turbo.png) | **Flow field** — `--flow spiral`, a weighted-Kruskal maze whose corridors follow a scalar field; still a perfect maze (`--flow-jitter` dials art ↔ twisty) |
| [`flow-image-logo.png`](flow-image-logo.png) | **Image flow field** — `--flow-image logo`, the same weighted Kruskal steered by an IMAGE (the bundled `logo`, sampled from `assets/trix-logo.svg` by `tools/gen_flow_field.py`); the corridors trace the wordmark while Kruskal still punches a perfect maze |
| [`flow-image-cat.png`](flow-image-cat.png) | **Image flow field (silhouette)** — `--flow-image cat`, a bold silhouette field (drawn by `tools/gen_flow_field.py`); its broad tonal masses steer the flow so the maze drapes over the figure |
| [`grid-hex-solve.png`](grid-hex-solve.png) | Hex maze with the solution path overlaid in red |
| [`solve-dead-end-fill.png`](solve-dead-end-fill.png) | **Solver: dead-end-fill** (`--solver dead-end-fill`) — every dead-end iteratively filled (grey), leaving only the start→end solution corridor + red ribbon (the "drained" maze) |
| [`solve-astar.png`](solve-astar.png) | **Solver: A\*** (`--solver astar`) — the cells A\* expanded tinted blue: a focused frontier toward the goal vs BFS's full flood (same maze/seed as the others) |
| [`solve-wall-follower.png`](solve-wall-follower.png) | **Solver: wall-follower** (`--solver wall-follower`, square) — the left-hand-rule walk, with its dead-end excursions; finds *a* path, not the shortest |
| [`unicursal-viridis.png`](unicursal-viridis.png) | **Unicursal labyrinth** (`--unicursal`) — a single non-branching path that visits every cell (a doubled perfect maze); the viridis gradient is distance-along-the-one-path, flowing continuously end to end (no junctions) |
| [`monster-magma.png`](monster-magma.png) | **Monster** heatmap — a 400×400 maze (160k cells) in magma distance shading |
| [`monster-division-rainbow.png`](monster-division-rainbow.png) | **Monster recursive-division** — 400×400 (160k cells), rainbow heatmap; the color blocks expose the recursive partition hierarchy |
| [`color-cividis.png`](color-cividis.png) | **cividis** colormap (colorblind-friendly perceptual) on a Kruskal maze |
| [`color-turbo.png`](color-turbo.png) | **turbo** colormap (perceptually-ordered rainbow) on a Kruskal maze |
| [`color-cubehelix.png`](color-cubehelix.png) | **cubehelix** colormap (grayscale-safe monotone luminance) on a Kruskal maze |
| [`color-grayscale.png`](color-grayscale.png) | **grayscale** colormap (smooth black→white ramp) on a Kruskal maze |
| [`mask-logo.png`](mask-logo.png) | **SVG masking** — the real Trix logo (`--mask logo`, turbo) cut out of a maze, rasterised from `assets/trix-logo.svg` by `tools/gen_mask_svg.py` |
| [`mask-text-amazing.png`](mask-text-amazing.png) | **Text mask** — `--mask-text 'Amazing!'` (Roboto Bold, default font), inferno; mixed case + punctuation, descenders honored |
| [`mask-font-roboto.png`](mask-font-roboto.png) | **Font select** — `--mask-text Trix --font roboto-mono-bold`, turbo (Apache-2.0 bitmap atlas) |
| [`mask-font-hershey.png`](mask-font-hershey.png) | **Stroke font** — `--mask-text Trix --font hershey-serif`, viridis (public-domain Hershey, rendered in pure Trix) |
| [`mask-disc.png`](mask-disc.png) | **Analytic mask** — `--mask disc`, a circular maze with an inferno distance heatmap |
| [`mask-trix-invert.png`](mask-trix-invert.png) | **Inverse mask** — `--mask-text Trix --mask-invert`: the letters punched out of a full magma maze |

Algorithms: recursive-backtracker, Kruskal, Wilson, Eller, binary-tree,
sidewinder, Aldous-Broder, Prim, Hunt-and-Kill, Growing Tree,
Origin Shift (edge-reversal), recursive-division (the one wall-adding generator).
Grids: square, hex, theta (polar), triangle, upsilon (octagon).
Colormaps: viridis, magma, inferno, plasma, cividis, turbo, rainbow, cubehelix,
grayscale, two-tone (plus the `mono` outline render).

The full-resolution **monster** — a 1000×1000-cell maze (3001×3001 px, ~0.9 MB)
for panning and zooming — isn't tracked here; run `examples/gallery.sh --full`
(or `trix.opt examples/amazing.trx --monster`, ~3 min) to generate `monster.png`
in this directory.
