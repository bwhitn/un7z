# Error contract

All archive-processing failures use `un7z::Error`. `Error::kind()` returns the
payload-free `ErrorKind` intended for logging policy, callbacks, and a future
FFI layer. Both enums are non-exhaustive; callers must retain a fallback arm.

| Kind | Meaning | Typical caller action |
| --- | --- | --- |
| `Format` | Bytes violate a 7z structural or semantic invariant | Reject the archive |
| `Checksum` | A named start/header/packed/folder/member CRC failed | Discard uncommitted output |
| `UnsupportedMethod` | No decoder exists for the exact method identifier | Report unsupported archive method |
| `UnsupportedFeature` | The archive is valid but uses an unsupported feature slice | Report the stable feature name |
| `LimitExceeded` | A configured count, byte, memory, KDF, recursion, work, or scan bound rejected the operation | Raise a limit only after policy review |
| `MissingVolume` | A required sequential part was unavailable | Request the exact `expected` name |
| `PasswordRequired` | Encrypted content was reached without a password | Retry by opening a new password-scoped session |
| `WrongPasswordOrCorrupt` | Unauthenticated AES-CBC output cannot distinguish a wrong password from corruption | Ask for another password or reject the archive |
| `Cancelled` | The shared cancellation token was set | Stop or retry with a new operation budget |
| `Io` | A provider, input path, or output writer failed | Inspect `source()` and apply I/O policy |

Errors never contain password, derived-key, or decrypted-header bytes.
Attacker-controlled diagnostics are bounded by the parser and use stable scope
or feature names where callers need machine behavior.

An error from `extract_entry_to`, `MemberReader::finish`, or an `EntrySink`
operation can occur after bytes reached the caller. Those bytes are not
verified output. Only the helper's `Ok`, `MemberReader::finish` returning `Ok`,
or `EntrySink::finish_entry` is a success boundary. The core does not delete or
roll back caller-owned destinations.

## Python exception mapping

The `un7z` distribution preserves each stable core category as a distinct
exception below `Un7zError`. Every mapped exception has a stable string
`kind`; payload-bearing errors also expose machine-readable attributes.

| Rust kind | Python exception | Additional attributes |
| --- | --- | --- |
| `Format` | `FormatError` | `detail` |
| `Checksum` | `ChecksumError` | `scope`, `member_index` |
| `UnsupportedMethod` | `UnsupportedMethodError` | `method_id`, `method_id_hex` |
| `UnsupportedFeature` | `UnsupportedFeatureError` | `feature` |
| `LimitExceeded` | `LimitExceededError` | `limit`, `requested`, `maximum` |
| `MissingVolume` | `MissingVolumeError` | `expected` |
| `PasswordRequired` | `PasswordRequiredError` | none |
| `WrongPasswordOrCorrupt` | `WrongPasswordOrCorruptError` | none |
| `Cancelled` | `CancelledError` | none |
| `Io` | `ArchiveIoError` | `io_kind`, `raw_os_error`, `detail` |

`InternalError` is binding-specific and indicates that an unexpected native
unwind was contained. It exposes no panic payload. An exception raised by a
Python volume provider, writer, stream callback, or batch entry-sink method is
re-raised unchanged rather than wrapped as `ArchiveIoError`; callback `False`
is the explicit cancellation signal and produces `CancelledError`.

Violations of the Python callback protocol are caller errors rather than
archive errors: a wrong provider/callback/writer return type raises
`TypeError`, and a writer count larger than its input raises `ValueError`.
Short valid writer counts are honored through the normal write contract.

As in Rust, a Python output call can fail after its writer or callback observed
bytes. For one-entry operations, only a successful return value is the
CRC-verified boundary. For `extract_entries_to`, each `finish_entry(index)` is
called only after that member's applicable CRCs pass; an exception from
`finish_entry` still fails the operation. The binding does not delete, rewind,
or publish a caller-owned destination.
