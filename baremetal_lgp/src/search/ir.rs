use core::fmt;

pub const CAND_MAX_BLOCKS: usize = 256;
pub const CAND_MAX_INSNS: usize = 4096;
pub const BLOCK_MAX_INSNS: usize = 1024;
pub const CONST_POOL_WORDS: usize = 128;

#[repr(u8)]
#[derive(Copy, Clone, Debug, PartialEq, Eq)]
pub enum Opcode {
    Halt = 0x00,
    Nop = 0x01,
    FMov = 0x02,
    FAdd = 0x03,
    FSub = 0x04,
    FMul = 0x05,
    FFma = 0x06,
    FAbs = 0x07,
    FNeg = 0x08,
    IMov = 0x09,
    IAdd = 0x0A,
    ISub = 0x0B,
    IAnd = 0x0C,
    IOr = 0x0D,
    IXor = 0x0E,
    IShl = 0x0F,
    IShr = 0x10,
    LdF = 0x11,
    StF = 0x12,
    FConst = 0x13,
    IConst = 0x14,
    LdMU32 = 0x15,
    LdMF32 = 0x16,
    IToF = 0x17,
    FToI = 0x18,
    FTanh = 0x19,
    FSigm = 0x1A,
    Jmp = 0x1B,
    Jz = 0x1C,
    Jnz = 0x1D,
    Loop = 0x1E,
    Call = 0x1F,
    Ret = 0x20,
    VAdd = 0x21,
    VMul = 0x22,
    VFma = 0x23,
    VDot = 0x24,
    VCAdd = 0x25,
    VCMul = 0x26,
    VCDot = 0x27,
    Gemm = 0x28,
    CallLib = 0x3F,
}

impl Opcode {
    pub fn from_u8(value: u8) -> Option<Self> {
        let op = match value {
            0x00 => Self::Halt,
            0x01 => Self::Nop,
            0x02 => Self::FMov,
            0x03 => Self::FAdd,
            0x04 => Self::FSub,
            0x05 => Self::FMul,
            0x06 => Self::FFma,
            0x07 => Self::FAbs,
            0x08 => Self::FNeg,
            0x09 => Self::IMov,
            0x0A => Self::IAdd,
            0x0B => Self::ISub,
            0x0C => Self::IAnd,
            0x0D => Self::IOr,
            0x0E => Self::IXor,
            0x0F => Self::IShl,
            0x10 => Self::IShr,
            0x11 => Self::LdF,
            0x12 => Self::StF,
            0x13 => Self::FConst,
            0x14 => Self::IConst,
            0x15 => Self::LdMU32,
            0x16 => Self::LdMF32,
            0x17 => Self::IToF,
            0x18 => Self::FToI,
            0x19 => Self::FTanh,
            0x1A => Self::FSigm,
            0x1B => Self::Jmp,
            0x1C => Self::Jz,
            0x1D => Self::Jnz,
            0x1E => Self::Loop,
            0x1F => Self::Call,
            0x20 => Self::Ret,
            0x21 => Self::VAdd,
            0x22 => Self::VMul,
            0x23 => Self::VFma,
            0x24 => Self::VDot,
            0x25 => Self::VCAdd,
            0x26 => Self::VCMul,
            0x27 => Self::VCDot,
            0x28 => Self::Gemm,
            0x3F => Self::CallLib,
            _ => return None,
        };
        Some(op)
    }

    pub fn class(self) -> OpClass {
        match self {
            Self::FMov
            | Self::FAdd
            | Self::FSub
            | Self::FMul
            | Self::FFma
            | Self::FAbs
            | Self::FNeg
            | Self::IToF
            | Self::FToI => OpClass::FloatScalar,
            Self::IMov
            | Self::IAdd
            | Self::ISub
            | Self::IAnd
            | Self::IOr
            | Self::IXor
            | Self::IShl
            | Self::IShr
            | Self::IConst => OpClass::IntScalar,
            Self::LdF | Self::StF | Self::FConst | Self::LdMU32 | Self::LdMF32 => OpClass::Mem,
            Self::FTanh | Self::FSigm => OpClass::NonLinear,
            Self::Jmp | Self::Jz | Self::Jnz | Self::Loop | Self::Call | Self::Ret => {
                OpClass::Control
            }
            Self::VAdd | Self::VMul | Self::VFma | Self::VDot | Self::Gemm => OpClass::VectorReal,
            Self::VCAdd | Self::VCMul | Self::VCDot => OpClass::VectorComplex,
            Self::Halt | Self::Nop | Self::CallLib => OpClass::Other,
        }
    }
}

#[derive(Copy, Clone, Debug, PartialEq, Eq)]
pub enum OpClass {
    FloatScalar,
    IntScalar,
    Mem,
    NonLinear,
    Control,
    VectorReal,
    VectorComplex,
    Other,
}

#[derive(Clone, Debug, PartialEq)]
pub struct Instruction {
    pub opcode: Opcode,
    pub rd: u8,
    pub ra: u8,
    pub rb: u8,
    pub imm14: u16,
}

impl Instruction {
    pub fn encode_word(&self) -> u32 {
        (self.opcode as u32)
            | ((u32::from(self.rd & 0x0F)) << 6)
            | ((u32::from(self.ra & 0x0F)) << 10)
            | ((u32::from(self.rb & 0x0F)) << 14)
            | ((u32::from(self.imm14 & 0x3FFF)) << 18)
    }
}

#[derive(Clone, Debug, PartialEq)]
pub enum Terminator {
    Halt,
    Jump {
        target: u16,
        imm14: u16,
    },
    CondZero {
        reg: u8,
        true_target: u16,
        false_target: u16,
        imm14: u16,
    },
    CondNonZero {
        reg: u8,
        true_target: u16,
        false_target: u16,
        imm14: u16,
    },
    Loop {
        reg: u8,
        body_target: u16,
        exit_target: u16,
        imm14: u16,
    },
    Return,
}

impl Terminator {
    pub fn for_each_target_mut<F>(&mut self, mut apply: F)
    where
        F: FnMut(&mut u16),
    {
        match self {
            Self::Halt | Self::Return => {}
            Self::Jump { target, .. } => apply(target),
            Self::CondZero {
                true_target,
                false_target,
                ..
            }
            | Self::CondNonZero {
                true_target,
                false_target,
                ..
            } => {
                apply(true_target);
                apply(false_target);
            }
            Self::Loop {
                body_target,
                exit_target,
                ..
            } => {
                apply(body_target);
                apply(exit_target);
            }
        }
    }

    pub fn target_count(&self) -> usize {
        match self {
            Self::Halt | Self::Return => 0,
            Self::Jump { .. } => 1,
            Self::CondZero { .. } | Self::CondNonZero { .. } | Self::Loop { .. } => 2,
        }
    }

    pub fn control_reg_mut(&mut self) -> Option<&mut u8> {
        match self {
            Self::CondZero { reg, .. } | Self::CondNonZero { reg, .. } | Self::Loop { reg, .. } => {
                Some(reg)
            }
            Self::Halt | Self::Jump { .. } | Self::Return => None,
        }
    }

    pub fn imm14_mut(&mut self) -> Option<&mut u16> {
        match self {
            Self::Jump { imm14, .. }
            | Self::CondZero { imm14, .. }
            | Self::CondNonZero { imm14, .. }
            | Self::Loop { imm14, .. } => Some(imm14),
            Self::Halt | Self::Return => None,
        }
    }

    pub fn swap_conditional_targets(&mut self) -> bool {
        match self {
            Self::CondZero {
                true_target,
                false_target,
                ..
            }
            | Self::CondNonZero {
                true_target,
                false_target,
                ..
            } => {
                core::mem::swap(true_target, false_target);
                true
            }
            _ => false,
        }
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct Block {
    pub insns: Vec<Instruction>,
    pub term: Terminator,
}

impl Default for Block {
    fn default() -> Self {
        Self {
            insns: Vec::new(),
            term: Terminator::Halt,
        }
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct CandidateCfg {
    pub blocks: Vec<Block>,
    pub entry: u16,
    pub const_pool: [f32; CONST_POOL_WORDS],
    pub regime_profile_bits: u8,
}

impl Default for CandidateCfg {
    fn default() -> Self {
        Self {
            blocks: vec![Block::default()],
            entry: 0,
            const_pool: [0.0; CONST_POOL_WORDS],
            regime_profile_bits: 0,
        }
    }
}

impl CandidateCfg {
    pub fn total_words(&self) -> usize {
        self.blocks.iter().map(|block| block.insns.len() + 1).sum()
    }

    pub fn verify(&self) -> Result<(), VerifyError> {
        if self.blocks.is_empty() {
            return Err(VerifyError::NoBlocks);
        }
        if self.blocks.len() > CAND_MAX_BLOCKS {
            return Err(VerifyError::TooManyBlocks(self.blocks.len()));
        }
        if usize::from(self.entry) >= self.blocks.len() {
            return Err(VerifyError::InvalidEntry {
                entry: usize::from(self.entry),
                block_count: self.blocks.len(),
            });
        }
        if self.regime_profile_bits > 0x0F {
            return Err(VerifyError::InvalidRegimeProfile(self.regime_profile_bits));
        }

        let mut total_words = 0usize;
        let block_count = self.blocks.len();
        for (block_idx, block) in self.blocks.iter().enumerate() {
            if block.insns.len() > BLOCK_MAX_INSNS {
                return Err(VerifyError::BlockTooLarge {
                    block: block_idx,
                    count: block.insns.len(),
                });
            }
            total_words = total_words.saturating_add(block.insns.len() + 1);
            if total_words > CAND_MAX_INSNS {
                return Err(VerifyError::TooManyInstructions(total_words));
            }
            let mut target_error: Option<VerifyError> = None;
            let mut check_target = |target: &mut u16| {
                if usize::from(*target) >= block_count && target_error.is_none() {
                    target_error = Some(VerifyError::InvalidTarget {
                        block: block_idx,
                        target: usize::from(*target),
                        block_count,
                    });
                }
            };
            let mut term = block.term.clone();
            term.for_each_target_mut(&mut check_target);
            if let Some(err) = target_error {
                return Err(err);
            }
        }

        Ok(())
    }

    pub fn to_program_words(&self) -> Vec<u32> {
        let mut starts = Vec::with_capacity(self.blocks.len());
        let mut cursor = 0usize;
        for block in &self.blocks {
            starts.push(cursor);
            cursor += block.insns.len() + 1;
        }

        let mut words = Vec::with_capacity(cursor);
        for (idx, block) in self.blocks.iter().enumerate() {
            for insn in &block.insns {
                words.push(insn.encode_word());
            }
            words.push(encode_terminator(&block.term, idx, &starts, words.len()));
        }
        words
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum VerifyError {
    NoBlocks,
    TooManyBlocks(usize),
    TooManyInstructions(usize),
    BlockTooLarge {
        block: usize,
        count: usize,
    },
    InvalidEntry {
        entry: usize,
        block_count: usize,
    },
    InvalidTarget {
        block: usize,
        target: usize,
        block_count: usize,
    },
    InvalidRegimeProfile(u8),
}

impl fmt::Display for VerifyError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::NoBlocks => write!(f, "candidate has no blocks"),
            Self::TooManyBlocks(count) => write!(f, "candidate has too many blocks: {count}"),
            Self::TooManyInstructions(count) => {
                write!(f, "candidate has too many instruction words: {count}")
            }
            Self::BlockTooLarge { block, count } => {
                write!(f, "block {block} has too many instructions: {count}")
            }
            Self::InvalidEntry { entry, block_count } => {
                write!(f, "entry block {entry} is outside 0..{block_count}")
            }
            Self::InvalidTarget {
                block,
                target,
                block_count,
            } => {
                write!(
                    f,
                    "block {block} has target {target} outside 0..{block_count}"
                )
            }
            Self::InvalidRegimeProfile(value) => {
                write!(f, "regime_profile_bits must be in 0..15, got {value}")
            }
        }
    }
}

impl std::error::Error for VerifyError {}

fn encode_terminator(term: &Terminator, block_idx: usize, starts: &[usize], term_pc: usize) -> u32 {
    let make_rel_imm14 = |target: u16, imm14: u16| -> u16 {
        let Some(target_pc) = starts.get(usize::from(target)).copied() else {
            return imm14 & 0x3FFF;
        };
        let rel = target_pc as isize - term_pc as isize;
        let rel_masked = (rel as i32) & 0x3FFF;
        rel_masked as u16
    };

    let insn = match term {
        Terminator::Halt => Instruction {
            opcode: Opcode::Halt,
            rd: 0,
            ra: 0,
            rb: 0,
            imm14: 0,
        },
        Terminator::Jump { target, imm14 } => Instruction {
            opcode: Opcode::Jmp,
            rd: 0,
            ra: 0,
            rb: 0,
            imm14: make_rel_imm14(*target, *imm14),
        },
        Terminator::CondZero {
            reg,
            true_target,
            false_target,
            imm14,
        } => {
            let fallback = starts
                .get(block_idx.saturating_add(1))
                .copied()
                .unwrap_or(term_pc.saturating_add(1));
            let rel_true = make_rel_imm14(*true_target, *imm14);
            let uses_fallthrough = starts
                .get(usize::from(*false_target))
                .copied()
                .is_some_and(|pc| pc == fallback);
            Instruction {
                opcode: Opcode::Jz,
                rd: 0,
                ra: *reg,
                rb: u8::from(!uses_fallthrough),
                imm14: rel_true,
            }
        }
        Terminator::CondNonZero {
            reg,
            true_target,
            false_target,
            imm14,
        } => {
            let fallback = starts
                .get(block_idx.saturating_add(1))
                .copied()
                .unwrap_or(term_pc.saturating_add(1));
            let rel_true = make_rel_imm14(*true_target, *imm14);
            let uses_fallthrough = starts
                .get(usize::from(*false_target))
                .copied()
                .is_some_and(|pc| pc == fallback);
            Instruction {
                opcode: Opcode::Jnz,
                rd: 0,
                ra: *reg,
                rb: u8::from(!uses_fallthrough),
                imm14: rel_true,
            }
        }
        Terminator::Loop {
            reg,
            body_target,
            imm14,
            ..
        } => Instruction {
            opcode: Opcode::Loop,
            rd: 0,
            ra: *reg,
            rb: 0,
            imm14: make_rel_imm14(*body_target, *imm14),
        },
        Terminator::Return => Instruction {
            opcode: Opcode::Ret,
            rd: 0,
            ra: 0,
            rb: 0,
            imm14: 0,
        },
    };
    insn.encode_word()
}
