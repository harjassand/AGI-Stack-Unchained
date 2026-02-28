use serde::{Deserialize, Serialize};

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
