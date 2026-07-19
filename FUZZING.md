# Fuzzing

## Active targets

`fuzz/fuzz_targets/path_validation.rs` feeds arbitrary UTF-8 (when valid) and
arbitrary little-endian UTF-16 units to both path validators. The target checks
the no-panic property and exercises traversal, root, drive, UNC, NUL, and
unpaired-surrogate handling. It has no filesystem side effects.

`fuzz/fuzz_targets/header_envelope.rs` feeds arbitrary bytes to the production
bounded envelope parser under reduced input/header/SFX limits and a finite work
budget. It also places a CRC-correct minimal plain envelope after an arbitrary
SFX prefix, exercising valid discovery and attacker-controlled false
candidates without bypassing production CRC checks.

`fuzz/fuzz_targets/next_header.rs` wraps arbitrary bytes in CRC-correct start
and next headers, then also forces them into a bounded plain Header body. It
invokes the production raw parser, exact property readers, graph validator, and
model conversion with reduced count/allocation limits and a finite work
budget. Recomputing both CRC layers ensures mutations reach nested validation.
The harness enables the documentation-hidden `unstable-internals` feature;
applications do not need and must not rely on that parser/model surface.

`fuzz/fuzz_targets/validated_graph.rs` constructs a complete small StreamsInfo
record and derives bind-pair domains from fuzz bytes. It keeps the surrounding
grammar and CRCs valid so cycles, duplicate inputs/outputs, roots, and
declaration-order variations reach the isolated production graph validator.

`fuzz/fuzz_targets/decoding.rs` invokes `Archive::open_bytes` and
`Archive::open_bytes_with_password`, then `Archive::verify`, with reduced
header/count/property/dictionary/input/output/KDF/recursion limits and a finite
work budget. Valid seeds reach encoded/encrypted-header resolution, arbitrary
graph execution, every Phase 3-5 decoder and filter, password/KDF handling, and
packed/folder/member CRC paths through the public API. Mutations retain the
no-panic, bounded-work contract even when an earlier CRC or parser layer rejects
them.

The same target also wraps every input into a CRC-correct one-member Copy
archive and into one selected single-input core coder archive. These generated
envelopes keep signature/start/next-header grammar and ranges valid, so
seedless CI runs reach production graph execution and Copy CRC finalization.
The selected one-coder wrappers directly exercise LZMA/LZMA2, all
single-input filters, Deflate, Deflate64, BZip2, PPMd, Brotli, LZ4, Zstandard,
and bounded AES/KDF error paths without disabling an integrity check in
production code. A second generated wrapper declares an unknown output size
for the closed allowlist of boundary- or EOS-terminated methods. BCJ2
four-input success coverage uses the corpus-free generated `7zz` oracle and
deterministic unit tests; malformed graph/input coverage remains in the fuzz
target.

`fuzz/fuzz_targets/volumes.rs` sends arbitrary part boundaries, missing terminal
parts, excessive part counts, and CRC-correct Copy archives through
`Archive::open_volumes` and `MemoryVolumeProvider`. Reduced volume/input/output
limits and finite work budgets exercise exact sequential discovery,
cross-boundary parsing/decoding, aggregate allocation checks, and missing/limit
termination through the public API.

Normal tests complement fuzzing with exhaustive decoding of every one- and
two-byte 7z integer encoding, all truncations of the nine-byte form, all split
points of the standard CRC vector, all byte-prefix truncations of valid outer
and nested headers, CRC-correct mutation sweeps, valid graph chains of lengths
one through eight, the 100,000-entry boundary, every prefix of small LZMA and
LZMA2 EOS streams and a raw Deflate final-block stream, truncated LZMA range
initialization, truncated BCJ2 range input, corrupt Copy/member CRCs, every
prefix of a stored Deflate64 block, and decoder output/work/cancellation
limits.

Solid-output regressions additionally cover pre-decode limits for every known
substream, an unknown final member capped to one entry allowance, typed
pre-decode rejection of an unknown non-final member, and proportional work
charging across an x86 BCJ input with no branch opcodes.

The targets use `libfuzzer-sys` 0.4.13. Its NCSA license term is recorded as an
exact, fuzz-only cargo-deny exception; it is not a runtime dependency or runtime
license exception.

Run a smoke test with a nightly toolchain and cargo-fuzz:

```text
cargo +nightly fuzz run path_validation -- -runs=10000
cargo +nightly fuzz run header_envelope -- -runs=10000
cargo +nightly fuzz run next_header -- -runs=10000
cargo +nightly fuzz run validated_graph -- -runs=10000
cargo +nightly fuzz run decoding -- -runs=10000
cargo +nightly fuzz run volumes -- -runs=10000
```

The fuzz package enables `un7z/unstable-internals` because three structural
targets require deep parser/model visibility; other targets do not call those
exports and continue to enter through the stable archive API. To confirm
the standalone harness graph and license policy before running:

```text
cargo check --manifest-path fuzz/Cargo.toml --bins --locked
cargo deny --manifest-path fuzz/Cargo.toml check
```

Generated corpus and crash artifacts are ignored. Minimized, non-sensitive
regressions move into normal unit/integration tests with documented provenance.
No private or external archive corpus is required for a seedless smoke run:
the structural targets synthesize valid envelopes/graphs and `decoding`
constructs CRC-correct Copy and selected-method wrappers from every input.

## Planned targets

| Target | Phase | Primary properties |
| --- | ---: | --- |
| Header-envelope parser | 2 | Active: no panic; bounded scan/ranges; CRCs; cancellation/work limits |
| Nested raw header parser | 2 | Active: bounded reads/allocations; exact property consumption |
| CRC-correct header mutation | 2 | Active in `next_header`: semantic validation beyond CRC gates |
| Validated graph builder | 2/3 | Active: index uniqueness, roots, cycles, totals, deterministic schedule |
| Decoder dispatch and loops | 3+ | Active in `decoding`: public dispatch, encoded headers, output/dictionary/work bounds, cancellation, CRCs, no stalls |
| Volume discovery/logical reads | 2/4 | Active in `volumes`: exact sequential requests, count/byte limits, missing parts, cross-boundary ranges |
| Path validation | 1 | No panic and stable safety classification |

Fuzz targets invoke the same production validation and limits as public APIs;
they do not bypass CRC or invent sizes. Future method-specific targets may
increase state-machine depth beyond the shared public decoder target.

## Python FFI coverage

Phase 7 adds no parser, model, graph, decoder, crypto, volume-assembly, or path
implementation to fuzz independently. Arbitrary archive bytes entering
`un7z.open_bytes` reach the same production functions already exercised by
`header_envelope`, `next_header`, `validated_graph`, and `decoding`; Python
volumes reach the same `VolumeProvider` logic exercised by `volumes`.

The FFI-only state space is covered by deterministic installed-wheel tests for
invalid archive bytes, CRC failure, unsafe raw UTF-16 names, provider absence,
limits, cancellation, callback exception identity, callback `False`, writer
delivery, and concurrent Python progress during detached Rust work. The native
unwind helper has a Rust regression that injects an unwind and observes
containment. A future dedicated CPython fuzz harness must be added only if the
adapter gains independent conversion grammar or stateful callback scheduling;
it must not bypass the existing core fuzz targets.

## Seed and mutation strategy

- Seed the raw parser with generated minimal plain/encoded headers and admit
  any future external seed only after its provenance review.
- Maintain a mutator that recomputes start/next-header CRCs so changes reach
  nested validation.
- Seed graph fuzzing with small valid multi-input and non-declaration-order
  graphs, then mutate counts, bindings, and packed indices.
- Seed volume fuzzing with gaps, empty parts, short reads, exact-boundary reads,
  encrypted-block boundaries, and excessive totals.
- Never place confidential archives, real passwords, decrypted headers, or
  customer paths in a fuzz corpus.

## Triage

Every crash, timeout, excessive allocation, non-progress loop, Miri failure,
checksum bypass, or inconsistent error classification is retained and treated
as a security issue until explained. Fixes add a minimized deterministic test.
Fuzz duration, toolchain, target, corpus revision, and peak memory are recorded
when sustained campaigns begin in Phase 2.

## Current smoke evidence

On 2026-07-18, `header_envelope`, `next_header`, `validated_graph`, and
`path_validation` each completed 10,000 executions with no crash using the
locally available stable-built libFuzzer runner. Those runs lacked sanitizer
and coverage instrumentation, as their warnings reported, so they are only
harness/no-panic smoke checks and do not replace the nightly `cargo-fuzz` CI
job.

On the same date, `decoding` completed 10,000 stable-built executions with no
crash after loading copied seeds for all ten supported method fixtures. The
runner reported a 179,082-byte, ten-file seed set and 26 MiB RSS at
initialization. It also reported missing sanitizer hooks and no coverage
instrumentation, so this is only a public-API harness/seed no-panic smoke run,
not a coverage or memory benchmark. The temporary seed directory was separate
from and did not modify the pinned corpus.

After CRC-correct generated Copy and selected single-input coder wrappers were
added, the same target also completed a 1,000-execution seedless stable-built
smoke run. That run began from the empty corpus and reached the generated valid
envelopes without external fixtures. It had the same missing-sanitizer and
missing-coverage limitations; nightly `cargo fuzz` remains the authoritative
CI smoke gate.

After Phase 4 decoder/password selectors and the volume target were added,
`decoding` and `volumes` each completed another 1,000-execution seedless
stable-built smoke run on 2026-07-18 with no crash. Each run reported 26-27 MiB
RSS and the same missing sanitizer hooks/no coverage instrumentation; these are
harness no-panic checks, not coverage or peak-memory claims. All six fuzz
binaries also compiled from the separately locked fuzz package.

After the Phase 5 selectors, unknown-output wrappers, and remaining methods
were added, all six fuzz binaries rebuilt and passed strict Clippy. The
`decoding` binary completed another 1,000-execution seedless stable-built smoke
run on 2026-07-18 with no crash and 27 MiB reported RSS. The runner again
reported missing sanitizer hooks and no coverage instrumentation, so this is a
harness no-panic check rather than coverage or peak-memory evidence.

After the Phase 6 API visibility change, all six fuzz binaries rebuilt with
the package-level `unstable-internals` feature and passed strict Clippy. Each
fresh binary completed a 1,000-execution seedless stable-built smoke run on
2026-07-18 with no crash. The runners reported 25-27 MiB RSS and again warned
that sanitizer hooks and coverage instrumentation were unavailable, so these
are harness/no-panic checks only; the nightly cargo-fuzz CI jobs remain the
authoritative instrumented gate.

Phase 7 changes no fuzz target or archive-processing implementation. The six
core targets still compile and run under the root workflow, while the separate
binding workflow exercises FFI-specific behavior through installed wheels. No
new fuzz-coverage claim is made for PyO3 or CPython internals.

After the repository owner confirmed that no separate valid or malformed
corpus is available, all six targets completed a fresh 10,000-execution
coverage-guided run on 2026-07-18. The local Homebrew stable sysroot could not
link `rustc-stable_rt.asan`; the local command therefore used cargo-fuzz 0.13.2
with `RUSTC_BOOTSTRAP=1 --sanitizer none`. This is real sanitizer-coverage
feedback, but it is not an AddressSanitizer result and does not replace the
nightly ASan CI gate.

Final libFuzzer observations were:

| Target | Coverage counters | Feature counters | Corpus entries | RSS |
| --- | ---: | ---: | ---: | ---: |
| `header_envelope` | 64 | 98 | 11 | 25 MiB |
| `next_header` | 400 | 596 | 97 | 25 MiB |
| `validated_graph` | 444 | 670 | 19 | 25 MiB |
| `decoding` | 1,661 | 3,257 | 288 | 28 MiB |
| `volumes` | 805 | 1,215 | 40 | 26 MiB |
| `path_validation` | 71 | 128 | 66 | 25 MiB |

No target crashed or timed out. The generated working corpora remain under the
ignored `fuzz/corpus/` path; they are disposable local fuzzer state, not
project compatibility fixtures. The reproducible authoritative command stays
the nightly cargo-fuzz form above, which enables AddressSanitizer by default.
