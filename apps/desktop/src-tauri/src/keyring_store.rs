use base64::prelude::*;

pub const DEFAULT_SERVICE_NAME: &str = "com.university.lectureplatform";
pub const USER_DEVICE_KEY: &str = "device_private_key";
pub const USER_REFRESH_TOKEN: &str = "refresh_token";

pub fn store_secret(service: &str, user: &str, secret: &str) -> Result<(), String> {
    let entry = keyring::Entry::new(service, user)
        .map_err(|e| format!("Secure storage unavailable: {}", e))?;
    entry
        .set_password(secret)
        .map_err(|e| format!("Secure storage unavailable: {}", e))
}

pub fn get_secret(service: &str, user: &str) -> Result<Option<String>, String> {
    let entry = keyring::Entry::new(service, user)
        .map_err(|e| format!("Secure storage unavailable: {}", e))?;
    match entry.get_password() {
        Ok(val) => Ok(Some(val)),
        Err(keyring::Error::NoEntry) => Ok(None),
        Err(e) => Err(format!("Secure storage unavailable: {}", e)),
    }
}

pub fn delete_secret(service: &str, user: &str) -> Result<(), String> {
    let entry = keyring::Entry::new(service, user)
        .map_err(|e| format!("Secure storage unavailable: {}", e))?;
    match entry.delete_credential() {
        Ok(_) | Err(keyring::Error::NoEntry) => Ok(()),
        Err(e) => Err(format!("Secure storage unavailable: {}", e)),
    }
}

pub fn store_device_private_key(service: &str, secret_bytes: &[u8; 32]) -> Result<(), String> {
    let b64 = BASE64_STANDARD.encode(secret_bytes);
    store_secret(service, USER_DEVICE_KEY, &b64)
}

pub fn get_device_private_key(service: &str) -> Result<Option<[u8; 32]>, String> {
    let opt_b64 = get_secret(service, USER_DEVICE_KEY)?;
    match opt_b64 {
        Some(b64) => {
            let bytes = BASE64_STANDARD
                .decode(b64.trim())
                .map_err(|e| format!("Failed to decode device key: {}", e))?;
            if bytes.len() != 32 {
                return Err("Invalid device key length in secure storage".to_string());
            }
            let mut arr = [0u8; 32];
            arr.copy_from_slice(&bytes);
            Ok(Some(arr))
        }
        None => Ok(None),
    }
}

pub fn store_refresh_token(service: &str, token: &str) -> Result<(), String> {
    store_secret(service, USER_REFRESH_TOKEN, token)
}

pub fn get_refresh_token(service: &str) -> Result<Option<String>, String> {
    get_secret(service, USER_REFRESH_TOKEN)
}

pub fn delete_refresh_token(service: &str) -> Result<(), String> {
    delete_secret(service, USER_REFRESH_TOKEN)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_secret_store_and_read_back_with_new_entry() {
        let nanos = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let service = format!("com.university.test.keyring.{}", nanos);
        let user = "test_user";
        let secret = "opaque_refresh_token_string_abc123";

        // Cleanup before
        let _ = delete_secret(&service, user);

        // 1. Store secret
        store_secret(&service, user, secret).expect("store_secret should succeed");

        // 2. Create a NEW keyring Entry for the same service and name (simulating an app restart)
        let fresh_entry = keyring::Entry::new(&service, user).expect("new Entry creation should succeed");
        let read_back = fresh_entry.get_password().expect("read back from new Entry should succeed");
        assert_eq!(read_back, secret);

        // 3. Clean up
        delete_secret(&service, user).expect("delete_secret should succeed");
        let after_delete = get_secret(&service, user).expect("get_secret after delete should succeed");
        assert_eq!(after_delete, None);
    }
}
