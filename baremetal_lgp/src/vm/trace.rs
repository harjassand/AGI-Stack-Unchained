#[cfg(feature = "trace")]
#[derive(Clone, Debug, Default)]
pub struct TraceState {
    pub pcs: Vec<u32>,
    pub opcodes: Vec<u8>,
}
