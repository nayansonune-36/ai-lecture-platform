use std::path::PathBuf;
use std::sync::Mutex;
use tauri::State;
use serde::{Deserialize, Serialize};

use crate::auth::{self, LoginResult};
use crate::db::Database;
use crate::device::{self, DeviceInfo};
use crate::settings::{self, UserProfile};

pub struct AppState {
    pub db: Mutex<Database>,
    pub app_data_dir: PathBuf,
    pub access_token: Mutex<Option<String>>,
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
pub struct DownloadedLecture {
    pub lecture_id: String,
    pub course_title: String,
    pub lecture_title: String,
    pub rendition: i32,
    pub size_bytes: i64,
    pub status: String,
    pub completed_at: Option<String>,
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
    // 1. Read server_url from DB (lock released before await)
    let server_url = {
        let db = state.db.lock().map_err(|e| e.to_string())?;
        settings::get_server_url(db.conn())
            .map_err(|e| e.to_string())?
            .ok_or_else(|| "Server URL has not been configured".to_string())?
    };

    // 2. Perform network login + GET /me (no DB lock held across await)
    let auth_res = auth::execute_login_network(&server_url, &email, &password).await?;

    // Store access token in memory in Rust (never sent to JS)
    {
        let mut token_guard = state.access_token.lock().map_err(|e| e.to_string())?;
        *token_guard = Some(auth_res.access_token.clone());
    }

    // 3. Save user profile and get device identity
    let (identity, existing_device_id) = {
        let db = state.db.lock().map_err(|e| e.to_string())?;
        let _ = settings::set_last_user(db.conn(), &auth_res.user);
        let id_info = device::get_or_create_device_identity(db.conn())?;
        let dev_id = settings::get_device_id(db.conn()).map_err(|e| e.to_string())?;
        (id_info, dev_id)
    };

    // 4. Register device if needed (lock released before await)
    let device_id = match existing_device_id {
        Some(id) => id,
        None => {
            match device::register_device_network(
                &server_url,
                &auth_res.access_token,
                &identity.name,
                &identity.public_key,
            ).await {
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
pub fn desktop_logout(state: State<'_, AppState>) -> Result<(), String> {
    if let Ok(mut guard) = state.access_token.lock() {
        *guard = None;
    }
    auth::execute_logout()
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
        let token = state.access_token.lock().map_err(|e| e.to_string())?
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
pub fn get_downloaded_lectures(
    state: State<'_, AppState>,
) -> Result<Vec<DownloadedLecture>, String> {
    let db = state.db.lock().map_err(|e| e.to_string())?;
    let conn = db.conn();

    let mut stmt = conn
        .prepare(
            "SELECT lecture_id, course_title, lecture_title, rendition, size_bytes, status, completed_at
             FROM downloads WHERE status = 'completed' ORDER BY completed_at DESC",
        )
        .map_err(|e| e.to_string())?;

    let rows = stmt
        .query_map([], |row| {
            Ok(DownloadedLecture {
                lecture_id: row.get(0)?,
                course_title: row.get(1)?,
                lecture_title: row.get(2)?,
                rendition: row.get(3)?,
                size_bytes: row.get(4)?,
                status: row.get(5)?,
                completed_at: row.get(6)?,
            })
        })
        .map_err(|e| e.to_string())?;

    let mut result = Vec::new();
    for r in rows {
        if let Ok(item) = r {
            result.push(item);
        }
    }

    Ok(result)
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
pub fn get_desktop_settings(
    state: State<'_, AppState>,
) -> Result<DesktopSettingsInfo, String> {
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
    get_desktop_settings(state)
}
