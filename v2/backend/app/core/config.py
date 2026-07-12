"""
Configuration de VersePro v2
"""

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
    ALLOWED_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000,http://localhost:3001,http://127.0.0.1:3001"
    
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
    
    # ProPresenter
    PROPRESENTER_HOST: str = "127.0.0.1"
    PROPRESENTER_PORT: int = 12345  # Port API TCP ProPresenter
    PROPRESENTER_AUTO_CONNECT: bool = True
    PROPRESENTER_AUTO_SEND: bool = False  # Envoi automatique ou validation manuelle
    
    # Parser
    BIBLE_VERSION: str = "LSG"  # Louis Segond 1910
    VALIDATE_REFERENCES: bool = True  # Valider les références (chapitres/versets existants)
    
    # Audio
    AUDIO_SAMPLE_RATE: int = 16000
    AUDIO_CHUNK_SIZE: int = 4096
    
    # WebSocket
    WS_HEARTBEAT_INTERVAL: int = 30  # secondes
    
    # Vosk
    VOSK_MODEL_TYPE: str = "small"  # 'small' ou 'large' pour le modèle français plus précis de 1.4 Go

    # Barrière vocale (Silero VAD local) : filtre musique/silences avant transcription
    VOICE_GATE_ENABLED: bool = False

    # vMix
    VMIX_ENABLED: bool = False
    VMIX_HOST: str = "127.0.0.1"
    VMIX_PORT: int = 8088
    VMIX_INPUT_ID: str = "VerseProTitle"
    
    @property
    def cors_origins(self) -> List[str]:
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",") if origin.strip()]


@lru_cache()
def get_settings() -> Settings:
    """Singleton pour les settings"""
    return Settings()


settings = get_settings()
