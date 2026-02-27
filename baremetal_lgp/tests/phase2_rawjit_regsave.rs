#![cfg(all(target_os = "macos", target_arch = "aarch64"))]

use std::ffi::c_void;

use baremetal_lgp::jit2::abi::RuntimeState;
use baremetal_lgp::jit2::ffi::{self, TrapInfo};

unsafe extern "C" {
    fn jit_test_snapshot_regs(out_gpr11: *mut u64, out_q8_q15_bytes: *mut u8);
    fn jit_test_clobber_entry(runtime_state_ptr: *mut c_void);
    fn jit_test_clobber_and_trap_entry(runtime_state_ptr: *mut c_void);
}

fn snapshot_regs() -> ([u64; 11], [u8; 128]) {
    let mut gpr = [0_u64; 11];
    let mut q = [0_u8; 128];

    // SAFETY: output buffers are valid and sized exactly for x19-x29 and q8-q15.
    unsafe { jit_test_snapshot_regs(gpr.as_mut_ptr(), q.as_mut_ptr()) };

    (gpr, q)
}

#[test]
fn phase2_rawjit_regsave_restores_across_success_and_trap() {
    // SAFETY: initializes per-thread trap and signal state.
    unsafe { ffi::jit_trap_thread_init() };

    let mut state = RuntimeState::default();

    let (gpr_before, q_before) = snapshot_regs();

    let mut trap = TrapInfo::default();
    // SAFETY: clobber entry has C ABI and accepts runtime state pointer.
    let rc = unsafe {
        ffi::run_jit_candidate(
            jit_test_clobber_entry,
            (&mut state as *mut RuntimeState).cast::<c_void>(),
            &mut trap as *mut TrapInfo,
        )
    };
    assert_eq!(rc, 0, "unexpected trap on success path: {:?}", trap);

    let (gpr_after_success, q_after_success) = snapshot_regs();
    assert_eq!(gpr_after_success, gpr_before);
    assert_eq!(q_after_success, q_before);

    trap = TrapInfo::default();
    // SAFETY: entry intentionally traps after clobbering callee-saved regs.
    let rc_trap = unsafe {
        ffi::run_jit_candidate(
            jit_test_clobber_and_trap_entry,
            (&mut state as *mut RuntimeState).cast::<c_void>(),
            &mut trap as *mut TrapInfo,
        )
    };
    assert_ne!(rc_trap, 0);
    assert_eq!(trap.kind, 1);

    let (gpr_after_trap, q_after_trap) = snapshot_regs();
    assert_eq!(gpr_after_trap, gpr_before);
    assert_eq!(q_after_trap, q_before);
}
