#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub struct CandidateId(pub u64);

#[derive(Clone, Copy, Debug)]
pub enum EvalMode {
    Proxy,     // 2 episodes
    Full,      // 16 episodes
    Stability, // 3 × Full (48 episodes total)
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum StopReason {
    Halt,
    FuelExhausted,
    FaultInvalidOpcode,
    FaultPcOob,
    FaultCallstackOverflow,
    FaultCallstackUnderflow,
    FaultVecWrap,    // vector op range wraps scratch
    FaultVecOob,     // base+len exceeds scratch
    FaultGemmOob,    // gemm range exceeds scratch
    FaultLibMissing, // CALL_LIB to empty slot
}

#[derive(Clone, Copy, Debug)]
pub struct EvalSummary {
    pub score_mean: f32,
    pub score_var: f32,
    pub fuel_used_mean: f32,
    pub stop_reason: StopReason,
    pub family_means: [f32; 4], // order fixed by oracle module
}

#[derive(Clone, Copy, Debug)]
pub struct HotReturn {
    pub id: CandidateId,
    pub score: f32,
    pub fuel_used: u32,
    pub code_size: u32,
}
