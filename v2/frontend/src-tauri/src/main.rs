// Prevents additional console window on Windows in release, DO NOT REMOVE!!
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use rand::rngs::OsRng;
use rand::RngCore;
use serde::Serialize;
use std::fs::OpenOptions;
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Mutex;
use std::time::{Duration, Instant};
use tauri::path::BaseDirectory;
use tauri::{Emitter, Manager};
use tauri_plugin_updater::UpdaterExt;

#[derive(Clone)]
struct BackendConfig {
    executable: PathBuf,
    data_dir: PathBuf,
    db_path: PathBuf,
    session_token: String,
}

struct BackendProcess {
    child: Mutex<Option<Child>>,
    shutting_down: AtomicBool,
    config: BackendConfig,
}

fn spawn_backend(config: &BackendConfig) -> std::io::Result<Child> {
    let log_path = config.data_dir.join("backend-desktop.log");
    let stdout = OpenOptions::new().create(true).append(true).open(&log_path)?;
    let stderr = stdout.try_clone()?;
    let mut cmd = Command::new(&config.executable);
    cmd.env("VERSEPRO_DATA_DIR", config.data_dir.to_string_lossy().to_string())
        .env("VERSEPRO_DB_PATH", config.db_path.to_string_lossy().to_string())
        .env("VERSEPRO_HOST", "127.0.0.1")
        .env("VERSEPRO_PORT", "17871")
        .env("VERSEPRO_SESSION_TOKEN", &config.session_token)
        .stdout(Stdio::from(stdout))
        .stderr(Stdio::from(stderr));
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(0x0800_0000);
    }
    cmd.spawn()
}

fn arreter_backend(app: &tauri::AppHandle) {
    if let Some(state) = app.try_state::<BackendProcess>() {
        state.shutting_down.store(true, Ordering::SeqCst);
        if let Some(mut child) = state.child.lock().unwrap().take() {
            let _ = child.kill();
            let _ = child.wait();
        }
    }
}

/// Vrai quand le micro ou la sortie à l'antenne est actif. Renseigné par
/// l'interface, lu avant une fermeture ou une installation.
struct EtatDirect(AtomicBool);

struct SessionToken(String);

fn nouveau_jeton_session() -> String {
    let mut bytes = [0_u8; 32];
    OsRng.fill_bytes(&mut bytes);
    bytes.iter().map(|byte| format!("{byte:02x}")).collect()
}

#[tauri::command]
fn obtenir_jeton_session(token: tauri::State<SessionToken>) -> String {
    token.0.clone()
}

/// L'interface signale l'entrée et la sortie de direct.
#[tauri::command]
fn definir_direct(actif: bool, etat: tauri::State<EtatDirect>) {
    etat.0.store(actif, Ordering::SeqCst);
}

/// Fermeture confirmée par l'opérateur : on quitte pour de bon.
#[tauri::command]
fn fermer_vraiment(app: tauri::AppHandle) {
    app.exit(0);
}

#[derive(Clone, Serialize)]
struct InfosMiseAJour {
    current: String,
    latest: Option<String>,
    update_available: bool,
    notes: Option<String>,
    date: Option<String>,
    checked: bool,
}

#[derive(Clone, Serialize)]
struct ProgressionMiseAJour {
    phase: String,
    downloaded: u64,
    total: Option<u64>,
}

/// Interroge le manifeste Tauri signé. Une absence de réseau est renvoyée à
/// l'interface, qui reste silencieuse lors du contrôle automatique.
#[tauri::command]
async fn verifier_mise_a_jour(app: tauri::AppHandle) -> Result<InfosMiseAJour, String> {
    let current = app.package_info().version.to_string();
    let update = app
        .updater()
        .map_err(|error| error.to_string())?
        .check()
        .await
        .map_err(|error| error.to_string())?;

    Ok(match update {
        Some(update) => InfosMiseAJour {
            current,
            latest: Some(update.version),
            update_available: true,
            notes: update.body,
            date: update.date.map(|date| date.to_string()),
            checked: true,
        },
        None => InfosMiseAJour {
            current,
            latest: None,
            update_available: false,
            notes: None,
            date: None,
            checked: true,
        },
    })
}

/// Télécharge, vérifie cryptographiquement, installe puis relance VersePro.
/// Le verrou est aussi contrôlé côté Rust : un bouton frontend contourné ne
/// peut donc pas remplacer l'application pendant un direct.
#[tauri::command]
async fn installer_mise_a_jour(
    app: tauri::AppHandle,
    etat: tauri::State<'_, EtatDirect>,
) -> Result<(), String> {
    if etat.0.load(Ordering::SeqCst) {
        return Err(
            "Mise à jour bloquée : arrêtez le micro et videz la sortie à l'antenne.".into(),
        );
    }

    let handle_for_exit = app.clone();
    let update = app
        .updater_builder()
        .on_before_exit(move || arreter_backend(&handle_for_exit))
        .build()
        .map_err(|error| error.to_string())?
        .check()
        .await
        .map_err(|error| error.to_string())?
        .ok_or_else(|| "VersePro est déjà à jour.".to_string())?;

    let progress_app = app.clone();
    let finished_app = app.clone();
    let mut downloaded = 0_u64;
    update
        .download_and_install(
            move |chunk_length, content_length| {
                downloaded = downloaded.saturating_add(chunk_length as u64);
                let _ = progress_app.emit(
                    "versepro://mise-a-jour-progression",
                    ProgressionMiseAJour {
                        phase: "download".into(),
                        downloaded,
                        total: content_length,
                    },
                );
            },
            move || {
                let _ = finished_app.emit(
                    "versepro://mise-a-jour-progression",
                    ProgressionMiseAJour {
                        phase: "install".into(),
                        downloaded: 0,
                        total: None,
                    },
                );
            },
        )
        .await
        .map_err(|error| error.to_string())?;

    arreter_backend(&app);
    app.restart();
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .manage(EtatDirect(AtomicBool::new(false)))
        .invoke_handler(tauri::generate_handler![
            definir_direct,
            fermer_vraiment,
            obtenir_jeton_session,
            verifier_mise_a_jour,
            installer_mise_a_jour
        ])
        // Fermer la fenêtre pendant un culte coupait la projection sans un mot.
        // On intercepte donc la demande : hors direct on laisse fermer, en
        // direct on retient la fenêtre et l'interface demande confirmation.
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                let en_direct = window
                    .try_state::<EtatDirect>()
                    .map(|etat| etat.0.load(Ordering::SeqCst))
                    .unwrap_or(false);
                if en_direct {
                    api.prevent_close();
                    // Si l'interface ne répond pas, l'opérateur garde le
                    // recours du menu Quitter : on ne bloque rien d'autre.
                    let _ = window.emit("versepro://fermeture-demandee", ());
                }
            }
        })
        .setup(|app| {
            let data_dir = app
                .path()
                .app_data_dir()
                .unwrap_or_else(|_| std::env::current_dir().unwrap().join("versepro-data"));
            std::fs::create_dir_all(&data_dir).ok();
            let db_path = data_dir.join("versepro.db");

            #[cfg(windows)]
            let backend_name = "backend/versepro-backend.exe";
            #[cfg(not(windows))]
            let backend_name = "backend/versepro-backend";
            let backend_exe = app
                .path()
                .resolve(backend_name, BaseDirectory::Resource)
                .expect("backend embarqué introuvable dans les ressources");

            #[cfg(unix)]
            {
                use std::os::unix::fs::PermissionsExt;
                if let Ok(meta) = std::fs::metadata(&backend_exe) {
                    let mut perms = meta.permissions();
                    perms.set_mode(perms.mode() | 0o755);
                    let _ = std::fs::set_permissions(&backend_exe, perms);
                }
            }

            let session_token = nouveau_jeton_session();
            app.manage(SessionToken(session_token.clone()));
            let config = BackendConfig {
                executable: backend_exe,
                data_dir,
                db_path,
                session_token,
            };
            let child = spawn_backend(&config).ok();
            app.manage(BackendProcess {
                child: Mutex::new(child),
                shutting_down: AtomicBool::new(false),
                config,
            });

            // Surveille le sidecar pendant toute la session. Un crash isolé est
            // réparé automatiquement; un crash en boucle reçoit un backoff.
            let handle = app.handle().clone();
            std::thread::spawn(move || {
                let mut failures = 0_u32;
                let mut started_at = Instant::now();
                loop {
                    std::thread::sleep(Duration::from_secs(2));
                    let state = handle.state::<BackendProcess>();
                    if state.shutting_down.load(Ordering::SeqCst) {
                        break;
                    }
                    let needs_start = {
                        let mut guard = state.child.lock().unwrap();
                        match guard.as_mut() {
                            Some(child) => match child.try_wait() {
                                Ok(Some(_)) => {
                                    guard.take();
                                    true
                                }
                                Ok(None) => false,
                                Err(_) => {
                                    guard.take();
                                    true
                                }
                            },
                            None => true,
                        }
                    };
                    if !needs_start {
                        continue;
                    }
                    if started_at.elapsed() < Duration::from_secs(10) {
                        failures = failures.saturating_add(1);
                    } else {
                        failures = 0;
                    }
                    let delay = 2_u64.saturating_pow(failures.min(4)).min(30);
                    std::thread::sleep(Duration::from_secs(delay));
                    if state.shutting_down.load(Ordering::SeqCst) {
                        break;
                    }
                    match spawn_backend(&state.config) {
                        Ok(child) => {
                            state.child.lock().unwrap().replace(child);
                            started_at = Instant::now();
                        }
                        Err(error) => {
                            failures = failures.saturating_add(1);
                            let _ = handle.emit(
                                "versepro://backend-indisponible",
                                error.to_string(),
                            );
                        }
                    }
                }
            });
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("erreur au démarrage de l'application Tauri")
        .run(|app_handle, event| {
            if let tauri::RunEvent::Exit = event {
                arreter_backend(app_handle);
            }
        });
}

#[cfg(test)]
mod tests {
    use super::nouveau_jeton_session;

    #[test]
    fn session_tokens_are_random_hex_256_bit_values() {
        let first = nouveau_jeton_session();
        let second = nouveau_jeton_session();
        assert_eq!(first.len(), 64);
        assert!(first.chars().all(|character| character.is_ascii_hexdigit()));
        assert_ne!(first, second);
    }
}
