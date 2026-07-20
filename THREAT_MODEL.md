# Threat model

Status: Phase 7 Python-FFI review, 2026-07-18. Revisit whenever a provider,
decoder, cryptographic/password layer, filesystem adapter, cache, callback, or
unsafe boundary is added.

## Assets and security goals

The implementation protects process availability and memory, caller-selected
output sinks, password/key confidentiality, archive/member integrity results,
file-to-stream mapping, and host filesystem safety. A malformed archive must
produce a typed error, never a panic, abort, unbounded allocation, unchecked
seek, silent checksum success, or unintended filesystem side effect.

## Attacker capabilities

An attacker may control every byte of every supplied volume, volume length and
read behavior when callbacks are used, archive ordering and duplication,
declared counts/sizes/offsets, coder graphs and properties, compressed data,
checksums, UTF-16 names, timestamps/attributes/modes, encryption parameters,
and password prompts. They may truncate or replace a later volume and may cause
short reads, interruptions, and sink failures.

The caller is trusted to select limits, password, volume provider, entry, and
output sink. The caller can weaken limits deliberately; defaults are the
project's safe baseline, not a containment boundary against a malicious caller.
Rust dependencies and CI tools are supply-chain inputs subject to separate
policy.

## Trust boundaries

1. **Volume boundary:** paths, memory buffers, or callbacks become bounded
   logical bytes only after count, length, and total-byte checks.
2. **Syntax boundary:** raw bytes become raw records, never validated model
   objects.
3. **Semantic boundary:** only fully checked counts, ranges, indices, optional
   values, and mappings become an archive model.
4. **Graph boundary:** only a unique, acyclic, rooted port graph becomes a
   decoder schedule.
5. **Decoder boundary:** validated properties still cannot allocate until the
   memory account approves them.
6. **Output boundary:** bytes are counted and CRC-tracked before being exposed;
   success requires `finish()` or a completed helper.
7. **Filesystem boundary:** raw names remain metadata until an explicit policy
   validates them. The current implementation has no filesystem extraction.
8. **Python FFI boundary:** Python objects become owned Rust input, callbacks,
   or volume handles only through the separate binding adapter. Rust-only work
   runs detached from the interpreter; Python is reattached only for a specific
   provider or sink call, and no borrowed Python reference crosses that region.

## Threats and required mitigations

### Parser panic or memory corruption

Threats include truncation, malformed variable integers, input-derived slice
indices, 32-bit narrowing, and overflowed `offset + size`. The core forbids
unsafe code. Archive paths may not use `unwrap`, `expect`, `panic!`, unchecked
input indexing, unchecked integer casts, or unchecked arithmetic. Parsing uses
fallible conversions, checked arithmetic, bounded readers, exact property
consumption, and fuzz/Miri coverage. Because no separate malformed corpus is
available, CRC-correct generated mutations and bounded grammar constructors
keep semantic parser/graph states reachable instead of relying only on random
signature matches.

### Memory exhaustion

Counts may request huge vectors; LZMA/LZMA2/PPMd and other methods may encode
large dictionaries or models. Limits are checked before capacity reservation or
decoder construction. Dictionary and working memory are charged before
allocation, and allocations use fallible reservation where size remains
attacker-controlled.

Retained state is also observable. `ArchiveResources` reports checked logical
input, validated metadata payload, zeroizing password storage, and their sum.
`MemberReader::retained_bytes` reports the complete decoded folder allocation
held during random/streaming member access, including other members in a solid
folder. These figures exclude allocator bookkeeping and stack frames, whose
sizes are not attacker-declared payload; the underlying input, header/name/
property/count, dictionary/window, and output allocations remain independently
bounded before allocation. Natural-order extraction drops the previous folder
when moving to the next and never retains a growing list of decoded folders.

### CPU exhaustion and decompression bombs

KDF power, parser loops, decoder loops, graph size, output size, and SFX scans
are bounded. Cancellation and work-budget checkpoints occur between input reads
and inside decoder loops. Per-entry and total output are charged before bytes
are released. EOS streams do not bypass output accounting.

Deflate64 adds attacker-controlled Huffman trees, matches up to 65,538 bytes,
and distances up to 65,536 bytes. Code counts are bounded and checked for
oversubscription in fixed stack storage; truncation and reserved symbols are
errors; history cannot precede produced output; and output capacity is checked
before every literal or match. Its fixed window is charged before packed input
is copied. IA64, ARM Thumb, RISC-V, Swap2, and Swap4 are size-preserving and
use checked ranges/conversions with work checkpoints throughout their scans.

### Graph confusion

Invalid or duplicate bind pairs, packed indices, cycles, disconnected ports,
multiple roots, and declaration-order dependencies can route the wrong bytes or
panic. A dedicated graph builder validates all port domains and uniqueness,
performs cycle detection/topological sorting, and produces an immutable
schedule. Decoders never read raw indices.

### Integrity confusion

CRC zero may be mistaken for “missing,” an encrypted stream may yield plausible
garbage, and partial reads may skip final verification. Every optional CRC is
an `Option<u32>`. Start, next, packed-stream, additional-stream,
encoded-header, folder, and member CRCs have separate scopes. Helpers finish
verification before success; streaming callers must call `finish()`. Missing
CRC is reported as metadata,
not silently invented.

### Password disclosure or cross-archive state

Passwords can leak through global caches, debug output, cloned errors, temporary
UTF-16 buffers, or crash artifacts. Passwords are converted once to a
per-archive zeroizing UTF-16LE buffer; derived AES keys, IVs, and digest buffers
are zeroized and are never globally cached. Diagnostics do not contain secret
bytes. Wrong passwords and corruption use the combined
`WrongPasswordOrCorrupt` classification when the format cannot distinguish
them.

The project does not promise side-channel-resistant decompression or KDF timing
beyond using established RustCrypto primitives and avoiding secret-dependent
diagnostics.

### Path and link attacks

Names may contain `..`, roots, drive-relative prefixes, UNC/device prefixes,
NULs, aliases, duplicate names, or symlink targets. Raw UTF-16 and decoded names
are retained unchanged. Validation is separate and cannot alter member ordering
or stream mapping. Automatic extraction is unavailable. A future filesystem
adapter must also define link, collision, platform-reserved-name, and race-safe
creation policy before it is enabled.

### Multi-volume substitution and over-read

A provider may omit, reorder, truncate, grow, or lie about a volume. Requests
carry an exact index/name, and a required absent input returns `MissingVolume`.
Volume count, each reported length, aggregate capacity, conversions, and
cross-volume ranges are checked before copy/decode; reads are checkpointed and
must reach their declared length. A terminal missing suffix is accepted only
after logical archive bounds prove the bytes complete. Reads remain bounded
when encrypted blocks or packed streams cross a boundary.

### SFX false positives

Executable prefixes may contain fake signatures or overflow subsequent ranges.
Scanning is bounded by `sfx_scan_limit`; each full-archive candidate must have
a complete fixed header, valid start-header CRC, supported version, checked
ranges and stored-next-header CRC, and a valid stored syntax/model before
selection. A CRC-correct nested decoy does not mask a later real archive. A bad
early candidate does not authorize reads outside the input. A signature at
absolute offset zero is treated as a regular archive. The narrower diagnostic
`parse_archive_header` API intentionally stops at its documented envelope
boundary.

### Dependency and provenance compromise

A permissively labeled crate may contain copied forbidden source, native code,
or an incomplete license declaration. cargo-deny enforces an allowlist and
source policy, while manual admission reviews packaged notices, origins,
features, unsafe code, and algorithm provenance. Official 7-Zip/p7zip source is
never inspected or used; `7zz` is executable test-oracle input only.

### Python callbacks, reentrancy, and unwinds

A Python volume provider, writer, or stream callback may block, re-enter the
same immutable archive, raise an exception, return an invalid type/count, or
retain every chunk. The adapter carries only owned, thread-safe Python handles
while Rust work is detached, reattaches around one call, validates provider
types and writer counts, and preserves a callback exception as the same Python
exception object. A stream callback returning `False` cancels the operation.
Each operation has its own cancellation token and work budget; no decoder,
password, or operation state is global.

Provider `bytes` are already allocated in Python before Rust can inspect them.
Their length is checked against the input limit before a fallible Rust copy,
and the core separately enforces the aggregate volume bound. Likewise, memory
retained by a Python writer or callback is caller-owned and cannot be included
in the archive resource account. Native output therefore uses bounded chunks
and provides no complete-output return API by default.

Every archive-processing or caller-invoking native operation has an explicit
unwind boundary, and the PyO3 trampoline protects trivial/generated accessors.
Release artifacts
retain `panic = "unwind"`; an unexpected unwind becomes `InternalError`
without copying its payload into Python. A process-global Rust panic hook is
host policy and may run before containment, so archive code must never put a
secret in a panic payload. The binding contains no handwritten unsafe code. PyO3 and
`pyo3-ffi` are the isolated CPython FFI boundary; the core continues to forbid
unsafe code and has no Python dependency.

A password originating as a Python `str` cannot be erased from Python-managed
memory by Rust. The binding documents that limitation, moves its Rust-owned
temporary into zeroizing storage, and passes it only into the core's existing
per-archive zeroizing password path.

## Default resource limits

| Limit | Default |
| --- | ---: |
| Header bytes | 64 MiB |
| Files | 100,000 |
| Folders | 100,000 |
| Coders per folder | 32 |
| Total coders | 100,000 |
| Stream ports per folder | 1,024 |
| Total stream ports | 200,000 |
| Substreams | 100,000 |
| Length-delimited header properties | 100,000 |
| Coder property bytes | 1 MiB |
| Name bytes per entry | 1 MiB |
| Total name bytes | 64 MiB |
| Dictionary memory | 256 MiB |
| Entry output | 2 GiB |
| Total output | 8 GiB |
| Volumes | 1,024 |
| Total input across volumes | 64 GiB |
| KDF power | 24 |
| Parser/encoded-header recursion depth | 64 |
| SFX scan | 1 MiB |

Every field has a builder override. `max_total_input_bytes` is an additional
explicit bound required for volume accounting; the 64 GiB default is a
reviewable project choice rather than a 7z format limit.

## Current implemented boundary and out-of-scope work

The implemented archive attack surface accepts owned bytes, a path, or an
object-safe sequential `VolumeProvider`. It includes bounded SFX discovery,
checked fixed/variable integers,
start/stored-next-header CRC-32, raw Header/EncodedHeader grammar, StreamsInfo,
FilesInfo, bounded properties, a validated owned model, packed archive ranges,
file/substream mapping, and arbitrary rooted acyclic coder graphs with a
topological schedule. The executor supports the exact method/property slices
listed in `COMPATIBILITY.md`: Copy, LZMA, LZMA2, Delta, BCJ, BCJ2, PPC, ARM,
ARM64, SPARC, Deflate, Deflate64, BZip2, PPMd, Brotli, LZ4, Zstandard, IA64,
ARM Thumb, RISC-V, Swap2, Swap4, and AES-256-CBC/SHA-256. Supported encoded and
encrypted headers are recursively resolved. It verifies applicable packed,
additional-stream, encoded-header, folder, and member CRCs and exposes listing,
stdout/sink extraction, and verification.

An encoded header can describe multiple logical substreams. Their declared
known sizes are cumulatively preflighted against header and total-output limits;
decoded ranges must partition each folder output exactly, and bytes are joined
only in validated stream order after the applicable folder/substream CRCs pass.

Count, name, property, dictionary/working-memory, KDF, recursion, volume,
input, header, output, cancellation, and work limits are checked before the
relevant allocation or expensive work. LZMA history is the already-accounted
output buffer; a folder is currently decoded completely in memory. The folder output
is bounded by `max_total_output_bytes`, each selected member is additionally
bounded by `max_entry_output_bytes`, and natural-order archive verification
or `EntrySink` extraction decodes/accounts a solid folder once. Sink
`finish_entry` is withheld until the member CRC succeeds, although bytes from a
member whose trailing CRC fails may already have reached the caller. This does
not claim constant-memory streaming.

The stable default Rust surface exposes only concrete archive sessions,
archive-order entry metadata, resource/error/limit controls, path validators,
member/sink output, and volume callbacks. Raw parser and validated coder-graph
inspection requires the hidden `unstable-internals` test/fuzz feature and has
no compatibility guarantee.

The separate `bindings/python` package exposes the same owned archive model as
`un7z._native`: path/bytes/volume-provider opening, metadata snapshots,
verification, and caller-directed writer/callback extraction. It adds no
parser, graph, decoder, cryptographic, path, or CRC implementation. Python
callbacks can observe unverified bytes before a trailing CRC failure, but a
native extraction call does not return success until the core finalizes all
applicable checks.

All known substream sizes in a selected folder are preflighted against the
entry limit, not only the requested member. For an unknown final substream the
decoder cap is the checked sum of known prefixes plus one entry allowance;
unknown non-final substreams return a typed unsupported-feature error before
packed input is copied. Coder methods, arities, and fixed property lengths are
also preflighted before packed-input materialization.

For an unknown coder output, the executor uses an explicit allowlist rather
than delegating the decision implicitly. LZMA/LZMA2 and Deflate/Deflate64 must
reach EOS/final-block markers; bounded size-preserving methods and BCJ2 derive
termination from input. Methods without a proven end condition return
`UnsupportedFeature`. Unknown packed-stream sizes remain unsupported because
the logical archive range cannot otherwise be bounded.

Sequential path/memory volume assembly, split packed data, encrypted data, and
per-archive password state are implemented under the limits above. Supported
external Name, creation/access/modification time, Windows attribute, and
StartPos streams are decoded from AdditionalStreamsInfo with exact consumption.
Explicit verification also decodes all AdditionalStreamsInfo folders, including
unreferenced ones, before main streams. It checks packed, folder, and logical
substream CRCs, drops one additional folder before starting the next, and shares
the total-output, dictionary, KDF, password, work, and cancellation state with
main-stream verification.
External folder definitions add a staged hostile-input boundary: the stored
header copy is header-bounded; AdditionalStreamsInfo and its folder-output
`DataIndex` are validated before decode; packed, folder, and substream CRCs are
checked; decoding is charged to output/dictionary/work/cancellation limits; and
the selected output must parse the exact declared folder count with no trailing
bytes. The complete header is then reparsed and revalidated so graph and count
limits cover both stages. Semantic comment decoding, Zstandard dictionaries,
and methods explicitly marked unsupported in `COMPATIBILITY.md` return typed
errors or remain preserved bounded raw metadata; they are not compatibility
claims.

The opt-in stock-`7zz` capability suite executes only in integration tests and
uses unique temporary paths. Its result classifications never enter runtime
feature selection. Oracle acceptance without semantic evidence does not relax
validation, and oracle rejection does not replace a Rust malformed-input or
limit regression. Temporary authored and synthesized archives are removed and
are not trusted corpus inputs.

On Windows CI, the black-box oracle installer is fetched from the pinned
official 26.02 release URL, checked against its release SHA-256 before
execution, and installed in an ephemeral runner directory. The test-only
executable override is not read by production code. The job's `-sni` and `-sns`
records are classification output only. The first reviewed run rejected both
switches before creating an archive, so no feature bytes crossed into the Rust
parser and no support claim followed. The revised probe separates the two
inputs, verifies ADS creation by byte-for-byte readback, requires a no-switch
control archive, retains bounded post-error context, and makes a stage change
fail for explicit review. Oracle diagnostics are sanitized and bounded before
publication in the CI summary.

The generated property matrix has the same test-only boundary. It bounds its
deterministic source sizes, disables unintended automatic filters, verifies the
serialized decoder-visible properties, and deletes its unique temporary tree.
It never selects runtime methods or limits, and an oracle-authored archive is
still processed as hostile input by the production parser and decoder.
Semantic mutations recompute both stored-next-header and start-header CRCs so
the parser must reach the changed packed-size or property declaration. They do
not alter production validation, and encrypted inner headers are never treated
as plaintext merely to manufacture coverage.

The deterministic PPMd seed retains only a 49-byte packed test vector authored
by exact stock `7zz` 26.02 from project text. It is never runtime input or a
decoder fallback. Its positive path is paired with every-prefix truncation,
meaningful corruption, property, CRC, dictionary/output/work, and cancellation
regressions, so oracle authorship does not confer trust or bypass any resource
or integrity boundary.

Archive creation, modification, automatic filesystem extraction, ALES
integration, network volume fetching, and isolation from a hostile in-process
Python or Rust caller are not offered.
