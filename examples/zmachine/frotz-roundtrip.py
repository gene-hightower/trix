#!/usr/bin/env python3
"""Cross-check Quetzal save files against Frotz, in both directions.

    ./examples/zmachine/frotz-roundtrip.py [story ...]

For each story it knows a recipe for, this plays the same few commands in both
interpreters, saves, and restores the other one's file:

    ours -> frotz    zmachine.trx saves; dfrotz restores and is asked to prove
                     the state came back
    frotz -> ours    dfrotz saves; zmachine.trx restores and is asked the same

Each recipe's marker is one a *fresh* session does not produce, and that is
asserted before anything else -- without it a restore that silently did nothing
would pass.  The two interpreters' IFhd chunks and frame shapes are compared
too, but not their frame contents: a local can legitimately hold a value that
depends on the interpreter (ZTUU's save leaves one holding an output column,
73 here against Frotz's 11), so only the shape is common ground.

SKIPS rather than fails when dfrotz is absent or a story file is not present:
the catalog is fetched, not shipped (see CATALOG.md), so this cannot be a CI
gate -- it is a local check to run when touching the save path.
"""

import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
TRIX = os.path.join(ROOT, "trix")
ZMACHINE = os.path.join(ROOT, "examples", "zmachine.trx")
CHECK = os.path.join(HERE, "quetzal-check.py")

# story -> what to do before saving, what to ask afterwards, and a marker the
# answer carries once the save has been restored.  The marker has to be absent
# from a fresh session, which main() checks: that is what makes it a marker
# rather than a coincidence, and it has to be absent from the game's opening
# text too, since the whole transcript is what gets searched.
RECIPES = {
    "zork1.z5": {
        "setup": ["open mailbox", "take leaflet"],
        "probe": "inventory",
        "expect": "leaflet",
    },
    "ztuu.z5": {
        # Not "drop sword": the intro describes the sword at length, so its
        # absence from inventory is invisible in a whole-transcript search.
        "setup": ["northeast"],
        "probe": "look",
        "expect": "entrance has been blocked",
    },
}

failures = []


def fail(msg):
    failures.append(msg)
    print("  FAIL  %s" % msg)


def run_trix(story, cmds, save_path):
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        f.write("\n".join(cmds) + "\n")
        script = f.name
    try:
        argv = [TRIX, "--vm-size=8M", ZMACHINE, "--save-file=%s" % save_path,
                "--script", script, story]
        p = subprocess.run(argv, capture_output=True, text=True, timeout=300,
                           stdin=subprocess.DEVNULL)
        return p.stdout + p.stderr
    finally:
        os.unlink(script)


def run_frotz(story, cmds):
    p = subprocess.run(["dfrotz", "-q", "-p", "-h", "400", story],
                       input="\n".join(cmds) + "\n",
                       capture_output=True, text=True, timeout=300)
    return p.stdout + p.stderr


def quetzal_ok(path, story):
    p = subprocess.run([sys.executable, CHECK, path, story],
                       capture_output=True, text=True)
    return p.returncode == 0, p.stdout


def chunks(path):
    data = open(path, "rb").read()
    out, pos = {}, 12
    end = 8 + int.from_bytes(data[4:8], "big")
    while pos < end:
        cid = data[pos:pos + 4].decode("latin-1")
        n = int.from_bytes(data[pos + 4:pos + 8], "big")
        out[cid] = data[pos + 8:pos + 8 + n]
        pos += 8 + n + (n & 1)
    return out


def frame_shapes(stks):
    """Every field of every frame except the locals and the eval stack."""
    out, pos = [], 0
    while pos + 8 <= len(stks):
        ret = int.from_bytes(stks[pos:pos + 3], "big")
        flags, result, args = stks[pos + 3], stks[pos + 4], stks[pos + 5]
        nstack = int.from_bytes(stks[pos + 6:pos + 8], "big")
        out.append((ret, flags, result, args, nstack))
        pos += 8 + 2 * (flags & 0x0F) + 2 * nstack
    return out


def check_story(story, recipe, tmp):
    name = os.path.basename(story)
    print("%s" % name)
    setup, probe, expect = recipe["setup"], recipe["probe"], recipe["expect"]
    tmp = os.path.join(tmp, name)          # frotz asks before overwriting, and
    os.makedirs(tmp, exist_ok=True)        # nothing here answers the prompt

    def restored_ok(where, out):
        if expect.lower() not in out.lower():
            fail("%s: %r missing from the restored session" % (where, expect))
            return False
        return True

    # A fresh session must not carry the marker, or a restore that did nothing
    # at all would pass.
    fresh = run_trix(story, [probe, "quit", "y"], os.path.join(tmp, "unused.qzl"))
    if expect.lower() in fresh.lower():
        fail("%s: a fresh session already shows %r; the recipe proves nothing"
             % (name, expect))
        return

    # --- ours -> frotz
    ours = os.path.join(tmp, "ours.qzl")
    run_trix(story, setup + ["save", "quit", "y"], ours)
    if not os.path.exists(ours):
        fail("%s: zmachine.trx wrote no save file" % name)
        return
    ok, report = quetzal_ok(ours, story)
    if not ok:
        fail("%s: our own save file does not validate\n%s" % (name, report))
    out = run_frotz(story, ["restore", ours, probe, "quit", "y"])
    if "Error reading save file" in out:
        fail("%s: frotz refused our save file" % name)
    elif restored_ok("ours -> frotz", out):
        print("  PASS  ours -> frotz")

    # --- frotz -> ours
    theirs = os.path.join(tmp, "theirs.qzl")
    run_frotz(story, setup + ["save", theirs, "quit", "y"])
    if not os.path.exists(theirs):
        fail("%s: frotz wrote no save file" % name)
        return
    ok, report = quetzal_ok(theirs, story)
    if not ok:
        fail("%s: frotz's save file does not validate against our checker\n%s"
             % (name, report))
    out = run_trix(story, ["restore", probe, "quit", "y"], theirs)
    if restored_ok("frotz -> ours", out):
        print("  PASS  frotz -> ours")

    # --- how close the two encoders came, for the same game state
    a, b = chunks(ours), chunks(theirs)
    if a.get("IFhd") == b.get("IFhd"):
        print("  PASS  IFhd byte-identical to frotz's")
    else:
        fail("%s: our IFhd differs from frotz's for the same game state" % name)
    sa, sb = frame_shapes(a.get("Stks", b"")), frame_shapes(b.get("Stks", b""))
    if sa == sb:
        print("  PASS  %d frame(s), shape-identical to frotz's" % len(sa))
    else:
        fail("%s: our frame shapes differ from frotz's\n    ours  %s\n    frotz %s"
             % (name, sa, sb))
    if a.get("Stks") != b.get("Stks"):
        print("  note  frame contents differ (locals may hold interpreter state)")


def main():
    if not shutil.which("dfrotz"):
        print("SKIP: dfrotz is not installed (apt install frotz)")
        return 0
    if not os.path.exists(TRIX):
        print("SKIP: %s has not been built" % TRIX)
        return 0

    wanted = sys.argv[1:] or [os.path.join(HERE, n) for n in RECIPES]
    ran = 0
    tmp = tempfile.mkdtemp(prefix="/tmp/qz")   # short: frotz caps the filename
    try:
        for story in wanted:
            recipe = RECIPES.get(os.path.basename(story))
            if recipe is None:
                print("SKIP: no recipe for %s" % os.path.basename(story))
                continue
            if not os.path.exists(story):
                print("SKIP: %s is not in the catalog directory" % os.path.basename(story))
                continue
            check_story(story, recipe, tmp)
            ran += 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if ran == 0:
        print("SKIP: no story files to check")
        return 0
    print("%s: %d story/stories, %d problem(s)"
          % ("FAILED" if failures else "OK", ran, len(failures)))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
