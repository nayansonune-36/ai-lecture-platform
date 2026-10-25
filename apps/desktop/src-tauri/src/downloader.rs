use std::fs::{self, File, OpenOptions};
use std::io::{Read, Write};
use std::path::Path;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::time::{Duration, Instant};

use futures_util::StreamExt;
use reqwest::header::RANGE;
use rusqlite::Connection;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use tauri::{AppHandle, Emitter};

use crate::encryption::{self, DEFAULT_CHUNK_SIZE};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DownloadProgressEvent {
    pub lecture_id: String,
    pub bytes_downloaded: u64,
    pub total_bytes: u64,
    pub speed_bps: u64,
    pub state: String,
    pub error: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ManifestFileEntry {
    pub path: String,
    pub size: u64,
    pub sha256: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ManifestJson {
    pub schema_version: u32,
    pub lecture_id: String,
    pub title: String,
    pub course_title: String,
    pub duration_ms: Option<i64>,
    pub rendition: i32,
    pub files: Vec<ManifestFileEntry>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OfflineBundlePollResponse {
    pub job_id: String,
    pub status: String,
    pub size_bytes: Option<u64>,
    pub sha256: Option<String>,
    pub download_url: Option<String>,
    pub license_token: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DownloadRecord {
    pub lecture_id: String,
    pub course_title: String,
    pub lecture_title: String,
    pub rendition: i32,
    pub version: i32,
    pub path: Option<String>,
    pub size_bytes: i64,
    pub sha256: String,
    pub status: String,
    pub progress: f64,
    pub error: Option<String>,
    pub created_at: String,
    pub completed_at: Option<String>,
    pub days_left: Option<i64>,
    pub is_expired: bool,
    pub expires_at: Option<String>,
}

pub fn compute_sha256(path: &Path) -> Result<String, String> {
    let mut file = File::open(path).map_err(|e| format!("Failed to open file for hashing: {}", e))?;
    let mut hasher = Sha256::new();
    let mut buffer = [0u8; 64 * 1024];

    loop {
        let n = file
            .read(&mut buffer)
            .map_err(|e| format!("Failed reading file for hash: {}", e))?;
        if n == 0 {
            break;
        }
        hasher.update(&buffer[..n]);
    }

    Ok(hex::encode(hasher.finalize()))
}

pub fn verify_file_hash(path: &Path, expected_hex: &str) -> Result<(), String> {
    let actual_hex = compute_sha256(path)?;
    if !actual_hex.eq_ignore_ascii_case(expected_hex) {
        return Err(format!(
            "Hash mismatch for {:?}: expected {}, got {}",
            path.file_name().unwrap_or_default(),
            expected_hex,
            actual_hex
        ));
    }
    Ok(())
}

pub fn verify_and_extract_bundle(
    zip_path: &Path,
    extract_dir: &Path,
    expected_bundle_sha256: &str,
) -> Result<ManifestJson, String> {
    // 1. Verify zip sha256
    verify_file_hash(zip_path, expected_bundle_sha256)?;

    // 2. Unzip to temporary extraction folder
    if extract_dir.exists() {
        let _ = fs::remove_dir_all(extract_dir);
    }
    fs::create_dir_all(extract_dir).map_err(|e| e.to_string())?;

    let file = File::open(zip_path).map_err(|e| format!("Cannot open zip file: {}", e))?;
    let mut archive = zip::ZipArchive::new(file).map_err(|e| format!("Invalid zip archive: {}", e))?;

    archive
        .extract(extract_dir)
        .map_err(|e| format!("Failed to extract zip archive: {}", e))?;

    // 3. Parse manifest.json
    let manifest_path = extract_dir.join("manifest.json");
    if !manifest_path.is_file() {
        return Err("manifest.json missing from extracted bundle".to_string());
    }

    let manifest_content = fs::read_to_string(&manifest_path)
        .map_err(|e| format!("Failed to read manifest.json: {}", e))?;
    let manifest: ManifestJson = serde_json::from_str(&manifest_content)
        .map_err(|e| format!("Failed to parse manifest.json: {}", e))?;

    // 4. Verify every file against manifest hashes
    for entry in &manifest.files {
        let target_file = extract_dir.join(&entry.path);
        if !target_file.is_file() {
            return Err(format!("Bundle missing manifest file: {}", entry.path));
        }

        let meta = target_file
            .metadata()
            .map_err(|e| format!("Cannot read meta for {}: {}", entry.path, e))?;
        if meta.len() != entry.size {
            return Err(format!(
                "Size mismatch for {}: expected {}, got {}",
                entry.path,
                entry.size,
                meta.len()
            ));
        }

        verify_file_hash(&target_file, &entry.sha256)?;
    }

    Ok(manifest)
}

pub fn encrypt_bundle_at_rest(
    extract_dir: &Path,
    dest_bundle_dir: &Path,
    lecture_id: &str,
    device_secret: &[u8; 32],
) -> Result<(), String> {
    if dest_bundle_dir.exists() {
        let _ = fs::remove_dir_all(dest_bundle_dir);
    }
    fs::create_dir_all(dest_bundle_dir).map_err(|e| e.to_string())?;

    // Recursively walk and encrypt all files in extract_dir
    fn visit_and_encrypt(
        dir: &Path,
        root: &Path,
        dest_bundle_dir: &Path,
        lecture_id: &str,
        device_secret: &[u8; 32],
    ) -> Result<(), String> {
        for entry in fs::read_dir(dir).map_err(|e| e.to_string())?.flatten() {
            let p = entry.path();
            if p.is_dir() {
                visit_and_encrypt(&p, root, dest_bundle_dir, lecture_id, device_secret)?;
            } else if p.is_file() {
                let rel = p
                    .strip_prefix(root)
                    .map_err(|e| e.to_string())?
                    .to_string_lossy()
                    .replace('\\', "/");

                let dest_enc_file = dest_bundle_dir.join(format!("{}.enc", rel));
                let file_key = encryption::derive_file_key(device_secret, lecture_id, &rel)?;

                encryption::encrypt_file(&p, &dest_enc_file, &file_key, DEFAULT_CHUNK_SIZE)?;
            }
        }
        Ok(())
    }

    visit_and_encrypt(
        extract_dir,
        extract_dir,
        dest_bundle_dir,
        lecture_id,
        device_secret,
    )
}

pub async fn request_and_poll_bundle(
    server_url: &str,
    access_token: &str,
    lecture_id: &str,
    rendition: i32,
    device_id: &str,
) -> Result<OfflineBundlePollResponse, String> {
    let client = reqwest::Client::new();
    let base = server_url.trim().trim_end_matches('/');

    let req_url = format!("{}/api/v1/lectures/{}/offline-bundle", base, lecture_id);
    let post_res = client
        .post(&req_url)
        .header("Authorization", format!("Bearer {}", access_token))
        .json(&serde_json::json!({
            "device_id": device_id,
            "rendition": rendition
        }))
        .send()
        .await
        .map_err(|e| format!("Failed to request bundle: {}", e))?;

    if !post_res.status().is_success() {
        let status = post_res.status();
        let body = post_res.text().await.unwrap_or_default();
        return Err(format!("Offline bundle request failed ({status}): {body}"));
    }

    let initial: OfflineBundlePollResponse = post_res
        .json()
        .await
        .map_err(|e| format!("Failed to parse bundle request response: {}", e))?;

    if initial.status == "succeeded" && initial.download_url.is_some() {
        return Ok(initial);
    }

    // Poll until ready
    let job_id = initial.job_id;
    let poll_url = format!("{}/api/v1/offline-bundles/{}", base, job_id);

    let start_time = Instant::now();
    let timeout = Duration::from_secs(180);

    while start_time.elapsed() < timeout {
        tokio::time::sleep(Duration::from_millis(1500)).await;

        let poll_res = client
            .get(&poll_url)
            .header("Authorization", format!("Bearer {}", access_token))
            .send()
            .await;

        if let Ok(res) = poll_res {
            if res.status().is_success() {
                if let Ok(data) = res.json::<OfflineBundlePollResponse>().await {
                    if data.status == "succeeded" {
                        return Ok(data);
                    }
                    if data.status == "failed" {
                        return Err("Server bundle packaging job failed".to_string());
                    }
                }
            }
        }
    }

    Err("Timed out waiting for server bundle packaging".to_string())
}

pub async fn stream_download_resumable(
    download_url: &str,
    destination_part_path: &Path,
    total_expected_bytes: u64,
    cancel_flag: Arc<AtomicBool>,
    app_handle: Option<&AppHandle>,
    lecture_id: &str,
) -> Result<(), String> {
    if let Some(parent) = destination_part_path.parent() {
        let _ = fs::create_dir_all(parent);
    }

    let mut current_bytes = if destination_part_path.exists() {
        fs::metadata(destination_part_path).map(|m| m.len()).unwrap_or(0)
    } else {
        0
    };

    if current_bytes >= total_expected_bytes && total_expected_bytes > 0 {
        return Ok(());
    }

    let client = reqwest::Client::new();
    let mut req = client.get(download_url);

    if current_bytes > 0 {
        req = req.header(RANGE, format!("bytes={}-", current_bytes));
    }

    let res = req
        .send()
        .await
        .map_err(|e| format!("Download stream request failed: {}", e))?;

    let status = res.status();
    if !status.is_success() {
        return Err(format!("Server returned HTTP status {}", status));
    }

    // Open file in append or create mode depending on status
    let mut file = if status == reqwest::StatusCode::PARTIAL_CONTENT {
        OpenOptions::new()
            .create(true)
            .append(true)
            .open(destination_part_path)
            .map_err(|e| e.to_string())?
    } else {
        // Full response (start from scratch)
        current_bytes = 0;
        File::create(destination_part_path).map_err(|e| e.to_string())?
    };

    let mut stream = res.bytes_stream();
    let mut last_speed_check = Instant::now();
    let mut bytes_since_check = 0u64;
    let mut current_speed = 0u64;

    while let Some(chunk_res) = stream.next().await {
        if !cancel_flag.load(Ordering::Relaxed) {
            // Cancel or Pause requested
            return Err("Paused".to_string());
        }

        let chunk = chunk_res.map_err(|e| format!("Stream read error: {}", e))?;
        file.write_all(&chunk)
            .map_err(|e| format!("File write error: {}", e))?;

        current_bytes += chunk.len() as u64;
        bytes_since_check += chunk.len() as u64;

        if last_speed_check.elapsed() >= Duration::from_millis(500) {
            let elapsed_secs = last_speed_check.elapsed().as_secs_f64();
            if elapsed_secs > 0.0 {
                current_speed = (bytes_since_check as f64 / elapsed_secs) as u64;
            }
            bytes_since_check = 0;
            last_speed_check = Instant::now();

            if let Some(app) = app_handle {
                let _ = app.emit(
                    "download_progress",
                    DownloadProgressEvent {
                        lecture_id: lecture_id.to_string(),
                        bytes_downloaded: current_bytes,
                        total_bytes: total_expected_bytes,
                        speed_bps: current_speed,
                        state: "downloading".to_string(),
                        error: None,
                    },
                );
            }
        }
    }

    file.flush().map_err(|e| e.to_string())?;

    if let Some(app) = app_handle {
        let _ = app.emit(
            "download_progress",
            DownloadProgressEvent {
                lecture_id: lecture_id.to_string(),
                bytes_downloaded: current_bytes,
                total_bytes: total_expected_bytes,
                speed_bps: 0,
                state: "verifying".to_string(),
                error: None,
            },
        );
    }

    Ok(())
}

pub fn save_license_token(
    conn: &Connection,
    lecture_id: &str,
    device_id: &str,
    token: &str,
    bundle_sha256: &str,
) -> Result<(), String> {
    let now = chrono_lite_iso();
    // Default 14-day validity string for cache
    let expires = chrono_lite_future_14_days();

    conn.execute(
        r#"
        INSERT INTO licenses (lecture_id, device_id, token, bundle_sha256, issued_at, expires_at, revoked_at)
        VALUES (?1, ?2, ?3, ?4, ?5, ?6, NULL)
        ON CONFLICT(lecture_id) DO UPDATE SET
            device_id = ?2,
            token = ?3,
            bundle_sha256 = ?4,
            issued_at = ?5,
            expires_at = ?6,
            revoked_at = NULL
        "#,
        [lecture_id, device_id, token, bundle_sha256, &now, &expires],
    )
    .map_err(|e| format!("Failed to save license token: {}", e))?;

    Ok(())
}

pub fn list_all_downloads(conn: &Connection) -> Result<Vec<DownloadRecord>, String> {
    let mut stmt = conn
        .prepare(
            r#"
            SELECT lecture_id, course_title, lecture_title, rendition, version, path,
                   size_bytes, sha256, status, progress, error, created_at, completed_at
            FROM downloads ORDER BY created_at DESC
            "#,
        )
        .map_err(|e| e.to_string())?;

    let raw_rows = stmt
        .query_map([], |row| {
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, String>(1)?,
                row.get::<_, String>(2)?,
                row.get::<_, i32>(3)?,
                row.get::<_, i32>(4)?,
                row.get::<_, Option<String>>(5)?,
                row.get::<_, i64>(6)?,
                row.get::<_, String>(7)?,
                row.get::<_, String>(8)?,
                row.get::<_, f64>(9)?,
                row.get::<_, Option<String>>(10)?,
                row.get::<_, String>(11)?,
                row.get::<_, Option<String>>(12)?,
            ))
        })
        .map_err(|e| e.to_string())?
        .collect::<Result<Vec<_>, _>>()
        .map_err(|e| e.to_string())?;

    drop(stmt);

    let mut result = Vec::with_capacity(raw_rows.len());
    for (
        lecture_id,
        course_title,
        lecture_title,
        rendition,
        version,
        path,
        size_bytes,
        sha256,
        status,
        progress,
        error,
        created_at,
        completed_at,
    ) in raw_rows
    {
        let lic_status = crate::license_verifier::get_license_status(conn, &lecture_id);
        result.push(DownloadRecord {
            lecture_id,
            course_title,
            lecture_title,
            rendition,
            version,
            path,
            size_bytes,
            sha256,
            status,
            progress,
            error,
            created_at,
            completed_at,
            days_left: lic_status.days_left,
            is_expired: lic_status.is_expired,
            expires_at: lic_status.expires_at,
        });
    }

    Ok(result)
}

pub fn remove_download_files_and_db(
    conn: &Connection,
    app_data_dir: &Path,
    lecture_id: &str,
) -> Result<(), String> {
    // 1. Remove encrypted bundle files on disk
    let bundle_dir = app_data_dir.join("bundles").join(lecture_id);
    if bundle_dir.exists() {
        let _ = fs::remove_dir_all(&bundle_dir);
    }

    // 2. Remove temp download / extract
    let temp_part = app_data_dir.join("temp_downloads").join(format!("{}.zip.part", lecture_id));
    if temp_part.exists() {
        let _ = fs::remove_file(&temp_part);
    }
    let temp_extract = app_data_dir.join("temp_extract").join(lecture_id);
    if temp_extract.exists() {
        let _ = fs::remove_dir_all(&temp_extract);
    }

    // 3. Remove DB rows
    conn.execute("DELETE FROM downloads WHERE lecture_id = ?1", [lecture_id])
        .map_err(|e| e.to_string())?;
    conn.execute("DELETE FROM licenses WHERE lecture_id = ?1", [lecture_id])
        .map_err(|e| e.to_string())?;

    Ok(())
}

fn chrono_lite_iso() -> String {
    let now = std::time::SystemTime::now();
    let dt = now
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs();
    format!("{}", dt)
}

fn chrono_lite_future_14_days() -> String {
    let now = std::time::SystemTime::now();
    let dt = now
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs()
        + (14 * 24 * 3600);
    format!("{}", dt)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_hash_mismatch_rejected() {
        let temp_dir = std::env::temp_dir().join(format!("test_mismatch_{}", std::process::id()));
        std::fs::create_dir_all(&temp_dir).unwrap();

        let dummy_zip = temp_dir.join("bundle.zip");
        std::fs::write(&dummy_zip, b"corrupted dummy zip payload").unwrap();

        let extract_dir = temp_dir.join("extracted");
        let expected_sha256 = "0000000000000000000000000000000000000000000000000000000000000000";

        let res = verify_and_extract_bundle(&dummy_zip, &extract_dir, expected_sha256);
        assert!(res.is_err(), "Expected hash mismatch to be rejected");
        assert!(res.unwrap_err().contains("Hash mismatch"));

        let _ = std::fs::remove_dir_all(&temp_dir);
    }

    #[test]
    fn test_resume_after_interruption() {
        let temp_dir = std::env::temp_dir().join(format!("test_resume_{}", std::process::id()));
        std::fs::create_dir_all(&temp_dir).unwrap();

        let part_file = temp_dir.join("sample.part");

        // 1. Simulate first chunk (50 KB)
        let chunk1 = vec![0xAAu8; 50 * 1024];
        std::fs::write(&part_file, &chunk1).unwrap();
        assert_eq!(std::fs::metadata(&part_file).unwrap().len(), 50 * 1024);

        // 2. Simulate resuming from offset 50 KB and appending chunk 2 (70 KB)
        let chunk2 = vec![0xBBu8; 70 * 1024];
        let mut f = OpenOptions::new().append(true).open(&part_file).unwrap();
        f.write_all(&chunk2).unwrap();
        f.flush().unwrap();

        // 3. Verify total length and contents
        let total = std::fs::read(&part_file).unwrap();
        assert_eq!(total.len(), 120 * 1024);
        assert_eq!(&total[0..(50 * 1024)], chunk1.as_slice());
        assert_eq!(&total[(50 * 1024)..], chunk2.as_slice());

        let _ = std::fs::remove_dir_all(&temp_dir);
    }
}
