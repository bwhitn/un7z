# Security policy

## Implementation status

This repository is pre-alpha. Phase 7 adds a Python adapter over the stable
Rust API but decodes only the methods explicitly supported in
`COMPATIBILITY.md`, resolves encoded and encrypted headers, supported external
folder definitions and metadata, and reads bounded
sequential volumes. Passwords and KDF output are per archive and zeroized. The
member reader holds one completely decoded folder in memory and reports that
retained allocation. Do
not use this project as a security boundary or infer compatibility for an
untested method/property combination.

Once the repository has a hosting location, vulnerabilities should be reported
through its private security-advisory channel rather than a public issue. Until
then, disclose directly to the repository owner. Reports should include the
affected commit, smallest reproducer, observed resource use or error, platform,
and whether a password is involved. Do not include real passwords or sensitive
archive contents when a synthetic reproducer is possible.

## Non-negotiable invariants

- Malformed input returns a typed error and does not panic.
- The core crate forbids unsafe code.
- Archive-processing paths contain no `unwrap`, `expect`, `panic!`, unchecked
  input-derived indexing, unchecked narrowing, or unchecked offset arithmetic.
- A declared property is parsed in an exact bounded sub-reader.
- Allocation and expensive work follow their relevant limit checks.
- Raw parser records never escape as validated model records.
- All stream counts, indices, bindings, roots, cycles, totals, CRC arrays, and
  ranges are validated before decoder construction.
- Missing CRC and unknown unpacked size use `Option`; zero is not a sentinel.
- Output helpers verify member CRC before success; streams require `finish()`.
- Unsafe paths never change file-to-stream mapping.
- Password and key material is per archive, redacted, and zeroized; no global
  secret cache is permitted.
- Volume count and aggregate bytes are checked before allocation/copying;
  provider reads are checkpointed and a missing part names the exact expected
  suffix.
- Unsupported valid features return `UnsupportedFeature`; unknown methods
  return `UnsupportedMethod`.
- `7zz` cannot be a runtime fallback or dependency.

## Error taxonomy

The public categories are `Format`, `Checksum`, `UnsupportedMethod`,
`UnsupportedFeature`, `LimitExceeded`, `MissingVolume`, `PasswordRequired`,
`WrongPasswordOrCorrupt`, `Cancelled`, and `Io`. Diagnostics must not contain
password bytes, derived keys, decrypted header bytes, or unbounded attacker
strings.

`ERRORS.md` defines retry and partial-output semantics. In particular, bytes
observed before `MemberReader::finish`, `extract_entry_to` success, or
`EntrySink::finish_entry` are unverified and must not be committed as trusted
output.

## Unsafe-code exception process

No exception exists. A proposed exception must be isolated in a separate crate
and review, document why safe Rust is insufficient, enumerate every safety
invariant, minimize and annotate each unsafe block, add direct misuse and
sanitizer/Miri tests where applicable, and update the threat/dependency/
provenance records. The core crate remains `#![forbid(unsafe_code)]`.

## Checksum semantics

Start-header CRC protects the fixed next-header location fields. Next-header
CRC protects the stored next-header bytes. Encoded-header, additional-stream,
packed-stream, and folder CRCs protect their applicable decoded streams.
Member CRC protects exactly that member's output. A failure is scoped and never
converted to success because a caller stopped reading early.

AES-CBC does not authenticate ciphertext. A wrong password may therefore be
indistinguishable from corruption until structure or CRC verification; the
combined error is intentional.

The current implementation enforces start-header and stored-next-header CRCs
for regular and bounded-SFX inputs. During supported decoding it also verifies
packed-stream CRCs before decode, encoded-header folder/substream CRCs before
parsing decoded header bytes, and folder/member CRCs before a high-level helper
returns success. Encoded-header folders are accounted cumulatively before
decode, every declared substream must consume its folder output exactly, and
all substream CRCs succeed before the reconstructed header is parsed. CRC
errors retain distinct typed scopes. External folder definitions follow the
same packed/folder/substream verification before their bytes reach the parser;
the selected decoded folder output must contain exactly the declared folder
records. A `MemberReader`
caller can observe bytes before integrity is final and therefore must call
`finish()`; dropping it never implies success.

Python `extract_entry_to` and `stream_entry` use that high-level finalizing
path. A Python writer or callback can observe chunks before a trailing member
CRC fails, but the native call does not return success until member and folder
checks finish. The binding never turns `Entry.raw_name` into a destination.

`Archive::extract_entries_to` verifies the complete containing folder before
delivering any of its bytes, and calls the sink's `finish_entry` only after the
current member CRC succeeds. A sink can still observe bytes for a member whose
later member-CRC check fails, so only `finish_entry` is the success boundary.
No sink API derives a filesystem destination from raw archive metadata.

## Python FFI boundary

The binding crate also forbids handwritten unsafe code. PyO3 and `pyo3-ffi`
own the CPython unsafe boundary; the core remains safe Rust and unaware of
Python. Native entry points contain unexpected unwinds and raise
`InternalError` without copying a panic payload into the Python exception.
Release builds explicitly
retain unwind semantics so this boundary remains effective.

Rust-only archive work detaches from the interpreter. Python is reattached only
for provider, writer, or stream-callback calls, and no borrowed Python
reference crosses a detached region. Callback exceptions are re-raised as the
same Python exception object. A `False` callback requests cancellation.
Tokens, work budgets, passwords, and decoder state are never global.

Rust panic hooks are process-global and remain under the embedding
application's control; an unwind boundary cannot suppress an already-installed
hook without a racy global mutation. Archive code must therefore never place
secrets in panic payloads. An embedder that redirects process diagnostics must
configure its hook as part of its own hosting policy.

`open_bytes` checks `max_total_input_bytes` before allocating its owned Rust
copy and reserves fallibly. A Python volume provider's `bytes` length is
checked before its Rust copy and then passes through aggregate volume limits.
Memory already allocated by Python and memory retained by caller writers or
callbacks cannot be bounded or accounted by Rust; callers must bound their own
provider and sink behavior.

Passwords passed as Python strings remain in Python-managed memory. Rust cannot
erase that caller object. Its Rust-owned buffer is moved immediately into
zeroizing storage, cleared after core construction, and the core retains only
its existing per-archive zeroizing representation.

## Limits and cancellation

Defaults are documented in `THREAT_MODEL.md` and implemented in `Limits`.
Builder overrides are explicit and per archive/session. A smaller entry limit
still applies inside a larger total limit. Dictionary memory is accounted
before allocation and does not include uncharged hidden caches. Parser and
encoded-header recursion is explicitly bounded. AES KDF power is checked before
hashing; each KDF round is charged. Cancellation and work-budget checks occur
between bounded volume/input reads and within long decoder/filter loops.
External-folder resolution validates its AdditionalStreamsInfo model and
folder-output `DataIndex` before decoding, charges all decoded outputs against
the cumulative output limit, reparses from the original header under the same
global count/property limits, and requires exact consumption of the selected
output. It may retain those bounded outputs because later `DataIndex` values can
refer to any folder. The bounded stored-header copy cannot exceed
`max_header_bytes`.
Supported LZMA decoding uses the output buffer itself as history. Third-party
codec adapters conservatively charge their working window/block memory before
decoder construction, bound output and input, and convert dependency panics to
typed format failures. `Archive::verify` processes every additional folder,
including unreferenced folders, before the main streams and drops each decoded
additional output before continuing. Additional and main folders share the
same total-output allowance, dictionary/KDF limits, per-archive password,
work budget, and cancellation token. Packed, folder, logical-substream, and
member CRCs retain distinct checksum scopes. Main-stream verification accounts
each folder once against total output, and natural-order `extract_entries_to`
does the same; one-member
random access bounds the complete containing folder. Every known solid
substream size is checked against the entry limit before folder decode. An
unknown final substream is decoded only where the codec supports EOS and with
an entry-sized remaining allowance; an unknown non-final substream is rejected
before decode. This is configured bounded memory, not constant-memory
streaming.

An open archive exposes checked `ArchiveResources` categories for its logical
input, validated metadata payload, per-archive secret buffer, and total. An
active `MemberReader` reports the complete decoded folder allocation that it
retains, including bytes outside the selected member in a solid folder.
Allocator bookkeeping and stack frames are not presented as archive payload;
input/header/name/property/count, dictionary/window, and output allocations
remain enforced by their separate configured limits. Natural-order sink
extraction retains at most one decoded folder and advances one substream cursor
rather than accumulating prior folders.

Deflate64 charges its fixed 64 KiB window during validated model construction,
before packed-input copying, and rechecks it at decoder entry. Its Huffman
alphabets are fixed-size stack values; attacker-sized output growth is checked
against the declared size and operation cap before fallible reservation. Every
bitstream refill and match-copy loop observes cancellation/work limits.

Unknown coder outputs use a closed allowlist. LZMA/LZMA2 and
Deflate/Deflate64 must reach their codec EOS/final block, and LZMA EOS also
requires a final range state with exact packed-input consumption; Copy and
size-preserving filters derive output from bounded input; BCJ2 ends with its
bounded main stream. PPMd and AES need declared sizes. BZip2, Brotli, LZ4, and
Zstandard are conservatively rejected for unknown output until their adapters
can prove exact framed-input consumption. No decoder invents a size.

## Password and volume boundaries

`Password` owns a zeroizing UTF-16LE buffer inside one `Archive`. Derived AES
keys, IVs, and digest buffers are zeroized and never cached globally. Error
messages do not echo passwords. Because AES-CBC is unauthenticated, encrypted
structural, size, or CRC failures are deliberately classified as
`WrongPasswordOrCorrupt` where the two causes cannot be separated.

`VolumeProvider` is an untrusted callback boundary. The archive layer checks
`max_volumes`, each reported length, the aggregate input limit, conversions,
and cancellation/work before reading or copying. Short reads are `Io`; a
provider-reported absent required part is `MissingVolume` with the expected
name. A terminal absent part is accepted only after the complete logical
archive bounds validate. The path provider performs no network discovery.

## Review gates

Security-sensitive changes must add a minimized regression and update all
affected compatibility, provenance, dependency, fuzzing, and benchmark claims.
Fuzz crashes are treated as security bugs until triaged. Corpus files need an
origin, hash, license/redistribution record, and expected oracle result before
commit.

No separate valid or malformed corpus is currently available. Security
regressions therefore use deterministic hostile constructors, CRC-correct
semantic mutation, exhaustive truncation/limit cases, and the six
coverage-guided fuzz targets. Temporary `7zz` output supplies positive
differential evidence only and is deleted after each opt-in test.

The one retained oracle-authored compressed payload is a 49-byte test-only PPMd
stream over project-authored text; `CORPUS.md` records its exact 7zz 26.02
command, properties, CRC, and hashes. Production code does not invoke the
oracle. Unit and public-API regressions require exact output and reject every
strict packed prefix, meaningful corruption, low dictionary/output/work
budgets, and pre-cancellation before the vector is admitted as positive
evidence.

The exact-version capability probes are classification tests, not validation
shortcuts. Their observed `7zz` rejection of unknown packed and non-final sizes
does not weaken Rust's checked-range policy, and Rust's ability to derive a
bounded Copy output does not generalize EOS permission to another codec.
Synthesized comment or alternative-coder candidates remain hostile input unless
the normal parser, model, and decoder invariants accept them.

The Windows oracle job verifies the official 26.02 installer SHA-256 before
executing it and installs it only inside the ephemeral runner. Its executable
override is read only by the ignored integration probe; no production library,
CLI, binding, or runtime path can invoke the oracle. In the hardened follow-up
at `24cf688`, the ordinary control passed oracle and Rust verification and ADS
creation passed byte-for-byte readback. Raw AES, `-sni`, and `-sns` then failed
during authoring with `System ERROR: Not implemented`, so none supplied feature
bytes to the Rust parser. The test keeps at most six sanitized diagnostic
marker/context lines and fails on a changed stage classification. Those test
diagnostics and assertions neither admit a runtime feature nor weaken any
hostile-input boundary.

The generated method/property matrix is positive differential evidence, not an
allocation or validation bypass. Requested dictionary/model sizes are asserted
from the validated coder properties and remain subject to the normal configured
limits before decoding. Its negative pass rejects packed corruption, strategic
physical truncation, low dictionary/output/work budgets, and cancellation for
every applicable generated form. CRC-correct plain-header mutations reach
logical packed truncation and oversized/empty coder-property validation without
disabling either header CRC. Its temporary archives are deleted.
