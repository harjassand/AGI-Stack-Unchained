use serde::Serialize;
use sha2::{Digest, Sha256};
use std::env;
use std::fs;
use std::path::PathBuf;

#[derive(Clone, Debug, Serialize)]
struct BackendContract {
    schema_version: String,
    backend_contract_id: String,
    winterfell_backend_id: String,
    winterfell_backend_version: String,
    winterfell_field_id: String,
    winterfell_extension_id: String,
    winterfell_merkle_hasher_id: String,
    winterfell_random_coin_hasher_id: String,
    winterfell_proof_options_keys: Vec<String>,
}

fn canonical_contract_bytes_without_id(contract: &BackendContract) -> Vec<u8> {
    let mut map = serde_json::Map::new();
    map.insert(
        "schema_version".to_string(),
        serde_json::Value::String(contract.schema_version.clone()),
    );
    map.insert(
        "winterfell_backend_id".to_string(),
        serde_json::Value::String(contract.winterfell_backend_id.clone()),
    );
    map.insert(
        "winterfell_backend_version".to_string(),
        serde_json::Value::String(contract.winterfell_backend_version.clone()),
    );
    map.insert(
        "winterfell_extension_id".to_string(),
        serde_json::Value::String(contract.winterfell_extension_id.clone()),
    );
    map.insert(
        "winterfell_field_id".to_string(),
        serde_json::Value::String(contract.winterfell_field_id.clone()),
    );
    map.insert(
        "winterfell_merkle_hasher_id".to_string(),
        serde_json::Value::String(contract.winterfell_merkle_hasher_id.clone()),
    );
    map.insert(
        "winterfell_proof_options_keys".to_string(),
        serde_json::Value::Array(
            contract
                .winterfell_proof_options_keys
                .iter()
                .map(|v| serde_json::Value::String(v.clone()))
                .collect(),
        ),
    );
    map.insert(
        "winterfell_random_coin_hasher_id".to_string(),
        serde_json::Value::String(contract.winterfell_random_coin_hasher_id.clone()),
    );
    serde_json::to_vec(&serde_json::Value::Object(map)).expect("serialize canonical backend contract")
}

fn contract_template() -> BackendContract {
    let mut out = BackendContract {
        schema_version: "policy_vm_winterfell_backend_contract_v1".to_string(),
        backend_contract_id: "sha256:0000000000000000000000000000000000000000000000000000000000000000"
            .to_string(),
        winterfell_backend_id: "WINTERFELL_RS_0_13_1".to_string(),
        winterfell_backend_version: "0.13.1".to_string(),
        winterfell_field_id: "WINTERFELL_F128".to_string(),
        winterfell_extension_id: "FIELD_EXTENSION_NONE_DEGREE_1".to_string(),
        winterfell_merkle_hasher_id: "winterfell::crypto::hashers::Blake3_256".to_string(),
        winterfell_random_coin_hasher_id:
            "winterfell::crypto::DefaultRandomCoin<Blake3_256>".to_string(),
        winterfell_proof_options_keys: vec![
            "num_queries".to_string(),
            "blowup_factor".to_string(),
            "grinding_factor".to_string(),
            "field_extension".to_string(),
            "fri_folding_factor".to_string(),
            "fri_remainder_max_degree".to_string(),
            "batching_constraints".to_string(),
            "batching_deep".to_string(),
            "num_partitions".to_string(),
            "hash_rate".to_string(),
        ],
    };
    let bytes = canonical_contract_bytes_without_id(&out);
    let digest = Sha256::digest(bytes);
    out.backend_contract_id = format!("sha256:{digest:x}");
    out
}

fn parse_out_path() -> Option<PathBuf> {
    let mut args = env::args().skip(1);
    while let Some(arg) = args.next() {
        if arg == "--emit-contract" {
            if let Some(path) = args.next() {
                return Some(PathBuf::from(path));
            }
            panic!("--emit-contract requires a target path");
        }
    }
    None
}

fn main() {
    let payload = contract_template();
    let data = serde_json::to_vec(&payload).expect("serialize backend contract");
    if let Some(path) = parse_out_path() {
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent).expect("create parent directory");
        }
        fs::write(path, data).expect("write backend contract");
    } else {
        println!("{}", String::from_utf8(data).expect("utf8 contract json"));
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn backend_contract_id_matches_canonical_contract_bytes() {
        let contract = contract_template();
        let bytes = canonical_contract_bytes_without_id(&contract);
        let digest = Sha256::digest(bytes);
        assert_eq!(contract.backend_contract_id, format!("sha256:{digest:x}"));
        assert_eq!(contract.winterfell_backend_version, "0.13.1");
    }
}
