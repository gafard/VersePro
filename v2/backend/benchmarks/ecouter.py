"""Écouter un vrai enregistrement, et voir ce que VersePro en aurait fait.

Le corpus de rejeu éprouve la détection sur des phrases isolées. Il ne dit
rien de la question qui décide de tout : **que se passe-t-il pendant une
prédication entière, avec le son d'une vraie salle ?**

Cet outil répond à ça. Il prend un enregistrement dans n'importe quel format,
le fait passer par la chaîne complète — voix → Vosk → cascade de détection —
et rend la chronologie de ce qui aurait été projeté, minute par minute.

    python3 benchmarks/ecouter.py culte.mp3

C'est volontairement une OBSERVATION, pas une note. Personne ne connaît la
vérité terrain d'une prédication d'une heure : compter un « taux de réussite »
supposerait qu'on ait relevé à la main chaque verset cité. Ce que l'outil
donne, c'est ce que l'opérateur aurait vu — et c'est à l'œil humain de dire
si c'est juste. Les détections douteuses se transforment ensuite en cas de
corpus, où elles deviennent des tests permanents.

Vie privée — les mêmes règles que le corpus (voir corpus/README.md) :
l'enregistrement reste sur la machine, rien n'est envoyé nulle part, et aucun
audio n'est versionné. La transcription produite contient la parole de
l'assemblée : traitez-la comme telle.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
import tempfile
import wave
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import main as runtime
from app.core.config import settings
from app.services.semantic_search import LocalSemanticService
from app.services.reference_engine import BibleReferenceEngine
from app.services.verse_graph import VerseGraphService
from app.services.transcription_health import SanteTranscription
from app.services.verse_parser import VerseParserService

# Vosk veut du mono 16 bits ; 16 kHz est la fréquence des modèles français.
FREQUENCE = 16000


def convertir(source: Path, destination: Path) -> None:
    """N'importe quel format vers le WAV que Vosk attend, via ffmpeg."""
    subprocess.run(
        ["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-i", str(source),
         "-ac", "1", "-ar", str(FREQUENCE), "-sample_fmt", "s16", str(destination)],
        check=True,
    )


def _horodater(secondes: float) -> str:
    return f"{int(secondes) // 60:02d}:{int(secondes) % 60:02d}"


def transcrire_par_segments_nemotron(wav: Path) -> List[Dict[str, Any]]:
    """Même contrat que la version Vosk, avec le moteur Nemotron.

    Permet de comparer les deux moteurs sur le MÊME enregistrement et la même
    cascade — c'est la seule façon honnête de savoir si le changement de moteur
    apporte quelque chose en conditions réelles.
    """
    import numpy as np
    from app.services.nemotron_service import NemotronService

    service = NemotronService()
    service.start()
    segments: List[Dict[str, Any]] = []
    ecoule = 0.0
    with wave.open(str(wav), "rb") as flux:
        while True:
            donnees = flux.readframes(4000)
            if not donnees:
                break
            echantillons = np.frombuffer(donnees, dtype=np.int16)
            service.accept_waveform(echantillons)
            ecoule += echantillons.size / FREQUENCE
            enonce = service.prendre_enonce_fini()
            if enonce:
                segments.append({"texte": enonce, "debut": ecoule, "fin": ecoule,
                                 "conf_moy": None, "conf_min": None,
                                 "mots": len(enonce.split())})
    service.stop()
    reste = service.prendre_enonce_fini()
    if reste:
        segments.append({"texte": reste, "debut": ecoule, "fin": ecoule,
                         "conf_moy": None, "conf_min": None, "mots": len(reste.split())})
    return segments


def transcrire_par_segments(wav: Path) -> List[Dict[str, Any]]:
    """Transcrit en gardant le DÉCOUPAGE et les horodatages de Vosk.

    Le direct n'analyse pas un bloc de texte d'une heure : il analyse au fil
    des énoncés. On rejoue donc segment par segment, sinon la mesure ne dirait
    rien du comportement réel.
    """
    from app.services.vosk_service import VoskService

    service = VoskService()
    if not service.initialize(allow_download=False):
        raise SystemExit("Modèle Vosk absent : installez-le depuis les paramètres.")

    with wave.open(str(wav), "rb") as flux:
        recogniseur = service.get_recognizer(flux.getframerate())
        if recogniseur is None:
            raise SystemExit("Vosk n'a pas produit de reconnaisseur.")
        try:
            recogniseur.SetWords(True)
        except Exception:  # pragma: no cover - selon la version de vosk
            pass

        segments: List[Dict[str, Any]] = []

        def retenir(brut: str) -> None:
            donnees = json.loads(brut or "{}")
            texte = (donnees.get("text") or "").strip()
            if not texte:
                return
            mots = donnees.get("result") or []
            confs = [float(m.get("conf", 0.0)) for m in mots]
            segments.append({
                "texte": texte,
                "debut": float(mots[0]["start"]) if mots else None,
                "fin": float(mots[-1]["end"]) if mots else None,
                # Ce que Vosk pense de lui-même : on le garde pour pouvoir
                # mesurer si sa propre incertitude prédit nos faux positifs.
                "conf_moy": round(sum(confs) / len(confs), 3) if confs else None,
                "conf_min": round(min(confs), 3) if confs else None,
                "mots": len(mots),
            })

        while True:
            donnees = flux.readframes(4000)
            if not donnees:
                break
            if recogniseur.AcceptWaveform(donnees):
                retenir(recogniseur.Result())
        retenir(recogniseur.FinalResult())
    return segments


async def ecouter(source: Path, garder_wav: Optional[Path] = None,
                  moteur: str = "vosk") -> Dict[str, Any]:
    parser = VerseParserService()
    semantique = LocalSemanticService(parser.bible_loader)
    semantique.initialize(allow_download=False)
    graphe = VerseGraphService(semantique)
    cascade = BibleReferenceEngine(
        verse_parser=parser,
        semantic_service=semantique,
        verse_graph=graphe,
        ai_service=None,
        settings=settings,
    )
    settings.AI_AGENT_ENABLED = False  # on mesure la chaîne LOCALE
    sante = SanteTranscription()
    cascade.sante_transcription = sante

    with tempfile.TemporaryDirectory() as temporaire:
        wav = Path(garder_wav) if garder_wav else Path(temporaire) / "audio.wav"
        print(f"  conversion  : {source.name} → mono {FREQUENCE} Hz…")
        convertir(source, wav)
        duree = wave.open(str(wav), "rb").getnframes() / FREQUENCE
        print(f"  durée       : {_horodater(duree)}")
        print(f"  transcription ({moteur})… cela prend un moment.")
        segments = (transcrire_par_segments_nemotron(wav) if moteur == "nemotron"
                    else transcrire_par_segments(wav))

    print(f"  segments    : {len(segments)}\n")

    detections: List[Dict[str, Any]] = []
    for segment in segments:
        # Comme le direct : chaque segment nourrit la mesure de santé AVANT
        # d'être analysé, jamais après — sinon on jugerait la phrase courante
        # sur une statistique qui l'inclut déjà.
        sante.noter(segment["texte"])
        resultat = await cascade.detecter_sans_effet(segment["texte"], final_state=True)
        if not resultat:
            continue
        # L'ancre se pose comme dans le direct : une citation énoncée ouvre un
        # passage pour les allusions des minutes qui suivent. C'est le service
        # qui décide ce qui fait ancre — le rejeu ne doit pas préfiltrer, sinon
        # il mesure sa propre règle au lieu de celle du produit.
        graphe.ancrer(resultat)
        detections.append({
            "quand": _horodater(segment["debut"] or 0),
            "reference": resultat.get("reference"),
            "etage": resultat.get("detection_method"),
            "confiance": round(float(resultat.get("confidence") or 0), 3),
            "conf_asr": segment.get("conf_moy"),
            "mots": segment.get("mots"),
            "extrait": segment["texte"][:120],
        })

    return {
        "source": source.name,
        "moteur": moteur,
        "duree_s": round(duree, 1),
        "segments": len(segments),
        "detections": detections,
        "sante": sante.etat(),
        "transcription": " ".join(s["texte"] for s in segments),
    }


def afficher(rapport: Dict[str, Any]) -> None:
    detections = rapport["detections"]
    print(f"── {len(detections)} détection(s) sur {rapport['segments']} segments\n")
    for d in detections:
        print(f"  {d['quand']}  {d['reference']:<24} {d['etage']:<18} {d['confiance']:.2f}")
        print(f"         « {d['extrait']} »")
    if not detections:
        print("  (aucune détection — vérifiez la transcription avant de conclure)")
    par_etage: Dict[str, int] = {}
    for d in detections:
        par_etage[d["etage"]] = par_etage.get(d["etage"], 0) + 1
    if par_etage:
        print("\n  par étage :", ", ".join(f"{k} {v}" for k, v in sorted(par_etage.items())))
    print("\n  ⚠️  Ceci est une OBSERVATION, pas un score : la vérité terrain de")
    print("      cet enregistrement n'est pas connue. Relisez la chronologie,")
    print("      puis figez les erreurs en cas de corpus avec --capturer.")


def main() -> int:
    analyseur = argparse.ArgumentParser(
        description="Faire passer un vrai enregistrement dans toute la chaîne VersePro.")
    analyseur.add_argument("audio", type=Path, help="enregistrement (mp3, m4a, mp4, wav…)")
    analyseur.add_argument("--sortie", type=Path, help="où écrire le rapport JSON")
    analyseur.add_argument("--moteur", choices=("vosk", "nemotron"), default="vosk",
                           help="moteur de transcription à éprouver")
    analyseur.add_argument("--garder-wav", type=Path,
                           help="conserver le WAV converti (utile pour découper des cas)")
    args = analyseur.parse_args()

    if not args.audio.is_file():
        print(f"Fichier introuvable : {args.audio}", file=sys.stderr)
        return 2

    print(f"\nÉcoute — {args.audio.name}\n")
    rapport = asyncio.run(ecouter(args.audio, args.garder_wav, args.moteur))
    afficher(rapport)

    if args.sortie:
        args.sortie.write_text(json.dumps(rapport, ensure_ascii=False, indent=2),
                               encoding="utf-8")
        print(f"\n  rapport écrit : {args.sortie}")
        print("  (il contient la transcription : c'est de la parole d'assemblée)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
