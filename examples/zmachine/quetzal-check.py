#!/usr/bin/env python3
"""Validate a Quetzal (.qzl) save file against the format spec.

Written from the Quetzal 1.4 specification rather than from zmachine.trx, so
it is an independent check of what the interpreter writes:

    https://inform-fiction.org/zmachine/standards/quetzal/index.html

    ./quetzal-check.py save.qzl [story.z5]

With a story file, IFhd is cross-checked against the story header and CMem is
decompressed against the story's dynamic memory.  Exits non-zero if anything
fails to parse or disagrees.
"""

import struct
import sys

problems = []


def fail(msg):
    problems.append(msg)
    print("  FAIL  %s" % msg)


def be(data, off, n):
    return int.from_bytes(data[off:off + n], "big")


def parse_chunks(data, start, end):
    """Yield (chunk-id, payload) walking IFF chunks, enforcing even padding."""
    pos = start
    while pos < end:
        if pos + 8 > end:
            fail("chunk header at %d runs past the FORM" % pos)
            return
        cid = data[pos:pos + 4].decode("latin-1")
        clen = be(data, pos + 4, 4)
        body = pos + 8
        if body + clen > end:
            fail("chunk %s claims %d bytes, only %d remain" % (cid, clen, end - body))
            return
        yield cid, data[body:body + clen]
        pos = body + clen + (clen & 1)


def check_ifhd(payload, story):
    if len(payload) != 13:
        fail("IFhd is %d bytes, must be 13" % len(payload))
        return None
    release = be(payload, 0, 2)
    serial = payload[2:8].decode("latin-1")
    checksum = be(payload, 8, 2)
    pc = be(payload, 10, 3)
    print("  IFhd    release %d, serial %s, checksum 0x%04X, pc 0x%06X"
          % (release, serial, checksum, pc))
    if story:
        want = (be(story, 0x02, 2), story[0x12:0x18].decode("latin-1"), be(story, 0x1C, 2))
        if (release, serial, checksum) != want:
            fail("IFhd %r does not match the story %r" % ((release, serial, checksum), want))
    return pc


def decode_cmem(payload, story):
    """XOR-RLE per Quetzal 3.3: literal bytes, and 00 <n-1> for a run of zeros."""
    out = bytearray()
    i = 0
    while i < len(payload):
        b = payload[i]
        i += 1
        if b == 0:
            if i >= len(payload):
                fail("CMem ends inside a zero-run pair")
                return out
            out.extend(b"\0" * (payload[i] + 1))
            i += 1
        else:
            out.append(b)
    if story is not None:
        static = be(story, 0x0E, 2)
        if len(out) > static:
            fail("CMem expands to %d bytes, past static memory at 0x%04X" % (len(out), static))
        out.extend(b"\0" * (static - len(out)))
        return bytes(a ^ b for a, b in zip(out, story[:static]))
    return bytes(out)


def check_stks(payload):
    pos = 0
    frames = 0
    while pos + 8 <= len(payload):
        ret_pc = be(payload, pos, 3)
        flags = payload[pos + 3]
        result = payload[pos + 4]
        args = payload[pos + 5]
        nstack = be(payload, pos + 6, 2)
        nlocals = flags & 0x0F
        discard = bool(flags & 0x10)
        if flags & 0xE0:
            fail("frame %d has reserved flag bits set (0x%02X)" % (frames, flags))
        if frames == 0 and (ret_pc, flags, result, args) != (0, 0, 0, 0):
            # Quetzal 4.8: the first frame stands for the main routine, and
            # every field but its stack-word count is fixed at zero.  Frotz
            # refuses a save whose dummy frame says anything else.
            fail("dummy frame must be all zeros, has ret 0x%06X flags 0x%02X "
                 "result %d args 0x%02X" % (ret_pc, flags, result, args))
        if args not in (0, 1, 3, 7, 15, 31, 63, 127):
            fail("frame %d args-supplied 0x%02X is not 2^n - 1" % (frames, args))
        if discard and result != 0:
            fail("frame %d discards its result but names variable %d" % (frames, result))
        pos += 8 + 2 * nlocals + 2 * nstack
        if pos > len(payload):
            fail("frame %d runs past the end of Stks" % frames)
            return
        print("    frame %d: ret 0x%06X, %d locals, %d stack words, %s"
              % (frames, ret_pc, nlocals, nstack,
                 "discards result" if discard else "result -> var %d" % result))
        frames += 1
    if pos != len(payload):
        fail("Stks has %d trailing bytes" % (len(payload) - pos))
    if frames == 0:
        fail("Stks has no frames; Quetzal requires at least the dummy frame")


def main():
    if len(sys.argv) < 2:
        print(__doc__.strip())
        return 2
    data = open(sys.argv[1], "rb").read()
    story = open(sys.argv[2], "rb").read() if len(sys.argv) > 2 else None

    print("%s (%d bytes)" % (sys.argv[1], len(data)))
    if len(data) < 12 or data[0:4] != b"FORM":
        fail("not an IFF FORM file")
        return 1
    form_len = be(data, 4, 4)
    if 8 + form_len != len(data) and 8 + form_len + (form_len & 1) != len(data):
        fail("FORM length %d does not match the file size %d" % (form_len, len(data)))
    if data[8:12] != b"IFZS":
        fail("form type is %r, not IFZS" % data[8:12])
        return 1

    seen = []
    for cid, payload in parse_chunks(data, 12, 8 + form_len):
        seen.append(cid)
        if cid == "IFhd":
            check_ifhd(payload, story)
        elif cid == "CMem":
            mem = decode_cmem(payload, story)
            note = ""
            if story is not None:
                static = be(story, 0x0E, 2)
                diff = sum(1 for a, b in zip(mem, story[:static]) if a != b)
                note = ", %d of %d dynamic bytes differ from the story" % (diff, static)
            print("  CMem    %d bytes compressed -> %d%s" % (len(payload), len(mem), note))
        elif cid == "UMem":
            print("  UMem    %d bytes uncompressed" % len(payload))
            if story is not None and len(payload) != be(story, 0x0E, 2):
                fail("UMem is %d bytes, static memory begins at 0x%04X"
                     % (len(payload), be(story, 0x0E, 2)))
        elif cid == "Stks":
            print("  Stks    %d bytes" % len(payload))
            check_stks(payload)
        else:
            print("  %s    %d bytes (optional, not checked)" % (cid, len(payload)))

    if "IFhd" not in seen:
        fail("no IFhd chunk")
    if "CMem" not in seen and "UMem" not in seen:
        fail("no CMem or UMem chunk")
    if "Stks" not in seen:
        fail("no Stks chunk")
    if seen and seen[0] != "IFhd":
        fail("IFhd must come first; found %s" % seen[0])

    print("%s: %d problem(s)" % ("FAILED" if problems else "OK", len(problems)))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
