use std::ffi::c_void;

#[repr(C)]
#[derive(Clone, Copy, Debug, Default)]
pub struct TrapInfo {
    pub kind: u32,
    pub sig: u32,
    pub fault_pc: u64,
    pub fault_addr: u64,
}

pub type JitEntry = unsafe extern "C" fn(*mut c_void);
pub type JitEntryI32 = unsafe extern "C" fn(*mut c_void) -> i32;

unsafe extern "C" {
    pub fn jit_trap_thread_init();
    pub fn run_jit_candidate(
        entry: JitEntry,
        runtime_state_ptr: *mut c_void,
        out_trap: *mut TrapInfo,
    ) -> libc::c_int;
    pub fn run_jit_candidate_i32_on_stack(
        entry: JitEntryI32,
        runtime_state_ptr: *mut c_void,
        stack_top: *mut c_void,
        out_trap: *mut TrapInfo,
        out_status: *mut i32,
    ) -> libc::c_int;

    pub fn sniper_start_once(max_stall_us: u64);
    pub fn sniper_register_worker(
        tid: libc::pthread_t,
        progress_ptr: *mut u64,
        armed_ptr: *mut u32,
    );
}

#[cfg(all(target_os = "macos", target_arch = "aarch64"))]
unsafe extern "C" {
    fn pthread_jit_write_protect_np(enabled: libc::c_int);
    fn sys_icache_invalidate(start: *const c_void, len: usize);
}

#[inline(always)]
pub unsafe fn jit_write_protect(protection_enabled: bool) {
    #[cfg(all(target_os = "macos", target_arch = "aarch64"))]
    {
        // SAFETY: caller upholds MAP_JIT write-protect protocol boundaries.
        unsafe { pthread_jit_write_protect_np(if protection_enabled { 1 } else { 0 }) };
    }

    #[cfg(not(all(target_os = "macos", target_arch = "aarch64")))]
    {
        let _ = protection_enabled;
    }
}

#[inline(always)]
pub unsafe fn jit_icache_invalidate(start: *const u8, len: usize) {
    #[cfg(all(target_os = "macos", target_arch = "aarch64"))]
    {
        // SAFETY: caller passes a valid executable memory range.
        unsafe { sys_icache_invalidate(start.cast::<c_void>(), len) };
    }

    #[cfg(not(all(target_os = "macos", target_arch = "aarch64")))]
    {
        let _ = (start, len);
    }
}
