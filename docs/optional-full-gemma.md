# Optional Full Gemma Mode

The default low-VRAM install does not download the full `google/gemma-3-12b-it` checkpoint.

Use this mode only when you want to compare prompt adherence against the original full Gemma text encoder. It is much slower and needs more system RAM.

## Requirements

- Around 64 GB system RAM recommended.
- A Docker volume named `scenema-audio_gemma-full-bf16`.
- Full Gemma files placed at:

```text
/app/gemma-full/gemma-3-12b-it
```

inside that volume.

## Start

```powershell
.\Start-ScenemaAudio-FullGemma.ps1 -StopFastMode
```

Open:

```text
http://127.0.0.1:8002/ui/
```

Stop:

```powershell
.\Stop-ScenemaAudio-FullGemma.ps1
```

## Notes

- This mode is not part of the one-command low-VRAM path.
- The compose file mounts the full Gemma volume as read-only, so it will not accidentally download the full checkpoint during normal startup.
- In the measured runs, full Gemma followed prompt context better, but did not fix Russian stress/pronunciation errors.
