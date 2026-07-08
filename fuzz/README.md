# Fuzz Testing

Coverage-guided fuzz testing for Trix using
[libFuzzer](https://llvm.org/docs/LibFuzzer.html).  Requires clang++-20
(or later) with the fuzzer runtime.

Two harnesses:

| harness     | target                              | input fed as          | driver               |
| ----------- | ----------------------------------- | --------------------- | -------------------- |
| `fuzz_trix` | full interpreter pipeline           | a Trix script (stdin) | `./fuzz/run.sh`      |
| `fuzz_thaw` | snap-shot **thaw** path (`--image`) | a VM image            | `./fuzz/run_thaw.sh` |

Most of this document describes `fuzz_trix`; the thaw harness is covered in
its own section below, but shares the same run-loop, triage, and reproduce
machinery.

## Build

```bash
./fuzz/build.sh          # builds both fuzz_trix and fuzz_thaw
```

## Run

```bash
./fuzz/run.sh                              # no time limit; stops on first event
./fuzz/run.sh -max_total_time=300          # budget-aware loop, 5 minutes total
./fuzz/run.sh -max_len=65536               # larger inputs for deeper execution
./fuzz/run.sh --vm-size=1M -fork=4         # 1MB VM, 4 parallel workers
./fuzz/run.sh -overnight                   # shorthand for -max_total_time=28800
                                           #   --vm-size=2M (explicit flags win)
```

Crash reproducers are saved to `fuzz/crashes/`.  After each fuzzer exit,
`run.sh` auto-triages every new `crash-*` artifact (see **Triage** below)
and moves false positives to `fuzz/crashes_rejected/`.  The corpus is
merged (minimized) once at the end.

### Budget-aware loop

When `-max_total_time=N` is supplied, `run.sh` wraps the fuzzer in an
outer loop.  libFuzzer exits on the first crash in single-process mode,
and on aarch64 the false-positive rate is non-trivial; without the loop a
single false crash cuts an 8-hour session short after 5 minutes.

Each iteration:

1. Compute `remaining = N - elapsed` and relaunch the fuzzer with
   `-max_total_time=remaining` (preserving the total wall-clock budget).
2. Triage any new artifacts.  FALSE / CLEAN get moved to
   `fuzz/crashes_rejected/`.
3. If anything real lands in `fuzz/crashes/`, exit 1.  Otherwise continue
   until the budget is spent or the user interrupts (Ctrl-C).

Without `-max_total_time`, the script prints a banner and runs the fuzzer
exactly once -- it stops on the first crash event, real or false.  Use
this mode for quick ad-hoc runs; use the budget-aware form for overnight
runs.

## Parallelism: use `-fork=N`, never `-jobs=N`

For multi-worker fuzzing, always pass `-fork=N` (single libFuzzer parent,
N fork-server children).  **Do not use `-jobs=N`.**

`-jobs=N` spawns N independent libFuzzer processes whose inter-process
pipes get inherited by saved crash artifacts.  When such an artifact is
replayed standalone (`./fuzz/fuzz_trix crash-<hash>`), the orphan pipes
have no writer and the binary blocks on them for ~2 minutes before
exiting with rc=0 and no sanitizer output -- indistinguishable from a
real slow-path crash on first inspection, but actually false.

`-fork=N` gives the same throughput without the jobs-mode IPC; the
parent aggregates coverage from children transparently and crashes stay
isolated to the child that produced them.

## Triage

libFuzzer on aarch64 (and, separately, stale `-jobs=N` artifacts) can
produce **false-positive crash files** that do not correspond to any
actual bug.  These are the result of signal-handling / pipe-read
interactions between libFuzzer, the sanitizer runtimes, and the target
-- not a Trix defect.  They have a distinctive replay signature:

| signal                    | real crash     | false positive      |
| ------------------------- | -------------- | ------------------- |
| time to report            | milliseconds   | exactly 2 minutes   |
| exit code                 | non-zero       | 0                   |
| sanitizer / libFuzzer log | present        | empty (banner only) |
| `trix` on same input      | ordinary error | clean exit          |

A 15-second timeout cleanly separates the two cases -- real crashes
always dump their report within a second, false positives always hang
the full two minutes.

**Why the weeding is safe.** The same aarch64 race can also *mask* a real bug:
if an `assert()` fires while `fuzz_trix` has stderr silenced, libFuzzer catches
the `SIGABRT`, tries to write its report to the closed stderr, and deadlocks on
the signal pipe -- the identical two-minute hang signature, but with a real bug
underneath.  So triage never trusts the hang alone: it runs **`trix` first** (no
stderr redirect, no libFuzzer signal handling), which surfaces the assert or
sanitizer report directly, and only falls back to `fuzz_trix` when `trix` comes
back clean.  A masked crash is caught by that first pass, not silently weeded out
as a false positive.

### Automatic triage (run.sh)

After every `./fuzz/run.sh` invocation, the script runs
`./fuzz/triage.sh` on every artifact libFuzzer dropped into
`fuzz/crashes/`.  libFuzzer uses distinct prefixes per artifact type --
`crash-*` (sanitizer / SIGSEGV / etc), `timeout-*` (`-timeout` fired),
`leak-*` (LSan finding), `oom-*` (`-rss_limit_mb` exceeded) -- and all
four are triaged.  Artifacts classified as FALSE or CLEAN (includes
signal-pipe hangs and slow-input timeouts with no sanitizer diagnostic)
are moved to `fuzz/crashes_rejected/`.  Only artifacts classified as
REAL (sanitizer or `libFuzzer:` diagnostic within 15 seconds) remain in
`fuzz/crashes/`.

The intent: when you come back to a finished run, anything still in
`fuzz/crashes/` is worth looking at.  Nothing in there is a two-minute
orphan-pipe or an exponential-output `repeat` that happened to trip
libFuzzer's 5-second unit timeout.

The harness also bounds wall-clock parks: `m_max_ops` cannot tick while
a coroutine is parked, so a mutated huge `coroutine-sleep` operand (the
2026-06-06 overnight artifacts decoded a binary-token int32 into a
~9.4-day sleep) used to stall a unit until `-timeout` flagged a false
positive.  `fuzz_trix.cpp` sets `cfg.m_sleep_budget_ms = 500`
(`--sleep-budget` on the CLI), capping TOTAL granted park time per
unit; spent budget turns timed parks into immediate wakes.

### Manual triage (triage.sh)

For ad-hoc checks, deleting stale artifacts, or auditing what landed in
`crashes_rejected/`:

```bash
./fuzz/triage.sh fuzz/crashes/crash-<hash>               # single file
./fuzz/triage.sh fuzz/crashes/crash-*                    # batch
./fuzz/triage.sh --move-false-to /tmp/rejects crashes/*  # triage + move
```

Each artifact is classified as `REAL`, `FALSE`, or `CLEAN`, with a
single-line summary at the end.  Exit status is 0 only if every artifact
is REAL.

## VM heap size

By default the harness uses MinVmSize (256KB).  Use `--vm-size=` to
set a larger heap -- accepts plain bytes or K/M suffixes:

```bash
./fuzz/run.sh --vm-size=1M -max_total_time=28800
./fuzz/run.sh --vm-size=2M -fork=4
```

Larger VMs exercise deeper allocation paths but reduce executions per
second.  For overnight runs, 1M-2M is a good balance.

## Reproduce a crash

```bash
# Triage first -- confirms the artifact is real, not a 2-minute false positive
./fuzz/triage.sh fuzz/crashes/crash-<hash>

# Full reproducer with ASan/UBSan output
./fuzz/fuzz_trix fuzz/crashes/crash-<hash>

# Minimal reproducer with ordinary error output
./trix fuzz/crashes/crash-<hash>
```

If `triage.sh` reports FALSE, `fuzz_trix` will hang for two minutes and
produce no sanitizer output; skip it and delete the artifact.  If it
reports REAL, the other two commands will surface the defect.

## Seed corpus

`fuzz/seeds/` contains small hand-crafted inputs (~50 bytes each)
covering all syntax forms, operator categories, and binary token types.
libFuzzer mutates these to discover new coverage.

The evolving corpus is stored in `fuzz/corpus/` (gitignored, auto-merged).

## Snap-shot thaw harness (`fuzz_thaw`)

`fuzz_thaw` targets `startup_image()` -- the `--image` / `-l` boot path in
`ops_snapshot.inl`: header validation, the memory / user-file / VM-blob
section reads, the overall and per-section CRC gates, `restore_from_header()`,
`apply_fixup_streams()`, stdio reattach, and post-thaw execution over the
restored (fuzzer-corrupted) heap.  The snap-shot format has been through 185
revisions of conditional decode, and thaw runs on **untrusted** input whenever
a user loads an image they did not produce.

```bash
./fuzz/run_thaw.sh                      # single-shot, stops on first event
./fuzz/run_thaw.sh -max_total_time=300  # budget-aware loop, 5 minutes
./fuzz/run_thaw.sh -overnight           # 8-hour run
```

Reproducers land in `fuzz/crashes_thaw/`; the evolving corpus in
`fuzz/corpus_thaw/` (both gitignored).

### Defeating the checksum gate

A snap-shot image is guarded by a CRC-32 over the whole file.  Random mutation
of a valid image essentially never reproduces a matching CRC, so a naive
fuzzer would stall at the checksum arm and never reach the decode / relocation
code that most rewards fuzzing.  A CRC-32 is an integrity check, **not** a
security boundary: an attacker supplying a malicious `--image` recomputes it
for free, so every crash reachable past the CRC with a structurally plausible
header is a real, attacker-reachable defect.

So `fuzz_thaw` installs a **custom mutator** that pins a valid header, fuzzes
the VM-blob body, and re-stamps the fields that must stay internally consistent
(`vm_used`, the VM-base sentinel, and the overall checksum) before handing the
input to the target.  Every generated image therefore clears the gates and
drives the decode path with a valid header whose root offsets point into
corrupted heap data -- modelling the real threat (untrusted image, valid CRC).

### Self-minted template (no committed seed)

The header and a representative boot heap come from a template image the
harness mints **at startup from its own linked engine** (it runs
`(<tmpfile>) snap-shot` once), so the template's `snapshot_version` and
operator-table signature always match the binary under test.  A committed seed
image cannot serve this role -- it would be rejected the moment the format or
operator set changes.  `run_thaw.sh` bootstraps the corpus by asking the
harness to persist that template (`TRIX_THAW_SEED_OUT`), giving the mutator a
full boot heap to corrupt.

At startup the harness validates every structural offset it relies on (magic,
`vm_used`, checksum position, and the CRC model) against the freshly minted
template and aborts loudly on any layout drift -- the same contract as
`tests/snapshot/patch_image.py`.

### Reproduce / triage a thaw crash

Thaw artifacts are images keyed to the fuzzing binary's exact operator-table
signature, so -- unlike `fuzz_trix` artifacts -- the standalone `./trix` cannot
replay them.  Reproduce with the harness binary itself:

```bash
./fuzz/triage.sh fuzz/crashes_thaw/crash-<hash>   # run_thaw.sh does this automatically
./fuzz/fuzz_thaw fuzz/crashes_thaw/crash-<hash>   # full ASan/UBSan reproducer
```

`run_thaw.sh` runs triage with the trix pass skipped and signal-return-code
detection on, so a silenced `SIGSEGV`/`SIGABRT` is still classified REAL on
x86_64.  On aarch64 the libFuzzer signal-pipe race can turn a real, stderr-
silenced assert into a 2-minute hang that triage records as FALSE; re-check any
FALSE thaw artifact there by hand with `./fuzz/fuzz_thaw <artifact>`.

### Note on size and throughput

Snap-shot images are hundreds of KB, so `run_thaw.sh` raises `-max_len` and the
RSS ceiling well above the `fuzz_trix` defaults, and each thaw+execute is
heavier than a script run -- expect lower executions/second but deep per-unit
coverage.
