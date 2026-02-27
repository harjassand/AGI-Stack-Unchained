#[derive(Clone, Debug, Default)]
pub struct VmProgram {
    pub words: Vec<u32>,
}

#[derive(Clone, Debug)]
pub struct VmWorker {
    pub f: [f32; 16],
    pub i: [i32; 16],
    pub scratch: Vec<f32>,
}

impl Default for VmWorker {
    fn default() -> Self {
        Self {
            f: [0.0; 16],
            i: [0; 16],
            scratch: vec![0.0; crate::contracts::constants::SCRATCH_WORDS_F32],
        }
    }
}
