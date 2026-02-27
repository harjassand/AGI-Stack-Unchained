use crate::contracts::constants::{F_REGS, I_REGS, META_F32, META_U32, SCRATCH_WORDS_F32};

#[repr(C, align(16))]
pub struct RuntimeState {
    pub scratch: [f32; SCRATCH_WORDS_F32], // 16384
    pub fregs: [f32; F_REGS],              // 16
    pub iregs: [i32; I_REGS],              // 16
    pub meta_u32: [u32; META_U32],         // 16
    pub meta_f32: [f32; META_F32],         // 16
    pub status_u32: u32,                   // kernel-written status (untrusted)
    pub _pad: [u32; 3],                    // pad to 16B multiple
}

impl RuntimeState {
    #[inline(always)]
    pub fn wipe_all(&mut self) {
        // Must be full wipe every episode (fatal-flaw fix)
        self.scratch.fill(0.0);
        self.fregs.fill(0.0);
        self.iregs.fill(0);
        self.meta_u32.fill(0);
        self.meta_f32.fill(0.0);
        self.status_u32 = 0;
    }
}

impl Default for RuntimeState {
    fn default() -> Self {
        Self {
            scratch: [0.0; SCRATCH_WORDS_F32],
            fregs: [0.0; F_REGS],
            iregs: [0; I_REGS],
            meta_u32: [0; META_U32],
            meta_f32: [0.0; META_F32],
            status_u32: 0,
            _pad: [0; 3],
        }
    }
}
