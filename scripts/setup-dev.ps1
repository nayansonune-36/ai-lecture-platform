# =============================================================================
# scripts/setup-dev.ps1
# Safe first-time development environment setup for Windows
# =============================================================================
[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path "$PSScriptRoot\..").Path
$EnvFile = Join-Path $RepoRoot ".env"
$EnvExampleFile = Join-Path $RepoRoot ".env.example"
$StorageDir = Join-Path $RepoRoot "storage"

Write-Host "================================================================="
Write-Host "AI Lecture Platform - Windows Dev Environment Setup"
Write-Host "================================================================="
Write-Host "Repository root : $RepoRoot"

# 1. Copy .env.example to .env only if .env does not exist
if (-not (Test-Path $EnvFile)) {
    if (-not (Test-Path $EnvExampleFile)) {
        Write-Error ".env.example was not found at $EnvExampleFile"
        exit 1
    }
    Copy-Item $EnvExampleFile $EnvFile
    Write-Host "[OK] Created initial .env from .env.example"
} else {
    Write-Host "[INFO] .env already exists. Preserving any previously configured values."
}

# 2. Ensure storage folder exists as an absolute path
if (-not (Test-Path $StorageDir)) {
    New-Item -ItemType Directory -Path $StorageDir -Force | Out-Null
    Write-Host "[OK] Created storage directory at: $StorageDir"
} else {
    Write-Host "[INFO] Storage directory already exists: $StorageDir"
}

# 3. Read .env content
$envContent = Get-Content $EnvFile -Raw -Encoding utf8

# Helper to generate random 32-byte hex string
function New-RandomHexKey {
    $bytes = New-Object byte[] 32
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $rng.GetBytes($bytes)
    return -join ($bytes | ForEach-Object { "{0:x2}" -f $_ })
}

# 4. Ensure host-resolvable database and redis URLs for local dev (using 127.0.0.1 to avoid IPv6 timeout on Windows)
if ($envContent -match '(?m)^DATABASE_URL=.*@(postgres|localhost):5432/(.*)$') {
    $envContent = [regex]::Replace($envContent, '(?m)^DATABASE_URL=postgresql\+asyncpg://([^:]+):([^@]+)@(postgres|localhost):5432/(.*)$', 'DATABASE_URL=postgresql+asyncpg://$1:$2@127.0.0.1:5432/$4')
    Write-Host "[OK] Updated DATABASE_URL to use 127.0.0.1:5432 for host development"
}
if ($envContent -match '(?m)^REDIS_URL=redis://(redis|localhost):6379/(.*)$') {
    $envContent = [regex]::Replace($envContent, '(?m)^REDIS_URL=redis://(redis|localhost):6379/(.*)$', 'REDIS_URL=redis://127.0.0.1:6379/$2')
    Write-Host "[OK] Updated REDIS_URL to use 127.0.0.1:6379 for host development"
}
if ($envContent -match '(?m)^OLLAMA_BASE_URL=http://(ollama|localhost):11434$') {
    $envContent = [regex]::Replace($envContent, '(?m)^OLLAMA_BASE_URL=http://(ollama|localhost):11434$', 'OLLAMA_BASE_URL=http://127.0.0.1:11434')
    Write-Host "[OK] Updated OLLAMA_BASE_URL to use 127.0.0.1:11434 for host development"
}

# 5. Update STORAGE_ROOT to absolute path if needed
if ($envContent -match '(?m)^STORAGE_ROOT=(.*)$') {
    $currentStorage = $matches[1].Trim('"', "'", " ")
    $isAbsolute = $false
    try {
        $isAbsolute = [System.IO.Path]::IsPathRooted($currentStorage) -and ($currentStorage -ne "./storage") -and ($currentStorage -ne ".\storage")
    } catch {
        $isAbsolute = $false
    }

    if (-not $isAbsolute) {
        $envContent = [regex]::Replace($envContent, '(?m)^STORAGE_ROOT=.*$', "STORAGE_ROOT=$StorageDir")
        Write-Host "[OK] Configured STORAGE_ROOT to absolute path: $StorageDir"
    } else {
        Write-Host "[INFO] Preserving existing absolute STORAGE_ROOT: $currentStorage"
    }
} else {
    $envContent += "`nSTORAGE_ROOT=$StorageDir"
    Write-Host "[OK] Added STORAGE_ROOT=$StorageDir to .env"
}

# 5. Generate random SECRET_KEY if empty or placeholder
if ($envContent -match '(?m)^SECRET_KEY=(.*)$') {
    $currentSecret = $matches[1].Trim('"', "'", " ")
    if ([string]::IsNullOrWhiteSpace($currentSecret) -or ($currentSecret -like "*change_this*") -or ($currentSecret -like "*insecure*")) {
        $newSecret = New-RandomHexKey
        $envContent = [regex]::Replace($envContent, '(?m)^SECRET_KEY=.*$', "SECRET_KEY=$newSecret")
        Write-Host "[OK] Generated and configured random 256-bit SECRET_KEY"
    } else {
        Write-Host "[INFO] Preserving existing configured SECRET_KEY"
    }
} else {
    $newSecret = New-RandomHexKey
    $envContent += "`nSECRET_KEY=$newSecret"
    Write-Host "[OK] Generated and added random 256-bit SECRET_KEY"
}

# 6. Generate random MEDIA_SIGNING_KEY if empty or placeholder
if ($envContent -match '(?m)^MEDIA_SIGNING_KEY=(.*)$') {
    $currentMediaKey = $matches[1].Trim('"', "'", " ")
    if ([string]::IsNullOrWhiteSpace($currentMediaKey) -or ($currentMediaKey -like "*change_this*") -or ($currentMediaKey -like "*insecure*")) {
        $newMediaKey = New-RandomHexKey
        $envContent = [regex]::Replace($envContent, '(?m)^MEDIA_SIGNING_KEY=.*$', "MEDIA_SIGNING_KEY=$newMediaKey")
        Write-Host "[OK] Generated and configured random 256-bit MEDIA_SIGNING_KEY"
    } else {
        Write-Host "[INFO] Preserving existing configured MEDIA_SIGNING_KEY"
    }
} else {
    $newMediaKey = New-RandomHexKey
    $envContent += "`nMEDIA_SIGNING_KEY=$newMediaKey"
    Write-Host "[OK] Generated and added random 256-bit MEDIA_SIGNING_KEY"
}

# 7. Generate LICENSE_SIGNING_KEY if empty or missing
if ($envContent -match '(?m)^LICENSE_SIGNING_KEY=(.*)$') {
    $currentLicenseKey = $matches[1].Trim('"', "'", " ")
    if ([string]::IsNullOrWhiteSpace($currentLicenseKey)) {
        Write-Host "[INFO] Generating Ed25519 offline license signing keypair..."
        $licenseScript = Join-Path $RepoRoot "services\api\scripts\generate_license_keys.py"
        try {
            $rawLicense = (uv run --project "$RepoRoot\services\api" python $licenseScript --raw-private).Trim()
            if (-not [string]::IsNullOrWhiteSpace($rawLicense)) {
                $envContent = [regex]::Replace($envContent, '(?m)^LICENSE_SIGNING_KEY=.*$', "LICENSE_SIGNING_KEY=`"$rawLicense`"")
                Write-Host "[OK] Configured Ed25519 LICENSE_SIGNING_KEY"
            } else {
                Write-Warning "License key generator returned empty string"
            }
        } catch {
            Write-Warning "Failed to run license key generator with uv: $_"
        }
    } else {
        Write-Host "[INFO] Preserving existing configured LICENSE_SIGNING_KEY"
    }
} else {
    Write-Host "[INFO] Generating Ed25519 offline license signing keypair..."
    $licenseScript = Join-Path $RepoRoot "services\api\scripts\generate_license_keys.py"
    try {
        $rawLicense = (uv run --project "$RepoRoot\services\api" python $licenseScript --raw-private).Trim()
        if (-not [string]::IsNullOrWhiteSpace($rawLicense)) {
            $envContent += "`nLICENSE_SIGNING_KEY=`"$rawLicense`""
            Write-Host "[OK] Generated and configured Ed25519 LICENSE_SIGNING_KEY"
        }
    } catch {
        Write-Warning "Failed to run license key generator with uv: $_"
    }
}

# 8. Save updated .env without BOM, UTF-8 encoded
$utf8NoBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText($EnvFile, $envContent, $utf8NoBom)

Write-Host "================================================================="
Write-Host "Dev setup complete! .env is ready for local execution."
Write-Host "Secrets were generated and saved safely without printing to console."
Write-Host "================================================================="
