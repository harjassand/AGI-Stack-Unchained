use serde::{Deserialize, Serialize};

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct RunDigestV2 {
    pub version: u32,
    pub seed: u64,
    pub epochs: u32,
    pub a_champion_hash: [u8; 32],
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct RunDigestV3 {
    pub version: u32,
    pub seed: u64,
    pub epochs: u32,
    pub a_champion_hash: [u8; 32],
    pub b_current_spec_hash: [u8; 32],
    pub b_league_topk_hashes: Vec<[u8; 32]>,
    pub chunk_schedule_hash: [u8; 32],
}

pub fn run_digest_v3_text(digest: &RunDigestV3) -> String {
    let mut out = String::new();
    out.push_str(&format!("version={}\n", digest.version));
    out.push_str(&format!("seed={}\n", digest.seed));
    out.push_str(&format!("epochs={}\n", digest.epochs));
    out.push_str(&format!(
        "a_champion_hash={}\n",
        bytes32_to_hex(&digest.a_champion_hash)
    ));
    out.push_str(&format!(
        "b_current_spec_hash={}\n",
        bytes32_to_hex(&digest.b_current_spec_hash)
    ));
    out.push_str("b_league_topk_hashes=");
    if digest.b_league_topk_hashes.is_empty() {
        out.push_str("[]\n");
    } else {
        let hashes = digest
            .b_league_topk_hashes
            .iter()
            .map(bytes32_to_hex)
            .collect::<Vec<_>>()
            .join(",");
        out.push('[');
        out.push_str(&hashes);
        out.push_str("]\n");
    }
    out.push_str(&format!(
        "chunk_schedule_hash={}\n",
        bytes32_to_hex(&digest.chunk_schedule_hash)
    ));
    out
}

pub fn bytes32_to_hex(bytes: &[u8; 32]) -> String {
    let mut out = String::with_capacity(64);
    for b in bytes {
        out.push(hex_nibble((b >> 4) & 0x0F));
        out.push(hex_nibble(b & 0x0F));
    }
    out
}

fn hex_nibble(n: u8) -> char {
    match n {
        0..=9 => (b'0' + n) as char,
        10..=15 => (b'a' + (n - 10)) as char,
        _ => '0',
    }
}
