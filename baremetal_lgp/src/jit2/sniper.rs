use std::sync::atomic::{AtomicU32, AtomicU64, Ordering::Relaxed};

use super::ffi;

#[repr(align(64))]
pub struct WorkerWatch {
    pub progress: AtomicU64, // increments before each candidate call
    pub armed: AtomicU32,    // 1 while executing candidate, 0 otherwise
}

impl WorkerWatch {
    pub fn new() -> Self {
        Self {
            progress: AtomicU64::new(0),
            armed: AtomicU32::new(0),
        }
    }

    #[inline(always)]
    pub fn arm_for_candidate(&self) {
        self.armed.store(1, Relaxed);
        self.progress.fetch_add(1, Relaxed);
    }

    #[inline(always)]
    pub fn disarm_after_candidate(&self) {
        self.armed.store(0, Relaxed);
    }
}

pub fn start_once(max_stall_us: u64) {
    // SAFETY: starts an internal singleton thread; idempotent in C layer.
    unsafe { ffi::sniper_start_once(max_stall_us) };
}

pub fn register_worker(watch: &WorkerWatch) {
    // SAFETY: pointers point to process-lived atomics owned by the worker.
    unsafe {
        ffi::sniper_register_worker(
            libc::pthread_self(),
            watch.progress.as_ptr(),
            watch.armed.as_ptr(),
        )
    };
}

impl Default for WorkerWatch {
    fn default() -> Self {
        Self::new()
    }
}
