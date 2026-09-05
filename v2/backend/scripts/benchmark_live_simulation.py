"""
VersePro Live Streaming Simulation Benchmark
=============================================
Simule un flux audio en direct (chunk par chunk) pour mesurer :
1. La Latence de Première Détection (Première fois que le verset est vu)
2. La Latence de Stabilisation (Dernier changement de la référence)
3. Le Nombre d'Oscillations / Répétitions (Stabilité)
4. La Précision finale (Exactitude de la détection)

Compare Faster-Whisper Small sous différentes fenêtres (0.8s, 1.2s, 1.5s, 2.0s) vs Vosk.
"""

import sys
import os
import time
import wave
import json
import asyncio
from pathlib import Path

# Ajouter le backend au path Python
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.verse_parser import VerseParserService
from app.services.semantic_search import LocalSemanticService
from app.services.verse_graph import VerseGraphService
from app.services.reference_engine import BibleReferenceEngine
from app.services.vosk_service import VoskService
from app.core.config import get_settings


class LiveStreamSimulator:
    def __init__(self, audio_path: str):
        self.audio_path = Path(audio_path)
        self.settings = get_settings()
        
        print("📚 Initialisation des services VersePro (Parser, Sémantique, Graph)...")
        self.verse_parser = VerseParserService()
        self.semantic_service = LocalSemanticService(self.verse_parser.bible_loader)
        self.semantic_service.initialize(allow_download=False)
        self.verse_graph = VerseGraphService(self.semantic_service)
        
        self.engine = BibleReferenceEngine(
            verse_parser=self.verse_parser,
            semantic_service=self.semantic_service,
            verse_graph=self.verse_graph,
            ai_service=None,
            settings=self.settings,
        )

    async def simulate_vosk(self):
        """Simulation Live avec Vosk (Baseline témoin)."""
        print("\n" + "=" * 60)
        print("🎙️ SIMULATION LIVE : VOSK LOCAL (Témoin)")
        print("=" * 60)
        
        vosk_svc = VoskService()
        if not vosk_svc.initialize(allow_download=True):
            return None

        wf = wave.open(str(self.audio_path), "rb")
        rec = vosk_svc.get_recognizer(wf.getframerate())
        
        start_time = time.time()
        first_detection_ms = None
        stable_detection_ms = None
        last_ref = None
        oscillations = 0
        detections = []

        sample_rate = wf.getframerate()
        chunk_samples = int(sample_rate * 0.1) # 100ms chunks
        
        bytes_read = 0
        total_audio_sec = wf.getnframes() / float(sample_rate)

        while True:
            data = wf.readframes(chunk_samples)
            if len(data) == 0:
                break
            bytes_read += len(data)
            current_audio_time_ms = (bytes_read / (sample_rate * 2)) * 1000.0

            if rec.AcceptWaveform(data):
                res = json.loads(rec.Result())
                text = res.get("text", "").strip()
                if text:
                    res_det = await self.engine.process(text, is_final=True, generation=1)
                    if res_det and res_det.get("detected") and res_det.get("reference"):
                        ref = res_det["reference"]
                        detections.append(ref)
                        if first_detection_ms is None:
                            first_detection_ms = current_audio_time_ms
                        if last_ref and last_ref != ref:
                            oscillations += 1
                        last_ref = ref
                        stable_detection_ms = current_audio_time_ms

        elapsed = time.time() - start_time
        return {
            "config": "Vosk Local (Baseline)",
            "first_detection_ms": round(first_detection_ms, 1) if first_detection_ms else "N/A",
            "stable_detection_ms": round(stable_detection_ms, 1) if stable_detection_ms else "N/A",
            "oscillations": oscillations,
            "final_reference": last_ref.get("reference") if last_ref else "Aucune",
            "elapsed_sec": round(elapsed, 2)
        }

    async def simulate_faster_whisper(self, model, window_sec: float, step_sec: float):
        """Simulation Live avec Faster-Whisper sous une fenêtre donnée."""
        config_name = f"Whisper Small (Fenêtre {window_sec}s, Pas {step_sec}s)"
        print("\n" + "=" * 60)
        print(f"⚡ SIMULATION LIVE : {config_name}")
        print("=" * 60)
        
        # Charger l'audio complet en mémoire pour découper virtuellement le flux
        import numpy as np
        wf = wave.open(str(self.audio_path), "rb")
        sample_rate = wf.getframerate()
        raw_bytes = wf.readframes(wf.getnframes())
        audio_np = np.frombuffer(raw_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        
        window_samples = int(window_sec * sample_rate)
        step_samples = int(step_sec * sample_rate)
        
        start_time = time.time()
        first_detection_ms = None
        stable_detection_ms = None
        last_ref = None
        oscillations = 0
        
        cursor = window_samples
        total_samples = len(audio_np)
        
        while cursor <= total_samples:
            current_audio_time_ms = (cursor / sample_rate) * 1000.0
            buffer_chunk = audio_np[max(0, cursor - window_samples):cursor]
            
            try:
                segments, _ = model.transcribe(buffer_chunk, language="fr", beam_size=1)
                text = " ".join(s.text.strip() for s in segments if s.text.strip())
            except Exception:
                text = ""

            if text:
                print(f"   [{current_audio_time_ms/1000.0:.1f}s] Text: '{text}'", flush=True)
                res_det = await self.engine.process(text, is_final=True, generation=1)
                if res_det and res_det.get("detected") and res_det.get("reference"):
                    ref = res_det["reference"]
                    print(f"   🎯 Détecté: {ref.get('reference')}", flush=True)
                    if first_detection_ms is None:
                        first_detection_ms = current_audio_time_ms
                    if last_ref and last_ref.get("reference") != ref.get("reference"):
                        oscillations += 1
                    last_ref = ref
                    stable_detection_ms = current_audio_time_ms

            cursor += step_samples

        print(f"  ✅ Test {config_name} terminé (1ère détection: {first_detection_ms} ms, Stable: {stable_detection_ms} ms)", flush=True)
        elapsed = time.time() - start_time
        return {
            "config": config_name,
            "first_detection_ms": round(first_detection_ms, 1) if first_detection_ms else "N/A",
            "stable_detection_ms": round(stable_detection_ms, 1) if stable_detection_ms else "N/A",
            "oscillations": oscillations,
            "final_reference": last_ref.get("reference") if last_ref else "Aucune",
            "elapsed_sec": round(elapsed, 2)
        }


async def main():
    audio_file = "tmp/test_ref_slice.wav"
    if not os.path.exists(audio_file):
        print(f"❌ Fichier {audio_file} introuvable.")
        return

    sim = LiveStreamSimulator(audio_file)
    results = []

    # 1. Vosk Baseline
    res_vosk = await sim.simulate_vosk()
    if res_vosk:
        results.append(res_vosk)

    # 2. Faster-Whisper Small avec différentes fenêtres
    try:
        from faster_whisper import WhisperModel
        print("📥 Pre-chargement du modèle Faster-Whisper Small...")
        fw_model = WhisperModel("small", device="cpu", compute_type="int8")
    except Exception as e:
        print(f"❌ Impossible de charger Faster-Whisper: {e}")
        fw_model = None

    if fw_model:
        windows = [
            (3.0, 0.5),
            (5.0, 0.5),
            (7.5, 0.5),
            (10.0, 0.5)
        ]

        for win, step in windows:
            res = await sim.simulate_faster_whisper(fw_model, win, step)
            if res:
                results.append(res)

    # Affichage du rapport comparatif Live
    print("\n" + "═" * 80)
    print("📊 RAPPORT DU BENCHMARK DE SIMULATION LIVE (RÉGIE TEMPS RÉEL)")
    print("═" * 80)
    print(f"{'Configuration Moteur':<38} | {'1ère Détect.':<12} | {'Stabilisation':<13} | {'Oscillations':<12} | {'Référence Détectée':<20}")
    print("─" * 105)

    for r in results:
        f_det = f"{r['first_detection_ms']} ms" if isinstance(r['first_detection_ms'], float) else str(r['first_detection_ms'])
        s_det = f"{r['stable_detection_ms']} ms" if isinstance(r['stable_detection_ms'], float) else str(r['stable_detection_ms'])
        print(f"{r['config']:<38} | {f_det:<12} | {s_det:<13} | {r['oscillations']:<12} | {r['final_reference']:<20}")

    print("═" * 105 + "\n")

if __name__ == "__main__":
    asyncio.run(main())
