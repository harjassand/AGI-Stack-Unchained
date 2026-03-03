use serde::{Deserialize, Serialize};

// Phase 3 SCIR-v2 program surface is owned by `types.rs`; we re-export the
// model here so the `scir::ast` module remains the single language entrypoint.
pub use crate::apfsc::types::{
    AdaptHook, BoundSpec, ChannelDef, CoreBlock, CoreOp, MacroCall, ReadoutDef, ScheduleDef,
    ScirV2Program, StateSchema,
};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum ScirV2Primitive {
    LinearMix,
    AffineBias,
    ElementwiseGate,
    StateUpdate,
    ScanReduce,
    SlotRead,
    SlotWrite,
    EventMask,
    ResetIf,
    HeadReadout,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Default)]
pub struct AlienMutationVector {
    #[serde(default)]
    pub ops_added: Vec<String>,
    #[serde(default)]
    pub ops_removed: Vec<String>,
}

impl AlienMutationVector {
    pub fn effective_fused_ops(&self, fallback_hint: u32) -> u32 {
        let structural = self.ops_added.len().saturating_add(self.ops_removed.len()) as u32;
        structural.max(fallback_hint).max(1)
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum ScirOp {
    ByteEmbedding {
        vocab: u32,
        dim: u32,
    },
    LagBytes {
        lags: Vec<u32>,
    },
    Linear {
        in_dim: u32,
        out_dim: u32,
        bias: bool,
    },
    Add,
    Mul,
    Tanh,
    Sigmoid,
    Relu,
    Concat,
    ReduceMean,
    ReduceSum,
    ShiftRegister {
        width: u32,
    },
    RunLengthBucket {
        buckets: u32,
    },
    ModCounter {
        modulus: u32,
    },
    RollingHash {
        n: u32,
        buckets: u32,
    },
    DelimiterReset {
        byte: u8,
    },
    HdcBind,
    HdcBundle,
    HdcPermute {
        shift: u32,
    },
    HdcThreshold {
        threshold: f32,
    },
    SparseEventQueue {
        slots: u32,
    },
    SparseRouter {
        experts: u32,
        topk: u32,
    },
    SymbolicStack {
        depth: u32,
    },
    SymbolicTape {
        cells: u32,
    },
    AfferentNode {
        channel: u8,
    },
    EctodermPrimitive {
        channel: u8,
    },
    Subcortex {
        #[serde(alias = "hash")]
        prior_hash: String,
        #[serde(default)]
        eigen_modulator_vector: Vec<f32>,
    },
    Alien {
        #[serde(alias = "hash")]
        seed_hash: String,
        #[serde(default)]
        mutation_vector: AlienMutationVector,
        // Legacy compatibility: old snapshots may carry `fused_ops`. We keep parsing it,
        // but avoid serializing opaque fused structure back into the genome artifact.
        #[serde(default, alias = "fused_ops", skip_serializing)]
        fused_ops_hint: u32,
    },
    AlephZero {
        recursion_depth: u32,
    },
    SimpleScan {
        in_dim: u32,
        hidden_dim: u32,
    },
    ReadoutNative {
        in_dim: u32,
    },
    ReadoutShadow {
        in_dim: u32,
        head_ix: u32,
    },
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ScirNode {
    pub id: u32,
    pub op: ScirOp,
    pub inputs: Vec<u32>,
    pub out_dim: u32,
    pub mutable: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ProgramOutputs {
    pub feature_node: u32,
    pub shadow_feature_nodes: Vec<u32>,
    pub probe_nodes: Vec<u32>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ScirBounds {
    pub max_state_bytes: u64,
    pub max_param_bits: u64,
    pub max_steps: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ScirProgram {
    pub input_len: u32,
    pub nodes: Vec<ScirNode>,
    pub outputs: ProgramOutputs,
    pub bounds: ScirBounds,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct InterpTrace {
    pub feature: Vec<f32>,
    pub shadows: Vec<Vec<f32>>,
    pub probes: Vec<Vec<f32>>,
}
