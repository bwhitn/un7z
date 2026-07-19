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


class BindingTests(unittest.TestCase):
    def test_distribution_and_native_module_names(self) -> None:
        self.assertEqual(importlib.metadata.version("un7z"), "0.1.0")
        self.assertEqual(un7z.__version__, "0.1.0")
        self.assertEqual(native.__name__, "un7z._native")
        self.assertEqual(un7z.Archive.__module__, "un7z._native")
        self.assertEqual(un7z.FormatError.__module__, "un7z._native")
        self.assertEqual(native.IMPLEMENTATION_STATUS, "phase-7-python-binding-pre-alpha")
        self.assertGreater(native.DEFAULT_MAX_WORK_UNITS, 0)

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
            max_substreams=8,
            max_header_properties=9,
            max_coder_property_bytes=10,
            max_name_bytes_per_entry=11,
            max_total_name_bytes=12,
            max_dictionary_bytes=13,
            max_entry_output_bytes=14,
            max_total_output_bytes=15,
            max_volumes=16,
            max_total_input_bytes=17,
            max_kdf_power=18,
            max_recursion_depth=19,
            sfx_scan_limit=20,
        )
        self.assertEqual(limits.max_header_bytes, 1)
        self.assertEqual(limits.max_total_input_bytes, 17)
        self.assertEqual(limits.sfx_scan_limit, 20)

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
