pub fn available() -> bool {
    cfg!(all(feature = "jit", target_arch = "aarch64"))
}
