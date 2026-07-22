"""Détection hybride (RRF + accord + recouvrement lexical).

- Tests unitaires de la logique de fusion (encodeur factice, tournent partout).
- Benchmark de bout en bout sur l'index e5 réel (sauté s'il n'est pas construit) :
  citations, paraphrases célèbres et bruit du quotidien -> précision / rappel.
"""

import pytest

from app.services.detection_fusion import fuse, lexical_overlap, content_stems, strip_attribution


# ────────────────────────── logique pure ──────────────────────────

def _lex(book, ch, v, text, conf, method="text_fuzzy"):
    return {"book_abbr": book, "chapter": ch, "verse_start": v, "reference": f"{book} {ch}:{v}",
            "text": text, "confidence": conf, "detection_method": method}


def _sem(book, ch, v, text, score):
    return {"book_abbr": book, "chapter": ch, "verse_start": v, "reference": f"{book} {ch}:{v}",
            "text": text, "score": score, "confidence": score}


PARAMS = dict(semantic_threshold=0.865, semantic_margin=0.012, overlap_min=0.34)


def test_agreement_surfaces():
    spoken = "pierre est sorti de la barque et il a marché sur l eau vers jésus"
    verse = "Pierre, étant descendu de la barque, marcha sur les eaux, pour aller vers Jésus"
    out = fuse([_lex("Mt", 14, 29, verse, 0.7)], [_sem("Mt", 14, 29, verse, 0.86)], spoken, **PARAMS)
    assert out and out["reference"] == "Mt 14:29"
    assert out["fusion"]["agreement"] is True
    assert out["requires_review"] is True


def test_agreement_normalizes_book_abbreviation_case():
    spoken = "je peux tout par celui qui me fortifie"
    verse = "Je puis tout par celui qui me fortifie"
    out = fuse(
        [_lex("Ph", 4, 13, verse, 0.96, method="text_phrase")],
        [_sem("ph", 4, 13, verse, 0.89)],
        spoken,
        **PARAMS,
    )
    assert out and out["reference"].lower() == "ph 4:13"
    assert out["fusion"]["agreement"] is True


def test_noise_single_retriever_low_overlap_rejected():
    # Un seul récupérateur, un seul mot commun (« pain ») -> jamais proposé.
    spoken = "il faut que j achète du pain et du lait en rentrant à la maison"
    verse = "Elle ne mange pas le pain de la paresse"
    out = fuse([], [_sem("Pr", 31, 27, verse, 0.87)], spoken, **PARAMS)
    assert out is None


def test_strong_semantic_without_overlap_rejected():
    # Sémantique au-dessus du seuil mais aucun mot en commun -> rejet (anti-faux).
    spoken = "je vous parle aujourd hui du budget de la sono pour l année prochaine"
    verse = "Au commencement, Dieu créa les cieux et la terre"
    out = fuse([], [_sem("Ge", 1, 1, verse, 0.90)], spoken, **PARAMS)
    assert out is None


def test_curated_phrase_surfaces():
    spoken = "car dieu a tant aimé le monde qu il a donné son fils unique"
    verse = "Car Dieu a tant aimé le monde qu'il a donné son Fils unique"
    out = fuse([_lex("Jn", 3, 16, verse, 0.96, method="text_phrase")], [], spoken, **PARAMS)
    assert out and out["reference"] == "Jn 3:16"


def test_strip_attribution():
    assert strip_attribution("et paul nous dit je peux tout faire").strip() == "et je peux tout faire"
    assert strip_attribution("comme le roi david a écrit l'éternel est mon berger") == "comme l'éternel est mon berger"
    assert strip_attribution("il est écrit tu ne tueras point") == "tu ne tueras point"
    # Pas de verbe d'attribution -> on ne touche à rien (ex. citation explicite).
    assert strip_attribution("jean chapitre trois verset seize") == "jean chapitre trois verset seize"


def test_overlap_discriminates():
    assert lexical_overlap("pierre a marché sur l eau vers jésus",
                           "Pierre marcha sur les eaux pour aller vers Jésus") >= 0.6
    assert lexical_overlap("j achète du pain et du lait",
                           "elle ne mange pas le pain de la paresse") < 0.34
    assert content_stems("le la les des un une") == set()  # que des mots-outils


# ────────────────────── bout en bout, index réel ──────────────────────

# (paraphrase parlée, référence attendue) — paraphrases ET quasi-citations,
# y compris des formulations d'autres traductions que la version indexée.
PARAPHRASES = [
    ("pierre est sorti de la barque et il a marché sur l'eau vers jésus", ("mt", 14)),
    ("je peux tout faire grâce à celui qui me donne la force", ("ph", 4)),
    ("car dieu a tellement aimé le monde qu'il a donné son fils unique", ("jn", 3)),
    ("l'éternel est mon berger je ne manquerai de rien", ("ps", 23)),
    ("au commencement dieu a créé le ciel et la terre", ("gen", 1)),
    ("demandez et vous recevrez cherchez et vous trouverez", ("mt", 7)),
    ("je suis le chemin la vérité et la vie", ("jn", 14)),
    ("le salaire du péché c'est la mort", ("rm", 6)),
    ("aimez vos ennemis et priez pour ceux qui vous persécutent", ("mt", 5)),
    ("si quelqu'un a soif qu'il vienne à moi et qu'il boive", ("jn", 7)),
    ("toutes choses concourent au bien de ceux qui aiment dieu", ("rm", 8)),
    ("heureux les pauvres en esprit car le royaume des cieux est à eux", ("mt", 5)),
    # Encadrement d'attribution (« Paul dit… », « le roi David a écrit… »).
    ("l'apôtre paul nous dit je peux tout par celui qui me fortifie", ("ph", 4)),
    ("comme le roi david a écrit l'éternel est mon berger je ne manquerai de rien", ("ps", 23)),
]

# Parole du quotidien d'un culte : ne doit JAMAIS remonter un verset.
NOISE = [
    "la réunion de l'équipe technique est prévue mardi prochain à quinze heures",
    "il faut que j'achète du pain et du lait en rentrant à la maison ce soir",
    "le match de football commence à vingt heures ce soir sur la grande chaîne",
    "j'ai garé la voiture juste devant l'entrée du parking souterrain du centre",
    "n'oubliez pas de régler le volume du micro avant le début de la louange",
    "on se retrouve tous après le culte pour partager un café dans la salle",
    "les enfants de l'école du dimanche montent à l'étage avec leurs moniteurs",
    "merci à l'équipe d'accueil qui a préparé les chaises et les brochures",
]


def test_end_to_end_precision_recall():
    # Exerce la VRAIE cascade de production (explicite + attribution + fusion).
    import asyncio
    from app import main as M
    from app.services.verse_parser import VerseParserService
    from app.services.semantic_search import LocalSemanticService

    M.verse_parser = VerseParserService()
    M.semantic_service = LocalSemanticService(M.verse_parser.bible_loader)
    if not M.semantic_service.initialize(allow_download=False):
        pytest.skip(f"Index sémantique non construit : {M.semantic_service.last_error}")

    def detect(spoken):
        return asyncio.run(M.run_detection_cascade(spoken, final_state=True))

    hits = 0
    for spoken, (book, chap) in PARAPHRASES:
        out = detect(spoken)
        if out and out["book_abbr"].lower() == book and out["chapter"] == chap:
            hits += 1
    recall = hits / len(PARAPHRASES)

    false_positives = sum(1 for spoken in NOISE if detect(spoken) is not None)

    # Objectif « imparable » : rattraper la quasi-totalité des paraphrases (100 %
    # à chaud ; petite marge pour un cas-limite au démarrage à froid), et ZÉRO
    # faux positif sur la parole du quotidien — la précision n'est jamais bradée.
    assert recall >= 0.85, f"rappel paraphrases trop bas : {recall:.0%} ({hits}/{len(PARAPHRASES)})"
    assert false_positives == 0, f"{false_positives} faux positif(s) sur du bruit"
