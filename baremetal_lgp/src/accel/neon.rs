pub fn neon_enabled() -> bool {
    cfg!(target_arch = "aarch64")
}
