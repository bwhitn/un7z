#![forbid(unsafe_code)]
//! Lists exact archive-order metadata without using names as filesystem paths.

use std::{env, error::Error as StdError, io, path::Path};

use un7z::{Archive, CancellationToken, Limits, WorkBudget};

fn main() -> Result<(), Box<dyn StdError>> {
    let path = env::args_os()
        .nth(1)
        .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidInput, "usage: list ARCHIVE"))?;
    let cancellation = CancellationToken::new();
    let mut budget = WorkBudget::unlimited();
    let archive = Archive::open_path(
        Path::new(&path),
        Limits::default(),
        &cancellation,
        &mut budget,
    )?;

    for (index, entry) in archive.entries().iter().enumerate() {
        let name = entry
            .name_lossy()
            .unwrap_or_else(|| String::from("<unnamed>"));
        println!(
            "{index}\t{:?}\t{:?}\t{:?}\t{name}",
            entry.kind(),
            entry.size(),
            entry.crc32()
        );
    }
    Ok(())
}
