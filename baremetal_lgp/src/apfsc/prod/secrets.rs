use std::fs;
use std::path::Path;

use crate::apfsc::errors::{io_err, Result};

pub trait SecretProvider {
    fn get_secret(&self, key: &str) -> Result<Option<String>>;
}

pub struct FileSecretProvider {
    pub root: std::path::PathBuf,
}

impl SecretProvider for FileSecretProvider {
    fn get_secret(&self, key: &str) -> Result<Option<String>> {
        let p = self.root.join(key);
        if !p.exists() {
            return Ok(None);
        }
        let v = fs::read_to_string(&p).map_err(|e| io_err(&p, e))?;
        Ok(Some(v.trim().to_string()))
    }
}

pub struct EnvSecretProvider;

impl SecretProvider for EnvSecretProvider {
    fn get_secret(&self, key: &str) -> Result<Option<String>> {
        Ok(std::env::var(key).ok())
    }
}

pub fn validate_secret_permissions(path: &Path) -> Result<()> {
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        if path.exists() {
            let md = fs::metadata(path).map_err(|e| io_err(path, e))?;
            let mode = md.permissions().mode() & 0o777;
            if mode & 0o077 != 0 {
                return Err(crate::apfsc::errors::ApfscError::Validation(format!(
                    "secret {} has overly broad permissions {:o}",
                    path.display(),
                    mode
                )));
            }
        }
    }
    Ok(())
}
