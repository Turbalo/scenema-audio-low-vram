# Optional bf16 Audio Transformer Mode

The default low-VRAM runtime uses the INT8 Scenema Audio transformer:

```text
/app/models/scenema-audio-transformer-int8.safetensors
```

This optional mode uses the official bf16 audio transformer instead:

```text
/app/models/scenema-audio-transformer.safetensors
```

Gemma remains in the low-VRAM NF4 unload mode. This isolates the test to the Scenema audio transformer.

## Why This Is Optional

The bf16 audio transformer is about twice as large as the INT8 transformer. On 16 GB VRAM this can be unstable or slower, especially when validation, vocal separation, or SeedVC are enabled.

64 GB system RAM is recommended for this mode. The runtime offloads Scenema audio models before Gemma text encoding, Whisper validation, and SeedVC, which helps VRAM but increases RAM and model reload pressure.

Use this mode for A/B quality checks, not as the default runtime.

## Start

```powershell
.\Start-ScenemaAudio-BF16Audio.ps1 -StopFastMode -StopFullGemmaMode
```

Open:

```text
http://127.0.0.1:8003/ui/
```

Stop:

```powershell
.\Stop-ScenemaAudio-BF16Audio.ps1
```

## Notes

- First start downloads `scenema-audio-transformer.safetensors` if it is missing.
- The file is stored in the same Docker model volume as the INT8 checkpoint.
- This mode sets `OFFLOAD_AUDIO_BEFORE_AUX=1` automatically.
- Default low-VRAM mode remains unchanged on port 8000.
- Optional full Gemma mode remains separate on port 8002.
