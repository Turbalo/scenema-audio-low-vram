$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

docker compose -f docker-compose.full-gemma.yml stop scenema-audio-full-gemma
