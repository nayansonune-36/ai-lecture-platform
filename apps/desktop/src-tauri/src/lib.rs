pub mod auth;
pub mod commands;
pub mod db;
pub mod device;
pub mod keyring_store;
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

            app.manage(commands::AppState {
                db: std::sync::Mutex::new(db),
                app_data_dir,
                access_token: std::sync::Mutex::new(None),
            });
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            commands::validate_and_set_server_url,
            commands::get_desktop_state,
            commands::desktop_login,
            commands::desktop_logout,
            commands::get_enrolled_courses_and_lectures,
            commands::get_downloaded_lectures,
            commands::get_desktop_settings,
            commands::update_desktop_settings,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
