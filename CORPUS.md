# Corpus record

## Inputs actually available

The request contained literal `<CORPUS>` and `<MALFORMED_CORPUS>` placeholders.
No paths were substituted, and a search of the target repository and adjacent
workspace found no separate 7z corpus. The project therefore cannot claim to
have inspected those two requested corpora.

On 2026-07-18 the repository owner confirmed that no separate valid or
malformed corpus is available. That absence is now an explicit test-design
constraint rather than a pending path request: ordinary development uses
deterministic in-tree constructors, on-demand `7zz` oracle generation,
CRC-correct semantic mutation, exhaustive truncation tests, and
coverage-guided fuzzing. No compatibility row is credited merely because a
fuzz target accepts arbitrary bytes.

The pinned Go repository supplied the only available 7z reference set:

- 38 top-level `testdata` files: 31 `.7z` files, six parts of
  `multi.7z.001` through `.006`, and one SFX executable;
- four Go fuzz artifacts under `testdata/fuzz/FuzzNewReaderWithPassword`;
- total files in the manifest: 42; and
- exact SHA-256 values in `reference/go-testdata.sha256`.

These files were inspected in the temporary pinned checkout and were **not
copied** into this repository. A hash manifest establishes identity, not a
right to redistribute each binary fixture.

The pinned checkout's own `go test ./...` suite passed with Go 1.26.5 on macOS;
this establishes the inspected reference baseline but is not Rust evidence.

## Current Rust structural evidence

The ignored integration harness in
`crates/un7z/tests/reference_headers.rs` reads fixtures only from an explicit
`UN7Z_GO_TESTDATA` directory, so no upstream binary is copied or implicitly
downloaded. On 2026-07-18 it passed the production stored-next-header parser
and validated model for 32 logical Go-reference archives: 31 named single-file
fixtures and the six `multi.7z.001` through `.006` parts joined as one logical
byte sequence. The set includes the SFX executable and plain, encoded, and
encrypted header families.

This is evidence for stored syntax/model validation, not for decoding an
encoded header, password handling, volume-provider behavior, decoded metadata,
or any decoder. The same opt-in run confirms that external
`COMPRESS-492.7z` is rejected. Generated Rust regressions independently cover
that missing-UnpackInfo condition, the FilesInfo-only initialization panic
class, and the invalid packed-index File.Open panic class; the upstream binary
itself remains external and is not committed.

The exact local command was:

```text
UN7Z_GO_TESTDATA=<PINNED_GO_CHECKOUT>/testdata \
  cargo test -p un7z --test reference_headers -- --ignored
```

## Current Rust decoding evidence

On 2026-07-18 the opt-in Phase 3 harness opened the exact external `copy.7z`,
`lzma.7z`, `lzma2.7z`, `delta.7z`, `bcj.7z`, `bcj2.7z`, `ppc.7z`, `arm.7z`,
`arm64.7z`, `sparc.7z`, and `sfx.exe` files identified by this repository's
hash manifest. Every streamed member was decoded through the production
archive/model/graph API, finalized with its Rust CRC, and compared against
`7zz` 26.02 output for exact bytes, declared size, and RustCrypto SHA-256.
Ordered path, size, and optional CRC metadata also matched `7zz l -slt`. The
external oracle exited successfully, including its own integrity check, and a
final Rust natural-order archive verification succeeded.

The exact command was:

```text
UN7Z_GO_TESTDATA=<PINNED_GO_CHECKOUT>/testdata \
  cargo test -p un7z --test phase3_reference -- --ignored
```

The same ten method archives were copied to a temporary directory for a
10,000-execution stable-built `decoding` fuzz-harness smoke test and then
deleted. The pinned corpus itself was not changed. That Phase 3 run made no
claim for encrypted fixtures, multi-volume provider behavior, or unsupported
methods. The separate `<CORPUS>`/`<MALFORMED_CORPUS>` sets are confirmed
unavailable and are not used as evidence.

## Corpus-free generated differential evidence

`crates/un7z/tests/generated_oracle.rs` removes the external-corpus dependency
for every method that stock `7zz` 26.02 can author in the original Go-parity
and core-filter set. The ignored suite creates deterministic synthetic input
and temporary archives for Copy, LZMA, LZMA2, Delta, BCJ, BCJ2, PPC, ARM,
ARM64, SPARC, Deflate, BZip2, and PPMd. Filter fixtures contain matching branch
or delta patterns, and the test confirms that their packed representation was
actually transformed. For every archive it compares ordered raw name, size,
optional CRC, exact output bytes, and SHA-256 with `7zz`, verifies with Rust,
then mutates a packed byte and requires Rust verification to fail.

The same suite independently creates header-encrypted and data-encrypted Copy
archives. It checks the exact `PasswordRequired` and
`WrongPasswordOrCorrupt` states, compares correct-password output with the
oracle, and rejects corruption. A synthetic test-only `MZ` prefix is prepended
to a generated Copy archive to exercise bounded SFX discovery in both Rust and
`7zz`; no 7-Zip SFX source or stub is copied. All source files and archives are
deleted with their unique temporary directory.

The exact command run on 2026-07-18 was:

```text
cargo test -p un7z --test generated_oracle --all-features --locked -- --ignored
```

All three tests passed with local `7zz` 26.02. These cases are reproducible
test generation, not a committed binary corpus and not a runtime dependency.

## Phase 4 external evidence

On 2026-07-18 the opt-in Phase 4 harness verified the exact external
`deflate.7z`, `bzip2.7z`, `ppmd.7z`, `brotli.7z`, `lz4.7z`, and `zstd.7z`
files plus password-protected `aes7z.7z`, `t2.7z`-`t5.7z`, and
`7zcracker.7z`. Deflate, BZip2, PPMd, `aes7z.7z`, `t2.7z`, and `t4.7z`
matched `7zz` 26.02 for ordered metadata, exact bytes, CRC, size, and SHA-256.
The private Brotli/LZ4/Zstd method IDs cannot be decoded by that stock oracle;
their fixtures instead matched the same independently oracle-verified Deflate
corpus bytes and metadata.

The real `multi.7z.001`-`.006` set verified through the path provider. The
harness also split the already identified Deflate and encrypted AES fixtures
deterministically into exactly five in-memory parts, without modifying or
committing either source fixture. An opt-in test used `7zz` to create a
temporary encrypted-header BCJ→LZMA2→AES archive from the pinned `sfx.exe`,
compared it to the oracle, and removed it. A separate generated Unix symlink
archive was likewise temporary. These generated cases are test-oracle outputs,
not redistributed corpus additions.

The command is:

```text
UN7Z_GO_TESTDATA=<PINNED_GO_CHECKOUT>/testdata \
  cargo test -p un7z --test phase4_reference -- --ignored
```

## Phase 5 generated differential evidence

No Phase 5 binary fixture is committed. The ignored harness in
`crates/un7z/tests/phase5_reference.rs` creates deterministic synthetic source
bytes and asks the locally installed `7zz` 26.02 executable to author archives
inside a unique temporary directory. It compares production Rust output,
SHA-256, size, CRC, ordered names, and metadata with the oracle and then
deletes the directory.

The generated positive matrix contains transforming inputs for Deflate64,
IA64, ARM Thumb, RISC-V, Swap2, and Swap4. The Deflate64 input contains a
65,536-byte deterministic prefix followed by distant repeated data and
long-match text. The architecture inputs contain synthetic IA64 bundles, ARM
Thumb branches, and RISC-V JAL/AUIPC pairs; packed bytes are checked to ensure
the oracle actually transformed each source. Each archive also receives a
separate mid-packed-region corruption that must fail Rust verification.

The composed matrix contains a two-member solid encrypted-header/data
Deflate64 archive, a two-member non-solid Deflate64 archive, and separately
authored unencrypted and encrypted Swap4 archives split by `7zz` into exactly
five `.001` through `.005` files. Both volume sets are read through the path
provider and compared with the oracle. These temporary oracle artifacts are
test outputs, not redistributable corpus additions. The separate user corpus
sets were confirmed unavailable.

The exact command run on 2026-07-18 was:

```text
cargo test -p un7z --test phase5_reference -- --ignored
```

Both Phase 5 ignored tests passed with `7zz` 26.02. Existing Phase 2-4 tests
remain the corpus evidence for malformed grammar/graphs, SFX, metadata,
Unicode, symlinks, duplicate names, wrong passwords, and the pinned Go
fixtures. A separate in-tree unit vector forces a dynamic Huffman block through
the Deflate64 decoder; the generated oracle fixture supplies the
Deflate64-specific long-distance and long-match evidence.

## Encoded-header compatibility closure

On 2026-07-18 an ignored unit oracle generated three temporary Copy-encoded
headers entirely from documented 7z records and deleted each file after asking
stock `7zz` 26.02 to test it. The baseline has one folder and one substream.
The compatibility case partitions a valid decoded FilesInfo header across two
CRC-protected substreams and preserves one named empty file; both Rust and
`7zz` accept it. Rust regressions additionally corrupt each CRC, reject every
truncated prefix, and preflight the combined decoded size.

A two-folder form built from the same decoded bytes is accepted by the Rust
implementation's ordered, bounded reconstruction but rejected by stock `7zz`
26.02 with `Headers Error`. That result is retained as negative oracle evidence
and is not presented as stock-7zz compatibility. The command is:

```text
cargo test -p un7z --lib stock_7zz_ -- --ignored
```

The 13-byte raw LZMA EOS unit in `decode/lzma.rs` is generated from the
synthetic bytes `abc` by XZ Utils 5.8.3 with
`xz --format=raw --stdout --lzma1=dict=4096,lc=3,lp=0,pb=2`. It is retained as
a deterministic positive unknown-size vector; every strict prefix and a byte
appended after EOS are negative termination cases. A validated-model
`Archive::extract_entry`
regression additionally requires that EOS and the member/folder/packed CRCs
all succeed before extraction is reported as successful. The vector contains
no third-party corpus content.

## Reference coverage observed

The Go tests identify fixtures for Copy, Delta, LZMA, LZMA2, BCJ, BCJ2, PPC,
ARM, ARM64, SPARC, Deflate, BZip2, PPMd, AES, Brotli, LZ4, and Zstd, plus plain,
encoded, and encrypted headers, empty streams/files, SFX, and six sequential
volumes. `lzma1900.7z` contains 633 listed entries and complex BCJ2/LZMA chains.

The Go fuzz target seeds `copy.7z` and asserts only that reader construction
does not panic. The four saved fuzz artifacts are malformed-input candidates,
not a complete malformed corpus.

## Local 7zz oracle inspection

`7zz` 26.02 successfully tested the standard-method, SFX, encrypted test
fixtures with known test passwords, and the six-volume archive. The locally
installed binary returned unsupported-method errors for the bundled private
method IDs `04F71101` (Zstd), `04F71102` (Brotli), and `04F71104` (LZ4).
`COMPRESS-492.7z` is a 39-byte malformed regression expected to fail. Archives
whose password was not documented were not treated as failed fixtures.

## Corpus admission requirements

Before using or committing the requested corpora, record for every file or
coherent source set:

- canonical path/source URL and acquisition date;
- SHA-256 and byte length;
- creator and redistribution license/permission;
- valid versus malformed classification and mutation history;
- passwords stored only in test configuration suitable for publication;
- expected `7zz` version/output and any oracle limitation; and
- the method, feature, metadata, volume, corruption, or regression claim it
  supports.

Malformed cases should be minimized without destroying the triggering
invariant. Valid cases must not be mutated in place; derived corruptions get new
hashes and provenance records.
