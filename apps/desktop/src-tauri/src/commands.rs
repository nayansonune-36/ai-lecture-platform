use std::collections::HashMap;
use std::path::PathBuf;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};

use serde::{Deserialize, Serialize};
use tauri::{AppHandle, Emitter, State};

use crate::auth::{self, LoginResult};
use crate::db::Database;
use crate::device::{self, DeviceInfo};
use crate::downloader::{self, DownloadProgressEvent, DownloadRecord};
use crate::keyring_store::{self, DEFAULT_SERVICE_NAME};
use crate::settings::{self, UserProfile};

pub struct AppState {
    pub db: Mutex<Database>,
    pub app_data_dir: PathBuf,
    pub access_token: Mutex<Option<String>>,
    pub active_downloads: Mutex<HashMap<String, Arc<AtomicBool>>>,
    pub local_server_port: u16,
    pub session_token: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LocalServerInfo {
    pub port: u16,
    pub session_token: String,
    pub base_url: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OfflinePlaybackInfo {
    pub lecture_id: String,
    pub lecture_title: String,
    pub course_title: String,
    pub manifest_url: String,
    pub poster_url: Option<String>,
    pub captions_url: Option<String>,
    pub chapters_url: Option<String>,
    pub initial_position_ms: i64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ServerValidationResponse {
    pub status: String,
    pub server_url: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DesktopState {
    pub server_url: Option<String>,
    pub has_server: bool,
    pub last_user: Option<UserProfile>,
    pub device: DeviceInfo,
    pub is_logged_in: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LectureItem {
    pub id: String,
    pub title: String,
    pub description: Option<String>,
    pub duration_ms: Option<i64>,
    pub status: String,
    pub published: bool,
    pub position: i32,
    pub poster_path: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CourseWithLectures {
    pub id: String,
    pub code: String,
    pub title: String,
    pub description: Option<String>,
    pub term: Option<String>,
    pub lectures: Vec<LectureItem>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DesktopSettingsInfo {
    pub server_url: String,
    pub device_name: String,
    pub device_id: Option<String>,
    pub device_public_key: String,
    pub storage_used_bytes: u64,
}

#[tauri::command]
pub async fn validate_and_set_server_url(
    state: State<'_, AppState>,
    server_url: String,
) -> Result<ServerValidationResponse, String> {
    let raw = server_url.trim();
    if raw.is_empty() {
        return Err("Server address cannot be empty".to_string());
    }

    let url_with_scheme = if !raw.starts_with("http://") && !raw.starts_with("https://") {
        format!("http://{}", raw)
    } else {
        raw.to_string()
    };
    let cleaned = url_with_scheme.trim_end_matches('/').to_string();

    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(5))
        .build()
        .map_err(|e| format!("Client creation failed: {}", e))?;

    let health_url = format!("{}/api/v1/healthz", cleaned);
    let res = client
        .get(&health_url)
        .send()
        .await
        .map_err(|e| format!("Failed to connect to {health_url}: {e}"))?;

    if !res.status().is_success() {
        return Err(format!(
            "Server health check failed with status code {}",
            res.status()
        ));
    }

    // Persist server URL in SQLite settings
    {
        let db = state.db.lock().map_err(|e| e.to_string())?;
        settings::set_server_url(db.conn(), &cleaned)
            .map_err(|e| format!("Failed to save server URL: {}", e))?;
    }

    // Pin server license verification public key at first contact (no Mutex held across await)
    let pub_key_url = format!("{}/api/v1/license-public-key", cleaned);
    if let Ok(pk_res) = client.get(&pub_key_url).send().await {
        if pk_res.status().is_success() {
            if let Ok(json) = pk_res.json::<serde_json::Value>().await {
                if let Some(pub_pem) = json.get("public_key").and_then(|v| v.as_str()) {
                    if let Ok(db) = state.db.lock() {
                        let _ = settings::set_license_public_key(db.conn(), pub_pem);
                    }
                }
            }
        }
    }

    Ok(ServerValidationResponse {
        status: "ok".to_string(),
        server_url: cleaned,
    })
}

#[tauri::command]
pub fn get_desktop_state(state: State<'_, AppState>) -> Result<DesktopState, String> {
    let db = state.db.lock().map_err(|e| e.to_string())?;
    let conn = db.conn();

    let server_url = settings::get_server_url(conn).map_err(|e| e.to_string())?;
    let has_server = server_url.as_ref().map(|s| !s.is_empty()).unwrap_or(false);
    let last_user = settings::get_last_user(conn).map_err(|e| e.to_string())?;
    let device = device::get_or_create_device_identity(conn)?;
    let is_logged_in = state.access_token.lock().map_err(|e| e.to_string())?.is_some();

    Ok(DesktopState {
        server_url,
        has_server,
        last_user,
        device,
        is_logged_in,
    })
}

#[tauri::command]
pub async fn desktop_login(
    state: State<'_, AppState>,
    email: String,
    password: String,
) -> Result<LoginResult, String> {
    let server_url = {
        let db = state.db.lock().map_err(|e| e.to_string())?;
        settings::get_server_url(db.conn())
            .map_err(|e| e.to_string())?
            .ok_or_else(|| "Server URL has not been configured".to_string())?
    };

    let auth_res = auth::execute_login_network(&server_url, &email, &password).await?;

    {
        let mut token_guard = state.access_token.lock().map_err(|e| e.to_string())?;
        *token_guard = Some(auth_res.access_token.clone());
    }

    let (identity, existing_device_id) = {
        let db = state.db.lock().map_err(|e| e.to_string())?;
        let _ = settings::set_last_user(db.conn(), &auth_res.user);
        let id_info = device::get_or_create_device_identity(db.conn())?;
        let dev_id = settings::get_device_id(db.conn()).map_err(|e| e.to_string())?;
        (id_info, dev_id)
    };

    let device_id = match existing_device_id {
        Some(id) => id,
        None => {
            match device::register_device_network(
                &server_url,
                &auth_res.access_token,
                &identity.name,
                &identity.public_key,
            )
            .await
            {
                Ok(new_id) => {
                    let db = state.db.lock().map_err(|e| e.to_string())?;
                    let _ = settings::set_device_id(db.conn(), &new_id);
                    new_id
                }
                Err(e) => {
                    eprintln!("Warning: automatic device registration failed: {}", e);
                    "unregistered".to_string()
                }
            }
        }
    };

    Ok(LoginResult {
        user: auth_res.user,
        device_id,
    })
}

#[tauri::command]
pub fn desktop_offline_login(state: State<'_, AppState>) -> Result<LoginResult, String> {
    let db = state.db.lock().map_err(|e| e.to_string())?;
    let conn = db.conn();

    let last_user = settings::get_last_user(conn)
        .map_err(|e| e.to_string())?
        .ok_or_else(|| "No remembered user found. You must connect to the network to sign in.".to_string())?;

    if settings::check_clock_rollback(conn).map_err(|e| e.to_string())? {
        return Err("Clock rollback detected. Connect to the university network to sync your licenses.".to_string());
    }

    let mut stmt = conn
        .prepare("SELECT lecture_id FROM downloads WHERE status = 'completed'")
        .map_err(|e| e.to_string())?;
    let lecture_ids: Vec<String> = stmt
        .query_map([], |r| r.get(0))
        .map_err(|e| e.to_string())?
        .flatten()
        .collect();

    if lecture_ids.is_empty() {
        return Err("No downloaded lectures found. You must connect to the network to sign in.".to_string());
    }

    let mut has_valid_license = false;
    for lid in &lecture_ids {
        if crate::license_verifier::verify_lecture_access(conn, lid).is_ok() {
            has_valid_license = true;
            break;
        }
    }

    if !has_valid_license {
        return Err("All offline licenses have expired or are invalid. Please connect to the university network to renew.".to_string());
    }

    let device = device::get_or_create_device_identity(conn)?;

    Ok(LoginResult {
        user: last_user,
        device_id: device.id.unwrap_or_default(),
    })
}

#[tauri::command]
pub fn desktop_logout(
    state: State<'_, AppState>,
    wipe_downloads: Option<bool>,
) -> Result<(), String> {
    if let Ok(mut guard) = state.access_token.lock() {
        *guard = None;
    }
    let _ = auth::execute_logout();

    if wipe_downloads.unwrap_or(false) {
        let db = state.db.lock().map_err(|e| e.to_string())?;
        let conn = db.conn();

        let bundles_dir = state.app_data_dir.join("bundles");
        if bundles_dir.exists() {
            let _ = std::fs::remove_dir_all(&bundles_dir);
            let _ = std::fs::create_dir_all(&bundles_dir);
        }
        let temp_dl = state.app_data_dir.join("temp_downloads");
        if temp_dl.exists() {
            let _ = std::fs::remove_dir_all(&temp_dl);
            let _ = std::fs::create_dir_all(&temp_dl);
        }
        let temp_ex = state.app_data_dir.join("temp_extract");
        if temp_ex.exists() {
            let _ = std::fs::remove_dir_all(&temp_ex);
            let _ = std::fs::create_dir_all(&temp_ex);
        }

        let _ = conn.execute("DELETE FROM downloads", []);
        let _ = conn.execute("DELETE FROM licenses", []);
        let _ = conn.execute("DELETE FROM progress_queue", []);
    }

    Ok(())
}

#[tauri::command]
pub async fn get_enrolled_courses_and_lectures(
    state: State<'_, AppState>,
) -> Result<Vec<CourseWithLectures>, String> {
    let (server_url, access_token) = {
        let db = state.db.lock().map_err(|e| e.to_string())?;
        let url = settings::get_server_url(db.conn())
            .map_err(|e| e.to_string())?
            .ok_or_else(|| "Server URL not configured".to_string())?;
        let token = state
            .access_token
            .lock()
            .map_err(|e| e.to_string())?
            .clone()
            .ok_or_else(|| "User is not signed in".to_string())?;
        (url, token)
    };

    let client = reqwest::Client::new();
    let courses_url = format!("{}/api/v1/courses", server_url.trim_end_matches('/'));

    let courses_res = client
        .get(&courses_url)
        .header("Authorization", format!("Bearer {}", access_token))
        .send()
        .await
        .map_err(|e| format!("Failed to fetch courses: {}", e))?;

    if !courses_res.status().is_success() {
        return Err(format!(
            "Failed to fetch enrolled courses: status {}",
            courses_res.status()
        ));
    }

    let courses: Vec<serde_json::Value> = courses_res
        .json()
        .await
        .map_err(|e| format!("Failed to parse courses response: {}", e))?;

    let mut result = Vec::new();

    for c in courses {
        let course_id = match c.get("id").and_then(|v| v.as_str()) {
            Some(id) => id,
            None => continue,
        };

        let lecs_url = format!(
            "{}/api/v1/courses/{}/lectures",
            server_url.trim_end_matches('/'),
            course_id
        );

        let mut lectures = Vec::new();
        if let Ok(l_res) = client
            .get(&lecs_url)
            .header("Authorization", format!("Bearer {}", access_token))
            .send()
            .await
        {
            if l_res.status().is_success() {
                if let Ok(items) = l_res.json::<Vec<serde_json::Value>>().await {
                    for item in items {
                        lectures.push(LectureItem {
                            id: item.get("id").and_then(|v| v.as_str()).unwrap_or_default().to_string(),
                            title: item.get("title").and_then(|v| v.as_str()).unwrap_or_default().to_string(),
                            description: item.get("description").and_then(|v| v.as_str()).map(|s| s.to_string()),
                            duration_ms: item.get("duration_ms").and_then(|v| v.as_i64()),
                            status: item.get("status").and_then(|v| v.as_str()).unwrap_or("ready").to_string(),
                            published: item.get("published").and_then(|v| v.as_bool()).unwrap_or(true),
                            position: item.get("position").and_then(|v| v.as_i64()).unwrap_or(0) as i32,
                            poster_path: item.get("poster_path").and_then(|v| v.as_str()).map(|s| s.to_string()),
                        });
                    }
                }
            }
        }

        result.push(CourseWithLectures {
            id: course_id.to_string(),
            code: c.get("code").and_then(|v| v.as_str()).unwrap_or_default().to_string(),
            title: c.get("title").and_then(|v| v.as_str()).unwrap_or_default().to_string(),
            description: c.get("description").and_then(|v| v.as_str()).map(|s| s.to_string()),
            term: c.get("term").and_then(|v| v.as_str()).map(|s| s.to_string()),
            lectures,
        });
    }

    Ok(result)
}

#[tauri::command]
pub async fn get_offline_estimate(
    state: State<'_, AppState>,
    lecture_id: String,
    rendition: i32,
) -> Result<i64, String> {
    let (server_url, access_token) = {
        let db = state.db.lock().map_err(|e| e.to_string())?;
        let url = settings::get_server_url(db.conn())
            .map_err(|e| e.to_string())?
            .ok_or_else(|| "Server URL not configured".to_string())?;
        let token = state
            .access_token
            .lock()
            .map_err(|e| e.to_string())?
            .clone()
            .ok_or_else(|| "User is not signed in".to_string())?;
        (url, token)
    };

    let client = reqwest::Client::new();
    let est_url = format!(
        "{}/api/v1/lectures/{}/offline-estimate?rendition={}",
        server_url.trim_end_matches('/'),
        lecture_id,
        rendition
    );

    let res = client
        .get(&est_url)
        .header("Authorization", format!("Bearer {}", access_token))
        .send()
        .await
        .map_err(|e| format!("Failed to get estimate: {}", e))?;

    if !res.status().is_success() {
        return Err(format!("Estimate request failed with status {}", res.status()));
    }

    let json: serde_json::Value = res.json().await.map_err(|e| e.to_string())?;
    let est = json
        .get("estimated_size_bytes")
        .and_then(|v| v.as_i64())
        .unwrap_or(0);

    Ok(est)
}

#[tauri::command]
pub fn list_downloads(state: State<'_, AppState>) -> Result<Vec<DownloadRecord>, String> {
    let db = state.db.lock().map_err(|e| e.to_string())?;
    downloader::list_all_downloads(db.conn())
}

#[tauri::command]
pub fn delete_download(state: State<'_, AppState>, lecture_id: String) -> Result<(), String> {
    let db = state.db.lock().map_err(|e| e.to_string())?;
    downloader::remove_download_files_and_db(db.conn(), &state.app_data_dir, &lecture_id)
}

#[tauri::command]
pub fn pause_download(state: State<'_, AppState>, lecture_id: String) -> Result<(), String> {
    let downloads = state.active_downloads.lock().map_err(|e| e.to_string())?;
    if let Some(flag) = downloads.get(&lecture_id) {
        flag.store(false, Ordering::Relaxed);
    }
    let db = state.db.lock().map_err(|e| e.to_string())?;
    db.conn()
        .execute(
            "UPDATE downloads SET status = 'paused' WHERE lecture_id = ?1",
            [&lecture_id],
        )
        .ok();
    Ok(())
}

#[tauri::command]
pub async fn resume_download(
    app: AppHandle,
    state: State<'_, AppState>,
    lecture_id: String,
) -> Result<(), String> {
    let rendition = {
        let db = state.db.lock().map_err(|e| e.to_string())?;
        let mut stmt = db
            .conn()
            .prepare("SELECT rendition FROM downloads WHERE lecture_id = ?1")
            .map_err(|e| e.to_string())?;
        stmt.query_row([&lecture_id], |row| row.get(0)).unwrap_or(480)
    };
    start_download(app, state, lecture_id, rendition, None, None).await
}

#[tauri::command]
pub fn cancel_download(state: State<'_, AppState>, lecture_id: String) -> Result<(), String> {
    // 1. Signal pause/cancel
    if let Ok(downloads) = state.active_downloads.lock() {
        if let Some(flag) = downloads.get(&lecture_id) {
            flag.store(false, Ordering::Relaxed);
        }
    }
    // 2. Remove files and DB rows
    let db = state.db.lock().map_err(|e| e.to_string())?;
    downloader::remove_download_files_and_db(db.conn(), &state.app_data_dir, &lecture_id)
}

#[tauri::command]
pub async fn start_download(
    app: AppHandle,
    state: State<'_, AppState>,
    lecture_id: String,
    rendition: i32,
    lecture_title: Option<String>,
    course_title: Option<String>,
) -> Result<(), String> {
    let (server_url, access_token, device_id) = {
        let db = state.db.lock().map_err(|e| e.to_string())?;
        let url = settings::get_server_url(db.conn())
            .map_err(|e| e.to_string())?
            .ok_or_else(|| "Server URL not configured".to_string())?;
        let token = state
            .access_token
            .lock()
            .map_err(|e| e.to_string())?
            .clone()
            .ok_or_else(|| "User is not signed in".to_string())?;
        let dev_id = settings::get_device_id(db.conn())
            .map_err(|e| e.to_string())?
            .ok_or_else(|| "Device is not registered".to_string())?;
        (url, token, dev_id)
    };

    let cancel_flag = Arc::new(AtomicBool::new(true));
    {
        let mut active = state.active_downloads.lock().map_err(|e| e.to_string())?;
        active.insert(lecture_id.clone(), cancel_flag.clone());
    }

    let lec_id = lecture_id.clone();
    let app_dir = state.app_data_dir.clone();
    let lec_title = lecture_title.unwrap_or_else(|| "Lecture".to_string());
    let crs_title = course_title.unwrap_or_else(|| "Course".to_string());

    // Record pending in downloads table
    {
        let db = state.db.lock().map_err(|e| e.to_string())?;
        db.conn()
            .execute(
                r#"
                INSERT INTO downloads (lecture_id, course_title, lecture_title, rendition, version, path,
                                       size_bytes, sha256, status, progress, error, created_at, completed_at)
                VALUES (?1, ?2, ?3, ?4, 1, NULL, 0, '', 'pending', 0.0, NULL, datetime('now'), NULL)
                ON CONFLICT(lecture_id) DO UPDATE SET
                    status = 'pending',
                    error = NULL
                "#,
                [&lec_id, &crs_title, &lec_title, &rendition.to_string()],
            )
            .map_err(|e| e.to_string())?;
    }

    let _ = app.emit(
        "download_progress",
        DownloadProgressEvent {
            lecture_id: lec_id.clone(),
            bytes_downloaded: 0,
            total_bytes: 0,
            speed_bps: 0,
            state: "pending".to_string(),
            error: None,
        },
    );

    // Spawn background download task
    tokio::spawn(async move {
        // Step 1: Request & poll bundle job
        let poll_res = downloader::request_and_poll_bundle(
            &server_url,
            &access_token,
            &lec_id,
            rendition,
            &device_id,
        )
        .await;

        let bundle_info = match poll_res {
            Ok(b) => b,
            Err(err) => {
                let _ = app.emit(
                    "download_progress",
                    DownloadProgressEvent {
                        lecture_id: lec_id.clone(),
                        bytes_downloaded: 0,
                        total_bytes: 0,
                        speed_bps: 0,
                        state: "failed".to_string(),
                        error: Some(err.clone()),
                    },
                );
                return;
            }
        };

        let raw_download_url = bundle_info.download_url.unwrap_or_default();
        let full_download_url = if raw_download_url.starts_with("http://")
            || raw_download_url.starts_with("https://")
        {
            raw_download_url
        } else {
            format!("{}/{}", server_url.trim_end_matches('/'), raw_download_url.trim_start_matches('/'))
        };

        let total_size = bundle_info.size_bytes.unwrap_or(0);
        let bundle_sha = bundle_info.sha256.unwrap_or_default();

        let part_file = app_dir
            .join("temp_downloads")
            .join(format!("{}.zip.part", lec_id));

        // Step 2: Stream ZIP using Range
        let stream_res = downloader::stream_download_resumable(
            &full_download_url,
            &part_file,
            total_size,
            cancel_flag.clone(),
            Some(&app),
            &lec_id,
        )
        .await;

        if let Err(e) = stream_res {
            if e == "Paused" {
                let _ = app.emit(
                    "download_progress",
                    DownloadProgressEvent {
                        lecture_id: lec_id.clone(),
                        bytes_downloaded: 0,
                        total_bytes: total_size,
                        speed_bps: 0,
                        state: "paused".to_string(),
                        error: None,
                    },
                );
            } else {
                let _ = app.emit(
                    "download_progress",
                    DownloadProgressEvent {
                        lecture_id: lec_id.clone(),
                        bytes_downloaded: 0,
                        total_bytes: total_size,
                        speed_bps: 0,
                        state: "failed".to_string(),
                        error: Some(e),
                    },
                );
            }
            return;
        }

        // Step 3: Verify & extract bundle
        let extract_dir = app_dir.join("temp_extract").join(&lec_id);
        let extract_res = downloader::verify_and_extract_bundle(&part_file, &extract_dir, &bundle_sha);

        if let Err(e) = extract_res {
            let _ = app.emit(
                "download_progress",
                DownloadProgressEvent {
                    lecture_id: lec_id.clone(),
                    bytes_downloaded: total_size,
                    total_bytes: total_size,
                    speed_bps: 0,
                    state: "failed".to_string(),
                    error: Some(format!("Bundle verification failed: {}", e)),
                },
            );
            return;
        }

        // Step 4: Encrypt each file at rest with AES-256-GCM chunking
        let _ = app.emit(
            "download_progress",
            DownloadProgressEvent {
                lecture_id: lec_id.clone(),
                bytes_downloaded: total_size,
                total_bytes: total_size,
                speed_bps: 0,
                state: "encrypting".to_string(),
                error: None,
            },
        );

        let device_secret = keyring_store::get_device_private_key(DEFAULT_SERVICE_NAME)
            .ok()
            .flatten()
            .unwrap_or([0u8; 32]);

        let dest_bundle_dir = app_dir.join("bundles").join(&lec_id);
        let enc_res = downloader::encrypt_bundle_at_rest(
            &extract_dir,
            &dest_bundle_dir,
            &lec_id,
            &device_secret,
        );

        if let Err(e) = enc_res {
            let _ = app.emit(
                "download_progress",
                DownloadProgressEvent {
                    lecture_id: lec_id.clone(),
                    bytes_downloaded: total_size,
                    total_bytes: total_size,
                    speed_bps: 0,
                    state: "failed".to_string(),
                    error: Some(format!("Encryption failed: {}", e)),
                },
            );
            return;
        }

        // Step 5: Clean up plaintext temporary files securely
        let _ = std::fs::remove_dir_all(&extract_dir);
        let _ = std::fs::remove_file(&part_file);

        // Step 6: Store license token and update DB
        if let Some(token) = bundle_info.license_token {
            let db_path = app_dir.join("desktop.db");
            if let Ok(conn) = rusqlite::Connection::open(&db_path) {
                let _ = downloader::save_license_token(
                    &conn,
                    &lec_id,
                    &device_id,
                    &token,
                    &bundle_sha,
                );
                let _ = conn.execute(
                    r#"
                    UPDATE downloads SET
                        status = 'completed',
                        progress = 1.0,
                        size_bytes = ?1,
                        sha256 = ?2,
                        path = ?3,
                        completed_at = datetime('now')
                    WHERE lecture_id = ?4
                    "#,
                    [
                        &(total_size as i64).to_string(),
                        &bundle_sha,
                        &format!("bundles/{}", lec_id),
                        &lec_id,
                    ],
                );
            }
        }

        // Final event
        let _ = app.emit(
            "download_progress",
            DownloadProgressEvent {
                lecture_id: lec_id,
                bytes_downloaded: total_size,
                total_bytes: total_size,
                speed_bps: 0,
                state: "completed".to_string(),
                error: None,
            },
        );
    });

    Ok(())
}

fn calculate_dir_size(path: &std::path::Path) -> u64 {
    if !path.exists() {
        return 0;
    }
    let mut total = 0;
    if let Ok(entries) = std::fs::read_dir(path) {
        for entry in entries.flatten() {
            let p = entry.path();
            if p.is_file() {
                if let Ok(meta) = entry.metadata() {
                    total += meta.len();
                }
            } else if p.is_dir() {
                total += calculate_dir_size(&p);
            }
        }
    }
    total
}

#[tauri::command]
pub fn storage_usage(state: State<'_, AppState>) -> Result<DesktopSettingsInfo, String> {
    let db = state.db.lock().map_err(|e| e.to_string())?;
    let conn = db.conn();

    let server_url = settings::get_server_url(conn)
        .map_err(|e| e.to_string())?
        .unwrap_or_default();
    let device = device::get_or_create_device_identity(conn)?;

    let bundles_dir = state.app_data_dir.join("bundles");
    let storage_used_bytes = calculate_dir_size(&bundles_dir);

    Ok(DesktopSettingsInfo {
        server_url,
        device_name: device.name,
        device_id: device.id,
        device_public_key: device.public_key,
        storage_used_bytes,
    })
}

#[tauri::command]
pub fn get_desktop_settings(state: State<'_, AppState>) -> Result<DesktopSettingsInfo, String> {
    storage_usage(state)
}

#[tauri::command]
pub fn update_desktop_settings(
    state: State<'_, AppState>,
    server_url: Option<String>,
    device_name: Option<String>,
) -> Result<DesktopSettingsInfo, String> {
    let db = state.db.lock().map_err(|e| e.to_string())?;
    let conn = db.conn();

    if let Some(ref url) = server_url {
        settings::set_server_url(conn, url).map_err(|e| e.to_string())?;
    }
    if let Some(ref name) = device_name {
        settings::set_device_name(conn, name).map_err(|e| e.to_string())?;
    }

    drop(db);
    storage_usage(state)
}

#[tauri::command]
pub fn get_local_server_info(state: State<'_, AppState>) -> Result<LocalServerInfo, String> {
    Ok(LocalServerInfo {
        port: state.local_server_port,
        session_token: state.session_token.clone(),
        base_url: format!("http://127.0.0.1:{}/{}", state.local_server_port, state.session_token),
    })
}

#[tauri::command]
pub fn get_offline_playback_info(
    state: State<'_, AppState>,
    lecture_id: String,
) -> Result<OfflinePlaybackInfo, String> {
    let db = state.db.lock().map_err(|e| e.to_string())?;
    let conn = db.conn();

    // 1. Check download record
    let mut stmt = conn
        .prepare("SELECT lecture_title, course_title, status FROM downloads WHERE lecture_id = ?1")
        .map_err(|e| e.to_string())?;

    let row = stmt
        .query_row([&lecture_id], |r| {
            Ok((
                r.get::<_, String>(0)?,
                r.get::<_, String>(1)?,
                r.get::<_, String>(2)?,
            ))
        })
        .map_err(|_| format!("Lecture {} has not been downloaded", lecture_id))?;

    let (lecture_title, course_title, status) = row;
    if status != "completed" {
        return Err(format!("Download is not complete (current status: {})", status));
    }

    // 2. Verify offline license (signature, exp, clock rollback, revoked, device, user)
    crate::license_verifier::verify_lecture_access(conn, &lecture_id)
        .map_err(|e| format!("License verification failed: {}. Connect to renew.", e))?;

    // 3. Get initial playback progress position
    let mut prog_stmt = conn
        .prepare("SELECT position_ms FROM progress_queue WHERE lecture_id = ?1 ORDER BY id DESC LIMIT 1")
        .map_err(|e| e.to_string())?;
    let initial_position_ms: i64 = prog_stmt
        .query_row([&lecture_id], |r| r.get(0))
        .unwrap_or(0);

    let base = format!(
        "http://127.0.0.1:{}/{}/lectures/{}",
        state.local_server_port, state.session_token, lecture_id
    );

    let bundle_dir = state.app_data_dir.join("bundles").join(&lecture_id);

    let poster_url = if bundle_dir.join("poster.jpg.enc").exists() {
        Some(format!("{}/poster.jpg", base))
    } else {
        None
    };

    let captions_url = if bundle_dir.join("captions.vtt.enc").exists() {
        Some(format!("{}/captions.vtt", base))
    } else {
        None
    };

    let chapters_url = if bundle_dir.join("chapters.json.enc").exists() {
        Some(format!("{}/chapters.json", base))
    } else {
        None
    };

    Ok(OfflinePlaybackInfo {
        lecture_id,
        lecture_title,
        course_title,
        manifest_url: format!("{}/hls/master.m3u8", base),
        poster_url,
        captions_url,
        chapters_url,
        initial_position_ms,
    })
}

#[tauri::command]
pub fn save_offline_progress(
    state: State<'_, AppState>,
    lecture_id: String,
    position_ms: i64,
    completed: bool,
) -> Result<(), String> {
    let db = state.db.lock().map_err(|e| e.to_string())?;
    db.conn()
        .execute(
            r#"
            INSERT INTO progress_queue (lecture_id, position_ms, completed, timestamp, attempts)
            VALUES (?1, ?2, ?3, datetime('now'), 0)
            "#,
            rusqlite::params![lecture_id, position_ms, if completed { 1 } else { 0 }],
        )
        .map_err(|e| format!("Failed to save progress: {}", e))?;
    Ok(())
}

#[tauri::command]
pub fn get_offline_progress(
    state: State<'_, AppState>,
    lecture_id: String,
) -> Result<i64, String> {
    let db = state.db.lock().map_err(|e| e.to_string())?;
    let mut stmt = db
        .conn()
        .prepare("SELECT position_ms FROM progress_queue WHERE lecture_id = ?1 ORDER BY id DESC LIMIT 1")
        .map_err(|e| e.to_string())?;
    let pos: Result<i64, _> = stmt.query_row([&lecture_id], |r| r.get(0));
    Ok(pos.unwrap_or(0))
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ConnectivityStatus {
    pub is_online: bool,
    pub server_url: Option<String>,
    pub rollback_detected: bool,
}

#[tauri::command]
pub async fn check_connectivity(state: State<'_, AppState>) -> Result<ConnectivityStatus, String> {
    let (server_url, rollback_detected) = {
        let db = state.db.lock().map_err(|e| e.to_string())?;
        let url = settings::get_server_url(db.conn()).map_err(|e| e.to_string())?;
        let rollback = settings::check_clock_rollback(db.conn()).unwrap_or(false);
        (url, rollback)
    };

    let server_url = match server_url {
        Some(u) if !u.trim().is_empty() => u,
        _ => {
            return Ok(ConnectivityStatus {
                is_online: false,
                server_url: None,
                rollback_detected,
            });
        }
    };

    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(3))
        .build()
        .map_err(|e| e.to_string())?;

    let health_url = format!("{}/healthz", server_url.trim_end_matches('/'));
    match client.get(&health_url).send().await {
        Ok(res) if res.status().is_success() => {
            if let Some(date_header) = res.headers().get(reqwest::header::DATE) {
                if let Ok(date_str) = date_header.to_str() {
                    if let Ok(systime) = httpdate::parse_http_date(date_str) {
                        let server_ts = systime
                            .duration_since(std::time::UNIX_EPOCH)
                            .unwrap_or_default()
                            .as_secs() as i64;
                        if let Ok(db) = state.db.lock() {
                            let _ = settings::set_max_seen_timestamp_authoritative(db.conn(), server_ts);
                        }
                    }
                }
            } else {
                let now = std::time::SystemTime::now()
                    .duration_since(std::time::UNIX_EPOCH)
                    .unwrap_or_default()
                    .as_secs() as i64;
                if let Ok(db) = state.db.lock() {
                    let _ = settings::set_max_seen_timestamp_authoritative(db.conn(), now);
                }
            }

            Ok(ConnectivityStatus {
                is_online: true,
                server_url: Some(server_url),
                rollback_detected: false,
            })
        }
        _ => {
            let rollback = {
                let db = state.db.lock().map_err(|e| e.to_string())?;
                settings::check_clock_rollback(db.conn()).unwrap_or(false)
            };
            Ok(ConnectivityStatus {
                is_online: false,
                server_url: Some(server_url),
                rollback_detected: rollback,
            })
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SyncResult {
    pub is_online: bool,
    pub renewed_count: usize,
    pub revoked_count: usize,
    pub revoked_titles: Vec<String>,
    pub progress_flushed_count: usize,
    pub error: Option<String>,
}

#[derive(Debug, Deserialize)]
struct RenewedLicenseItem {
    pub lecture_id: String,
    pub token: String,
    pub expires_at: String,
}

#[derive(Debug, Deserialize)]
struct RenewResponsePayload {
    #[allow(dead_code)]
    pub device_id: String,
    pub renewed: Vec<RenewedLicenseItem>,
    pub revoked: Vec<String>,
}

pub async fn perform_flush_progress(
    conn_mutex: &Mutex<Database>,
    server_url: &str,
    access_token: &str,
) -> Result<usize, String> {
    let lecture_ids: Vec<String> = {
        let db = conn_mutex.lock().map_err(|e| e.to_string())?;
        let mut stmt = db
            .conn()
            .prepare("SELECT DISTINCT lecture_id FROM progress_queue")
            .map_err(|e| e.to_string())?;
        let rows = stmt
            .query_map([], |r| r.get::<_, String>(0))
            .map_err(|e| e.to_string())?;
        rows.flatten().collect()
    };

    if lecture_ids.is_empty() {
        return Ok(0);
    }

    let client = reqwest::Client::new();
    let mut flushed_count = 0;

    for lecture_id in lecture_ids {
        let latest_opt = {
            let db = conn_mutex.lock().map_err(|e| e.to_string())?;
            let mut stmt = db
                .conn()
                .prepare(
                    r#"
                    SELECT id, position_ms, completed
                    FROM progress_queue
                    WHERE lecture_id = ?1
                    ORDER BY id DESC
                    LIMIT 1
                    "#,
                )
                .map_err(|e| e.to_string())?;

            stmt.query_row([&lecture_id], |r| {
                Ok((
                    r.get::<_, i64>(0)?,
                    r.get::<_, i64>(1)?,
                    r.get::<_, i32>(2)?,
                ))
            })
            .ok()
        };

        if let Some((max_id, pos_ms, comp)) = latest_opt {
            let progress_url = format!(
                "{}/api/v1/lectures/{}/progress",
                server_url.trim_end_matches('/'),
                lecture_id
            );

            let res = client
                .put(&progress_url)
                .header("Authorization", format!("Bearer {}", access_token))
                .json(&serde_json::json!({
                    "position_ms": pos_ms,
                    "completed": comp == 1
                }))
                .send()
                .await;

            match res {
                Ok(r) if r.status().is_success() => {
                    if let Ok(db) = conn_mutex.lock() {
                        let _ = db.conn().execute(
                            "DELETE FROM progress_queue WHERE lecture_id = ?1 AND id <= ?2",
                            rusqlite::params![lecture_id, max_id],
                        );
                    }
                    flushed_count += 1;
                }
                _ => {
                    if let Ok(db) = conn_mutex.lock() {
                        let _ = db.conn().execute(
                            "UPDATE progress_queue SET attempts = attempts + 1 WHERE lecture_id = ?1",
                            rusqlite::params![lecture_id],
                        );
                    }
                }
            }
        }
    }

    Ok(flushed_count)
}

#[tauri::command]
pub async fn flush_progress_queue(state: State<'_, AppState>) -> Result<usize, String> {
    let (server_url, access_token) = {
        let db = state.db.lock().map_err(|e| e.to_string())?;
        let url = settings::get_server_url(db.conn())
            .map_err(|e| e.to_string())?
            .ok_or_else(|| "Server URL not configured".to_string())?;
        let token = state
            .access_token
            .lock()
            .map_err(|e| e.to_string())?
            .clone()
            .ok_or_else(|| "User not logged in".to_string())?;
        (url, token)
    };

    perform_flush_progress(&state.db, &server_url, &access_token).await
}

#[tauri::command]
pub async fn sync_offline_licenses(state: State<'_, AppState>) -> Result<SyncResult, String> {
    let (server_url, device_id, access_token) = {
        let db = state.db.lock().map_err(|e| e.to_string())?;
        let url = settings::get_server_url(db.conn())
            .map_err(|e| e.to_string())?
            .unwrap_or_default();
        let dev_id = settings::get_device_id(db.conn())
            .map_err(|e| e.to_string())?
            .unwrap_or_default();
        let token = state
            .access_token
            .lock()
            .map_err(|e| e.to_string())?
            .clone();
        (url, dev_id, token)
    };

    if server_url.is_empty() {
        return Ok(SyncResult {
            is_online: false,
            renewed_count: 0,
            revoked_count: 0,
            revoked_titles: Vec::new(),
            progress_flushed_count: 0,
            error: Some("Server URL not configured".to_string()),
        });
    }

    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(4))
        .build()
        .map_err(|e| e.to_string())?;

    let health_url = format!("{}/healthz", server_url.trim_end_matches('/'));
    let health_res = client.get(&health_url).send().await;

    let is_online = match health_res {
        Ok(r) if r.status().is_success() => {
            if let Some(date_header) = r.headers().get(reqwest::header::DATE) {
                if let Ok(date_str) = date_header.to_str() {
                    if let Ok(systime) = httpdate::parse_http_date(date_str) {
                        let server_ts = systime
                            .duration_since(std::time::UNIX_EPOCH)
                            .unwrap_or_default()
                            .as_secs() as i64;
                        if let Ok(db) = state.db.lock() {
                            let _ = settings::set_max_seen_timestamp_authoritative(db.conn(), server_ts);
                        }
                    }
                }
            } else {
                let now = std::time::SystemTime::now()
                    .duration_since(std::time::UNIX_EPOCH)
                    .unwrap_or_default()
                    .as_secs() as i64;
                if let Ok(db) = state.db.lock() {
                    let _ = settings::set_max_seen_timestamp_authoritative(db.conn(), now);
                }
            }
            true
        }
        _ => false,
    };

    if !is_online {
        return Ok(SyncResult {
            is_online: false,
            renewed_count: 0,
            revoked_count: 0,
            revoked_titles: Vec::new(),
            progress_flushed_count: 0,
            error: None,
        });
    }

    let token = match access_token {
        Some(t) => t,
        None => {
            return Ok(SyncResult {
                is_online: true,
                renewed_count: 0,
                revoked_count: 0,
                revoked_titles: Vec::new(),
                progress_flushed_count: 0,
                error: Some("Not signed in; cannot sync licenses".to_string()),
            });
        }
    };

    let progress_flushed_count = perform_flush_progress(&state.db, &server_url, &token)
        .await
        .unwrap_or(0);

    if device_id.is_empty() || device_id == "unregistered" {
        return Ok(SyncResult {
            is_online: true,
            renewed_count: 0,
            revoked_count: 0,
            revoked_titles: Vec::new(),
            progress_flushed_count,
            error: Some("Device not registered".to_string()),
        });
    }

    let renew_url = format!(
        "{}/api/v1/offline-licenses/renew",
        server_url.trim_end_matches('/')
    );

    let res = client
        .post(&renew_url)
        .header("Authorization", format!("Bearer {}", token))
        .json(&serde_json::json!({
            "device_id": device_id
        }))
        .send()
        .await;

    let renew_payload: RenewResponsePayload = match res {
        Ok(r) if r.status().is_success() => match r.json().await {
            Ok(p) => p,
            Err(e) => {
                return Ok(SyncResult {
                    is_online: true,
                    renewed_count: 0,
                    revoked_count: 0,
                    revoked_titles: Vec::new(),
                    progress_flushed_count,
                    error: Some(format!("Failed to parse renewal response: {}", e)),
                });
            }
        },
        Ok(r) => {
            return Ok(SyncResult {
                is_online: true,
                renewed_count: 0,
                revoked_count: 0,
                revoked_titles: Vec::new(),
                progress_flushed_count,
                error: Some(format!("Renewal request failed with HTTP {}", r.status())),
            });
        }
        Err(e) => {
            return Ok(SyncResult {
                is_online: true,
                renewed_count: 0,
                revoked_count: 0,
                revoked_titles: Vec::new(),
                progress_flushed_count,
                error: Some(format!("Renewal network error: {}", e)),
            });
        }
    };

    let mut renewed_count = 0;
    let mut revoked_titles = Vec::new();

    {
        let db = state.db.lock().map_err(|e| e.to_string())?;
        let conn = db.conn();

        for item in renew_payload.renewed {
            let res = conn.execute(
                r#"
                UPDATE licenses
                SET token = ?1, expires_at = ?2, revoked_at = NULL
                WHERE lecture_id = ?3
                "#,
                rusqlite::params![item.token, item.expires_at, item.lecture_id],
            );
            if res.is_ok() {
                renewed_count += 1;
            }
        }

        for revoked_id in &renew_payload.revoked {
            let mut title_stmt = conn
                .prepare("SELECT lecture_title FROM downloads WHERE lecture_id = ?1")
                .ok();
            let title: String = title_stmt
                .as_mut()
                .and_then(|s| s.query_row([revoked_id], |r| r.get(0)).ok())
                .unwrap_or_else(|| format!("Lecture {}", revoked_id));

            revoked_titles.push(title);

            let _ = downloader::remove_download_files_and_db(conn, &state.app_data_dir, revoked_id);
            let _ = conn.execute(
                "DELETE FROM progress_queue WHERE lecture_id = ?1",
                rusqlite::params![revoked_id],
            );
        }
    }

    Ok(SyncResult {
        is_online: true,
        renewed_count,
        revoked_count: renew_payload.revoked.len(),
        revoked_titles,
        progress_flushed_count,
        error: None,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::db::Database;
    use std::fs;

    #[test]
    fn test_revoke_and_wipe_on_renew() {
        let db = Database::in_memory().unwrap();
        let conn = db.conn();

        let temp_dir = std::env::temp_dir().join(format!("test_revoke_{}", std::process::id()));
        let bundle_dir = temp_dir.join("bundles").join("lec-revoked");
        fs::create_dir_all(&bundle_dir).unwrap();
        fs::write(bundle_dir.join("media.m3u8.enc"), b"encrypted data").unwrap();

        conn.execute(
            r#"
            INSERT INTO downloads (lecture_id, course_title, lecture_title, rendition, version, path, size_bytes, sha256, status, progress, error, created_at)
            VALUES ('lec-revoked', 'CS101', 'Intro to Algorithms', 480, 1, '/path', 1000, 'hash', 'completed', 1.0, NULL, '2026-10-25')
            "#,
            [],
        ).unwrap();

        conn.execute(
            r#"
            INSERT INTO licenses (lecture_id, device_id, token, bundle_sha256, issued_at, expires_at)
            VALUES ('lec-revoked', 'dev-1', 'tok', 'hash', 'now', 'future')
            "#,
            [],
        ).unwrap();

        conn.execute(
            r#"
            INSERT INTO progress_queue (lecture_id, position_ms, completed, timestamp, attempts)
            VALUES ('lec-revoked', 5000, 0, '2026-10-25', 0)
            "#,
            [],
        ).unwrap();

        // Ensure file exists before wipe
        assert!(bundle_dir.exists());

        // Perform revoke and wipe
        downloader::remove_download_files_and_db(conn, &temp_dir, "lec-revoked").unwrap();
        conn.execute("DELETE FROM progress_queue WHERE lecture_id = 'lec-revoked'", []).unwrap();

        // Assert files removed from disk
        assert!(!bundle_dir.exists());

        // Assert rows removed from DB
        let dl_count: i64 = conn.query_row("SELECT count(*) FROM downloads WHERE lecture_id = 'lec-revoked'", [], |r| r.get(0)).unwrap();
        assert_eq!(dl_count, 0);

        let lic_count: i64 = conn.query_row("SELECT count(*) FROM licenses WHERE lecture_id = 'lec-revoked'", [], |r| r.get(0)).unwrap();
        assert_eq!(lic_count, 0);

        let prog_count: i64 = conn.query_row("SELECT count(*) FROM progress_queue WHERE lecture_id = 'lec-revoked'", [], |r| r.get(0)).unwrap();
        assert_eq!(prog_count, 0);

        let _ = fs::remove_dir_all(&temp_dir);
    }

    #[test]
    fn test_progress_queue_flush_last_write_wins() {
        let db = Database::in_memory().unwrap();
        let conn = db.conn();

        // Insert multiple progress entries for lec-A and lec-B
        conn.execute(
            "INSERT INTO progress_queue (lecture_id, position_ms, completed, timestamp, attempts) VALUES ('lec-A', 1000, 0, '2026-10-25 10:00:00', 0)",
            [],
        ).unwrap();
        conn.execute(
            "INSERT INTO progress_queue (lecture_id, position_ms, completed, timestamp, attempts) VALUES ('lec-A', 5000, 0, '2026-10-25 10:05:00', 0)",
            [],
        ).unwrap();
        conn.execute(
            "INSERT INTO progress_queue (lecture_id, position_ms, completed, timestamp, attempts) VALUES ('lec-A', 25000, 1, '2026-10-25 10:10:00', 0)",
            [],
        ).unwrap();

        conn.execute(
            "INSERT INTO progress_queue (lecture_id, position_ms, completed, timestamp, attempts) VALUES ('lec-B', 3000, 0, '2026-10-25 10:02:00', 0)",
            [],
        ).unwrap();

        // 1. Check last-write-wins selection for lec-A
        let mut stmt = conn.prepare(
            "SELECT id, position_ms, completed FROM progress_queue WHERE lecture_id = ?1 ORDER BY id DESC LIMIT 1"
        ).unwrap();
        let (max_id, pos_ms, comp): (i64, i64, i32) = stmt.query_row(["lec-A"], |r| {
            Ok((r.get(0)?, r.get(1)?, r.get(2)?))
        }).unwrap();

        assert_eq!(pos_ms, 25000);
        assert_eq!(comp, 1);

        // 2. Simulate flush up to max_id:
        conn.execute("DELETE FROM progress_queue WHERE lecture_id = ?1 AND id <= ?2", rusqlite::params!["lec-A", max_id]).unwrap();

        // 3. lec-A is now drained
        let count_a: i64 = conn.query_row("SELECT count(*) FROM progress_queue WHERE lecture_id = 'lec-A'", [], |r| r.get(0)).unwrap();
        assert_eq!(count_a, 0);

        // 4. lec-B is still preserved
        let count_b: i64 = conn.query_row("SELECT count(*) FROM progress_queue WHERE lecture_id = 'lec-B'", [], |r| r.get(0)).unwrap();
        assert_eq!(count_b, 1);
    }
}
