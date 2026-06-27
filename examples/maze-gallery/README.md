# Maze gallery

Sample output from [`examples/amazing.trx`](../amazing.trx) — a ~5,000-line
pure-Trix maze generator (homage to Steve Capps' *Amazing* on the 128K Mac).
Every image here is a real PNG whose format `amazing.trx` assembles itself in
Trix -- no libpng, over the engine's native `deflate`/`crc32`/`adler32` ops --
holding eleven maze algorithms across five grid topologies, distance-colored with
six colormaps.

This directory is otherwise generated output and git-ignored; the handful below
is curated and tracked for the project README and docs. To render the full set
(grids × algorithms × colormaps, plus solve/braid/weave feature shots), run:

```sh
examples/gallery.sh
```

| Image | Shows |
| --- | --- |
| [`grid-upsilon-viridis.png`](grid-upsilon-viridis.png) | **Upsilon** grid (octagons + squares), viridis shading — the README hero |
| [`grid-theta-viridis.png`](grid-theta-viridis.png) | Concentric **polar** grid, viridis distance shading |
| [`grid-hex-magma.png`](grid-hex-magma.png) | **Hex** grid (pointy-top, odd-r offset), magma colormap |
| [`grid-triangle-inferno.png`](grid-triangle-inferno.png) | **Triangle** grid (alternating up/down), inferno colormap |
| [`compare-4-algos.png`](compare-4-algos.png) | Four algorithms side by side (backtracker, Kruskal, Wilson, Eller) |
| [`algo-division-magma.png`](algo-division-magma.png) | **Recursive division** (wall-adding), magma heatmap — the color bands trace its nested-room subdivision |
| [`algo-division-rainbow.png`](algo-division-rainbow.png) | **Recursive division** at 100×100, rainbow heatmap — the README's third hero shot |
| [`grid-hex-solve.png`](grid-hex-solve.png) | Hex maze with the solution path overlaid in red |
| [`monster-magma.png`](monster-magma.png) | **Monster** heatmap — a 400×400 maze (160k cells) in magma distance shading |
| [`monster-division-rainbow.png`](monster-division-rainbow.png) | **Monster recursive-division** — 400×400 (160k cells), rainbow heatmap; the color blocks expose the recursive partition hierarchy |

Algorithms: recursive-backtracker, Kruskal, Wilson, Eller, binary-tree,
sidewinder, Aldous-Broder, Prim, Hunt-and-Kill, Growing Tree,
recursive-division (the one wall-adding generator).
Grids: square, hex, theta (polar), triangle, upsilon (octagon).

The full-resolution **monster** — a 1000×1000-cell maze (3001×3001 px, ~0.9 MB)
for panning and zooming — isn't tracked here; run `examples/gallery.sh --full`
(or `trix.opt examples/amazing.trx --monster`, ~3 min) to generate `monster.png`
in this directory.
