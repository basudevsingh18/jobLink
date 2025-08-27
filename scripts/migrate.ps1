<# 
.SYNOPSIS
  Run SQL migrations inside a Postgres Docker container.
.USAGE
  .\migrate.ps1 [-Container jl_postgres] [-Db joblink] [-User joblink] [-MigDir ..\db\init]
#>
param(
  [string]$Container = "joblink-db-1",
  [string]$Db = "joblink",
  [string]$User = "joblink",
  [string]$MigDir = "$PSScriptRoot\..\db\init"
)

if (-not (Test-Path $MigDir)) {
  Write-Error "Migration directory not found: $MigDir"
  exit 2
}

# Check if container is running
$running = & docker ps --format "{{.Names}}"
if ($running -notmatch ("^" + [regex]::Escape($Container) + "$")) {
  Write-Error "Container $Container not running. Start with 'docker compose up -d'."
  exit 3
}

$files = Get-ChildItem -Path $MigDir -Filter *.sql | Sort-Object Name
if ($files.Length -eq 0) {
  Write-Error "No .sql files found in $MigDir"
  exit 4
}

foreach ($f in $files) {
  Write-Host "Applying $($f.Name)"
  Get-Content -Raw $f.FullName | docker exec -i $Container psql -U $User -d $Db
}

Write-Host "Migrations completed."
