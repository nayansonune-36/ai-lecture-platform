use serde::{Deserialize, Serialize};

use crate::keyring_store::{self, DEFAULT_SERVICE_NAME};
use crate::settings::UserProfile;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LoginNetworkResponse {
    pub user: UserProfile,
    pub access_token: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LoginResult {
    pub user: UserProfile,
    pub device_id: String,
}

pub async fn execute_login_network(
    server_url: &str,
    email: &str,
    password: &str,
) -> Result<LoginNetworkResponse, String> {
    let client = reqwest::Client::new();
    let base = server_url.trim().trim_end_matches('/');
    let login_url = format!("{}/api/v1/auth/login", base);

    let res = client
        .post(&login_url)
        .json(&serde_json::json!({
            "email": email,
            "password": password
        }))
        .send()
        .await
        .map_err(|e| format!("Could not reach server: {}", e))?;

    if !res.status().is_success() {
        let status = res.status();
        let body = res.text().await.unwrap_or_default();
        return Err(format!("Login failed ({status}): {body}"));
    }

    let token_json: serde_json::Value = res
        .json()
        .await
        .map_err(|e| format!("Failed to parse login response: {}", e))?;

    let access_token = token_json
        .get("access_token")
        .and_then(|v| v.as_str())
        .ok_or_else(|| "Missing access_token from login response".to_string())?
        .to_string();

    // Store refresh token in Windows Credential Manager (never crosses to JS)
    if let Some(refresh_token) = token_json.get("refresh_token").and_then(|v| v.as_str()) {
        keyring_store::store_refresh_token(DEFAULT_SERVICE_NAME, refresh_token)?;
    }

    // Step 6: Call GET /api/v1/me to fill in full user details
    let me_url = format!("{}/api/v1/me", base);
    let me_res = client
        .get(&me_url)
        .header("Authorization", format!("Bearer {}", access_token))
        .send()
        .await
        .map_err(|e| format!("Failed to get user details: {}", e))?;

    if !me_res.status().is_success() {
        return Err("Failed to retrieve current user info from /api/v1/me".to_string());
    }

    let user: UserProfile = me_res
        .json()
        .await
        .map_err(|e| format!("Failed to decode user profile: {}", e))?;

    Ok(LoginNetworkResponse {
        user,
        access_token,
    })
}

pub fn execute_logout() -> Result<(), String> {
    keyring_store::delete_refresh_token(DEFAULT_SERVICE_NAME)
}
