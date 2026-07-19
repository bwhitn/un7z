#![forbid(unsafe_code)]
//! Opens explicitly supplied sequential volume bytes through the public provider.

use std::{env, error::Error as StdError, fs, io};

use un7z::{Archive, CancellationToken, Limits, MemoryVolumeProvider, WorkBudget};

fn main() -> Result<(), Box<dyn StdError>> {
    let mut paths = env::args_os();
    let _program = paths.next();
    let first_path = paths.next().ok_or_else(|| {
        io::Error::new(
            io::ErrorKind::InvalidInput,
            "usage: open_volumes ARCHIVE.001 [ARCHIVE.002 ...]",
        )
    })?;
    let mut volumes = vec![fs::read(&first_path)?];
    for path in paths {
        volumes.push(fs::read(path)?);
    }
    let first_name = first_path.to_string_lossy();
    let mut provider = MemoryVolumeProvider::new(volumes);
    let cancellation = CancellationToken::new();
    let mut budget = WorkBudget::unlimited();
    let archive = Archive::open_volumes(
        &mut provider,
        &first_name,
        Limits::default(),
        &cancellation,
        &mut budget,
    )?;
    println!("{} entries", archive.entries().len());
    Ok(())
}
