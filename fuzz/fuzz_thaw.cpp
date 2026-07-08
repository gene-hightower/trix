// fuzz_thaw.cpp -- libFuzzer harness for the Trix snap-shot THAW path.
//
// Targets startup_image() (the `--image` / `-l` boot path in ops_snapshot.inl):
// header validation, the memory/user-file/VM-blob section reads, the overall +
// per-section CRC gates, restore_from_header(), apply_fixup_streams(), stdio
// reattach, and post-thaw execution over the restored (fuzzer-corrupted) heap.
//
// The problem this harness solves
// -------------------------------
// A snap-shot image is guarded by a CRC-32 over the whole file.  Random
// mutation of a valid image virtually never reproduces a matching CRC, so a
// naive fuzzer would stall at the checksum arm and never reach the ~140-field
// restore_from_header() decode or the pointer-fixup/relocation code -- exactly
// the "185 format revisions of conditional decode paths" that most reward
// fuzzing.  A CRC-32 is an integrity check, NOT a security boundary: an
// attacker supplying a malicious `--image` file recomputes it for free, so
// every crash reachable past the CRC with a structurally plausible header is a
// real, attacker-reachable defect.
//
// So the custom mutator (below) fuzzes the VM-blob BODY of a valid image and
// then re-stamps vm_used, the VM-base sentinel, and the overall checksum, so
// every generated input clears the gates and drives the decode path with a
// valid header whose root offsets point into corrupted heap data.  This models
// the real threat (untrusted image, valid CRC) and reaches the high-risk code.
//
// The template image is minted at startup from THIS harness's own linked
// engine (see mint_template), so its snapshot_version and operator-table
// signature always match the binary under test -- no committed seed to rot
// when the format or operator set changes.
//
// Build:  see build.sh (requires clang with -fsanitize=fuzzer)
// Run:    ./fuzz/run_thaw.sh                    # bootstraps a seed, then fuzzes
//         ./fuzz/run_thaw.sh -max_total_time=300

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>

#include <fcntl.h>
#include <sys/mman.h>
#include <unistd.h>
#include <zlib.h>  // crc32 -- same IEEE 802.3 polynomial the engine uses (see snapshot.inl)

#include "../trix.h"

// libFuzzer's built-in mutator, called from our custom mutator to do the actual
// byte-level mutation before we re-wrap the result as a valid image.
extern "C" size_t LLVMFuzzerMutate(uint8_t *data, size_t size, size_t max_size);

// ── Structural layout facts (SnapShotHeader is private to class Trix, so -- like
//    tests/snapshot/patch_image.py -- we work on raw bytes by offset).  All of
//    these are verified against the freshly minted template in mint_template(),
//    which aborts loudly on drift. ────────────────────────────────────────────
static constexpr size_t kHeaderSize = 608;                     // sizeof(SnapShotHeader)
static constexpr size_t kOffVmUsed = 24;                       // uint32_t vm_used
static constexpr size_t kOffVmGlobalUsed = 28;                 // uint32_t vm_global_used
static constexpr size_t kOffVmCapacity = 32;                   // uint32_t vm_capacity
static constexpr size_t kOffChecksum = 600;                    // crc32_t checksum (last field)
static constexpr uint8_t kSentinel[4] = {'T', 'R', 'I', 'X'};  // magic AND VM-base sentinel

// ── The minted template and derived sizing. ──────────────────────────────────
static uint8_t *g_template = nullptr;  // full valid image bytes
static size_t g_template_size = 0;
static Trix::vm_size_t g_vm_size = Trix::DefaultVmSize;  // VM heap to thaw into (== template's vm_capacity)
static size_t g_body_cap = 0;                            // max body length: vm_capacity - header

static uint32_t rd_u32(const uint8_t *p, size_t off) {
    uint32_t v = 0;
    std::memcpy(&v, p + off, sizeof(v));
    return v;
}

static void wr_u32(uint8_t *p, size_t off, uint32_t v) {
    std::memcpy(p + off, &v, sizeof(v));
}

// Overall CRC: crc32 over the whole image with the 4 checksum bytes zeroed.
// Matches thaw's incremental accumulation for a stream-free image (file ==
// header + VM blob), and patch_image.py's overall_crc().
static uint32_t overall_crc(const uint8_t *img, size_t len) {
    uint32_t saved = rd_u32(img, kOffChecksum);
    auto *m = const_cast<uint8_t *>(img);
    wr_u32(m, kOffChecksum, 0);
    auto crc = static_cast<uint32_t>(::crc32(0, img, static_cast<uInt>(len)));
    wr_u32(m, kOffChecksum, saved);  // restore -- never mutate the caller's buffer
    return crc;
}

[[noreturn]] static void die(const char *msg) {
    std::fprintf(stderr, "fuzz_thaw: fatal: %s\n", msg);
    std::fflush(stderr);
    _exit(1);
}

// Run a Trix program that writes a fresh snap-shot to `out_path`, using this
// harness's own engine so version + operator-table signature match exactly.
// Non-sandbox (snap-shot is disabled in sandbox mode).  Returns on success.
static void run_snapshot_script(const char *out_path) {
    char script[PATH_MAX + 32];
    int n = std::snprintf(script, sizeof(script), "(%s) snap-shot\n", out_path);
    if ((n <= 0) || (static_cast<size_t>(n) >= sizeof(script))) {
        die("template path too long");
    }

    // Feed the script on stdin via a memfd (same trick fuzz_trix uses for input).
    auto saved_stdin = ::dup(STDIN_FILENO);
    auto fd = ::memfd_create("thaw_tmpl_script", 0);
    if (fd < 0) {
        die("memfd_create for template script failed");
    }
    static_cast<void>(::write(fd, script, static_cast<size_t>(n)));
    ::lseek(fd, 0, SEEK_SET);
    ::dup2(fd, STDIN_FILENO);
    ::close(fd);

    {
        Trix::Config cfg{};
        cfg.m_mode = Trix::StartupMode::StdIn;
        cfg.m_sandbox = false;  // snap-shot writes a file
        cfg.m_quiet = true;
        // The constructor runs the script synchronously and catches all exceptions.
        Trix trx(Trix::DefaultVmSize, cfg);
    }

    ::dup2(saved_stdin, STDIN_FILENO);
    ::close(saved_stdin);
}

// Mint the template image and validate every structural offset this harness
// relies on.  Called once from LLVMFuzzerInitialize.
static void mint_template() {
    char path[] = "/tmp/trix_fuzz_thaw_tmpl_XXXXXX";
    int tfd = ::mkstemp(path);
    if (tfd < 0) {
        die("mkstemp for template failed");
    }
    ::close(tfd);  // snap-shot writes "<path>.tmp" then renames onto `path`

    run_snapshot_script(path);

    int rfd = ::open(path, O_RDONLY);
    if (rfd < 0) {
        die("template image was not produced (snap-shot failed?)");
    }
    off_t sz = ::lseek(rfd, 0, SEEK_END);
    ::lseek(rfd, 0, SEEK_SET);
    if (sz < static_cast<off_t>(kHeaderSize)) {
        die("template image shorter than a header");
    }
    g_template_size = static_cast<size_t>(sz);
    g_template = static_cast<uint8_t *>(std::malloc(g_template_size));
    if (g_template == nullptr) {
        die("malloc for template failed");
    }
    ssize_t got = ::read(rfd, g_template, g_template_size);
    ::close(rfd);
    ::unlink(path);
    if (got < 0 || static_cast<size_t>(got) != g_template_size) {
        die("short read of template image");
    }

    // ── Validate the structural assumptions, aborting on any drift. ──
    if (std::memcmp(g_template, kSentinel, 4) != 0) {
        die("template magic is not 'TRIX' (layout drift)");
    }
    uint32_t vm_used = rd_u32(g_template, kOffVmUsed);
    uint32_t vm_global_used = rd_u32(g_template, kOffVmGlobalUsed);
    uint32_t vm_capacity = rd_u32(g_template, kOffVmCapacity);
    if (vm_global_used != 0) {
        die("template unexpectedly has a global VM region (mint state should be local-only)");
    }
    // file == [header][vm_used bytes] for a stream-free, global-free image.
    if (kHeaderSize + vm_used != g_template_size) {
        die("template size != header + vm_used (offset 24 drift)");
    }
    if (rd_u32(g_template, kHeaderSize) != rd_u32(kSentinel, 0)) {
        // VM-base sentinel: first 4 bytes of the VM blob must also be 'TRIX'.
        die("template VM-base sentinel is not 'TRIX' (offset/layout drift)");
    }
    // Overall CRC must reproduce the stored checksum (validates offset 600 + our
    // crc model against the engine that wrote the image).
    if (overall_crc(g_template, g_template_size) != rd_u32(g_template, kOffChecksum)) {
        die("template checksum recomputation mismatch (CRC model or offset drift)");
    }

    // Thaw into a VM exactly as large as the image was frozen from, so vm_used
    // fits and (were a global region ever present) capacities would match.
    size_t cap = vm_capacity;
    if (cap < Trix::MinVmSize) {
        cap = Trix::MinVmSize;
    }
    if (cap > Trix::MaxVmSize) {
        cap = Trix::MaxVmSize;
    }
    g_vm_size = static_cast<Trix::vm_size_t>(cap);
    g_body_cap = (vm_capacity > kHeaderSize) ? (vm_capacity - kHeaderSize) : 0;

    // Optional bootstrap: persist the minted (signature-matching) template so the
    // run script can seed the corpus with a full boot heap for the mutator to
    // corrupt.  A committed seed cannot serve this role -- it would rot the moment
    // the format or operator set changes.  Opt-in only; the harness is otherwise
    // read-only against the filesystem.
    if (const char *out = std::getenv("TRIX_THAW_SEED_OUT"); out != nullptr) {
        int ofd = ::open(out, O_CREAT | O_WRONLY | O_TRUNC, 0644);
        if (ofd >= 0) {
            static_cast<void>(::write(ofd, g_template, g_template_size));
            ::close(ofd);
            std::fprintf(stderr, "fuzz_thaw: wrote seed template to %s\n", out);
        }
    }

    std::fprintf(stderr,
                 "fuzz_thaw: template minted (%zu bytes, vm_used=%u, vm_capacity=%u); "
                 "structural self-check passed\n",
                 g_template_size,
                 vm_used,
                 vm_capacity);
    std::fflush(stderr);
}

extern "C" int LLVMFuzzerInitialize(int * /*argc*/, char *** /*argv*/) {
    mint_template();
    return 0;
}

// Custom mutator: pin a valid header, fuzz the VM-blob body, and re-stamp the
// fields that must stay internally consistent (vm_used, VM-base sentinel,
// overall checksum) so the input clears every gate and reaches the decode path.
extern "C" size_t LLVMFuzzerCustomMutator(uint8_t *data, size_t size, size_t max_size, unsigned int /*seed*/) {
    // Let libFuzzer mutate whatever it has (header region included -- we overwrite
    // it below, so only the body edits survive).
    size_t n = LLVMFuzzerMutate(data, size, max_size);

    if (max_size < kHeaderSize + 4) {
        return n;  // cannot fit a header + sentinel; leave as-is (exercises short-input rejects)
    }

    // Pin the header to the valid template.
    std::memcpy(data, g_template, kHeaderSize);

    // Body = mutated bytes past the header, clamped to the VM capacity and buffer.
    size_t body = (n > kHeaderSize) ? (n - kHeaderSize) : 0;
    size_t cap = max_size - kHeaderSize;
    if (body > cap) {
        body = cap;
    }
    if (body > g_body_cap) {
        body = g_body_cap;
    }
    if (body < 4) {
        body = 4;  // room for the VM-base sentinel
    }

    std::memcpy(data + kHeaderSize, kSentinel, 4);  // VM-base sentinel
    wr_u32(data, kOffVmUsed, static_cast<uint32_t>(body));
    wr_u32(data, kOffVmGlobalUsed, 0);

    size_t total = kHeaderSize + body;
    wr_u32(data, kOffChecksum, 0);
    wr_u32(data, kOffChecksum, static_cast<uint32_t>(::crc32(0, data, static_cast<uInt>(total))));
    return total;
}

extern "C" int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
    if ((size < kHeaderSize) || (size > g_template_size * 4 + kHeaderSize)) {
        return 0;
    }

    // Materialize the image in a memfd and thaw it via the constructor's --image
    // path (cfg.m_filename -> /proc/self/fd/N).
    auto fd = ::memfd_create("fuzz_thaw_img", 0);
    if (fd < 0) {
        return 0;
    }
    static_cast<void>(::write(fd, data, size));
    ::lseek(fd, 0, SEEK_SET);

    char img_path[64];
    std::snprintf(img_path, sizeof(img_path), "/proc/self/fd/%d", fd);

    // Silence Trix stdout/stderr (thaw diagnostics + post-thaw program output).
    auto saved_stdout = ::dup(STDOUT_FILENO);
    auto saved_stderr = ::dup(STDERR_FILENO);
    auto devnull = ::open("/dev/null", O_WRONLY);
    if (devnull >= 0) {
        ::dup2(devnull, STDOUT_FILENO);
        ::dup2(devnull, STDERR_FILENO);
        ::close(devnull);
    }

    {
        Trix::Config cfg{};
        cfg.m_mode = Trix::StartupMode::ImageFile;
        cfg.m_filename = img_path;
        cfg.m_sandbox = true;  // startup_image is not sandbox-gated; keeps post-thaw exec safe
        cfg.m_quiet = true;
        cfg.m_max_ops = 1'000'000;    // bound post-thaw execution over corrupt heap
        cfg.m_sleep_budget_ms = 500;  // bound wall-clock parks (see fuzz_trix rationale)
        cfg.m_timeout_ms = 2000;      // in-process deadline before libFuzzer's external -timeout

        // Constructor thaws (startup_image) then, on success, runs interpreter();
        // all exceptions are caught internally.
        Trix trx(g_vm_size, cfg);
    }

    // Restore stdio for the next iteration.
    ::dup2(saved_stdout, STDOUT_FILENO);
    ::close(saved_stdout);
    ::dup2(saved_stderr, STDERR_FILENO);
    ::close(saved_stderr);
    ::close(fd);

    return 0;
}
