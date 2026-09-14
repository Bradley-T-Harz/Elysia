//! The only pre-account preview reads the file the user picks in this dialog.
//! There is deliberately no webview-supplied path argument or arbitrary read API.
use base64::{engine::general_purpose::STANDARD, Engine};
use serde::Serialize;
use std::{fs::File, io::Read};
use tauri_plugin_dialog::DialogExt;

const MAX_BYTES: u64 = 10 * 1024 * 1024;
#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SelectedPhoto { source_path: String, preview_url: String }

fn image_mime(bytes: &[u8]) -> Result<&'static str, String> {
    if bytes.starts_with(b"\x89PNG\r\n\x1a\n") { Ok("image/png") }
    else if bytes.starts_with(b"\xff\xd8\xff") { Ok("image/jpeg") }
    else if bytes.len() >= 12 && &bytes[..4] == b"RIFF" && &bytes[8..12] == b"WEBP" { Ok("image/webp") }
    else { Err("Choose a valid JPG, PNG, or WebP image.".into()) }
}

#[tauri::command]
pub async fn choose_identity_photo(app: tauri::AppHandle) -> Result<Option<SelectedPhoto>, String> {
    tauri::async_runtime::spawn_blocking(move || {
        let Some(selected) = app.dialog().file().set_title("Choose Identity Photo")
            .add_filter("Identity photo (JPG, PNG, WebP)", &["jpg", "jpeg", "png", "webp"])
            .blocking_pick_file() else { return Ok(None); };
        let path = selected.into_path().map_err(|_| "Choose a local image file.".to_string())?;
        let mut options = File::options();
        options.read(true);
        #[cfg(unix)] {
            use std::os::unix::fs::OpenOptionsExt;
            options.custom_flags(libc::O_NOFOLLOW | libc::O_NONBLOCK);
        }
        let file = options.open(&path).map_err(|_| "The selected image cannot be read.".to_string())?;
        if !file.metadata().map_err(|_| "The selected image is unavailable.".to_string())?.is_file() {
            return Err("Choose a regular local image file.".into());
        }
        let mut bytes = Vec::new();
        file.take(MAX_BYTES + 1).read_to_end(&mut bytes).map_err(|_| "The selected image cannot be read.".to_string())?;
        if bytes.len() as u64 > MAX_BYTES { return Err("Identity photo exceeds the 10 MB size limit.".into()); }
        let mime = image_mime(&bytes)?;
        Ok(Some(SelectedPhoto {
            source_path: path.to_string_lossy().into_owned(),
            preview_url: format!("data:{mime};base64,{}", STANDARD.encode(bytes)),
        }))
    }).await.map_err(|_| "The identity photo chooser could not finish.".to_string())?
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn accepts_only_raster_photo_signatures() {
        assert_eq!(image_mime(b"\x89PNG\r\n\x1a\n").unwrap(), "image/png");
        assert_eq!(image_mime(b"\xff\xd8\xff").unwrap(), "image/jpeg");
        assert_eq!(image_mime(b"RIFF1234WEBP").unwrap(), "image/webp");
        assert!(image_mime(b"<svg onload='script()'>").is_err());
        assert!(image_mime(b"not an image").is_err());
    }
}
