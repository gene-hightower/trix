#!/bin/bash
# run_thaw.sh -- Run the snap-shot THAW fuzzer (fuzz_thaw).
#
# Thin wrapper over run.sh: it points the shared budget-loop + triage + merge
# machinery at the fuzz_thaw harness and its own corpus/crashes directories,
# raises the input/memory bounds for ~hundreds-of-KB snap-shot images, and
# bootstraps a signature-matching seed image before the first run.
#
# Usage (mirrors run.sh):
#   ./fuzz/run_thaw.sh                          # single-shot, stops on first event
#   ./fuzz/run_thaw.sh -max_total_time=300      # budget-aware loop, 5 minutes
#   ./fuzz/run_thaw.sh -overnight               # 8-hour run
#   ./fuzz/run_thaw.sh -max_len=2000000         # explicit override (wins)
#
# Crash reproducers land in fuzz/crashes_thaw/; the evolving corpus in
# fuzz/corpus_thaw/ (both gitignored).  Reproduce / triage exactly as for
# fuzz_trix, but with the fuzz_thaw binary:
#   ./fuzz/triage.sh fuzz/crashes_thaw/crash-<hash>
#   ./fuzz/fuzz_thaw fuzz/crashes_thaw/crash-<hash>

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
FUZZ_BIN="${SCRIPT_DIR}/fuzz_thaw"
CORPUS="${SCRIPT_DIR}/corpus_thaw"
SEEDS="${SCRIPT_DIR}/seeds_thaw"

if [ ! -x "${FUZZ_BIN}" ]; then
    echo "Error: ${FUZZ_BIN} not found. Run fuzz/build.sh first."
    exit 1
fi

mkdir -p "${CORPUS}" "${SEEDS}"

# Bootstrap: drop a full boot-heap image the mutator can corrupt.  The seed MUST
# be minted by this very binary (its snapshot_version + operator-table signature
# have to match), so we ask the harness to persist the template it mints at
# startup.  A committed seed cannot serve this role -- it would be rejected the
# moment the format or operator set changes.  Only done when the corpus is empty
# so an evolved corpus is never clobbered.
if [ -z "$(ls -A "${CORPUS}" 2>/dev/null)" ]; then
    echo "Bootstrapping a signature-matching seed image into ${CORPUS}/ ..."
    TRIX_THAW_SEED_OUT="${CORPUS}/template.img" "${FUZZ_BIN}" -runs=0 "${CORPUS}" >/dev/null 2>&1 || true
    if [ ! -s "${CORPUS}/template.img" ]; then
        echo "Warning: seed bootstrap produced no image; the fuzzer will build one from scratch."
    fi
fi

# Snap-shot images are ~hundreds of KB and each thaw+execute allocates a full VM,
# so raise -max_len and the RSS ceiling well above the fuzz_trix defaults.  A
# user-supplied -max_len / -rss_limit_mb on the command line still wins.
export TRIX_FUZZ_BIN="${FUZZ_BIN}"
export TRIX_FUZZ_CORPUS="${CORPUS}"
export TRIX_FUZZ_SEEDS="${SEEDS}"
export TRIX_FUZZ_CRASHES="${SCRIPT_DIR}/crashes_thaw"
export TRIX_FUZZ_MAX_LEN="${TRIX_FUZZ_MAX_LEN:-1100000}"
export TRIX_FUZZ_RSS_MB="${TRIX_FUZZ_RSS_MB:-4096}"
# Thaw artifacts are images keyed to this binary; the standalone ./trix cannot
# reproduce them, so triage skips its trix pass and uses signal-rc detection.
export TRIX_FUZZ_SKIP_TRIX_PASS=1

exec "${SCRIPT_DIR}/run.sh" "$@"
