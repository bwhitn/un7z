# Test and platform matrix

The required local phase gates are:

```text
cargo fmt --all -- --check
cargo clippy --workspace --all-targets --all-features -- -D warnings
cargo test --workspace --all-features --locked
cargo deny check
```

Phase 6 also checks the curated default API, examples, and warning-free docs:

```text
cargo check -p un7z --no-default-features --locked
cargo test -p un7z --examples --all-features --locked
RUSTDOCFLAGS="-D warnings" cargo doc --workspace --no-deps --all-features --locked
cargo test --workspace --doc --all-features --locked
```

GitHub Actions runs all targets/features on Linux, macOS, and Windows and runs
Rust 1.85 separately as the MSRV. Tests use only caller-selected temporary
paths and make no automatic archive-name-based extraction decisions.

## 32-bit

The Linux i686 job installs the target and multilib linker, then compiles the
whole workspace and runs the core library/integration tests:

```text
rustup target add i686-unknown-linux-gnu
cargo check --workspace --all-targets --all-features --locked \
  --target i686-unknown-linux-gnu
cargo test -p un7z --lib --tests --all-features --locked \
  --target i686-unknown-linux-gnu
```

The Phase 2 suite includes a `target_pointer_width = "32"` regression that
raises count limits deliberately and confirms a file count that cannot fit
`usize` returns `Format` before allocation. The normal conversion, offset,
volume, metadata, and Phase 6 stable-API tests run in the same linked job.

## Miri

Miri applies to the safe in-tree parser/model/graph/decoder logic. The CI job
uses nightly and runs the library tests without the unstable inspection API:

```text
rustup toolchain install nightly --component miri
cargo +nightly miri setup
cargo +nightly miri test -p un7z --lib --no-default-features
```

The core has `#![forbid(unsafe_code)]`; Miri remains useful for dependency-free
aliasing, bounds, and platform-model regressions. Oracle tests, filesystem
volume discovery, benchmarks, and libFuzzer are not Miri workloads and have
their own gates.

## Differential tests

`7zz` is a test oracle only. With the inspected Go testdata available:

```text
UN7Z_GO_TESTDATA=/path/to/pinned/testdata \
  cargo test -p un7z --test reference_headers --all-features -- --ignored
UN7Z_GO_TESTDATA=/path/to/pinned/testdata \
  cargo test -p un7z --test phase3_reference -- --ignored
UN7Z_GO_TESTDATA=/path/to/pinned/testdata \
cargo test -p un7z --test phase4_reference -- --ignored
cargo test -p un7z --test phase5_reference -- --ignored
cargo test -p un7z --lib stock_7zz_ -- --ignored
```

No external corpus is required for the stock-method generated matrix. With
`7zz` 26.02 or newer on `PATH`:

```text
cargo test -p un7z --test generated_oracle --all-features --locked -- --ignored
cargo test -p un7z --test phase5_reference --all-features --locked -- --ignored
cargo test -p un7z --test phase4_reference \
  generated_symlink_metadata_and_target_match_oracle \
  --all-features --locked -- --ignored
cargo test -p un7z --lib stock_7zz_ --all-features --locked -- --ignored
```

The first command generates Copy, LZMA, LZMA2, Delta, BCJ, BCJ2, PPC, ARM,
ARM64, SPARC, Deflate, BZip2, PPMd, AES, and synthetic-prefix SFX cases in a
temporary directory. It compares bytes, SHA-256, size, CRC, method, and name,
checks transforming filter input, and rejects packed-data corruption. The
second command supplies the six Phase 5 methods plus solid, encrypted, and
five-volume compositions. Generated archives are deleted and never become a
runtime dependency or committed corpus.

No result is claimed for the literal `<CORPUS>` or `<MALFORMED_CORPUS>`
placeholders; the owner confirmed that no such external sets are available.
See `CORPUS.md` and `COMPATIBILITY.md` for the generated-evidence boundary.

## Coverage

Coverage is measured for the core independently from the intentionally small
CLI. Install `cargo-llvm-cov` 0.8.7 or newer as a development tool, then run
the ordinary suite:

```text
cargo llvm-cov -p un7z --all-features --locked
```

To merge the corpus-free oracle paths into the same report, start clean and
run the opt-in tests without deleting prior profiles:

```text
cargo llvm-cov clean --workspace
cargo llvm-cov --no-clean -p un7z --all-features --locked
cargo llvm-cov --no-clean -p un7z --test generated_oracle \
  --all-features --locked -- --ignored
cargo llvm-cov --no-clean -p un7z --test phase5_reference \
  --all-features --locked -- --ignored
cargo llvm-cov --no-clean -p un7z --test phase4_reference \
  --all-features --locked -- \
  generated_symlink_metadata_and_target_match_oracle --ignored
cargo llvm-cov report --ignore-filename-regex 'un7z-cli/'
```

Coverage percentages are diagnostic, not compatibility claims. Positive
oracle fixtures, corruption/limit regressions, and fuzz depth remain required
even when a line is executed.

On 2026-07-18, cargo-llvm-cov 0.8.7 measured 65.00% core line coverage for the
ordinary all-feature suite. Merging the corpus-free generated-method, Phase 5,
and symlink oracle tests raised core line coverage to 81.66% (78.21% regions).
The report excludes `un7z-cli`, as compatibility work in this project is
evaluated at the core API. In particular, positive generated PPMd raised its
decoder file from 7.99% to 70.79% lines, and the generated core/Phase 5 filter
matrices raised the two filter files to 81.29% and 80.51%. These values describe
this source revision and toolchain, not a permanent threshold.

## Fuzzing and benchmarks

Nightly cargo-fuzz commands, seed policy, triage, and current smoke evidence
are in `FUZZING.md`. The reproducible natural-order solid benchmark is:

```text
UN7Z_GO_TESTDATA=/path/to/pinned/testdata \
UN7Z_BENCH_ITERATIONS=50 \
  cargo bench -p un7z --bench natural_order_solid
```

The benchmark verifies output before timing and reports deterministic work
units plus retained archive accounting. The 10,000-substream unit regression
is the non-timing proof that natural-order member/substream traversal is
linear; timing is not used as a correctness assertion.

## Python binding and wheels

The binding is intentionally excluded from the root workspace and has its own
lockfile and gates:

```text
cargo fmt --manifest-path bindings/python/Cargo.toml --all -- --check
PYO3_PYTHON=python cargo clippy \
  --manifest-path bindings/python/Cargo.toml \
  --all-targets --all-features --locked -- -D warnings
PYO3_PYTHON=python cargo test \
  --manifest-path bindings/python/Cargo.toml \
  --no-default-features --lib --locked
PYO3_PYTHON=python cargo check \
  --manifest-path bindings/python/Cargo.toml --all-features --locked
cargo deny --manifest-path bindings/python/Cargo.toml \
  --all-features --config bindings/python/deny.toml check
```

The no-default-features Rust tests link against the selected interpreter,
exercise the binding's unexpected-unwind containment helper, and assert a
distinct structured mapping for every stable core error. The all-features
target uses PyO3 extension-module linkage and is compile/Clippy
checked; an installed wheel is the correct executable test artifact for that
mode on platforms which deliberately leave CPython symbols for the loader.

Build and test the actual package, not an in-tree Python shim:

```text
python -m pip install 'maturin==1.13.3'
maturin build --manifest-path bindings/python/Cargo.toml \
  --release --locked --compatibility pypi --out bindings/python/dist
python -m pip install --force-reinstall bindings/python/dist/un7z-*.whl
python -m unittest discover -s bindings/python/tests -v
maturin sdist --manifest-path bindings/python/Cargo.toml \
  --out bindings/python/dist
python -m pip wheel --no-deps bindings/python/dist/un7z-*.tar.gz \
  --wheel-dir bindings/python/dist/from-sdist
```

The binding suite constructs a CRC-protected Copy archive independently and
tests distribution/native module names, raw UTF-16 metadata and unsafe paths,
writer/callback extraction, callback exception identity and cancellation,
provider/writer exception identity, same-archive callback reentrancy, CRC
failure, structured format/limit/work/cancellation errors, every limit override, per-archive
password accounting, path opening, Python volume
providers and exact missing-volume names, and interpreter detachment during an
8 MiB Rust-only verification. A 46,000-byte callback output also asserts that
delivery spans multiple chunks and no chunk exceeds 8 KiB; partial writer
counts are honored and an impossible count is rejected.

On 2026-07-18 the locally built `cp39-abi3` macOS wheel installed into a clean
CPython 3.12 virtual environment and all 10 binding tests passed. The sdist
also rebuilt into a wheel in an isolated PEP 517 build; that rebuilt wheel was
installed and passed the same suite. This is local macOS/Python 3.12 evidence
only. GitHub Actions is configured to build, install, and
test produced wheels with Python 3.9 on Linux, macOS, and Windows, and
separately checks Rust 1.85 and sdist rebuildability; those remote matrix
results are not claimed until CI runs.
