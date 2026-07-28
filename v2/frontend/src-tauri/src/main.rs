// Prevents additional console window on Windows in release, DO NOT REMOVE!!
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::fs::OpenOptions;
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Mutex;
use std::time::{Duration, Instant};
use tauri::path::BaseDirectory;
use tauri::{Emitter, Manager};

#[derive(Clone)]
struct BackendConfig {
    executable: PathBuf,
    data_dir: PathBuf,
    db_path: PathBuf,
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
        .stdout(Stdio::from(stdout))
        .stderr(Stdio::from(stderr));
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(0x0800_0000);
    }
    cmd.spawn()
}

/// Vrai quand la régie est en direct (micro ouvert). Renseigné par l'interface,
/// lu au moment où l'on tente de fermer la fenêtre.
struct EtatDirect(AtomicBool);

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

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .manage(EtatDirect(AtomicBool::new(false)))
        .invoke_handler(tauri::generate_handler![definir_direct, fermer_vraiment])
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

            let config = BackendConfig { executable: backend_exe, data_dir, db_path };
            let child = spawn_backend(&config).expect("échec du lancement du backend VersePro");
            app.manage(BackendProcess {
                child: Mutex::new(Some(child)),
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
                    let exited = {
                        let mut guard = state.child.lock().unwrap();
                        match guard.as_mut().and_then(|child| child.try_wait().ok()).flatten() {
                            Some(_) => {
                                guard.take();
                                true
                            }
                            None => false,
                        }
                    };
                    if !exited {
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
                    if let Ok(child) = spawn_backend(&state.config) {
                        state.child.lock().unwrap().replace(child);
                        started_at = Instant::now();
                    }
                }
            });
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("erreur au démarrage de l'application Tauri")
        .run(|app_handle, event| {
            if let tauri::RunEvent::Exit = event {
                if let Some(state) = app_handle.try_state::<BackendProcess>() {
                    state.shutting_down.store(true, Ordering::SeqCst);
                    if let Some(mut child) = state.child.lock().unwrap().take() {
                        let _ = child.kill();
                        let _ = child.wait();
                    }
                }
            }
        });
}
