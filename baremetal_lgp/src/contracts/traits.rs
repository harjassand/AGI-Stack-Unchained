use crate::types::*;
use crate::vm::{VmProgram, VmWorker};
use crate::library::LibraryImage;

pub trait OracleHarness {
    fn eval(&mut self, worker: &mut VmWorker, prog: &VmProgram, mode: EvalMode) -> EvalSummary;
    fn eval_with_trace(
        &mut self,
        worker: &mut VmWorker,
        prog: &VmProgram,
        mode: EvalMode,
        trace: &mut dyn TraceSink,
    ) -> EvalSummary;
}

pub trait TraceSink {
    fn on_block_enter(&mut self, block_id: u16);
    fn on_edge(&mut self, from: u16, to: u16);
    fn on_checkpoint(&mut self, step: u32, f: &[f32; 16], i: &[i32; 16]);
    fn on_finish(&mut self, output: &[f32], score: f32, fuel_used: u32);
}

pub trait SearchEngine {
    fn step(&mut self, oracle: &mut dyn OracleHarness, workers: &mut [VmWorker], lib: &LibraryImage);
}
