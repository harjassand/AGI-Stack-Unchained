pub type ChunkPackDigest = [u8; 32];

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum NumericSubstrate {
    Fp32,
    Log8Sim,
    Posit16Sim,
    Int4Gate,
    Int2Gate,
}

impl NumericSubstrate {
    pub fn as_tag(self) -> &'static str {
        match self {
            NumericSubstrate::Fp32 => "fp32",
            NumericSubstrate::Log8Sim => "log8_sim",
            NumericSubstrate::Posit16Sim => "posit16_sim",
            NumericSubstrate::Int4Gate => "int4_gate",
            NumericSubstrate::Int2Gate => "int2_gate",
        }
    }

    pub fn capacity_multiplier_estimate(self) -> f32 {
        match self {
            NumericSubstrate::Fp32 => 1.0,
            NumericSubstrate::Posit16Sim => 2.0,
            NumericSubstrate::Log8Sim => 4.0,
            NumericSubstrate::Int4Gate => 8.0,
            NumericSubstrate::Int2Gate => 16.0,
        }
    }
}

impl Default for NumericSubstrate {
    fn default() -> Self {
        Self::Fp32
    }
}

#[derive(Clone)]
pub struct ChunkPack {
    pub spec_hash: [u8; 32],
    pub compile_seed: u64,
    pub episode_count: u32,
    pub numeric_substrate: NumericSubstrate,

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

    pub fn quantize_in_place(&mut self, substrate: NumericSubstrate) {
        quantize_slice(&mut self.inputs, substrate);
        quantize_slice(&mut self.targets, substrate);
        quantize_slice(&mut self.meta_f32, substrate);
        self.numeric_substrate = substrate;
        self.digest = compute_chunk_digest(self);
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
    hasher.update(chunk.numeric_substrate.as_tag().as_bytes());

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

pub fn quantize_slice(values: &mut [f32], substrate: NumericSubstrate) {
    for v in values {
        *v = quantize_value(*v, substrate);
    }
}

fn quantize_value(v: f32, substrate: NumericSubstrate) -> f32 {
    match substrate {
        NumericSubstrate::Fp32 => v,
        // Approximate logarithmic coding via log-domain bucketization.
        NumericSubstrate::Log8Sim => {
            if v == 0.0 {
                return 0.0;
            }
            let sign = if v < 0.0 { -1.0 } else { 1.0 };
            let lv = v.abs().ln_1p();
            let q = (lv * 32.0).round() / 32.0;
            sign * q.exp_m1()
        }
        // Simulated posit-like rounding: keep coarse exponent/mantissa.
        NumericSubstrate::Posit16Sim => (v * 1024.0).round() / 1024.0,
        // Int4 gate for routing-like values in [-1, 1].
        NumericSubstrate::Int4Gate => ((v.clamp(-1.0, 1.0) * 7.0).round()) / 7.0,
        // Int2 gate for ultra-coarse branch routing.
        NumericSubstrate::Int2Gate => ((v.clamp(-1.0, 1.0) * 1.0).round()) / 1.0,
    }
}
