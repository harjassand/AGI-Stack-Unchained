use crate::abi::CONST_POOL_WORDS;

#[derive(Clone, Debug, PartialEq)]
pub struct Program {
    pub words: Vec<u32>,
    pub const_pool: [f32; CONST_POOL_WORDS],
}

impl Default for Program {
    fn default() -> Self {
        Self {
            words: Vec::new(),
            const_pool: [0.0; CONST_POOL_WORDS],
        }
    }
}
