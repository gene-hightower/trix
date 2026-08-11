#!/usr/bin/env bash
# ====================================================================
# tools/ci-local.sh -- run the .github/workflows/ci.yml gate set locally,
# building the SAME way CI does, so "green here" means "green in CI".
# Run this before every push.
# ====================================================================
# Why this exists (the local-vs-CI gap that kept turning CI red):
#   * build.sh compiles with -DTRIX_DEBUGGER -DTRIX_HEAP_TRACKING, so its
#     binary has vm-gc-stress / debug ops / heap-track keys that CI's cmake
#     build does NOT.  Tests gated on those (e.g. test_gc_stress_*) behave
#     differently -- they pass under build.sh and error under CI.
#     Because of that gap the GC-stress tests ran in no automated gate at
#     all: run_all.sh skips them and the primary cmake build cannot execute
#     them.  This script therefore makes a SECOND cmake build with
#     -DTRIX_DEBUGGER=ON and runs them against it (the "GC-stress suite"
#     gate), so they are covered without the primary build drifting from
#     CI's shipping configuration.
#   * CI's clang-format check is a SEPARATE job (clang-format-20 --dry-run
#     --Werror over all of src/), NOT part of runtests.sh (which runs the
#     unrelated cpp_style.py linter).
#   * CI builds trix + tetrix + chip8 (cmake); the cross-binary snapshot /
#     lockstep tests run against those matching binaries.
# This script builds with cmake (CI's exact config) and runs every ci.yml
# gate, so validating with it removes the gap.
#
# It does NOT clobber your dev binaries: ./trix, ./tetrix, ./chip8 are
# stashed, the cmake-built trio is staged for the run, and the dev binaries
# are restored on exit.  Rebuild your dev tree afterward with ./build.sh.
#
# Usage:  tools/ci-local.sh            # cmake Debug (CI's representative leg)
#   CLANG_FORMAT=clang-format tools/ci-local.sh   # override the formatter
# ====================================================================
set -uo pipefail
cd "$(dirname "$0")/.."
ROOT=$(pwd)

CF=${CLANG_FORMAT:-clang-format-20}
command -v "$CF" >/dev/null 2>&1 || CF=clang-format

TMP=$(mktemp)
FAILED=()
gate() {
    local name="$1"; shift
    printf '  %-32s ' "$name"
    if "$@" >"$TMP" 2>&1; then
        echo "PASS"
    else
        echo "FAIL (rc=$?)"
        tail -8 "$TMP" | sed 's/^/      /'
        FAILED+=("$name")
    fi
}

# --- stash dev binaries; the cmake-built trio is staged below (matches CI) ---
STASH=$(mktemp -d)
cleanup() {
    for b in trix tetrix chip8; do
        [ -e "$STASH/$b" ] && mv -f "$STASH/$b" "$ROOT/$b"
    done
    rm -rf "$STASH" "$TMP"
}
trap cleanup EXIT
for b in trix tetrix chip8; do
    [ -e "$ROOT/$b" ] && mv "$ROOT/$b" "$STASH/$b"
done

echo "== ci-local: cmake build (CI config: Debug, sanitizers ON, no TRIX_DEBUGGER) =="
rm -rf build-ci
if ! cmake -B build-ci -G Ninja -DCMAKE_BUILD_TYPE=Debug >"$TMP" 2>&1; then
    echo "  CONFIGURE FAILED"; tail -15 "$TMP" | sed 's/^/    /'; exit 1
fi
if ! cmake --build build-ci >"$TMP" 2>&1; then
    echo "  BUILD FAILED"; tail -20 "$TMP" | sed 's/^/    /'; exit 1
fi
cp build-ci/trix build-ci/tetrix build-ci/chip8 "$ROOT/"
echo "  build OK -> ./trix ./tetrix ./chip8 (cmake)"

# --- second build: TRIX_DEBUGGER, for the GC-stress gate -------------------
# tests/test_gc_stress_*.trx drive vm-gc-stress / vm-gc-poison, which are
# compiled out of the default build entirely -- run_all.sh skips them and the
# primary cmake build above cannot run them at all.  Without this they execute
# in no automated gate, which is how they sat for the whole GC perf campaign.
# Built into its own tree so the primary binaries staged above are untouched.
echo "== ci-local: cmake build #2 (TRIX_DEBUGGER, for GC-stress) =="
DBG_TRIX=""
if ! cmake -B build-ci-dbg -G Ninja -DCMAKE_BUILD_TYPE=Debug -DTRIX_DEBUGGER=ON >"$TMP" 2>&1; then
    echo "  CONFIGURE FAILED"; tail -15 "$TMP" | sed 's/^/    /'; exit 1
fi
if ! cmake --build build-ci-dbg --target trix >"$TMP" 2>&1; then
    echo "  BUILD FAILED"; tail -20 "$TMP" | sed 's/^/    /'; exit 1
fi
DBG_TRIX="$ROOT/build-ci-dbg/trix"
echo "  build OK -> build-ci-dbg/trix (TRIX_DEBUGGER)"

echo "== ci-local: gates (mirror of ci.yml) =="
gate "Run full test suite"       ./runtests.sh
gate "clang-format (--Werror)"   bash -c "find src trix.h trix.cpp -type f \( -name '*.inl' -o -name '*.h' -o -name '*.cpp' \) -print0 | xargs -0 '$CF' --style=file --dry-run --Werror"
gate "check_readme_examples"     ./tests/check_readme_examples.py
gate "check_doc_links"           ./tests/check_doc_links.py
gate "check_operator_count"      ./tests/check_operator_count.py
gate "check_error_codes"         ./tests/check_error_codes.py
gate "gen_op_effects --check"    ./tools/gen_op_effects.py --check
gate "check_operator_throws"     ./tests/check_operator_throws.py
gate "check_operator_shadows"    bash -c "./tests/check_operator_shadows.py --quiet examples/*.trx"
gate "check_doc_examples"        ./tools/check_doc_examples.py
gate "check_scanner_grammar"     ./tools/check_scanner_grammar.py
gate "check_type_facts"          ./tools/check_type_facts.py
gate "check_collection_facts"    ./tools/check_collection_facts.py
gate "check_reference_facts"     ./tools/check_reference_facts.py
gate "cpp_style --check"         ./tools/cpp_style.py --check
gate "assert_blank_line --check" ./tools/assert_blank_line.py --check
gate "check_signed_char --check" ./tools/check_signed_char.py --check
gate "GC-stress suite"           env TRIX_BIN="$DBG_TRIX" ./tests/run_gc_stress_tests.sh

echo "===================================="
if [ ${#FAILED[@]} -eq 0 ]; then
    echo "  CI-LOCAL: ALL GATES GREEN"
    echo "  (./trix is now the cmake build; run ./build.sh to restore your dev binary)"
    exit 0
else
    echo "  CI-LOCAL: ${#FAILED[@]} GATE(S) FAILED -> ${FAILED[*]}"
    exit 1
fi
