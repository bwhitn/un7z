#![forbid(unsafe_code)]
//! Extracts one numeric member to an explicit caller-selected destination.

use std::{env, error::Error as StdError, fs::File, io, path::Path};

use un7z::{Archive, CancellationToken, Limits, WorkBudget};

fn invalid_input(message: &'static str) -> io::Error {
    io::Error::new(io::ErrorKind::InvalidInput, message)
}

fn main() -> Result<(), Box<dyn StdError>> {
    let mut arguments = env::args_os();
    let _program = arguments.next();
    let archive_path = arguments
        .next()
        .ok_or_else(|| invalid_input("usage: extract_entry_to ARCHIVE INDEX DESTINATION"))?;
    let index = arguments
        .next()
        .ok_or_else(|| invalid_input("member index is missing"))?
        .into_string()
        .map_err(|_| invalid_input("member index is not valid UTF-8"))?
        .parse::<u64>()?;
    let destination = arguments
        .next()
        .ok_or_else(|| invalid_input("destination is missing"))?;

    let cancellation = CancellationToken::new();
    let mut budget = WorkBudget::unlimited();
    let archive = Archive::open_path(
        Path::new(&archive_path),
        Limits::default(),
        &cancellation,
        &mut budget,
    )?;
    let mut output = File::create(destination)?;
    let _verified_bytes =
        archive.extract_entry_to(index, &mut output, &cancellation, &mut budget)?;
    Ok(())
}
