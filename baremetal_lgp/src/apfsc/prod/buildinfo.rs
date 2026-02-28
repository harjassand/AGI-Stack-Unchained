use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct BuildInfo {
    pub pkg_name: String,
    pub pkg_version: String,
    pub git_commit: Option<String>,
    pub rustc_version: Option<String>,
    pub target: String,
    pub build_profile: String,
}

pub fn current_build_info() -> BuildInfo {
    BuildInfo {
        pkg_name: env!("CARGO_PKG_NAME").to_string(),
        pkg_version: env!("CARGO_PKG_VERSION").to_string(),
        git_commit: option_env!("GIT_COMMIT").map(|v| v.to_string()),
        rustc_version: option_env!("RUSTC_VERSION").map(|v| v.to_string()),
        target: std::env::var("TARGET").unwrap_or_else(|_| std::env::consts::ARCH.to_string()),
        build_profile: std::env::var("PROFILE").unwrap_or_else(|_| "dev".to_string()),
    }
}
