pub type BlockId = u16;

#[derive(Clone)]
pub struct CandidateCfg {
    pub const_pool: [f32; crate::abi::CONST_POOL_WORDS],
    pub blocks: Vec<Block>,
    pub entry: BlockId,
}

#[derive(Clone)]
pub struct Block {
    pub id: BlockId,
    pub instrs: Vec<Instr>,
    pub term: Terminator,
}

#[derive(Clone, Copy)]
pub struct Instr {
    pub op: crate::isa::op::Op,
    pub rd: u8,
    pub ra: u8,
    pub rb: u8,
    pub imm14: u16,
}

#[derive(Clone)]
pub enum Terminator {
    Halt,
    Jmp {
        target: BlockId,
    },
    Jz {
        cond: u8,
        t: BlockId,
        f: BlockId,
    },
    Jnz {
        cond: u8,
        t: BlockId,
        f: BlockId,
    },
    Loop {
        counter: u8,
        body: BlockId,
        exit: BlockId,
    },
    Call {
        target: BlockId,
        ret: BlockId,
    },
    Ret,
    CallLib {
        slot: u8,
        ret: BlockId,
    },
}
