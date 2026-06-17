# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.9.0] - 2026-06-15

First public release. Trix is an embeddable, stack-based (concatenative) scripting VM
that ships as a single C++23 header you `#include` into a host program. The language and
runtime are feature-complete; this release follows a full release-readiness pass
(documentation audit, sad-path test expansion, fuzzing campaigns, example hardening, and
a performance pass).

### Added

**Language and runtime**
- Concatenative core with 829 operators: stack manipulation, arithmetic, strings,
  arrays/dicts/sets/records, control flow, error handling, formatting, and I/O.
- Tagged-union value model: 31 types in an 8-byte `Object`, with 64-bit values
  (Long/ULong/Double/Address) in journaled heap extension slots and 128-bit values
  (Int128/UInt128) in 16-byte wide-value slots.
- Optional infix expressions, scoped modules (`require`/`use`/`import`), and
  precondition/postcondition contracts.

**Concurrency (cooperative, single-threaded)**
- Coroutines with sleep/yield/join and a two-tier priority scheduler.
- Bounded-buffer pipelines with automatic backpressure.
- Actors: isolated processes with mailboxes, send/recv, and selective receive.
- Erlang/OTP-style supervision: monitors, links, and restart strategies/intensity.

**Computation**
- Logic programming: Prolog-style unification, backtracking, and choice points,
  built on the save/restore journal.
- Reactive cells: spreadsheet-style incremental recomputation with watchers.
- Lazy sequences: infinite streams with deferred evaluation and transducers.
- Algebraic effects and delimited continuations; pattern matching, protocols
  (open type dispatch), and a GenServer abstraction.

**Durability and memory**
- Transactional local arena: `save`/`restore` checkpoints reclaim allocations and
  revert in-place mutations through a journal (no GC on the local arena).
- Precise mark-sweep garbage collector for the durable global region.
- Whole-VM snapshot/thaw: serialize the entire interpreter (stacks, heap, in-flight
  coroutines, mailboxes, supervision trees, reactive graph) to disk and resume later.

**Tooling and embedding**
- Single-header embedding with a constexpr user-operator table and a resident/server
  mode (`invoke()` / `raise_interrupt()`) for long-lived hosts.
- Source-level interactive debugger (`--inspect`): TUI single-stepping, conditional and
  one-shot breakpoints, watch expressions, and a sandboxed eval prompt — its UI is
  written in Trix itself.
- 24 example programs, including a full Infocom Z-machine, a metacircular Scheme with
  `call/cc`, a CHIP-8 emulator, a regex engine, and an in-memory SQL with transactions.
- 61 reference documents covering every subsystem.

### Quality

- ASan/UBSan clean; compiles `-Werror` under GCC 15 and Clang 20 with an extensive
  warning set.
- 20,200+ test assertions across 274 test files; a libFuzzer harness over the full
  interpreter (coverage-guided).
- Dependencies are readline and zlib, both opt-out (`--no-readline` / `--no-zlib`).
- Apache 2.0 licensed.

[Unreleased]: https://github.com/mcguidarelli/trix/compare/v0.9.0...HEAD
[0.9.0]: https://github.com/mcguidarelli/trix/releases/tag/v0.9.0
