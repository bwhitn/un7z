from __future__ import annotations

import os
from collections.abc import Callable
from typing import Protocol

DEFAULT_MAX_WORK_UNITS: int
IMPLEMENTATION_STATUS: str


class Un7zError(Exception):
    kind: str


class FormatError(Un7zError):
    detail: str


class ChecksumError(Un7zError):
    scope: str
    member_index: int | None


class UnsupportedMethodError(Un7zError):
    method_id: bytes
    method_id_hex: str


class UnsupportedFeatureError(Un7zError):
    feature: str


class LimitExceededError(Un7zError):
    limit: str
    requested: int
    maximum: int


class MissingVolumeError(Un7zError):
    expected: str


class PasswordRequiredError(Un7zError): ...
class WrongPasswordOrCorruptError(Un7zError): ...
class CancelledError(Un7zError): ...


class ArchiveIoError(Un7zError):
    io_kind: str
    raw_os_error: int | None
    detail: str


class InternalError(Un7zError): ...


class Limits:
    def __init__(
        self,
        *,
        max_header_bytes: int | None = ...,
        max_files: int | None = ...,
        max_folders: int | None = ...,
        max_coders_per_folder: int | None = ...,
        max_total_coders: int | None = ...,
        max_streams_per_folder: int | None = ...,
        max_total_streams: int | None = ...,
        max_substreams: int | None = ...,
        max_header_properties: int | None = ...,
        max_coder_property_bytes: int | None = ...,
        max_name_bytes_per_entry: int | None = ...,
        max_total_name_bytes: int | None = ...,
        max_dictionary_bytes: int | None = ...,
        max_entry_output_bytes: int | None = ...,
        max_total_output_bytes: int | None = ...,
        max_volumes: int | None = ...,
        max_total_input_bytes: int | None = ...,
        max_kdf_power: int | None = ...,
        max_recursion_depth: int | None = ...,
        sfx_scan_limit: int | None = ...,
    ) -> None: ...
    @property
    def max_header_bytes(self) -> int: ...
    @property
    def max_files(self) -> int: ...
    @property
    def max_folders(self) -> int: ...
    @property
    def max_coders_per_folder(self) -> int: ...
    @property
    def max_total_coders(self) -> int: ...
    @property
    def max_streams_per_folder(self) -> int: ...
    @property
    def max_total_streams(self) -> int: ...
    @property
    def max_substreams(self) -> int: ...
    @property
    def max_header_properties(self) -> int: ...
    @property
    def max_coder_property_bytes(self) -> int: ...
    @property
    def max_name_bytes_per_entry(self) -> int: ...
    @property
    def max_total_name_bytes(self) -> int: ...
    @property
    def max_dictionary_bytes(self) -> int: ...
    @property
    def max_entry_output_bytes(self) -> int: ...
    @property
    def max_total_output_bytes(self) -> int: ...
    @property
    def max_volumes(self) -> int: ...
    @property
    def max_total_input_bytes(self) -> int: ...
    @property
    def max_kdf_power(self) -> int: ...
    @property
    def max_recursion_depth(self) -> int: ...
    @property
    def sfx_scan_limit(self) -> int: ...


class CancellationToken:
    def __init__(self) -> None: ...
    def cancel(self) -> None: ...
    @property
    def is_cancelled(self) -> bool: ...


class Entry:
    @property
    def index(self) -> int: ...
    @property
    def raw_name(self) -> list[int] | None: ...
    @property
    def name(self) -> str | None: ...
    @property
    def kind(self) -> str: ...
    @property
    def has_stream(self) -> bool: ...
    @property
    def is_empty_file(self) -> bool: ...
    @property
    def is_anti_item(self) -> bool: ...
    @property
    def size(self) -> int | None: ...
    @property
    def crc32(self) -> int | None: ...
    @property
    def creation_time(self) -> int | None: ...
    @property
    def access_time(self) -> int | None: ...
    @property
    def modification_time(self) -> int | None: ...
    @property
    def windows_attributes(self) -> int | None: ...
    @property
    def start_position(self) -> int | None: ...
    @property
    def unix_mode(self) -> int | None: ...
    @property
    def is_symlink(self) -> bool: ...
    @property
    def is_safe_path(self) -> bool: ...
    @property
    def unsafe_path_reason(self) -> str | None: ...


class ArchiveResources:
    @property
    def input_bytes(self) -> int: ...
    @property
    def metadata_bytes(self) -> int: ...
    @property
    def password_bytes(self) -> int: ...
    @property
    def retained_bytes(self) -> int: ...


class Archive:
    def __len__(self) -> int: ...
    def entries(self) -> list[Entry]: ...
    def entry(self, index: int) -> Entry | None: ...
    @property
    def limits(self) -> Limits: ...
    @property
    def resources(self) -> ArchiveResources: ...
    def verify(
        self,
        *,
        cancellation: CancellationToken | None = ...,
        max_work_units: int = ...,
    ) -> None: ...
    def extract_entry_to(
        self,
        index: int,
        writer: _Writer,
        *,
        cancellation: CancellationToken | None = ...,
        max_work_units: int = ...,
    ) -> int: ...
    def stream_entry(
        self,
        index: int,
        callback: Callable[[bytes], bool | None],
        *,
        cancellation: CancellationToken | None = ...,
        max_work_units: int = ...,
    ) -> int: ...


class _Writer(Protocol):
    def write(self, data: bytes, /) -> int: ...


class VolumeProvider(Protocol):
    def open_volume(self, index: int, expected_name: str, /) -> bytes | None: ...


def open_bytes(
    data: bytes,
    *,
    limits: Limits | None = ...,
    password: str | None = ...,
    cancellation: CancellationToken | None = ...,
    max_work_units: int = ...,
) -> Archive: ...


def open_path(
    path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
    *,
    limits: Limits | None = ...,
    password: str | None = ...,
    cancellation: CancellationToken | None = ...,
    max_work_units: int = ...,
) -> Archive: ...


def open_volumes(
    provider: VolumeProvider | Callable[[int, str], bytes | None],
    first_volume_name: str,
    *,
    limits: Limits | None = ...,
    password: str | None = ...,
    cancellation: CancellationToken | None = ...,
    max_work_units: int = ...,
) -> Archive: ...
