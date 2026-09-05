"""Tests du traqueur de lecture (« Lecture vivante »)."""

from app.services.reading_tracker import ReadingTracker

PS23 = "L'Éternel est mon berger: je ne manquerai de rien."


def test_exact_reading_advances_to_completion():
    tracker = ReadingTracker()
    tracker.set_verse(PS23)

    # « L'Éternel » = un seul token, aligné sur l'affichage à l'écran
    tracker.feed("l'éternel est mon berger")
    assert tracker.position == 4

    tracker.feed("je ne manquerai de rien")
    assert tracker.completed


def test_asr_errors_and_skipped_words_still_advance():
    tracker = ReadingTracker()
    tracker.set_verse(PS23)

    # « bergé » (faute ASR) + « manquerais » (flexion) + saut de « je ne »
    tracker.feed("l'éternel est mon bergé")
    assert tracker.position == 4
    tracker.feed("manquerais de rien")
    assert tracker.completed


def test_unrelated_speech_does_not_advance():
    tracker = ReadingTracker()
    tracker.set_verse(PS23)

    tracker.feed("avant de lire ce passage je voudrais saluer les visiteurs")
    assert tracker.position <= 1  # aucune vraie progression sur une parole libre


def test_asr_split_letters_are_merged():
    """Vosk peut découper « l eternel » : les lettres isolées fusionnent avec le mot suivant."""
    tracker = ReadingTracker()
    tracker.set_verse(PS23)
    tracker.feed("l eternel est mon berger")
    assert tracker.position == 4


def test_token_count_matches_display_split():
    """La position doit être exploitable telle quelle par l'écran (split espaces)."""
    tracker = ReadingTracker()
    text = "Cantique de David. L'Éternel est mon berger: je ne manquerai de rien."
    tracker.set_verse(text)
    assert tracker.total == len(text.split())


def test_new_verse_resets_position():
    tracker = ReadingTracker()
    tracker.set_verse(PS23)
    tracker.feed("l'éternel est mon berger")
    assert tracker.position > 0

    tracker.set_verse("Car Dieu a tant aimé le monde qu'il a donné son Fils unique")
    assert tracker.position == 0
    assert tracker.active
