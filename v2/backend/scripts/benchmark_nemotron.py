#!/usr/bin/env python3
"""
Benchmark Nemotron-3.5-ASR q8_0 sur audio réel d'église.
Compare latence, RTF, qualité transcription, détection références bibliques.
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

# Ajout du backend au path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.nemotron_service import NemotronService
from app.services.verse_parser import VerseParserService


def load_wav_16k_mono(path: str) -> np.ndarray:
    """Charge un fichier WAV et retourne PCM float32 16kHz mono."""
    try:
        import wave

        with wave.open(path, "rb") as wf:
            n_channels = wf.getnchannels()
            sample_width = wf.getsampwidth()
            sample_rate = wf.getframerate()
            n_frames = wf.getnframes()
            raw = wf.readframes(n_frames)

            if sample_width == 2:
                pcm = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
            elif sample_width == 4:
                pcm = np.frombuffer(raw, dtype=np.float32)
            else:
                raise ValueError(f"Sample width non supporté : {sample_width}")

            if n_channels == 2:
                pcm = pcm.reshape(-1, 2).mean(axis=1)

            if sample_rate != 16000:
                ratio = 16000 / sample_rate
                n_new = int(len(pcm) * ratio)
                pcm = np.interp(
                    np.linspace(0, len(pcm) - 1, n_new),
                    np.arange(len(pcm)),
                    pcm,
                )

            return pcm.astype(np.float32)

    except Exception:
        import librosa

        pcm, sr = librosa.load(path, sr=16000, mono=True)
        return pcm.astype(np.float32)


def benchmark_streaming(
    audio_path: str,
    chunk_duration_ms: float = 80.0,
) -> dict:
    pcm = load_wav_16k_mono(audio_path)
    total_samples = len(pcm)
    duration_sec = total_samples / 16000.0
    chunk_samples = int(16000 * chunk_duration_ms / 1000.0)

    svc = NemotronService()
    if not svc.is_ready:
        print("Téléchargement du modèle Nemotron-3.5-ASR q8_0 GGUF...")
        svc.prepare(allow_download=True)
        while svc.downloading:
            time.sleep(0.5)

    print(f"Fichier : {audio_path}")
    print(f"Durée   : {duration_sec:.2f} s")
    print(f"Chunks  : {chunk_duration_ms:.0f} ms ({chunk_samples} échantillons)")

    if not svc.is_ready:
        print("❌ NemotronService non prêt (modèle ou parakeet.cpp absent).")
        return {"error": "not_ready"}

    svc.start()

    start_time = time.perf_counter()
    wall_clock_start = start_time

    final_text = ""
    time_to_first_word = None
    time_to_stable_reference = None

    parser = VerseParserService()

    for i in range(0, total_samples, chunk_samples):
        chunk = pcm[i : i + chunk_samples]
        svc.accept_waveform(chunk)

        text = svc.get_result()
        if text and text != final_text:
            final_text = text
            elapsed = time.perf_counter() - wall_clock_start

            if time_to_first_word is None and len(text.split()) >= 1:
                time_to_first_word = elapsed

            refs = parser.parse_incremental(text)
            if refs and time_to_stable_reference is None:
                time_to_stable_reference = elapsed

    svc.stop()

    end_time = time.perf_counter()
    inference_time = end_time - start_time
    rtf = inference_time / duration_sec

    result = {
        "audio_path": audio_path,
        "audio_duration_sec": round(duration_sec, 2),
        "inference_time_sec": round(inference_time, 2),
        "rtf": round(rtf, 3),
        "chunks_ms": chunk_duration_ms,
        "transcript": final_text.strip(),
        "time_to_first_word_sec": (
            round(time_to_first_word, 3) if time_to_first_word else None
        ),
        "time_to_stable_reference_sec": (
            round(time_to_stable_reference, 3)
            if time_to_stable_reference
            else None
        ),
        "model": "nemotron-3.5-asr-streaming-0.6b-Q8_0.gguf",
    }

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark Nemotron-3.5-ASR")
    parser.add_argument(
        "audio",
        nargs="?",
        default="tmp/test_youtube_1018.wav",
        help="Chemin vers le fichier WAV 16kHz mono",
    )
    parser.add_argument(
        "--chunk-ms",
        type=float,
        default=80.0,
        help="Taille des chunks audio en ms (défaut: 80)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default=None,
        help="Fichier JSON de sortie",
    )
    args = parser.parse_args()

    result = benchmark_streaming(args.audio, chunk_duration_ms=args.chunk_ms)

    print("\n" + "=" * 50)
    print("RÉSULTATS BENCHMARK NEMOTRON-3.5-ASR")
    print("=" * 50)
    for k, v in result.items():
        print(f"{k:30s} : {v}")

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"\nRésultats sauvegardés dans {args.output}")


if __name__ == "__main__":
    main()
