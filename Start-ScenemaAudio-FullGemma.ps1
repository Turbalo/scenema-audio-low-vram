param(
    [switch]$StopFastMode
)

$ErrorActionPreference = "Stop"
$tokenPath = Join-Path $env:USERPROFILE ".cache\huggingface\token"
$outputDir = if ($env:SCENEMA_OUTPUT_DIR) { $env:SCENEMA_OUTPUT_DIR } else { Join-Path $PSScriptRoot "outputs" }
$fullGemmaVolume = "scenema-audio_gemma-full-bf16"

docker volume inspect $fullGemmaVolume *> $null
if ($LASTEXITCODE -ne 0) {
    throw "Optional full Gemma volume not found: $fullGemmaVolume. See docs/optional-full-gemma.md."
}

if (-not (Test-Path -LiteralPath $tokenPath)) {
    throw "Hugging Face token not found: $tokenPath. Run: huggingface-cli login"
}

New-Item -ItemType Directory -Force -Path $outputDir | Out-Null
$env:SCENEMA_OUTPUT_DIR = $outputDir

$env:HF_TOKEN = (Get-Content -LiteralPath $tokenPath -Raw).Trim()
if (-not $env:HF_TOKEN) {
    throw "Hugging Face token file is empty: $tokenPath"
}

Set-Location -LiteralPath $PSScriptRoot

if ($StopFastMode) {
    docker compose stop scenema-audio
}

docker compose -f docker-compose.full-gemma.yml up -d --build
Write-Host "Full Gemma mode: http://127.0.0.1:8002/ui/"
Write-Host "Logs: docker compose -f docker-compose.full-gemma.yml logs -f scenema-audio-full-gemma"
