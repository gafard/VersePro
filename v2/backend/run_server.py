"""Point d'entrée du backend EMPAQUETÉ (sidecar Tauri).

Lance uvicorn en programmatique. Le lanceur Tauri fixe l'environnement :
  VERSEPRO_PORT      port d'écoute (17871 dans l'app, 8001 par défaut en dev)
  VERSEPRO_HOST      hôte (défaut 127.0.0.1)
  VERSEPRO_DATA_DIR  dossier inscriptible (modèles, index, base) — voir config

Une fois figé par PyInstaller, ce fichier devient l'exécutable autonome
`versepro-backend` : aucune installation de Python requise sur la machine cible.
"""
import os
import sys


def main() -> None:
    host = os.environ.get("VERSEPRO_HOST", "127.0.0.1")
    port = int(os.environ.get("VERSEPRO_PORT", "8001"))

    # Import tardif : laisse le temps à PyInstaller de préparer sys.path figé.
    import uvicorn
    from app.main import app

    # On passe l'objet app directement (pas une chaîne d'import) : indispensable
    # en binaire figé, où l'import dynamique par chaîne échouerait.
    uvicorn.run(app, host=host, port=port, log_level="info", access_log=False)


if __name__ == "__main__":
    # Sous PyInstaller, garde-fou multiprocessing (évite les fork-bombs au boot).
    try:
        import multiprocessing
        multiprocessing.freeze_support()
    except Exception:
        pass
    main()
