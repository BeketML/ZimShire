# scripts/setup.ps1
# Runs from the repo root. Starts containers, waits for Postgres,
# then applies Alembic migrations.
#
# Usage (from repo root):
#   .\scripts\setup.ps1
#   .\scripts\setup.ps1 -Detach          # run in background
#   .\scripts\setup.ps1 -SkipMigrations  # infra only, no alembic

param(
    [switch]$Detach,
    [switch]$SkipMigrations
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

Write-Host "Starting containers..."
if ($Detach) {
    docker compose up -d --build
} else {
    docker compose up -d
}

Write-Host "Waiting for postgres to be healthy..."
$timeout = 60
$elapsed = 0
while ($elapsed -lt $timeout) {
    $status = docker inspect --format="{{.State.Health.Status}}" zimshire-postgres 2>$null
    if ($status -eq "healthy") {
        Write-Host "Postgres is healthy."
        break
    }
    Start-Sleep -Seconds 2
    $elapsed += 2
    Write-Host "  ...waiting ($elapsed s)"
}

if ($elapsed -ge $timeout) {
    Write-Error "Postgres did not become healthy within ${timeout}s. Aborting."
    exit 1
}

if (-not $SkipMigrations) {
    Write-Host "Running Alembic migrations..."
    & .\venv\Scripts\python.exe -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Alembic migration failed (exit $LASTEXITCODE)."
        exit 1
    }
    Write-Host "Migrations applied."
}

Write-Host ""
Write-Host "Services:"
Write-Host "  Postgres  -> localhost:$env:POSTGRES_PORT"
Write-Host "  Qdrant    -> http://localhost:$env:QDRANT_PORT"
Write-Host "  pgAdmin   -> http://localhost:$env:PGADMIN_PORT"
Write-Host ""
Write-Host "Done."
