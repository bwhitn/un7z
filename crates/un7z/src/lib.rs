#![forbid(unsafe_code)]
#![deny(missing_docs)]
#![deny(
    clippy::expect_used,
    clippy::indexing_slicing,
    clippy::panic,
    clippy::unwrap_used
)]
//! A security-focused, unpack-only 7z reader.
//!
//! The stable surface owns archive input, exposes concrete metadata, and sends
//! decoded bytes only to caller-selected memory or output sinks. It never
//! creates, edits, or automatically extracts archive paths. See [`Archive`]
//! for opening and listing, [`MemberReader`] for bounded reads with explicit
//! checksum finalization, and [`Limits`] for attacker-controlled resource
//! bounds.
//!
//! Low-level parser and coder-graph types are intentionally not part of this
//! API. The hidden `unstable-internals` feature exists only for this
//! repository's structural regression tests and fuzz harnesses and carries no
//! compatibility guarantee.
//!
//! # Opening and listing
//!
//! ```no_run
//! use std::path::Path;
//! use un7z::{Archive, CancellationToken, Limits, WorkBudget};
//!
//! # fn main() -> un7z::Result<()> {
//! let cancellation = CancellationToken::new();
//! let mut budget = WorkBudget::bounded(100_000_000);
//! let archive = Archive::open_path(
//!     Path::new("archive.7z"),
//!     Limits::default(),
//!     &cancellation,
//!     &mut budget,
//! )?;
//! for entry in archive.entries() {
//!     println!("{:?} {:?}", entry.kind(), entry.name_lossy());
//! }
//! # Ok(())
//! # }
//! ```
//!
//! A raw name is metadata, not an extraction destination. Validate it with
//! [`validate_safe_utf16_path`] before applying a separately defined
//! filesystem policy. Even after the last [`MemberReader::read_chunk`] returns
//! zero, call [`MemberReader::finish`] before treating streamed bytes as
//! verified.

mod archive;
mod bounded;
mod cancel;
mod checksum;
mod decode;
mod error;
mod execute;
mod graph;
mod limits;
mod metadata;
mod model;
mod parse_util;
mod parser;
mod password;
mod path;
mod raw;
mod validate;
mod volume;

pub use archive::{Archive, ArchiveResources, EntrySink, MemberReader};
pub use cancel::{CancellationToken, WorkBudget};
pub use error::{ChecksumScope, Error, ErrorKind, LimitKind};
pub use limits::{Limits, LimitsBuilder};
#[cfg(feature = "unstable-internals")]
#[doc(hidden)]
pub use model::{
    ArchiveHeader, ArchiveVersion, BindPair, Coder, ExternalProperty, FileStream, FilesInfo,
    Folder, HeaderEnvelope, NextHeaderKind, PackStream, ParsedArchive, ParsedNextHeader,
    PendingExternalFolderHeader, StoredProperty, StreamsInfo, Substream,
};
pub use model::{EntryKind, FileEntry};
#[cfg(feature = "unstable-internals")]
#[doc(hidden)]
pub use parser::{parse_archive, parse_archive_header};
pub use path::{UnsafePathReason, validate_safe_path, validate_safe_utf16_path};
pub use volume::{MemoryVolumeProvider, PathVolumeProvider, Volume, VolumeProvider, VolumeRequest};

/// The result type returned by the core library.
pub type Result<T> = std::result::Result<T, Error>;

/// A machine-readable statement of the current implementation boundary.
pub const IMPLEMENTATION_STATUS: &str = "phase-6-stable-rust-api-pre-alpha";
