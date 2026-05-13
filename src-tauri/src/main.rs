#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::process::{Child, Command};
use std::sync::Mutex;
use tauri::{
    menu::{Menu, MenuItem, PredefinedMenuItem},
    tray::TrayIconBuilder,
    Manager,
};

const BACKEND_URL: &str = "http://127.0.0.1:8770";

struct BackendProcess(Mutex<Option<Child>>);

fn iniciar_backend() -> Option<Child> {
    let exe  = std::env::current_exe().ok()?;
    let raiz = exe.parent()?.parent()?.parent()?.parent()?.to_path_buf();

    let python_venv = if cfg!(target_os = "windows") {
        raiz.join("venv").join("Scripts").join("python.exe")
    } else {
        raiz.join("venv").join("bin").join("python")
    };

    let mut c = if python_venv.exists() {
        Command::new(python_venv)
    } else {
        Command::new("python")
    };

    c.args(["-m", "uvicorn", "backend.main:app",
            "--host", "127.0.0.1", "--port", "8770",
            "--log-level", "warning"])
     .current_dir(raiz);
    c.spawn().ok()
}

fn post(ruta: &str, body: serde_json::Value) {
    let url = format!("{}{}", BACKEND_URL, ruta);
    std::thread::spawn(move || {
        let _ = reqwest::blocking::Client::new().post(&url).json(&body).send();
    });
}

#[tauri::command]
fn get_estado() -> String {
    match reqwest::blocking::get(format!("{}/estado", BACKEND_URL)) {
        Ok(r)  => r.text().unwrap_or_else(|_| "{}".into()),
        Err(_) => r#"{"error":"backend no disponible"}"#.into(),
    }
}

#[tauri::command]
fn send_chat(texto: String) -> String {
    match reqwest::blocking::Client::new()
        .post(format!("{}/chat", BACKEND_URL))
        .json(&serde_json::json!({ "texto": texto }))
        .send()
    {
        Ok(r)  => r.text().unwrap_or_else(|_| "{}".into()),
        Err(e) => format!(r#"{{"error":"{}"}}"#, e),
    }
}

#[tauri::command]
fn registrar_identidad() {
    post("/registrar_identidad", serde_json::json!({}));
}

#[tauri::command]
fn silenciar(activar: bool) {
    post("/silenciar", serde_json::json!({ "silenciado": activar }));
}

fn main() {
    tauri::Builder::default()
        .manage(BackendProcess(Mutex::new(None)))
        .setup(|app| {
            let proceso = iniciar_backend();
            if let Ok(mut g) = app.state::<BackendProcess>().0.lock() {
                *g = proceso;
            }

            let activar_it   = MenuItem::with_id(app, "activar",    "▶  Activar GEM",       true, None::<&str>)?;
            let silenciar_it = MenuItem::with_id(app, "silenciar",  "⏸  Silenciar GEM",     true, None::<&str>)?;
            let registrar    = MenuItem::with_id(app, "registrar",  "📷  Registrar mi cara", true, None::<&str>)?;
            let mostrar_it   = MenuItem::with_id(app, "mostrar",    "🪟  Mostrar ventana",   true, None::<&str>)?;
            let sep          = PredefinedMenuItem::separator(app)?;
            let salir        = MenuItem::with_id(app, "salir",      "✕  Salir",              true, None::<&str>)?;

            let menu = Menu::with_items(app, &[&activar_it, &silenciar_it, &registrar, &mostrar_it, &sep, &salir])?;

            TrayIconBuilder::new()
                .tooltip("GEM — activo")
                .menu(&menu)
                .on_menu_event(move |app, event| match event.id.as_ref() {
                    "salir" => {
                        if let Ok(mut g) = app.state::<BackendProcess>().0.lock() {
                            if let Some(ref mut child) = *g { let _ = child.kill(); }
                        }
                        app.exit(0);
                    }
                    "registrar"  => post("/registrar_identidad", serde_json::json!({})),
                    "silenciar"  => post("/silenciar", serde_json::json!({ "silenciado": true })),
                    "activar"    => post("/silenciar", serde_json::json!({ "silenciado": false })),
                    "mostrar"    => {
                        if let Some(w) = app.get_webview_window("main") {
                            let _ = w.show();
                            let _ = w.set_focus();
                        }
                    }
                    _ => {}
                })
                .build(app)?;

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            get_estado,
            send_chat,
            registrar_identidad,
            silenciar,
        ])
        .run(tauri::generate_context!())
        .expect("Error al iniciar GEM");
}