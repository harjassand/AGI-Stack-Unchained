use std::env;
use std::fs;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};

pub fn args() -> Vec<String> {
    env::args().collect()
}

pub fn current_dir() -> Result<PathBuf, String> {
    env::current_dir().map_err(|_| "INVALID:KERNEL_INTERNAL".to_string())
}

pub fn current_exe() -> Result<PathBuf, String> {
    env::current_exe().map_err(|_| "INVALID:KERNEL_INTERNAL".to_string())
}

pub fn read_to_string(path: &Path) -> Result<String, String> {
    fs::read_to_string(path).map_err(|_| "INVALID:MISSING_ARTIFACT".to_string())
}

pub fn read_bytes(path: &Path) -> Result<Vec<u8>, String> {
    fs::read(path).map_err(|_| "INVALID:MISSING_ARTIFACT".to_string())
}

pub fn write_bytes(path: &Path, bytes: &[u8]) -> Result<(), String> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|_| "INVALID:OUTSIDE_ROOT_WRITE".to_string())?;
    }
    fs::write(path, bytes).map_err(|_| "INVALID:OUTSIDE_ROOT_WRITE".to_string())
}

pub fn create_dir_all(path: &Path) -> Result<(), String> {
    fs::create_dir_all(path).map_err(|_| "INVALID:OUTSIDE_ROOT_WRITE".to_string())
}

pub fn remove_dir_all(path: &Path) -> Result<(), String> {
    if path.exists() {
        fs::remove_dir_all(path).map_err(|_| "INVALID:OUTSIDE_ROOT_WRITE".to_string())
    } else {
        Ok(())
    }
}

pub fn copy_file(src: &Path, dst: &Path) -> Result<(), String> {
    if let Some(parent) = dst.parent() {
        fs::create_dir_all(parent).map_err(|_| "INVALID:OUTSIDE_ROOT_WRITE".to_string())?;
    }
    fs::copy(src, dst).map_err(|_| "INVALID:MISSING_ARTIFACT".to_string())?;
    Ok(())
}

pub fn exists(path: &Path) -> bool {
    path.exists()
}

pub fn list_files_recursive(root: &Path) -> Result<Vec<PathBuf>, String> {
    let mut out: Vec<PathBuf> = Vec::new();
    walk_dir(root, &mut out)?;
    out.sort();
    Ok(out)
}

fn walk_dir(path: &Path, out: &mut Vec<PathBuf>) -> Result<(), String> {
    let meta = fs::metadata(path).map_err(|_| "INVALID:MISSING_ARTIFACT".to_string())?;
    if meta.is_file() {
        out.push(path.to_path_buf());
        return Ok(());
    }
    for entry in fs::read_dir(path).map_err(|_| "INVALID:MISSING_ARTIFACT".to_string())? {
        let entry = entry.map_err(|_| "INVALID:MISSING_ARTIFACT".to_string())?;
        walk_dir(&entry.path(), out)?;
    }
    Ok(())
}

pub fn run_command(argv: &[String], stdin_data: Option<&[u8]>) -> Result<(i32, String, String), String> {
    if argv.is_empty() {
        return Err("INVALID:KERNEL_INTERNAL".to_string());
    }
    let mut cmd = Command::new(&argv[0]);
    if argv.len() > 1 {
        cmd.args(&argv[1..]);
    }
    if stdin_data.is_some() {
        cmd.stdin(Stdio::piped());
    }
    cmd.stdout(Stdio::piped());
    cmd.stderr(Stdio::piped());

    let mut child = cmd.spawn().map_err(|_| "INVALID:KERNEL_INTERNAL".to_string())?;
    if let Some(data) = stdin_data {
        if let Some(stdin) = child.stdin.as_mut() {
            stdin
                .write_all(data)
                .map_err(|_| "INVALID:KERNEL_INTERNAL".to_string())?;
        }
    }
    let out = child
        .wait_with_output()
        .map_err(|_| "INVALID:KERNEL_INTERNAL".to_string())?;
    let code = out.status.code().unwrap_or(30);
    let stdout = String::from_utf8_lossy(&out.stdout).to_string();
    let stderr = String::from_utf8_lossy(&out.stderr).to_string();
    Ok((code, stdout, stderr))
}

pub fn exit(code: i32) -> ! {
    std::process::exit(code)
}

pub fn sha256_file(path: &Path) -> Result<String, String> {
    let argv = vec![
        "/usr/bin/shasum".to_string(),
        "-a".to_string(),
        "256".to_string(),
        path.to_string_lossy().to_string(),
    ];
    let (code, stdout, _stderr) = run_command(&argv, None)?;
    if code != 0 {
        return Err("INVALID:KERNEL_INTERNAL".to_string());
    }
    parse_shasum_output(&stdout)
}

pub fn sha256_bytes(bytes: &[u8]) -> Result<String, String> {
    let argv = vec![
        "/usr/bin/shasum".to_string(),
        "-a".to_string(),
        "256".to_string(),
    ];
    let (code, stdout, _stderr) = run_command(&argv, Some(bytes))?;
    if code != 0 {
        return Err("INVALID:KERNEL_INTERNAL".to_string());
    }
    parse_shasum_output(&stdout)
}

fn parse_shasum_output(raw: &str) -> Result<String, String> {
    let token = raw
        .split_whitespace()
        .next()
        .ok_or_else(|| "INVALID:KERNEL_INTERNAL".to_string())?;
    if token.len() != 64 || !token.chars().all(|c| c.is_ascii_hexdigit()) {
        return Err("INVALID:KERNEL_INTERNAL".to_string());
    }
    Ok(token.to_ascii_lowercase())
}
