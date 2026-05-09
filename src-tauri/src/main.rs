#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::process::{Child, Command};
use std::sync::Mutex;
use tauri::{
    menu::{Menu, MenuItem, PredefinedMenuItem},
    tray::TrayIconBuilder,
    Manager,
};

const BACKEND_URL: &str = "http://127.0.0.1:8765";

struct BackendProcess(Mutex<Option<Child>>);

fn iniciar_backend() -> Option<Child> {
    // Sube dos niveles: src-tauri/target/debug/gem.exe -> Gem/
    let exe = std::env::current_exe().ok()?;
    let raiz = exe
        .parent()? // debug
        .parent()? // target
        .parent()? // src-tauri
        .parent()? // Gem
        .to_path_buf();

    // Prefiere el python del venv si existe
    let python_venv = if cfg!(target_os = "windows") {
        raiz.join(".venv").join("Scripts").join("python.exe")
    } else {
        raiz.join(".venv").join("bin").join("python")
    };

    let comando = if python_venv.exists() {
        let mut c = Command::new(python_venv);
        c.args([
            "-m",
            "uvicorn",
            "backend.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8765",
            "--log-level",
            "warning",
        ]);
        c
    } else {
        let mut c = Command::new("uvicorn");
        c.args([
            "backend.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8765",
            "--log-level",
            "warning",
        ]);
        c
    };

    let mut comando = comando;
    comando.current_dir(raiz);
    comando.spawn().ok()
}

fn llamar_backend_post(ruta: &str) {
    let url = format!("{}{}", BACKEND_URL, ruta);
    std::thread::spawn(move || {
        let _ = reqwest::blocking::Client::new().post(&url).send();
    });
}

fn llamar_backend_get(ruta: &str) {
    let url = format!("{}{}", BACKEND_URL, ruta);
    std::thread::spawn(move || {
        let _ = reqwest::blocking::get(&url);
    });
}

#[tauri::command]
fn get_estado() -> String {
    match reqwest::blocking::get(format!("{}/estado", BACKEND_URL)) {
        Ok(r) => r.text().unwrap_or_else(|_| "{}".into()),
        Err(_) => "{\"error\": \"backend no disponible\"}".into(),
    }
}

#[tauri::command]
fn registrar_identidad() {
    llamar_backend_post("/registrar_identidad");
}

#[tauri::command]
fn silenciar(activar: bool) {
    let url = format!("{}/silenciar", BACKEND_URL);
    let body = serde_json::json!({ "silenciado": activar });
    std::thread::spawn(move || {
        let _ = reqwest::blocking::Client::new()
            .post(&url)
            .json(&body)
            .send();
    });
}

fn main() {
    tauri::Builder::default()
        .manage(BackendProcess(Mutex::new(None)))
        .setup(|app| {
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.hide();
            }

            let proceso = iniciar_backend();
            if let Ok(mut guard) = app.state::<BackendProcess>().0.lock() {
                *guard = proceso;
            }

            let silenciar_it = MenuItem::with_id(app, "silenciar", "⏸  Silenciar GEM", true, None::<&str>)?;
            let activar_it   = MenuItem::with_id(app, "activar",   "▶  Activar GEM",    true, None::<&str>)?;
            let registrar    = MenuItem::with_id(app, "registrar", "📷  Registrar mi cara", true, None::<&str>)?;
            let estado_it    = MenuItem::with_id(app, "estado",    "📊  Ver estado",        true, None::<&str>)?;
            let sep          = PredefinedMenuItem::separator(app)?;
            let salir        = MenuItem::with_id(app, "salir",     "✕   Salir",            true, None::<&str>)?;

            let menu = Menu::with_items(
                app,
                &[&activar_it, &silenciar_it, &registrar, &estado_it, &sep, &salir],
            )?;

            TrayIconBuilder::new()
                .tooltip("GEM — activo")
                .menu(&menu)
                .on_menu_event(move |app, event| match event.id.as_ref() {
                    "salir" => {
                        if let Ok(mut guard) = app.state::<BackendProcess>().0.lock() {
                            if let Some(ref mut child) = *guard {
                                let _ = child.kill();
                            }
                        }
                        app.exit(0);
                    }
                    "registrar" => llamar_backend_post("/registrar_identidad"),
                    "estado"    => llamar_backend_get("/estado"),
                    "silenciar" => {
                        let url = format!("{}/silenciar", BACKEND_URL);
                        std::thread::spawn(move || {
                            let _ = reqwest::blocking::Client::new()
                                .post(&url)
                                .json(&serde_json::json!({ "silenciado": true }))
                                .send();
                        });
                    }
                    "activar" => {
                        let url = format!("{}/silenciar", BACKEND_URL);
                        std::thread::spawn(move || {
                            let _ = reqwest::blocking::Client::new()
                                .post(&url)
                                .json(&serde_json::json!({ "silenciado": false }))
                                .send();
                        });
                    }
                    _ => {}
                })
                .build(app)?;

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            get_estado,
            registrar_identidad,
            silenciar
        ])
        .run(tauri::generate_context!())
        .expect("Error al iniciar GEM");
}
