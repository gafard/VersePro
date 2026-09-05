"""
VersePro ASR Benchmark Harness
================================
Compare les moteurs ASR embarqués (Vosk, Faster-Whisper, MLX-Whisper, Sherpa-ONNX)
sur des extraits audio d'églises réels.

Mesures effectuées :
- Temps d'exécution total (s) & Real Time Factor (RTF = Temps / Durée Audio)
- Mots transcrits & Débit (mots/min)
- Références bibliques capturées par VersePro (BibleReferenceEngine)
- Précision du texte généré pour la détection
"""

import sys
import os
import time
import wave
import json
import asyncio
from pathlib import Path

# Ajouter le backend au chemin Python
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.verse_parser import VerseParserService
from app.services.semantic_search import LocalSemanticService
from app.services.verse_graph import VerseGraphService
from app.services.reference_engine import BibleReferenceEngine
from app.core.config import get_settings


def get_audio_duration_seconds(audio_path: str) -> float:
    """Calcule la durée exacte d'un fichier WAV."""
    try:
        with wave.open(audio_path, "rb") as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
            return frames / float(rate)
    except Exception:
        return 0.0


class ASRBenchmark:
    def __init__(self, audio_path: str):
        self.audio_path = Path(audio_path)
        self.duration_sec = get_audio_duration_seconds(str(self.audio_path))
        
        print("📚 Initialisation du moteur VersePro (Parser, Sémantique, Graph)...")
        self.settings = get_settings()
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

    async def benchmark_vosk(self):
        """Évalue Vosk Local (Modèle fr-0.22)."""
        print("\n" + "=" * 60)
        print("🎙️ TEST 1 : VOSK LOCAL (vosk-model-fr-0.22)")
        print("=" * 60)
        
        from app.services.vosk_service import VoskService
        vosk_svc = VoskService()
        if not vosk_svc.initialize(allow_download=True):
            print("❌ Vosk non disponible")
            return None

        wf = wave.open(str(self.audio_path), "rb")
        rec = vosk_svc.get_recognizer(wf.getframerate())
        
        start_time = time.time()
        mots_totaux = 0
        detections = []
        full_text = []

        while True:
            data = wf.readframes(4000)
            if len(data) == 0:
                break
            if rec.AcceptWaveform(data):
                res = json.loads(rec.Result())
                text = res.get("text", "").strip()
                if text:
                    full_text.append(text)
                    mots_totaux += len(text.split())
                    res_det = await self.engine.process(text, is_final=True, generation=1)
                    if res_det and res_det.get("detected") and res_det.get("reference"):
                        detections.append(res_det["reference"])

        final_res = json.loads(rec.FinalResult())
        text_f = final_res.get("text", "").strip()
        if text_f:
            full_text.append(text_f)
            mots_totaux += len(text_f.split())
            res_det = await self.engine.process(text_f, is_final=True, generation=1)
            if res_det and res_det.get("detected") and res_det.get("reference"):
                detections.append(res_det["reference"])

        elapsed = time.time() - start_time
        rtf = elapsed / max(self.duration_sec, 0.1)

        return {
            "name": "Vosk Local (fr-0.22)",
            "elapsed_sec": round(elapsed, 2),
            "rtf": round(rtf, 4),
            "total_words": mots_totaux,
            "detections_count": len(detections),
            "detections": detections,
            "sample_transcript": " ".join(full_text[:3])
        }

    async def benchmark_faster_whisper(self, model_size="small"):
        """Évalue Faster-Whisper (CTranslate2)."""
        print("\n" + "=" * 60)
        print(f"⚡ TEST 2 : FASTER-WHISPER ({model_size})")
        print("=" * 60)
        
        try:
            from faster_whisper import WhisperModel
        except ImportError:
            print("❌ faster_whisper non installé")
            return None

        print(f"📥 Chargement du modèle faster-whisper '{model_size}'...")
        # Sur Mac CPU / Metal, compute_type="float32" ou "int8"
        model = WhisperModel(model_size, device="cpu", compute_type="int8")
        
        start_time = time.time()
        segments, info = model.transcribe(str(self.audio_path), language="fr", beam_size=2)
        
        full_text = []
        mots_totaux = 0
        detections = []
        
        for segment in segments:
            text = segment.text.strip()
            if text:
                full_text.append(text)
                mots_totaux += len(text.split())
                res_det = await self.engine.process(text, is_final=True, generation=1)
                if res_det and res_det.get("detected") and res_det.get("reference"):
                    detections.append(res_det["reference"])

        elapsed = time.time() - start_time
        rtf = elapsed / max(self.duration_sec, 0.1)

        return {
            "name": f"Faster-Whisper ({model_size})",
            "elapsed_sec": round(elapsed, 2),
            "rtf": round(rtf, 4),
            "total_words": mots_totaux,
            "detections_count": len(detections),
            "detections": detections,
            "sample_transcript": " ".join(full_text[:3])
        }

    async def benchmark_mlx_whisper(self, model_path="mlx-community/whisper-small-mlx"):
        """Évalue MLX-Whisper (GPU Metal Apple Silicon)."""
        print("\n" + "=" * 60)
        print(f"🍏 TEST 3 : MLX-WHISPER ({model_path}) sur GPU Metal")
        print("=" * 60)
        
        try:
            import mlx_whisper
        except ImportError:
            print("❌ mlx_whisper non installé (requis sur Mac Apple Silicon)")
            return None

        start_time = time.time()
        result = mlx_whisper.transcribe(str(self.audio_path), path_or_hf_repo=model_path, language="fr")
        
        full_text = []
        mots_totaux = 0
        detections = []
        
        for segment in result.get("segments", []):
            text = segment.get("text", "").strip()
            if text:
                full_text.append(text)
                mots_totaux += len(text.split())
                res_det = await self.engine.process(text, is_final=True, generation=1)
                if res_det and res_det.get("detected") and res_det.get("reference"):
                    detections.append(res_det["reference"])

        elapsed = time.time() - start_time
        rtf = elapsed / max(self.duration_sec, 0.1)

        return {
            "name": f"MLX-Whisper ({model_path.split('/')[-1]})",
            "elapsed_sec": round(elapsed, 2),
            "rtf": round(rtf, 4),
            "total_words": mots_totaux,
            "detections_count": len(detections),
            "detections": detections,
            "sample_transcript": " ".join(full_text[:3])
        }

    async def benchmark_parakeet_tdt(self, model_name="nemo-parakeet-tdt-0.6b-v3"):
        """Évalue NVIDIA Parakeet TDT (onnx-asr)."""
        print("\n" + "=" * 60)
        print(f"🦜 TEST 4 : NVIDIA PARAKEET TDT ({model_name}) via ONNX")
        print("=" * 60)
        
        try:
            import onnx_asr
        except ImportError:
            print("❌ onnx_asr non installé")
            return None

        print(f"📥 Chargement de Parakeet TDT '{model_name}'...")
        try:
            model = onnx_asr.load_model(model_name)
        except Exception as e:
            print(f"⚠️ Erreur chargement Parakeet TDT: {e}")
            return None

        start_time = time.time()
        try:
            transcription = model.recognize(str(self.audio_path))
        except Exception as e:
            print(f"⚠️ Erreur inférence Parakeet: {e}")
            return None

        full_text = [transcription] if isinstance(transcription, str) else transcription
        mots_totaux = sum(len(t.split()) for t in full_text)
        detections = []

        for text in full_text:
            if text.strip():
                res_det = await self.engine.process(text, is_final=True, generation=1)
                if res_det and res_det.get("detected") and res_det.get("reference"):
                    detections.append(res_det["reference"])

        elapsed = time.time() - start_time
        rtf = elapsed / max(self.duration_sec, 0.1)

        return {
            "name": f"Parakeet TDT ({model_name})",
            "elapsed_sec": round(elapsed, 2),
            "rtf": round(rtf, 4),
            "total_words": mots_totaux,
            "detections_count": len(detections),
            "detections": detections,
            "sample_transcript": " ".join(full_text[:3])
        }



async def main():
    audio_file = "tmp/test_youtube_1018.wav"
    if not os.path.exists(audio_file):
        print(f"❌ Fichier {audio_file} introuvable.")
        return

    bench = ASRBenchmark(audio_file)
    print(f"⏱️ Durée de l'extrait audio : {bench.duration_sec:.2f} secondes ({bench.duration_sec/60:.2f} min)")

    results = []

    # 1. Vosk
    res_vosk = await bench.benchmark_vosk()
    if res_vosk:
        results.append(res_vosk)

    # 2. Faster-Whisper
    res_fw = await bench.benchmark_faster_whisper("small")
    if res_fw:
        results.append(res_fw)

    # 3. MLX-Whisper (désactivé pour le test hors-ligne)
    # res_mlx = await bench.benchmark_mlx_whisper("mlx-community/whisper-small-mlx")
    # if res_mlx:
    #     results.append(res_mlx)

    # 4. Parakeet TDT (NVIDIA ONNX)
    res_pk = await bench.benchmark_parakeet_tdt()
    if res_pk:
        results.append(res_pk)

    # Synthèse Finale
    print("\n" + "═" * 70)
    print("🏆 RÉSULTATS DU BENCHMARK ASR VERSEPRO")
    print("═" * 70)
    
    for r in results:
        print(f"\n🔹 MOTEUR : {r['name']}")
        print(f"   • Temps de calcul  : {r['elapsed_sec']} s (sur {bench.duration_sec:.1f} s audio)")
        print(f"   • RTF (Vitesse)    : {r['rtf']} (Plus bas est le mieux - < 1.0 = Temps Réel)")
        print(f"   • Mots transcrits  : {r['total_words']}")
        print(f"   • Versets Détectés : {r['detections_count']}")
        if r['detections']:
            for d in r['detections']:
                print(f"      - {d.get('reference')} (Couche: {d.get('detection_layer')}, Conf: {d.get('confidence')})")
        print(f"   • Aperçu Texte     : \"{r['sample_transcript'][:120]}...\"")

    print("\n" + "═" * 70)

if __name__ == "__main__":
    asyncio.run(main())
