#![forbid(unsafe_code)]
//! Command-line listing, stdout extraction, and verification frontend.

use std::{
    env,
    ffi::OsStr,
    io::{self, Write},
    path::Path,
    process::ExitCode,
};

use un7z::{Archive, CancellationToken, EntryKind, Limits, WorkBudget};

fn usage(mut output: impl Write) -> io::Result<()> {
    writeln!(
        output,
        "un7z {}\n\nUSAGE:\n    un7z list ARCHIVE\n    un7z cat ARCHIVE MEMBER_INDEX\n    un7z verify ARCHIVE\n    un7z status\n    un7z --help\n    un7z --version\n\n`cat` writes one member to stdout. Automatic filesystem extraction is intentionally unavailable.",
        env!("CARGO_PKG_VERSION")
    )
}

fn invalid_input(detail: &'static str) -> io::Error {
    io::Error::new(io::ErrorKind::InvalidInput, detail)
}

fn open_archive(path: &OsStr) -> Result<Archive, Box<dyn std::error::Error>> {
    let cancellation = CancellationToken::new();
    let mut budget = WorkBudget::unlimited();
    Ok(Archive::open_path(
        Path::new(path),
        Limits::default(),
        &cancellation,
        &mut budget,
    )?)
}

fn list(path: &OsStr) -> Result<(), Box<dyn std::error::Error>> {
    let archive = open_archive(path)?;
    let stdout = io::stdout();
    let mut output = stdout.lock();
    writeln!(output, "INDEX\tTYPE\tSIZE\tCRC32\tATTRS\tMODE\tSAFE\tNAME")?;
    for (index, entry) in archive.entries().iter().enumerate() {
        let kind = match entry.kind() {
            EntryKind::File => "file",
            EntryKind::Directory => "directory",
            EntryKind::SymbolicLink => "symlink",
            EntryKind::AntiItem => "anti",
            _ => "unknown",
        };
        let size = entry
            .size()
            .map_or_else(|| String::from("-"), |value| value.to_string());
        let crc = entry
            .crc32()
            .map_or_else(|| String::from("-"), |value| format!("{value:08x}"));
        let name = entry
            .raw_name()
            .map_or_else(|| String::from("<unnamed>"), String::from_utf16_lossy);
        let attributes = entry
            .windows_attributes()
            .map_or_else(|| String::from("-"), |value| format!("{value:08x}"));
        let mode = entry
            .unix_mode()
            .map_or_else(|| String::from("-"), |value| format!("{value:o}"));
        let safe = entry
            .raw_name()
            .is_some_and(|raw| un7z::validate_safe_utf16_path(raw).is_ok());
        writeln!(
            output,
            "{index}\t{kind}\t{size}\t{crc}\t{attributes}\t{mode}\t{safe}\t{name}"
        )?;
    }
    Ok(())
}

fn cat(path: &OsStr, member_index: &OsStr) -> Result<(), Box<dyn std::error::Error>> {
    let member_index = member_index
        .to_str()
        .ok_or_else(|| invalid_input("member index is not valid UTF-8"))?
        .parse::<u64>()?;
    let archive = open_archive(path)?;
    let cancellation = CancellationToken::new();
    let mut budget = WorkBudget::unlimited();
    let stdout = io::stdout();
    let mut output = stdout.lock();
    let _ = archive.extract_entry_to(member_index, &mut output, &cancellation, &mut budget)?;
    output.flush()?;
    Ok(())
}

fn verify(path: &OsStr) -> Result<(), Box<dyn std::error::Error>> {
    let archive = open_archive(path)?;
    let cancellation = CancellationToken::new();
    let mut budget = WorkBudget::unlimited();
    archive.verify(&cancellation, &mut budget)?;
    writeln!(io::stdout().lock(), "ok")?;
    Ok(())
}

fn run() -> Result<(), Box<dyn std::error::Error>> {
    let mut arguments = env::args_os();
    let _program = arguments.next();
    let Some(command) = arguments.next() else {
        usage(io::stdout().lock())?;
        return Ok(());
    };
    match command.to_str() {
        Some("-h" | "--help") => usage(io::stdout().lock())?,
        Some("-V" | "--version") => {
            writeln!(io::stdout().lock(), "un7z {}", env!("CARGO_PKG_VERSION"))?;
        }
        Some("status") => writeln!(io::stdout().lock(), "{}", un7z::IMPLEMENTATION_STATUS)?,
        Some("list") => {
            let path = arguments
                .next()
                .ok_or_else(|| invalid_input("list requires ARCHIVE"))?;
            list(&path)?;
        }
        Some("cat") => {
            let path = arguments
                .next()
                .ok_or_else(|| invalid_input("cat requires ARCHIVE"))?;
            let index = arguments
                .next()
                .ok_or_else(|| invalid_input("cat requires MEMBER_INDEX"))?;
            cat(&path, &index)?;
        }
        Some("verify") => {
            let path = arguments
                .next()
                .ok_or_else(|| invalid_input("verify requires ARCHIVE"))?;
            verify(&path)?;
        }
        Some(_) | None => return Err(invalid_input("unknown command; use --help").into()),
    }
    if arguments.next().is_some() {
        return Err(invalid_input("unexpected trailing argument").into());
    }
    Ok(())
}

fn main() -> ExitCode {
    match run() {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            let _ = writeln!(io::stderr().lock(), "un7z: {error}");
            ExitCode::from(2)
        }
    }
}
