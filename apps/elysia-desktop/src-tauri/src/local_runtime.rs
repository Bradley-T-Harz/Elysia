//! Private installed native transport. Socket paths come from XDG, never a
//! webview, editor setting, browser page, URL descriptor, or source checkout.
use crate::codev_contracts::RUNTIME_CONTRACT;
use std::fs::{self, OpenOptions};
use std::io::{self, Read, Write};
use std::net::{SocketAddr, TcpStream};
use std::os::fd::{AsRawFd, FromRawFd, OwnedFd};
use std::os::unix::fs::{FileTypeExt, MetadataExt, OpenOptionsExt};
use std::os::unix::net::UnixStream;
use std::path::Path;
use std::time::Duration;

pub enum Stream {
    Tcp(TcpStream),
    Unix(UnixStream),
}

pub fn connect_unix(directory: &Path) -> io::Result<(UnixStream, i32)> {
    let handle = OpenOptions::new().read(true).custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW).open(directory)?;
    let info = handle.metadata()?;
    let uid = unsafe { libc::geteuid() };
    if !info.is_dir() || info.uid() != uid || info.mode() & 0o077 != 0 {
        return Err(io::Error::new(io::ErrorKind::PermissionDenied, "Unsafe private runtime directory"));
    }
    // fd-relative resolution handles long XDG paths without a public /tmp
    // socket or a username-dependent transport fallback.
    let socket_path = format!("/proc/self/fd/{}/core.sock", handle.as_raw_fd());
    let metadata = fs::symlink_metadata(&socket_path)?;
    if !metadata.file_type().is_socket() || metadata.uid() != uid || metadata.mode() & 0o077 != 0 {
        return Err(io::Error::new(io::ErrorKind::PermissionDenied, "Unsafe private runtime socket"));
    }
    let stream = UnixStream::connect(socket_path)?;
    let mut peer: libc::ucred = unsafe { std::mem::zeroed() };
    let mut length = std::mem::size_of::<libc::ucred>() as libc::socklen_t;
    let result = unsafe { libc::getsockopt(stream.as_raw_fd(), libc::SOL_SOCKET, libc::SO_PEERCRED,
                                         &mut peer as *mut _ as *mut libc::c_void, &mut length) };
    if result != 0 || peer.uid != uid || peer.pid <= 1 {
        return Err(io::Error::new(io::ErrorKind::PermissionDenied, "Runtime peer ownership mismatch"));
    }
    Ok((stream, peer.pid))
}

impl Stream {
    pub fn connect(directory: Option<&Path>, address: &SocketAddr, timeout: Duration) -> io::Result<Self> {
        match directory {
            Some(path) => connect_verified(path).map(|(stream, _)| Self::Unix(stream)),
            None => TcpStream::connect_timeout(address, timeout).map(Self::Tcp),
        }
    }
    pub fn set_read_timeout(&self, timeout: Option<Duration>) -> io::Result<()> {
        match self { Self::Tcp(stream) => stream.set_read_timeout(timeout), Self::Unix(stream) => stream.set_read_timeout(timeout) }
    }
    pub fn set_write_timeout(&self, timeout: Option<Duration>) -> io::Result<()> {
        match self { Self::Tcp(stream) => stream.set_write_timeout(timeout), Self::Unix(stream) => stream.set_write_timeout(timeout) }
    }
}

pub fn connect_verified(directory: &Path) -> io::Result<(UnixStream, i32)> {
    let (mut stream, pid) = connect_unix(directory)?;
    stream.set_read_timeout(Some(Duration::from_secs(2)))?;
    stream.set_write_timeout(Some(Duration::from_secs(2)))?;
    stream.write_all(b"GET /runtime/identity HTTP/1.1\r\nHost: localhost\r\nConnection: keep-alive\r\n\r\n")?;
    let mut headers = Vec::new();
    while !headers.ends_with(b"\r\n\r\n") && headers.len() < 8192 {
        let mut byte = [0u8];
        stream.read_exact(&mut byte)?;
        headers.push(byte[0]);
    }
    let text = String::from_utf8_lossy(&headers);
    if !headers.ends_with(b"\r\n\r\n") || !text.starts_with("HTTP/1.1 200 ") {
        return Err(io::Error::new(io::ErrorKind::InvalidData, "Installed runtime handshake failed"));
    }
    let size = text.lines().find_map(|line| {
        let (key, value) = line.split_once(':')?;
        if key.eq_ignore_ascii_case("content-length") { value.trim().parse::<usize>().ok() } else { None }
    }).filter(|size| *size <= 16384).ok_or_else(|| io::Error::new(io::ErrorKind::InvalidData, "Runtime handshake length invalid"))?;
    let mut body = vec![0; size];
    stream.read_exact(&mut body)?;
    let value: serde_json::Value = serde_json::from_slice(&body)?;
    if value["contract"] != RUNTIME_CONTRACT || value["pid"].as_i64() != Some(pid as i64)
        || value["uid"].as_u64() != Some(unsafe { libc::geteuid() } as u64) || value["transport"] != "unix" {
        return Err(io::Error::new(io::ErrorKind::PermissionDenied, "Installed runtime identity mismatch"));
    }
    Ok((stream, pid))
}
impl Read for Stream {
    fn read(&mut self, buffer: &mut [u8]) -> io::Result<usize> {
        match self { Self::Tcp(stream) => stream.read(buffer), Self::Unix(stream) => stream.read(buffer) }
    }
}
impl Write for Stream {
    fn write(&mut self, buffer: &[u8]) -> io::Result<usize> {
        match self { Self::Tcp(stream) => stream.write(buffer), Self::Unix(stream) => stream.write(buffer) }
    }
    fn flush(&mut self) -> io::Result<()> {
        match self { Self::Tcp(stream) => stream.flush(), Self::Unix(stream) => stream.flush() }
    }
}

/// Stop only the kernel-identified runtime peer, using a pidfd to prevent PID
/// reuse. No shell, process-name search, arbitrary PID, or borrowed TCP port.
pub fn stop_peer(directory: &Path) -> io::Result<()> {
    // Hard-stop cannot depend on a responsive API event loop. The private
    // descriptor binds the kernel peer to this boot and process start time.
    let (_stream, pid) = connect_unix(directory)?;
    if pid == std::process::id() as i32 { return Err(io::Error::new(io::ErrorKind::PermissionDenied, "Refusing to stop this client")); }
    let fd = unsafe { libc::syscall(libc::SYS_pidfd_open, pid, 0) } as i32;
    if fd < 0 { return Err(io::Error::last_os_error()); }
    let _owned_pidfd = unsafe { OwnedFd::from_raw_fd(fd) };
    let file = OpenOptions::new().read(true).custom_flags(libc::O_NOFOLLOW).open(directory.join("service.json"))?;
    let metadata = file.metadata()?;
    if !metadata.is_file() || metadata.nlink() != 1 || metadata.uid() != unsafe { libc::geteuid() } || metadata.mode() & 0o077 != 0 || metadata.len() > 16384 {
        return Err(io::Error::new(io::ErrorKind::PermissionDenied, "Unsafe runtime descriptor"));
    }
    let value: serde_json::Value = serde_json::from_reader(file.take(16384))?;
    let process_stat = fs::read_to_string(format!("/proc/{pid}/stat"))?;
    let start = process_stat.rsplit_once(')').and_then(|(_, rest)| rest.split_whitespace().nth(19));
    let boot = fs::read_to_string("/proc/sys/kernel/random/boot_id")?;
    if value["contract"] != RUNTIME_CONTRACT || value["pid"].as_i64() != Some(pid as i64)
        || value["uid"].as_u64() != Some(unsafe { libc::geteuid() } as u64)
        || value["process_start_ticks"].as_str() != start || value["boot_id"].as_str() != Some(boot.trim()) {
        return Err(io::Error::new(io::ErrorKind::PermissionDenied, "Stale runtime descriptor"));
    }
    let result = unsafe { libc::syscall(libc::SYS_pidfd_send_signal, fd, libc::SIGTERM, std::ptr::null::<libc::siginfo_t>(), 0) };
    if result < 0 { return Err(io::Error::last_os_error()); }
    let mut pollfd = libc::pollfd { fd, events: libc::POLLIN, revents: 0 };
    let wait = unsafe { libc::poll(&mut pollfd, 1, 3000) };
    if wait < 0 { return Err(io::Error::last_os_error()); }
    if wait > 0 && pollfd.revents & libc::POLLIN != 0 { return Ok(()); }
    let killed = unsafe { libc::syscall(libc::SYS_pidfd_send_signal, fd, libc::SIGKILL, std::ptr::null::<libc::siginfo_t>(), 0) };
    if killed < 0 { return Err(io::Error::last_os_error()); }
    if unsafe { libc::poll(&mut pollfd, 1, 3000) } > 0 && pollfd.revents & libc::POLLIN != 0 { return Ok(()); }
    Err(io::Error::new(io::ErrorKind::TimedOut, "Runtime termination could not be confirmed"))
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::fs::PermissionsExt;
    use std::os::unix::net::UnixListener;

    #[test]
    #[ignore = "bounded subprocess fixture, invoked by hard-stop test"]
    fn unresponsive_fixture() {
        let root = std::path::PathBuf::from(std::env::var_os("ELYSIA_TEST_SOCKET_ROOT").expect("fixture directory"));
        unsafe { libc::signal(libc::SIGTERM, libc::SIG_IGN); }
        let listener = UnixListener::bind(root.join("core.sock")).unwrap();
        fs::set_permissions(root.join("core.sock"), fs::Permissions::from_mode(0o600)).unwrap();
        let process_stat = fs::read_to_string("/proc/self/stat").unwrap();
        let value = serde_json::json!({
            "contract": RUNTIME_CONTRACT, "pid": std::process::id(), "uid": unsafe { libc::geteuid() },
            "boot_id": fs::read_to_string("/proc/sys/kernel/random/boot_id").unwrap().trim(),
            "process_start_ticks": process_stat.rsplit_once(')').unwrap().1.split_whitespace().nth(19).unwrap()
        });
        let mut file = OpenOptions::new().write(true).create_new(true).mode(0o600).open(root.join("service.json")).unwrap();
        file.write_all(value.to_string().as_bytes()).unwrap();
        let mut connections = Vec::new();
        for incoming in listener.incoming() { connections.push(incoming.unwrap()); }
    }

    #[test]
    fn hard_stop_rejects_stale_identity_and_confirms_unresponsive_peer_exit() {
        use std::os::unix::process::ExitStatusExt;
        let root = std::env::temp_dir().join(format!("elysia-unresponsive-socket-{}", std::process::id()));
        fs::create_dir(&root).unwrap();
        fs::set_permissions(&root, fs::Permissions::from_mode(0o700)).unwrap();
        let child = std::process::Command::new(std::env::current_exe().unwrap())
            .args(["--ignored", "--exact", "local_runtime::tests::unresponsive_fixture"])
            .env("ELYSIA_TEST_SOCKET_ROOT", &root).stdout(std::process::Stdio::null()).spawn().unwrap();
        struct Cleanup(std::process::Child, std::path::PathBuf);
        impl Drop for Cleanup {
            fn drop(&mut self) { let _ = self.0.kill(); let _ = self.0.wait(); let _ = fs::remove_dir_all(&self.1); }
        }
        let mut owned = Cleanup(child, root.clone());
        let descriptor = root.join("service.json");
        let deadline = std::time::Instant::now() + Duration::from_secs(5);
        while !descriptor.exists() && std::time::Instant::now() < deadline { std::thread::sleep(Duration::from_millis(20)); }
        let original = fs::read_to_string(&descriptor).unwrap();
        let mut stale: serde_json::Value = serde_json::from_str(&original).unwrap();
        stale["process_start_ticks"] = serde_json::json!("0");
        fs::write(&descriptor, stale.to_string()).unwrap();
        assert!(stop_peer(&root).is_err());
        assert!(owned.0.try_wait().unwrap().is_none(), "a stale identity must never authorize termination");
        fs::write(&descriptor, original).unwrap();
        stop_peer(&root).expect("confirmed hard stop of an unresponsive verified peer");
        assert_eq!(owned.0.wait().unwrap().signal(), Some(libc::SIGKILL));
    }

    #[test]
    fn private_socket_verifies_peer_and_rejects_loose_permissions_and_links() {
        let root = std::env::temp_dir().join(format!("elysia-native-socket-{}", std::process::id()));
        fs::create_dir(&root).unwrap();
        fs::set_permissions(&root, fs::Permissions::from_mode(0o700)).unwrap();
        let path = root.join("core.sock");
        let listener = UnixListener::bind(&path).unwrap();
        fs::set_permissions(&path, fs::Permissions::from_mode(0o600)).unwrap();
        assert_eq!(connect_unix(&root).unwrap().1, std::process::id() as i32);
        fs::set_permissions(&path, fs::Permissions::from_mode(0o666)).unwrap();
        assert!(connect_unix(&root).is_err());
        fs::remove_file(&path).unwrap();
        std::os::unix::fs::symlink("other.sock", &path).unwrap();
        assert!(connect_unix(&root).is_err());
        drop(listener);
        fs::remove_file(path).unwrap();
        fs::remove_dir(root).unwrap();
    }
}
