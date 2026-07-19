# un7z

`un7z` is a security-focused, unpack-only Rust implementation of the 7z
container format.

> **Current status: Phase 7 Python binding implemented, pre-alpha.** The core
> validates regular and bounded-SFX archives, executes arbitrary validated
> coder graphs, and supports the evidence-backed Copy/LZMA family, core
> filters, Deflate, Deflate64, BZip2, PPMd, Brotli, LZ4, Zstandard, IA64,
> ARM Thumb, RISC-V, Swap2, Swap4, and
> AES-256-CBC/SHA-256 slices in
> [COMPATIBILITY.md](COMPATIBILITY.md). It resolves supported encoded/encrypted
> headers and external metadata and reads bounded sequential volumes. Member
> and archive APIs enforce applicable CRCs; streaming callers must explicitly
> call `finish()`. This is not a general “all 7z” compatibility claim.

The intended scope is reading, listing, verifying, decrypting, and
decompressing archives. Archive creation and modification, automatic
filesystem extraction and integration with ALES are outside the current scope.

## Workspace

- `crates/un7z`: safe Rust core. It has `#![forbid(unsafe_code)]`.
- `crates/un7z-cli`: small `list`, stdout `cat`, `verify`, and status frontend.
- `bindings/python`: separately locked PyO3/maturin package distributed and
  imported as `un7z`, with native module `un7z._native`.
- `fuzz`: cargo-fuzz targets, kept outside the publishable workspace.

The completed Phase 1 foundation establishes typed errors, configurable
resource limits, cancellation and work budgets, a `VolumeProvider` contract,
and a path validator that does not alter archive metadata or stream mapping.
Phase 2 adds a bounded reader, borrowed raw grammar, an isolated graph
validator, exact property sub-readers, an owned validated archive model, and
start/next-header CRC enforcement. Phase 3 adds topological folder execution,
the core method set above, encoded-header resolution, packed/folder/member CRC
enforcement, configured output/work/cancellation bounds, and CRC-finalizing
member extraction. `Archive::extract_entries_to` decodes solid folders once in
natural order and finalizes each caller-owned sink entry only after its member
CRC succeeds. Folder output is currently fully buffered and bounded; this is
not yet a constant-memory decompression pipeline.

Phase 4 adds bounded adapters for Deflate, BZip2, Brotli, LZ4, and Zstandard;
an in-tree safe PPMd7 adaptation; RustCrypto AES-256-CBC/SHA-256 with
per-archive zeroized passwords; encoded/encrypted headers; supported external
Name/time/attribute/StartPos streams; Unix-mode/symlink metadata; and bounded
path/memory sequential volume providers. Unsupported methods, external folder
definitions, semantic comment decoding, and Zstandard dictionaries remain
explicit typed boundaries.

Phase 5 adds an in-tree bounded Deflate64 decoder and size-preserving IA64,
ARM Thumb, RISC-V, Swap2, and Swap4 filters without adding a runtime
dependency. Generated opt-in tests compare exact bytes, SHA-256, size, CRC,
and metadata with `7zz`, exercise corruption and encrypted solid/non-solid
archives, and use real five-part encrypted and unencrypted volume sets. The
literal `<CORPUS>` and `<MALFORMED_CORPUS>` sets were confirmed unavailable,
so no claim is made for them.

Phase 6 freezes the documented `0.1.x` Rust surface for owned path/byte/volume
opening, concrete archive-order metadata, explicit-`finish()` member streams,
caller-selected output, errors, limits, volume callbacks, and retained-state
accounting. Raw parser and coder-graph inspection moved behind the hidden,
off-by-default `unstable-internals` test/fuzz feature. See [API.md](API.md),
[ERRORS.md](ERRORS.md), and the runnable examples in `crates/un7z/examples`.

Phase 7 wraps only that stable surface. Python archive work runs with the
interpreter detached; writer and callback extraction crosses the boundary in
bounded chunks and does not report success before Rust CRC finalization.
Python volume providers receive exact indices and names, core errors become
structured exception subclasses, callback exceptions are preserved, and
unexpected Rust unwinds are contained at the native boundary. No parser,
decoder, cryptography, or path-policy logic is duplicated in the binding.

## Build

The workspace uses Rust edition 2024 and has a minimum supported Rust version
(MSRV) of **1.85**. `Cargo.lock` is committed.

```text
cargo test --workspace --all-features --locked
cargo clippy --workspace --all-targets --all-features -- -D warnings
cargo fmt --all -- --check
cargo deny check
```

The Python package targets Python 3.9+ through ABI3 wheels:

```text
maturin build --manifest-path bindings/python/Cargo.toml --release --locked
python -m unittest discover -s bindings/python/tests -v
cargo deny --manifest-path bindings/python/Cargo.toml \
  --all-features --config bindings/python/deny.toml check
```

See [bindings/python/README.md](bindings/python/README.md) for the output,
password, and callback trust boundaries.

`7zz` is permitted only in differential tests. It is never linked, invoked, or
required by the runtime library or CLI.

The CLI deliberately has no automatic filesystem extraction command:

```text
un7z list archive.7z
un7z cat archive.7z 0 > member.bin
un7z verify archive.7z
```

The Rust API additionally provides `open_bytes_with_password`,
`open_path_with_password`, `open_volumes`, and
`open_volumes_with_password`. Passwords are not accepted by the current small
CLI so they are not exposed through process arguments.

## Project controls

- [ARCHITECTURE.md](ARCHITECTURE.md) defines trust boundaries and module
  ownership.
- [API.md](API.md) and [ERRORS.md](ERRORS.md) define the stable Rust and error
  contracts.
- [TESTING.md](TESTING.md) records platform, 32-bit, Miri, differential, fuzz,
  and benchmark commands.
- [PHASE_PLAN.md](PHASE_PLAN.md) defines review and exit gates.
- [`docs/adr`](docs/adr) records accepted trust-boundary, API, and Python-FFI
  decisions.
- [SECURITY.md](SECURITY.md) and [THREAT_MODEL.md](THREAT_MODEL.md) define
  security invariants.
- [DEPENDENCIES.md](DEPENDENCIES.md) and `deny.toml` define supply-chain rules.
- [PROVENANCE.md](PROVENANCE.md) records exact source origins and decoder
  provenance.
- [CORPUS.md](CORPUS.md) records what corpus material was actually inspected.
- [AGENTS.md](AGENTS.md) records repository-wide implementation and review
  rules.

## Licensing

Original Rust work is available under **MIT OR Apache-2.0**. Any translated or
adapted work retains the applicable BSD-3-Clause notice. See `LICENSE-MIT`,
`LICENSE-APACHE`, `LICENSE-BSD-3-CLAUSE`,
`LICENSE-ULIKUNITZ-XZ-BSD-3-CLAUSE`,
`LICENSE-STANGELANDCL-PPMD-MIT`, `NOTICE`, and `PROVENANCE.md`.
