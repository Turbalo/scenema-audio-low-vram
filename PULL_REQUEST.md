# Add Windows low-VRAM runtime for Scenema Audio

## Summary

- adds a Windows/WSL Docker runtime for 16 GB VRAM systems
- adds NF4 Gemma low-VRAM mode as the default runtime
- keeps full Gemma CPU-streaming as an optional comparison mode only
- pre-encodes all chunk text conditioning before audio diffusion, then unloads Gemma
- adds progress/cancel API endpoints and Gradio progress UI
- autosaves WAV and JSON metadata to `OUTPUT_DIR`
- adds one-command Windows startup through `Install-And-Run.ps1`
- documents benchmark comparisons from four local runs

## Benchmarks

All runs used seed `120`, `background_sfx=true`, `validate=false`, RTX 4080 SUPER 16 GB, and local Windows/WSL Docker.

| Pair | Mode | Audio duration | Processing time | Peak VRAM |
|---|---:|---:|---:|---:|
| Long prompt | NF4 low-VRAM | 50.34s | 108.36s | 14,488 MB |
| Long prompt | Optional full Gemma | 46.24s | 414.21s | 13,220 MB |
| Short prompt | NF4 low-VRAM | 12.20s | 19.72s | 14,488 MB |
| Short prompt | Optional full Gemma | 10.66s | 194.98s | 8,428 MB |

## Observations

- NF4 mode is much faster and is the practical default.
- Full Gemma followed prompt/context more closely in listening tests.
- Russian stress/pronunciation errors remained in both modes, so the issue is likely not caused only by Gemma quantization.
- WSL/Docker volume model storage avoids slow Windows bind-mount model reads.
- The default install does not download the full `google/gemma-3-12b-it` checkpoint.

## Test

```powershell
python -m py_compile app.py src\server.py src\audio_core\engine.py src\audio_core\inference.py src\audio_core\processor.py src\audio_core\whisper_aligner.py
docker compose config
docker compose -f docker-compose.full-gemma.yml config
```
