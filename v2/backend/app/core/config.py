"""
Configuration de VersePro v2
"""

import os
import sys
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
from typing import List


class Settings(BaseSettings):
    """Configuration de l'application"""
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        case_sensitive=True,
    )
    
    # Application
    DEBUG: bool = True
    APP_NAME: str = "VersePro v2"
    VERSION: str = "2.0.0"
    API_TOKEN: str = ""
    # Origines de la fenêtre applicative. Tauri 2 sert la fenêtre depuis
    # « http://tauri.localhost » sous Windows — en HTTP, là où Tauri 1 utilisait
    # HTTPS. Oublier cette origine coupe TOUTES les requêtes HTTP côté Windows
    # (les WebSockets, non soumis au CORS, continuent de passer : l'application
    # semble alors « injoignable » alors que le moteur tourne parfaitement).
    ALLOWED_ORIGINS: str = (
        "http://localhost:3000,http://127.0.0.1:3000,"
        "http://localhost:3001,http://127.0.0.1:3001,"
        "tauri://localhost,http://tauri.localhost,https://tauri.localhost"
    )
    
    # Deepgram API
    DEEPGRAM_API_KEY: str = ""
    DEEPGRAM_MODEL: str = "nova-2"  # Meilleur modèle pour la précision
    DEEPGRAM_LANGUAGE: str = "fr"
    DEEPGRAM_SMART_FORMAT: bool = True  # Formatage intelligent
    
    # Gemini / OpenRouter API (AI Agent)
    GEMINI_API_KEY: str = ""
    OPENROUTER_API_KEY: str = ""
    AI_AGENT_ENABLED: bool = True
    AI_FILTERING_MODE: str = "strict"  # "strict" (filtre sémantique de mots-clés) ou "open" (sans filtre)
    AI_CONFIDENCE_THRESHOLD: int = 95  # Seuil de confiance minimal pour l'IA (en %)
    OPENROUTER_MODEL: str = "google/gemini-2.5-flash"
    GEMINI_MODEL: str = "gemini-2.0-flash"
    OLLAMA_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3.1:8b"
    # Un 8B local répond en 10–15 s (chargement + génération). L'ancien délai de
    # 6 s faisait expirer TOUS les appels : l'arbitrage local ne rendait jamais
    # rien. Il ne tourne qu'en dernier recours, en tâche de fond.
    OLLAMA_TIMEOUT: float = 30.0
    
    # ProPresenter
    PROPRESENTER_HOST: str = "127.0.0.1"
    PROPRESENTER_PORT: int = 1025  # Port de l'API ProPresenter 7.9+ (Réglages → Réseau)
    # Nom du « Message » préparé dans ProPresenter : c'est LUI qui porte les
    # habillages de l'église. VersePro ne fait que remplir ses jetons.
    PROPRESENTER_MESSAGE_NAME: str = "VersePro"
    PROPRESENTER_AUTO_CONNECT: bool = True
    PROPRESENTER_AUTO_SEND: bool = False  # Envoi automatique ou validation manuelle
    SUNDAY_SAFE_MODE: bool = True  # Interdit toute projection automatique
    SHADOW_MODE: bool = False  # Détecte et mesure sans piloter les sorties
    
    # Parser
    BIBLE_VERSION: str = "LSG"  # Louis Segond 1910
    VALIDATE_REFERENCES: bool = True  # Valider les références (chapitres/versets existants)
    
    # Projection & Themes
    # Version de l'application et contrôle de mise à jour.
    # URL VIDE = contrôle désactivé, aucun appel réseau. VersePro ne téléphone
    # nulle part par défaut : c'est un outil d'église, il doit pouvoir tourner
    # sans jamais sortir du bâtiment. Renseigner l'URL d'un manifeste JSON
    # {"version": "2.1.0", "url": "https://…", "notes": "…"} pour l'activer.
    APP_VERSION: str = "2.0.0"
    UPDATE_CHECK_URL: str = ""
    UPDATE_CHECK_TIMEOUT: float = 6.0

    PROJECTION_THEME: str = "presentation"
    # Zones de texte de l'habillage personnalisé (JSON, pourcentages du cadre).
    # Vide = valeurs de départ de overlay_store.DEFAULT_ZONES.
    OVERLAY_ZONES: str = ""
    # Formes vectorielles construites dans VersePro (JSON). Vide = formes de
    # départ ; une liste vide explicite « [] » signifie « aucune forme ».
    OVERLAY_SHAPES: str = ""
    PROJECTION_STYLE: str = "default"
    SHOW_BIBLE_VERSION: bool = True
    DUAL_TRANSLATIONS: str = "LSG,KJF"
    
    # Audio
    AUDIO_SAMPLE_RATE: int = 16000
    AUDIO_CHUNK_SIZE: int = 4096
    ASR_DEFAULT_ENGINE: str = "auto"  # auto, deepgram, whisper, vosk, local_auto
    WHISPER_MODEL: str = "auto"  # auto choisit tiny/base/small selon la machine
    WHISPER_COMPUTE_TYPE: str = "int8"
    WHISPER_CHUNK_SECONDS: float = 2.4
    WHISPER_OVERLAP_SECONDS: float = 0.25
    WHISPER_BEAM_SIZE: int = 1
    WHISPER_AUTO_DOWNLOAD: bool = False
    
    # WebSocket
    WS_HEARTBEAT_INTERVAL: int = 30  # secondes
    
    # Vosk — moteur local de référence. Au réel, le grand modèle FR s'est
    # montré nettement plus juste et plus réactif que Whisper fenêtré ; son
    # poids (~1,4 Go) n'est payé qu'une fois, au téléchargement explicite.
    VOSK_MODEL_TYPE: str = "large"
    VOSK_MODEL_SHA256: str = ""  # À renseigner pour imposer la vérification du fournisseur

    # Recherche sémantique locale. Le moteur ONNX est optionnel et retombe
    # automatiquement sur l'index lexical si le runtime n'est pas disponible.
    LOCAL_SEMANTIC_ENABLED: bool = True
    # Encodeur sémantique unique : e5-small ONNX (~118 Mo). Qwen a été évalué
    # (0,6 Md, ~585 Mo) puis écarté : sur le corpus biblique il ne séparait pas
    # proprement signal et bruit (chevauchement des scores) — e5 fait mieux et
    # reste léger.
    # e5-BASE par défaut, e5-small en repli s'il n'est pas encore téléchargé.
    # Mesuré sur le corpus de référence (17 énoncés vrais / 8 de bruit) :
    #   e5-small : signal min 0.8682 < bruit max 0.8758 → SÉPARATION -0.0076,
    #              aucun seuil ne peut trancher proprement ;
    #   e5-base  : signal min 0.8411 > bruit max 0.8360 → SÉPARATION +0.0051.
    # C'est le pouvoir de séparation, pas la taille, qui était le plafond :
    # Qwen (0,6 Md, génératif détourné) faisait PIRE qu'e5-small.
    LOCAL_SEMANTIC_MODEL: str = "e5-base"
    LOCAL_SEMANTIC_FALLBACK: str = "e5-small"
    LOCAL_SEMANTIC_CALIBRATION: dict = {
        "e5-base": {"threshold": 0.8385, "margin": 0.005},   # milieu de la bande mesurée
        "e5-small": {"threshold": 0.865, "margin": 0.012},
    }
    LOCAL_SEMANTIC_THRESHOLD: float = 0.8385
    LOCAL_SEMANTIC_MARGIN: float = 0.005
    LOCAL_SEMANTIC_TOP_K: int = 5
    LOCAL_SEMANTIC_AUTO_DOWNLOAD: bool = False
    # Fusion hybride (détection des paraphrases) : recouvrement lexical minimal
    # de confirmation, et bonus d'accord entre récupérateurs indépendants.
    HYBRID_OVERLAP_MIN: float = 0.34
    HYBRID_TOP_K: int = 6
    # La récupération des paraphrases se concentre sur les derniers mots : une
    # paraphrase tient dans une phrase, et cela empêche un verset précédent encore
    # présent dans le buffer de masquer celui que le prédicateur cite maintenant.
    HYBRID_WINDOW_WORDS: int = 22

    # Barrière vocale (Silero VAD local) : filtre musique/silences avant transcription
    VOICE_GATE_ENABLED: bool = False

    # vMix
    VMIX_ENABLED: bool = False
    VMIX_HOST: str = "127.0.0.1"
    VMIX_PORT: int = 8088
    VMIX_INPUT_ID: str = "VerseProTitle"
    
    # NDI
    NDI_ENABLED: bool = False

    # OSC
    OSC_ENABLED: bool = False
    OSC_PORT: int = 8000
    
    @property
    def cors_origins(self) -> List[str]:
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",") if origin.strip()]


@lru_cache()
def get_settings() -> Settings:
    """Singleton pour les settings"""
    return Settings()


settings = get_settings()


# ── Résolution des chemins (dev ET application empaquetée) ──────────────────
# Deux natures de dossiers, distinctes une fois l'app figée par PyInstaller :
#   • RESOURCE_DIR : ressources LECTURE SEULE embarquées (bible.json, kjf.json).
#     Figé : à côté de l'exécutable (sys._MEIPASS) ; sinon la racine du backend.
#   • DATA_DIR : dossier INSCRIPTIBLE (modèles Vosk/e5, index, base). Fixé par
#     le lanceur (VERSEPRO_DATA_DIR → ~/Library/Application Support/VersePro) ;
#     en dev, le classique v2/backend/data. Ne JAMAIS écrire dans le bundle.
_BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _resource_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return _BACKEND_ROOT


def _data_dir() -> Path:
    env = os.environ.get("VERSEPRO_DATA_DIR")
    base = Path(env).expanduser() if env else (_BACKEND_ROOT / "data")
    base.mkdir(parents=True, exist_ok=True)
    return base


RESOURCE_DIR = _resource_dir()
DATA_DIR = _data_dir()


def db_path() -> Path:
    """Chemin de la base SQLite (inscriptible)."""
    env = os.environ.get("VERSEPRO_DB_PATH")
    return Path(env).expanduser() if env else (DATA_DIR / "versepro.db")
