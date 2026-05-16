# Local Run

This is the simple Windows run guide for the default 16 GB VRAM mode.

You do not need to edit any project files. Do not paste tokens into code files.

## 1. Install Requirements

Install these first:

- [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- [WSL2](https://learn.microsoft.com/windows/wsl/install)
- NVIDIA GPU driver with Docker Desktop GPU support
- Python only if you want to use `huggingface-cli login`

After installing Docker Desktop, open it once and make sure it is running.

## 2. Log In To Hugging Face

The app needs a Hugging Face token to download upstream model files.

Recommended:

```powershell
huggingface-cli login
```

Paste your Hugging Face token when it asks.

Alternative, only for the current PowerShell window:

```powershell
$env:HF_TOKEN = "your_huggingface_token"
```

Do not commit `.env` or any real token.

## 3. Open PowerShell In This Folder

In File Explorer:

1. Open this repository folder.
2. Click the address bar.
3. Type `powershell`.
4. Press Enter.

PowerShell should open directly inside the repo.

## 4. Start The App

Run:

```powershell
.\Install-And-Run.ps1
```

First run can take a long time because Docker builds the image and downloads models into Docker volumes.

When it finishes, open:

```text
http://127.0.0.1:8000/ui/
```

## 5. Where Outputs Are Saved

By default, WAV and JSON files go here:

```text
./outputs
```

That means an `outputs` folder inside this repo.

To save somewhere else:

```powershell
.\Install-And-Run.ps1 -OutputDir "D:\ScenemaAudioOutputs"
```

You can also set:

```powershell
$env:SCENEMA_OUTPUT_DIR = "D:\ScenemaAudioOutputs"
.\Install-And-Run.ps1
```

## 6. Stop The App

```powershell
docker compose stop scenema-audio
```

## 7. Start Again Later

Fast start without rebuilding:

```powershell
.\Install-And-Run.ps1 -NoBuild
```

Or:

```powershell
docker compose up -d
```

## 8. Watch Logs

```powershell
docker compose logs -f scenema-audio
```

Press `Ctrl+C` to stop watching logs. This does not stop the server.

## 9. Check Health

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

Expected:

```text
status
------
ok
```

## 10. If Something Breaks

Check Docker is running:

```powershell
docker ps
```

Check logs:

```powershell
docker compose logs --tail 100 scenema-audio
```

Restart:

```powershell
docker compose restart scenema-audio
```

Full Gemma is optional and not part of normal startup. See [docs/optional-full-gemma.md](docs/optional-full-gemma.md).
