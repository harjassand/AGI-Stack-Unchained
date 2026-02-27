#[derive(Clone, Debug)]
pub struct BytecodeProgram {
    pub words: Vec<u32>,
    pub const_pool: [f32; crate::abi::CONST_POOL_WORDS],
    #[cfg(feature = "trace")]
    pub pc_to_block: Vec<u16>,
}

impl Default for BytecodeProgram {
    fn default() -> Self {
        Self {
            words: Vec::new(),
            const_pool: [0.0; crate::abi::CONST_POOL_WORDS],
            #[cfg(feature = "trace")]
            pc_to_block: Vec::new(),
        }
    }
}
