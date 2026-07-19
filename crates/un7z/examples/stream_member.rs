#![forbid(unsafe_code)]
//! Streams a numeric member to stdout and explicitly finalizes its CRC.

use std::{
    env,
    error::Error as StdError,
    io::{self, Write},
    path::Path,
};

use un7z::{Archive, CancellationToken, Limits, WorkBudget};

fn invalid_input(message: &'static str) -> io::Error {
    io::Error::new(io::ErrorKind::InvalidInput, message)
}

fn main() -> Result<(), Box<dyn StdError>> {
    let mut arguments = env::args_os();
    let _program = arguments.next();
    let path = arguments
        .next()
        .ok_or_else(|| invalid_input("usage: stream_member ARCHIVE INDEX"))?;
    let index = arguments
        .next()
        .ok_or_else(|| invalid_input("member index is missing"))?
        .into_string()
        .map_err(|_| invalid_input("member index is not valid UTF-8"))?
        .parse::<u64>()?;

    let cancellation = CancellationToken::new();
    let mut budget = WorkBudget::unlimited();
    let archive = Archive::open_path(
        Path::new(&path),
        Limits::default(),
        &cancellation,
        &mut budget,
    )?;
    let mut member = archive.open_member(index, &cancellation, &mut budget)?;
    let stdout = io::stdout();
    let mut output = stdout.lock();
    let mut buffer = [0_u8; 16 * 1024];
    loop {
        let count = member.read_chunk(&mut buffer)?;
        if count == 0 {
            break;
        }
        let bytes = buffer
            .get(..count)
            .ok_or_else(|| io::Error::other("reader returned an invalid chunk length"))?;
        output.write_all(bytes)?;
    }
    member.finish()?;
    output.flush()?;
    Ok(())
}
