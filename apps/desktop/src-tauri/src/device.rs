use ed25519_dalek::{SigningKey, VerifyingKey};
use rand::rngs::OsRng;
use rusqlite::Connection;
use serde::{Deserialize, Serialize};

use crate::keyring_store::{self, DEFAULT_SERVICE_NAME};
use crate::settings;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DeviceInfo {
    pub id: Option<String>,
    pub name: String,
    pub public_key: String,
}

pub fn get_or_create_device_identity_with_service(
    conn: &Connection,
    service_name: &str,
) -> Result<DeviceInfo, String> {
    let mut pub_key = settings::get_device_public_key(conn).map_err(|e| e.to_string())?;
    let priv_key_bytes = keyring_store::get_device_private_key(service_name)?;

    match priv_key_bytes {
        Some(sec_bytes) => {
            let signing_key = SigningKey::from_bytes(&sec_bytes);
            let verifying_key: VerifyingKey = signing_key.verifying_key();
            let pub_hex = hex::encode(verifying_key.to_bytes());
            if pub_key.as_deref() != Some(&pub_hex) {
                settings::set_device_public_key(conn, &pub_hex)
                    .map_err(|e| format!("Failed to save device public key: {}", e))?;
                pub_key = Some(pub_hex);
            }
        }
        None => {
            let mut csprng = OsRng;
            let signing_key = SigningKey::generate(&mut csprng);
            let verifying_key: VerifyingKey = signing_key.verifying_key();

            let sec_bytes = signing_key.to_bytes();
            let pub_hex = hex::encode(verifying_key.to_bytes());

            // Store 32 bytes in base64 in Windows Credential Manager
            keyring_store::store_device_private_key(service_name, &sec_bytes)?;

            // Store public key in SQLite settings
            settings::set_device_public_key(conn, &pub_hex)
                .map_err(|e| format!("Failed to save device public key: {}", e))?;

            pub_key = Some(pub_hex);
        }
    }

    let mut name = settings::get_device_name(conn).map_err(|e| e.to_string())?;
    if name.is_none() {
        let default_name = std::env::var("COMPUTERNAME")
            .unwrap_or_else(|_| "Windows Student Laptop".to_string());
        settings::set_device_name(conn, &default_name)
            .map_err(|e| format!("Failed to save device name: {}", e))?;
        name = Some(default_name);
    }

    let id = settings::get_device_id(conn).map_err(|e| e.to_string())?;

    Ok(DeviceInfo {
        id,
        name: name.unwrap_or_else(|| "Windows Student Desktop".to_string()),
        public_key: pub_key.unwrap_or_default(),
    })
}

pub fn get_or_create_device_identity(conn: &Connection) -> Result<DeviceInfo, String> {
    get_or_create_device_identity_with_service(conn, DEFAULT_SERVICE_NAME)
}

pub async fn register_device_network(
    server_url: &str,
    access_token: &str,
    name: &str,
    public_key: &str,
) -> Result<String, String> {
    let client = reqwest::Client::new();
    let url = format!("{}/api/v1/devices", server_url.trim_end_matches('/'));

    let res = client
        .post(&url)
        .header("Authorization", format!("Bearer {}", access_token))
        .json(&serde_json::json!({
            "name": name,
            "public_key": public_key
        }))
        .send()
        .await
        .map_err(|e| format!("Network request to register device failed: {}", e))?;

    if !res.status().is_success() {
        let status = res.status();
        let body = res.text().await.unwrap_or_default();
        return Err(format!("Device registration failed ({status}): {body}"));
    }

    let data: serde_json::Value = res
        .json()
        .await
        .map_err(|e| format!("Failed to parse device response: {}", e))?;

    let device_id = data
        .get("id")
        .and_then(|v| v.as_str())
        .ok_or_else(|| "Device registration response did not contain an id".to_string())?;

    Ok(device_id.to_string())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::db::Database;
    use crate::keyring_store;

    #[test]
    fn test_device_identity_persistence_across_fresh_entry() {
        let nanos = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let service = format!("com.university.test.device.{}", nanos);
        let _ = keyring_store::delete_secret(&service, keyring_store::USER_DEVICE_KEY);

        let db = Database::in_memory().unwrap();
        let conn = db.conn();

        // 1. Call get_or_create_device_identity
        let dev1 = get_or_create_device_identity_with_service(conn, &service)
            .expect("first get_or_create should succeed");
        assert!(!dev1.public_key.is_empty());

        // 2. Simulate fresh Entry check in between
        let fresh_entry = keyring::Entry::new(&service, keyring_store::USER_DEVICE_KEY)
            .expect("fresh entry creation should succeed");
        let stored_b64 = fresh_entry
            .get_password()
            .expect("password must be present in keystore");
        assert!(!stored_b64.is_empty());

        // 3. Call get_or_create_device_identity second time
        let dev2 = get_or_create_device_identity_with_service(conn, &service)
            .expect("second get_or_create should succeed");
        assert_eq!(dev1.public_key, dev2.public_key);
        assert_eq!(dev1.name, dev2.name);

        // Cleanup
        let _ = keyring_store::delete_secret(&service, keyring_store::USER_DEVICE_KEY);
    }
}
