#![forbid(unsafe_code)]
//! Corpus-free differential checks using a locally installed `7zz` test oracle.

use std::{
    error::Error as StdError,
    fs,
    path::{Path, PathBuf},
    process::Command,
    sync::atomic::{AtomicU64, Ordering},
};

use sha2::{Digest, Sha256};
use un7z::{Archive, CancellationToken, ErrorKind, Limits, WorkBudget};

const PASSWORD: &str = "generated-oracle-password";

struct OracleEntry {
    path: String,
    size: u64,
    crc: Option<u32>,
    method: Option<String>,
}

fn temporary_directory(label: &str) -> Result<PathBuf, Box<dyn StdError>> {
    static COUNTER: AtomicU64 = AtomicU64::new(0);
    let ordinal = COUNTER.fetch_add(1, Ordering::Relaxed);
    let directory = std::env::temp_dir().join(format!(
        "un7z-generated-oracle-{label}-{}-{ordinal}",
        std::process::id()
    ));
    fs::create_dir(&directory)?;
    Ok(directory)
}

fn command_failure(label: &str, output: &std::process::Output) -> String {
    format!(
        "{label} failed: stdout={} stderr={}",
        String::from_utf8_lossy(&output.stdout),
        String::from_utf8_lossy(&output.stderr)
    )
}

fn oracle_metadata(
    path: &Path,
    password: Option<&str>,
) -> Result<Vec<OracleEntry>, Box<dyn StdError>> {
    let mut command = Command::new("7zz");
    command.args(["l", "-slt"]);
    if let Some(password) = password {
        command.arg(format!("-p{password}"));
    }
    let output = command.arg(path).env("LC_ALL", "C").output()?;
    if !output.status.success() {
        return Err(command_failure("7zz metadata listing", &output).into());
    }
    let listing = String::from_utf8(output.stdout)?.replace("\r\n", "\n");
    let (_, records) = listing
        .split_once("\n----------\n")
        .ok_or_else(|| String::from("7zz listing has no entry section"))?;
    let mut entries = Vec::new();
    for record in records.split("\n\n") {
        let mut member_path = None;
        let mut size = None;
        let mut crc = None;
        let mut method = None;
        for line in record.lines() {
            if let Some(value) = line.strip_prefix("Path = ") {
                member_path = Some(value.to_owned());
            } else if let Some(value) = line.strip_prefix("Size = ") {
                size = Some(value.parse::<u64>()?);
            } else if let Some(value) = line.strip_prefix("CRC = ") {
                crc = Some(u32::from_str_radix(value, 16)?);
            } else if let Some(value) = line.strip_prefix("Method = ") {
                method = Some(value.to_owned());
            }
        }
        if let Some(path) = member_path {
            entries.push(OracleEntry {
                path,
                size: size.ok_or_else(|| String::from("7zz entry has no size"))?,
                crc,
                method,
            });
        }
    }
    Ok(entries)
}

fn oracle_member(
    path: &Path,
    name: &str,
    password: Option<&str>,
) -> Result<Vec<u8>, Box<dyn StdError>> {
    let mut command = Command::new("7zz");
    command.args(["x", "-so", "-y"]);
    if let Some(password) = password {
        command.arg(format!("-p{password}"));
    }
    let output = command.arg(path).arg("--").arg(name).output()?;
    if !output.status.success() {
        return Err(command_failure("7zz member extraction", &output).into());
    }
    Ok(output.stdout)
}

fn open_archive(path: &Path, password: Option<&str>) -> un7z::Result<Archive> {
    let cancellation = CancellationToken::new();
    let mut budget = WorkBudget::unlimited();
    match password {
        Some(password) => Archive::open_path_with_password(
            path,
            Limits::default(),
            password,
            &cancellation,
            &mut budget,
        ),
        None => Archive::open_path(path, Limits::default(), &cancellation, &mut budget),
    }
}

fn compare_to_oracle(
    path: &Path,
    password: Option<&str>,
    expected_method: &str,
    expected_bytes: &[u8],
) -> Result<(), Box<dyn StdError>> {
    let archive = open_archive(path, password)?;
    let oracle = oracle_metadata(path, password)?;
    if archive.entries().len() != oracle.len() || oracle.len() != 1 {
        return Err(String::from("generated archive does not contain exactly one entry").into());
    }
    let expected = oracle
        .first()
        .ok_or_else(|| String::from("7zz generated-entry metadata is missing"))?;
    let method = expected
        .method
        .as_deref()
        .ok_or_else(|| String::from("7zz generated-entry method is missing"))?;
    if !method.split_whitespace().any(|item| {
        item == expected_method
            || item
                .strip_prefix(expected_method)
                .is_some_and(|suffix| suffix.starts_with(':'))
    }) {
        return Err(format!(
            "7zz did not use requested method {expected_method}: reported {method}"
        )
        .into());
    }

    let entry = archive
        .entries()
        .first()
        .ok_or_else(|| String::from("Rust generated-entry metadata is missing"))?;
    let raw_name = entry
        .raw_name()
        .ok_or_else(|| String::from("generated archive member has no raw name"))?;
    let name = String::from_utf16_lossy(raw_name);
    if name != expected.path {
        return Err(String::from("generated member name differs from 7zz").into());
    }
    if entry.size() != Some(expected.size) {
        return Err(String::from("generated member size differs from 7zz").into());
    }
    if entry.crc32() != expected.crc {
        return Err(String::from("generated member CRC differs from 7zz").into());
    }

    let cancellation = CancellationToken::new();
    let mut budget = WorkBudget::unlimited();
    let rust = archive.extract_entry(0, &cancellation, &mut budget)?;
    let oracle = oracle_member(path, &name, password)?;
    if rust.len() != oracle.len()
        || Sha256::digest(&rust) != Sha256::digest(&oracle)
        || rust != oracle
        || rust != expected_bytes
    {
        return Err(
            String::from("generated member bytes/SHA-256 differ from 7zz or source").into(),
        );
    }
    let mut budget = WorkBudget::unlimited();
    archive.verify(&cancellation, &mut budget)?;
    Ok(())
}

fn repeated_pattern(pattern: &[u8], count: usize) -> Result<Vec<u8>, Box<dyn StdError>> {
    let capacity = pattern
        .len()
        .checked_mul(count)
        .ok_or_else(|| String::from("generated payload size overflows"))?;
    let mut bytes = Vec::new();
    bytes.try_reserve_exact(capacity)?;
    for _ in 0..count {
        bytes.extend_from_slice(pattern);
    }
    Ok(bytes)
}

fn deterministic_bytes(length: usize) -> Result<Vec<u8>, Box<dyn StdError>> {
    let mut bytes = Vec::new();
    bytes.try_reserve_exact(length)?;
    let mut state = 0x9e37_79b9_u32;
    for _ in 0..length {
        state ^= state.wrapping_shl(13);
        state ^= state >> 17;
        state ^= state.wrapping_shl(5);
        bytes.push(u8::try_from(state >> 24)?);
    }
    Ok(bytes)
}

fn method_payload(name: &str) -> Result<Vec<u8>, Box<dyn StdError>> {
    match name {
        "bcj" | "bcj2" => repeated_pattern(
            &[
                0xe8, 0, 0, 0, 0, 0x90, 0xe9, 0, 0, 0, 0, 0x0f, 0x85, 0, 0, 0, 0,
            ],
            2048,
        ),
        "ppc" => repeated_pattern(&[0x48, 0, 0, 1, 0x60, 0, 0, 0], 4096),
        "arm" => repeated_pattern(&[0, 0, 0, 0xeb, 0, 0, 0, 0xea], 4096),
        "arm64" => repeated_pattern(&[0, 0, 0, 0x94, 0, 0, 0, 0x90], 4096),
        "sparc" => repeated_pattern(&[0x40, 0, 0, 0, 0x01, 0, 0, 0], 4096),
        "ppmd" => repeated_pattern(
            b"PPMd context modelling fixture: alpha beta gamma delta 0123456789\n",
            4096,
        ),
        _ => {
            let mut bytes = deterministic_bytes(32 * 1024)?;
            bytes.extend_from_slice(&repeated_pattern(
                b"un7z generated differential fixture\n",
                2048,
            )?);
            Ok(bytes)
        }
    }
}

fn create_archive(
    directory: &Path,
    name: &str,
    switches: &[&str],
    password: Option<&str>,
    payload: &[u8],
) -> Result<PathBuf, Box<dyn StdError>> {
    let source_name = format!("{name}.bin");
    fs::write(directory.join(&source_name), payload)?;
    let archive = directory.join(format!("{name}.7z"));
    let mut command = Command::new("7zz");
    command
        .current_dir(directory)
        .args(["a", "-y", "-t7z", "-mhc=off"])
        .args(switches);
    if let Some(password) = password {
        command.arg(format!("-p{password}"));
    }
    let output = command.arg(&archive).arg(&source_name).output()?;
    if !output.status.success() {
        return Err(command_failure("7zz fixture creation", &output).into());
    }
    Ok(archive)
}

fn assert_packed_data_was_transformed(
    path: &Path,
    payload: &[u8],
) -> Result<(), Box<dyn StdError>> {
    let archive = fs::read(path)?;
    let comparison_end = 32_usize
        .checked_add(payload.len())
        .ok_or_else(|| String::from("generated packed comparison range overflows"))?
        .min(archive.len());
    let packed_prefix = archive
        .get(32..comparison_end)
        .ok_or_else(|| String::from("generated packed comparison range is missing"))?;
    let source_prefix = payload
        .get(..packed_prefix.len())
        .ok_or_else(|| String::from("generated source comparison range is missing"))?;
    if packed_prefix == source_prefix {
        return Err(String::from("7zz filter did not transform the positive fixture").into());
    }
    Ok(())
}

fn assert_corruption_fails(path: &Path, password: Option<&str>) -> Result<(), Box<dyn StdError>> {
    let mut bytes = fs::read(path)?;
    let next_offset = <[u8; 8]>::try_from(
        bytes
            .get(12..20)
            .ok_or_else(|| String::from("generated start header is truncated"))?,
    )?;
    let packed_length = usize::try_from(u64::from_le_bytes(next_offset))?;
    if packed_length == 0 {
        return Err(String::from("generated archive has no packed region").into());
    }
    let mutation_index = 32_usize
        .checked_add(packed_length / 2)
        .ok_or_else(|| String::from("generated packed-data index overflows"))?;
    let byte = bytes
        .get_mut(mutation_index)
        .ok_or_else(|| String::from("generated packed-data byte is missing"))?;
    *byte ^= 0x5a;

    let cancellation = CancellationToken::new();
    let mut budget = WorkBudget::unlimited();
    let opened = match password {
        Some(password) => Archive::open_bytes_with_password(
            bytes,
            Limits::default(),
            password,
            &cancellation,
            &mut budget,
        ),
        None => Archive::open_bytes(bytes, Limits::default(), &cancellation, &mut budget),
    };
    let failed = match opened {
        Ok(archive) => {
            let mut budget = WorkBudget::unlimited();
            archive.verify(&cancellation, &mut budget).is_err()
        }
        Err(_) => true,
    };
    if !failed {
        return Err(String::from("corrupted generated archive verified successfully").into());
    }
    Ok(())
}

#[test]
#[ignore = "requires stock 7zz 26.02"]
fn generated_core_and_go_parity_methods_match_7zz() -> Result<(), Box<dyn StdError>> {
    let directory = temporary_directory("methods")?;
    let result = (|| -> Result<(), Box<dyn StdError>> {
        for (name, method, switches, is_filter) in [
            ("copy", "Copy", &["-m0=Copy"][..], false),
            ("lzma", "LZMA", &["-m0=LZMA:d=1m"][..], false),
            ("lzma2", "LZMA2", &["-m0=LZMA2:d=1m"][..], false),
            ("delta", "Delta", &["-m0=Copy", "-m1=Delta:1"][..], true),
            ("bcj", "BCJ", &["-m0=Copy", "-m1=BCJ"][..], true),
            ("bcj2", "BCJ2", &["-m0=BCJ2"][..], true),
            ("ppc", "PPC", &["-m0=Copy", "-m1=PPC"][..], true),
            ("arm", "ARM", &["-m0=Copy", "-m1=ARM"][..], true),
            ("arm64", "ARM64", &["-m0=Copy", "-m1=ARM64"][..], true),
            ("sparc", "SPARC", &["-m0=Copy", "-m1=SPARC"][..], true),
            ("deflate", "Deflate", &["-m0=Deflate"][..], false),
            ("bzip2", "BZip2", &["-m0=BZip2"][..], false),
            ("ppmd", "PPMD", &["-m0=PPMd:o=6:mem=1m"][..], false),
        ] {
            let payload = method_payload(name)?;
            let archive = create_archive(&directory, name, switches, None, &payload)?;
            if is_filter {
                assert_packed_data_was_transformed(&archive, &payload)
                    .map_err(|error| format!("{name} transform check failed: {error}"))?;
            }
            compare_to_oracle(&archive, None, method, &payload)
                .map_err(|error| format!("{name} differential failed: {error}"))?;
            assert_corruption_fails(&archive, None)
                .map_err(|error| format!("{name} corruption check failed: {error}"))?;
        }
        Ok(())
    })();
    let cleanup = fs::remove_dir_all(&directory);
    result?;
    cleanup?;
    Ok(())
}

#[test]
#[ignore = "requires stock 7zz 26.02"]
fn generated_encrypted_header_and_data_match_7zz() -> Result<(), Box<dyn StdError>> {
    let directory = temporary_directory("aes")?;
    let result = (|| -> Result<(), Box<dyn StdError>> {
        let payload = method_payload("copy")?;
        let encrypted_header = create_archive(
            &directory,
            "encrypted-header",
            &["-m0=Copy", "-mhe=on"],
            Some(PASSWORD),
            &payload,
        )?;
        if open_archive(&encrypted_header, None)
            .as_ref()
            .err()
            .map(un7z::Error::kind)
            != Some(ErrorKind::PasswordRequired)
        {
            return Err(String::from("encrypted header did not require a password").into());
        }
        if open_archive(&encrypted_header, Some("wrong-password"))
            .as_ref()
            .err()
            .map(un7z::Error::kind)
            != Some(ErrorKind::WrongPasswordOrCorrupt)
        {
            return Err(String::from("wrong header password was not typed").into());
        }
        compare_to_oracle(&encrypted_header, Some(PASSWORD), "7zAES", &payload)?;
        assert_corruption_fails(&encrypted_header, Some(PASSWORD))?;

        let encrypted_data = create_archive(
            &directory,
            "encrypted-data",
            &["-m0=Copy", "-mhe=off"],
            Some(PASSWORD),
            &payload,
        )?;
        let wrong = open_archive(&encrypted_data, Some("wrong-password"))?;
        let cancellation = CancellationToken::new();
        let mut budget = WorkBudget::unlimited();
        if wrong
            .verify(&cancellation, &mut budget)
            .as_ref()
            .err()
            .map(un7z::Error::kind)
            != Some(ErrorKind::WrongPasswordOrCorrupt)
        {
            return Err(String::from("wrong data password was not typed").into());
        }
        compare_to_oracle(&encrypted_data, Some(PASSWORD), "7zAES", &payload)?;
        assert_corruption_fails(&encrypted_data, Some(PASSWORD))?;
        Ok(())
    })();
    let cleanup = fs::remove_dir_all(&directory);
    result?;
    cleanup?;
    Ok(())
}

#[test]
#[ignore = "requires stock 7zz 26.02"]
fn generated_sfx_prefix_matches_7zz() -> Result<(), Box<dyn StdError>> {
    let directory = temporary_directory("sfx")?;
    let result = (|| -> Result<(), Box<dyn StdError>> {
        let payload = method_payload("copy")?;
        let archive = create_archive(&directory, "plain-for-sfx", &["-m0=Copy"], None, &payload)?;
        let archive_bytes = fs::read(&archive)?;
        let mut sfx = repeated_pattern(b"MZ synthetic un7z test-only SFX prefix\n", 128)?;
        sfx.try_reserve(archive_bytes.len())?;
        sfx.extend_from_slice(&archive_bytes);
        let sfx_path = directory.join("synthetic-sfx.exe");
        fs::write(&sfx_path, sfx)?;
        compare_to_oracle(&sfx_path, None, "Copy", &payload)
    })();
    let cleanup = fs::remove_dir_all(&directory);
    result?;
    cleanup?;
    Ok(())
}
