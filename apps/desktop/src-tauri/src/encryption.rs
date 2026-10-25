use std::fs::File;
use std::io::{Read, Seek, SeekFrom, Write};
use std::path::Path;

use aes_gcm::aead::{Aead, KeyInit};
use aes_gcm::{Aes256Gcm, Key, Nonce};
use hkdf::Hkdf;
use sha2::Sha256;

pub const DEFAULT_CHUNK_SIZE: usize = 256 * 1024; // 256 KB
pub const HEADER_MAGIC: &[u8; 8] = b"LPENC01\0";
pub const HEADER_SIZE: usize = 32;
pub const NONCE_SIZE: usize = 12;
pub const TAG_SIZE: usize = 16;
pub const CHUNK_OVERHEAD: usize = NONCE_SIZE + TAG_SIZE; // 28 bytes

pub fn derive_file_key(
    device_secret: &[u8; 32],
    lecture_id: &str,
    file_path: &str,
) -> Result<[u8; 32], String> {
    let salt = b"lecture-platform-bundle-encryption-v1";
    let hk = Hkdf::<Sha256>::new(Some(salt), device_secret);
    let mut okm = [0u8; 32];
    let info = format!("{}:{}", lecture_id, file_path);
    hk.expand(info.as_bytes(), &mut okm)
        .map_err(|e| format!("HKDF key expansion failed: {:?}", e))?;
    Ok(okm)
}

fn make_nonce(chunk_idx: u32) -> [u8; NONCE_SIZE] {
    let mut nonce = [0u8; NONCE_SIZE];
    nonce[0..8].copy_from_slice(&(chunk_idx as u64).to_be_bytes());
    nonce
}

pub fn encrypt_file(
    src_path: &Path,
    dst_path: &Path,
    key: &[u8; 32],
    chunk_size: usize,
) -> Result<(), String> {
    if let Some(parent) = dst_path.parent() {
        std::fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    }

    let mut src = File::open(src_path).map_err(|e| format!("Failed to open src: {}", e))?;
    let file_len = src
        .metadata()
        .map_err(|e| format!("Failed to get src meta: {}", e))?
        .len();

    let num_chunks = if file_len == 0 {
        1
    } else {
        ((file_len + (chunk_size as u64) - 1) / (chunk_size as u64)) as u32
    };

    let mut dst = File::create(dst_path).map_err(|e| format!("Failed to create dst: {}", e))?;

    // 32-byte header
    let mut header = [0u8; HEADER_SIZE];
    header[0..8].copy_from_slice(HEADER_MAGIC);
    header[8..12].copy_from_slice(&1u32.to_le_bytes()); // version = 1
    header[12..16].copy_from_slice(&(chunk_size as u32).to_le_bytes());
    header[16..24].copy_from_slice(&file_len.to_le_bytes());
    header[24..28].copy_from_slice(&num_chunks.to_le_bytes());
    // 28..32 reserved zeroes
    dst.write_all(&header).map_err(|e| e.to_string())?;

    let cipher = Aes256Gcm::new(Key::<Aes256Gcm>::from_slice(key));
    let mut buffer = vec![0u8; chunk_size];

    for i in 0..num_chunks {
        let n = src.read(&mut buffer).map_err(|e| e.to_string())?;
        let nonce_bytes = make_nonce(i);
        let nonce = Nonce::from_slice(&nonce_bytes);

        let ciphertext = cipher
            .encrypt(nonce, &buffer[..n])
            .map_err(|e| format!("AES-GCM encryption failed at chunk {i}: {:?}", e))?;

        // Write 12 bytes nonce + ciphertext (with 16 bytes tag appended)
        dst.write_all(&nonce_bytes).map_err(|e| e.to_string())?;
        dst.write_all(&ciphertext).map_err(|e| e.to_string())?;
    }

    dst.flush().map_err(|e| e.to_string())?;
    Ok(())
}

pub fn decrypt_file(src_path: &Path, dst_path: &Path, key: &[u8; 32]) -> Result<(), String> {
    if let Some(parent) = dst_path.parent() {
        std::fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    }

    let mut src = File::open(src_path).map_err(|e| format!("Failed to open enc src: {}", e))?;
    let mut header = [0u8; HEADER_SIZE];
    src.read_exact(&mut header)
        .map_err(|e| format!("Failed to read header: {}", e))?;

    if &header[0..8] != HEADER_MAGIC {
        return Err("Invalid file magic in encrypted header".to_string());
    }

    let version = u32::from_le_bytes(header[8..12].try_into().unwrap());
    if version != 1 {
        return Err(format!("Unsupported encryption version: {version}"));
    }

    let chunk_size = u32::from_le_bytes(header[12..16].try_into().unwrap()) as usize;
    let _original_len = u64::from_le_bytes(header[16..24].try_into().unwrap());
    let num_chunks = u32::from_le_bytes(header[24..28].try_into().unwrap());

    let mut dst = File::create(dst_path).map_err(|e| format!("Failed to create dst: {}", e))?;
    let cipher = Aes256Gcm::new(Key::<Aes256Gcm>::from_slice(key));

    for i in 0..num_chunks {
        let mut nonce_bytes = [0u8; NONCE_SIZE];
        src.read_exact(&mut nonce_bytes)
            .map_err(|e| format!("Failed to read nonce for chunk {i}: {}", e))?;
        let nonce = Nonce::from_slice(&nonce_bytes);

        // Determine ciphertext chunk length on disk
        // A chunk has up to chunk_size plaintext bytes, plus TAG_SIZE (16 bytes)
        // If it's not the last chunk, it is chunk_size + TAG_SIZE
        // For the last chunk, read until EOF or remaining bytes
        let mut chunk_buf = Vec::new();
        if i + 1 < num_chunks {
            chunk_buf.resize(chunk_size + TAG_SIZE, 0);
            src.read_exact(&mut chunk_buf)
                .map_err(|e| format!("Failed to read chunk {i}: {}", e))?;
        } else {
            src.read_to_end(&mut chunk_buf)
                .map_err(|e| format!("Failed to read last chunk {i}: {}", e))?;
        }

        let plaintext = cipher
            .decrypt(nonce, chunk_buf.as_slice())
            .map_err(|e| format!("Decryption / authentication failed at chunk {i}: {:?}", e))?;

        dst.write_all(&plaintext).map_err(|e| e.to_string())?;
    }

    dst.flush().map_err(|e| e.to_string())?;
    Ok(())
}

pub fn decrypt_range(
    enc_path: &Path,
    key: &[u8; 32],
    start_offset: u64,
    end_offset: u64,
) -> Result<Vec<u8>, String> {
    let mut file = File::open(enc_path).map_err(|e| format!("Failed to open enc file: {}", e))?;
    let mut header = [0u8; HEADER_SIZE];
    file.read_exact(&mut header)
        .map_err(|e| format!("Failed to read header: {}", e))?;

    if &header[0..8] != HEADER_MAGIC {
        return Err("Invalid file magic in encrypted header".to_string());
    }

    let chunk_size = u32::from_le_bytes(header[12..16].try_into().unwrap()) as usize;
    let original_len = u64::from_le_bytes(header[16..24].try_into().unwrap());
    let num_chunks = u32::from_le_bytes(header[24..28].try_into().unwrap());

    if start_offset >= original_len || start_offset >= end_offset {
        return Ok(Vec::new());
    }

    let effective_end = end_offset.min(original_len);
    let first_chunk = (start_offset / (chunk_size as u64)) as u32;
    let last_chunk = ((effective_end - 1) / (chunk_size as u64)) as u32;

    let cipher = Aes256Gcm::new(Key::<Aes256Gcm>::from_slice(key));
    let mut output = Vec::with_capacity((effective_end - start_offset) as usize);

    for chunk_idx in first_chunk..=last_chunk {
        let chunk_offset_on_disk = (HEADER_SIZE as u64)
            + (chunk_idx as u64) * ((chunk_size + CHUNK_OVERHEAD) as u64);

        file.seek(SeekFrom::Start(chunk_offset_on_disk))
            .map_err(|e| format!("Seek failed: {}", e))?;

        let mut nonce_bytes = [0u8; NONCE_SIZE];
        file.read_exact(&mut nonce_bytes)
            .map_err(|e| format!("Nonce read failed: {}", e))?;
        let nonce = Nonce::from_slice(&nonce_bytes);

        let mut ciphertext = Vec::new();
        if chunk_idx + 1 < num_chunks {
            ciphertext.resize(chunk_size + TAG_SIZE, 0);
            file.read_exact(&mut ciphertext)
                .map_err(|e| format!("Read chunk {chunk_idx} failed: {}", e))?;
        } else {
            // Last chunk: read remaining ciphertext bytes
            let rem_plain = (original_len - (chunk_idx as u64 * chunk_size as u64)) as usize;
            ciphertext.resize(rem_plain + TAG_SIZE, 0);
            file.read_exact(&mut ciphertext)
                .map_err(|e| format!("Read last chunk {chunk_idx} failed: {}", e))?;
        }

        let decrypted = cipher
            .decrypt(nonce, ciphertext.as_slice())
            .map_err(|e| format!("Authentication/decryption failed for chunk {chunk_idx}: {:?}", e))?;

        let chunk_start_in_file = chunk_idx as u64 * (chunk_size as u64);
        let chunk_end_in_file = chunk_start_in_file + (decrypted.len() as u64);

        let slice_start = if start_offset > chunk_start_in_file {
            (start_offset - chunk_start_in_file) as usize
        } else {
            0
        };

        let slice_end = if effective_end < chunk_end_in_file {
            (effective_end - chunk_start_in_file) as usize
        } else {
            decrypted.len()
        };

        if slice_start < slice_end && slice_start < decrypted.len() {
            output.extend_from_slice(&decrypted[slice_start..slice_end]);
        }
    }

    Ok(output)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_encrypt_decrypt_round_trip() {
        let temp_dir = std::env::temp_dir().join(format!("test_roundtrip_{}", std::process::id()));
        std::fs::create_dir_all(&temp_dir).unwrap();

        let src_path = temp_dir.join("original.bin");
        let enc_path = temp_dir.join("encrypted.enc");
        let dec_path = temp_dir.join("decrypted.bin");

        // 600 KB payload spans multiple 256 KB chunks
        let original_data = vec![0x42u8; 600 * 1024];
        std::fs::write(&src_path, &original_data).unwrap();

        let key = [7u8; 32];
        encrypt_file(&src_path, &enc_path, &key, DEFAULT_CHUNK_SIZE).expect("encrypt should succeed");
        decrypt_file(&enc_path, &dec_path, &key).expect("decrypt should succeed");

        let decrypted_data = std::fs::read(&dec_path).unwrap();
        assert_eq!(decrypted_data.len(), original_data.len());
        assert_eq!(decrypted_data, original_data);

        let _ = std::fs::remove_dir_all(&temp_dir);
    }

    #[test]
    fn test_tamper_detection() {
        let temp_dir = std::env::temp_dir().join(format!("test_tamper_{}", std::process::id()));
        std::fs::create_dir_all(&temp_dir).unwrap();

        let src_path = temp_dir.join("plain.bin");
        let enc_path = temp_dir.join("tampered.enc");
        let dec_path = temp_dir.join("out.bin");

        let original_data = b"Sensitive lecture media content to be verified";
        std::fs::write(&src_path, original_data).unwrap();

        let key = [9u8; 32];
        encrypt_file(&src_path, &enc_path, &key, DEFAULT_CHUNK_SIZE).unwrap();

        // Tamper with one byte in the ciphertext portion (past header)
        let mut enc_bytes = std::fs::read(&enc_path).unwrap();
        let target_idx = HEADER_SIZE + NONCE_SIZE + 5;
        enc_bytes[target_idx] ^= 0xFF; // flip bits
        std::fs::write(&enc_path, &enc_bytes).unwrap();

        // Decryption MUST fail authentication
        let res = decrypt_file(&enc_path, &dec_path, &key);
        assert!(res.is_err(), "Tampered file must fail authentication");

        let _ = std::fs::remove_dir_all(&temp_dir);
    }

    #[test]
    fn test_range_read_across_chunk_boundary() {
        let temp_dir = std::env::temp_dir().join(format!("test_range_{}", std::process::id()));
        std::fs::create_dir_all(&temp_dir).unwrap();

        let src_path = temp_dir.join("media.bin");
        let enc_path = temp_dir.join("media.enc");

        // Use a small chunk size for testing: 1024 bytes per chunk
        let test_chunk_size = 1024;
        let mut sample_data = Vec::with_capacity(3500);
        for i in 0..3500 {
            sample_data.push((i % 256) as u8);
        }
        std::fs::write(&src_path, &sample_data).unwrap();

        let key = [42u8; 32];
        encrypt_file(&src_path, &enc_path, &key, test_chunk_size).unwrap();

        // Range read across chunk boundary: bytes 900 to 2200 (spans chunk 0, 1, 2)
        let start = 900u64;
        let end = 2200u64;
        let range_bytes = decrypt_range(&enc_path, &key, start, end).expect("range read should succeed");

        let expected_bytes = &sample_data[(start as usize)..(end as usize)];
        assert_eq!(range_bytes.len(), expected_bytes.len());
        assert_eq!(range_bytes, expected_bytes);

        let _ = std::fs::remove_dir_all(&temp_dir);
    }
}
