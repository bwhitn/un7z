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
or `False` to cancel. `open_volumes` accepts a callable or an object with
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
