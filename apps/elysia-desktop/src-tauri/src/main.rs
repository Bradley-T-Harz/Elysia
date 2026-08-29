#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

// Elysia Desktop native bootstrap.
//
// The native shell owns only a fixed local API lifecycle handshake. It never
// accepts an arbitrary command, shell string, worker request, network target,
// or private-data mount from the webview.

use serde::Serialize;
use std::env;
use std::fs;
use std::io::{Read, Write};
use std::net::{IpAddr, Ipv4Addr, SocketAddr, TcpListener, TcpStream};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::thread;
use std::time::{Duration, Instant};
use tauri::Manager;

#[cfg(unix)]
use std::os::unix::fs::PermissionsExt;
#[cfg(unix)]
use std::os::unix::process::CommandExt;

const DEFAULT_API_PORT: u16 = 8000;
const API_PORT_ENV: &str = "ELYSIA_LOCAL_API_PORT";
const LOCAL_API_STARTUP_TIMEOUT: Duration = Duration::from_secs(60);

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct LocalApiSession {
    runtime_mode: String,
    lifecycle_state: String,
    base_url: String,
    authentication_required: bool,
    authentication_state: String,
    raw_path_exposed: bool,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct LocalApiResponse {
    status_code: u16,
    body: String,
    content_type: String,
}

struct LocalApiLifecycle {
    child: Mutex<Option<Child>>,
    runtime_mode: &'static str,
    api_address: SocketAddr,
    launcher_path: PathBuf,
    credential_path: PathBuf,
    distribution_form: &'static str,
}

fn home_dir() -> PathBuf {
    env::var_os("HOME")
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("/nonexistent"))
}

fn xdg_state_dir() -> PathBuf {
    env::var_os("XDG_STATE_HOME")
        .map(PathBuf::from)
        .unwrap_or_else(|| home_dir().join(".local").join("state"))
        .join("elysia")
}

fn xdg_data_dir() -> PathBuf {
    env::var_os("XDG_DATA_HOME")
        .map(PathBuf::from)
        .unwrap_or_else(|| home_dir().join(".local").join("share"))
        .join("elysia")
}

fn packaged_runtime_path() -> PathBuf {
    env::current_exe()
        .ok()
        .and_then(|path| path.parent().map(|parent| parent.join("elysia")))
        .unwrap_or_else(|| PathBuf::from("/usr/bin/elysia"))
}

fn classify_distribution_form(
    appimage: bool,
    executable: &Path,
    development_build: bool,
) -> &'static str {
    if development_build {
        "source"
    } else if appimage {
        "appimage"
    } else if executable == Path::new("/usr/bin/elysia-desktop") {
        "deb"
    } else {
        "user_local_desktop"
    }
}

fn desktop_distribution_form() -> &'static str {
    let executable = env::current_exe().unwrap_or_else(|_| PathBuf::from("/nonexistent"));
    classify_distribution_form(
        env::var_os("APPIMAGE").is_some(),
        &executable,
        cfg!(debug_assertions),
    )
}

fn xdg_runtime_dir() -> PathBuf {
    env::var_os("XDG_RUNTIME_DIR")
        .map(PathBuf::from)
        .map(|path| path.join("elysia"))
        .unwrap_or_else(|| xdg_state_dir().join("runtime"))
}

fn parse_api_port(value: Option<&str>) -> u16 {
    value
        .and_then(|candidate| candidate.trim().parse::<u16>().ok())
        .filter(|port| *port >= 1024)
        .unwrap_or(DEFAULT_API_PORT)
}

fn available_loopback_port() -> Option<u16> {
    TcpListener::bind(SocketAddr::new(IpAddr::V4(Ipv4Addr::LOCALHOST), 0))
        .ok()?
        .local_addr()
        .ok()
        .map(|address| address.port())
        .filter(|port| *port >= 1024)
}

fn select_api_port(configured: Option<&str>, available: Option<u16>) -> u16 {
    if configured.is_some() {
        parse_api_port(configured)
    } else {
        available.unwrap_or(DEFAULT_API_PORT)
    }
}

fn configured_api_address() -> SocketAddr {
    let configured = env::var(API_PORT_ENV).ok();
    let port = select_api_port(configured.as_deref(), available_loopback_port());
    SocketAddr::new(IpAddr::V4(Ipv4Addr::LOCALHOST), port)
}

impl LocalApiLifecycle {
    fn new() -> Self {
        let runtime_mode = if cfg!(debug_assertions) {
            "source"
        } else {
            "packaged"
        };
        Self {
            child: Mutex::new(None),
            runtime_mode,
            api_address: configured_api_address(),
            launcher_path: packaged_runtime_path(),
            credential_path: xdg_runtime_dir().join("auth").join("local-api.credential"),
            distribution_form: desktop_distribution_form(),
        }
    }

    fn start_if_packaged(&self) {
        if self.runtime_mode != "packaged" || !self.launcher_path.is_file() {
            return;
        }

        let Ok(mut slot) = self.child.lock() else {
            return;
        };
        if let Some(process) = slot.as_mut() {
            match process.try_wait() {
                Ok(None) => return,
                Ok(Some(_)) | Err(_) => {
                    slot.take();
                }
            }
        }
        if self.api_reachable() {
            return;
        }

        let port = self.api_address.port().to_string();
        let mut command = Command::new(&self.launcher_path);
        command
            .args(["serve", "--host", "127.0.0.1", "--port"])
            .arg(port)
            .args(["--mode", "packaged"])
            .env("ELYSIA_DESKTOP_PACKAGE", "present")
            .env("ELYSIA_DISTRIBUTION_FORM", self.distribution_form)
            .env("ELYSIA_WORKER_ENVS_ROOT", xdg_data_dir().join("components"))
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null());
        #[cfg(unix)]
        command.process_group(0);
        if let Ok(process) = command.spawn() {
            *slot = Some(process);
        }
    }

    fn stop_owned_process(&self) {
        if let Ok(mut slot) = self.child.lock() {
            if let Some(mut process) = slot.take() {
                #[cfg(unix)]
                unsafe {
                    libc::killpg(process.id() as i32, libc::SIGTERM);
                }
                let deadline = Instant::now() + Duration::from_secs(3);
                while Instant::now() < deadline {
                    match process.try_wait() {
                        Ok(Some(_)) => break,
                        Ok(None) => thread::sleep(Duration::from_millis(50)),
                        Err(_) => break,
                    }
                }
                if process.try_wait().ok().flatten().is_none() {
                    #[cfg(unix)]
                    unsafe {
                        libc::killpg(process.id() as i32, libc::SIGKILL);
                    }
                    #[cfg(not(unix))]
                    let _ = process.kill();
                }
                let _ = process.wait();
            }
        }
    }

    fn launcher_present(&self) -> bool {
        self.launcher_path.is_file()
    }

    fn api_reachable(&self) -> bool {
        TcpStream::connect_timeout(&self.api_address, Duration::from_millis(150)).is_ok()
    }

    fn owns_running_process(&self) -> bool {
        let Ok(mut guard) = self.child.lock() else {
            return false;
        };
        let Some(child) = guard.as_mut() else {
            return false;
        };
        matches!(child.try_wait(), Ok(None))
    }
}

fn read_private_credential(path: &Path) -> Option<String> {
    let metadata = fs::metadata(path).ok()?;
    if !metadata.is_file() {
        return None;
    }
    #[cfg(unix)]
    if metadata.permissions().mode() & 0o077 != 0 {
        return None;
    }
    let value = fs::read_to_string(path).ok()?.trim().to_string();
    if value.len() >= 32 {
        Some(value)
    } else {
        None
    }
}

fn validated_api_path(path: &str) -> Result<&str, String> {
    if path.is_empty()
        || path.len() > 4096
        || !path.starts_with('/')
        || path.starts_with("//")
        || path.contains("://")
        || path.contains('\r')
        || path.contains('\n')
    {
        return Err("The local API request path is invalid.".to_string());
    }
    Ok(path)
}

fn validated_method(method: &str) -> Result<String, String> {
    match method.to_ascii_uppercase().as_str() {
        "GET" | "POST" | "PUT" | "PATCH" | "DELETE" | "OPTIONS" => Ok(method.to_ascii_uppercase()),
        _ => Err("The local API request method is not allowed.".to_string()),
    }
}

fn wait_for_api(state: &LocalApiLifecycle) -> bool {
    // The packaged Core is a large CPython one-file sidecar. A cold AppImage
    // restart must unpack it before binding loopback, which can legitimately
    // take longer than five seconds under disk or memory pressure. Keep the
    // wait bounded, but long enough for emergency-stop recovery to work on the
    // same clean-machine profile that can start the application normally.
    let deadline = Instant::now() + LOCAL_API_STARTUP_TIMEOUT;
    while !state.api_reachable() && Instant::now() < deadline {
        thread::sleep(Duration::from_millis(100));
    }
    state.api_reachable()
}

fn write_native_emergency_marker_at(path: &Path) -> Result<(), String> {
    let parent = path
        .parent()
        .ok_or_else(|| "The emergency-state parent is unavailable.".to_string())?;
    fs::create_dir_all(parent)
        .map_err(|_| "The emergency-state directory could not be created.".to_string())?;
    #[cfg(unix)]
    fs::set_permissions(parent, fs::Permissions::from_mode(0o700))
        .map_err(|_| "The emergency-state directory could not be protected.".to_string())?;
    let temporary = parent.join(".emergency-state-native.tmp");
    let payload = concat!(
        "{\n",
        "  \"active\": true,\n",
        "  \"cleanup\": {\"canonical_user_data_deleted\": false, \"owned_process_hard_stopped\": true},\n",
        "  \"content_free\": true,\n",
        "  \"contract\": \"system-emergency-stop-v1\",\n",
        "  \"internet_effectively_enabled\": false,\n",
        "  \"reason\": \"Native owned-process hard-stop fallback\",\n",
        "  \"reason_code\": \"native_owned_process_hard_stop\",\n",
        "  \"reason_detail_stored\": false,\n",
        "  \"restart_recovery_performed\": false,\n",
        "  \"resume_required\": true,\n",
        "  \"runtime_autonomy_override\": 1,\n",
        "  \"sealed_memory_relocked\": true,\n",
        "  \"trigger_id\": \"native-hard-stop\",\n",
        "  \"triggered_at_utc\": null,\n",
        "  \"triggered_by_user_id\": null\n",
        "}\n"
    );
    fs::write(&temporary, payload)
        .map_err(|_| "The emergency-state marker could not be written.".to_string())?;
    #[cfg(unix)]
    fs::set_permissions(&temporary, fs::Permissions::from_mode(0o600))
        .map_err(|_| "The emergency-state marker could not be protected.".to_string())?;
    fs::rename(&temporary, &path)
        .map_err(|_| "The emergency-state marker could not be committed.".to_string())?;
    Ok(())
}

fn write_native_emergency_marker() -> Result<(), String> {
    write_native_emergency_marker_at(
        &xdg_state_dir()
            .join("cognition")
            .join("emergency-state.json"),
    )
}

fn request_emergency_stop(
    state: &LocalApiLifecycle,
    reason: &str,
) -> Result<LocalApiResponse, String> {
    state.start_if_packaged();
    if !wait_for_api(state) {
        return Err("The local API did not become ready for emergency stop.".to_string());
    }
    if state.runtime_mode == "packaged" && !state.owns_running_process() {
        return Err("The reachable listener is not owned by this Desktop session.".to_string());
    }
    let credential = if state.runtime_mode == "packaged" {
        Some(
            read_private_credential(&state.credential_path)
                .ok_or_else(|| "The packaged local API credential is unavailable.".to_string())?,
        )
    } else {
        None
    };
    let safe_reason: String = reason
        .chars()
        .filter(|value| !value.is_control() && *value != '"' && *value != '\\')
        .take(180)
        .collect();
    let payload = format!("{{\"reason\":\"{}\"}}", safe_reason);
    let mut headers = format!(
        "POST /emergency/stop HTTP/1.1\r\nHost: {}\r\nAccept: application/json\r\nContent-Type: application/json\r\nX-Elysia-Client: elysia-desktop-emergency/1\r\nConnection: close\r\nContent-Length: {}\r\n",
        state.api_address,
        payload.len()
    );
    if let Some(value) = credential {
        headers.push_str(&format!("Authorization: Bearer {value}\r\n"));
    }
    headers.push_str("\r\n");
    let mut stream = TcpStream::connect_timeout(&state.api_address, Duration::from_millis(750))
        .map_err(|_| "Emergency stop could not connect to the owned API.".to_string())?;
    stream
        .set_read_timeout(Some(Duration::from_secs(2)))
        .map_err(|_| "Emergency stop timeout setup failed.".to_string())?;
    stream
        .set_write_timeout(Some(Duration::from_secs(2)))
        .map_err(|_| "Emergency stop timeout setup failed.".to_string())?;
    stream
        .write_all(headers.as_bytes())
        .and_then(|_| stream.write_all(payload.as_bytes()))
        .map_err(|_| "Emergency stop could not be sent.".to_string())?;
    let mut raw = Vec::new();
    stream
        .take(1024 * 1024)
        .read_to_end(&mut raw)
        .map_err(|_| "Emergency stop did not answer within the bounded timeout.".to_string())?;
    let separator = raw
        .windows(4)
        .position(|window| window == b"\r\n\r\n")
        .ok_or_else(|| "Emergency stop returned an invalid response.".to_string())?;
    let header_text = String::from_utf8_lossy(&raw[..separator]);
    let status_code = header_text
        .lines()
        .next()
        .and_then(|line| line.split_whitespace().nth(1))
        .and_then(|value| value.parse::<u16>().ok())
        .ok_or_else(|| "Emergency stop returned an invalid status.".to_string())?;
    Ok(LocalApiResponse {
        status_code,
        body: String::from_utf8_lossy(&raw[separator + 4..]).to_string(),
        content_type: "application/json".to_string(),
    })
}

#[tauri::command]
fn emergency_stop_owned(
    state: tauri::State<'_, LocalApiLifecycle>,
    reason: String,
) -> Result<LocalApiResponse, String> {
    if let Ok(response) = request_emergency_stop(&state, &reason) {
        if (200..300).contains(&response.status_code) {
            // The governed API first persists the stop posture and asks every
            // cooperative subsystem to cancel. Terminating the exact child
            // process group afterwards closes blocking native/provider calls
            // that cannot observe an in-process cancellation event. A later
            // Desktop request may restart Core, but restart recovery reads the
            // persisted stop posture and remains fail-closed until Owner/Admin
            // reset.
            state.stop_owned_process();
            return Ok(response);
        }
    }
    // Fail closed beneath the webview: persist restart posture, then terminate
    // only the exact child process group spawned and held by this Desktop.
    write_native_emergency_marker()?;
    state.stop_owned_process();
    Ok(LocalApiResponse {
        status_code: 200,
        body: "{\"status\":\"ok\",\"result_type\":\"emergency_stop\",\"data\":{\"active\":true,\"resume_required\":true,\"native_hard_stop\":true}}".to_string(),
        content_type: "application/json".to_string(),
    })
}

#[tauri::command]
fn local_api_request(
    state: tauri::State<'_, LocalApiLifecycle>,
    method: String,
    path: String,
    body: Option<String>,
) -> Result<LocalApiResponse, String> {
    let method = validated_method(&method)?;
    let path = validated_api_path(&path)?;
    if body.as_ref().map_or(0, String::len) > 2 * 1024 * 1024 {
        return Err("The local API request body exceeds the Desktop bridge limit.".to_string());
    }

    state.start_if_packaged();
    if !wait_for_api(&state) {
        return Err("The packaged local API did not become ready.".to_string());
    }
    if state.runtime_mode == "packaged" && !state.owns_running_process() {
        return Err(
            "The loopback API listener is not owned by this Elysia Desktop session; no credential was sent."
                .to_string(),
        );
    }

    let credential = if state.runtime_mode == "packaged" {
        Some(
            read_private_credential(&state.credential_path)
                .ok_or_else(|| "The packaged local API credential is unavailable.".to_string())?,
        )
    } else {
        None
    };

    let payload = body.unwrap_or_default();
    let mut headers = format!(
        "{method} {path} HTTP/1.1\r\nHost: {}\r\nAccept: application/json\r\nX-Elysia-Client: elysia-desktop/1.0.0\r\nConnection: close\r\n",
        state.api_address
    );
    if let Some(value) = credential {
        headers.push_str(&format!("Authorization: Bearer {value}\r\n"));
    }
    if !payload.is_empty() {
        headers.push_str("Content-Type: application/json\r\n");
    }
    headers.push_str(&format!("Content-Length: {}\r\n\r\n", payload.len()));

    let mut stream = TcpStream::connect_timeout(&state.api_address, Duration::from_secs(5))
        .map_err(|_| "The packaged local API request could not connect.".to_string())?;
    stream
        .set_read_timeout(Some(Duration::from_secs(120)))
        .map_err(|_| "The packaged local API timeout could not be configured.".to_string())?;
    stream
        .set_write_timeout(Some(Duration::from_secs(10)))
        .map_err(|_| "The packaged local API timeout could not be configured.".to_string())?;
    stream
        .write_all(headers.as_bytes())
        .and_then(|_| stream.write_all(payload.as_bytes()))
        .map_err(|_| "The packaged local API request could not be sent.".to_string())?;

    let mut raw = Vec::new();
    stream
        .take(8 * 1024 * 1024 + 1)
        .read_to_end(&mut raw)
        .map_err(|_| "The packaged local API response could not be read.".to_string())?;
    if raw.len() > 8 * 1024 * 1024 {
        return Err(
            "The packaged local API response exceeds the Desktop bridge limit.".to_string(),
        );
    }
    let separator = raw
        .windows(4)
        .position(|window| window == b"\r\n\r\n")
        .ok_or_else(|| "The packaged local API returned an invalid HTTP response.".to_string())?;
    let header_text = String::from_utf8_lossy(&raw[..separator]);
    let mut header_lines = header_text.lines();
    let status_code = header_lines
        .next()
        .and_then(|line| line.split_whitespace().nth(1))
        .and_then(|value| value.parse::<u16>().ok())
        .ok_or_else(|| "The packaged local API returned an invalid status line.".to_string())?;
    let content_type = header_lines
        .find_map(|line| {
            let (name, value) = line.split_once(':')?;
            name.eq_ignore_ascii_case("content-type")
                .then(|| value.trim().to_string())
        })
        .unwrap_or_else(|| "application/octet-stream".to_string());
    let body = String::from_utf8(raw[separator + 4..].to_vec())
        .map_err(|_| "The packaged local API returned a non-text bridge response.".to_string())?;
    Ok(LocalApiResponse {
        status_code,
        body,
        content_type,
    })
}

#[tauri::command]
fn local_api_session(state: tauri::State<'_, LocalApiLifecycle>) -> LocalApiSession {
    state.start_if_packaged();
    let listener_reachable = wait_for_api(&state);
    let owned = state.runtime_mode != "packaged" || state.owns_running_process();
    let reachable = listener_reachable && owned;
    let port_conflict = state.runtime_mode == "packaged" && listener_reachable && !owned;
    let credential = if state.runtime_mode == "packaged" && reachable {
        read_private_credential(&state.credential_path)
    } else {
        None
    };
    let lifecycle_state = if port_conflict {
        "port_conflict"
    } else if reachable && (state.runtime_mode != "packaged" || credential.is_some()) {
        "reachable"
    } else if reachable {
        "unverified_listener"
    } else if state.launcher_present() {
        "launcher_failed"
    } else {
        "launcher_missing"
    };
    LocalApiSession {
        runtime_mode: state.runtime_mode.to_string(),
        lifecycle_state: lifecycle_state.to_string(),
        base_url: format!("http://{}", state.api_address),
        authentication_required: state.runtime_mode == "packaged",
        authentication_state: if state.runtime_mode != "packaged" {
            "development_disabled".to_string()
        } else if credential.is_some() {
            "ready".to_string()
        } else {
            "missing".to_string()
        },
        raw_path_exposed: false,
    }
}

#[cfg(test)]
mod tests {
    use super::{
        classify_distribution_form, parse_api_port, select_api_port,
        write_native_emergency_marker_at, LocalApiLifecycle, DEFAULT_API_PORT,
        LOCAL_API_STARTUP_TIMEOUT,
    };

    #[test]
    fn distribution_form_is_bound_to_the_running_desktop_package() {
        assert_eq!(
            classify_distribution_form(true, Path::new("/tmp/Elysia.AppImage"), false),
            "appimage"
        );
        assert_eq!(
            classify_distribution_form(false, Path::new("/usr/bin/elysia-desktop"), false),
            "deb"
        );
        assert_eq!(
            classify_distribution_form(false, Path::new("qa/.local/bin/elysia-desktop"), false),
            "user_local_desktop"
        );
        assert_eq!(
            classify_distribution_form(false, Path::new("/tmp/target/debug/elysia-desktop"), true),
            "source"
        );
    }
    use std::fs;
    use std::net::{IpAddr, Ipv4Addr, SocketAddr};
    use std::path::{Path, PathBuf};
    use std::process::{Command, Stdio};
    use std::sync::Mutex;
    use std::time::{Duration, SystemTime, UNIX_EPOCH};

    #[cfg(unix)]
    use std::os::unix::process::CommandExt;

    #[test]
    fn local_api_port_is_bounded_and_deterministic() {
        assert_eq!(parse_api_port(None), DEFAULT_API_PORT);
        assert_eq!(parse_api_port(Some("")), DEFAULT_API_PORT);
        assert_eq!(parse_api_port(Some("80")), DEFAULT_API_PORT);
        assert_eq!(parse_api_port(Some("not-a-port")), DEFAULT_API_PORT);
        assert_eq!(parse_api_port(Some("38124")), 38124);
    }

    #[test]
    fn packaged_desktop_prefers_a_selected_loopback_port_unless_explicitly_configured() {
        assert_eq!(select_api_port(None, Some(49152)), 49152);
        assert_eq!(select_api_port(None, None), DEFAULT_API_PORT);
        assert_eq!(select_api_port(Some("38124"), Some(49152)), 38124);
    }

    #[test]
    fn packaged_core_restart_window_is_bounded_and_one_file_safe() {
        assert_eq!(LOCAL_API_STARTUP_TIMEOUT, Duration::from_secs(60));
    }

    #[test]
    fn native_emergency_marker_is_content_free_and_fail_closed() {
        let suffix = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("system time")
            .as_nanos();
        let root = std::env::temp_dir().join(format!(
            "elysia-native-emergency-marker-{}-{suffix}",
            std::process::id()
        ));
        let marker = root.join("cognition").join("emergency-state.json");
        write_native_emergency_marker_at(&marker).expect("write marker");
        let payload = fs::read_to_string(&marker).expect("read marker");
        assert!(payload.contains("\"active\": true"));
        assert!(payload.contains("\"owned_process_hard_stopped\": true"));
        assert!(payload.contains("\"canonical_user_data_deleted\": false"));
        assert!(payload.contains("\"resume_required\": true"));
        assert!(!payload.contains("prompt"));
        fs::remove_file(&marker).expect("remove exact marker");
        fs::remove_dir(marker.parent().expect("marker parent")).expect("remove cognition dir");
        fs::remove_dir(&root).expect("remove exact test root");
    }

    #[cfg(unix)]
    #[test]
    fn hard_stop_terminates_only_the_owned_child_process_group() {
        let mut command = Command::new("sleep");
        command
            .arg("30")
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null());
        command.process_group(0);
        let child = command.spawn().expect("spawn bounded test child");
        let child_id = child.id();
        let lifecycle = LocalApiLifecycle {
            child: Mutex::new(Some(child)),
            runtime_mode: "packaged",
            api_address: SocketAddr::new(IpAddr::V4(Ipv4Addr::LOCALHOST), 9),
            launcher_path: PathBuf::from("/nonexistent/elysia"),
            credential_path: PathBuf::from("/nonexistent/credential"),
            distribution_form: "user_local_desktop",
        };
        lifecycle.stop_owned_process();
        assert!(lifecycle.child.lock().expect("child slot").is_none());
        let alive = unsafe { libc::kill(child_id as i32, 0) } == 0;
        assert!(!alive, "owned child process survived exact hard stop");
    }
}

fn main() {
    let lifecycle = LocalApiLifecycle::new();
    lifecycle.start_if_packaged();
    let app = tauri::Builder::default()
        .manage(lifecycle)
        .on_window_event(|window, event| {
            if matches!(event, tauri::WindowEvent::CloseRequested { .. }) {
                window.state::<LocalApiLifecycle>().stop_owned_process();
            }
        })
        .invoke_handler(tauri::generate_handler![
            local_api_session,
            local_api_request,
            emergency_stop_owned
        ])
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .build(tauri::generate_context!())
        .expect("error while building Elysia desktop chamber");

    app.run(|app_handle, event| {
        if matches!(event, tauri::RunEvent::Exit) {
            app_handle.state::<LocalApiLifecycle>().stop_owned_process();
        }
    });
}
