#[derive(Copy, Clone, Debug, PartialEq, Eq, Hash)]
pub struct BlockId(pub u16);

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct BasicBlock {
    pub id: BlockId,
    pub insns: Vec<u32>,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct CandidateCfg {
    pub entry: BlockId,
    pub blocks: Vec<BasicBlock>,
}
