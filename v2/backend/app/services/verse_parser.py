"""
Parser de Références Bibliques v2 (Corrigé, Amélioré & Multi-Traduction)
Supporte plusieurs bibles (LSG, SEM, KJF, NBS, FC, TOB), la recherche textuelle
et la correction d'homophones vocaux.
"""

import re
import unicodedata
from typing import Optional, Dict, Any, List
from loguru import logger

def strip_accents(text: str) -> str:
    """Enlève les accents d'une chaîne de caractères et la met en minuscules"""
    text_clean = text.lower().strip()
    return "".join(c for c in unicodedata.normalize('NFD', text_clean) if unicodedata.category(c) != 'Mn')

# Mapping des noms de livres vers abréviations standards
STANDARD_BOOK_MAP = {
    # Ancien Testament
    "genese": "Gen", "genèse": "Gen",
    "exode": "Ex",
    "levitique": "Lév", "lévitique": "Lév",
    "nombres": "Nb",
    "deuteronome": "Dt", "deutéronome": "Dt",
    "josue": "Jos", "josué": "Jos",
    "juges": "Jg",
    "ruth": "Rt",
    "1 samuel": "1 S",
    "2 samuel": "2 S",
    "1 rois": "1 R",
    "2 rois": "2 R",
    "1 chroniques": "1 Ch",
    "2 chroniques": "2 Ch",
    "esdras": "Esd",
    "nehemie": "Neh", "néhémie": "Neh",
    "esther": "Est",
    "job": "Job",
    "psaumes": "Ps", "psaume": "Ps",
    "proverbes": "Pr",
    "ecclesiaste": "Ec", "ecclésiaste": "Ec",
    "cantique": "Ct", "cantique des cantiques": "Ct",
    "esaie": "És", "ésaïe": "És",
    "jeremie": "Jér", "jérémie": "Jér",
    "lamentations": "Lm", "lm": "Lm", "lamentations de jeremie": "Lm", "lamentations de jérémie": "Lm",
    "ezechiel": "Éz", "ézéchiel": "Éz",
    "daniel": "Dn",
    "osee": "Os", "osée": "Os",
    "joel": "Jl", "joël": "Jl",
    "amos": "Am",
    "abdias": "Abd",
    "jonas": "Jon",
    "micee": "Mi", "micée": "Mi",
    "nahum": "Na",
    "habacuc": "Hab",
    "sophonie": "So",
    "aggee": "Ag", "aggée": "Ag",
    "zacharie": "Za",
    "malachie": "Ml",

    # Nouveau Testament
    "matthieu": "Mt",
    "marc": "Mc",
    "luc": "Lc",
    "jean": "Jn",
    "actes": "Ac", "actes des apotres": "Ac", "actes des apôtres": "Ac", "ac": "Ac",
    "romains": "Rm", "rm": "Rm", "rom": "Rm", "ro": "Rm",
    "1 corinthiens": "1 Co",
    "2 corinthiens": "2 Co",
    "galates": "Ga",
    "ephesiens": "Éph", "éphésiens": "Éph",
    "philippiens": "Ph",
    "colossiens": "Col",
    "1 thessaloniciens": "1 Th",
    "2 thessaloniciens": "2 Th",
    "1 timothee": "1 Tm", "1 timothée": "1 Tm",
    "2 timothee": "2 Tm", "2 timothée": "2 Tm",
    "tite": "Tt",
    "philemon": "Phm", "philémon": "Phm",
    "hebreux": "He", "hébreux": "He",
    "jacques": "Jc",
    "1 pierre": "1 P",
    "2 pierre": "2 P",
    "1 jean": "1 Jn",
    "2 jean": "2 Jn",
    "3 jean": "3 Jn",
    "jude": "Jude",
    "apocalypse": "Ap", "révélation": "Ap",

    # Certaines sources Darby emploient des noms anglais dans les
    # métadonnées alors que le texte des versets est français. Sans ces alias,
    # 56 livres sur 66 étaient silencieusement exclus de l'index global.
    "genesis": "Gen", "exodus": "Ex", "leviticus": "Lév", "numbers": "Nb",
    "deuteronomy": "Dt", "joshua": "Jos", "judges": "Jg",
    "i samuel": "1 S", "ii samuel": "2 S", "i kings": "1 R", "ii kings": "2 R",
    "i chronicles": "1 Ch", "ii chronicles": "2 Ch", "ezra": "Esd",
    "nehemiah": "Neh", "psalms": "Ps", "proverbs": "Pr", "ecclesiastes": "Ec",
    "song of solomon": "Ct", "isaiah": "És", "jeremiah": "Jér", "ezekiel": "Éz",
    "hosea": "Os", "obadiah": "Abd", "jonah": "Jon", "micah": "Mi",
    "habakkuk": "Hab", "zephaniah": "So", "haggai": "Ag", "zechariah": "Za", "malachi": "Ml",
    "matthew": "Mt", "mark": "Mc", "luke": "Lc", "john": "Jn", "acts": "Ac",
    "romans": "Rm", "i corinthians": "1 Co", "ii corinthians": "2 Co",
    "galatians": "Ga", "ephesians": "Éph", "philippians": "Ph", "colossians": "Col",
    "i thessalonians": "1 Th", "ii thessalonians": "2 Th",
    "i timothy": "1 Tm", "ii timothy": "2 Tm", "titus": "Tt",
    "hebrews": "He", "james": "Jc", "i peter": "1 P", "ii peter": "2 P",
    "i john": "1 Jn", "ii john": "2 Jn", "iii john": "3 Jn",
    "revelation of john": "Ap",

    # Libellés éditoriaux rencontrés dans les fichiers NBS, Semeur et Français
    # courant. Ce sont des métadonnées de livres, mais aussi des formulations
    # que l'ASR peut réellement produire (« première lettre aux Corinthiens »).
    "michee": "Mi", "nahoum": "Na", "habaquq": "Hab",
    "premier livre de samuel": "1 S", "deuxieme livre de samuel": "2 S",
    "premier livre des rois": "1 R", "deuxieme livre des rois": "2 R",
    "premier livre des chroniques": "1 Ch", "deuxieme livre des chroniques": "2 Ch",
    "l'ecclesiaste ou les paroles du sage": "Ec",
    "evangile selon matthieu": "Mt", "evangile selon marc": "Mc",
    "evangile selon luc": "Lc", "evangile selon jean": "Jn",
    "lettre aux romains": "Rm", "premiere lettre aux corinthiens": "1 Co",
    "deuxieme lettre aux corinthiens": "2 Co", "lettre aux galates": "Ga",
    "lettre aux ephesiens": "Éph", "lettre aux philippiens": "Ph",
    "lettre aux colossiens": "Col", "premiere lettre aux thessaloniciens": "1 Th",
    "deuxieme lettre aux thessaloniciens": "2 Th", "premiere lettre a timothee": "1 Tm",
    "deuxieme lettre a timothee": "2 Tm", "lettre a tite": "Tt",
    "lettre a philemon": "Phm", "lettre aux hebreux": "He",
    "lettre de jacques": "Jc", "premiere lettre de pierre": "1 P",
    "deuxieme lettre de pierre": "2 P", "premiere lettre de jean": "1 Jn",
    "deuxieme lettre de jean": "2 Jn", "troisieme lettre de jean": "3 Jn",
    "lettre de jude": "Jude", "apocalypse ou revelation accordee a jean": "Ap",
}

def get_standard_abbr(book_name: str) -> Optional[str]:
    """Retourne l'abréviation standard d'un livre"""
    name_clean = book_name.lower().strip()
    name_clean = "".join(c for c in unicodedata.normalize('NFD', name_clean) if unicodedata.category(c) != 'Mn')
    name_clean = re.sub(r"\s+", " ", name_clean.replace("’", "'").replace("`", "'"))
    return STANDARD_BOOK_MAP.get(name_clean)

def get_full_book_name(book_abbr: str) -> str:
    """Retourne le nom complet du livre depuis l'abréviation"""
    for name, abbr in STANDARD_BOOK_MAP.items():
        if abbr.lower() == book_abbr.lower():
            return name.title()
    return book_abbr.title()


# Noms complets AVEC accents/casse propres, pour l'AFFICHAGE (jamais pour la
# recherche). Clés = abréviations minuscules de bible.json (« mt », « 1 co »,
# « és », « ac »…). L'interne garde les abréviations ; l'utilisateur voit les noms.
BOOK_FULL_NAMES = {
    "gen": "Genèse", "ex": "Exode", "lév": "Lévitique", "nb": "Nombres",
    "dt": "Deutéronome", "jos": "Josué", "jg": "Juges", "rt": "Ruth",
    "1 s": "1 Samuel", "2 s": "2 Samuel", "1 r": "1 Rois", "2 r": "2 Rois",
    "1 ch": "1 Chroniques", "2 ch": "2 Chroniques", "esd": "Esdras", "neh": "Néhémie",
    "est": "Esther", "job": "Job", "ps": "Psaumes", "pr": "Proverbes",
    "ec": "Ecclésiaste", "ct": "Cantique des cantiques", "és": "Ésaïe", "jér": "Jérémie",
    "lm": "Lamentations", "éz": "Ézéchiel", "dn": "Daniel", "os": "Osée",
    "jl": "Joël", "am": "Amos", "abd": "Abdias", "jon": "Jonas", "mi": "Michée",
    "na": "Nahum", "hab": "Habacuc", "so": "Sophonie", "ag": "Aggée", "za": "Zacharie",
    "ml": "Malachie", "mt": "Matthieu", "mc": "Marc", "lc": "Luc", "jn": "Jean",
    "ac": "Actes", "rm": "Romains", "1 co": "1 Corinthiens", "2 co": "2 Corinthiens",
    "ga": "Galates", "éph": "Éphésiens", "ph": "Philippiens", "col": "Colossiens",
    "1 th": "1 Thessaloniciens", "2 th": "2 Thessaloniciens", "1 tm": "1 Timothée",
    "2 tm": "2 Timothée", "tt": "Tite", "phm": "Philémon", "he": "Hébreux",
    "jc": "Jacques", "1 p": "1 Pierre", "2 p": "2 Pierre", "1 jn": "1 Jean",
    "2 jn": "2 Jean", "3 jn": "3 Jean", "jude": "Jude", "ap": "Apocalypse",
}


def display_book_name(book_abbr: str) -> str:
    """Nom d'affichage complet (accents propres) pour n'importe quelle casse
    d'abréviation. Repli sur get_full_book_name puis titrecase."""
    if not book_abbr:
        return ""
    key = book_abbr.strip().lower()
    if key in BOOK_FULL_NAMES:
        return BOOK_FULL_NAMES[key]
    # abréviation « standard » (Mt, Ac…) : retrouver la clé minuscule équivalente
    for k, full in BOOK_FULL_NAMES.items():
        if k.replace(" ", "") == key.replace(" ", ""):
            return full
    return get_full_book_name(book_abbr)


def format_reference(book_abbr: str, chapter, verse_start=None, verse_end=None) -> str:
    """Référence d'AFFICHAGE : « Jean 3:16 », « Actes 2:38 », « Romains 8:28-30 »."""
    name = display_book_name(book_abbr)
    if verse_start is None:
        return f"{name} {chapter}".strip()
    if verse_end and verse_end != verse_start:
        return f"{name} {chapter}:{verse_start}-{verse_end}"
    return f"{name} {chapter}:{verse_start}"


# Nom d'édition en toutes lettres. « LSG » ne dit rien à une assemblée : ce
# sigle est un code d'initié, et c'est lui qui s'affichait jusqu'ici sous les
# versets projetés. La forme courte reste utile en régie, où la place manque.
BIBLE_VERSION_LABELS = {
    "LSG": ("Louis Segond 1910", "Segond 1910"),
    "KJF": ("King James Française", "King James fr."),
    "NBS": ("Nouvelle Bible Segond", "Nouvelle Segond"),
    "SEM": ("Bible du Semeur", "Semeur"),
    "TOB": ("Traduction œcuménique de la Bible", "TOB"),
    "FC": ("Bible en français courant", "Français courant"),
    "DBY": ("Bible Darby", "Darby"),
}


def version_label(code: str, short: bool = False) -> str:
    """Libellé lisible d'une version ; retombe sur le sigle si inconnue."""
    entry = BIBLE_VERSION_LABELS.get((code or "").upper())
    if not entry:
        return code or ""
    return entry[1] if short else entry[0]


class BibleLoader:
    """Charge plusieurs versions de la Bible et gère la recherche textuelle multi-version"""
    _shared_versions = None
    _shared_index = None
    _shared_phrase_hits = None
    _shared_fuzzy = None
    _shared_manual = None

    def __init__(self, json_path: Optional[str] = None):
        import os

        self.versions = {}  # version_id -> dict (book -> chapter -> verse -> text)
        self.active_version = "LSG"
        self.verse_index = {}  # Index inversé global
        self.curated_phrase_hits = {}

        self.fuzzy_index = None
        self.manual_index = None

        if BibleLoader._shared_versions is not None:
            self.versions = BibleLoader._shared_versions
            self.verse_index = BibleLoader._shared_index or {}
            self.curated_phrase_hits = BibleLoader._shared_phrase_hits or {}
            self.fuzzy_index = BibleLoader._shared_fuzzy
            self.manual_index = BibleLoader._shared_manual
            logger.info(f"📚 BibleLoader réutilisé en mémoire: {len(self.versions)} versions, {len(self.verse_index)} clés")
            return

        # 1. Charge la version par défaut LSG (avec fallbacks).
        #    RESOURCE_DIR d'abord : indispensable en application figée, où le
        #    dossier de travail n'a plus de dossier data/ relatif.
        from ..core.config import RESOURCE_DIR
        lsg_path = json_path or "data/bible.json"
        paths_to_try = [
            lsg_path,
            str(RESOURCE_DIR / "data" / "bible.json"),
            "v2/backend/data/bible.json",
            "../data/bible.json",
            "../../data/bible.json"
        ]

        for p in paths_to_try:
            if os.path.exists(p):
                loaded_lsg = self._load_version("LSG", p)
                if loaded_lsg:
                    self.versions["LSG"] = loaded_lsg
                    logger.info(f"📚 Bible LSG chargée avec succès depuis {p}")
                    break

        # 2. Charge les autres versions converties (celles présentes seulement :
        #    l'app distribuée n'embarque que le domaine public — LSG + KJF).
        from pathlib import Path
        from ..core.config import DATA_DIR
        cache_dirs = [
            str(RESOURCE_DIR / "data" / "bibles_cache"),
            "data/bibles_cache",
            "v2/backend/data/bibles_cache",
            "../data/bibles_cache",
            "../../data/bibles_cache"
        ]

        # On retenait le PREMIER dossier trouvé. Dans l'application installée,
        # c'était celui du paquet — en lecture seule — et une traduction
        # importée par l'église, forcément écrite dans le dossier de données,
        # restait invisible. On parcourt donc les deux : le paquet d'abord, puis
        # les imports, qui peuvent ainsi compléter la liste.
        dossiers_retenus = []
        for cd in cache_dirs:
            if os.path.exists(cd):
                dossiers_retenus.append(cd)
                break
        dossier_imports = str(Path(DATA_DIR) / "bibles_cache")
        if os.path.exists(dossier_imports) and dossier_imports not in dossiers_retenus:
            dossiers_retenus.append(dossier_imports)

        for cache_dir in dossiers_retenus:
            for filename in os.listdir(cache_dir):
                # Les fiches .meta.json accompagnent un import ; ce ne sont pas
                # des bibles et elles n'ont rien à faire dans la liste.
                if filename.endswith(".json") and not filename.endswith(".meta.json"):
                    v_id = filename.replace(".json", "").upper()
                    if v_id == "SEMEUR":
                        v_id = "SEM"
                    elif v_id == "OECUMENIQUE":
                        v_id = "TOB"
                    elif v_id == "FRANCAIS_COURANT":
                        v_id = "FC"
                    elif v_id == "NOUVELLE_SEGOND":
                        v_id = "NBS"

                    path = os.path.join(cache_dir, filename)
                    loaded = self._load_version(v_id, path)
                    if loaded:
                        self.versions[v_id] = loaded

        logger.info(f"📚 {len(self.versions)} versions de la Bible prêtes: {list(self.versions.keys())}")

        # 3. Construit l'index de recherche textuelle global
        self._build_index()
        self._build_curated_phrase_hits()
        self._build_manual_index()
        BibleLoader._shared_versions = self.versions
        BibleLoader._shared_index = self.verse_index
        BibleLoader._shared_phrase_hits = self.curated_phrase_hits
        BibleLoader._shared_manual = self.manual_index

        # 4. Index flou local (citations approximatives / erreurs ASR) — en
        #    arrière-plan pour ne pas retarder le démarrage, sur la version de
        #    référence LSG. Les tests qui couvrent cet index le construisent
        #    explicitement : ne pas laisser ce calcul CPU de 64 Mo survivre au
        #    cycle de vie du TestClient, sinon il affame les tests réseau qui
        #    suivent sur les petits runners GitHub.
        if os.environ.get("VERSEPRO_TESTING") != "1":
            import threading
            threading.Thread(target=self._build_fuzzy_index, daemon=True).start()

    def _build_fuzzy_index(self):
        try:
            from .fuzzy_search import FuzzyVerseIndex
            base = self.versions.get("LSG") or (next(iter(self.versions.values())) if self.versions else None)
            if not base:
                return
            index = FuzzyVerseIndex(base)
            self.fuzzy_index = index
            BibleLoader._shared_fuzzy = index
        except Exception as e:
            logger.error(f"❌ Construction de l'index flou impossible: {e}")

    def _build_manual_index(self):
        """Index exhaustif réservé à la recherche déclenchée par l'opérateur."""
        try:
            import os
            import threading
            from .manual_search import ManualVerseIndex

            active = self.versions.get(self.active_version)
            initial_versions = {self.active_version: active} if active else self.versions
            # Le corpus principal est disponible immédiatement. Charger en
            # série sept traductions ajoutait huit secondes au démarrage du
            # serveur de régie ; les traductions supplémentaires enrichissent
            # donc l'index en arrière-plan, puis le remplacent atomiquement.
            self.manual_index = ManualVerseIndex(initial_versions, self.active_version)

            if len(self.versions) > len(initial_versions):
                def enrich_all_versions():
                    try:
                        complete = ManualVerseIndex(self.versions, self.active_version)
                        self.manual_index = complete
                        BibleLoader._shared_manual = complete
                    except Exception as exc:
                        logger.error(f"❌ Enrichissement de l'index de fragments impossible: {exc}")

                if os.environ.get("VERSEPRO_TESTING") == "1":
                    enrich_all_versions()
                else:
                    threading.Thread(target=enrich_all_versions, daemon=True).start()
        except Exception as exc:
            # La recherche par référence doit rester disponible même sur un
            # poste très contraint ou avec une traduction importée malformée.
            logger.error(f"❌ Construction de l'index de fragments impossible: {exc}")
            self.manual_index = None

    def _load_version(self, v_id: str, path: str) -> dict:
        """Charge une version et la normalise en book_abbr -> { chapter -> { verse -> text } }"""
        import json
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            books_dict = {}

            # Schema 1: books -> chapters -> verses (comme lsg1910)
            if isinstance(data, dict) and "books" in data:
                def to_real(val):
                    return 1 if val == 0 else val

                for book in data.get("books", []):
                    book_name = book.get("name", "").strip()
                    book_abbr = book.get("abbreviation", "").strip()
                    std_abbr = get_standard_abbr(book_name) or book_abbr
                    # Garde-fou : un livre sans abréviation résolue créerait une
                    # clé vide invisible (bug historique « Actes des Apôtres »).
                    if not std_abbr or not std_abbr.strip():
                        logger.warning(f"⚠️ Livre ignoré (abréviation introuvable) : {book_name!r}")
                        continue

                    books_dict[std_abbr.lower()] = {}

                    for ch in book.get("chapters", []):
                        ch_num = to_real(ch.get("chapter", 0))
                        books_dict[std_abbr.lower()][ch_num] = {}

                        for v in ch.get("verses", []):
                            v_num = to_real(v.get("verse", 0))
                            v_text = v.get("text", "").strip()
                            books_dict[std_abbr.lower()][ch_num][v_num] = v_text

            # Schema 2: Testaments -> Books -> Chapters -> Verses
            elif isinstance(data, dict) and "Testaments" in data:
                for testament in data.get("Testaments", []):
                    for book in testament.get("Books", []):
                        book_name = book.get("Text", "").strip()
                        std_abbr = get_standard_abbr(book_name)
                        if not std_abbr:
                            continue

                        books_dict[std_abbr.lower()] = {}

                        for ch_index, ch in enumerate(book.get("Chapters", [])):
                            ch_num = ch.get("ID", ch_index + 1)
                            books_dict[std_abbr.lower()][ch_num] = {}

                            for v_index, v in enumerate(ch.get("Verses", [])):
                                v_num = v.get("ID", v_index + 1)
                                v_text = v.get("Text", "").strip()
                                books_dict[std_abbr.lower()][ch_num][v_num] = v_text

            # Schema 3: Indexation directe par livre 1-66 (comme kjf.json)
            elif isinstance(data, dict) and "1" in data and isinstance(data["1"], dict) and "1" in data["1"]:
                STANDARD_66_BOOKS = [
                    "Gen", "Ex", "Lév", "Nb", "Dt", "Jos", "Jg", "Rt", "1 S", "2 S",
                    "1 R", "2 R", "1 Ch", "2 Ch", "Esd", "Neh", "Est", "Job", "Ps", "Pr",
                    "Ec", "Ct", "És", "Jér", "Lm", "Éz", "Dn", "Os", "Jl", "Am",
                    "Abd", "Jon", "Mi", "Na", "Hab", "So", "Ag", "Za", "Ml",
                    "Mt", "Mc", "Lc", "Jn", "Ac", "Rm", "1 Co", "2 Co", "Ga", "Éph",
                    "Ph", "Col", "1 Th", "2 Th", "1 Tm", "2 Tm", "Tt", "Phm", "He", "Jc",
                    "1 P", "2 P", "1 Jn", "2 Jn", "3 Jn", "Jude", "Ap"
                ]
                for book_idx_str, chapters in data.items():
                    try:
                        book_idx = int(book_idx_str) - 1
                        if 0 <= book_idx < len(STANDARD_66_BOOKS):
                            std_abbr = STANDARD_66_BOOKS[book_idx]
                            books_dict[std_abbr.lower()] = {}

                            for ch_num_str, verses in chapters.items():
                                ch_num = int(ch_num_str)
                                books_dict[std_abbr.lower()][ch_num] = {}

                                for v_num_str, text in verses.items():
                                    v_num = int(v_num_str)
                                    books_dict[std_abbr.lower()][ch_num][v_num] = text.strip()
                    except ValueError:
                        continue

            return books_dict
        except Exception as e:
            logger.error(f"Erreur chargement version {v_id} depuis {path}: {e}")
            return {}

    def _normalize_text(self, text: str) -> str:
        """Normalise le texte : minuscules, suppression des accents et de la ponctuation"""
        text = text.lower()
        text = "".join(c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c) != 'Mn')
        text = re.sub(r"[^\w\s\']", " ", text)
        return " ".join(text.split())

    def _build_index(self):
        """Construit un index inversé global sur les 5 premiers mots de chaque verset"""
        self.verse_index = {}

        # Mots vides ou extrêmement fréquents pour éviter les faux-positifs sur des formules de transition orales
        STOP_WORDS = {
            "il", "y", "a", "point", "de", "le", "la", "les", "car", "je", "vous", "dit", "est",
            "un", "une", "dans", "en", "pour", "ce", "ces", "mon", "ma", "mes", "ton", "ta", "tes",
            "son", "sa", "ses", "et", "ou", "mais", "donc", "or", "ni", "que", "qui", "ceux",
            "celles", "ils", "elles", "nous", "se", "ne", "pas", "plus", "tout", "tous", "faire",
            "fait", "comme", "avec", "sur", "par", "aux", "au", "des", "du", "lui", "leur", "leurs",
            "en", "y", "moi", "toi", "soi", "ete", "ont", "sont", "ces", "ses", "cette"
        }

        LEADING_CONJUNCTIONS = {"car", "et", "mais", "or", "afin", "en", "pour", "ainsi", "par"}
        # On utilise LSG en priorité pour peupler l'index, puis les autres
        # afin de couvrir le maximum de formulations orales.
        for v_id in sorted(self.versions.keys(), key=lambda x: 0 if x == "LSG" else 1):
            version = self.versions[v_id]
            for book_abbr, chapters in version.items():
                for ch_num, verses in chapters.items():
                    for v_num, text in verses.items():
                        if not text:
                            continue
                        norm_text = self._normalize_text(text)
                        all_words = norm_text.split()

                        candidate_windows = []
                        if len(all_words) >= 5:
                            candidate_windows.append(all_words[:5])
                        if len(all_words) >= 6 and all_words[0] in LEADING_CONJUNCTIONS:
                            candidate_windows.append(all_words[1:6])

                        for words in candidate_windows:
                            # Pour éviter d'indexer des phrases trop triviales
                            significant_count = sum(1 for w in words if w not in STOP_WORDS and len(w) >= 3)
                            if significant_count >= 2:
                                key = " ".join(words)
                                if key not in self.verse_index:
                                    self.verse_index[key] = []
                                # Évite les doublons de référence identique
                                if not any(r["book_abbr"] == book_abbr and r["chapter"] == ch_num and r["verse"] == v_num for r in self.verse_index[key]):
                                    self.verse_index[key].append({
                                        "book_abbr": book_abbr,
                                        "chapter": ch_num,
                                        "verse": v_num,
                                        "text": text
                                    })

        logger.info(f"⚡ Index de recherche textuelle global construit: {len(self.verse_index)} phrases uniques")

    def _build_curated_phrase_hits(self):
        """Ajoute des accroches courtes difficiles à trouver avec un index à 5 mots."""
        phrases = {
            "car dieu a tant aime le monde": ("Jn", 3, 16),
            "dieu a tant aime le monde": ("Jn", 3, 16),
            "dieu a tant aime": ("Jn", 3, 16),
            "car dieu a tant aime": ("Jn", 3, 16),
            "dieu est amour": ("1 Jn", 4, 8),
            "l eternel est mon berger": ("Ps", 23, 1),
            "le seigneur est mon berger": ("Ps", 23, 1),
            "je suis le chemin": ("Jn", 14, 6),
            "je suis la verite et la vie": ("Jn", 14, 6),
            "jesus pleura": ("Jn", 11, 35),
            "priez sans cesse": ("1 Th", 5, 17),
            "rejouissez vous toujours": ("1 Th", 5, 16),
            "la foi est une ferme assurance": ("He", 11, 1),
            "je puis tout par celui qui me fortifie": ("Ph", 4, 13),
            "je peux tout par celui qui me fortifie": ("Ph", 4, 13),
            "je peux tout par celui qui me donne la force": ("Ph", 4, 13),
            "au commencement dieu crea": ("Gen", 1, 1),
            "au commencement etait la parole": ("Jn", 1, 1),
        }
        self.curated_phrase_hits = {
            self._normalize_text(phrase): ref
            for phrase, ref in phrases.items()
        }

    def _make_reference_result(self, book_abbr: str, chapter: int, verse: int, detected_from: str) -> Dict[str, Any]:
        ref_text = format_reference(book_abbr, chapter, verse)
        translations = {}
        for v_name in self.versions.keys():
            text_v = self.get_verse_text(book_abbr, chapter, verse, version_id=v_name)
            if text_v:
                translations[v_name] = text_v
        return {
            "book": get_full_book_name(book_abbr),
            "book_abbr": book_abbr,
            "chapter": chapter,
            "verse_start": verse,
            "verse_end": None,
            "reference": ref_text,
            "text": self.get_verse_text(book_abbr, chapter, verse),
            "translations": translations,
            "detected_from": detected_from[:100],
            "detection_method": "text_phrase",
            "confidence": 0.96,
        }

    def get_verse_text(self, book_abbr: str, chapter: int, verse_start: Optional[int], verse_end: Optional[int] = None, version_id: Optional[str] = None) -> str:
        """Récupère le texte du ou des versets pour la version spécifiée ou active"""
        if verse_start is None:
            return ""

        v_id = version_id or self.active_version
        version = self.versions.get(v_id)
        if not version:
            if not self.versions:
                return ""
            version = list(self.versions.values())[0]

        book_key = book_abbr.lower()
        if book_key not in version:
            return ""

        ch_dict = version[book_key]
        if chapter not in ch_dict:
            return ""

        v_dict = ch_dict[chapter]

        verses_to_find = list(range(verse_start, (verse_end or verse_start) + 1))
        found_texts = []

        for v_num in verses_to_find:
            if v_num in v_dict:
                found_texts.append(v_dict[v_num])

        return " ".join(found_texts)

    def search_by_text(self, query_text: str) -> Optional[Dict[str, Any]]:
        """Recherche une référence à partir d'une phrase textuelle parlée"""
        if not self.versions or not query_text:
            return None

        norm_query = self._normalize_text(query_text)
        words = norm_query.split()

        for phrase, (book_abbr, chapter, verse) in self.curated_phrase_hits.items():
            if phrase in norm_query:
                return self._make_reference_result(book_abbr, chapter, verse, query_text)

        if len(words) < 5:
            return None

        # 1. Recherche par les 5 premiers mots (index inversé très rapide) - De droite à gauche (plus récent d'abord)
        for i in range(len(words) - 5, -1, -1):
            for length in range(min(5, len(words) - i), 4, -1):
                phrase = " ".join(words[i : i + length])
                if phrase in self.verse_index:
                    match = self.verse_index[phrase][0]
                    ref_text = format_reference(match['book_abbr'], match['chapter'], match['verse'])

                    # Récupération de toutes les traductions disponibles pour la comparaison
                    translations = {}
                    for v_name in self.versions.keys():
                        text_v = self.get_verse_text(match['book_abbr'], match['chapter'], match['verse'], version_id=v_name)
                        if text_v:
                            translations[v_name] = text_v

                    return {
                        "book": get_full_book_name(match['book_abbr']),
                        "book_abbr": match["book_abbr"],
                        "chapter": match["chapter"],
                        "verse_start": match["verse"],
                        "verse_end": None,
                        "reference": ref_text,
                        "text": self.get_verse_text(match['book_abbr'], match['chapter'], match['verse']),
                        "translations": translations,
                        "detected_from": query_text[:100],
                        "detection_method": "text_index",
                        "confidence": 0.9,
                    }

        # 2. (Supprimé) L'ancien scan par sous-chaîne parcourait ~180 000 versets
        #    en BLOQUANT la boucle d'événements ~2,6 s par phrase sans détection —
        #    cause directe des transcripts saccadés et des projections en retard.
        #    L'index flou ci-dessous couvre ce cas en ~10 ms.

        # 3. Recherche floue locale : citations approximatives, mots déformés par l'ASR.
        #    Confiance plafonnée sous le seuil d'autopilotage -> toujours en validation manuelle.
        if self.fuzzy_index:
            matches = self.fuzzy_index.search(norm_query, top_k=1, min_score=0.55)
            if matches:
                m = matches[0]
                result = self._make_reference_result(m["book_abbr"], m["chapter"], m["verse"], query_text)
                result["detection_method"] = "text_fuzzy"
                result["confidence"] = round(min(0.9, 0.55 + m["score"] * 0.35), 2)
                return result

        return None

    def translations_for(self, book_abbr: str, chapter: int, verse: int) -> dict:
        """Texte du verset dans chaque version disponible (pour confirmer un
        recouvrement lexical quel que soit la traduction paraphrasée)."""
        out = {}
        for v_name in self.versions.keys():
            text_v = self.get_verse_text(book_abbr, chapter, verse, version_id=v_name)
            if text_v:
                out[v_name] = text_v
        return out

    def search_candidates(self, query_text: str, limit: int = 6) -> list:
        """Candidats multiples pour la palette de recherche (aperçu + score)."""
        results = []
        seen = set()

        def push(book_abbr, chapter, verse, method, score):
            key = f"{book_abbr}|{chapter}|{verse}"
            if key in seen:
                return
            seen.add(key)
            res = self._make_reference_result(book_abbr, chapter, verse, query_text)
            res["detection_method"] = method
            res["confidence"] = score
            results.append(res)

        norm_query = self._normalize_text(query_text)

        # Accroches connues et index exact
        for phrase, (b, c, v) in self.curated_phrase_hits.items():
            if phrase in norm_query:
                push(b, c, v, "text_phrase", 0.96)
        exact = self.search_by_text(query_text)
        if exact and exact.get("verse_start") is not None:
            push(exact["book_abbr"], exact["chapter"], exact["verse_start"], exact["detection_method"], exact["confidence"])

        # Voisins flous
        if self.fuzzy_index and len(results) < limit:
            for m in self.fuzzy_index.search(norm_query, top_k=limit, min_score=0.45):
                push(m["book_abbr"], m["chapter"], m["verse"], "text_fuzzy", round(min(0.9, 0.55 + m["score"] * 0.35), 2))

        return results[:limit]

    def search_manual_candidates(self, query_text: str, limit: int = 12) -> list:
        """Recherche opérateur : fragment situé n'importe où dans un verset.

        Ce chemin est volontairement séparé de ``search_candidates`` : les
        fragments très courts sont utiles quand un humain les tape, mais trop
        ambigus pour déclencher la détection automatique d'un culte.
        """
        if not self.manual_index:
            return self.search_candidates(query_text, limit)

        results = []
        for match in self.manual_index.search(query_text, top_k=max(limit * 2, 12)):
            result = self._make_reference_result(
                match["book_abbr"], match["chapter"], match["verse"], query_text
            )
            verse_end = match.get("verse_end")
            if verse_end:
                result["verse_end"] = verse_end
                result["reference"] = format_reference(
                    match["book_abbr"], match["chapter"], match["verse"], verse_end
                )
                result["text"] = self.get_verse_text(
                    match["book_abbr"], match["chapter"], match["verse"], verse_end
                )
            result["detection_method"] = match["detection_method"]
            result["confidence"] = match["score"]
            result["matched_version"] = match.get("matched_version")
            result["matched_text"] = match.get("matched_text")
            results.append(result)
        return results[:limit]


class VerseParserService:
    """
    Service de parsing de références bibliques v2 avec multi-traduction et correction d'homophones
    """

    def __init__(self, bible_json_path: Optional[str] = None):
        self.book_names = self._load_book_names()
        self.book_abbreviations = self._load_abbreviations()
        self.chapter_counts = self._load_chapter_counts()
        self.patterns = self._compile_patterns()
        self.inc_patterns = self._compile_inc_patterns()

        # Tableaux de correspondance insensibles aux accents
        self.clean_book_names = {strip_accents(k): v for k, v in self.book_names.items()}

        # Initialise le chargeur de texte biblique multi-version
        self.bible_loader = BibleLoader(bible_json_path)

        logger.info("✅ Parser de versets initialisé")

    def _load_book_names(self) -> Dict[str, str]:
        """Charge le dictionnaire complet de correspondance de livres"""
        return {
            # Ancien Testament
            "genèse": "Gen", "gen": "Gen", "gn": "Gen",
            "exode": "Ex", "ex": "Ex",
            "lévitique": "Lév", "lév": "Lév", "lv": "Lév",
            "nombres": "Nb", "nbr": "Nb", "nb": "Nb",
            "deutéronome": "Dt", "deut": "Dt", "dt": "Dt",
            "josué": "Jos", "jos": "Jos",
            "juges": "Jg", "jug": "Jg", "jg": "Jg",
            "ruth": "Rt", "rut": "Rt", "rt": "Rt",
            "1 samuel": "1 S", "1sam": "1 S", "1s": "1 S", "1 s": "1 S",
            "2 samuel": "2 S", "2sam": "2 S", "2s": "2 S", "2 s": "2 S",
            "1 rois": "1 R", "1rois": "1 R", "1r": "1 R", "1 r": "1 R",
            "2 rois": "2 R", "2rois": "2 R", "2r": "2 R", "2 r": "2 R",
            "1 chroniques": "1 Ch", "1chron": "1 Ch", "1ch": "1 Ch", "1 ch": "1 Ch",
            "2 chroniques": "2 Ch", "2chron": "2 Ch", "2ch": "2 Ch", "2 ch": "2 Ch",
            "esdras": "Esd", "esd": "Esd",
            "néhémie": "Neh", "neh": "Neh",
            "esther": "Est", "est": "Est",
            "job": "Job", "jb": "Job",
            "psaumes": "Ps", "psaume": "Ps", "ps": "Ps",
            "proverbes": "Pr", "prov": "Pr", "pr": "Pr",
            "ecclésiaste": "Ec", "eccl": "Ec", "ec": "Ec",
            "cantique": "Ct", "cant": "Ct", "ct": "Ct", "cantique des cantiques": "Ct",
            "ésaïe": "És", "esai": "És", "es": "És",
            "jérémie": "Jér", "jer": "Jér", "jr": "Jér",
            "lamentations": "Lm", "lam": "Lm", "lm": "Lm", "lamentations de jeremie": "Lm", "lamentations de jérémie": "Lm",
            "ézéchiel": "Éz", "ez": "Éz",
            "daniel": "Dn", "dan": "Dn", "dn": "Dn",
            "osée": "Os", "ose": "Os",
            "joël": "Jl", "joel": "Jl",
            "amos": "Am", "am": "Am",
            "abdias": "Abd", "abd": "Abd",
            "jonas": "Jon", "jon": "Jon",
            "micée": "Mi", "michee": "Mi", "mi": "Mi",
            "nahum": "Na", "na": "Na",
            "habacuc": "Hab", "hab": "Hab",
            "sophonie": "So", "soph": "So",
            "aggée": "Ag", "agee": "Ag", "ag": "Ag",
            "zacharie": "Za", "zach": "Za",
            "malachie": "Ml", "mal": "Ml",

            # Nouveau Testament
            "matthieu": "Mt", "mat": "Mt", "mt": "Mt",
            "marc": "Mc", "mar": "Mc", "mc": "Mc",
            "luc": "Lc",
            "jean": "Jn", "jn": "Jn",
            "actes": "Ac", "act": "Ac", "ac": "Ac", "actes des apotres": "Ac", "actes des apôtres": "Ac",
            "romains": "Rm", "rom": "Rm", "rm": "Rm",
            "1 corinthiens": "1 Co", "1cor": "1 Co", "1co": "1 Co", "1 co": "1 Co",
            "2 corinthiens": "2 Co", "2cor": "2 Co", "2co": "2 Co", "2 co": "2 Co",
            "galates": "Ga", "gal": "Ga",
            "éphésiens": "Éph", "eph": "Éph",
            "philippiens": "Ph", "phil": "Ph",
            "colossiens": "Col", "col": "Col",
            "1 thessaloniciens": "1 Th", "1thes": "1 Th", "1th": "1 Th", "1 th": "1 Th",
            "2 thessaloniciens": "2 Th", "2thes": "2 Th", "2th": "2 Th", "2 th": "2 Th",
            "1 timothée": "1 Tm", "1tim": "1 Tm", "1tm": "1 Tm", "1 tm": "1 Tm",
            "2 timothée": "2 Tm", "2tim": "2 Tm", "2tm": "2 Tm", "2 tm": "2 Tm",
            "tite": "Tt", "tit": "Tt",
            "philémon": "Phm", "phm": "Phm",
            "hébreux": "He", "heb": "He",
            "jacques": "Jc", "jac": "Jc",
            "1 pierre": "1 P", "1pier": "1 P", "1p": "1 P", "1 p": "1 P",
            "2 pierre": "2 P", "2pier": "2 P", "2p": "2 P", "2 p": "2 P",
            "1 jean": "1 Jn", "1jn": "1 Jn", "1 jn": "1 Jn",
            "2 jean": "2 Jn", "2jn": "2 Jn", "2 jn": "2 Jn",
            "3 jean": "3 Jn", "3jn": "3 Jn", "3 jn": "3 Jn",
            "jude": "Jude", "jud": "Jude",
            "apocalypse": "Ap", "apoc": "Ap", "ap": "Ap",
            "révélation": "Ap", "rev": "Ap",
        }

    def _load_abbreviations(self) -> Dict[str, str]:
        """Charge les abréviations courantes"""
        return {
            "1 co": "1 corinthiens",
            "2 co": "2 corinthiens",
            "1 th": "1 thessaloniciens",
            "2 th": "2 thessaloniciens",
            "1 tm": "1 timothée",
            "2 tm": "2 timothée",
            "1 s": "1 samuel",
            "2 s": "2 samuel",
            "1 r": "1 rois",
            "2 r": "2 rois",
            "1 ch": "1 chroniques",
            "2 ch": "2 chroniques",
            "1 p": "1 pierre",
            "2 p": "2 pierre",
            "1 jn": "1 jean",
            "2 jn": "2 jean",
            "3 jn": "3 jean",
        }

    def _load_chapter_counts(self) -> Dict[str, int]:
        """Charge le nombre de chapitres par livre"""
        return {
            "Gen": 50, "Ex": 40, "Lév": 27, "Nb": 36, "Dt": 34,
            "Jos": 24, "Jg": 21, "Rt": 4, "1 S": 31, "2 S": 24,
            "1 R": 22, "2 R": 25, "1 Ch": 29, "2 Ch": 36,
            "Esd": 10, "Neh": 13, "Est": 10, "Job": 42, "Ps": 150,
            "Pr": 31, "Ec": 12, "Ct": 8, "És": 66, "Jér": 52,
            "Lm": 5, "Éz": 48, "Dn": 12, "Os": 14, "Jl": 3,
            "Am": 9, "Abd": 1, "Jon": 4, "Mi": 7, "Na": 3,
            "Hab": 3, "So": 3, "Ag": 2, "Za": 14, "Ml": 4,
            "Mt": 28, "Mc": 16, "Lc": 24, "Jn": 21, "Ac": 28,
            "Rm": 16, "1 Co": 16, "2 Co": 13, "Ga": 6, "Éph": 6,
            "Ph": 4, "Col": 4, "1 Th": 5, "2 Th": 3,
            "1 Tm": 6, "2 Tm": 4, "Tt": 3, "Phm": 1, "He": 13,
            "Jc": 5, "1 P": 5, "2 P": 3, "1 Jn": 5, "2 Jn": 1,
            "3 Jn": 1, "Jude": 1, "Ap": 22,
        }

    RANGE_WITHOUT_VERSET_PATTERN_INDEX = 4
    CHAPTER_ONLY_PATTERN_INDEX = 5
    SINGLE_CHAPTER_PATTERN_INDEX = 6
    INVERTED_A_PATTERN_INDEX = 7
    INVERTED_B_PATTERN_INDEX = 8

    def _compile_patterns(self) -> List[re.Pattern]:
        """Compile les patterns regex optimisés (évite le greedy matching)"""
        books = sorted(STANDARD_BOOK_MAP.keys(), key=len, reverse=True)
        books_pattern = "|".join(re.escape(b) for b in books)

        patterns = [
            # 0: "Jean 3:16" ou "Jn 3:16" ou "1 Co 13:4-8"
            re.compile(r'\b((?:\d+\s+)?[A-Za-zÀ-ÿ]+(?:\s+(?:de|des)\s+[A-Za-zÀ-ÿ]+)?)\s+(\d+)\s*[:\.]\s*(\d+)(?:\s*(?:[-–àa]|et(?:\s+le\s+verset)?|jusqu(?:\'| )?au(?:\s+verset)?)\s*(\d+))?\b', re.IGNORECASE),

            # 1: "Jean chapitre 3 verset 16" ou "Matthieu chapitre 8, et je lis à partir du verset 2"
            re.compile(r'\b((?:\d+\s+)?[A-Za-zÀ-ÿ]+(?:\s+(?:de|des)\s+[A-Za-zÀ-ÿ]+)?)(?:\s+(?:au|aux|dans|le|la|livre\s+de|épître\s+aux))*\s+(?:chapitre|ch\.?|chap\.?)\s*(\d+)(?:[\s,]+(?:[^\d\n]{1,45}?\s+)?)?(?:versets?|v\.?s?)\s*(\d+)(?:\s*(?:[-–àa]|et(?:\s+le\s+verset)?|jusqu(?:\'| )?au(?:\s+verset)?)\s*(\d+))?\b', re.IGNORECASE),

            # 2: "Jean 3 verset 16" ou "Matthieu 8, et je lis au verset 2"
            re.compile(r'\b((?:\d+\s+)?[A-Za-zÀ-ÿ]+(?:\s+(?:de|des)\s+[A-Za-zÀ-ÿ]+)?)\s+(\d+)(?:[\s,]+(?:[^\d\n]{1,45}?\s+)?)?(?:versets?|v\.?s?)\s*(\d+)(?:\s*(?:[-–àa]|et(?:\s+le\s+verset)?|jusqu(?:\'| )?au(?:\s+verset)?)\s*(\d+))?\b', re.IGNORECASE),

            # 3: "Jean 3 16" (sans séparateur, par exemple après conversion des mots de Vosk)
            # ⚠️ Pattern "loose" : sujet aux faux positifs sur du langage courant converti en
            # chiffres — sa confiance est plafonnée sous le seuil d'autopilotage (voir LOOSE_PATTERN_INDEX)
            re.compile(r'\b((?:\d+\s+)?[A-Za-zÀ-ÿ]+(?:\s+(?:de|des)\s+[A-Za-zÀ-ÿ]+)?)\s+(\d+)\s+(\d+)(?:\s*(?:[-–àa]|jusqu(?:\'| )?au(?:\s+verset)?)\s*(\d+))?\b', re.IGNORECASE),

            # 4: « Actes chapitre 16, 16 à 19 ». Les moteurs ASR omettent
            # souvent le second mot « verset ». Le mot « chapitre » et le
            # connecteur de plage gardent cette forme suffisamment stricte.
            re.compile(r'\b((?:\d+\s+)?[A-Za-zÀ-ÿ]+(?:\s+(?:de|des)\s+[A-Za-zÀ-ÿ]+)?)(?:\s+(?:au|aux|dans|le|la))*\s+(?:chapitre|ch\.?|chap\.?)\s*(\d+)[\s,]+(\d+)\s*(?:[-–àa]|jusqu(?:\'| )?au(?:\s+verset)?|et(?:\s+le\s+verset)?)\s*(\d+)\b', re.IGNORECASE),

            # 5: "Ésaïe chapitre 53" : candidat chapitre seul, sans inventer un verset 1.
            re.compile(r'\b((?:\d+\s+)?[A-Za-zÀ-ÿ]+(?:\s+(?:de|des)\s+[A-Za-zÀ-ÿ]+)?)(?:\s+(?:au|aux|dans|le|la))*\s+(?:chapitre|ch\.?|chap\.?)\s*(\d+)\b', re.IGNORECASE),

            # 6: "Jude verset 24" : livre à CHAPITRE UNIQUE, cité sans chapitre
            re.compile(r'\b((?:\d+\s+)?[A-Za-zÀ-ÿ]+)(?:\s+(?:au|aux|dans|le|la))*\s+(?:versets?|v\.?)\s*(\d+)(?:\s*(?:[-–àa])\s*(\d+))?\b', re.IGNORECASE),

            # 7: Inversé A: "verset 2 du chapitre 8 de Matthieu"
            re.compile(r'\b(?:versets?|v\.?s?)\s*(\d+)(?:\s*(?:[-–àa]|jusqu(?:\'| )?au(?:\s+verset)?)\s*(\d+))?(?:[\s,]+(?:du|dans|au|dans\s+le)\s*(?:chapitre|ch\.?|chap\.?)\s*(\d+))(?:[\s,]+(?:de|des|du|dans|dans\s+le\s+livre\s+de|d\'|à))\s+\b(' + books_pattern + r')\b', re.IGNORECASE),

            # 8: Inversé B: "verset 2 dans Matthieu chapitre 8" ou "verset 2 dans Matthieu 8"
            re.compile(r'\b(?:versets?|v\.?s?)\s*(\d+)(?:\s*(?:[-–àa]|jusqu(?:\'| )?au(?:\s+verset)?)\s*(\d+))?(?:[\s,]+(?:dans|de|du|dans\s+le\s+livre\s+de|dans\s+l\'|d\'|à))\s+\b(' + books_pattern + r')\b(?:[\s,]+(?:au|dans|le|la|livre\s+de))*\s*(?:chapitre|ch\.?|chap\.?)?\s*(\d+)\b', re.IGNORECASE),
        ]
        return patterns

    def _compile_inc_patterns(self) -> List[re.Pattern]:
        """Compile les regex pour la détection incrémentale (Livre seul, Livre + Chapitre)"""
        # On regroupe les noms de livres triés par longueur décroissante
        books = sorted(STANDARD_BOOK_MAP.keys(), key=len, reverse=True)
        books_pattern = "|".join(re.escape(b) for b in books)

        return [
            # 0. Livre + Chapitre ("dans jean 3" ou "jean chapitre 3")
            re.compile(rf'\b((?:\d+\s+)?[A-Za-zÀ-ÿ]+(?:\s+(?:de|des)\s+[A-Za-zÀ-ÿ]+)?)(?:\s+(?:au|aux|dans|le|la))*\s+(?:chapitre|ch\.?|chap\.?)?\s*(\d+)\b', re.IGNORECASE),

            # 1. Livre seul ("dans jean", "lisons jean")
            re.compile(rf'\b((?:\d+\s+)?[A-Za-zÀ-ÿ]+(?:\s+(?:de|des)\s+[A-Za-zÀ-ÿ]+)?)\b', re.IGNORECASE)
        ]

    # Index du pattern "livre chiffre chiffre" (sans séparateur) dans la liste ci-dessus
    LOOSE_PATTERN_INDEX = 3

    # Livres à plusieurs épîtres : « première/seconde/troisième … » devient « 1/2/3 … »
    _ORDINAL_BOOK_RE = re.compile(
        r"\b(premi[eè]re?|1[eè]?re|second[e]?|deuxi[eè]me|2[eè]?me|troisi[eè]me|3[eè]?me)\s+"
        r"(?:[ée]p[iî]tre\s+|lettre\s+)?(?:de\s+|d'|aux\s+|à\s+)?"
        r"(jean|pierre|corinthiens|thessaloniciens|timoth[ée]e|samuel|rois|chroniques)\b",
        re.IGNORECASE,
    )

    @classmethod
    def _convert_ordinal_books(cls, text: str) -> str:
        def repl(m):
            o = m.group(1).lower()
            n = "1" if o.startswith(("premi", "1")) else ("3" if o.startswith(("troisi", "3")) else "2")
            return f"{n} {m.group(2)}"
        return cls._ORDINAL_BOOK_RE.sub(repl, text)

    # Ordinal désignant un VERSET ou un CHAPITRE — « au psaume 23, premier
    # verset » est une formule courante en chaire, et elle n'était pas comprise :
    # seule la forme « verset un » l'était. On réécrit vers cette forme.
    _ORDINAUX_RANG = {
        "premier": 1, "première": 1, "premiere": 1, "1er": 1, "1re": 1, "1ère": 1,
        "deuxième": 2, "deuxieme": 2, "second": 2, "seconde": 2, "2e": 2, "2ème": 2,
        "troisième": 3, "troisieme": 3, "3e": 3, "3ème": 3,
        "quatrième": 4, "quatrieme": 4, "cinquième": 5, "cinquieme": 5,
        "sixième": 6, "sixieme": 6, "septième": 7, "septieme": 7,
        "huitième": 8, "huitieme": 8, "neuvième": 9, "neuvieme": 9,
        "dixième": 10, "dixieme": 10, "onzième": 11, "onzieme": 11,
        "douzième": 12, "douzieme": 12, "treizième": 13, "treizieme": 13,
        "quatorzième": 14, "quatorzieme": 14, "quinzième": 15, "quinzieme": 15,
        "seizième": 16, "seizieme": 16, "dix-septième": 17, "dix-huitième": 18,
        "dix-neuvième": 19, "vingtième": 20, "vingtieme": 20,
    }
    _ORDINAL_RANG_RE = re.compile(
        r"\b(" + "|".join(sorted((re.escape(o) for o in _ORDINAUX_RANG), key=len, reverse=True))
        + r")\s+(versets?|chapitres?)\b",
        re.IGNORECASE,
    )

    @classmethod
    def _convert_ordinal_ranks(cls, text: str) -> str:
        """« premier verset » devient « verset 1 », « deuxième chapitre » devient
        « chapitre 2 » : la place du nombre est rétablie pour les motifs."""
        def repl(m):
            rang = cls._ORDINAUX_RANG[m.group(1).lower()]
            mot = m.group(2).lower().rstrip("s")
            return f"{mot} {rang}"
        return cls._ORDINAL_RANG_RE.sub(repl, text)

    def _clean_homophones(self, text: str) -> str:
        """Nettoie le texte en corrigeant les homophones vocaux ASR courants en français"""
        text = text.lower()
        text = self._convert_ordinal_books(text)
        # Nemotron/Deepgram transcrivent parfois « première Jean » comme
        # « un Jean ». La correction est volontairement limitée à une amorce
        # de référence pour ne pas réécrire la parole ordinaire.
        text = re.sub(r"\bun\s+jean\s+(?=(?:au\s+)?chapitre\b)", "1 jean ", text)
        text = re.sub(r"\bun\s+pi[eè]ge\s+(?=(?:au\s+)?chapitre\b)", "1 pierre ", text)
        # Après les livres ordinaux (« première épître de Jean »), pour ne pas
        # confondre un rang de livre avec un rang de verset.
        text = self._convert_ordinal_ranks(text)
        replacements = {
            r'\bgens\b': 'jean',
            r'\brm\b': 'romains',
            r'\brom\b': 'romains',
            r'\bro\b': 'romains',
            r'\bromain\b': 'romains',
            r'\bjn\b': 'jean',
            r'\bps\b': 'psaumes',
            r'\beph\b': 'éphésiens',
            r'\bapoc\b': 'apocalypse',
            r'\bpoème\b': 'psaume',
            r'\bpoèmes\b': 'psaumes',
            r'\bgenese\b': 'genèse',
            r'\besaie\b': 'ésaïe',
            r'\bjeremie\b': 'jérémie',
            r'\bezechiel\b': 'ézéchiel',
            r'\bephesiens\b': 'éphésiens',
            r'\bhebreux\b': 'hébreux',
            r'\bphilemon\b': 'philémon',
            r'\b1 co\b': '1 corinthiens',
            r'\b2 co\b': '2 corinthiens',
            r'\b1co\b': '1 corinthiens',
            r'\b2co\b': '2 corinthiens',
            r'\b1 th\b': '1 thessaloniciens',
            r'\b2 th\b': '2 thessaloniciens',
            r'\b1th\b': '1 thessaloniciens',
            r'\b2th\b': '2 thessaloniciens',
            r'\b1 tm\b': '1 timothée',
            r'\b2 tm\b': '2 timothée',
            r'\b1tm\b': '1 timothée',
            r'\b2tm\b': '2 timothée',
            r'\b1 s\b': '1 samuel',
            r'\b2 s\b': '2 samuel',
            r'\b1s\b': '1 samuel',
            r'\b2s\b': '2 samuel',
            r'\b1 r\b': '1 rois',
            r'\b2 r\b': '2 rois',
            r'\b1r\b': '1 rois',
            r'\b2r\b': '2 rois',
            r'\b1 ch\b': '1 chroniques',
            r'\b2 ch\b': '2 chroniques',
            r'\b1ch\b': '1 chroniques',
            r'\b2ch\b': '2 chroniques',
            r'\b1 p\b': '1 pierre',
            r'\b2 p\b': '2 pierre',
            r'\b1p\b': '1 pierre',
            r'\b2p\b': '2 pierre',
            r'\b1 jn\b': '1 jean',
            r'\b2 jn\b': '2 jean',
            r'\b3 jn\b': '3 jean',
            r'\b1jn\b': '1 jean',
            r'\b2jn\b': '2 jean',
            r'\b3jn\b': '3 jean',
        }
        for pattern, replacement in replacements.items():
            text = re.sub(pattern, replacement, text)
        return text

    def _convert_spoken_numbers(self, text: str) -> str:
        """Convertit les nombres prononcés en français (un, deux, vingt et un...) en chiffres (1, 2, 21...)"""
        values = {
            "zero": 0, "un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "six": 6, "sept": 7, "huit": 8, "neuf": 9,
            "dix": 10, "onze": 11, "douze": 12, "treize": 13, "quatorze": 14, "quinze": 15, "seize": 16,
            "vingt": 20, "trente": 30, "quarante": 40, "cinquante": 50, "soixante": 60, "cent": 100
        }

        def parse_french_number_words(words: list[str]) -> int:
            total = 0
            current = 0
            for word in words:
                if word == "et":
                    continue
                val = values.get(word, 0)
                if val == 100:
                    if current == 0:
                        current = 100
                    else:
                        current *= 100
                elif val == 20 and current == 4:
                    current = 80
                elif val > current and current > 0:
                    current *= val
                else:
                    total += current
                    current = val
            return total + current

        normalized = text.lower()
        normalized = re.sub(r'(?<=[a-zà-ÿ])-(?=[a-zà-ÿ])', ' ', normalized)
        # Garde : . - pour ne pas dégrader les références déjà bien formatées.
        normalized = re.sub(r'[^a-z0-9à-ÿ\s:\.\-–]', ' ', normalized)
        words = normalized.split()

        new_words = []
        i = 0
        while i < len(words):
            word = words[i]
            if word in values:
                num_sequence = [word]
                current_val = values[word]
                i += 1
                while i < len(words):
                    next_word = words[i]
                    if next_word == "et":
                        num_sequence.append(next_word)
                        i += 1
                        continue
                    next_val = values.get(next_word)
                    if next_val is None:
                        break

                    is_cont = False
                    if next_val == 100:
                        is_cont = True
                    elif next_val == 20 and current_val == 4:
                        is_cont = True
                    elif next_val < current_val:
                        is_cont = True

                    if is_cont:
                        num_sequence.append(next_word)
                        if next_val == 100:
                            current_val = 100 if current_val == 0 else current_val * 100
                        elif next_val == 20 and current_val == 4:
                            current_val = 80
                        else:
                            current_val = next_val
                        i += 1
                    else:
                        break

                while num_sequence and num_sequence[-1] == "et":
                    num_sequence.pop()
                    i -= 1

                val = parse_french_number_words(num_sequence)
                new_words.append(str(val))
            else:
                new_words.append(word)
                i += 1

        return " ".join(new_words)

    RELATIVE_JUMP_RE = re.compile(
        r'\b(?:allons|passons|lisons|sautons|regardons|venons|relisons)?'
        r'(?:\s+(?:au|aux|le|du|vers\s+le))*\s*'
        r'(?:versets?|v\.?)\s*(\d+)(?:\s*(?:[-–àa]|jusqu(?:\'| )?au(?:\s+verset)?)\s*(\d+))?\b',
        re.IGNORECASE
    )

    async def parse(
        self,
        text: str,
        skip_text_search: bool = False,
        active_context: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Parse un texte et extrait la référence biblique (explicite ou par recherche textuelle)

        Args:
            text: Texte transcrit contenant potentiellement une référence
            skip_text_search: Si True, ignore la recherche textuelle en fallback
            active_context: Dictionnaire optionnel avec {"book_abbr": "Mt", "chapter": 8} pour sauts relatifs

        Returns:
            Dictionnaire avec la référence structurée ou None
        """
        if not text:
            return None

        # 1. Correction d'homophones sémantiques vocaux
        cleaned_text = self._clean_homophones(text)

        # 1.5. Conversion des nombres parlés en chiffres (très utile pour Vosk)
        cleaned_text = self._convert_spoken_numbers(cleaned_text)

        # Conservation d'une copie nettoyée pour le regex
        clean_text_regex = cleaned_text.lower().strip()
        clean_text_regex = clean_text_regex.replace(",", " ")

        # 2. Patterns explicites (regex), par groupes de fiabilité décroissante :
        #    formes précises d'abord, puis le pattern "loose", puis le chapitre seul.
        #    Au sein d'un groupe, la référence la plus RÉCEMMENT prononcée prime :
        #    dans un buffer de parole continue ("...jean 3:16 ... puis philippiens
        #    4:13"), c'est le dernier passage cité que le prédicateur commente.
        # Le pattern « sans séparateur » (jean 3 16) ne s'applique que si le contexte
        # contient un indice de citation — sinon la parole libre remplit la file de faux.
        CUE_RE = re.compile(r"\b(verset|versets|chapitre|lisons|lisez|lecture|ouvrez|ouvrons|bible|évangile|evangile|épître|epitre|livre|psaume|selon|écrit|ecrit|parole)\b")
        has_cue = bool(CUE_RE.search(clean_text_regex))

        # Le motif « livre verset N » vient juste après les motifs explicites :
        # il est aussi sûr qu'eux puisqu'il exige un livre à chapitre unique,
        # mais il ne doit pas primer sur une référence pleinement énoncée.
        pattern_groups = [
            (0, 1, 2, self.RANGE_WITHOUT_VERSET_PATTERN_INDEX,
             self.INVERTED_A_PATTERN_INDEX, self.INVERTED_B_PATTERN_INDEX),
            (self.SINGLE_CHAPTER_PATTERN_INDEX,),
            (self.LOOSE_PATTERN_INDEX,),
            (self.CHAPTER_ONLY_PATTERN_INDEX,),
        ]
        is_direct_input = skip_text_search
        for group in pattern_groups:
            if group == (self.LOOSE_PATTERN_INDEX,) and not has_cue and not is_direct_input:
                continue
            candidates = []
            for idx in group:
                for match in self.patterns[idx].finditer(clean_text_regex):
                    candidates.append((match.start(), idx, match))
            # Position décroissante = du plus récent au plus ancien dans la parole
            for _, idx, match in sorted(candidates, key=lambda c: -c[0]):
                reference = self._extract_reference(
                    match, cleaned_text,
                    loose=(idx == self.LOOSE_PATTERN_INDEX),
                    single_chapter=(idx == self.SINGLE_CHAPTER_PATTERN_INDEX),
                    inverted_a=(idx == self.INVERTED_A_PATTERN_INDEX),
                    inverted_b=(idx == self.INVERTED_B_PATTERN_INDEX),
                )
                if reference:
                    if self._validate_reference(reference):
                        if reference.get("verse_start") is None and not skip_text_search:
                            book_abbr = reference["book_abbr"]
                            chapter = reference["chapter"]
                            best_verse = None
                            best_rank = (-1, -1, -1, -1.0)

                            version = self.bible_loader.versions.get(self.bible_loader.active_version)
                            if not version and self.bible_loader.versions:
                                version = list(self.bible_loader.versions.values())[0]

                            if version and book_abbr.lower() in version and chapter in version[book_abbr.lower()]:
                                chapter_verses = version[book_abbr.lower()][chapter]
                                # On retire la référence elle-même avant de
                                # comparer la citation. Sinon « Luc / chapitre
                                # / quinze » compte comme du texte biblique et
                                # avantage arbitrairement les versets courts.
                                quote_text = (
                                    clean_text_regex[:match.start()] + " " + clean_text_regex[match.end():]
                                ).strip()
                                query_tokens = self.bible_loader._normalize_text(quote_text).replace("'", " ").split()

                                def ngrams(tokens, size):
                                    return {
                                        tuple(tokens[i:i + size])
                                        for i in range(max(0, len(tokens) - size + 1))
                                    }

                                query_bigrams = ngrams(query_tokens, 2)
                                query_trigrams = ngrams(query_tokens, 3)
                                from .detection_fusion import best_overlap, content_stems
                                query_stems = content_stems(quote_text)

                                for v_num, v_text in chapter_verses.items():
                                    if not v_text:
                                        continue
                                    translations = self.bible_loader.translations_for(book_abbr, chapter, v_num)
                                    texts = list(translations.values()) or [v_text]
                                    candidate_bigrams = set()
                                    candidate_trigrams = set()
                                    candidate_stems = set()
                                    for candidate_text in texts:
                                        tokens = self.bible_loader._normalize_text(candidate_text).replace("'", " ").split()
                                        candidate_bigrams.update(ngrams(tokens, 2))
                                        candidate_trigrams.update(ngrams(tokens, 3))
                                        candidate_stems.update(content_stems(candidate_text))

                                    trigram_hits = len(query_trigrams & candidate_trigrams)
                                    bigram_hits = len(query_bigrams & candidate_bigrams)
                                    stem_hits = len(query_stems & candidate_stems)
                                    coverage = best_overlap(
                                        quote_text,
                                        {"text": v_text, "translations": translations},
                                    )
                                    # Une séquence de trois mots est le signal
                                    # le plus précis. Sans trigramme, les mots
                                    # distinctifs et leur couverture priment
                                    # sur un bigramme courant (« par la »), qui
                                    # confondait Romains 9:31 avec 9:32.
                                    rank = (trigram_hits, stem_hits, coverage, bigram_hits)
                                    has_evidence = (
                                        trigram_hits >= 1
                                        or (bigram_hits >= 2 and stem_hits >= 1)
                                        or (stem_hits >= 2 and coverage >= 0.45)
                                    )
                                    if has_evidence and rank > best_rank:
                                        best_rank = rank
                                        best_verse = v_num

                            if best_verse:
                                reference["verse_start"] = best_verse
                                reference["reference"] = format_reference(book_abbr, chapter, best_verse)
                                reference["text"] = self.bible_loader.get_verse_text(book_abbr, chapter, best_verse)
                                reference["translations"] = self.bible_loader.translations_for(book_abbr, chapter, best_verse)
                                reference["detection_method"] = "chapter_contextual_text"
                                phrase_hits = best_rank[0] + best_rank[3]
                                reference["confidence"] = min(
                                    0.98,
                                    max(0.85, 0.80 + phrase_hits * 0.03 + best_rank[2] * 0.12),
                                )
                                logger.info(
                                    f"📖 Verset déduit du contexte du chapitre: {reference['reference']} "
                                    f"(3-grammes={best_rank[0]}, 2-grammes={best_rank[3]}, "
                                    f"mots={best_rank[1]}, couverture={best_rank[2]:.2f})"
                                )
                                return reference

                        logger.info(f"📖 Référence explicite détectée: {reference['reference']}")
                        return reference
                    else:
                        logger.debug(f"⚠️ Référence explicite invalide rejetée: {match.group()}")

        if skip_text_search:
            return None

        # 3. Fallback : Recherche textuelle directe dans la Bible (si phrase parlée)
        text_search_res = self.bible_loader.search_by_text(cleaned_text)
        if text_search_res:
            logger.info(f"📖 Référence détectée par texte du verset: {text_search_res['reference']}")
            return text_search_res

        return None

    def parse_incremental(self, text: str) -> Optional[Dict[str, Any]]:
        """
        Analyse une transcription partielle pour détecter progressivement
        le livre, ou le livre + chapitre, avant que le verset complet ne soit prononcé.
        """
        if not text:
            return None

        cleaned_text = self._convert_spoken_numbers(self._clean_homophones(text))
        clean_text_regex = cleaned_text.lower().strip().replace(",", " ")

        # On teste d'abord Livre + Chapitre, puis Livre seul

        # Livre + Chapitre
        for match in self.inc_patterns[0].finditer(clean_text_regex):
            raw_book = match.group(1).strip()
            chapter_str = match.group(2).strip()

            # Reprise de la logique de nettoyage de _extract_reference
            book_name = raw_book.lower()
            book_name = re.sub(r'\s+', ' ', book_name)
            book_name = re.sub(
                r'^(?:livre de|livre des|evangile selon|evangile de|epitre de|epitre aux|epitre de paul aux|epitre de paul de)\s+',
                '',
                book_name
            )

            book_abbr = self._normalize_book(book_name)
            if book_abbr and chapter_str.isdigit():
                return {
                    "book": raw_book,
                    "book_abbr": book_abbr,
                    "chapter": int(chapter_str),
                    "verse": None,
                }

        # Livre seul (on veut le plus récent dans la phrase, d'où finditer et on prend le dernier)
        matches = list(self.inc_patterns[1].finditer(clean_text_regex))
        for match in reversed(matches):
            raw_book = match.group(1).strip()

            # Nettoyage
            book_name = raw_book.lower()
            book_name = re.sub(r'\s+', ' ', book_name)
            book_name = re.sub(
                r'^(?:livre de|livre des|evangile selon|evangile de|epitre de|epitre aux|epitre de paul aux|epitre de paul de)\s+',
                '',
                book_name
            )

            book_abbr = self._normalize_book(book_name)
            if book_abbr:
                return {
                    "book": raw_book,
                    "book_abbr": book_abbr,
                    "chapter": None,
                    "verse": None,
                }

        return None

    def normalize_spoken(self, text: str) -> str:
        """Nettoyage vocal partagé (homophones + nombres parlés). La détection
        hybride s'en sert pour aligner l'entrée lexicale/sémantique sur celle du
        regex explicite : mêmes corrections, mêmes chiffres."""
        if not text:
            return ""
        return self._convert_spoken_numbers(self._clean_homophones(text))

    def _extract_reference(self, match: re.Match, full_text: str, loose: bool = False,
                           single_chapter: bool = False, inverted_a: bool = False, inverted_b: bool = False) -> Optional[Dict[str, Any]]:
        """
        Extrait les informations de référence du match regex.
        """
        try:
            if inverted_a:
                verse_start = int(match.group(1))
                verse_end = int(match.group(2)) if match.group(2) else None
                chapter = int(match.group(3))
                book_name = match.group(4).lower().strip()
                book_abbr = self._normalize_book(book_name)
            elif inverted_b:
                verse_start = int(match.group(1))
                verse_end = int(match.group(2)) if match.group(2) else None
                book_name = match.group(3).lower().strip()
                chapter = int(match.group(4))
                book_abbr = self._normalize_book(book_name)
            elif single_chapter:
                book_name = match.group(1).lower().strip()
                book_name = re.sub(r'\s+', ' ', book_name)
                book_name = re.sub(
                    r'^(?:livre de|livre des|evangile selon|evangile de|epitre de|epitre aux|epitre de paul aux|epitre de paul de)\s+',
                    '',
                    book_name
                )
                book_abbr = self._normalize_book(book_name)
                if not book_abbr or self.chapter_counts.get(book_abbr) != 1:
                    return None
                chapter = 1
                verse_start = int(match.group(2))
                verse_end = int(match.group(3)) if match.lastindex and match.lastindex >= 3 and match.group(3) else None
            else:
                book_name = match.group(1).lower().strip()
                book_name = re.sub(r'\s+', ' ', book_name)
                book_name = re.sub(
                    r'^(?:livre de|livre des|evangile selon|evangile de|epitre de|epitre aux|epitre de paul aux|epitre de paul de)\s+',
                    '',
                    book_name
                )
                chapter = int(match.group(2))

                if match.lastindex >= 3 and match.group(3) is not None:
                    verse_start = int(match.group(3))
                else:
                    verse_start = None

                if match.lastindex >= 4 and match.group(4) is not None:
                    verse_end = int(match.group(4))
                else:
                    verse_end = None

                book_abbr = self._normalize_book(book_name)
            if not book_abbr:
                return None

            if verse_end and verse_start is None:
                verse_end = None

            # Référence d'AFFICHAGE en nom complet (« Actes 2:38 »), l'abréviation
            # reste dans book_abbr pour la recherche/les clés.
            ref_text = format_reference(book_abbr, chapter, verse_start, verse_end)

            # Récupère le texte de la version active
            verse_text = self.bible_loader.get_verse_text(book_abbr, chapter, verse_start, verse_end)

            # Récupère toutes les traductions disponibles pour comparaison
            translations = {}
            if verse_start is not None:
                for v_name in self.bible_loader.versions.keys():
                    text_v = self.bible_loader.get_verse_text(book_abbr, chapter, verse_start, verse_end, version_id=v_name)
                    if text_v:
                        translations[v_name] = text_v

            return {
                "book": self._get_full_book_name(book_abbr),
                "book_abbr": book_abbr,
                "chapter": chapter,
                "verse_start": verse_start,
                "verse_end": verse_end,
                "reference": ref_text,
                "text": verse_text,
                "translations": translations,
                "detected_from": full_text[:100],
                # Segment exact reconnu par la regex. Le moteur hybride peut
                # ainsi retirer « Psaume 3 verset 8 » avant de comparer le
                # texte cité au corpus, sans deviner où finit la référence.
                "matched_reference": match.group(0),
                "detection_method": "chapter_candidate" if verse_start is None else "explicit",
                "confidence": 0.72 if verse_start is None else (0.85 if loose else 0.98),
            }

        except Exception as e:
            logger.error(f"❌ Erreur extraction référence: {e}")
            return None

    def _normalize_book(self, book_name: str) -> Optional[str]:
        """Normalise le nom du livre vers son abréviation en évitant les collisions"""
        book_clean = strip_accents(book_name)

        if book_clean in self.clean_book_names:
            return self.clean_book_names[book_clean]

        for abbr, full in self.book_abbreviations.items():
            abbr_clean = strip_accents(abbr)
            # Une abréviation courte doit correspondre entièrement. Le vieux
            # `startswith` transformait « 1 parking chapitre 5 » en 1 Pierre 5.
            if book_clean == abbr_clean:
                return self.clean_book_names.get(strip_accents(full))

        sorted_names = sorted(self.clean_book_names.keys(), key=len, reverse=True)
        for name in sorted_names:
            if name == book_clean:
                return self.clean_book_names[name]
            if len(book_clean) >= 2 and name.startswith(book_clean):
                return self.clean_book_names[name]

        return None

    def _get_full_book_name(self, abbr: str) -> str:
        """Retourne le nom complet du livre depuis l'abréviation"""
        for name, a in self.book_names.items():
            if a == abbr:
                return name.title()
        return abbr

    def _validate_reference(self, reference: Dict[str, Any]) -> bool:
        """Valide qu'une référence est bibliquement correcte"""
        book_abbr = reference.get("book_abbr")
        chapter = reference.get("chapter")
        verse_start = reference.get("verse_start")
        verse_end = reference.get("verse_end")

        if not book_abbr or not chapter:
            return False

        max_chapters = self.chapter_counts.get(book_abbr)
        if max_chapters and chapter > max_chapters:
            logger.debug(f"❌ Chapitre {chapter} invalide pour {book_abbr} (max: {max_chapters})")
            return False

        if verse_start is None:
            return True

        if verse_start > 176:
            logger.debug(f"❌ Verset {verse_start} invalide (max: 176)")
            return False

        if verse_end and verse_end < verse_start:
            logger.debug(f"❌ Verset fin {verse_end} < début {verse_start}")
            return False

        return True

    async def parse_batch(self, texts: List[str]) -> List[Dict[str, Any]]:
        """Parse plusieurs textes en batch"""
        results = []
        for text in texts:
            ref = await self.parse(text)
            if ref:
                results.append(ref)
        return results
