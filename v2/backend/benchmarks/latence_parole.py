"""Délai « fin de la référence prononcée → candidat à l'écran », mesuré de bout en bout.

C'est LE critère de lancement du plan stratégique (docs/AUDIT-STRATEGIQUE-
LANCEMENT-2026-09-05.md, point 7) : « p95 inférieur à deux secondes entre fin
de référence et candidat ». Or rien ne le mesurait. Le Replay Lab démarre son
chronomètre APRÈS la transcription, le benchmark de détection part de texte :
aucun des deux ne voit le moteur vocal, la file d'attente ni le découpage en
énoncés. Et le dépôt ne contient aucun fichier audio.

Cet outil mesure la chaîne réelle, sans rien simuler à l'intérieur :

1. il synthétise une phrase de prédication avec une voix française de macOS
   (« Ouvrons nos Bibles dans Jean chapitre trois verset seize ») suivie de sa
   continuation (« Car Dieu a tant aimé le monde… »), et mesure l'instant exact
   où la référence finit de sonner ;
2. il lance un backend isolé (base temporaire : l'historique réel n'est pas
   touché) et lui envoie l'audio par le VRAI WebSocket /ws/audio, au rythme du
   micro — blocs de 43 ms en PCM 16 kHz, comme createAudioSlice.js ;
3. il horodate chaque `reference_detected` renvoyé par le backend.

Délai = instant de réception − instant où la référence a fini d'être dite.
Voix de synthèse : ce n'est pas une salle d'église. C'est un plancher mesuré,
reproductible, qui voit enfin toute la chaîne ; les enregistrements de pilotes
viendront le compléter.

    python3 benchmarks/latence_parole.py            # tous les cas, Nemotron
    python3 benchmarks/latence_parole.py --moteur vosk --voix Jacques

VRAIES VOIX. Les voix de synthèse ne suffisent pas : Nemotron décroche sur
elles (« Chap Iii », mots anglais), alors qu'il tient une heure de vraie
prédication. Pour mesurer sur une voix humaine :

    python3 benchmarks/latence_parole.py --enregistrer        # ~3 min, une fois
    python3 benchmarks/latence_parole.py --voix-enregistree   # autant de fois que voulu

La voix reste sur ce poste, dans data/voix-latence/ (ignoré par git) :
c'est une donnée personnelle, elle ne doit jamais être versionnée.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
import wave
from pathlib import Path

import numpy as np

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))
DOSSIER_VOIX = RACINE / "data" / "voix-latence"

TAUX = 16000
chronologie: list = []  # (t, nature, texte) du dernier cas joué, pour --detail
BLOC = 683  # ≈ 43 ms : ScriptProcessor de 2048 à 48 kHz, ramené à 16 kHz
JETON = "latence-parole"

# (référence dite, continuation, référence attendue). Formulations de chaire,
# nombres en toutes lettres comme on les prononce.
CAS = [
    ("Ouvrons nos Bibles dans Jean chapitre trois, verset seize.",
     "Car Dieu a tant aimé le monde qu'il a donné son Fils unique.", "Jean 3:16"),
    ("Lisons ensemble le psaume vingt-trois, verset un.",
     "L'Éternel est mon berger, je ne manquerai de rien.", "Psaumes 23:1"),
    ("Mes frères, allons dans Romains chapitre huit, verset vingt-huit.",
     "Nous savons que toutes choses concourent au bien de ceux qui aiment Dieu.", "Romains 8:28"),
    ("Prenons Philippiens chapitre quatre, verset treize.",
     "Je puis tout par celui qui me fortifie.", "Philippiens 4:13"),
    ("La parole se trouve dans Ésaïe chapitre quarante, verset trente et un.",
     "Ceux qui se confient en l'Éternel renouvellent leur force.", "Ésaïe 40:31"),
    ("Voyons Matthieu chapitre onze, verset vingt-huit.",
     "Venez à moi, vous tous qui êtes fatigués et chargés.", "Matthieu 11:28"),
    ("Ouvrez à Proverbes chapitre trois, verset cinq.",
     "Confie-toi en l'Éternel de tout ton cœur.", "Proverbes 3:5"),
    ("Hébreux chapitre onze, verset un, nous dit ceci.",
     "Or la foi est une ferme assurance des choses qu'on espère.", "Hébreux 11:1"),
    ("Allons dans Jérémie vingt-neuf, verset onze.",
     "Car je connais les projets que j'ai formés sur vous.", "Jérémie 29:11"),
    ("Lisons Galates chapitre cinq, verset vingt-deux.",
     "Mais le fruit de l'Esprit, c'est l'amour, la joie, la paix.", "Galates 5:22"),
    ("Dans première Corinthiens treize, verset quatre, Paul écrit.",
     "L'amour est patient, il est plein de bonté.", "1 Corinthiens 13:4"),
    ("Josué chapitre un, verset neuf.",
     "Fortifie-toi et prends courage, ne t'effraie point.", "Josué 1:9"),
]

# Des phrases de culte sans référence : tout candidat ici est un faux.
NEGATIFS = [
    "Nous allons maintenant prier pour les malades et pour les familles de l'assemblée.",
    "Le groupe de louange va nous conduire dans deux chants avant la prédication.",
    "N'oubliez pas la réunion des jeunes samedi à quinze heures dans la grande salle.",
]


def synthetiser(texte: str, voix: str, dossier: Path, nom: str) -> np.ndarray:
    """Texte → échantillons int16 mono 16 kHz, via `say` puis afconvert."""
    aiff, wav = dossier / f"{nom}.aiff", dossier / f"{nom}.wav"
    subprocess.run(["say", "-v", voix, "-o", str(aiff), texte], check=True)
    subprocess.run(["afconvert", "-f", "WAVE", "-d", f"LEI16@{TAUX}", "-c", "1", str(aiff), str(wav)],
                   check=True, capture_output=True)
    with wave.open(str(wav)) as fichier:
        return np.frombuffer(fichier.readframes(fichier.getnframes()), dtype=np.int16)


def lire_wav(chemin: Path) -> np.ndarray:
    with wave.open(str(chemin)) as fichier:
        if fichier.getframerate() != TAUX or fichier.getnchannels() != 1:
            raise SystemExit(f"{chemin} : attendu mono {TAUX} Hz")
        return np.frombuffer(fichier.readframes(fichier.getnframes()), dtype=np.int16)


def enregistrer_phrase(chemin: Path, texte: str, micro: str) -> None:
    """Enregistre le micro jusqu'à Entrée, en mono 16 kHz."""
    input(f"\n  Prêt ? Entrée, puis lisez à voix haute :\n\n      « {texte} »\n")
    ffmpeg = subprocess.Popen(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "avfoundation",
         "-i", f":{micro}", "-ac", "1", "-ar", str(TAUX), "-sample_fmt", "s16", str(chemin)],
        stdin=subprocess.PIPE,
    )
    input("  … enregistrement. Entrée quand vous avez fini.")
    ffmpeg.communicate(b"q", timeout=10)
    if not chemin.exists() or chemin.stat().st_size < TAUX:
        raise SystemExit("Enregistrement vide : le Terminal a-t-il accès au micro ? "
                         "(Réglages Système → Confidentialité → Micro)")


def enregistrer(dossier: Path, micro: str) -> int:
    dossier.mkdir(parents=True, exist_ok=True)
    print(f"Enregistrement de {len(CAS)} références et {len(NEGATIFS)} phrases sans référence, "
          f"micro « {micro} ». Parlez comme en chaire, à distance normale du micro.")
    for n, (reference_dite, suite, _) in enumerate(CAS):
        enregistrer_phrase(dossier / f"{n:02d}_a.wav", reference_dite, micro)
        enregistrer_phrase(dossier / f"{n:02d}_b.wav", suite, micro)
    for n, phrase in enumerate(NEGATIFS):
        enregistrer_phrase(dossier / f"neg{n:02d}.wav", phrase, micro)
    print(f"\nTerminé : {dossier}. Mesure : python3 benchmarks/latence_parole.py --voix-enregistree")
    return 0


def fin_de_parole(echantillons: np.ndarray) -> float:
    """Instant (s) du dernier son audible : la synthèse ajoute du silence en fin."""
    energie = np.abs(echantillons.astype(np.int32))
    seuil = max(300, int(energie.max() * 0.02))
    audibles = np.nonzero(energie > seuil)[0]
    return (audibles[-1] + 1) / TAUX if len(audibles) else len(echantillons) / TAUX


def demarrer_backend(port: int, moteur: str) -> tuple[subprocess.Popen, Path]:
    """Backend isolé : base et réglages temporaires, modèles réels en lien."""
    donnees = Path(tempfile.mkdtemp(prefix="vp-latence-"))
    reelles = RACINE / "data"
    for nom in ("models", "semantic", "bibles_cache", "vosk-model-fr-0.22", "vosk-model-small-fr-0.22"):
        if (reelles / nom).exists():
            (donnees / nom).symlink_to(reelles / nom)
    env = {**os.environ, "VERSEPRO_DATA_DIR": str(donnees), "VERSEPRO_PORT": str(port),
           "VERSEPRO_HOST": "127.0.0.1", "VERSEPRO_SESSION_TOKEN": JETON,
           "ASR_DEFAULT_ENGINE": moteur}
    journal = open(donnees / "backend.log", "w")
    processus = subprocess.Popen([sys.executable, "run_server.py"], cwd=RACINE, env=env,
                                 stdout=journal, stderr=subprocess.STDOUT)
    return processus, donnees


async def attendre_backend(port: int, processus: subprocess.Popen) -> None:
    import httpx
    async with httpx.AsyncClient() as client:
        for _ in range(180):
            if processus.poll() is not None:
                raise SystemExit("Le backend s'est arrêté au démarrage.")
            try:
                r = await client.get(f"http://127.0.0.1:{port}/api/v1/health",
                                     headers={"Authorization": f"Bearer {JETON}"}, timeout=2)
                if r.status_code == 200:
                    return
            except Exception:
                pass
            await asyncio.sleep(1)
    raise SystemExit("Backend muet après 180 s.")


async def canonique(parser, reference):
    lue = await parser.parse(reference, skip_text_search=True) if reference else None
    return lue and (lue["book_abbr"], lue["chapter"], lue["verse_start"])


async def jouer(port: int, moteur: str, echantillons: np.ndarray, silence_final: float = 2.5):
    """Envoie l'audio au rythme réel ; rend [(t_reçu, référence)] et les transcriptions."""
    import websockets

    audio = np.concatenate([echantillons, np.zeros(int(silence_final * TAUX), dtype=np.int16)])
    recus, transcriptions = [], []
    chronologie.clear()
    async with websockets.connect(
        f"ws://127.0.0.1:{port}/ws/audio?engine={moteur}",
        subprotocols=["versepro", f"versepro.auth.{JETON}"], max_size=None,
    ) as ws:
        # Le moteur est prêt quand le serveur annonce son statut.
        fin_attente = time.monotonic() + 60
        while time.monotonic() < fin_attente:
            message = json.loads(await asyncio.wait_for(ws.recv(), timeout=60))
            if message.get("type") == "status_update" and message.get("status") in ("connected", "ready", "local"):
                break
            if message.get("type") == "error":
                raise SystemExit(f"Moteur {moteur} indisponible : {message.get('message')}")
        await asyncio.sleep(0.3)

        depart = time.monotonic()

        async def ecouter():
            async for brut in ws:
                message = json.loads(brut)
                t = time.monotonic() - depart
                if message.get("type") == "reference_detected":
                    ref = message.get("reference") or {}
                    recus.append((t, ref.get("reference")))
                elif message.get("type") == "transcript":
                    if message.get("is_final"):
                        transcriptions.append(message.get("text", ""))
                    chronologie.append((t, "final" if message.get("is_final") else "partiel", message.get("text", "")))

        auditeur = asyncio.create_task(ecouter())
        for i in range(0, len(audio), BLOC):
            await ws.send(audio[i:i + BLOC].tobytes())
            # Rythme du micro : chaque bloc part quand il a été « dit ».
            cible = depart + (i + BLOC) / TAUX
            await asyncio.sleep(max(0.0, cible - time.monotonic()))
        await asyncio.sleep(1.5)
        auditeur.cancel()
    return recus, transcriptions


async def principal(options) -> int:
    from app.services.verse_parser import VerseParserService

    parser = VerseParserService()
    dossier = Path(tempfile.mkdtemp(prefix="vp-voix-"))
    processus, donnees = demarrer_backend(options.port, options.moteur)
    try:
        await attendre_backend(options.port, processus)
        delais, manques, faux = [], [], 0
        cas = CAS[: options.limite] if options.limite else CAS
        voix = options.voix_enregistree
        for n, (reference_dite, suite, attendu) in enumerate(cas):
            if voix:
                debut_audio, suite_audio = lire_wav(voix / f"{n:02d}_a.wav"), lire_wav(voix / f"{n:02d}_b.wav")
            else:
                debut_audio = synthetiser(reference_dite, options.voix, dossier, f"a{n}")
                suite_audio = synthetiser(suite, options.voix, dossier, f"b{n}")
            fin_ref = fin_de_parole(debut_audio)
            audio = np.concatenate([debut_audio[: int(fin_ref * TAUX)],
                                    np.zeros(int(0.25 * TAUX), dtype=np.int16), suite_audio])
            recus, transcrit = await jouer(options.port, options.moteur, audio)
            cible = await canonique(parser, attendu)
            bons = [t for t, ref in recus if await canonique(parser, ref) == cible]
            autres = [ref for t, ref in recus if await canonique(parser, ref) != cible]
            faux += len(autres)
            if options.detail:
                print(f"     référence finie à {fin_ref:.2f} s de son")
                for t, nature, texte in chronologie:
                    print(f"     {t:6.2f} s  {nature:7}  {texte[-70:]}")
                for t, ref in recus:
                    print(f"     {t:6.2f} s  CANDIDAT {ref}")
            if bons:
                delai = bons[0] - fin_ref
                delais.append(delai)
                print(f"OK   {delai:6.2f} s  {attendu:20} {('+ faux : ' + ', '.join(autres)) if autres else ''}")
            else:
                manques.append(attendu)
                print(f"RATÉ          {attendu:20} reçu {[r for _, r in recus]} | entendu : {' / '.join(transcrit)[:110]}")

        for n, phrase in enumerate(NEGATIFS):
            audio = (lire_wav(voix / f"neg{n:02d}.wav") if voix
                     else synthetiser(phrase, options.voix, dossier, f"n{n}"))
            recus, transcrit = await jouer(options.port, options.moteur, audio)
            faux += len(recus)
            print(f"{'FAUX' if recus else 'OK  '}          (négatif) {[r for _, r in recus] or 'aucun candidat'}")

        print()
        print(f"Moteur {options.moteur} · voix {'enregistrée (' + str(voix) + ')' if voix else options.voix} · {len(cas)} références, {len(NEGATIFS)} phrases sans référence")
        print(f"Rappel : {len(delais)}/{len(cas)} ({100 * len(delais) / len(cas):.0f} %)")
        if len(delais) >= 2:
            q = statistics.quantiles(delais, n=20)
            print(f"Délai fin de référence → candidat : p50 {statistics.median(delais):.2f} s · "
                  f"p95 {q[18]:.2f} s · max {max(delais):.2f} s   (cible du plan : p95 < 2 s)")
        print(f"Faux candidats : {faux}")
        if manques:
            print("Manqués :", ", ".join(manques))
        return 0
    finally:
        processus.terminate()
        try:
            processus.wait(timeout=10)
        except subprocess.TimeoutExpired:
            processus.kill()
        if options.garder:
            print(f"Journal du backend : {donnees / 'backend.log'}")
        else:
            shutil.rmtree(donnees, ignore_errors=True)
        shutil.rmtree(dossier, ignore_errors=True)


if __name__ == "__main__":
    analyseur = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    analyseur.add_argument("--moteur", choices=("nemotron", "vosk"), default="nemotron")
    analyseur.add_argument("--voix", default="Jacques", help="voix française de `say -v '?'`")
    analyseur.add_argument("--port", type=int, default=17998)
    analyseur.add_argument("--limite", type=int, default=0, help="n'exécuter que les N premiers cas")
    analyseur.add_argument("--garder", action="store_true", help="conserver le journal du backend")
    analyseur.add_argument("--detail", action="store_true", help="chronologie des transcriptions par cas")
    analyseur.add_argument("--enregistrer", action="store_true", help="enregistrer sa propre voix (une fois)")
    analyseur.add_argument("--voix-enregistree", nargs="?", const=DOSSIER_VOIX, type=Path, default=None,
                           help=f"mesurer sur les enregistrements (défaut : {DOSSIER_VOIX})")
    analyseur.add_argument("--micro", default="0", help="périphérique audio avfoundation (ffmpeg -list_devices)")
    options = analyseur.parse_args()
    if options.enregistrer:
        sys.exit(enregistrer(options.voix_enregistree or DOSSIER_VOIX, options.micro))
    sys.exit(asyncio.run(principal(options)))
