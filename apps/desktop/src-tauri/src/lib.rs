pub mod auth;
pub mod commands;
pub mod db;
pub mod device;
pub mod downloader;
pub mod encryption;
pub mod keyring_store;
pub mod license_verifier;
pub mod local_server;
pub mod settings;

use tauri::Manager;

pub fn run() {
    tauri::Builder::default()
        .setup(|app| {
            let app_data_dir = app
                .path()
                .app_data_dir()
                .unwrap_or_else(|_| {
                    dirs::data_local_dir()
                        .unwrap_or_else(|| std::path::PathBuf::from("."))
                        .join("com.university.lectureplatform")
                });
            let _ = std::fs::create_dir_all(&app_data_dir);
            let db_path = app_data_dir.join("desktop.db");
            let db = db::Database::open(&db_path)
                .expect("Failed to initialize SQLite database");

            let session_token = hex::encode(rand::random::<[u8; 16]>());
            let server_state = local_server::LocalServerState {
                app_data_dir: app_data_dir.clone(),
                session_token: session_token.clone(),
                db_path: db_path.clone(),
                default_service_name: keyring_store::DEFAULT_SERVICE_NAME.to_string(),
            };

            let (local_server_port, _server_handle) = tauri::async_runtime::block_on(async {
                local_server::start_local_server(server_state).await
            })
            .expect("Failed to start local playback server on 127.0.0.1:0");

            app.manage(commands::AppState {
                db: std::sync::Mutex::new(db),
                app_data_dir,
                access_token: std::sync::Mutex::new(None),
                active_downloads: std::sync::Mutex::new(std::collections::HashMap::new()),
                local_server_port,
                session_token,
            });
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            commands::validate_and_set_server_url,
            commands::get_desktop_state,
            commands::desktop_login,
            commands::desktop_logout,
            commands::get_enrolled_courses_and_lectures,
            commands::get_offline_estimate,
            commands::start_download,
            commands::pause_download,
            commands::resume_download,
            commands::cancel_download,
            commands::list_downloads,
            commands::delete_download,
            commands::storage_usage,
            commands::get_desktop_settings,
            commands::update_desktop_settings,
            commands::get_local_server_info,
            commands::get_offline_playback_info,
            commands::save_offline_progress,
            commands::get_offline_progress,
            commands::check_connectivity,
            commands::sync_offline_licenses,
            commands::desktop_offline_login,
            commands::flush_progress_queue,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
