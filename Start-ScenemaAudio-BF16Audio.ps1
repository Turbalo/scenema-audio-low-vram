param(
    [switch]$StopFastMode,
    [switch]$StopFullGemmaMode
)

$ErrorActionPreference = "Stop"
$tokenPath = Join-Path $env:USERPROFILE ".cache\huggingface\token"
$outputDir = if ($env:SCENEMA_OUTPUT_DIR) { $env:SCENEMA_OUTPUT_DIR } else { Join-Path $PSScriptRoot "outputs" }

if (-not (Test-Path -LiteralPath $tokenPath)) {
    throw "Hugging Face token not found: $tokenPath. Run: huggingface-cli login"
}

New-Item -ItemType Directory -Force -Path $outputDir | Out-Null
$env:SCENEMA_OUTPUT_DIR = $outputDir

$env:HF_TOKEN = (Get-Content -LiteralPath $tokenPath -Raw).Trim()
if (-not $env:HF_TOKEN) {
    throw "Hugging Face token file is empty: $tokenPath"
}

docker volume create scenema-audio_model-cache | Out-Null
docker volume create scenema-audio_seedvc-checkpoints | Out-Null

Set-Location -LiteralPath $PSScriptRoot

if ($StopFastMode) {
    docker compose stop scenema-audio
}

if ($StopFullGemmaMode) {
    docker compose -f docker-compose.full-gemma.yml stop scenema-audio-full-gemma
}

docker compose -f docker-compose.bf16-audio.yml up -d --build
Write-Host "bf16 audio mode: http://127.0.0.1:8003/ui/"
Write-Host "Logs: docker compose -f docker-compose.bf16-audio.yml logs -f scenema-audio-bf16"
