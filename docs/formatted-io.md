<!--
   ______    _
  /_  __/___(_)_  __
   / / / __/ /\ \/ /       Stack-Based Interpreter & VM
  / / / / / /  > · <      C++23 · Single-Header Library
 /_/ /_/ /_/  /_/\_\     Copyright 2026 Mark Guidarelli

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    https://www.apache.org/licenses/LICENSE-2.0
-->

# Trix Formatted I/O: the print / parse round trip

Trix's `print-fmt` and `scan-fmt` families are not two unrelated facilities —
they are a deliberate **inverse pair** over the type system: one renders typed
values to text, the other reads that text back into typed values, and they
share a single `{id:spec}` grammar.  This guide is about what that buys you —
the **round-trip guarantee**, the **type-safe parse** model, and (honestly)
**where the round trip stops** — rather than the field grammar itself.

For the grammar, every type letter, and a C-printf / Python-format comparison,
see the [Format String Cheat Sheet](format-cheatsheet.md) and
[`trix-reference.md` § 3.19](trix-reference.md).  This guide assumes that
reference and focuses on capability.

---

## 1. One grammar, two directions

The same replacement-field grammar drives both directions and several other
surfaces, so there is one formatting engine to learn, not three:

| Direction | Operators | Targets |
| --- | --- | --- |
| Render | `print-fmt` / `fprint-fmt` / `sprint-fmt` | stdout / a Stream / a String buffer |
| Render (array args) | `aprint-fmt` / `afprint-fmt` / `asprint-fmt` | same, with args passed as an array |
| Parse | `sscan-fmt` / `fscan-fmt` | a String / a readable Stream |
| Also reuses the engine | `=`, `==`, `stack`, `print-stack`, `\{name}` interpolation | — |

The render family takes its arguments **after a `mark`** (`{0}` is the first
value above the mark); the array family takes a single array instead.  Render
returns `count true` on success or `count false` if a String buffer was too
small — it does **not** throw for an overflowing buffer:

```
(The answer is {0}) mark 42 print-fmt     % prints "The answer is 42", leaves: 16 true
32 string ({0:>10s}) mark (hi) sprint-fmt % leaves "hi" right-aligned in width 10 (8 leading spaces), true
```

---

## 2. The round-trip guarantee

A value is **round-trippable** when formatting it and reading the text back
yields an equal value.  Trix gives this for scalars and the three structural
composites, through the `{:O}` ("object") type plus the radix / prefix / suffix
scalar forms — all of which emit **valid Trix scanner source**.

The read-back mechanism differs by shape, and that distinction matters:

* **Scalars** are a single token — read them back with `token`.
* **Composites** are a constructor *expression* (`[ … ]`, `<< … >>`,
  `{{ … }}`) — read them back by **executing** the text.

### Scalars (via `token`)

```
32 string ({0:.16d}) mark 255  sprint-fmt pop   % "16#ff"  -- radix form
32 string ({0:#x})   mark 255  sprint-fmt pop   % "0xff"   -- prefixed form
32 string ({0:O})    mark 200b sprint-fmt pop   % "200b"   -- value + type suffix

(16#ff) token pop exch pop   % => 255   (Integer)
(0xff)  token pop exch pop   % => 255
(200b)  token pop exch pop   % => 200b  (Byte)
```

### Floats round-trip *exactly*

`{:O}` emits the shortest decimal that reparses to the identical IEEE value,
tagged with the precision suffix (`r` for Real, `d` for Double), so no digits
are lost:

```
32 string ({0:O}) mark 0.1   sprint-fmt pop   % "0.1r"
32 string ({0:O}) mark 0.1d  sprint-fmt pop   % "0.1d"
1.0d 3.0d div /third exch def
32 string ({0:O}) mark third sprint-fmt pop   % "0.3333333333333333d"

(0.3333333333333333d) token pop exch pop third eq   % => true
```

### Composites (via `make-executable exec`)

```
64 string ({0:O}) mark [ 1 2 3 ] sprint-fmt pop                % "[1i 2i 3i]"
64 string ({0:O}) mark << /x 1 >> sprint-fmt pop               % "<</x 1i>>"
64 string ({0:O}) mark [ 7 8 9 ] set-from-array sprint-fmt pop % "{{8i 7i 9i}}" (set order unspecified)

([1i 2i 3i])  make-executable exec   % => the array  [ 1 2 3 ]
(<</x 1i>>)   make-executable exec   % => the dict   << /x 1 >>
({{8i 7i 9i}}) make-executable exec  % => the set    (membership preserved; order is not)
```

The `{:O}` form recurses into nested composites and is what `==` and
`print-stack` use, so "print it with `==`, paste it back into a script" works
for any nesting of arrays, dicts, and sets.

---

## 3. Where the round trip stops

The guarantee is precise, which means it has edges.  `{:O}` is a faithful
*constructor* for scalars, arrays, dicts, and sets; for everything else it is a
**human-readable display form**, not source.  Do not expect these to reparse:

| Form | `{:O}` output | Round-trips? |
| --- | --- | --- |
| Integer / radix / prefix forms | `42i`, `16#ff`, `0xff` | yes (`token`) |
| Real / Double | `0.1r`, `0.1d` | yes, exactly (`token`) |
| Byte | `200b` | yes (`token`) |
| String | encoded string form | yes (`token`) |
| Array / Dict / Set | `[…]` / `<<…>>` / `{{…}}` | yes (`exec`) |
| **Tagged** | `/ok 42i` | **no** — that is a name then a value, not a `tag` call |
| **Record** | `--record {/x: 1i}--` | **no** — display wrapper |
| **Curry** | `--curry arg {proc}--` | **no** — display wrapper |
| **Stream / Coroutine / opaque handle** | label form | **no** — runtime identity, not data |

Two more limits even within the round-trippable composites:

* **Depth** is capped at 16 levels; deeper structure prints `...`.
* **Cycles** are detected and printed as `--cycle--` rather than looping.

So `{:O}` is safe for serializing plain data trees (config, fixtures,
debug dumps you intend to paste back).  For arbitrary object graphs — cycles,
tagged sums, records, closures — reach for whole-VM `snapshot` / `thaw` or
`object-to-binary-token` instead; those are binary and identity-preserving,
where `{:O}` is text and value-preserving.

The plain `{:s}` / default form is the *other* non-round-tripping case by
design: it is the friendly form (`=` uses it), lossy where `{:O}` is faithful
(e.g. it does not append type suffixes).  Use `{:s}` for humans, `{:O}` for a
parser.

---

## 4. Type-safe parsing

`scan-fmt` is the inverse of `{:O}`-style rendering, and it is **strict**: each
replacement field is checked against the **type of the target slot** you supply
above the mark.

* A **numeric target** is a value of the wanted type — `0` (Integer), `0u`
  (UInteger), `0.` (Real), `0b` (Byte) — acting as a type slot.  `null` means
  "auto-detect the natural type".
* A **String target** is a caller-sized buffer (`N string`); the parsed text is
  written into it.

```
(name=bob age=30) (name={0:s} age={1:d}) mark 32 string 0 sscan-fmt
% => "bob"  30  2          (values below the count; count = fields filled)

(42) ({0:d}) mark null sscan-fmt   % => 42  1   ; null slot auto-detects Integer
```

Mismatches are **caught, not coerced** — each is a distinct, catchable error:

| Error | Cause |
| --- | --- |
| `scan-type-fail` | parsed literal's type ≠ target slot's type (e.g. `42.5` into a `{:d}` Integer slot, or `42u` into an `0i` slot); no lossy conversion |
| `scan-match-fail` | a literal in the format does not match the input (`{0:d},{1:d}` on `12;34`) |
| `scan-input-fail` | a String target buffer is too small, or input ran out at a field |

```
{ (42.5) ({0:d}) mark 0 sscan-fmt } try          % => /scan-type-fail
{ (12;34) ({0:d},{1:d}) mark 0 0 sscan-fmt } try % => /scan-match-fail
```

The target type acts as an implicit suffix when the input carries none (`65`
into a Byte slot parses as `65b`), but ScanFmt never silently narrows.  If you
*want* coercion, scan into a `null` (or wider) slot and `cast`/`coerce`
afterward.

---

## 5. Strengths — and when to reach for it

What distinguishes Trix's formatted I/O from the field:

* **It is a symmetric, type-checked parse, not regex.**  Most scripting
  languages ship rich `printf`/`format` but parse with patterns or regex
  (Lua patterns, Python `re`, Factor PEG/combinators).  Trix ships a real
  `scanf` that mirrors its `printf` field-for-field — and, unlike C `scanf`
  (memory-unsafe) or Go `Sscanf` (loose coercion) or Tcl `scan` (stringly
  typed), Trix's is **type-strict with named errors**.

* **Round-trippable output is first-class.**  `{:O}` / radix / suffix forms are
  *designed* to reparse, including **exact floats**.  This is the spirit of
  Lisp `prin1` / Python `repr` / Go `%#v`, but exposed as format *types* and
  extended with radix and type-suffix round-tripping.

* **One engine, several surfaces.**  `=`, `==`, `print-stack`, and `\{name}`
  string interpolation all run through the same code, so display and
  serialization stay consistent.

* **A no-throw render contract.**  `(count, bool)` lets a caller handle a
  too-small buffer without an exception — convenient in concatenative flow.

Reach for which tool:

| Goal | Use |
| --- | --- |
| Human-readable output | `{:s}` / `=` |
| Text you intend to parse back (data trees) | `{:O}` + `token` / `exec` |
| Structured parse of typed fields | `sscan-fmt` / `fscan-fmt` |
| Compact, identity-preserving persistence (cycles, closures, whole VM) | `snapshot` / `thaw`, `object-to-binary-token` |
| Free-form / pattern extraction | regex (`regex-*`) |

What Trix's format mini-language does **not** do, relative to the most powerful
peers: it has no in-string iteration / conditional directives (Common Lisp
`format`'s `~{~}` / `~[~]`), and no locale-aware grouping or keyword fields
(Python `{:,}` / `{name}` in the fmt ops — though `\{name}` interpolation does
resolve names).  Loop in Trix code, not in the format string.

---

## Where to go next

  * **Field grammar, every type letter, C-printf / Python table:**
    [Format String Cheat Sheet](format-cheatsheet.md).
  * **Per-op stack effects:** [`trix-reference.md`](trix-reference.md) § 3.19.
  * **Strings, UTF-8, parsing:** [String Processing](string-processing.md).
  * **Streams (file / memory / process I/O):** [Streams and I/O](streams-io.md).
  * **Whole-VM persistence:** [Save / Restore](save-restore.md), snapshot/thaw.
  * **Engine internals (maintainer-side):** `src/printfmt.inl`, `src/scanfmt.inl`.
