# Dependency policy and ledger

## Current runtime graph

`un7z-cli` depends only on the workspace's `un7z` crate. The core now has the
following exact direct runtime dependencies; default features are disabled and
`Cargo.lock` is committed.

| Crate | Version | License | Enabled features | Runtime role and origin |
| --- | --- | --- | --- | --- |
| `aes` | 0.9.1 | MIT OR Apache-2.0 | `zeroize` | RustCrypto AES-256 primitive; `https://github.com/RustCrypto/block-ciphers` |
| `cbc` | 0.2.1 | MIT OR Apache-2.0 | `zeroize` | RustCrypto CBC mode; `https://github.com/RustCrypto/block-modes` |
| `sha2` | 0.11.0 | MIT OR Apache-2.0 | `zeroize` | RustCrypto SHA-256 for the 7z KDF and differential hashes; `https://github.com/RustCrypto/hashes` |
| `zeroize` | 1.9.0 | Apache-2.0 OR MIT | `alloc` | Per-archive password and derived-secret clearing; `https://github.com/RustCrypto/utils` |
| `miniz_oxide` | 0.8.9 | MIT OR Zlib OR Apache-2.0 | `with-alloc` | Raw Deflate decoder; `https://github.com/Frommi/miniz_oxide` |
| `bzip2-rs` | 0.1.2 | MIT OR Apache-2.0 | `rustc_1_37` | Safe Rust BZip2 decoder; `https://github.com/paolobarbolini/bzip2-rs` |
| `brotli-decompressor` | 5.0.3 | BSD-3-Clause OR MIT | `std` | Brotli decoder; `https://github.com/dropbox/rust-brotli-decompressor` |
| `lz4_flex` | 0.13.1 | MIT | `checked-decode`, `frame`, `safe-decode`, `safe-encode` | Safe checked LZ4-frame decoder; `https://github.com/pseitz/lz4_flex` |
| `ruzstd` | 0.8.2 | MIT | `std` | Zstandard frame decoder; `https://github.com/KillingSpark/zstd-rs`; 0.8.3 was not selected because it requires Rust 1.87 above this project's MSRV |

The complete normal/build transitive graph at this revision is:

| Crates | Versions | License selection |
| --- | --- | --- |
| `cipher`, `crypto-common`, `inout` | 0.5.2, 0.2.2, 0.2.2 | MIT OR Apache-2.0 |
| `digest`, `block-buffer`, `hybrid-array` | 0.11.3, 0.12.1, 0.4.13 | MIT OR Apache-2.0 |
| `cpubits`, `cpufeatures`, `cfg-if`, `typenum` | 0.1.1, 0.3.0, 1.0.4, 1.20.1 | MIT OR Apache-2.0 |
| `alloc-no-stdlib`, `alloc-stdlib` | 2.0.4, 0.2.4 | BSD-3-Clause |
| `crc32fast`, `tinyvec` | 1.5.0, 1.12.0 | MIT OR Apache-2.0; Zlib OR Apache-2.0 OR MIT |
| `twox-hash` | 2.1.2 | MIT |
| `adler2` | 2.0.1 | MIT selected from 0BSD OR MIT OR Apache-2.0 |

No decoder dependency uses FFI or links a native library. The core crate still
enforces `#![forbid(unsafe_code)]`; dependency-internal unsafe cannot bypass
that crate boundary. The admission audit found target-intrinsic/volatile or
buffer implementations in RustCrypto/`zeroize` and `ruzstd`. `lz4_flex` is
compiled with its checked, safe decoder features, and Brotli's optional unsafe
feature is disabled. Each dependency decoder is wrapped by bounded input and
output accounting, cancellation/work checkpoints, a panic boundary, and a
method-specific allocation preflight. BZip2 charges five times the advertised
block size, Brotli charges 32 MiB, linked LZ4 charges 24 MiB plus 64 KiB, raw
Deflate charges 32 KiB, and Zstandard charges its parsed frame-window size
before constructing the decoder. Dictionary-bearing Zstandard frames are
rejected as unsupported.

Phase 5 adds no runtime dependency. The in-tree Deflate64 decoder charges its
fixed 64 KiB history requirement during model validation and again at decoder
entry, uses only stack-bounded Huffman tables plus fallibly grown bounded
output, and checkpoints every input refill and output loop. Its Apache-2.0
algorithm source and notice are recorded in `PROVENANCE.md` and `NOTICE`.
IA64, ARM Thumb, RISC-V, Swap2, and Swap4 are in-tree size-preserving filters
with no dictionary allocation or external linkage. XZ Utils was consulted only
as the pinned 0BSD algorithm-description reference identified in provenance;
it is neither a Cargo dependency nor shipped code.

Phase 6 adds no runtime or development dependency. Public API curation,
retained-resource accounting, examples, platform tests, and documentation are
original workspace changes. The default core feature set remains empty; the
`unstable-internals` feature only changes visibility for repository tests and
fuzz harnesses and activates no dependency.

Phase 7 is isolated in the separately locked and workspace-excluded
`bindings/python` package. It adds no dependency to `un7z` or `un7z-cli` and no
decoder or cryptographic implementation. Its direct binding dependencies are:

| Crate | Version | License | Enabled features | Binding role and origin |
| --- | --- | --- | --- | --- |
| `pyo3` | 0.29.0 | MIT OR Apache-2.0 | `abi3-py39`, `macros`; `extension-module` only for wheels | CPython ABI/type/call adapter; `https://github.com/PyO3/pyo3` |
| `zeroize` | 1.9.0 | Apache-2.0 OR MIT | `alloc` | Clears the binding's temporary Rust password owner before/while the core assumes ownership; already admitted above |
| `un7z` | 0.1.0, local path | MIT OR Apache-2.0 plus recorded adapted-source notices | normal core features only | Sole parser/model/decoder/crypto implementation |

PyO3 resolves `pyo3-build-config`, `pyo3-ffi`, `pyo3-macros`, and
`pyo3-macros-backend` 0.29.0; `libc` 0.2.186; `once_cell` 1.21.4;
`portable-atomic` 1.14.0; `proc-macro2` 1.0.107; `quote` 1.0.47; `syn`
2.0.119; `heck` 0.5.0; and `unicode-ident` 1.0.24. These are MIT and/or
Apache-2.0. Build-only `target-lexicon` 0.13.5 is `Apache-2.0 WITH
LLVM-exception`; the LLVM exception
adds permission, is recorded as an exact-version build-only cargo-deny
exception, and is not linked into the wheel. The binding's independently
resolved core graph is captured in `bindings/python/Cargo.lock`; it remains
subject to the same decoder admissions and runtime allowlist. That independent
resolution selects `twox-hash` 2.1.3 (MIT) rather than the root lockfile's
2.1.2; no duplicate version occurs within either artifact graph.

PyO3 and `pyo3-ffi` contain the reviewed unsafe/FFI implementation needed to
call CPython. The binding crate itself has `unsafe_code = "forbid"`, and the
core remains `#![forbid(unsafe_code)]` and Python-unaware. The adapter uses
owned `Py<PyAny>` handles across detached regions, performs no borrowed-Python
access while detached, and reattaches for one provider/writer/callback call.
There is no native decoder dependency or second archive parser.

A Python 3.9-or-newer interpreter is the caller-provided host platform for the
extension, licensed by its distributor (CPython uses the PSF License). The
interpreter is not bundled, vendored, declared as a Python `Requires-Dist`, or
linked into the macOS wheel, and is outside the shipped Cargo dependency graph
and its runtime-license allowlist. This platform prerequisite does not permit a
PSF-licensed Rust/native library to be added to the wheel without a separate
policy decision.

Maturin 1.13.3 is pinned as the PEP 517 build backend and CI packaging tool; it
is not installed or imported by the wheel at runtime. The produced package has
no Python-level runtime dependency. Wheel and sdist license payloads include
the repository MIT, Apache-2.0, upstream BSD-3-Clause, decoder notices, and
`NOTICE` files. The CI-only `PyO3/maturin-action` is pinned to commit
`86b9d133d34bc1b40018696f782949dac11bd380` (v1.49.4, MIT).

On 2026-07-18, after the Phase 5 in-tree method additions,
cargo-deny 0.20.2 reported `advisories ok, bans ok, licenses ok, sources ok`
for both the runtime workspace and the separately locked fuzz package. The
final gate result is recorded in `PHASE_PLAN.md`.

The same cargo-deny 0.20.2 checks passed again after the Phase 6 feature/API
changes; the resolved dependency and license graphs did not change.

The separately configured Phase 7 binding graph also passed cargo-deny 0.20.2
for advisories, bans, licenses, and sources on 2026-07-18. Its exact
`target-lexicon` exception does not alter the root runtime allowlist.

`libfuzzer-sys` 0.4.13 and its transitive crates are confined to the excluded
`fuzz` package and are not linked into runtime artifacts. Its declared license
is `(MIT OR Apache-2.0) AND NCSA`; the required NCSA term has an exact-version,
fuzz-only exception in `fuzz/deny.exceptions.toml`. That exception is outside
the runtime workspace and does not expand the runtime license allowlist.
`cargo-deny`, cargo-fuzz, cargo-llvm-cov, Miri, Rust toolchains, GitHub Actions,
and `7zz` are development/test tools, not runtime dependencies. The local
coverage/fuzz audit used cargo-llvm-cov 0.8.7 and cargo-fuzz 0.13.2 installed
under a temporary tool root; neither changes a lockfile or shipped artifact.

## License allowlist

Every applicable runtime license must be satisfiable solely with:

- MIT
- Apache-2.0
- BSD-2-Clause
- BSD-3-Clause
- ISC
- Zlib
- Unicode-3.0 or Unicode-DFS-2016

GPL, LGPL, AGPL, MPL, SSPL, Commons Clause, noncommercial terms, source-available
terms, and unknown/custom terms are rejected. Dual-license expressions are
accepted only when an allowed option actually applies. Combined `AND`
expressions must have every term allowed.

## Source and version policy

- crates.io is the only approved registry;
- git dependencies are denied;
- wildcard requirements are denied;
- duplicate crate versions are denied by default and require a documented,
  time-bounded exception if cargo-deny policy is later amended;
- exact resolved versions and checksums are committed in lockfiles;
- default features are disabled unless they are reviewed and needed; and
- runtime crates that vendor or derive from official 7-Zip or p7zip source are
  forbidden regardless of their declared crate license.

## Admission checklist

Before adding or updating a runtime crate, the change must record:

1. exact crate version, repository URL, maintainer/release status, and enabled
   features;
2. complete normal/build transitive graph from `cargo tree`;
3. Cargo SPDX expression and manual inspection of every packaged license and
   notice file;
4. upstream source provenance, including whether algorithm code was copied or
   generated from another project;
5. confirmation that official 7-Zip and p7zip source were not used;
6. unsafe blocks and FFI/native code, with isolation and audit plan;
7. maximum allocation/dictionary behavior and a way to account memory before
   allocation;
8. bounded-input, output-limit, cancellation, and malformed-property behavior;
9. current RustSec advisories, yanked status, and maintenance risk; and
10. the corresponding decoder row in `PROVENANCE.md`.

Passing cargo-deny is necessary but not sufficient: package metadata can omit
embedded or generated-code licensing facts.

## Capability admission status

| Capability | Required family or approach | Admission status |
| --- | --- | --- |
| CRC-32 | original safe Rust implementation in `checksum.rs` | Admitted; no dependency |
| AES-256 | RustCrypto `aes` family | `aes` 0.9.1 admitted with `zeroize` |
| CBC | RustCrypto `cbc`/`cipher` family | `cbc` 0.2.1 admitted with `zeroize` |
| SHA-256 | RustCrypto `sha2` family | `sha2` 0.11.0 admitted for the KDF and differential hashes |
| Secret storage | zeroizing per-archive owned bytes | `zeroize` 1.9.0 admitted; no global password/key cache |
| LZMA/LZMA2 | safe, limit-aware permissive implementation | In-tree safe Rust adaptation admitted; exact BSD-3-Clause provenance in `PROVENANCE.md` |
| Deflate | safe permissive implementation | `miniz_oxide` 0.8.9 admitted for Deflate |
| Deflate64 | safe permissive implementation | In-tree checked Rust adaptation of Apache Commons Compress's Apache-2.0 grammar/tables; no new dependency |
| IA64/ARM Thumb/RISC-V/Swap | safe size-preserving filters | In-tree checked Rust with pinned algorithm provenance; no new dependency |
| BZip2 | permissive implementation without native linkage | `bzip2-rs` 0.1.2 admitted behind a bounded adapter |
| PPMd | safe, explicitly memory-bounded permissive implementation | In-tree adaptation of `stangelandcl/ppmd` v0.1.1 admitted; exact MIT provenance in `PROVENANCE.md` |
| Brotli | safe permissive decoder | `brotli-decompressor` 5.0.3 admitted with unsafe feature disabled |
| LZ4 | safe permissive decoder | `lz4_flex` 0.13.1 admitted with checked/safe frame features |
| Zstd | safe permissive decoder | `ruzstd` 0.8.2 admitted with frame-window preflight and dictionaries rejected |
| Python FFI | isolated adapter over the stable core | PyO3 0.29.0 admitted in `bindings/python`; no Python dependency enters the core workspace |

## Development-only 7zz rule

`7zz` may be located and invoked by tests to generate or compare oracle output.
Runtime crates and the installed CLI must contain no command invocation or
fallback path to `7zz`. Official 7-Zip and p7zip source must not be downloaded,
vendored, read, or translated.
