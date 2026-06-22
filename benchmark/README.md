# Trix benchmark artifacts

Small, self-contained scripts used to validate hash/scanner performance
work.  Not part of the build; retained for regression comparison.

## Files

| File | Purpose |
| --- | --- |
| `bench_hash.cpp` | Standalone micro-benchmark: times two hash implementations on matched string pools (tiny/short/medium/long buckets) and prints ns/hash + MB/s.  Currently compares FNV-1a (historical) against wyhash (current).  Update in place to compare any new candidate against `wyhash32_sv`. |
| `bench_interpreter.trx` | Main interpreter-loop dispatch benchmark.  Runs a tight `repeat` loop whose body executes four dispatched ops (`1 2 add pop`), 25M iterations by default for ~100M total ops.  Headline figure in the top-level README is derived from this. |
| `gen_bench.py` | Generates `bench_scan.trx`: 1M literal-name tokens over 20K unique names (3-12 bytes each), deterministic seed.  Pure scanner/hash workload, no dict defines. |
| `timer.py` | Runs a binary against a script N times; prints min / mean-of-5-best / median / max in milliseconds. |
| `release.sh` | Builds an optimized (-O2, no ASAN/UBSAN) release binary at `benchmark/trix.rel` for end-to-end timing.  The debug build under `./build.sh` is too noisy for wall-clock benchmarks. |

## Typical workflow

```bash
# 1. Build release binary
benchmark/release.sh

# 2. (First time only) generate the scanner workload
python3 benchmark/gen_bench.py

# 3. Hash micro-benchmark
g++-15 -O2 -std=c++23 benchmark/bench_hash.cpp -o benchmark/bench_hash
benchmark/bench_hash

# 4. End-to-end scanner timing, 20 runs
python3 benchmark/timer.py 20 benchmark/trix.rel benchmark/bench_scan.trx
```

## Reference results (2026-04, commit 44c525e)

Micro-benchmark (wyhash vs the prior FNV-1a):

| bucket | avg len | FNV-1a  | wyhash | speedup |
| ------ | ------- | ------- | ------ | ------- |
| tiny   | 5.5 B   | 5.4 ns  | 1.5 ns | 3.64x   |
| short  | 9.5 B   | 7.4 ns  | 1.5 ns | 4.85x   |
| medium | 19.9 B  | 11.4 ns | 1.7 ns | 6.84x   |
| long   | 80.1 B  | 57.0 ns | 7.0 ns | 8.16x   |

End-to-end (1M scan-time hash calls): ~1-2% wall-clock improvement.
Scanner is not hash-bound.

## Interpreter dispatch (2026-06-06)

Hardware: aarch64 (Apple Silicon via Parallels VM, 8 cores), gcc-15,
`-O2 -DNDEBUG`, no sanitizers.

```bash
benchmark/release.sh                                                           # build benchmark/trix.rel
python3 benchmark/timer.py 10 benchmark/trix.rel benchmark/bench_interpreter.trx
```

Typical result (min of 10 runs): **~2.12 s for 100M dispatched ops =
~47M ops/sec**.  The workload is `1 2 add pop` inside a `repeat`,
which exercises integer push, the arithmetic shim, and a stack pop
-- four dispatches through the main interpreter loop per iteration.
Process-startup overhead measured separately at ~1 ms and is
negligible at this scale.

History: ~45M ops/sec (2026-04-22); a P3-era regression to ~39M was
diagnosed and reversed in the Phase-5 performance pass (consteval
dispatch tables + object hot-path fast paths).

Companion numbers on the same hardware/date (min of 10):
bench_scan 139 ms (1M tokens), bench_journal_write 4528 ms (1M
save+put+restore), bench_journal_write2 842 ms (4M journal writes).

x86_64 hardware has not been measured; native Apple Silicon (no VM)
should be somewhat faster due to Parallels' ~5-10% overhead.

## Frame-local access -- slot-indexing (2026-06-22)

Isolates the slot-indexing read win: a frame proc reading its own params
by direct frame-slot index instead of a dict-stack name lookup.  Only a
frame proc's depth-0 top-level executable name-refs are rewritten to
slot-refs (nested procs stay dynamic name lookups), so the benchmark
unrolls the reads at the proc's top level and drives them with an outer
`repeat` (no recursion, no TCO-depth dependency).

```bash
python3 benchmark/gen_frame_locals.py                                # K=200 N=125000 -> 50M param reads
python3 benchmark/timer.py 10 <binary> benchmark/bench_frame_locals.trx
```

A/B on the same hardware (aarch64 Parallels VM, gcc-15 `-O2 -DNDEBUG`),
isolated release binaries built at each commit, identical flags:

| build                                | commit     | min of 10 | frame-local reads/sec |
| ------------------------------------ | ---------- | --------- | --------------------- |
| baseline (SlotRef type, no emission) | `1b41bf0f` | 2590 ms   | 19.3M reads/sec       |
| slot-indexing (params + /locals)     | `47344697` | 2145 ms   | 23.3M reads/sec       |

**Result: 17.2% faster (1.21x) on the 50M-read workload.**  The workload
is `a b add pop` x200 inside a `|a b|` frame proc, repeated 125000 times
(~100M dispatched ops total); slot-indexing lifts a param-read-heavy
frame loop from ~39M to ~47M ops/sec, i.e. up to frameless dispatch speed.

Mechanism confirmed via `proc-disasm` on a `TRIX_DEBUGGER` build: HEAD
emits `<slot 0>` / `<slot 1>` for the `a` / `b` reads; the same source on
`1b41bf0f` leaves them as executable names resolved by `name_lookup_in_stack`.

x86_64 hardware has not been measured.
