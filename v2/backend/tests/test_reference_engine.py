import pytest
import asyncio
from app.services.verse_parser import VerseParserService
from app.services.reference_engine import BibleReferenceEngine
from unittest.mock import AsyncMock, MagicMock


class ConflictSemanticService:
    """Petit index déterministe pour tester l'arbitrage sans modèle ONNX."""

    initialized = True
    indexing = False
    active_threshold = 0.8385
    active_margin = 0.005

    def search(self, query, top_k=6, min_score=0.0):
        if "instruirai" not in query:
            return []
        return [{
            "reference": "Psaumes 32:8",
            "book_abbr": "ps",
            "chapter": 32,
            "verse_start": 8,
            "verse_end": None,
            "text": (
                "Je t'instruirai et te montrerai la voie que tu dois suivre; "
                "Je te conseillerai, j'aurai le regard sur toi."
            ),
            "score": 0.94,
            "confidence": 0.94,
        }]

@pytest.fixture
def parser_service():
    # Use a dummy JSON path for tests or real if available, let's just initialize it
    # We might need to mock BibleLoader if it takes time, but it's usually fast.
    return VerseParserService()

@pytest.fixture
def reference_engine(parser_service):
    settings_mock = MagicMock()
    settings_mock.HYBRID_WINDOW_WORDS = 40
    settings_mock.LOCAL_SEMANTIC_ENABLED = False
    
    return BibleReferenceEngine(
        verse_parser=parser_service,
        semantic_service=None,
        verse_graph=None,
        ai_service=None,
        settings=settings_mock,
        db_service=None,
        sante_transcription=None
    )

@pytest.mark.anyio
async def test_un_livre_seul_ne_declenche_rien(reference_engine):
    """« le livre de Jean », sans chapitre, ne doit RIEN remonter.

    Un étage « incrémental » annonçait ici le passage pressenti. Mesuré sur 30
    minutes de prédication réelle : 1 683 déclenchements, un toutes les 1,1
    seconde, parce que les articles français entrent dans les abréviations de
    livres — « est » → Esther, « la » → Lamentations, « je » → Jérémie.
    L'étage est retiré ; ce test garde la porte fermée.
    """
    result = await reference_engine.process(
        "prenons dans le livre de jean", is_final=False, generation=1)
    assert result is None


def test_le_parseur_incremental_reste_disponible_mais_trop_large(parser_service):
    """La capacité existe encore — et ce test dit pourquoi elle n'est pas branchée.

    Si l'idée revient, il lui faudra une amorce et un filtre de longueur : sans
    eux, un simple pronom désigne un livre de la Bible."""
    assert parser_service.parse_incremental("prenons dans le livre de jean")["book_abbr"] == "Jn"
    # La raison du retrait, figée noir sur blanc :
    assert parser_service.parse_incremental("je vais au marché")["book_abbr"] == "Jér"


def test_match_textuel_exact_peut_etre_projete_en_diffusion_directe(reference_engine):
    """Les phrases vérifiées localement ne doivent pas rester en validation."""
    assert reference_engine._is_direct_projection_allowed({
        "detection_method": "text_phrase",
        "confidence": 0.96,
        "verse_start": 16,
        "requires_review": False,
    }) is True
    assert reference_engine._is_direct_projection_allowed({
        "detection_method": "text_index",
        "confidence": 0.90,
        "verse_start": 16,
        "requires_review": False,
    }) is True
    assert reference_engine._is_direct_projection_allowed({
        "detection_method": "text_fuzzy",
        "confidence": 0.99,
        "verse_start": 16,
        "requires_review": False,
    }) is False

@pytest.mark.anyio
async def test_livre_et_chapitre_sont_une_VRAIE_detection(reference_engine):
    """« Jean chapitre 3 » n'est pas une piste : c'est un passage ouvert.

    L'étage explicite le reconnaît comme `chapter_candidate`, ce qui vaut bien
    mieux qu'un badge informatif — cette détection pose aussi l'ancre
    VerseGraph, qui permettra de rattacher les allusions des minutes suivantes.
    """
    text = "prenons dans le livre de jean chapitre 3"
    result = await reference_engine.process(text, is_final=False, generation=2)

    assert result is not None
    assert result["type"] == "reference_detected"
    assert result["payload"]["book_abbr"] == "Jn"
    assert result["payload"]["chapter"] == 3
    assert result["payload"]["detection_method"] == "chapter_candidate"
    assert result["payload"]["transient"] is True


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("spoken", "expected"),
    [
        (
            "première épître de pierre chapitre cinq soyez sobres veillez "
            "votre adversaire le diable rôde comme un lion rugissant cherchant qui il dévorera",
            "1 Pierre 5:8",
        ),
        (
            "un Jean chapitre quatre tel il est tels nous sommes aussi dans ce monde",
            "1 Jean 4:17",
        ),
        (
            "Jean chapitre dix-sept sanctifie-les par ta vérité ta parole est la vérité",
            "Jean 17:17",
        ),
        (
            "Romains chapitre neuf poursuivant la loi de la justice n'est pas parvenu à cette loi",
            "Romains 9:31",
        ),
        (
            "Luc chapitre quinze étant rentré en lui-même combien de mercenaires chez mon père "
            "ont du pain en abondance et moi ici je meurs de faim",
            "Luc 15:17",
        ),
    ],
)
async def test_chapitre_annonce_est_affine_par_la_citation(reference_engine, spoken, expected):
    """Régressions extraites du sermon réel fourni par l'utilisateur."""
    result = await reference_engine.process(spoken, is_final=True, generation=10)

    assert result is not None
    assert result["payload"]["reference"] == expected
    assert result["payload"]["verse_start"] > 0
    assert result["payload"]["detection_method"] == "chapter_contextual_text"
    assert not result["payload"].get("transient")


@pytest.mark.anyio
async def test_chapitre_suivi_de_parole_logistique_n_invente_pas_de_verset(reference_engine):
    result = await reference_engine.process(
        "Luc chapitre quinze la réunion commence demain matin dans la grande salle",
        is_final=True,
        generation=11,
    )

    assert result is not None
    assert result["payload"]["reference"] == "Luc 15"
    assert result["payload"]["detection_method"] == "chapter_candidate"
    assert result["payload"]["transient"] is True


@pytest.mark.anyio
async def test_une_reference_complete_sort_DES_le_partiel(reference_engine):
    """Ne pas attendre la fin de l'énoncé quand la référence est déjà dite.

    Le prédicateur continue de parler plusieurs secondes après avoir annoncé
    son verset. Attendre le « final » ajouterait tout ce délai avant l'écran —
    c'est exactement ce que faisait le moteur avant cette correction : l'étage
    incrémental répondait en premier et court-circuitait l'explicite.
    """
    text = "c'est vraiment la parole ouvrons ensemble romains chapitre huit verset vingt-huit"
    result = await reference_engine.process(text, is_final=False, generation=4)

    assert result is not None
    assert result["type"] == "reference_detected"
    assert result["payload"]["reference"] == "Romains 8:28"

@pytest.mark.anyio
async def test_final_parser_full_verse(reference_engine):
    # Test full explicit citation when final
    text = "prenons dans le livre de jean chapitre 3 verset 16"
    result = await reference_engine.process(text, is_final=True, generation=3)
    
    assert result is not None
    assert result["type"] == "reference_detected"
    payload = result["payload"]
    assert payload["book_abbr"] == "Jn"
    assert payload["chapter"] == 3
    assert payload["verse_start"] == 16
    assert payload["detection_method"] == "explicit"


@pytest.mark.anyio
async def test_reference_annoncee_incorrecte_est_signalee_sans_autoprojection(parser_service):
    settings_mock = MagicMock()
    settings_mock.HYBRID_WINDOW_WORDS = 32
    settings_mock.HYBRID_TOP_K = 6
    settings_mock.HYBRID_OVERLAP_MIN = 0.34
    settings_mock.LOCAL_SEMANTIC_ENABLED = True
    settings_mock.AI_AGENT_ENABLED = False
    engine = BibleReferenceEngine(
        verse_parser=parser_service,
        semantic_service=ConflictSemanticService(),
        verse_graph=None,
        ai_service=None,
        settings=settings_mock,
    )

    result = await engine.process(
        "Psaume trois verset huit je t'instruirai et te montrerai la voie que tu dois "
        "suivre je te conseillerai j'aurai le regard sur toi",
        is_final=True,
        generation=20,
    )

    payload = result["payload"]
    assert payload["reference"] == "Psaumes 32:8"
    assert payload["detection_method"] == "semantic_conflict"
    assert payload["explicit_conflict"]["spoken_reference"] == "Psaumes 3:8"
    assert payload["requires_review"] is True
    assert payload["auto_projected"] is False
