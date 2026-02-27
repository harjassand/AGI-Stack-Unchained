use smallvec::SmallVec;

pub const TRACE_SNAPSHOT_STRIDE: u32 = 64;
pub const TRACE_MAX_SNAPSHOTS: usize = 8;

#[derive(Clone, Debug, Default)]
pub struct TraceState {
    pub block_counts: Vec<u32>,
    pub snapshot_stride: u32,
    pub snapshots: SmallVec<[RegSnapshot; 8]>,
    pub steps: u32,
}

#[derive(Clone, Debug)]
pub struct RegSnapshot {
    pub step: u32,
    pub f: [f32; 16],
    pub i: [i32; 16],
}

impl TraceState {
    pub fn new(block_count: usize) -> Self {
        Self {
            block_counts: vec![0; block_count],
            snapshot_stride: TRACE_SNAPSHOT_STRIDE,
            snapshots: SmallVec::new(),
            steps: 0,
        }
    }
}
