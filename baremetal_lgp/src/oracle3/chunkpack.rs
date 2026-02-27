pub type ChunkPackDigest = [u8; 32];

#[derive(Clone)]
pub struct ChunkPack {
    pub spec_hash: [u8; 32],
    pub compile_seed: u64,
    pub episode_count: u32,

    pub input_len: u32,
    pub output_len: u32,
    pub meta_u32_len: u32,
    pub meta_f32_len: u32,

    pub inputs: Vec<f32>,
    pub targets: Vec<f32>,
    pub meta_u32: Vec<u32>,
    pub meta_f32: Vec<f32>,

    pub digest: ChunkPackDigest,
}

impl ChunkPack {
    pub fn input(&self, ep: u32) -> &[f32] {
        let ep_usize = ep as usize;
        assert!(
            ep_usize < self.episode_count as usize,
            "episode out of bounds"
        );
        let stride = self.input_len as usize;
        let start = ep_usize.saturating_mul(stride);
        &self.inputs[start..start + stride]
    }

    pub fn target(&self, ep: u32) -> &[f32] {
        let ep_usize = ep as usize;
        assert!(
            ep_usize < self.episode_count as usize,
            "episode out of bounds"
        );
        let stride = self.output_len as usize;
        let start = ep_usize.saturating_mul(stride);
        &self.targets[start..start + stride]
    }

    pub fn meta_u32(&self, ep: u32) -> &[u32] {
        let ep_usize = ep as usize;
        assert!(
            ep_usize < self.episode_count as usize,
            "episode out of bounds"
        );
        let stride = self.meta_u32_len as usize;
        let start = ep_usize.saturating_mul(stride);
        &self.meta_u32[start..start + stride]
    }

    pub fn meta_f32(&self, ep: u32) -> &[f32] {
        let ep_usize = ep as usize;
        assert!(
            ep_usize < self.episode_count as usize,
            "episode out of bounds"
        );
        let stride = self.meta_f32_len as usize;
        let start = ep_usize.saturating_mul(stride);
        &self.meta_f32[start..start + stride]
    }

    pub fn recompute_digest(&self) -> ChunkPackDigest {
        compute_chunk_digest(self)
    }
}

pub fn compute_chunk_digest(chunk: &ChunkPack) -> ChunkPackDigest {
    let mut hasher = blake3::Hasher::new();

    hasher.update(&chunk.spec_hash);
    hasher.update(&chunk.compile_seed.to_le_bytes());
    hasher.update(&chunk.episode_count.to_le_bytes());
    hasher.update(&chunk.input_len.to_le_bytes());
    hasher.update(&chunk.output_len.to_le_bytes());
    hasher.update(&chunk.meta_u32_len.to_le_bytes());
    hasher.update(&chunk.meta_f32_len.to_le_bytes());

    for value in &chunk.inputs {
        hasher.update(&value.to_le_bytes());
    }
    for value in &chunk.targets {
        hasher.update(&value.to_le_bytes());
    }
    for value in &chunk.meta_u32 {
        hasher.update(&value.to_le_bytes());
    }
    for value in &chunk.meta_f32 {
        hasher.update(&value.to_le_bytes());
    }

    *hasher.finalize().as_bytes()
}
