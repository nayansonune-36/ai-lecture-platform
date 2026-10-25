use rusqlite::{Connection, Result};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct UserProfile {
    pub id: String,
    pub email: String,
    pub name: String,
    pub role: String,
}

pub fn get_setting(conn: &Connection, key: &str) -> Result<Option<String>> {
    let mut stmt = conn.prepare("SELECT value FROM settings WHERE key = ?1")?;
    let mut rows = stmt.query([key])?;
    if let Some(row) = rows.next()? {
        Ok(Some(row.get(0)?))
    } else {
        Ok(None)
    }
}

pub fn set_setting(conn: &Connection, key: &str, value: &str) -> Result<()> {
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?1, ?2) ON CONFLICT(key) DO UPDATE SET value = ?2",
        [key, value],
    )?;
    Ok(())
}

pub fn delete_setting(conn: &Connection, key: &str) -> Result<()> {
    conn.execute("DELETE FROM settings WHERE key = ?1", [key])?;
    Ok(())
}

pub fn get_server_url(conn: &Connection) -> Result<Option<String>> {
    get_setting(conn, "server_url")
}

pub fn set_server_url(conn: &Connection, url: &str) -> Result<()> {
    let cleaned = url.trim().trim_end_matches('/');
    set_setting(conn, "server_url", cleaned)
}

pub fn get_device_id(conn: &Connection) -> Result<Option<String>> {
    get_setting(conn, "device_id")
}

pub fn set_device_id(conn: &Connection, id: &str) -> Result<()> {
    set_setting(conn, "device_id", id)
}

pub fn get_device_name(conn: &Connection) -> Result<Option<String>> {
    get_setting(conn, "device_name")
}

pub fn set_device_name(conn: &Connection, name: &str) -> Result<()> {
    set_setting(conn, "device_name", name)
}

pub fn get_device_public_key(conn: &Connection) -> Result<Option<String>> {
    get_setting(conn, "device_public_key")
}

pub fn set_device_public_key(conn: &Connection, key: &str) -> Result<()> {
    set_setting(conn, "device_public_key", key)
}

pub fn get_license_public_key(conn: &Connection) -> Result<Option<String>> {
    get_setting(conn, "license_public_key")
}

pub fn set_license_public_key(conn: &Connection, key_pem: &str) -> Result<()> {
    set_setting(conn, "license_public_key", key_pem)
}

pub fn get_last_user(conn: &Connection) -> Result<Option<UserProfile>> {
    if let Some(json_str) = get_setting(conn, "last_user")? {
        if let Ok(user) = serde_json::from_str::<UserProfile>(&json_str) {
            return Ok(Some(user));
        }
    }
    Ok(None)
}

pub fn set_last_user(conn: &Connection, user: &UserProfile) -> Result<()> {
    let json_str = serde_json::to_string(user).unwrap_or_default();
    set_setting(conn, "last_user", &json_str)
}

pub fn clear_last_user(conn: &Connection) -> Result<()> {
    delete_setting(conn, "last_user")
}

pub fn get_max_seen_timestamp(conn: &Connection) -> Result<Option<i64>> {
    if let Some(val) = get_setting(conn, "max_seen_timestamp")? {
        if let Ok(ts) = val.parse::<i64>() {
            return Ok(Some(ts));
        }
    }
    Ok(None)
}

pub fn update_max_seen_timestamp(conn: &Connection, timestamp: i64) -> Result<()> {
    let current_max = get_max_seen_timestamp(conn)?.unwrap_or(0);
    if timestamp > current_max {
        set_setting(conn, "max_seen_timestamp", &timestamp.to_string())?;
    }
    Ok(())
}

pub fn set_max_seen_timestamp_authoritative(conn: &Connection, timestamp: i64) -> Result<()> {
    set_setting(conn, "max_seen_timestamp", &timestamp.to_string())
}

pub fn check_clock_rollback(conn: &Connection) -> Result<bool> {
    let now = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs() as i64;

    if let Some(max_seen) = get_max_seen_timestamp(conn)? {
        if now < max_seen {
            return Ok(true);
        }
    }
    let _ = update_max_seen_timestamp(conn, now);
    Ok(false)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::db::Database;

    #[test]
    fn test_clock_rollback_protection() {
        let db = Database::in_memory().unwrap();
        let conn = db.conn();

        let now = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap_or_default()
            .as_secs() as i64;

        // 1. Initial state: no rollback
        assert_eq!(check_clock_rollback(conn).unwrap(), false);
        let max_seen = get_max_seen_timestamp(conn).unwrap().unwrap();
        assert!(max_seen >= now);

        // 2. Setting a higher future timestamp simulates advancing the clock
        let future_time = now + 100_000;
        set_max_seen_timestamp_authoritative(conn, future_time).unwrap();
        assert_eq!(get_max_seen_timestamp(conn).unwrap(), Some(future_time));

        // 3. Now checking rollback detects that current system clock (now) < future_time
        assert_eq!(check_clock_rollback(conn).unwrap(), true);

        // 4. Server sync provides authoritative current timestamp, resetting the lock
        set_max_seen_timestamp_authoritative(conn, now).unwrap();
        assert_eq!(check_clock_rollback(conn).unwrap(), false);
    }

    #[test]
    fn test_settings_crud() {
        let db = Database::in_memory().unwrap();
        let conn = db.conn();

        assert_eq!(get_setting(conn, "server_url").unwrap(), None);

        set_server_url(conn, "http://localhost:8080/").unwrap();
        assert_eq!(
            get_server_url(conn).unwrap(),
            Some("http://localhost:8080".to_string())
        );

        set_device_id(conn, "dev-uuid-1234").unwrap();
        assert_eq!(
            get_device_id(conn).unwrap(),
            Some("dev-uuid-1234".to_string())
        );

        let user = UserProfile {
            id: "u-123".to_string(),
            email: "student@test.local".to_string(),
            name: "Test Student".to_string(),
            role: "student".to_string(),
        };
        set_last_user(conn, &user).unwrap();
        assert_eq!(get_last_user(conn).unwrap(), Some(user));

        clear_last_user(conn).unwrap();
        assert_eq!(get_last_user(conn).unwrap(), None);
    }
}
