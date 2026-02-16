use serde::de::DeserializeOwned;
use serde::Serialize;
use std::env;
use std::fs;
use std::path::PathBuf;

pub struct Args {
    pub prior_path: PathBuf,
    pub out_plan_path: PathBuf,
}

impl Args {
    pub fn parse() -> Result<Self, String> {
        let mut it = env::args().skip(1);
        let mut prior_path: Option<PathBuf> = None;
        let mut out_plan_path: Option<PathBuf> = None;
        while let Some(arg) = it.next() {
            match arg.as_str() {
                "--prior" => {
                    let value = it.next().ok_or_else(|| "missing --prior value".to_string())?;
                    prior_path = Some(PathBuf::from(value));
                }
                "--out_plan" => {
                    let value = it.next().ok_or_else(|| "missing --out_plan value".to_string())?;
                    out_plan_path = Some(PathBuf::from(value));
                }
                _ => return Err(format!("unknown arg: {}", arg)),
            }
        }
        Ok(Args {
            prior_path: prior_path.ok_or_else(|| "missing --prior".to_string())?,
            out_plan_path: out_plan_path.ok_or_else(|| "missing --out_plan".to_string())?,
        })
    }
}

pub fn read_json<T: DeserializeOwned>(path: &PathBuf) -> Result<T, String> {
    let raw = fs::read_to_string(path).map_err(|e| format!("read {} failed: {}", path.display(), e))?;
    serde_json::from_str::<T>(&raw).map_err(|e| format!("parse {} failed: {}", path.display(), e))
}

pub fn write_json<T: Serialize>(path: &PathBuf, value: &T) -> Result<(), String> {
    let raw = serde_json::to_string(value).map_err(|e| format!("serialize failed: {}", e))?;
    fs::write(path, raw + "\n").map_err(|e| format!("write {} failed: {}", path.display(), e))
}
