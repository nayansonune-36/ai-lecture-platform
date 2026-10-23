use rusqlite::{Connection, Result};
use std::path::Path;

pub struct Database {
    conn: Connection,
}

impl Database {
    pub fn new(conn: Connection) -> Result<Self> {
        let mut db = Self { conn };
        db.migrate()?;
        Ok(db)
    }

    pub fn open<P: AsRef<Path>>(path: P) -> Result<Self> {
        if let Some(parent) = path.as_ref().parent() {
            let _ = std::fs::create_dir_all(parent);
        }
        let conn = Connection::open(path)?;
        Self::new(conn)
    }

    pub fn in_memory() -> Result<Self> {
        let conn = Connection::open_in_memory()?;
        Self::new(conn)
    }

    pub fn conn(&self) -> &Connection {
        &self.conn
    }

    pub fn conn_mut(&mut self) -> &mut Connection {
        &mut self.conn
    }

    pub fn migrate(&mut self) -> Result<()> {
        self.conn.execute_batch(
            r#"
            CREATE TABLE IF NOT EXISTS migrations (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL
            );

            -- 1. settings table
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            -- 2. downloads table
            CREATE TABLE IF NOT EXISTS downloads (
                lecture_id TEXT PRIMARY KEY,
                course_title TEXT NOT NULL,
                lecture_title TEXT NOT NULL,
                rendition INTEGER NOT NULL,
                version INTEGER NOT NULL DEFAULT 1,
                path TEXT,
                size_bytes INTEGER NOT NULL,
                sha256 TEXT NOT NULL,
                status TEXT NOT NULL,
                progress REAL NOT NULL DEFAULT 0.0,
                error TEXT,
                created_at TEXT NOT NULL,
                completed_at TEXT
            );

            -- 3. licenses table
            CREATE TABLE IF NOT EXISTS licenses (
                lecture_id TEXT PRIMARY KEY,
                device_id TEXT NOT NULL,
                token TEXT NOT NULL,
                bundle_sha256 TEXT NOT NULL,
                issued_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                revoked_at TEXT
            );

            -- 4. progress_queue table
            CREATE TABLE IF NOT EXISTS progress_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lecture_id TEXT NOT NULL,
                position_ms INTEGER NOT NULL,
                completed INTEGER NOT NULL DEFAULT 0,
                timestamp TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0
            );

            INSERT OR IGNORE INTO migrations (version, applied_at)
            VALUES (1, datetime('now'));
            "#,
        )?;
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_database_migrations() {
        let db = Database::in_memory().expect("in-memory db init should succeed");
        let conn = db.conn();

        // Verify table existence
        let mut stmt = conn
            .prepare("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
            .unwrap();
        let tables: Vec<String> = stmt
            .query_map([], |row| row.get(0))
            .unwrap()
            .map(|r| r.unwrap())
            .collect();

        assert!(tables.contains(&"settings".to_string()));
        assert!(tables.contains(&"downloads".to_string()));
        assert!(tables.contains(&"licenses".to_string()));
        assert!(tables.contains(&"progress_queue".to_string()));
        assert!(tables.contains(&"migrations".to_string()));
    }
}
