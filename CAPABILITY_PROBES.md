# Stock 7zz capability probes

## Purpose and boundary

`crates/un7z/tests/capability_probe.rs` is an opt-in, corpus-free black-box
suite for the exact stock `7zz` 26.02 executable. It separates four facts that
must not be conflated:

- whether `7zz` can author a candidate archive;
- whether `7zz` can read or test it;
- whether the Rust production API can open and verify it; and
- whether a platform-specific semantic effect was actually preserved.

The suite does not invoke `7zz` from the library or CLI, does not inspect or
adapt official 7-Zip source, and does not turn a synthesized candidate into a
positive compatibility fixture merely because a parser accepts it. Generated
files live in a uniquely named temporary directory and are removed after the
run.

## Running the probes

Place the exact stock `7zz` 26.02 executable on `PATH`, or set `UN7Z_7ZZ` to
the exact stock console executable. The override permits the official Windows
`7z.exe` name without changing the library or CLI environment. Then run:

```text
cargo test -p un7z --test capability_probe \
  stock_7zz_2602_capability_probe_report \
  --all-features --locked -- --ignored --nocapture
```

Each result is one tab-separated line prefixed with `UN7Z_7ZZ_PROBE`. The
columns are probe name, author status, oracle-read status, Rust-read status,
generated archive SHA-256 when one exists, and a bounded diagnostic. The
platform-neutral statuses are asserted as an exact 26.02 baseline so a changed
oracle result fails the ignored test instead of silently changing a claim.

`accepted-with-warning` means the command exited successfully but emitted a
warning marker. It is not equivalent to semantic support.

The `windows-7zip-capability` GitHub Actions job downloads the official x64
26.02 installer release asset, requires SHA-256
`6745fa76dc2ea031596d8678f6f6b99c3c1b435b4164a63485adbbc7b8d82ef0`
before executing it, installs into the ephemeral runner directory, sets
`UN7Z_7ZZ` to that installation's `7z.exe`, and runs this ignored test with
output visible. The binary is a test oracle only; it is not cached, packaged,
or available to runtime code.

## Observed 26.02 results

The following results were observed on 2026-07-19 with the x64 macOS build of
stock `7zz` 26.02:

| Probe | Fixture origin | 7zz result | Rust result | Interpretation |
| --- | --- | --- | --- | --- |
| File comment candidate | Original CRC-correct synthetic Copy archive | Test/list exit successfully with `Unsupported feature` warnings; no `Comment` field is listed | Opens and verifies; bounded raw property is retained | Not evidence that 7zz supports this comment serialization or that Rust semantically decodes comments |
| Archive comment candidate | Original CRC-correct synthetic Copy archive | Test/list succeed without warning, but no `Comment` field is listed | Opens and verifies; bounded raw archive property is retained | Appears ignored as an archive property; not semantic-comment evidence |
| Alternative Copy coder candidate | Original CRC-correct synthetic Copy archive | Rejected with `Unsupported feature` | Typed `UnsupportedFeature` | No demonstrated 26.02 parity gap; candidate validity beyond the black-box result is not claimed |
| Unknown Copy unpacked size | Original CRC-correct synthetic Copy archive | Rejected with `Data Error` | Opens and verifies by deriving Copy output from bounded input | Rust's safe extension is not credited as 7zz compatibility |
| Unknown packed size | Original CRC-correct synthetic Copy archive | Rejected with `Headers Error` | Typed `UnsupportedFeature` | Current Rust boundary agrees with the observed oracle rejection |
| Unknown non-final substream size | Original CRC-correct two-member Copy archive | Rejected with `Headers Error` | Typed `UnsupportedFeature` during verification | Current structured rejection remains appropriate |
| Raw `AES256CBC` author request | `7zz a -m0=AES256CBC` | Authoring fails with `E_NOTIMPL` | Not run because no archive was produced | `7zz i` advertises the decoder ID, but read compatibility remains unproven without a permissibly sourced fixture |
| Hard-link switch | `7zz`-authored `-snh` archive over two host hard links | Author/test/extract succeed; extracted paths are distinct files on this host | Opens and verifies both entries | Hard-link relationship preservation is not established by this host result |
| Symbolic-link switch | `7zz`-authored `-snl` archive | Author/test/extract succeed and restore the relative target | Opens and verifies both entries | Confirms the already documented symlink slice |
| NT security | Windows-only `-sni` probe | Not applicable on this host | Not run | Requires a Windows security-descriptor fixture |
| NTFS alternate streams | Windows-only `-sns` probe | Not applicable on this host | Not run | Requires a Windows NTFS ADS fixture |

The six deterministic synthesized archives had these SHA-256 values:

| Probe | SHA-256 |
| --- | --- |
| File comment candidate | `0613dd8ff540059ce5fb9cabc5ab876afa98fb9c1c6945a571a86ad4743ad6f4` |
| Archive comment candidate | `ffcce8a0d54efc09c6059309be3d7c6c89ae16ad6ea156ce7d247a4bb8b0f46d` |
| Alternative Copy coder candidate | `a1e1cbd05c69e982cb44fe620afbc5e7a6d27e8cd5f928a1d4c6ccd7d7e39423` |
| Unknown Copy unpacked size | `4bd9c052eb719182bc574ac88bf681f7eeefa05ef949f646d285f380ac34ef1d` |
| Unknown packed size | `5ee94cbc6de923ad71f97b3b9156df1019c0ac7551c65337ba0d7861704a353f` |
| Unknown non-final substream size | `2aa96e58bc47a5da7e42d26fc8986eea031deafacab695eec31abc2c1edf74d3` |

These hashes identify ephemeral test construction, not committed corpus files
or redistributed oracle material. `7zz`-authored link archives include host
metadata and therefore are not assigned stable hashes.

## Remaining probe work

The exact-version Windows job is configured but has not yet produced an
observed repository result. Review its first `nt-security` and `ntfs-ads` TSV
records, record the exact outcomes here, and only then decide whether either is
positive metadata evidence or an implementation gap. A raw `AES256CBC` read
probe, a positive alternative-coder archive, or a semantic comment fixture may
be added only when its bytes have an acceptable documented origin and
redistribution status. Multi-output coder support likewise remains a
conditional implementation item until a valid stock-accepted method graph is
available.

No probe result justifies weakening checked ranges, unknown-size policy, path
validation, CRC enforcement, or typed unsupported errors.
