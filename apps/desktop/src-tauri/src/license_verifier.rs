use std::time::{SystemTime, UNIX_EPOCH};

use base64::engine::general_purpose::{STANDARD, URL_SAFE, URL_SAFE_NO_PAD};
use base64::Engine;
use ed25519_dalek::{Signature, Signer, SigningKey, Verifier, VerifyingKey};
use rusqlite::Connection;
use serde::{Deserialize, Serialize};

use crate::settings;

const ED25519_SPKI_PREFIX: [u8; 12] = [
    0x30, 0x2a, 0x30, 0x05, 0x06, 0x03, 0x2b, 0x65, 0x70, 0x03, 0x21, 0x00,
];

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LicenseClaims {
    pub user_id: String,
    pub device_id: String,
    pub lecture_id: String,
    pub bundle_sha256: String,
    #[serde(default)]
    pub issued_at: Option<String>,
    #[serde(default)]
    pub expires_at: Option<String>,
    #[serde(default)]
    pub iat: Option<i64>,
    pub exp: i64,
}

pub fn decode_base64_url(input: &str) -> Result<Vec<u8>, String> {
    let unpadded = input.trim_end_matches('=');
    URL_SAFE_NO_PAD
        .decode(unpadded)
        .or_else(|_| URL_SAFE.decode(input))
        .map_err(|e| format!("Base64URL decode failed: {}", e))
}

pub fn encode_base64_url(input: &[u8]) -> String {
    URL_SAFE_NO_PAD.encode(input)
}

pub fn parse_ed25519_public_key(pem_or_raw: &str) -> Result<VerifyingKey, String> {
    let trimmed = pem_or_raw.trim();

    // 1. Try PEM format
    if trimmed.contains("-----BEGIN") {
        let lines: Vec<&str> = trimmed
            .lines()
            .filter(|line| !line.starts_with("-----"))
            .collect();
        let b64 = lines.concat();
        let der = STANDARD
            .decode(&b64)
            .map_err(|e| format!("Failed to decode PEM base64: {}", e))?;

        if der.len() == 44 && der.starts_with(&ED25519_SPKI_PREFIX) {
            let mut key_bytes = [0u8; 32];
            key_bytes.copy_from_slice(&der[12..44]);
            return VerifyingKey::from_bytes(&key_bytes)
                .map_err(|e| format!("Invalid Ed25519 public key bytes: {}", e));
        }

        if der.len() == 32 {
            let mut key_bytes = [0u8; 32];
            key_bytes.copy_from_slice(&der);
            return VerifyingKey::from_bytes(&key_bytes)
                .map_err(|e| format!("Invalid Ed25519 public key bytes: {}", e));
        }
    }

    // 2. Try 64-char hex
    if trimmed.len() == 64 {
        if let Ok(bytes) = hex::decode(trimmed) {
            if bytes.len() == 32 {
                let mut key_bytes = [0u8; 32];
                key_bytes.copy_from_slice(&bytes);
                return VerifyingKey::from_bytes(&key_bytes)
                    .map_err(|e| format!("Invalid Ed25519 public key bytes: {}", e));
            }
        }
    }

    // 3. Try raw base64 (32 bytes)
    if let Ok(bytes) = STANDARD.decode(trimmed) {
        if bytes.len() == 32 {
            let mut key_bytes = [0u8; 32];
            key_bytes.copy_from_slice(&bytes);
            return VerifyingKey::from_bytes(&key_bytes)
                .map_err(|e| format!("Invalid Ed25519 public key bytes: {}", e));
        }
    }

    Err("Could not parse string as Ed25519 PEM or public key".to_string())
}

pub fn verify_license_jwt(token: &str, public_key_pem: &str) -> Result<LicenseClaims, String> {
    let parts: Vec<&str> = token.split('.').collect();
    if parts.len() != 3 {
        return Err("License token format is invalid (expected 3 parts)".to_string());
    }

    let signing_input = format!("{}.{}", parts[0], parts[1]);
    let sig_bytes = decode_base64_url(parts[2])?;
    if sig_bytes.len() != 64 {
        return Err(format!(
            "Invalid Ed25519 signature length (expected 64, got {})",
            sig_bytes.len()
        ));
    }

    let mut sig_arr = [0u8; 64];
    sig_arr.copy_from_slice(&sig_bytes);
    let signature = Signature::from_bytes(&sig_arr);

    let verifying_key = parse_ed25519_public_key(public_key_pem)?;
    verifying_key
        .verify(signing_input.as_bytes(), &signature)
        .map_err(|e| format!("License signature verification failed: {}", e))?;

    let payload_bytes = decode_base64_url(parts[1])?;
    let claims: LicenseClaims = serde_json::from_slice(&payload_bytes)
        .map_err(|e| format!("Failed to parse license token claims: {}", e))?;

    let now = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs() as i64;

    if claims.exp <= now {
        return Err(format!(
            "License token has expired (expires at {}, current time {})",
            claims.exp, now
        ));
    }

    Ok(claims)
}

pub fn issue_test_license_token(
    signing_key: &SigningKey,
    claims: &LicenseClaims,
) -> Result<String, String> {
    let header_json = serde_json::json!({
        "alg": "EdDSA",
        "typ": "JWT"
    });
    let header_b64 = encode_base64_url(header_json.to_string().as_bytes());
    let claims_json = serde_json::to_string(claims).map_err(|e| e.to_string())?;
    let payload_b64 = encode_base64_url(claims_json.as_bytes());

    let signing_input = format!("{}.{}", header_b64, payload_b64);
    let signature = signing_key.sign(signing_input.as_bytes());
    let sig_b64 = encode_base64_url(&signature.to_bytes());

    Ok(format!("{}.{}.{}", header_b64, payload_b64, sig_b64))
}

pub fn format_public_key_pem(key_bytes: &[u8; 32]) -> String {
    let mut der = Vec::with_capacity(44);
    der.extend_from_slice(&ED25519_SPKI_PREFIX);
    der.extend_from_slice(key_bytes);
    let b64 = STANDARD.encode(&der);
    format!("-----BEGIN PUBLIC KEY-----\n{}\n-----END PUBLIC KEY-----\n", b64)
}

pub fn verify_lecture_access(conn: &Connection, lecture_id: &str) -> Result<LicenseClaims, String> {
    // 1. Query licenses row
    let mut stmt = conn
        .prepare(
            r#"
            SELECT device_id, token, expires_at, revoked_at
            FROM licenses
            WHERE lecture_id = ?1
            "#,
        )
        .map_err(|e| e.to_string())?;

    let row = stmt
        .query_row([lecture_id], |r| {
            Ok((
                r.get::<_, String>(0)?,
                r.get::<_, String>(1)?,
                r.get::<_, String>(2)?,
                r.get::<_, Option<String>>(3)?,
            ))
        })
        .map_err(|_| format!("No offline license found for lecture {}", lecture_id))?;

    let (db_device_id, token, _expires_at, revoked_at) = row;

    if revoked_at.is_some() {
        return Err("Offline license has been revoked".to_string());
    }

    // 2. Get pinned server public key
    let public_key_pem = settings::get_license_public_key(conn)
        .map_err(|e| e.to_string())?
        .ok_or_else(|| "Server license verification public key not pinned".to_string())?;

    // 3. Verify JWT signature & expiration
    let claims = verify_license_jwt(&token, &public_key_pem)?;

    // 4. Verify lecture_id
    if claims.lecture_id != lecture_id {
        return Err(format!(
            "License lecture ID mismatch: expected {}, got {}",
            lecture_id, claims.lecture_id
        ));
    }

    // 5. Verify device_id
    let current_device_id = settings::get_device_id(conn)
        .map_err(|e| e.to_string())?
        .unwrap_or_default();
    if !current_device_id.is_empty()
        && (claims.device_id != current_device_id || db_device_id != current_device_id)
    {
        return Err(format!(
            "License device ID mismatch: expected {}, got {}",
            current_device_id, claims.device_id
        ));
    }

    // 6. Verify user matches
    if let Ok(Some(last_user)) = settings::get_last_user(conn) {
        if claims.user_id != last_user.id {
            return Err(format!(
                "License user ID mismatch: expected {}, got {}",
                last_user.id, claims.user_id
            ));
        }
    }

    Ok(claims)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::db::Database;
    use rand::rngs::OsRng;

    #[test]
    fn test_license_jwt_round_trip_and_expiration() {
        let mut csprng = OsRng;
        let signing_key = SigningKey::generate(&mut csprng);
        let verifying_key = signing_key.verifying_key();
        let pub_pem = format_public_key_pem(&verifying_key.to_bytes());

        let now = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_secs() as i64;

        let valid_claims = LicenseClaims {
            user_id: "user-123".to_string(),
            device_id: "dev-456".to_string(),
            lecture_id: "lec-789".to_string(),
            bundle_sha256: "abcde".to_string(),
            issued_at: None,
            expires_at: None,
            iat: Some(now),
            exp: now + 3600,
        };

        let token = issue_test_license_token(&signing_key, &valid_claims).unwrap();
        let verified = verify_license_jwt(&token, &pub_pem).unwrap();
        assert_eq!(verified.user_id, "user-123");
        assert_eq!(verified.lecture_id, "lec-789");

        // Expired token
        let expired_claims = LicenseClaims {
            exp: now - 10,
            ..valid_claims.clone()
        };
        let expired_token = issue_test_license_token(&signing_key, &expired_claims).unwrap();
        let err = verify_license_jwt(&expired_token, &pub_pem).unwrap_err();
        assert!(err.contains("expired"));

        // Tampered token
        let mut tampered = token.clone();
        tampered.push_str("extra");
        assert!(verify_license_jwt(&tampered, &pub_pem).is_err());
    }

    #[test]
    fn test_verify_lecture_access_database_flow() {
        let db = Database::in_memory().unwrap();
        let conn = db.conn();

        let mut csprng = OsRng;
        let signing_key = SigningKey::generate(&mut csprng);
        let pub_pem = format_public_key_pem(&signing_key.verifying_key().to_bytes());

        settings::set_license_public_key(conn, &pub_pem).unwrap();
        settings::set_device_id(conn, "dev-1").unwrap();
        settings::set_last_user(
            conn,
            &settings::UserProfile {
                id: "user-1".to_string(),
                email: "student@univ.edu".to_string(),
                name: "Student".to_string(),
                role: "student".to_string(),
            },
        )
        .unwrap();

        let now = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_secs() as i64;

        let claims = LicenseClaims {
            user_id: "user-1".to_string(),
            device_id: "dev-1".to_string(),
            lecture_id: "lec-1".to_string(),
            bundle_sha256: "sha256-test".to_string(),
            issued_at: None,
            expires_at: None,
            iat: Some(now),
            exp: now + 86400,
        };
        let token = issue_test_license_token(&signing_key, &claims).unwrap();

        conn.execute(
            r#"
            INSERT INTO licenses (lecture_id, device_id, token, bundle_sha256, issued_at, expires_at, revoked_at)
            VALUES (?1, ?2, ?3, ?4, 'now', 'future', NULL)
            "#,
            rusqlite::params!["lec-1", "dev-1", token, "sha256-test"],
        )
        .unwrap();

        // Valid check
        let verified = verify_lecture_access(conn, "lec-1").unwrap();
        assert_eq!(verified.lecture_id, "lec-1");

        // Revoked check
        conn.execute(
            "UPDATE licenses SET revoked_at = 'now' WHERE lecture_id = 'lec-1'",
            [],
        )
        .unwrap();
        let err = verify_lecture_access(conn, "lec-1").unwrap_err();
        assert!(err.contains("revoked"));
    }
}
