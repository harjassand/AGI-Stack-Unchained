use std::collections::BTreeMap;
use std::fs;
use std::path::Path;

use serde::{Deserialize, Serialize};

use crate::apfsc::errors::{io_err, ApfscError, Result};

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq, PartialOrd, Ord)]
pub enum Role {
    Reader,
    Operator,
    ReleaseManager,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct TokenRecord {
    pub actor: String,
    pub role: Role,
    pub token: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct TokenFile {
    pub tokens: Vec<TokenRecord>,
}

pub fn load_token_file(path: &Path) -> Result<TokenFile> {
    let body = fs::read(path).map_err(|e| io_err(path, e))?;
    Ok(serde_json::from_slice(&body)?)
}

pub fn validate_token_permissions(path: &Path) -> Result<()> {
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let md = fs::metadata(path).map_err(|e| io_err(path, e))?;
        let mode = md.permissions().mode() & 0o777;
        if mode != 0o600 {
            return Err(ApfscError::Validation(format!(
                "token file {} must be mode 0600, got {:o}",
                path.display(),
                mode
            )));
        }
    }
    Ok(())
}

pub fn resolve_role(path: &Path, actor: &str, token: Option<&str>) -> Result<Role> {
    let tf = load_token_file(path)?;
    let mut map = BTreeMap::<&str, (&str, Role)>::new();
    for rec in &tf.tokens {
        map.insert(rec.actor.as_str(), (rec.token.as_str(), rec.role));
    }
    let (expect, role) = map
        .get(actor)
        .ok_or_else(|| ApfscError::Validation(format!("unknown actor: {actor}")))?;
    let provided = token.ok_or_else(|| ApfscError::Validation("missing token".to_string()))?;
    if provided != *expect {
        return Err(ApfscError::Validation("token mismatch".to_string()));
    }
    Ok(*role)
}

pub fn authorize(role: Role, required: Role) -> Result<()> {
    if role < required {
        return Err(ApfscError::Validation(format!(
            "insufficient role: have {:?}, need {:?}",
            role, required
        )));
    }
    Ok(())
}
