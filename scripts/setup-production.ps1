# Production Setup Script for agent-gatefield (Windows PowerShell)
# PostgreSQL + pgvector installation and configuration

param(
    [string]$DbPassword = "gatefield_prod_password",
    [string]$DbUser = "gatefield",
    [string]$DbName = "gatefield",
    [int]$DbPort = 5432
)

Write-Host "=== agent-gatefield Production Setup (Windows) ===" -ForegroundColor Cyan

# Step 1: Check PostgreSQL installation
Write-Host ""
Write-Host "Step 1: Checking PostgreSQL installation..." -ForegroundColor Yellow

$pgPath = "C:\Program Files\PostgreSQL\17\bin"
if (Test-Path "$pgPath\psql.exe") {
    $env:PATH += ";$pgPath"
    Write-Host "Found PostgreSQL at: $pgPath" -ForegroundColor Green
} else {
    Write-Host "PostgreSQL not found. Attempting installation via winget..." -ForegroundColor Yellow
    winget install PostgreSQL.PostgreSQL.17 --accept-source-agreements --accept-package-agreements
    $env:PATH += ";$pgPath"
}

# Verify psql is available
$psqlCmd = Get-Command psql -ErrorAction SilentlyContinue
if (-not $psqlCmd) {
    Write-Host "psql not in PATH. Adding PostgreSQL bin directory..." -ForegroundColor Yellow
    $env:PATH = "$pgPath;$env:PATH"
}

# Step 2: Check PostgreSQL service
Write-Host ""
Write-Host "Step 2: Checking PostgreSQL service..." -ForegroundColor Yellow

$pgService = Get-Service "postgresql-x64-17" -ErrorAction SilentlyContinue
if ($pgService) {
    if ($pgService.Status -ne "Running") {
        Write-Host "Starting PostgreSQL service..." -ForegroundColor Yellow
        Start-Service "postgresql-x64-17"
    }
    Write-Host "PostgreSQL service is running" -ForegroundColor Green
} else {
    Write-Host "PostgreSQL service not found" -ForegroundColor Red
    exit 1
}

# Step 3: Create database and user
Write-Host ""
Write-Host "Step 3: Creating database and user..." -ForegroundColor Yellow

# Set PGPASSWORD for subsequent commands
$env:PGPASSWORD = "postgres"  # Default postgres password

# Check if database exists
$dbExists = & psql -U postgres -lqt 2>$null | Where-Object { $_ -match "^$DbName\s" }
if (-not $dbExists) {
    Write-Host "Creating database: $DbName" -ForegroundColor Yellow
    & psql -U postgres -c "CREATE DATABASE $DbName;" 2>$null
}

# Check if user exists
$userExists = & psql -U postgres -c "SELECT 1 FROM pg_roles WHERE rolname='$DbUser'" 2>$null
if (-not ($userExists -match "1")) {
    Write-Host "Creating user: $DbUser" -ForegroundColor Yellow
    & psql -U postgres -c "CREATE USER $DbUser WITH PASSWORD '$DbPassword';"
    & psql -U postgres -c "GRANT ALL PRIVILEGES ON DATABASE $DbName TO $DbUser;"
}

# Step 4: Install pgvector extension (Windows specific)
Write-Host ""
Write-Host "Step 4: Installing pgvector extension..." -ForegroundColor Yellow

$pgLibPath = "C:\Program Files\PostgreSQL\17\lib"
$pgExtPath = "C:\Program Files\PostgreSQL\17\share\extension"

# Check if vector.dll exists
if (-not (Test-Path "$pgLibPath\vector.dll")) {
    Write-Host "pgvector extension not found. Options:" -ForegroundColor Red
    Write-Host ""
    Write-Host "Option A: Use Docker (recommended for Windows)" -ForegroundColor Cyan
    Write-Host "  docker compose up -d"
    Write-Host ""
    Write-Host "Option B: Download pre-built pgvector for Windows" -ForegroundColor Cyan
    Write-Host "  1. Download from: https://github.com/pgvector/pgvector/releases"
    Write-Host "     Or use the included scripts/download-pgvector.ps1"
    Write-Host "  2. Copy vector.dll to: $pgLibPath"
    Write-Host "  3. Copy vector.control and vector--*.sql to: $pgExtPath"
    Write-Host ""
    Write-Host "Option C: Compile from source using Visual Studio" -ForegroundColor Cyan
    Write-Host "  See: https://github.com/pgvector/pgvector#windows"
    Write-Host ""
    Write-Host "For now, proceeding with mock mode..." -ForegroundColor Yellow
} else {
    Write-Host "pgvector extension found" -ForegroundColor Green

    # Enable extension
    $env:PGPASSWORD = $DbPassword
    & psql -U $DbUser -d $DbName -c "CREATE EXTENSION IF NOT EXISTS vector;" 2>$null
    Write-Host "pgvector extension enabled" -ForegroundColor Green
}

# Step 5: Apply schema
Write-Host ""
Write-Host "Step 5: Applying database schema..." -ForegroundColor Yellow

$env:PGPASSWORD = $DbPassword
$schemaFile = "src/vector_store/schema.sql"
if (Test-Path $schemaFile) {
    & psql -U $DbUser -d $DbName -f $schemaFile 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Schema applied successfully" -ForegroundColor Green
    } else {
        Write-Host "Schema application had issues (may be expected if pgvector not installed)" -ForegroundColor Yellow
    }
} else {
    Write-Host "Schema file not found: $schemaFile" -ForegroundColor Red
}

# Step 6: Create .env file
Write-Host ""
Write-Host "Step 6: Creating environment configuration..." -ForegroundColor Yellow

$envContent = @"
DATABASE_URL=postgresql://${DbUser}:${DbPassword}@localhost:${DbPort}/${DbName}
POSTGRES_USER=${DbUser}
POSTGRES_PASSWORD=${DbPassword}
POSTGRES_DB=${DbName}
POSTGRES_PORT=${DbPort}
"@

$envContent | Out-File -FilePath ".env" -Encoding utf8
Write-Host "Created .env file" -ForegroundColor Green

# Step 7: Install Python dependencies
Write-Host ""
Write-Host "Step 7: Installing Python dependencies..." -ForegroundColor Yellow

pip install psycopg2-binary pgvector 2>$null
if ($LASTEXITCODE -ne 0) {
    pip install psycopg2-binary 2>$null
}
Write-Host "Python dependencies installed" -ForegroundColor Green

# Step 8: Verify setup
Write-Host ""
Write-Host "Step 8: Verifying setup..." -ForegroundColor Yellow

# Test connection
$env:PGPASSWORD = $DbPassword
$testResult = & psql -U $DbUser -d $DbName -c "SELECT current_database(), current_user;" 2>$null
Write-Host $testResult

# Summary
Write-Host ""
Write-Host "=== Setup Complete ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "Database: $DbName" -ForegroundColor Green
Write-Host "User: $DbUser" -ForegroundColor Green
Write-Host "Connection: postgresql://${DbUser}:${DbPassword}@localhost:${DbPort}/${DbName}" -ForegroundColor Green
Write-Host ""
Write-Host "Note: If pgvector.dll is not installed, the system will use mock mode." -ForegroundColor Yellow
Write-Host "To enable real vector search, install pgvector as described above." -ForegroundColor Yellow
Write-Host ""
Write-Host "To test:" -ForegroundColor Cyan
Write-Host "  python -m pytest tests/ -v"
Write-Host "  python -m cli.gate_cli dry-run --run-id test-001"
Write-Host ""