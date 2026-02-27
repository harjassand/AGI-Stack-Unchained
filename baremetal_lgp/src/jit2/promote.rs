use std::sync::Arc;

use super::constants::{A64_RET, RAW_MAX_WORDS, RAW_MIN_WORDS};

pub struct ActiveRawKernel {
    pub hash: [u8; 32],
    pub words: Arc<Vec<u32>>,
    pub epoch: u64,
}

impl ActiveRawKernel {
    pub fn new(words: Vec<u32>, epoch: u64) -> Arc<Self> {
        let normalized = normalize_words(words);
        let hash = blake3::hash(bytemuck_words(&normalized)).into();
        Arc::new(Self {
            hash,
            words: Arc::new(normalized),
            epoch,
        })
    }
}

fn normalize_words(mut words: Vec<u32>) -> Vec<u32> {
    if words.len() > RAW_MAX_WORDS {
        words.truncate(RAW_MAX_WORDS);
    }
    if words.len() < RAW_MIN_WORDS {
        words.push(A64_RET);
    }
    words
}

fn bytemuck_words(words: &[u32]) -> &[u8] {
    // SAFETY: u32 slice is plain-old-data and reinterpreted as bytes.
    unsafe { std::slice::from_raw_parts(words.as_ptr().cast::<u8>(), words.len() * 4) }
}
