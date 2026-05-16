$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

docker compose -f docker-compose.bf16-audio.yml stop scenema-audio-bf16
