use crate::vm::worker::{StopReason, VmWorker};

pub fn charge(worker: &mut VmWorker, cost: u32) -> bool {
    if worker.fuel < cost {
        worker.halted = true;
        worker.stop_reason = StopReason::FuelExhausted;
        return false;
    }
    worker.fuel -= cost;
    true
}

pub fn halt(worker: &mut VmWorker) {
    worker.halted = true;
    worker.stop_reason = StopReason::Halt;
}
