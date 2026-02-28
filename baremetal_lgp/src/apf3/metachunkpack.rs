use std::fs;
use std::path::Path;

use serde::{Deserialize, Serialize};

use crate::apf3::digest::{Digest32, DigestBuilder, TAG_APF3_PACK_V1};

#[derive(Clone, Serialize, Deserialize)]
pub struct Chunk {
    pub x: Vec<f32>,
    pub y: Vec<f32>,
    pub meta: Vec<u32>,
}

#[derive(Clone, Serialize, Deserialize)]
pub struct MetaChunkPack {
    pub version: u32,
    pub support: Vec<Chunk>,
    pub query: Vec<Chunk>,
    pub salt: u64,
    pub pack_digest: Digest32,
}

impl MetaChunkPack {
    pub fn new(version: u32, support: Vec<Chunk>, query: Vec<Chunk>, salt: u64) -> Self {
        let mut pack = Self {
            version,
            support,
            query,
            salt,
            pack_digest: Digest32::zero(),
        };
        pack.pack_digest = pack.recompute_digest();
        pack
    }

    pub fn recompute_digest(&self) -> Digest32 {
        let mut b = DigestBuilder::new(TAG_APF3_PACK_V1);
        b.u32(self.version);
        b.u64(self.salt);

        b.u64(self.support.len() as u64);
        for chunk in &self.support {
            hash_chunk(&mut b, chunk);
        }

        b.u64(self.query.len() as u64);
        for chunk in &self.query {
            hash_chunk(&mut b, chunk);
        }

        b.finish()
    }

    pub fn validate_digest(&self) -> bool {
        self.pack_digest == self.recompute_digest()
    }

    pub fn to_json_file(&self, path: &Path) -> Result<(), String> {
        let body = serde_json::to_vec_pretty(self).map_err(|e| e.to_string())?;
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent).map_err(|e| e.to_string())?;
        }
        fs::write(path, body).map_err(|e| e.to_string())
    }

    pub fn from_json_file(path: &Path) -> Result<Self, String> {
        let body = fs::read(path).map_err(|e| e.to_string())?;
        let pack: MetaChunkPack = serde_json::from_slice(&body).map_err(|e| e.to_string())?;
        if !pack.validate_digest() {
            return Err(format!("invalid pack digest in {}", path.display()));
        }
        Ok(pack)
    }
}

pub fn hash_chunk(b: &mut DigestBuilder, chunk: &Chunk) {
    b.u64(chunk.x.len() as u64);
    for &v in &chunk.x {
        b.f32(v);
    }

    b.u64(chunk.y.len() as u64);
    for &v in &chunk.y {
        b.f32(v);
    }

    b.u64(chunk.meta.len() as u64);
    for &v in &chunk.meta {
        b.u32(v);
    }
}
