# Benchmark results

## Current result

Phase 7 retains the Phase 6 opt-in release-mode benchmark for natural-order
caller-owned sink extraction of the solid `lzma2.7z` reference fixture.
Extraction decodes its folder once, checks every member CRC before the sink
finalizes that member, and checks the folder CRC before delivery. Parsing/opening and one correctness
warmup occur outside the timed loop.

| Date | Commit | Benchmark | Result | Peak memory | Notes |
| --- | --- | --- | --- | --- | --- |
| 2026-07-18 | Pre-commit Phase 1 snapshot | N/A | Not run | Not measured | Foundation only |
| 2026-07-18 | Pre-commit Phase 2.1 snapshot | Header envelope | Not benchmarked | No archive-derived buffer allocation | Correctness/fuzz review unit only |
| 2026-07-18 | Pre-commit Phase 2 snapshot | Parser/model amplification | 100,000 empty entries accepted; 100,001 rejected | Not measured | Pass/fail bounded-allocation regression; not a performance claim |
| 2026-07-18 | Pre-commit Phase 3 snapshot | Natural-order solid `Archive::extract_entries_to`, `lzma2.7z`, 50 timed iterations | 36,054 decoded bytes/iteration; 0.035271 s total; 48.742 MiB/s | Not measured | Counting sink correctness warmup passed; one solid folder decoded per iteration; no filesystem I/O in timed loop |
| 2026-07-18 | Pre-commit Phase 4 snapshot | Natural-order solid `Archive::extract_entries_to`, `lzma2.7z`, 50 timed iterations | 36,054 decoded bytes/iteration; 0.034955 s total; 49.183 MiB/s | Not measured | Same reproducibility workload after codec/crypto/volume integration; counting sink correctness warmup passed; one solid folder decoded per iteration |
| 2026-07-18 | Pre-commit Phase 5 snapshot | Natural-order solid `Archive::extract_entries_to`, `lzma2.7z`, 50 timed iterations | 36,054 decoded bytes/iteration; 0.038949 s total; 44.139 MiB/s | Not measured | Same reproducibility workload after remaining-method integration; counting sink correctness warmup passed; one solid folder decoded per iteration |
| 2026-07-18 | Pre-commit Phase 6 snapshot | Natural-order solid `Archive::extract_entries_to`, `lzma2.7z`, 50 timed iterations | 10 entries; 36,054 decoded bytes and 92,896 deterministic work units/iteration; 0.042591 s total; 40.364 MiB/s | 1,359,872-byte direct-process peak RSS; 8,184-byte retained archive payload account; one 36,054-byte folder output | Direct release binary under macOS `/usr/bin/time -l`; correctness warmup passed; every timed iteration matched byte and work counts |
| 2026-07-18 | Pre-commit Phase 7 snapshot | Python FFI | Not benchmarked | Not measured | Installed-wheel test verifies that another Python thread advances during 8 MiB Copy verification; this is a GIL-detachment correctness test, not a throughput or memory result |
| 2026-07-21 | Uncommitted ALES-readiness snapshot | Python natural-order batch adapter | Not benchmarked | Caller-retained Python buffers not measured | Installed-wheel functional test proves one shared work budget and a batch work cost below two random-access solid-folder decodes; no new decoder path was added |

The exact Git object for these historical measurements was not recorded. The
`Pre-commit` labels preserve that limitation; the rows must not be attributed
to merge commit `77c2176` or treated as fresh post-merge measurements.

Benchmark context:

- archive SHA-256:
  `15934a5ff1325d4608f9b9c63b1a6d110957566fbea4f9e12c60864b5b7a684f`;
- archive size: 6,110 bytes; output size: 36,054 bytes;
- command: `UN7Z_GO_TESTDATA=<pinned>/testdata
  UN7Z_BENCH_ITERATIONS=50 cargo bench -p un7z --bench
  natural_order_solid`;
- Rust: 1.97.0 (`2d8144b78`), release profile, target
  `x86_64-apple-darwin`;
- host: Intel Core i9-9880H at 2.30 GHz, 16 GiB RAM;
- sampling: one untimed verified extraction warmup followed by one
  50-iteration wall-time sample; Phase 6 peak RSS used the already-built
  release benchmark binary directly under `/usr/bin/time -l`;
- limits: `Limits::default()` and an unlimited abstract work budget. Byte,
  dictionary, count, and recursion limits remain active.

The Phase 6 account reports 6,110 owned input bytes, 2,074 validated metadata
bytes, no password bytes, and 8,184 retained archive payload bytes. This solid
fixture has one 36,054-byte decoded folder output, which is retained only for
the current extraction iteration. The 1,359,872-byte RSS measurement is the
whole benchmark process and therefore includes executable/runtime/allocator
state that is deliberately outside archive payload accounting.

Complexity correctness does not depend on the timing sample. The unit
regression constructs 10,000 zero-size substreams and gives verification,
natural-order sink extraction, and last-member range discovery their exact
checked work allowance. Natural-order extraction consumes `2n + 3` work units,
finishes all `n` entries, advances one substream cursor, and decodes its folder
once; an accidental nested rescan exhausts the budget. Random access remains
documented separately because selecting members independently can re-decode a
solid folder.

This microbenchmark is a reproducibility baseline, not a statistically robust
performance claim. The current decoder retains a complete bounded folder
output, so this result does not claim constant-memory streaming.

The Phase 7 adapter, including Python `extract_entries_to`, calls the same
natural-order Rust operations and introduces no alternate parser or decoder.
The batch test measures minimum accepted work allowances only as a
deterministic complexity assertion: its allowance is greater than either
single member and less than the sum of two random-access extractions. It is not
a timing or throughput result. Writer/callback time, Python-owned buffers, and
objects retained by a caller are outside the core benchmark and resource
account. A future Python benchmark must separately report native decoder time,
callback overhead, chunk count, interpreter version, free-threaded/GIL mode,
and Python-owned peak memory. The functional detachment regression is not used
as performance evidence.

## Expanded future methodology

Future work adds statistically sampled natural-order solid extraction and peak
RSS benchmarks as the current full-folder-buffered callback/sink pipeline
evolves. Each published result records commit, Rust version, target triple,
CPU, RAM, archive hash, method graph, compressed and output bytes, file count,
warmup/sample method, wall throughput, peak RSS, and configured limits.

Benchmark inputs include small-file-heavy and large-file solid archives,
non-solid controls, random versus natural order, encrypted and unencrypted
chains once AES exists, and five-volume inputs once admitted. Correct output and
CRC verification run before timing. A faster failure or skipped CRC is never a
valid result.

Bounded-memory tests are separate pass/fail gates and verify that declared
dictionary/property/output sizes are rejected before allocation. Benchmark
regressions do not justify weakening defaults.
