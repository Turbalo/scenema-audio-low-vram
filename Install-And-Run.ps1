param(
    [string]$OutputDir = "",
    [switch]$NoBuild
)

$ErrorActionPreference = "Stop"

$repo = Split-Path -Parent $MyInvocation.MyCommand.Path
$envPath = Join-Path $repo ".env"

if (Test-Path -LiteralPath $envPath) {
    Get-Content -LiteralPath $envPath | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
            $name, $value = $line.Split("=", 2)
            $name = $name.Trim()
            $value = $value.Trim().Trim('"').Trim("'")
            if ($name -and -not [Environment]::GetEnvironmentVariable($name, "Process")) {
                [Environment]::SetEnvironmentVariable($name, $value, "Process")
            }
        }
    }
}

if (-not $OutputDir) {
    $OutputDir = if ($env:SCENEMA_OUTPUT_DIR) { $env:SCENEMA_OUTPUT_DIR } else { Join-Path $repo "outputs" }
}

if (-not $env:HF_TOKEN) {
    $tokenPath = Join-Path $env:USERPROFILE ".cache\huggingface\token"
    if (Test-Path -LiteralPath $tokenPath) {
        $env:HF_TOKEN = (Get-Content -LiteralPath $tokenPath -Raw).Trim()
    }
}

if (-not $env:HF_TOKEN) {
    throw "HF_TOKEN is not set. Run `huggingface-cli login` or set `$env:HF_TOKEN before starting."
}

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$env:SCENEMA_OUTPUT_DIR = (Resolve-Path -LiteralPath $OutputDir).Path

docker volume create scenema-audio_model-cache | Out-Null
docker volume create scenema-audio_seedvc-checkpoints | Out-Null

Set-Location -LiteralPath $repo

$composeArgs = @("compose", "up", "-d")
if (-not $NoBuild) {
    $composeArgs += "--build"
}

& docker @composeArgs

Write-Host ""
Write-Host "Scenema Audio low-VRAM mode is starting."
Write-Host "UI: http://127.0.0.1:8000/ui/"
Write-Host "Outputs: $env:SCENEMA_OUTPUT_DIR"
Write-Host "Logs: docker compose logs -f scenema-audio"
