# un7z for Python

`un7z` is the Python distribution for the repository's security-focused,
unpack-only Rust 7z reader. The package imports as `un7z`; its implementation
module is `un7z._native`.

The binding delegates all parsing, graph validation, decoding, cryptography,
CRC verification, limits, and path classification to the stable Rust core. It
does not create archives and does not automatically extract archive names to
the filesystem.

Decoded output is delivered to a Python writer or bounded callback. A writer
or callback can observe bytes before a trailing archive CRC is checked, so the
operation's successful return is the integrity boundary. Use a temporary
destination when output must be published atomically.

Python retains ownership of any password `str` passed by the caller and cannot
be erased by Rust. Every Rust-side password copy is zeroized and kept only in
the corresponding archive session.

```python
import un7z

archive = un7z.open_path("example.7z")
for entry in archive.entries():
    print(entry.index, entry.name, entry.size, entry.crc32)

with open("caller-selected-output.bin", "wb") as output:
    verified_bytes = archive.extract_entry_to(0, output)
```

`stream_entry(index, callback)` sends the same bounded chunks without first
forming a complete Python output object. Return `None` or `True` to continue,
or `False` to cancel.

`extract_entries_to(sink)` is the natural-order batch surface for solid
archives. It uses one core work budget and cancellation token for the entire
operation and decodes each solid folder at most once. The sink is structural;
archive names remain metadata and are never opened as filesystem paths:

```python
class Sink:
    def begin_entry(self, entry: un7z.Entry, size: int) -> None:
        # Select a destination by entry.index and caller policy, not entry.name.
        ...

    def write_entry(self, index: int, chunk: bytes) -> None:
        # Chunks are bounded (currently at most 4 KiB).
        ...

    def finish_entry(self, index: int) -> None:
        # This callback is the CRC-verified success boundary for the entry.
        ...

verified_bytes = archive.extract_entries_to(Sink())
```

Each sink method returns `None` or `True` to continue, or `False` to cancel.
Python exceptions are re-raised unchanged. `begin_entry` and `write_entry` may
be observed before a later member CRC failure; only `finish_entry` means that
the core verified the applicable member and folder CRCs. A Python exception
raised by `finish_entry` still makes the overall operation fail. Duplicate
names remain separate index-addressed entries, and empty files receive
`begin_entry` followed by `finish_entry` without a write call. Streamless
directories and anti-items intentionally produce no sink event; callers that
need to materialize those records must use `archive.entries()` metadata and
their own validated policy.

`open_volumes` accepts a callable or an object with
`open_volume(index, expected_name)` returning `bytes` or `None`; all returned
parts remain subject to the core volume and aggregate-input limits.

For a local development build:

```text
python -m pip install 'maturin==1.13.3'
maturin develop --manifest-path bindings/python/Cargo.toml
python -m unittest discover -s bindings/python/tests -v
```

See the repository `API.md`, `SECURITY.md`, `COMPATIBILITY.md`, and
`bindings/python/AGENTS.md` for the complete contracts and current support
evidence.
