#!/usr/bin/env python3
"""Replay Lab — rejouer un culte dans toute la chaîne, et comparer.

Le banc de détection existant (`run_detection_benchmark.py`) part d'un texte
déjà transcrit : il éprouve la cascade de détection, pas l'écoute. Or ce que
VersePro n'a jamais prouvé, c'est justement sa tenue sur du VRAI son d'église —
accents, débit, réverbération, musique de fond, micro saturé.

Ce module ajoute les trois capacités qui manquaient :

  1. le rejeu AUDIO — un enregistrement traverse l'ASR local puis la cascade,
     exactement comme un dimanche matin ;
  2. la COMPARAISON de deux exécutions — ce qui s'est amélioré, ce qui a
     régressé, cas par cas ; sans elle, « ça marche mieux » reste une opinion ;
  3. la capture d'INCIDENT — un raté observé en culte devient un cas
     permanent, donc une régression impossible à réintroduire en silence.

Le rejeu texte reste possible et rapide : il tourne sans modèle et convient à
l'intégration continue. Le rejeu audio demande Vosk installé, et il est lent —
c'est le prix du réalisme.

Usage :
    python3 benchmarks/replay_lab.py --corpus corpus/ --sortie run.json
    python3 benchmarks/replay_lab.py --comparer avant.json apres.json
    python3 benchmarks/replay_lab.py --capturer "texte entendu" --attendu "Jn 3:16"
"""

import argparse
import asyncio
import json
import statistics
import sys
import time
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import main as runtime
from app.core.config import settings
from app.services.semantic_search import LocalSemanticService
from app.services.reference_engine import BibleReferenceEngine
from app.services.verse_graph import VerseGraphService
from app.services.verse_parser import VerseParserService

RACINE_CORPUS = Path(__file__).resolve().parents[1] / "corpus"


class IANeutralisee:
    """L'IA cloud est écartée du rejeu : elle rendrait les mesures
    non reproductibles et coûterait un appel payant par cas."""
    enabled = False


# ── Corpus ───────────────────────────────────────────────────────────────────

def charger_corpus(racine: Path) -> List[Dict[str, Any]]:
    """Lit les cas d'un corpus. Un cas = un dossier avec `cas.json`.

    Le format reste volontairement proche de celui du banc existant — texte,
    attendu, nature — pour qu'un cas puisse être promu de texte à audio sans
    être réécrit.
    """
    cas: List[Dict[str, Any]] = []
    dossier_cas = racine / "cas"
    if not dossier_cas.is_dir():
        return cas
    for chemin in sorted(dossier_cas.iterdir()):
        fiche = chemin / "cas.json"
        if not fiche.is_file():
            continue
        try:
            donnees = json.loads(fiche.read_text(encoding="utf-8"))
        except ValueError as exc:
            print(f"  ⚠️  {chemin.name} illisible : {exc}", file=sys.stderr)
            continue
        donnees["id"] = chemin.name
        donnees["dossier"] = chemin
        audio = chemin / "audio.wav"
        donnees["audio"] = audio if audio.is_file() else None
        cas.append(donnees)
    return cas


def charger_cas_plats(chemin: Path) -> List[Dict[str, Any]]:
    """Compatibilité avec `sermon_cases.json` : une liste plate de cas texte."""
    donnees = json.loads(chemin.read_text(encoding="utf-8"))
    for index, cas in enumerate(donnees):
        cas.setdefault("id", f"{chemin.stem}-{index:03d}")
        cas["audio"] = None
        cas.setdefault("conditions", {})
    return donnees


# ── Transcription d'un cas audio ─────────────────────────────────────────────

def transcrire(audio: Path) -> Optional[str]:
    """Fait passer un WAV par Vosk, comme le ferait le direct.

    Renvoie None si Vosk n'est pas installé : le cas est alors ignoré plutôt
    que compté en échec — un modèle absent n'est pas une régression de
    détection, et le confondre fausserait toutes les mesures.
    """
    try:
        from app.services.vosk_service import VoskService
    except ImportError:
        return None
    service = VoskService()
    if not service.initialize(allow_download=False):
        return None

    with wave.open(str(audio), "rb") as flux:
        if flux.getnchannels() != 1 or flux.getsampwidth() != 2:
            raise ValueError(
                f"{audio.name} : le rejeu attend du WAV mono 16 bits "
                f"(reçu {flux.getnchannels()} canaux, {flux.getsampwidth() * 8} bits)"
            )
        recogniseur = service.get_recognizer(flux.getframerate())
        if recogniseur is None:
            return None
        morceaux: List[str] = []
        while True:
            donnees = flux.readframes(4000)
            if not donnees:
                break
            if recogniseur.AcceptWaveform(donnees):
                morceaux.append(json.loads(recogniseur.Result()).get("text", ""))
        morceaux.append(json.loads(recogniseur.FinalResult()).get("text", ""))
    return " ".join(m for m in morceaux if m).strip()


# ── Exécution ────────────────────────────────────────────────────────────────

async def _canonique(parser: VerseParserService, reference: Optional[str]):
    if not reference:
        return None
    parsed = await parser.parse(reference, skip_text_search=True)
    if not parsed:
        return None
    return (parsed.get("book_abbr"), parsed.get("chapter"),
            parsed.get("verse_start"), parsed.get("verse_end"))


async def rejouer(cas: List[Dict[str, Any]], avec_audio: bool = True,
                  avec_graphe: bool = True) -> Dict[str, Any]:
    parser = VerseParserService()
    semantique = LocalSemanticService(parser.bible_loader)
    semantique.initialize(allow_download=False)
    graphe = VerseGraphService(semantique)

    # La cascade vit dans BibleReferenceEngine depuis le découplage ASR. On
    # instancie le moteur ICI plutôt que de câbler des globales sur `main` :
    # la mesure montre alors exactement quels services y entrent.
    moteur = BibleReferenceEngine(
        verse_parser=parser,
        semantic_service=semantique,
        verse_graph=graphe if avec_graphe else None,
        ai_service=IANeutralisee(),
        settings=settings,
    )
    settings.AI_AGENT_ENABLED = False

    lignes: List[Dict[str, Any]] = []
    latences: List[float] = []
    ignores = 0

    for item in cas:
        texte = item.get("text")
        source = "texte"
        if avec_audio and item.get("audio") is not None:
            transcrit = transcrire(item["audio"])
            if transcrit is None:
                ignores += 1
                continue
            texte, source = transcrit, "audio"
        if not texte:
            ignores += 1
            continue

        # Un cas peut déclarer le passage que le prédicateur venait d'ouvrir
        # (« ancre »: « Exode 17 »). Il est rejoué comme le direct le ferait :
        # on fait passer la référence par l'étage explicite, et c'est SON
        # résultat qui pose l'ancre — jamais une valeur écrite à la main.
        graphe.oublier()
        if item.get("ancre"):
            amorce = await parser.parse(f"{item['ancre']} verset 1", skip_text_search=True)
            if not graphe.ancrer(amorce):
                print(f"  ⚠️  ancre « {item['ancre']} » non reconnue ({item.get('id')})",
                      file=sys.stderr)

        attendu = await _canonique(parser, item.get("expected"))
        depart = time.perf_counter()
        resultat = await moteur.detecter_sans_effet(texte, final_state=True)
        latence = (time.perf_counter() - depart) * 1000
        latences.append(latence)

        predit_brut = resultat.get("reference") if resultat else None
        predit = await _canonique(parser, predit_brut)
        lignes.append({
            "id": item.get("id"),
            "source": source,
            "kind": item.get("kind", "inconnu"),
            "conditions": item.get("conditions", {}),
            "texte": texte[:200],
            "attendu": item.get("expected"),
            "predit": predit_brut,
            "etage": (resultat or {}).get("detection_method"),
            "ancre": item.get("ancre"),
            "ok": predit == attendu,
            "latence_ms": round(latence, 2),
        })

    justes = sum(1 for l in lignes if l["ok"])
    vp = sum(1 for l in lignes if l["ok"] and l["attendu"])
    fp = sum(1 for l in lignes if not l["ok"] and l["predit"])
    fn = sum(1 for l in lignes if not l["ok"] and l["attendu"])
    precision = vp / (vp + fp) if vp + fp else 1.0
    rappel = vp / (vp + fn) if vp + fn else 1.0

    return {
        "horodatage": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "cas_joues": len(lignes),
        "cas_ignores": ignores,
        "exactitude": round(justes / len(lignes), 4) if lignes else 0.0,
        "precision": round(precision, 4),
        "rappel": round(rappel, 4),
        "f1": round(2 * precision * rappel / (precision + rappel), 4) if precision + rappel else 0.0,
        "latence_p50": round(statistics.median(latences), 2) if latences else 0.0,
        "latence_p95": round(sorted(latences)[min(len(latences) - 1, round((len(latences) - 1) * 0.95))], 2) if latences else 0.0,
        "semantique_active": semantique.initialized,
        "lignes": lignes,
    }


# ── Comparaison de deux exécutions ───────────────────────────────────────────

def comparer(avant: Dict[str, Any], apres: Dict[str, Any]) -> Dict[str, Any]:
    """Ce qui a changé, cas par cas. C'est ici que « ça marche mieux » cesse
    d'être une impression : une régression est nommée, pas ressentie."""
    par_id_avant = {l["id"]: l for l in avant.get("lignes", [])}
    par_id_apres = {l["id"]: l for l in apres.get("lignes", [])}
    communs = set(par_id_avant) & set(par_id_apres)

    regressions, gains = [], []
    for identifiant in sorted(communs):
        a, b = par_id_avant[identifiant], par_id_apres[identifiant]
        if a["ok"] and not b["ok"]:
            regressions.append({"id": identifiant, "attendu": a["attendu"],
                                "etait": a["predit"], "devient": b["predit"]})
        elif not a["ok"] and b["ok"]:
            gains.append({"id": identifiant, "attendu": b["attendu"], "etait": a["predit"]})

    return {
        "regressions": regressions,
        "gains": gains,
        "exactitude_avant": avant.get("exactitude"),
        "exactitude_apres": apres.get("exactitude"),
        "latence_p95_avant": avant.get("latence_p95"),
        "latence_p95_apres": apres.get("latence_p95"),
        "cas_absents_apres": sorted(set(par_id_avant) - set(par_id_apres)),
    }


# ── Capture d'incident ───────────────────────────────────────────────────────

def capturer(texte: str, attendu: Optional[str], nature: str,
             conditions: Optional[Dict[str, Any]] = None,
             racine: Path = RACINE_CORPUS) -> Path:
    """Fige un raté observé en culte sous forme de cas permanent.

    C'est le geste qui fait grandir le corpus sans effort : ce qui a échoué une
    fois ne peut plus échouer en silence.
    """
    dossier = racine / "cas"
    dossier.mkdir(parents=True, exist_ok=True)
    horodatage = datetime.now().strftime("%Y%m%d-%H%M%S")
    cible = dossier / f"incident-{horodatage}"
    cible.mkdir()
    (cible / "cas.json").write_text(json.dumps({
        "text": texte,
        "expected": attendu,
        "kind": nature,
        "conditions": conditions or {},
        "origine": "incident capturé en culte",
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return cible


# ── Ligne de commande ────────────────────────────────────────────────────────

def _resume(rapport: Dict[str, Any]) -> None:
    print(f"  cas joués      : {rapport['cas_joues']}"
          + (f"  (ignorés : {rapport['cas_ignores']})" if rapport["cas_ignores"] else ""))
    print(f"  exactitude     : {rapport['exactitude'] * 100:.1f} %")
    print(f"  précision      : {rapport['precision'] * 100:.1f} %")
    print(f"  rappel         : {rapport['rappel'] * 100:.1f} %")
    print(f"  latence p50/p95: {rapport['latence_p50']} / {rapport['latence_p95']} ms")
    print(f"  sémantique     : {'active' if rapport['semantique_active'] else 'absente'}")
    rates = [l for l in rapport["lignes"] if not l["ok"]]
    if rates:
        print(f"\n  {len(rates)} cas manqués :")
        for ligne in rates[:12]:
            print(f"    {ligne['id']:28} attendu {ligne['attendu']!s:14} → {ligne['predit']}")


def main() -> int:
    analyseur = argparse.ArgumentParser(description="Replay Lab de VersePro")
    analyseur.add_argument("--corpus", type=Path, help="dossier de corpus à rejouer")
    analyseur.add_argument("--cas", type=Path, help="fichier de cas plats (sermon_cases.json)")
    analyseur.add_argument("--sortie", type=Path, help="où écrire le rapport JSON")
    analyseur.add_argument("--sans-audio", action="store_true",
                           help="ignorer l'audio et ne rejouer que le texte (rapide)")
    analyseur.add_argument("--sans-graphe", action="store_true",
                           help="désactiver VerseGraph, pour mesurer son apport réel")
    analyseur.add_argument("--comparer", nargs=2, type=Path, metavar=("AVANT", "APRÈS"))
    analyseur.add_argument("--capturer", metavar="TEXTE")
    analyseur.add_argument("--attendu", metavar="RÉFÉRENCE")
    analyseur.add_argument("--nature", default="incident")
    args = analyseur.parse_args()

    if args.comparer:
        avant = json.loads(args.comparer[0].read_text(encoding="utf-8"))
        apres = json.loads(args.comparer[1].read_text(encoding="utf-8"))
        diff = comparer(avant, apres)
        print("Comparaison de deux exécutions")
        print(f"  exactitude : {diff['exactitude_avant'] * 100:.1f} % → {diff['exactitude_apres'] * 100:.1f} %")
        print(f"  latence p95: {diff['latence_p95_avant']} → {diff['latence_p95_apres']} ms")
        if diff["regressions"]:
            print(f"\n  ⚠️  {len(diff['regressions'])} RÉGRESSIONS :")
            for r in diff["regressions"]:
                print(f"    {r['id']:28} {r['attendu']} : {r['etait']} → {r['devient']}")
        else:
            print("\n  aucune régression")
        if diff["gains"]:
            print(f"\n  ✅ {len(diff['gains'])} cas réparés :")
            for g in diff["gains"]:
                print(f"    {g['id']:28} {g['attendu']} (était : {g['etait']})")
        if diff["cas_absents_apres"]:
            print(f"\n  cas disparus du corpus : {', '.join(diff['cas_absents_apres'])}")
        return 1 if diff["regressions"] else 0

    if args.capturer:
        cible = capturer(args.capturer, args.attendu, args.nature)
        print(f"Incident figé en cas permanent : {cible}")
        return 0

    cas: List[Dict[str, Any]] = []
    if args.cas:
        cas += charger_cas_plats(args.cas)
    if args.corpus:
        cas += charger_corpus(args.corpus)
    if not cas:
        analyseur.error("aucun cas : précisez --corpus ou --cas")

    print(f"Replay Lab — {len(cas)} cas")
    rapport = asyncio.run(rejouer(cas, avec_audio=not args.sans_audio, avec_graphe=not args.sans_graphe))
    _resume(rapport)
    if args.sortie:
        args.sortie.write_text(json.dumps(rapport, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n  rapport écrit : {args.sortie}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
