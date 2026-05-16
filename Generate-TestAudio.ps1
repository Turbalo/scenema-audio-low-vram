$ErrorActionPreference = "Stop"

$out = if ($args.Count -gt 0) { $args[0] } else { "output.wav" }
$body = @{
    prompt = '<speak voice="A warm, clear male voice with a slight British accent. Measured, thoughtful pacing." gender="male">The old lighthouse had stood on the cliff for over a century.</speak>'
    mode = "voice_design"
    seed = 42
} | ConvertTo-Json

Invoke-RestMethod `
    -Method Post `
    -Uri "http://localhost:8000/generate" `
    -ContentType "application/json" `
    -Body $body `
    -OutFile $out

Write-Host "Saved $out"
