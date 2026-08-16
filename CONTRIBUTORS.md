# Contributors

Trix is created and maintained by Mark Guidarelli.

Thanks to everyone who has contributed fixes and improvements:

- **Gene Hightower** ([@gene-hightower](https://github.com/gene-hightower)) —
  build-portability fix: include `<limits.h>` for `PATH_MAX` so the header
  compiles on toolchains that no longer provide it transitively (Fedora 44 /
  GCC 16.1). ([#11](https://github.com/mcguidarelli/trix/pull/11))

- **[@Danl2620](https://github.com/Danl2620)** — reported that the
  inspector TUI never came up on their script, which turned out to be four
  separate defects: `let` / `destructure` scopes were fixed-capacity and
  overflowed on the first `def` (so no halt inside one could render),
  `stream-name` returned a synthetic placeholder for non-file streams,
  `--inspect` ended the session at a fatal error instead of halting there,
  and `--inspect` only resolved `lib/debugger.trx` from a checkout root.
  ([#14](https://github.com/mcguidarelli/trix/issues/14))

Contributions are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).
