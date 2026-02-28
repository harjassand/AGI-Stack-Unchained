use std::path::PathBuf;

use thiserror::Error;

#[derive(Debug, Error)]
pub enum ApfscError {
    #[error("io error at {path}: {source}")]
    Io {
        path: PathBuf,
        #[source]
        source: std::io::Error,
    },

    #[error("json error: {0}")]
    Json(#[from] serde_json::Error),

    #[error("toml decode error: {0}")]
    TomlDecode(#[from] toml::de::Error),

    #[error("toml encode error: {0}")]
    TomlEncode(#[from] toml::ser::Error),

    #[error("validation error: {0}")]
    Validation(String),

    #[error("missing artifact: {0}")]
    Missing(String),

    #[error("digest mismatch: {0}")]
    DigestMismatch(String),

    #[error("unsupported: {0}")]
    Unsupported(String),

    #[error("protocol error: {0}")]
    Protocol(String),
}

pub type Result<T> = std::result::Result<T, ApfscError>;

pub fn io_err(path: impl Into<PathBuf>, source: std::io::Error) -> ApfscError {
    ApfscError::Io {
        path: path.into(),
        source,
    }
}
