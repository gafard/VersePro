"""Benchmark de la recherche par description (barre de recherche de la régie).

Le benchmark de détection mesure ce que VersePro entend pendant le culte. Ce
lui-ci mesure ce que le régisseur TAPE quand il ne connaît pas la référence :
« le fils prodigue », « Jonas dans le poisson ». Sans lui, un récit aussi
connu que la Pâque (Exode 12) pouvait disparaître du top 3 sans que personne
ne s'en aperçoive.

Il appelle la vraie route /bible/search (lexical + sémantique, fusion au
score), IA désactivée pour que la mesure soit reproductible et hors ligne.

Un cas est réussi si l'un des trois premiers résultats tombe dans l'un des
passages attendus (même livre, même chapitre, verset dans la plage).
"""

import argparse
import asyncio
import json
import statistics
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import main  # noqa: E402
from app.api import routes  # noqa: E402
from app.services.semantic_search import LocalSemanticService  # noqa: E402
from app.services.verse_parser import VerseParserService  # noqa: E402

DEFAULT_CASES = Path(__file__).with_name("description_cases.json")


async def _plage(parser, reference):
    parsed = await parser.parse(reference, skip_text_search=True)
    if not parsed:
        raise ValueError(f"Référence attendue illisible : {reference}")
    debut = parsed["verse_start"]
    return parsed["book_abbr"].casefold(), parsed["chapter"], debut, parsed.get("verse_end") or debut


def _dans(resultat, plage):
    livre, chapitre, debut, fin = plage
    verset = resultat.get("verse_start") or resultat.get("verse")
    return (
        # La sémantique renvoie « lc », le parseur « Lc » : on compare sans casse.
        str(resultat.get("book_abbr") or "").casefold() == livre
        and resultat.get("chapter") == chapitre
        and verset is not None
        and debut <= int(verset) <= fin
    )


async def _ia_locale(modele: str):
    """L'assistant réduit à Ollama : ni clé cloud, ni réessais facturés."""
    from app.core.config import settings
    from app.services.ai_service import AIService

    settings.AI_AGENT_ENABLED = True
    ia = AIService()
    ia.openrouter_key = ia.api_key = ""
    ia.ollama_model = modele
    await ia._detect_ollama()
    if not ia.ollama_active:
        raise SystemExit(f"Ollama ou le modèle {modele} est indisponible")
    await ia.trouver_passage_decrit("échauffement : Jésus marche sur les eaux")
    return ia


async def run(cases_path: Path, top: int, modele_ia: str | None = None) -> int:
    parser = VerseParserService()
    # L'index manuel se complète en arrière-plan ; on mesure l'état stable.
    while threading.active_count() > 1:
        time.sleep(0.5)
    semantique = LocalSemanticService(parser.bible_loader)
    semantique.initialize()
    main.verse_parser, main.semantic_service, main.ai_service = parser, semantique, None

    ia = await _ia_locale(modele_ia) if modele_ia else None
    ia_justes, ia_sauvetages, ia_latences, rangs_fusion = 0, 0, [], []

    cases = json.loads(cases_path.read_text(encoding="utf-8"))
    rangs, latences, rates = [], [], []
    for case in cases:
        plages = [await _plage(parser, ref) for ref in case["attendu"]]
        debut = time.perf_counter()
        reponse = await routes.bible_search(case["q"], limit=6)
        latences.append((time.perf_counter() - debut) * 1000)
        resultats = reponse["results"]
        rang = next(
            (i + 1 for i, r in enumerate(resultats) if any(_dans(r, p) for p in plages)),
            None,
        )
        rangs.append(rang)
        statut = f"#{rang}" if rang and rang <= top else "RATÉ"
        premiers = " | ".join(r.get("reference", "?") for r in resultats[:3]) or "aucun"
        print(f"{statut:5} {latences[-1]:7.0f} ms  {case['q'][:52]:52}  {premiers}")
        if not (rang and rang <= top):
            rates.append(case["q"])

        if ia:
            # Ce que voit le régisseur : la liste locale, puis la réponse de
            # /bible/search/ia qui la remplace (IA vérifiée + fusion).
            main.ai_service = ia
            debut = time.perf_counter()
            reponse_ia = await routes.bible_search_ia(case["q"], limit=6)
            ia_latences.append((time.perf_counter() - debut) * 1000)
            main.ai_service = None
            fusion = reponse_ia["results"]
            rang_f = next(
                (i + 1 for i, r in enumerate(fusion) if any(_dans(r, p) for p in plages)), None
            )
            rangs_fusion.append(rang_f)
            tete = fusion[0] if fusion else {}
            juste = tete.get("source") == "ai" and any(_dans(tete, p) for p in plages)
            ia_justes += juste
            ia_sauvetages += bool(rang_f and rang_f <= top) and not (rang and rang <= top)
            print(f"      IA {ia_latences[-1]:6.0f} ms  {reponse_ia['ia']:10} "
                  f"{'#' + str(rang_f) if rang_f and rang_f <= top else 'RATÉ':5} {tete.get('reference')}")

    n = len(cases)
    top1 = sum(1 for r in rangs if r == 1)
    topn = sum(1 for r in rangs if r and r <= top)
    q = statistics.quantiles(latences, n=20)
    print()
    print(f"Top 1 : {top1}/{n} ({100 * top1 / n:.0f} %)")
    print(f"Top {top} : {topn}/{n} ({100 * topn / n:.0f} %)")
    print(f"Latence p50 / p95 / max : {statistics.median(latences):.0f} / {q[18]:.0f} / {max(latences):.0f} ms")
    print(f"Sémantique active : {'oui' if semantique.initialized else 'NON — mesure lexicale seule'}")
    if ia:
        qi = statistics.quantiles(ia_latences, n=20)
        f1 = sum(1 for r in rangs_fusion if r == 1)
        f3 = sum(1 for r in rangs_fusion if r and r <= top)
        print(f"AVEC IA {modele_ia} : top 1 {f1}/{n} ({100 * f1 / n:.0f} %) ; top {top} {f3}/{n} "
              f"({100 * f3 / n:.0f} %) ; {ia_sauvetages} cas sauvés ; latence IA p50 / p95 "
              f"{statistics.median(ia_latences):.0f} / {qi[18]:.0f} ms")
    return 0


if __name__ == "__main__":
    arguments = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    arguments.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    arguments.add_argument("--top", type=int, default=3)
    arguments.add_argument("--ia", metavar="MODELE_OLLAMA", help="mesurer aussi l'IA locale, ex. llama3.1:8b")
    options = arguments.parse_args()
    sys.exit(asyncio.run(run(options.cases, options.top, options.ia)))
