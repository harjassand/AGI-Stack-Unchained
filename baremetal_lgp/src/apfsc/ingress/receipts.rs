use std::path::Path;

use crate::apfsc::artifacts::{digest_json, receipt_path, write_json_atomic};
use crate::apfsc::errors::Result;
use crate::apfsc::types::IngressReceipt;

pub fn write_ingress_receipt(root: &Path, receipt: &IngressReceipt) -> Result<String> {
    let hash = digest_json(receipt)?;
    let path = receipt_path(root, "ingress", &format!("{hash}.json"));
    write_json_atomic(&path, receipt)?;
    Ok(hash)
}
