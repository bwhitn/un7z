"""Security-focused, unpack-only 7z archive access."""

from ._native import (
    Archive,
    ArchiveIoError,
    ArchiveResources,
    CancelledError,
    CancellationToken,
    ChecksumError,
    Entry,
    FormatError,
    InternalError,
    LimitExceededError,
    Limits,
    MissingVolumeError,
    PasswordRequiredError,
    Un7zError,
    UnsupportedFeatureError,
    UnsupportedMethodError,
    WrongPasswordOrCorruptError,
    open_bytes,
    open_path,
    open_volumes,
)

__version__ = "0.1.0"

__all__ = [
    "Archive",
    "ArchiveIoError",
    "ArchiveResources",
    "CancelledError",
    "CancellationToken",
    "ChecksumError",
    "Entry",
    "FormatError",
    "InternalError",
    "LimitExceededError",
    "Limits",
    "MissingVolumeError",
    "PasswordRequiredError",
    "Un7zError",
    "UnsupportedFeatureError",
    "UnsupportedMethodError",
    "WrongPasswordOrCorruptError",
    "open_bytes",
    "open_path",
    "open_volumes",
]
