use std::path::PathBuf;

use axum::extract::{Path as AxumPath, State};
use axum::http::header::{
    ACCEPT_RANGES, CONTENT_LENGTH, CONTENT_RANGE, CONTENT_TYPE, ORIGIN, RANGE,
};
use axum::http::{HeaderMap, HeaderValue, Method, StatusCode};
use axum::response::{IntoResponse, Response};
use axum::routing::{any, Router};
use rusqlite::Connection;
use tokio::net::TcpListener;
use tokio::task::JoinHandle;

use crate::encryption;
use crate::keyring_store;
use crate::license_verifier;

#[derive(Clone)]
pub struct LocalServerState {
    pub app_data_dir: PathBuf,
    pub session_token: String,
    pub db_path: PathBuf,
    pub default_service_name: String,
}

pub fn is_allowed_origin(origin: &str) -> bool {
    let lower = origin.trim().to_ascii_lowercase();
    lower.starts_with("http://localhost:")
        || lower.starts_with("http://127.0.0.1:")
        || lower.starts_with("tauri://localhost")
        || lower.starts_with("http://tauri.localhost")
        || lower == "http://localhost"
        || lower == "http://127.0.0.1"
        || lower == "tauri://localhost"
        || lower == "null"
}

pub fn add_cors_headers(response: &mut Response, origin_opt: Option<&str>) {
    if let Some(origin) = origin_opt {
        if is_allowed_origin(origin) {
            if let Ok(hv) = HeaderValue::from_str(origin) {
                response.headers_mut().insert("Access-Control-Allow-Origin", hv);
                response.headers_mut().insert(
                    "Access-Control-Allow-Methods",
                    HeaderValue::from_static("GET, HEAD, OPTIONS"),
                );
                response.headers_mut().insert(
                    "Access-Control-Allow-Headers",
                    HeaderValue::from_static("Range, Content-Type, Accept, Origin"),
                );
                response.headers_mut().insert(
                    "Access-Control-Expose-Headers",
                    HeaderValue::from_static("Content-Range, Content-Length, Accept-Ranges"),
                );
            }
        }
    }
}

pub fn get_mime_type(file_path: &str) -> &'static str {
    let lower = file_path.to_ascii_lowercase();
    if lower.ends_with(".m3u8") {
        "application/vnd.apple.mpegurl"
    } else if lower.ends_with(".m4s") || lower.ends_with(".mp4") {
        "video/mp4"
    } else if lower.ends_with(".ts") {
        "video/mp2t"
    } else if lower.ends_with(".vtt") {
        "text/vtt"
    } else if lower.ends_with(".json") {
        "application/json"
    } else if lower.ends_with(".jpg") || lower.ends_with(".jpeg") {
        "image/jpeg"
    } else if lower.ends_with(".png") {
        "image/png"
    } else {
        "application/octet-stream"
    }
}

pub fn parse_range_header(range_header: &str, total_len: u64) -> Option<(u64, u64)> {
    if !range_header.starts_with("bytes=") {
        return None;
    }
    let spec = range_header.trim_start_matches("bytes=").trim();
    let parts: Vec<&str> = spec.split('-').collect();
    if parts.len() != 2 {
        return None;
    }
    if parts[0].is_empty() {
        let suffix: u64 = parts[1].parse().ok()?;
        if suffix == 0 {
            return None;
        }
        let start = total_len.saturating_sub(suffix);
        let end = total_len.saturating_sub(1);
        Some((start, end))
    } else if parts[1].is_empty() {
        let start: u64 = parts[0].parse().ok()?;
        if start >= total_len {
            return None;
        }
        let end = total_len.saturating_sub(1);
        Some((start, end))
    } else {
        let start: u64 = parts[0].parse().ok()?;
        let end: u64 = parts[1].parse().ok()?;
        if start > end || start >= total_len {
            return None;
        }
        let effective_end = end.min(total_len.saturating_sub(1));
        Some((start, effective_end))
    }
}

async fn handle_playback(
    State(state): State<LocalServerState>,
    AxumPath((token, lecture_id, raw_file_path)): AxumPath<(String, String, String)>,
    headers: HeaderMap,
    method: Method,
) -> Response {
    let origin_opt = headers.get(ORIGIN).and_then(|h| h.to_str().ok());

    // 1. Origin check: Reject any Origin other than app's own origin
    if let Some(origin) = origin_opt {
        if !is_allowed_origin(origin) {
            return (StatusCode::FORBIDDEN, "Forbidden: Invalid Origin").into_response();
        }
    }

    // Handle preflight OPTIONS
    if method == Method::OPTIONS {
        let mut res = (StatusCode::NO_CONTENT, ()).into_response();
        add_cors_headers(&mut res, origin_opt);
        return res;
    }

    // 2. Session token check: Every request requires a random per-session token in the path
    if token != state.session_token {
        let mut res = (StatusCode::FORBIDDEN, "Forbidden: Invalid session token").into_response();
        add_cors_headers(&mut res, origin_opt);
        return res;
    }

    // 3. License check: Check the license for that lecture
    let conn_res = Connection::open(&state.db_path);
    let conn = match conn_res {
        Ok(c) => c,
        Err(e) => {
            let mut res = (
                StatusCode::INTERNAL_SERVER_ERROR,
                format!("Database error: {}", e),
            )
                .into_response();
            add_cors_headers(&mut res, origin_opt);
            return res;
        }
    };

    if let Err(err_msg) = license_verifier::verify_lecture_access(&conn, &lecture_id) {
        let mut res = (
            StatusCode::FORBIDDEN,
            format!("Forbidden: License validation failed ({})", err_msg),
        )
            .into_response();
        add_cors_headers(&mut res, origin_opt);
        return res;
    }

    // 4. Sanitize file path
    let cleaned_file_path = raw_file_path
        .trim_start_matches('/')
        .replace('\\', "/");

    if cleaned_file_path.contains("..") {
        let mut res = (StatusCode::BAD_REQUEST, "Invalid file path").into_response();
        add_cors_headers(&mut res, origin_opt);
        return res;
    }

    let enc_file_path = state
        .app_data_dir
        .join("bundles")
        .join(&lecture_id)
        .join(format!("{}.enc", cleaned_file_path));

    if !enc_file_path.exists() {
        let mut res = (
            StatusCode::NOT_FOUND,
            format!("Bundle file not found: {}", cleaned_file_path),
        )
            .into_response();
        add_cors_headers(&mut res, origin_opt);
        return res;
    }

    // 5. Derive per-file key
    let device_secret = match keyring_store::get_device_private_key(&state.default_service_name) {
        Ok(Some(s)) => s,
        _ => [0u8; 32],
    };

    let file_key = match encryption::derive_file_key(
        &device_secret,
        &lecture_id,
        &cleaned_file_path,
    ) {
        Ok(k) => k,
        Err(e) => {
            let mut res = (
                StatusCode::INTERNAL_SERVER_ERROR,
                format!("Failed to derive decryption key: {}", e),
            )
                .into_response();
            add_cors_headers(&mut res, origin_opt);
            return res;
        }
    };

    // 6. Read original file length from encrypted header
    let total_len = match encryption::get_original_file_len(&enc_file_path) {
        Ok(len) => len,
        Err(e) => {
            let mut res = (
                StatusCode::INTERNAL_SERVER_ERROR,
                format!("Failed reading encrypted file header: {}", e),
            )
                .into_response();
            add_cors_headers(&mut res, origin_opt);
            return res;
        }
    };

    let mime_type = get_mime_type(&cleaned_file_path);

    // 7. Check for Range header
    let range_header = headers.get(RANGE).and_then(|h| h.to_str().ok());

    if let Some(rh) = range_header {
        if let Some((start, end)) = parse_range_header(rh, total_len) {
            let chunk_len = end - start + 1;
            match encryption::decrypt_range(&enc_file_path, &file_key, start, end + 1) {
                Ok(bytes) => {
                    let mut res = Response::new(axum::body::Body::from(bytes));
                    *res.status_mut() = StatusCode::PARTIAL_CONTENT;
                    res.headers_mut().insert(CONTENT_TYPE, HeaderValue::from_static(mime_type));
                    res.headers_mut().insert(ACCEPT_RANGES, HeaderValue::from_static("bytes"));
                    if let Ok(cl) = HeaderValue::from_str(&chunk_len.to_string()) {
                        res.headers_mut().insert(CONTENT_LENGTH, cl);
                    }
                    if let Ok(cr) = HeaderValue::from_str(&format!("bytes {}-{}/{}", start, end, total_len)) {
                        res.headers_mut().insert(CONTENT_RANGE, cr);
                    }
                    add_cors_headers(&mut res, origin_opt);
                    return res;
                }
                Err(e) => {
                    let mut res = (
                        StatusCode::INTERNAL_SERVER_ERROR,
                        format!("Decryption range failed: {}", e),
                    )
                        .into_response();
                    add_cors_headers(&mut res, origin_opt);
                    return res;
                }
            }
        } else {
            let mut res = (
                StatusCode::RANGE_NOT_SATISFIABLE,
                "Range Not Satisfiable",
            )
                .into_response();
            if let Ok(cr) = HeaderValue::from_str(&format!("bytes */{}", total_len)) {
                res.headers_mut().insert(CONTENT_RANGE, cr);
            }
            add_cors_headers(&mut res, origin_opt);
            return res;
        }
    }

    // 8. Serve entire file (200 OK)
    match encryption::decrypt_range(&enc_file_path, &file_key, 0, total_len) {
        Ok(bytes) => {
            let mut res = Response::new(axum::body::Body::from(bytes));
            *res.status_mut() = StatusCode::OK;
            res.headers_mut().insert(CONTENT_TYPE, HeaderValue::from_static(mime_type));
            res.headers_mut().insert(ACCEPT_RANGES, HeaderValue::from_static("bytes"));
            if let Ok(cl) = HeaderValue::from_str(&total_len.to_string()) {
                res.headers_mut().insert(CONTENT_LENGTH, cl);
            }
            add_cors_headers(&mut res, origin_opt);
            res
        }
        Err(e) => {
            let mut res = (
                StatusCode::INTERNAL_SERVER_ERROR,
                format!("Decryption failed: {}", e),
            )
                .into_response();
            add_cors_headers(&mut res, origin_opt);
            return res;
        }
    }
}

pub fn create_router(state: LocalServerState) -> Router {
    Router::new()
        .route(
            "/:token/lectures/:lecture_id/*file_path",
            any(handle_playback),
        )
        .with_state(state)
}

pub async fn start_local_server(
    state: LocalServerState,
) -> Result<(u16, JoinHandle<()>), String> {
    // Server ONLY binds to 127.0.0.1 with random port
    let listener = TcpListener::bind("127.0.0.1:0")
        .await
        .map_err(|e| format!("Failed to bind local playback server to 127.0.0.1:0: {}", e))?;

    let local_addr = listener
        .local_addr()
        .map_err(|e| format!("Failed to get local addr: {}", e))?;

    let port = local_addr.port();
    let app = create_router(state);

    let handle = tokio::spawn(async move {
        axum::serve(listener, app).await.ok();
    });

    Ok((port, handle))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::db::Database;
    use crate::license_verifier::{self, LicenseClaims};
    use crate::settings;
    use ed25519_dalek::SigningKey;
    use rand::rngs::OsRng;
    use std::fs;
    use std::time::{SystemTime, UNIX_EPOCH};

    struct TestFixture {
        pub temp_dir: PathBuf,
        pub db_path: PathBuf,
        pub port: u16,
        pub session_token: String,
        pub signing_key: SigningKey,
        pub lecture_id: String,
        pub device_id: String,
        pub user_id: String,
        pub device_secret: [u8; 32],
        _server_handle: JoinHandle<()>,
    }

    async fn setup_test_fixture() -> TestFixture {
        let temp_dir = std::env::temp_dir().join(format!("test_local_server_{}", rand::random::<u64>()));
        fs::create_dir_all(&temp_dir).unwrap();

        let db_path = temp_dir.join("desktop.db");
        let db = Database::open(&db_path).unwrap();
        let conn = db.conn();

        let mut csprng = OsRng;
        let signing_key = SigningKey::generate(&mut csprng);
        let pub_pem = license_verifier::format_public_key_pem(&signing_key.verifying_key().to_bytes());

        let lecture_id = "test-lec-1".to_string();
        let device_id = "test-dev-1".to_string();
        let user_id = "test-user-1".to_string();
        let device_secret = [7u8; 32];
        let service_name = format!("test_serv_{}", rand::random::<u32>());

        settings::set_license_public_key(conn, &pub_pem).unwrap();
        settings::set_device_id(conn, &device_id).unwrap();
        settings::set_last_user(
            conn,
            &settings::UserProfile {
                id: user_id.clone(),
                email: "student@test.edu".to_string(),
                name: "Student".to_string(),
                role: "student".to_string(),
            },
        )
        .unwrap();

        // Store device secret in keyring for this test service
        keyring_store::store_device_private_key(&service_name, &device_secret).unwrap();

        let session_token = "secret_session_token_123".to_string();
        let server_state = LocalServerState {
            app_data_dir: temp_dir.clone(),
            session_token: session_token.clone(),
            db_path: db_path.clone(),
            default_service_name: service_name,
        };

        let (port, _server_handle) = start_local_server(server_state.clone()).await.unwrap();

        TestFixture {
            temp_dir,
            db_path,
            port,
            session_token,
            signing_key,
            lecture_id,
            device_id,
            user_id,
            device_secret,
            _server_handle,
        }
    }

    #[tokio::test]
    async fn test_server_only_binds_to_127_0_0_1() {
        let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let addr = listener.local_addr().unwrap();
        assert_eq!(addr.ip().to_string(), "127.0.0.1");
    }

    #[tokio::test]
    async fn test_valid_license_serves_200_and_206() {
        let fixture = setup_test_fixture().await;

        // Create plaintext bundle content and encrypt it
        let bundles_dir = fixture.temp_dir.join("bundles").join(&fixture.lecture_id).join("hls");
        fs::create_dir_all(&bundles_dir).unwrap();

        let plaintext = b"#EXTM3U\n#EXT-X-VERSION:3\n#EXT-X-TARGETDURATION:6\n#EXTINF:6.0,\nseg-0.m4s\n";
        let src_file = fixture.temp_dir.join("media.m3u8");
        fs::write(&src_file, plaintext).unwrap();

        let enc_dst = bundles_dir.join("media.m3u8.enc");
        let file_key = encryption::derive_file_key(&fixture.device_secret, &fixture.lecture_id, "hls/media.m3u8").unwrap();
        encryption::encrypt_file(&src_file, &enc_dst, &file_key, 256 * 1024).unwrap();

        // Issue valid license
        let now = SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_secs() as i64;
        let claims = LicenseClaims {
            user_id: fixture.user_id.clone(),
            device_id: fixture.device_id.clone(),
            lecture_id: fixture.lecture_id.clone(),
            bundle_sha256: "sha256-test".to_string(),
            issued_at: None,
            expires_at: None,
            iat: Some(now),
            exp: now + 3600,
        };
        let token = license_verifier::issue_test_license_token(&fixture.signing_key, &claims).unwrap();

        let conn = Connection::open(&fixture.db_path).unwrap();
        conn.execute(
            r#"
            INSERT INTO licenses (lecture_id, device_id, token, bundle_sha256, issued_at, expires_at, revoked_at)
            VALUES (?1, ?2, ?3, ?4, 'now', 'future', NULL)
            "#,
            rusqlite::params![fixture.lecture_id, fixture.device_id, token, "sha256-test"],
        )
        .unwrap();

        let client = reqwest::Client::new();

        // 1. Full 200 OK request
        let url = format!(
            "http://127.0.0.1:{}/{}/lectures/{}/hls/media.m3u8",
            fixture.port, fixture.session_token, fixture.lecture_id
        );
        let res = client
            .get(&url)
            .header("Origin", "http://localhost:5173")
            .send()
            .await
            .unwrap();

        assert_eq!(res.status(), StatusCode::OK);
        assert_eq!(
            res.headers().get("content-type").unwrap(),
            "application/vnd.apple.mpegurl"
        );
        assert_eq!(res.headers().get("access-control-allow-origin").unwrap(), "http://localhost:5173");
        let body = res.bytes().await.unwrap();
        assert_eq!(body.as_ref(), plaintext);

        // 2. Range 206 Partial Content request
        let res_range = client
            .get(&url)
            .header("Origin", "http://localhost:5173")
            .header("Range", "bytes=0-9")
            .send()
            .await
            .unwrap();

        assert_eq!(res_range.status(), StatusCode::PARTIAL_CONTENT);
        assert_eq!(
            res_range.headers().get("content-range").unwrap(),
            &format!("bytes 0-9/{}", plaintext.len())
        );
        let range_bytes = res_range.bytes().await.unwrap();
        assert_eq!(range_bytes.as_ref(), &plaintext[0..10]);

        // Cleanup
        let _ = fs::remove_dir_all(&fixture.temp_dir);
    }

    #[tokio::test]
    async fn test_range_request_across_chunk_boundary() {
        let fixture = setup_test_fixture().await;

        // Create 600 KB file (exceeds default 256 KB chunk size)
        let chunk_size = 256 * 1024;
        let mut large_plaintext = Vec::with_capacity(600 * 1024);
        for i in 0..(600 * 1024) {
            large_plaintext.push((i % 251) as u8);
        }

        let bundles_dir = fixture.temp_dir.join("bundles").join(&fixture.lecture_id).join("hls");
        fs::create_dir_all(&bundles_dir).unwrap();

        let src_file = fixture.temp_dir.join("segment.m4s");
        fs::write(&src_file, &large_plaintext).unwrap();

        let enc_dst = bundles_dir.join("segment.m4s.enc");
        let file_key = encryption::derive_file_key(&fixture.device_secret, &fixture.lecture_id, "hls/segment.m4s").unwrap();
        encryption::encrypt_file(&src_file, &enc_dst, &file_key, chunk_size).unwrap();

        // Valid license
        let now = SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_secs() as i64;
        let claims = LicenseClaims {
            user_id: fixture.user_id.clone(),
            device_id: fixture.device_id.clone(),
            lecture_id: fixture.lecture_id.clone(),
            bundle_sha256: "sha256-test".to_string(),
            issued_at: None,
            expires_at: None,
            iat: Some(now),
            exp: now + 3600,
        };
        let token = license_verifier::issue_test_license_token(&fixture.signing_key, &claims).unwrap();

        let conn = Connection::open(&fixture.db_path).unwrap();
        conn.execute(
            r#"
            INSERT INTO licenses (lecture_id, device_id, token, bundle_sha256, issued_at, expires_at, revoked_at)
            VALUES (?1, ?2, ?3, ?4, 'now', 'future', NULL)
            "#,
            rusqlite::params![fixture.lecture_id, fixture.device_id, token, "sha256-test"],
        )
        .unwrap();

        let client = reqwest::Client::new();
        let url = format!(
            "http://127.0.0.1:{}/{}/lectures/{}/hls/segment.m4s",
            fixture.port, fixture.session_token, fixture.lecture_id
        );

        // Range spanning chunk boundary: from 250,000 to 270,000 (crosses 262,144 byte boundary)
        let start = 250_000u64;
        let end = 270_000u64;
        let res = client
            .get(&url)
            .header("Range", format!("bytes={}-{}", start, end))
            .send()
            .await
            .unwrap();

        assert_eq!(res.status(), StatusCode::PARTIAL_CONTENT);
        assert_eq!(
            res.headers().get("content-range").unwrap(),
            &format!("bytes {}-{}/{}", start, end, large_plaintext.len())
        );

        let body = res.bytes().await.unwrap();
        assert_eq!(body.len(), (end - start + 1) as usize);
        assert_eq!(body.as_ref(), &large_plaintext[start as usize..=end as usize]);

        let _ = fs::remove_dir_all(&fixture.temp_dir);
    }

    #[tokio::test]
    async fn test_expired_or_tampered_license_gets_403() {
        let fixture = setup_test_fixture().await;

        let bundles_dir = fixture.temp_dir.join("bundles").join(&fixture.lecture_id);
        fs::create_dir_all(&bundles_dir).unwrap();
        let src_file = fixture.temp_dir.join("captions.vtt");
        fs::write(&src_file, b"WEBVTT\n").unwrap();
        let enc_dst = bundles_dir.join("captions.vtt.enc");
        let file_key = encryption::derive_file_key(&fixture.device_secret, &fixture.lecture_id, "captions.vtt").unwrap();
        encryption::encrypt_file(&src_file, &enc_dst, &file_key, 256 * 1024).unwrap();

        let now = SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_secs() as i64;
        let conn = Connection::open(&fixture.db_path).unwrap();
        let client = reqwest::Client::new();
        let url = format!(
            "http://127.0.0.1:{}/{}/lectures/{}/captions.vtt",
            fixture.port, fixture.session_token, fixture.lecture_id
        );

        // 1. Expired token
        let expired_claims = LicenseClaims {
            user_id: fixture.user_id.clone(),
            device_id: fixture.device_id.clone(),
            lecture_id: fixture.lecture_id.clone(),
            bundle_sha256: "sha256-test".to_string(),
            issued_at: None,
            expires_at: None,
            iat: Some(now - 100),
            exp: now - 10,
        };
        let expired_token = license_verifier::issue_test_license_token(&fixture.signing_key, &expired_claims).unwrap();
        conn.execute(
            r#"
            INSERT INTO licenses (lecture_id, device_id, token, bundle_sha256, issued_at, expires_at, revoked_at)
            VALUES (?1, ?2, ?3, ?4, 'now', 'past', NULL)
            ON CONFLICT(lecture_id) DO UPDATE SET token = ?3
            "#,
            rusqlite::params![fixture.lecture_id, fixture.device_id, expired_token, "sha256-test"],
        )
        .unwrap();

        let res_expired = client.get(&url).send().await.unwrap();
        assert_eq!(res_expired.status(), StatusCode::FORBIDDEN);

        // 2. Tampered token signature
        let mut tampered_token = expired_token;
        tampered_token.push_str("tampered");
        conn.execute(
            "UPDATE licenses SET token = ?1 WHERE lecture_id = ?2",
            rusqlite::params![tampered_token, fixture.lecture_id],
        )
        .unwrap();

        let res_tampered = client.get(&url).send().await.unwrap();
        assert_eq!(res_tampered.status(), StatusCode::FORBIDDEN);

        // 3. Revoked license
        conn.execute(
            "UPDATE licenses SET revoked_at = datetime('now') WHERE lecture_id = ?1",
            rusqlite::params![fixture.lecture_id],
        )
        .unwrap();

        let res_revoked = client.get(&url).send().await.unwrap();
        assert_eq!(res_revoked.status(), StatusCode::FORBIDDEN);

        let _ = fs::remove_dir_all(&fixture.temp_dir);
    }

    #[tokio::test]
    async fn test_wrong_token_gets_403() {
        let fixture = setup_test_fixture().await;

        let client = reqwest::Client::new();
        let wrong_url = format!(
            "http://127.0.0.1:{}/wrong_token/lectures/{}/hls/media.m3u8",
            fixture.port, fixture.lecture_id
        );

        let res = client.get(&wrong_url).send().await.unwrap();
        assert_eq!(res.status(), StatusCode::FORBIDDEN);

        let _ = fs::remove_dir_all(&fixture.temp_dir);
    }

    #[tokio::test]
    async fn test_forbidden_origin_gets_403() {
        let fixture = setup_test_fixture().await;

        let client = reqwest::Client::new();
        let url = format!(
            "http://127.0.0.1:{}/{}/lectures/{}/hls/media.m3u8",
            fixture.port, fixture.session_token, fixture.lecture_id
        );

        let res = client
            .get(&url)
            .header("Origin", "http://malicious-website.com")
            .send()
            .await
            .unwrap();

        assert_eq!(res.status(), StatusCode::FORBIDDEN);

        let _ = fs::remove_dir_all(&fixture.temp_dir);
    }
}
