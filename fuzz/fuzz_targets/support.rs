#![forbid(unsafe_code)]
// Each fuzz binary selects a different subset of these shared constructors.
#![allow(dead_code)]

const SIGNATURE: &[u8] = b"7z\xbc\xaf\x27\x1c";

fn crc32(bytes: &[u8]) -> u32 {
    let mut crc = u32::MAX;
    for byte in bytes {
        crc ^= u32::from(*byte);
        for _ in 0..8 {
            crc = if crc & 1 == 0 {
                crc >> 1
            } else {
                (crc >> 1) ^ 0xedb8_8320
            };
        }
    }
    !crc
}

pub(crate) fn wrap_next_header(next_header: &[u8]) -> Option<Vec<u8>> {
    let next_size = u64::try_from(next_header.len()).ok()?;
    let next_crc = crc32(next_header);
    let mut start_fields = Vec::new();
    start_fields.try_reserve_exact(20).ok()?;
    start_fields.extend_from_slice(&0_u64.to_le_bytes());
    start_fields.extend_from_slice(&next_size.to_le_bytes());
    start_fields.extend_from_slice(&next_crc.to_le_bytes());
    let archive_size = 32_usize.checked_add(next_header.len())?;
    let mut archive = Vec::new();
    archive.try_reserve_exact(archive_size).ok()?;
    archive.extend_from_slice(SIGNATURE);
    archive.extend_from_slice(&[0, 4]);
    archive.extend_from_slice(&crc32(&start_fields).to_le_bytes());
    archive.extend_from_slice(&start_fields);
    archive.extend_from_slice(next_header);
    Some(archive)
}

fn push_uint(bytes: &mut Vec<u8>, value: u64) -> Option<()> {
    for additional in 0_u32..8 {
        let value_bits = 7_u32.checked_mul(additional.checked_add(1)?)?;
        let threshold = 1_u64.checked_shl(value_bits)?;
        if value >= threshold {
            continue;
        }
        let prefix = if additional == 0 {
            0
        } else {
            u8::MAX.checked_shl(8_u32.checked_sub(additional)?)?
        };
        let high = u8::try_from(value >> 8_u32.checked_mul(additional)?).ok()?;
        bytes.push(prefix | high);
        let additional = usize::try_from(additional).ok()?;
        bytes.extend(value.to_le_bytes().iter().take(additional));
        return Some(());
    }
    bytes.push(u8::MAX);
    bytes.extend_from_slice(&value.to_le_bytes());
    Some(())
}

fn wrap_payload_and_header(payload: &[u8], next_header: &[u8]) -> Option<Vec<u8>> {
    let next_offset = u64::try_from(payload.len()).ok()?;
    let next_size = u64::try_from(next_header.len()).ok()?;
    let next_crc = crc32(next_header);
    let mut start_fields = Vec::new();
    start_fields.try_reserve_exact(20).ok()?;
    start_fields.extend_from_slice(&next_offset.to_le_bytes());
    start_fields.extend_from_slice(&next_size.to_le_bytes());
    start_fields.extend_from_slice(&next_crc.to_le_bytes());
    let capacity = 32_usize
        .checked_add(payload.len())?
        .checked_add(next_header.len())?;
    let mut archive = Vec::new();
    archive.try_reserve_exact(capacity).ok()?;
    archive.extend_from_slice(SIGNATURE);
    archive.extend_from_slice(&[0, 4]);
    archive.extend_from_slice(&crc32(&start_fields).to_le_bytes());
    archive.extend_from_slice(&start_fields);
    archive.extend_from_slice(payload);
    archive.extend_from_slice(next_header);
    Some(archive)
}

pub(crate) fn wrap_one_coder_archive(
    payload: &[u8],
    method: &[u8],
    properties: Option<&[u8]>,
    unpack_size: u64,
    folder_crc: Option<u32>,
) -> Option<Vec<u8>> {
    let mut streams = Vec::new();
    streams.try_reserve_exact(96).ok()?;
    streams.push(0x06);
    push_uint(&mut streams, 0)?;
    push_uint(&mut streams, 1)?;
    streams.push(0x09);
    push_uint(&mut streams, u64::try_from(payload.len()).ok()?)?;
    streams.push(0x00);

    streams.extend_from_slice(&[0x07, 0x0b]);
    push_uint(&mut streams, 1)?;
    streams.push(0);
    push_uint(&mut streams, 1)?;
    let mut flags = u8::try_from(method.len()).ok()?;
    if properties.is_some() {
        flags |= 0x20;
    }
    streams.push(flags);
    streams.extend_from_slice(method);
    if let Some(properties) = properties {
        push_uint(&mut streams, u64::try_from(properties.len()).ok()?)?;
        streams.extend_from_slice(properties);
    }
    streams.push(0x0c);
    push_uint(&mut streams, unpack_size)?;
    if let Some(crc) = folder_crc {
        streams.extend_from_slice(&[0x0a, 1]);
        streams.extend_from_slice(&crc.to_le_bytes());
    }
    streams.extend_from_slice(&[0x00, 0x00]);

    let mut header = Vec::new();
    header
        .try_reserve_exact(streams.len().checked_add(8)?)
        .ok()?;
    header.extend_from_slice(&[0x01, 0x04]);
    header.extend_from_slice(&streams);
    header.extend_from_slice(&[0x05, 0x01, 0x00, 0x00]);
    wrap_payload_and_header(payload, &header)
}

pub(crate) fn wrap_copy_archive(payload: &[u8]) -> Option<Vec<u8>> {
    wrap_one_coder_archive(
        payload,
        &[0],
        None,
        u64::try_from(payload.len()).ok()?,
        Some(crc32(payload)),
    )
}
