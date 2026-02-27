#[cfg(target_os = "macos")]
pub fn accelerate_enabled() -> bool {
    true
}

#[cfg(not(target_os = "macos"))]
pub fn accelerate_enabled() -> bool {
    false
}
