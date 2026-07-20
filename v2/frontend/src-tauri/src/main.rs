// Prevents additional console window on Windows in release, DO NOT REMOVE!!
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::process::{Child, Command};
use std::sync::Mutex;
use tauri::Manager;

// Conserve le processus backend pour l'arrêter à la fermeture de l'application.
struct BackendProcess(Mutex<Option<Child>>);

fn main() {
    tauri::Builder::default()
        .manage(BackendProcess(Mutex::new(None)))
        .setup(|app| {
            // Dossier de données INSCRIPTIBLE de l'utilisateur (modèles, index, base).
            let data_dir = app
                .path_resolver()
                .app_data_dir()
                .unwrap_or_else(|| std::env::current_dir().unwrap().join("versepro-data"));
            std::fs::create_dir_all(&data_dir).ok();
            let db_path = data_dir.join("versepro.db");

            // Backend empaqueté (PyInstaller onedir) : l'exécutable et son dossier
            // _internal/ sont embarqués comme ressources. onedir = démarrage rapide
            // (pas de ré-extraction ni de re-scan Gatekeeper à chaque lancement).
            // Le nom diffère par OS : PyInstaller produit un .exe sous Windows.
            #[cfg(windows)]
            let backend_name = "backend/versepro-backend.exe";
            #[cfg(not(windows))]
            let backend_name = "backend/versepro-backend";
            let backend_exe = app
                .path_resolver()
                .resolve_resource(backend_name)
                .expect("backend embarqué introuvable dans les ressources");

            // Garantit le bit exécutable (les ressources peuvent le perdre à la copie).
            #[cfg(unix)]
            {
                use std::os::unix::fs::PermissionsExt;
                if let Ok(meta) = std::fs::metadata(&backend_exe) {
                    let mut perms = meta.permissions();
                    perms.set_mode(perms.mode() | 0o755);
                    let _ = std::fs::set_permissions(&backend_exe, perms);
                }
            }

            let mut cmd = Command::new(&backend_exe);
            cmd.env("VERSEPRO_DATA_DIR", data_dir.to_string_lossy().to_string())
                .env("VERSEPRO_DB_PATH", db_path.to_string_lossy().to_string())
                .env("VERSEPRO_HOST", "127.0.0.1")
                .env("VERSEPRO_PORT", "17871");
            // Sous Windows, un exécutable console lancé par une app graphique
            // ouvre une fenêtre de terminal à chaque démarrage : CREATE_NO_WINDOW.
            #[cfg(windows)]
            {
                use std::os::windows::process::CommandExt;
                cmd.creation_flags(0x0800_0000);
            }
            let child = cmd
                .spawn()
                .expect("échec du lancement du backend VersePro");

            app.state::<BackendProcess>()
                .0
                .lock()
                .unwrap()
                .replace(child);

            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("erreur au démarrage de l'application Tauri")
        .run(|app_handle, event| {
            // Arrêt propre du backend quand l'app se ferme.
            if let tauri::RunEvent::Exit = event {
                if let Some(state) = app_handle.try_state::<BackendProcess>() {
                    if let Some(mut child) = state.0.lock().unwrap().take() {
                        let _ = child.kill();
                    }
                }
            }
        });
}
