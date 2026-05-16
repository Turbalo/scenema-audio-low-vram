# Copyright (c) 2026 Scenema AI
# https://scenema.ai
# SPDX-License-Identifier: MIT

"""Inference orchestration for Scenema Audio.

Generates audio for planned chunks with A2V voice conditioning between
chunks and concatenates the results. A2V reference from each chunk's tail
guides the next chunk toward a consistent voice, which SeedVC then
polishes for exact identity matching.
"""

import logging

import numpy as np

from .audio_utils import normalize_volume, trim_silence
from .chunker import ChunkSpec
from .engine import AudioEngine, AudioResult
from .whisper_aligner import validate_text

logger = logging.getLogger(__name__)

REF_TAIL_SECONDS = 3.0
MAX_RETRIES = 3
RETRY_DURATION_FACTOR = 1.3
MIN_WORD_MATCH_RATIO = 0.90


def generate_chunks(
    engine: AudioEngine,
    chunks: list[ChunkSpec],
    ref_latent=None,
    ref_duration_s: float = REF_TAIL_SECONDS,
    validate: bool = False,
    min_match_ratio: float = MIN_WORD_MATCH_RATIO,
    anchor_ref: bool = False,
    progress_callback=None,
) -> list[AudioResult]:
    """Generate audio for all chunks with A2V voice conditioning.

    Each chunk gets its own Gemma encode (since each has different text).
    The tail of each chunk's audio is encoded via Audio VAE and used as
    A2V reference for the next chunk, guiding voice consistency. SeedVC
    is applied afterward by the processor for exact identity matching.

    Args:
        engine: AudioEngine instance
        chunks: List of ChunkSpec from plan_chunks()
        ref_latent: Initial reference latent (from user-provided voice URL)
        ref_duration_s: Seconds of tail audio to use as A2V reference
        validate: If True, run Whisper validation with retry loop.
            If False (default), generate once without validation.
        anchor_ref: If True, every chunk uses ref_latent instead of
            chaining from the previous chunk's tail. Keeps voice
            anchored to the external reference.
    """
    results: list[AudioResult] = []
    encoded_contexts: list[tuple[object, object]] = []

    # Text embeddings are independent across chunks, while A2V reference
    # chaining depends on generated audio. Encode all prompts first so Gemma
    # can be loaded once, then unloaded before Scenema audio diffusion starts.
    engine.begin_text_encode_batch()
    try:
        for i, chunk in enumerate(chunks):
            base_percent = 20 + int((i / max(len(chunks), 1)) * 16)
            logger.info("Compiled prompt: %s", chunk.compiled_prompt)
            if progress_callback:
                progress_callback(
                    base_percent,
                    f"Chunk {i + 1}/{len(chunks)}: text encoding",
                    "Gemma batch encoding",
                )
            encoded_contexts.append(engine.encode_text(chunk.compiled_prompt))
    finally:
        engine.end_text_encode_batch()

    for i, chunk in enumerate(chunks):
        base_percent = 36 + int((i / max(len(chunks), 1)) * 32)
        next_percent = 36 + int(((i + 1) / max(len(chunks), 1)) * 32)
        label = "with ref" if ref_latent is not None else "no ref"
        logger.info(
            "Chunk %d/%d (%s, %.1fs): %s",
            i + 1,
            len(chunks),
            label,
            chunk.duration_s,
            chunk.expected_text[:60] + ("..." if len(chunk.expected_text) > 60 else ""),
        )

        # Gemma embeddings were precomputed for all chunks and are reused across retries.
        vc, ac = encoded_contexts[i]

        duration = chunk.duration_s
        seed = chunk.seed

        if not validate:
            # Single generation, no whisper validation
            if progress_callback:
                progress_callback(
                    min(next_percent - 4, base_percent + 12),
                    f"Chunk {i + 1}/{len(chunks)}: audio diffusion",
                    f"Generating {duration:.1f}s",
                )
            result = engine.generate(vc, ac, duration, seed, ref_latent=ref_latent)
            best_result = result
        else:
            # Validation retry loop with whisper
            best_result = None
            best_ratio = -1.0

            for attempt in range(MAX_RETRIES + 1):
                if progress_callback:
                    progress_callback(
                        min(next_percent - 6, base_percent + 10 + attempt * 2),
                        f"Chunk {i + 1}/{len(chunks)}: audio diffusion",
                        f"Attempt {attempt + 1}/{MAX_RETRIES + 1}, {duration:.1f}s",
                    )
                result = engine.generate(vc, ac, duration, seed, ref_latent=ref_latent)

                if progress_callback:
                    progress_callback(
                        min(next_percent - 3, base_percent + 16 + attempt * 2),
                        f"Chunk {i + 1}/{len(chunks)}: validation",
                        "Checking generated speech with Whisper",
                    )
                passed, transcribed, ratio = validate_text(
                    result.waveform_np,
                    result.sample_rate,
                    chunk.expected_text,
                    language=chunk.language,
                    min_word_ratio=min_match_ratio,
                )

                if ratio > best_ratio:
                    best_result = result
                    best_ratio = ratio

                if passed:
                    logger.info(
                        "  Chunk %d validated: %.0f%% word match",
                        i + 1,
                        ratio * 100,
                    )
                    break

                if attempt < MAX_RETRIES:
                    duration = min(duration * RETRY_DURATION_FACTOR, 20.0)
                    seed += 1
                    logger.info(
                        "  Chunk %d retry %d: %.0f%% match, extending to %.1fs, seed=%d",
                        i + 1,
                        attempt + 1,
                        ratio * 100,
                        duration,
                        seed,
                    )
                else:
                    logger.warning(
                        "  Chunk %d: best %.0f%% match after %d retries, accepting",
                        i + 1,
                        best_ratio * 100,
                        MAX_RETRIES,
                    )

        results.append(best_result)

        # A2V: use tail of this chunk as reference for the next
        # In anchor mode, keep using the original ref_latent for every chunk
        if i < len(chunks) - 1 and not anchor_ref:
            if progress_callback:
                progress_callback(
                    next_percent - 1,
                    f"Chunk {i + 1}/{len(chunks)}: reference latent",
                    "Encoding tail for voice consistency",
                )
            tail_samples = int(ref_duration_s * result.sample_rate)
            tail_wav = result.waveform_np[-tail_samples:]
            ref_latent = engine.encode_reference(tail_wav, result.sample_rate)

        if progress_callback:
            progress_callback(
                next_percent,
                f"Chunk {i + 1}/{len(chunks)} complete",
                "Moving to next stage",
            )

    return results


def concatenate_chunks(
    results: list[AudioResult],
    trim: bool = True,
    normalize: bool = True,
) -> tuple[np.ndarray, int]:
    """Concatenate audio chunks with silence trimming and volume normalization.

    Trims excess silence from chunk boundaries and normalizes volume
    per-chunk to ensure consistent loudness across the full output.
    Chunks are hard-concatenated (no crossfade).

    Args:
        results: List of AudioResult from generate_chunks().
        trim: Whether to trim silence from chunk boundaries.
        normalize: Whether to normalize volume per chunk.

    Returns:
        Tuple of (concatenated waveform numpy array, sample_rate).
    """
    if not results:
        raise ValueError("No chunks to concatenate")

    sr = results[0].sample_rate
    processed: list[np.ndarray] = []

    for i, r in enumerate(results):
        w = r.waveform_np
        if trim:
            w = trim_silence(w, sr, max_silence=0.5)
        if normalize:
            w = normalize_volume(w, sr)
        processed.append(w)
        logger.debug(
            "Chunk %d: %.1fs -> %.1fs",
            i,
            r.duration_s,
            w.shape[0] / sr,
        )

    result = np.concatenate(processed, axis=0)
    logger.info(
        "Concatenated: %.1fs from %d chunks", result.shape[0] / sr, len(processed)
    )
    return result, sr
