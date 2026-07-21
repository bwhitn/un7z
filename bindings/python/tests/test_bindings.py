from __future__ import annotations

import binascii
import importlib.metadata
import io
import pathlib
import tempfile
import threading
import time
import unittest

import un7z
import un7z._native as native


SIGNATURE = b"7z\xbc\xaf\x27\x1c"
HELLO_DOT_Z = bytes.fromhex(
    "1f9d9068cab061f306441d3769f08018f3a60d1c3965e6cc5100"
)


def raw_lz4_frame(payload: bytes) -> bytes:
    if len(payload) > 64 * 1024:
        raise ValueError("test LZ4 payload exceeds one block")
    block = b""
    if payload:
        block_header = (len(payload) | (1 << 31)).to_bytes(4, "little")
        block = block_header + payload
    return b"\x04\x22\x4d\x18\x60\x40\x82" + block + b"\0\0\0\0"


def raw_zstandard_frame(payload: bytes) -> bytes:
    if len(payload) > 255:
        raise ValueError("test Zstandard payload exceeds one-byte content size")
    block_header = ((len(payload) << 3) | 1).to_bytes(4, "little")[:3]
    return b"\x28\xb5\x2f\xfd\x20" + bytes((len(payload),)) + block_header + payload


def encode_uint(value: int) -> bytes:
    if value < 0 or value > 0xFFFF_FFFF_FFFF_FFFF:
        raise ValueError("fixture integer is outside u64")
    for extra in range(9):
        if extra == 8 or value < (1 << (7 * (extra + 1))):
            prefix = (0xFF << (8 - extra)) & 0xFF
            high_mask = 0 if extra == 8 else (0x7F >> extra)
            first = prefix | ((value >> (8 * extra)) & high_mask)
            low = bytes((value >> (8 * index)) & 0xFF for index in range(extra))
            return bytes((first,)) + low
    raise AssertionError("unreachable fixture integer encoding")


def crc32(data: bytes) -> int:
    return binascii.crc32(data) & 0xFFFF_FFFF


def copy_archive(payload: bytes, raw_name: list[int] | None = None) -> bytes:
    name_units = raw_name if raw_name is not None else [ord(character) for character in "member.bin"]

    size = len(payload)
    streams = bytearray((0x06,))
    streams += encode_uint(0)
    streams += encode_uint(1)
    streams.append(0x09)
    streams += encode_uint(size)
    streams.append(0x00)
    streams += bytes((0x07, 0x0B))
    streams += encode_uint(1)
    streams.append(0)
    streams += encode_uint(1)
    streams += bytes((1, 0))
    streams.append(0x0C)
    streams += encode_uint(size)
    streams += bytes((0x0A, 1))
    streams += crc32(payload).to_bytes(4, "little")
    streams += bytes((0x00, 0x00))

    name_property = bytearray((0,))
    for unit in name_units:
        name_property += unit.to_bytes(2, "little")
    name_property += b"\0\0"
    files = bytearray()
    files += encode_uint(1)
    files.append(0x11)
    files += encode_uint(len(name_property))
    files += name_property
    files.append(0)

    next_header = bytearray((0x01, 0x04))
    next_header += streams
    next_header.append(0x05)
    next_header += files
    next_header.append(0)

    start_fields = bytearray()
    start_fields += size.to_bytes(8, "little")
    start_fields += len(next_header).to_bytes(8, "little")
    start_fields += crc32(next_header).to_bytes(4, "little")
    return (
        SIGNATURE
        + bytes((0, 4))
        + crc32(start_fields).to_bytes(4, "little")
        + start_fields
        + payload
        + next_header
    )


def bit_vector(values: list[bool]) -> bytes:
    output = bytearray((len(values) + 7) // 8)
    for index, value in enumerate(values):
        if value:
            output[index // 8] |= 0x80 >> (index % 8)
    return bytes(output)


def solid_copy_archive(
    entries: list[tuple[str, bytes | None]],
    *,
    corrupt_stream_index: int | None = None,
) -> bytes:
    streamed = [payload for _, payload in entries if payload is not None]
    if len(streamed) < 2:
        raise ValueError("solid fixture requires at least two streamed entries")
    payload = b"".join(streamed)

    streams = bytearray((0x06,))
    streams += encode_uint(0)
    streams += encode_uint(1)
    streams.append(0x09)
    streams += encode_uint(len(payload))
    streams += bytes((0x0A, 1))
    streams += crc32(payload).to_bytes(4, "little")
    streams += bytes((0x00, 0x07, 0x0B))
    streams += encode_uint(1)
    streams.append(0)
    streams += encode_uint(1)
    streams += bytes((1, 0))
    streams.append(0x0C)
    streams += encode_uint(len(payload))
    streams += bytes((0x0A, 1))
    streams += crc32(payload).to_bytes(4, "little")
    streams.append(0)
    streams += bytes((0x08, 0x0D))
    streams += encode_uint(len(streamed))
    streams.append(0x09)
    for member in streamed[:-1]:
        streams += encode_uint(len(member))
    streams += bytes((0x0A, 1))
    for index, member in enumerate(streamed):
        checksum = crc32(member)
        if index == corrupt_stream_index:
            checksum ^= 1
        streams += checksum.to_bytes(4, "little")
    streams += bytes((0, 0))

    files = bytearray()
    files += encode_uint(len(entries))
    empty_streams = [member is None for _, member in entries]
    if any(empty_streams):
        empty_stream_vector = bit_vector(empty_streams)
        files.append(0x0E)
        files += encode_uint(len(empty_stream_vector))
        files += empty_stream_vector
        empty_file_vector = bit_vector([True for empty in empty_streams if empty])
        files.append(0x0F)
        files += encode_uint(len(empty_file_vector))
        files += empty_file_vector
    name_property = bytearray((0,))
    for name, _ in entries:
        for unit in name.encode("utf-16-le"):
            name_property.append(unit)
        name_property += b"\0\0"
    files.append(0x11)
    files += encode_uint(len(name_property))
    files += name_property
    files.append(0)

    next_header = bytearray((0x01, 0x04))
    next_header += streams
    next_header.append(0x05)
    next_header += files
    next_header.append(0)

    start_fields = bytearray()
    start_fields += len(payload).to_bytes(8, "little")
    start_fields += len(next_header).to_bytes(8, "little")
    start_fields += crc32(next_header).to_bytes(4, "little")
    return (
        SIGNATURE
        + bytes((0, 4))
        + crc32(start_fields).to_bytes(4, "little")
        + start_fields
        + payload
        + next_header
    )


class CollectEntrySink:
    def __init__(self) -> None:
        self.events: list[tuple[object, ...]] = []
        self.entries: dict[int, bytearray] = {}
        self.chunks: list[int] = []

    def begin_entry(self, entry: un7z.Entry, size: int) -> None:
        self.events.append(("begin", entry.index, entry.name, size))
        self.entries[entry.index] = bytearray()

    def write_entry(self, index: int, chunk: bytes) -> None:
        self.events.append(("write", index, len(chunk)))
        self.entries[index].extend(chunk)
        self.chunks.append(len(chunk))

    def finish_entry(self, index: int) -> None:
        self.events.append(("finish", index))


class BindingTests(unittest.TestCase):
    def test_distribution_and_native_module_names(self) -> None:
        self.assertEqual(importlib.metadata.version("un7z"), "0.1.0")
        self.assertEqual(un7z.__version__, "0.1.0")
        self.assertEqual(native.__name__, "un7z._native")
        self.assertEqual(un7z.Archive.__module__, "un7z._native")
        self.assertEqual(un7z.CompressedStream.__module__, "un7z._native")
        self.assertEqual(un7z.StreamInfo.__module__, "un7z._native")
        self.assertEqual(un7z.FormatError.__module__, "un7z._native")
        self.assertEqual(
            native.IMPLEMENTATION_STATUS,
            "phase-7-python-binding-plus-streams-pre-alpha",
        )
        self.assertGreater(native.DEFAULT_MAX_WORK_UNITS, 0)

    def test_standalone_stream_info_and_bounded_extraction(self) -> None:
        lz4_payload = b"standalone lz4 " * 2_000
        cases = [
            (raw_lz4_frame(lz4_payload), "lz4", lz4_payload),
            (raw_zstandard_frame(b"standalone zstandard"), "zstandard", b"standalone zstandard"),
            (HELLO_DOT_Z, "unix-compress", b"hello unix compress\n"),
        ]
        for encoded, expected_format, expected in cases:
            with self.subTest(format=expected_format):
                stream = un7z.open_stream_bytes(encoded)
                self.assertIsInstance(stream, un7z.CompressedStream)
                self.assertEqual(stream.info.format, expected_format)
                self.assertEqual(stream.info.compressed_size, len(encoded))
                self.assertEqual(stream.retained_input_bytes, len(encoded))

                writer = io.BytesIO()
                self.assertEqual(stream.extract_to(writer), len(expected))
                self.assertEqual(writer.getvalue(), expected)

                chunks: list[bytes] = []
                self.assertEqual(stream.stream(lambda chunk: chunks.append(chunk)), len(expected))
                self.assertEqual(b"".join(chunks), expected)
                self.assertLessEqual(max(map(len, chunks)), 8 * 1024)
                self.assertIsNone(stream.verify())

        lz4_info = un7z.open_stream_bytes(cases[0][0]).info
        self.assertEqual(lz4_info.frame_count, 1)
        self.assertEqual(lz4_info.maximum_block_bytes, 64 * 1024)
        self.assertIsNone(lz4_info.uncompressed_size)
        zstandard_info = un7z.open_stream_bytes(cases[1][0]).info
        self.assertEqual(zstandard_info.uncompressed_size, len(cases[1][2]))
        self.assertEqual(zstandard_info.maximum_window_bytes, len(cases[1][2]))
        compress_info = un7z.open_stream_bytes(cases[2][0]).info
        self.assertEqual(compress_info.maximum_code_bits, 16)
        self.assertTrue(compress_info.block_mode)
        self.assertEqual(compress_info.decoder_dictionary_bytes, 256 * 1024)

    def test_standalone_stream_explicit_formats_paths_and_failures(self) -> None:
        zstandard = raw_zstandard_frame(b"path stream")
        self.assertEqual(
            un7z.open_stream_bytes(zstandard, format="zstd").info.format,
            "zstandard",
        )
        self.assertEqual(
            un7z.open_stream_bytes(HELLO_DOT_Z, format="z").info.format,
            "unix-compress",
        )
        with self.assertRaises(ValueError):
            un7z.open_stream_bytes(zstandard, format="zip")
        with self.assertRaises(un7z.FormatError) as caught:
            un7z.open_stream_bytes(zstandard, format="lz4")
        self.assertEqual(caught.exception.format, "lz4")

        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "input.zst"
            path.write_bytes(zstandard)
            stream = un7z.open_stream_path(path)
            writer = io.BytesIO()
            self.assertEqual(stream.extract_to(writer), len(b"path stream"))
            self.assertEqual(writer.getvalue(), b"path stream")
            self.assertEqual(list(pathlib.Path(directory).iterdir()), [path])

        limited = un7z.Limits(max_total_output_bytes=4)
        with self.assertRaises(un7z.LimitExceededError) as caught:
            un7z.open_stream_bytes(zstandard, limits=limited)
        self.assertEqual(caught.exception.limit, "total_output_bytes")

        stream = un7z.open_stream_bytes(HELLO_DOT_Z, limits=limited)
        with self.assertRaises(un7z.LimitExceededError):
            stream.verify()
        with self.assertRaises(un7z.LimitExceededError) as caught:
            un7z.open_stream_bytes(
                HELLO_DOT_Z,
                limits=un7z.Limits(max_stream_frames=0),
            )
        self.assertEqual(caught.exception.limit, "stream_frames")
        with self.assertRaises(un7z.LimitExceededError) as caught:
            un7z.open_stream_bytes(zstandard, max_work_units=1)
        self.assertEqual(caught.exception.limit, "work_units")

        class MarkerError(Exception):
            pass

        stream = un7z.open_stream_bytes(raw_lz4_frame(b"callback"))

        def fail(_chunk: bytes) -> None:
            raise MarkerError("stream callback marker")

        with self.assertRaisesRegex(MarkerError, "stream callback marker"):
            stream.stream(fail)
        with self.assertRaises(un7z.CancelledError):
            stream.stream(lambda _chunk: False)

        cancellation = un7z.CancellationToken()
        cancellation.cancel()
        with self.assertRaises(un7z.CancelledError):
            stream.verify(cancellation=cancellation)

    def test_open_list_raw_metadata_and_resources(self) -> None:
        payload = b"python binding"
        raw_name = [ord(character) for character in "directory/member.bin"]
        archive = un7z.open_bytes(copy_archive(payload, raw_name))
        self.assertEqual(len(archive), 1)
        entry = archive.entries()[0]
        self.assertEqual(entry.index, 0)
        self.assertEqual(entry.raw_name, raw_name)
        self.assertEqual(entry.name, "directory/member.bin")
        self.assertEqual(entry.kind, "file")
        self.assertEqual(entry.size, len(payload))
        self.assertEqual(entry.crc32, crc32(payload))
        self.assertTrue(entry.is_safe_path)
        self.assertIsNone(entry.unsafe_path_reason)
        self.assertIsNone(archive.entry(1))
        self.assertGreater(archive.resources.metadata_bytes, 0)
        self.assertEqual(archive.resources.password_bytes, 0)
        self.assertGreaterEqual(archive.resources.retained_bytes, len(payload))

    def test_raw_utf16_and_unsafe_path_are_preserved(self) -> None:
        cases = [
            ([ord("."), ord("."), ord("/"), 0xD800], "traversal"),
            ([ord(character) for character in "/absolute"], "absolute"),
            ([ord(character) for character in "C:\\drive"], "drive"),
            ([ord(character) for character in "\\\\server\\share"], "unc"),
        ]
        for raw_name, reason in cases:
            with self.subTest(reason=reason):
                entry = un7z.open_bytes(copy_archive(b"x", raw_name)).entry(0)
                self.assertIsNotNone(entry)
                assert entry is not None
                self.assertEqual(entry.raw_name, raw_name)
                self.assertFalse(entry.is_safe_path)
                self.assertEqual(entry.unsafe_path_reason, reason)

    def test_writer_and_callback_finish_before_success(self) -> None:
        payload = b"bounded callback output" * 2_000
        archive = un7z.open_bytes(copy_archive(payload))
        writer = io.BytesIO()
        self.assertEqual(archive.extract_entry_to(0, writer), len(payload))
        self.assertEqual(writer.getvalue(), payload)

        chunks: list[bytes] = []
        count = archive.stream_entry(0, lambda chunk: chunks.append(chunk))
        self.assertEqual(count, len(payload))
        self.assertEqual(b"".join(chunks), payload)
        self.assertGreater(len(chunks), 1)
        self.assertLessEqual(max(map(len, chunks)), 8 * 1024)

        class PartialWriter:
            def __init__(self) -> None:
                self.output = bytearray()

            def write(self, chunk: bytes) -> int:
                count = max(1, len(chunk) // 2)
                self.output.extend(chunk[:count])
                return count

        partial = PartialWriter()
        self.assertEqual(archive.extract_entry_to(0, partial), len(payload))
        self.assertEqual(partial.output, payload)

        class ImpossibleWriter:
            def write(self, chunk: bytes) -> int:
                return len(chunk) + 1

        with self.assertRaises(ValueError):
            archive.extract_entry_to(0, ImpossibleWriter())

    def test_callback_exception_and_cancellation_are_preserved(self) -> None:
        archive = un7z.open_bytes(copy_archive(b"callback"))

        class MarkerError(Exception):
            pass

        marker = MarkerError("marker")

        def fail(_: bytes) -> None:
            raise marker

        with self.assertRaises(MarkerError) as raised:
            archive.stream_entry(0, fail)
        self.assertIs(raised.exception, marker)

        class FailingWriter:
            def write(self, _: bytes) -> int:
                raise marker

        with self.assertRaises(MarkerError) as writer_raised:
            archive.extract_entry_to(0, FailingWriter())
        self.assertIs(writer_raised.exception, marker)

        with self.assertRaises(un7z.CancelledError) as cancelled:
            archive.stream_entry(0, lambda _: False)
        self.assertEqual(cancelled.exception.kind, "cancelled")

        reentered = [False]

        def reenter(_: bytes) -> bool:
            archive.verify()
            reentered[0] = True
            return True

        self.assertEqual(archive.stream_entry(0, reenter), len(b"callback"))
        self.assertTrue(reentered[0])

    def test_batch_sink_preserves_natural_entry_boundaries(self) -> None:
        first = b"a" * 9_000
        second = b"b" * 9_000
        archive = un7z.open_bytes(
            solid_copy_archive(
                [("duplicate.bin", first), ("empty.bin", None), ("duplicate.bin", second)]
            )
        )
        sink = CollectEntrySink()
        self.assertEqual(archive.extract_entries_to(sink), len(first) + len(second))
        self.assertEqual(bytes(sink.entries[0]), first)
        self.assertEqual(bytes(sink.entries[1]), b"")
        self.assertEqual(bytes(sink.entries[2]), second)
        self.assertTrue(sink.chunks)
        self.assertLessEqual(max(sink.chunks), 8 * 1024)
        self.assertEqual(
            [event for event in sink.events if event[0] != "write"],
            [
                ("begin", 0, "duplicate.bin", len(first)),
                ("finish", 0),
                ("begin", 1, "empty.bin", 0),
                ("finish", 1),
                ("begin", 2, "duplicate.bin", len(second)),
                ("finish", 2),
            ],
        )

    def test_batch_crc_callback_and_cancellation_failures_stop_boundaries(self) -> None:
        entries = [("first.bin", b"first"), ("second.bin", b"second")]
        corrupt = un7z.open_bytes(solid_copy_archive(entries, corrupt_stream_index=1))
        corrupt_sink = CollectEntrySink()
        with self.assertRaises(un7z.ChecksumError) as checksum:
            corrupt.extract_entries_to(corrupt_sink)
        self.assertEqual(checksum.exception.scope, "member")
        self.assertEqual(checksum.exception.member_index, 1)
        self.assertIn(("finish", 0), corrupt_sink.events)
        self.assertNotIn(("finish", 1), corrupt_sink.events)

        archive = un7z.open_bytes(solid_copy_archive(entries))

        class MarkerError(Exception):
            pass

        begin_marker = MarkerError("begin callback marker")

        class BeginFailingSink(CollectEntrySink):
            def begin_entry(self, entry: un7z.Entry, size: int) -> None:
                raise begin_marker

        with self.assertRaises(MarkerError) as begin_callback:
            archive.extract_entries_to(BeginFailingSink())
        self.assertIs(begin_callback.exception, begin_marker)

        marker = MarkerError("batch callback marker")

        class FailingSink(CollectEntrySink):
            def write_entry(self, index: int, chunk: bytes) -> None:
                if index == 1:
                    raise marker
                super().write_entry(index, chunk)

        with self.assertRaises(MarkerError) as callback:
            archive.extract_entries_to(FailingSink())
        self.assertIs(callback.exception, marker)

        finish_marker = MarkerError("finish callback marker")

        class FinishFailingSink(CollectEntrySink):
            def finish_entry(self, index: int) -> None:
                if index == 0:
                    raise finish_marker
                super().finish_entry(index)

        with self.assertRaises(MarkerError) as finish_callback:
            archive.extract_entries_to(FinishFailingSink())
        self.assertIs(finish_callback.exception, finish_marker)

        token = un7z.CancellationToken()

        class CancellingSink(CollectEntrySink):
            def write_entry(self, index: int, chunk: bytes) -> None:
                super().write_entry(index, chunk)
                token.cancel()

        cancelled_sink = CancellingSink()
        with self.assertRaises(un7z.CancelledError):
            archive.extract_entries_to(cancelled_sink, cancellation=token)
        self.assertNotIn(("finish", 0), cancelled_sink.events)

        class FalseSink(CollectEntrySink):
            def begin_entry(self, entry: un7z.Entry, size: int) -> bool:
                super().begin_entry(entry, size)
                return False

        with self.assertRaises(un7z.CancelledError):
            archive.extract_entries_to(FalseSink())

    def test_batch_output_limit_and_shared_work_budget(self) -> None:
        first = b"a" * 9_000
        second = b"b" * 9_000
        archive_bytes = solid_copy_archive([("first.bin", first), ("second.bin", second)])
        limited = un7z.open_bytes(
            archive_bytes,
            limits=un7z.Limits(max_entry_output_bytes=len(first) - 1),
        )
        limited_sink = CollectEntrySink()
        with self.assertRaises(un7z.LimitExceededError) as output_limit:
            limited.extract_entries_to(limited_sink)
        self.assertEqual(output_limit.exception.limit, "entry_output_bytes")
        self.assertEqual(limited_sink.events, [])

        archive = un7z.open_bytes(archive_bytes)

        def minimum_work(operation: object) -> int:
            if not callable(operation):
                raise TypeError("test operation must be callable")
            lower = -1
            upper = 1
            while True:
                try:
                    operation(upper)
                    break
                except un7z.LimitExceededError as error:
                    if error.limit != "work_units":
                        raise
                    upper *= 2
            while upper - lower > 1:
                middle = (upper + lower) // 2
                try:
                    operation(middle)
                    upper = middle
                except un7z.LimitExceededError as error:
                    if error.limit != "work_units":
                        raise
                    lower = middle
            return upper

        first_work = minimum_work(
            lambda maximum: archive.extract_entry_to(
                0, io.BytesIO(), max_work_units=maximum
            )
        )
        second_work = minimum_work(
            lambda maximum: archive.extract_entry_to(
                1, io.BytesIO(), max_work_units=maximum
            )
        )
        batch_work = minimum_work(
            lambda maximum: archive.extract_entries_to(
                CollectEntrySink(), max_work_units=maximum
            )
        )
        self.assertGreater(batch_work, max(first_work, second_work))
        self.assertLess(batch_work, first_work + second_work)

        with self.assertRaises(un7z.LimitExceededError) as shared:
            archive.extract_entries_to(
                CollectEntrySink(),
                max_work_units=max(first_work, second_work),
            )
        self.assertEqual(shared.exception.limit, "work_units")

    def test_corrupt_member_never_reports_success(self) -> None:
        archive_bytes = bytearray(copy_archive(b"checksum"))
        archive_bytes[32] ^= 1
        archive = un7z.open_bytes(bytes(archive_bytes))
        output = io.BytesIO()
        with self.assertRaises(un7z.ChecksumError) as raised:
            archive.extract_entry_to(0, output)
        self.assertEqual(raised.exception.kind, "checksum")
        self.assertIn(raised.exception.scope, {"folder", "member"})

    def test_structured_format_limit_work_and_cancellation_errors(self) -> None:
        with self.assertRaises(un7z.FormatError) as malformed:
            un7z.open_bytes(b"not a 7z archive")
        self.assertEqual(malformed.exception.kind, "format")
        self.assertTrue(malformed.exception.detail)

        limits = un7z.Limits(max_total_input_bytes=1)
        with self.assertRaises(un7z.LimitExceededError) as limited:
            un7z.open_bytes(copy_archive(b"x"), limits=limits)
        self.assertEqual(limited.exception.limit, "total_input_bytes")
        self.assertEqual(limited.exception.maximum, 1)

        with self.assertRaises(un7z.LimitExceededError) as work:
            un7z.open_bytes(copy_archive(b"x"), max_work_units=0)
        self.assertEqual(work.exception.limit, "work_units")

        token = un7z.CancellationToken()
        token.cancel()
        self.assertTrue(token.is_cancelled)
        with self.assertRaises(un7z.CancelledError):
            un7z.open_bytes(copy_archive(b"x"), cancellation=token)

    def test_every_limit_is_exposed_and_password_is_archive_scoped(self) -> None:
        limits = un7z.Limits(
            max_header_bytes=1,
            max_files=2,
            max_folders=3,
            max_coders_per_folder=4,
            max_total_coders=5,
            max_streams_per_folder=6,
            max_total_streams=7,
            max_stream_frames=8,
            max_substreams=9,
            max_header_properties=10,
            max_coder_property_bytes=11,
            max_name_bytes_per_entry=12,
            max_total_name_bytes=13,
            max_dictionary_bytes=14,
            max_entry_output_bytes=15,
            max_total_output_bytes=16,
            max_volumes=17,
            max_total_input_bytes=18,
            max_kdf_power=19,
            max_recursion_depth=20,
            sfx_scan_limit=21,
        )
        self.assertEqual(limits.max_header_bytes, 1)
        self.assertEqual(limits.max_total_input_bytes, 18)
        self.assertEqual(limits.max_stream_frames, 8)
        self.assertEqual(limits.sfx_scan_limit, 21)

        archive = un7z.open_bytes(copy_archive(b"secret state"), password="temporary")
        self.assertGreater(archive.resources.password_bytes, 0)

    def test_path_and_python_volume_provider(self) -> None:
        archive_bytes = copy_archive(b"volumes")
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory, "sample.7z")
            path.write_bytes(archive_bytes)
            self.assertEqual(len(un7z.open_path(path)), 1)

        split = len(archive_bytes) // 2
        parts = [archive_bytes[:split], archive_bytes[split:]]

        class Provider:
            def __init__(self) -> None:
                self.requests: list[tuple[int, str]] = []

            def open_volume(self, index: int, expected: str) -> bytes | None:
                self.requests.append((index, expected))
                return parts[index] if index < len(parts) else None

        provider = Provider()
        archive = un7z.open_volumes(provider, "memory.001")
        self.assertEqual(len(archive), 1)
        self.assertEqual(provider.requests[:2], [(0, "memory.001"), (1, "memory.002")])

        with self.assertRaises(un7z.MissingVolumeError) as missing:
            un7z.open_volumes(lambda index, _: parts[0] if index == 0 else None, "lost.001")
        self.assertEqual(missing.exception.expected, "lost.002")

        with self.assertRaises(un7z.LimitExceededError) as volume_limit:
            un7z.open_volumes(
                lambda index, _: archive_bytes if index == 0 else None,
                "limited.001",
                limits=un7z.Limits(max_total_input_bytes=1),
            )
        self.assertEqual(volume_limit.exception.limit, "total_input_bytes")
        self.assertEqual(volume_limit.exception.requested, len(archive_bytes))
        self.assertEqual(volume_limit.exception.maximum, 1)

        provider_error = RuntimeError("provider marker")

        def fail_provider(_: int, __: str) -> bytes:
            raise provider_error

        with self.assertRaises(RuntimeError) as provider_raised:
            un7z.open_volumes(fail_provider, "failed.001")
        self.assertIs(provider_raised.exception, provider_error)

    def test_rust_only_verification_releases_the_gil(self) -> None:
        archive = un7z.open_bytes(copy_archive(b"g" * (8 * 1024 * 1024)))
        ready = threading.Event()
        stop = threading.Event()
        counter = [0]

        def spin() -> None:
            ready.set()
            while not stop.is_set():
                counter[0] += 1

        worker = threading.Thread(target=spin)
        worker.start()
        self.assertTrue(ready.wait(timeout=5))
        time.sleep(0.01)
        before = counter[0]
        archive.verify()
        after = counter[0]
        stop.set()
        worker.join(timeout=5)
        self.assertFalse(worker.is_alive())
        self.assertGreater(after, before)


if __name__ == "__main__":
    unittest.main()
