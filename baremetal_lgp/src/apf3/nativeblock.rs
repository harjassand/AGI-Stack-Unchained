use std::collections::HashMap;
use std::ffi::c_void;
use std::mem;

use serde::{Deserialize, Serialize};

use crate::apf3::a64_scan;
use crate::apf3::digest::{Digest32, DigestBuilder};
use crate::apf3::sfi::SfiContext;
use crate::jit2::arena::JitArena;
use crate::jit2::ffi::{self, JitEntryI32, TrapInfo};
use crate::jit2::raw_runner::TRAP_SIGALRM;
use crate::jit2::sniper::{self, WorkerWatch};

#[derive(Clone, Serialize, Deserialize)]
pub struct NativeBlockSpec {
    pub words: Vec<u32>,
    pub declared_stack: u32,
}

impl NativeBlockSpec {
    pub fn digest(&self) -> Digest32 {
        let mut b = DigestBuilder::new(b"APF3_NATIVEBLOCK_V1");
        b.u32(self.words.len() as u32);
        for &w in &self.words {
            b.u32(w);
        }
        b.finish()
    }
}

#[repr(C)]
pub struct NativeCtx {
    pub phase: u32,
    pub fuel_left: u64,
    pub state_ptr: *mut u8,
    pub state_len: u32,
    pub heap_ptr: *mut u8,
    pub heap_len: u32,
    pub in_ptr: *const f32,
    pub out_ptr: *mut f32,
    pub len: u32,
    pub reserved: u32,
}

#[derive(Debug)]
pub enum NativeBlockInstallError {
    Scan(a64_scan::ScanError),
    InvalidSpec(&'static str),
    Arena(String),
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum NativeExecError {
    MissingBlock,
    PointerEscape,
    Fault { trap_kind: u32 },
    Timeout,
}

pub struct NativeSandbox {
    watch: &'static WorkerWatch,
}

impl NativeSandbox {
    pub fn new(max_stall_us: u64) -> Self {
        // SAFETY: initializes thread-local trap handlers and stacks.
        unsafe {
            ffi::jit_trap_thread_init();
        }
        sniper::start_once(max_stall_us.max(1));
        let watch = Box::leak(Box::new(WorkerWatch::new()));
        sniper::register_worker(watch);
        Self { watch }
    }

    pub fn watch(&self) -> &WorkerWatch {
        self.watch
    }
}

struct InstalledNativeBlock {
    code_ptr: *mut u8,
    _arena: JitArena,
}

pub struct NativeBlockRegistry {
    blocks: HashMap<Digest32, InstalledNativeBlock>,
}

impl NativeBlockRegistry {
    pub fn new() -> Self {
        Self {
            blocks: HashMap::new(),
        }
    }

    pub fn install(&mut self, spec: &NativeBlockSpec) -> Result<Digest32, NativeBlockInstallError> {
        if spec.words.is_empty() {
            return Err(NativeBlockInstallError::InvalidSpec("empty native block"));
        }

        a64_scan::scan_block(&spec.words).map_err(NativeBlockInstallError::Scan)?;

        let digest = spec.digest();
        if self.blocks.contains_key(&digest) {
            return Ok(digest);
        }

        // Install order:
        // 1) scan already completed above
        // 2) allocate executable slot via phase-2 JIT arena
        // 3) copy words into slot
        // 4) restore execute protections (handled by arena write-protect protocol)
        // 5) I-cache invalidate (handled by arena)
        // 6) register digest -> installed block
        let mut arena = JitArena::new().map_err(NativeBlockInstallError::Arena)?;
        arena
            .install_active(&spec.words)
            .map_err(NativeBlockInstallError::Arena)?;
        let code_ptr = arena.active_slot_ptr();

        self.blocks.insert(
            digest,
            InstalledNativeBlock {
                code_ptr,
                _arena: arena,
            },
        );

        Ok(digest)
    }

    pub fn contains(&self, digest: Digest32) -> bool {
        self.blocks.contains_key(&digest)
    }

    pub fn execute(
        &self,
        digest: Digest32,
        native_ctx: *mut NativeCtx,
        sfi: &SfiContext,
        sandbox: &NativeSandbox,
    ) -> Result<i32, NativeExecError> {
        let block = self
            .blocks
            .get(&digest)
            .ok_or(NativeExecError::MissingBlock)?;

        if !sfi.contains_range(native_ctx.cast::<u8>(), mem::size_of::<NativeCtx>()) {
            return Err(NativeExecError::PointerEscape);
        }

        // SAFETY: native_ctx range is validated to lie within SFI window.
        let ctx = unsafe { &*native_ctx };
        if !sfi.contains_range(ctx.state_ptr.cast::<u8>(), ctx.state_len as usize) {
            return Err(NativeExecError::PointerEscape);
        }
        if !sfi.contains_range(ctx.heap_ptr.cast::<u8>(), ctx.heap_len as usize) {
            return Err(NativeExecError::PointerEscape);
        }
        let in_len = (ctx.len as usize)
            .checked_mul(mem::size_of::<f32>())
            .ok_or(NativeExecError::PointerEscape)?;
        if !sfi.contains_range(ctx.in_ptr.cast::<u8>(), in_len) {
            return Err(NativeExecError::PointerEscape);
        }
        if !sfi.contains_range(ctx.out_ptr.cast::<u8>(), in_len) {
            return Err(NativeExecError::PointerEscape);
        }

        let mut trap = TrapInfo::default();
        let mut status: i32 = 0;
        sandbox.watch().arm_for_candidate();
        // SAFETY: code_ptr points to executable AArch64 words with expected ABI.
        let rc = unsafe {
            let entry: JitEntryI32 = mem::transmute::<*mut u8, JitEntryI32>(block.code_ptr);
            ffi::run_jit_candidate_i32_on_stack(
                entry,
                native_ctx.cast::<c_void>(),
                sfi.stack_ptr_top().cast::<c_void>(),
                &mut trap as *mut TrapInfo,
                &mut status as *mut i32,
            )
        };
        sandbox.watch().disarm_after_candidate();

        if rc != 0 {
            if trap.kind == TRAP_SIGALRM {
                return Err(NativeExecError::Timeout);
            }
            return Err(NativeExecError::Fault {
                trap_kind: trap.kind,
            });
        }

        Ok(status)
    }
}

impl Default for NativeBlockRegistry {
    fn default() -> Self {
        Self::new()
    }
}
