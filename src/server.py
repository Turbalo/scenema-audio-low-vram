# Copyright (c) 2026 Scenema AI
# https://scenema.ai
# SPDX-License-Identifier: MIT

"""Scenema Audio standalone server.

Thin FastAPI wrapper around the production AudioProcessor.
"""

import asyncio
import base64
import json
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from huggingface_hub import hf_hub_download, snapshot_download
import uvicorn

logger = logging.getLogger("scenema-audio")

# Must be set before any torch import
os.environ.setdefault(
    "PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True"
)

from audio_core.processor import AudioProcessor  # noqa: E402
from common.handlers.base import ProcessJob  # noqa: E402

# ── Model download ──────────────────────────────────────────────

HF_REPO = "ScenemaAI/scenema-audio"
DEFAULT_GEMMA_REPO = "google/gemma-3-12b-it"
DEFAULT_NF4_GEMMA_REPO = "unsloth/gemma-3-12b-it-bnb-4bit"
SEEDVC_REPO = "Plachta/Seed-VC"
BIGVGAN_REPO = "nvidia/bigvgan_v2_22khz_80band_256x"
WHISPER_REPO = "openai/whisper-small"

MODEL_DIR = Path(os.environ.get("MODEL_DIR", "/app/models"))
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "/app/outputs"))


def _download_models():
    """Download missing model checkpoints from HuggingFace."""

    token = os.environ.get("HF_TOKEN")

    # Audio transformer (INT8 by default)
    audio_ckpt = Path(os.environ.get(
        "AUDIO_CKPT",
        str(MODEL_DIR / "scenema-audio-transformer-int8.safetensors"),
    ))
    if not audio_ckpt.exists():
        logger.info("Downloading audio transformer (INT8, ~4.9 GB)...")
        hf_hub_download(
            HF_REPO,
            "scenema-audio-transformer-int8.safetensors",
            local_dir=str(audio_ckpt.parent),
            token=token,
        )

    # Pipeline checkpoint
    pipeline_ckpt = Path(os.environ.get(
        "PIPELINE_CKPT",
        str(MODEL_DIR / "scenema-audio-pipeline.safetensors"),
    ))
    if not pipeline_ckpt.exists():
        logger.info("Downloading pipeline checkpoint (~7.1 GB)...")
        hf_hub_download(
            HF_REPO,
            "scenema-audio-pipeline.safetensors",
            local_dir=str(pipeline_ckpt.parent),
            token=token,
        )

    # VAE encoder (small, may already be baked)
    vae_ckpt = Path(os.environ.get(
        "VAE_ENCODER_CKPT",
        str(MODEL_DIR / "scenema-audio-vae-encoder.safetensors"),
    ))
    if not vae_ckpt.exists():
        logger.info("Downloading VAE encoder (~42 MB)...")
        hf_hub_download(
            HF_REPO,
            "scenema-audio-vae-encoder.safetensors",
            local_dir=str(vae_ckpt.parent),
            token=token,
        )

    # Gemma 3 12B IT. Fast low-VRAM mode defaults to the public NF4 checkpoint.
    gemma_root = Path(os.environ.get("GEMMA_ROOT", str(MODEL_DIR / "gemma-3-12b-it")))
    if not gemma_root.exists() or not any(gemma_root.glob("*.safetensors")):
        gemma_repo = os.environ.get("GEMMA_REPO")
        if not gemma_repo:
            gemma_repo = (
                DEFAULT_NF4_GEMMA_REPO
                if os.environ.get("GEMMA_QUANTIZE", "").lower() == "nf4"
                else DEFAULT_GEMMA_REPO
            )
        logger.info("Downloading Gemma from %s...", gemma_repo)
        snapshot_download(
            gemma_repo,
            local_dir=str(gemma_root),
            ignore_patterns=["*.gguf"],
            token=token,
        )

    # SeedVC
    seedvc_path = Path(os.environ.get("SEEDVC_PATH", "/app/seed-vc"))
    seedvc_cache = seedvc_path / "checkpoints"
    if not seedvc_cache.exists() or not any(seedvc_cache.glob("*.pth")):
        logger.info("Downloading SeedVC checkpoints (~1.6 GB)...")
        hf_cache = seedvc_cache / "hf_cache"
        hf_cache.mkdir(parents=True, exist_ok=True)
        os.environ["HF_HUB_CACHE"] = str(hf_cache)
        hf_hub_download(
            SEEDVC_REPO,
            "DiT_seed_v2_uvit_whisper_small_wavenet_bigvgan_pruned.pth",
            local_dir=str(seedvc_cache),
            token=token,
        )
        hf_hub_download(
            SEEDVC_REPO,
            "config_dit_mel_seed_uvit_whisper_small_wavenet.yml",
            local_dir=str(seedvc_cache),
            token=token,
        )
        snapshot_download(BIGVGAN_REPO, local_dir=str(hf_cache / "bigvgan"))
        snapshot_download(WHISPER_REPO, local_dir=str(hf_cache / "whisper-small"))


# ── FastAPI app ─────────────────────────────────────────────────

processor = AudioProcessor()
_semaphore = asyncio.Semaphore(1)
_progress: dict[str, dict] = {}
_cancelled: set[str] = set()


def _set_progress(job_id: str, payload: dict) -> None:
    _progress[job_id] = {
        "job_id": job_id,
        "percent": payload.get("percent", 0),
        "stage": payload.get("stage", "Queued"),
        "detail": payload.get("detail", ""),
        "ts": payload.get("ts", time.time()),
    }


def _save_output(job_id: str, audio_bytes: bytes | None, metadata: dict) -> dict:
    if not audio_bytes:
        return {}

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    seed = metadata.get("seed", "seed")
    stem = f"{stamp}-{job_id[:8]}-seed-{seed}"
    wav_path = OUTPUT_DIR / f"{stem}.wav"
    meta_path = OUTPUT_DIR / f"{stem}.json"

    wav_path.write_bytes(audio_bytes)
    meta = dict(metadata)
    meta.update(
        {
            "job_id": job_id,
            "saved_wav": str(wav_path),
            "saved_metadata": str(meta_path),
        }
    )
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Saved generation output: %s", wav_path)
    return {
        "saved_wav": str(wav_path),
        "saved_metadata": str(meta_path),
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    _download_models()
    processor.startup()
    logger.info("Scenema Audio ready on port %s", os.environ.get("PORT", "8000"))
    yield
    processor.shutdown()


app = FastAPI(title="Scenema Audio", lifespan=lifespan)

# ── Gradio UI (optional) ──────────────────────────────────────

if os.environ.get("ENABLE_GRADIO") == "1":
    try:
        import gradio as gr
        # app.py is at repo root, one level above src/
        import importlib.util
        _app_path = Path(__file__).resolve().parent.parent / "app.py"
        _spec = importlib.util.spec_from_file_location("gradio_app", _app_path)
        _mod = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        _demo = _mod.create_demo()
        app = gr.mount_gradio_app(app, _demo, path="/ui")
        logger.info("Gradio UI mounted at /ui")
    except ImportError:
        logger.warning(
            "ENABLE_GRADIO=1 but gradio is not installed. "
            "Install with: pip install gradio"
        )


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/progress/{job_id}")
async def progress(job_id: str):
    return _progress.get(
        job_id,
        {
            "job_id": job_id,
            "percent": 0,
            "stage": "Queued",
            "detail": "Waiting for worker",
            "ts": time.time(),
        },
    )


@app.post("/cancel/{job_id}")
async def cancel(job_id: str):
    _cancelled.add(job_id)
    _set_progress(
        job_id,
        {
            "percent": _progress.get(job_id, {}).get("percent", 0),
            "stage": "Cancelling",
            "detail": "Stop requested. Waiting for the current model step to return.",
        },
    )
    return {"status": "cancelling", "job_id": job_id}


def _run_job(job: ProcessJob):
    processor.progress_callback = lambda payload: _set_progress(job.job_id, payload)
    processor.cancel_callback = lambda: job.job_id in _cancelled
    try:
        return asyncio.run(processor.process(job))
    finally:
        processor.progress_callback = None
        processor.cancel_callback = None


@app.post("/generate")
async def generate(request: Request):
    body = await request.json()
    job_id = body.get("job_id") or str(uuid.uuid4())
    _set_progress(job_id, {"percent": 1, "stage": "Queued", "detail": "Request accepted"})

    job = ProcessJob(
        job_id=job_id,
        input=body,
    )

    async with _semaphore:
        if job_id in _cancelled:
            _cancelled.discard(job_id)
        result = await asyncio.to_thread(_run_job, job)

    if not result.success:
        if job_id in _cancelled:
            _cancelled.discard(job_id)
        _set_progress(
            job_id,
            {
                "percent": _progress.get(job_id, {}).get("percent", 0),
                "stage": "Failed",
                "detail": result.error or "Generation failed",
            },
        )
        return JSONResponse(
            status_code=500,
            content={
                "status": "failed",
                "error": result.error or "Generation failed",
            },
        )

    output = result.output
    audio_b64 = base64.b64encode(output.data).decode() if output.data else None
    metadata = output.metadata or {}
    saved = _save_output(job_id, output.data, metadata)
    if saved:
        metadata = dict(metadata)
        metadata.update(saved)
        _set_progress(
            job_id,
            {
                "percent": 100,
                "stage": "Complete",
                "detail": f"Saved to {saved['saved_wav']}",
            },
        )

    return {
        "status": "succeeded",
        "job_id": job_id,
        "audio": audio_b64,
        "content_type": output.content_type or "audio/wav",
        "metadata": metadata,
    }


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
