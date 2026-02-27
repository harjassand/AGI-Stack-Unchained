use std::collections::{HashMap, VecDeque};
use std::ffi::c_void;
use std::io;
use std::ptr::NonNull;

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum KernelKind {
    VAdd,
    VMul,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub struct KernelRequest {
    pub kind: KernelKind,
    pub len: u16,
}

pub trait KernelBuilder {
    fn build_kernel(&mut self, request: KernelRequest) -> Option<Vec<u8>>;
}

pub trait ShadowSuite {
    fn run_shadow_suite(&mut self, request: KernelRequest, entry_ptr: *const c_void) -> bool;
}

#[derive(Debug)]
pub struct KernelVersion {
    pub request: KernelRequest,
    pub bytes: Vec<u8>,
    pub wins_per_hour: f32,
    pub exec: ExecutableBuffer,
}

#[derive(Debug)]
pub struct StageCManager {
    pub enabled: HashMap<KernelKind, KernelVersion>,
    history: HashMap<KernelKind, VecDeque<KernelVersion>>,
}

#[derive(Debug)]
pub enum StageCError {
    BuildFailed,
    EmptyKernel,
    MapJit(io::Error),
}

impl StageCManager {
    pub fn new() -> Self {
        Self {
            enabled: HashMap::new(),
            history: HashMap::new(),
        }
    }

    pub fn propose_kernel<B, S>(
        &mut self,
        request: KernelRequest,
        builder: &mut B,
        shadow: &mut S,
        wins_per_hour: f32,
    ) -> Result<bool, StageCError>
    where
        B: KernelBuilder,
        S: ShadowSuite,
    {
        let bytes = builder
            .build_kernel(request)
            .ok_or(StageCError::BuildFailed)?;
        if bytes.is_empty() {
            return Err(StageCError::EmptyKernel);
        }

        let exec = ExecutableBuffer::from_bytes(&bytes).map_err(StageCError::MapJit)?;
        if !shadow.run_shadow_suite(request, exec.as_ptr() as *const c_void) {
            return Ok(false);
        }

        let version = KernelVersion {
            request,
            bytes,
            wins_per_hour,
            exec,
        };

        let regression = self
            .enabled
            .get(&request.kind)
            .is_some_and(|current| wins_per_hour < current.wins_per_hour);
        if regression {
            return Ok(false);
        }

        self.enabled.insert(request.kind, version);
        let history = self.history.entry(request.kind).or_default();
        if let Some(enabled) = self.enabled.get(&request.kind) {
            history.push_back(KernelVersion {
                request: enabled.request,
                bytes: enabled.bytes.clone(),
                wins_per_hour: enabled.wins_per_hour,
                exec: ExecutableBuffer::from_bytes(&enabled.bytes).map_err(StageCError::MapJit)?,
            });
        }
        while history.len() > 3 {
            history.pop_front();
        }
        Ok(true)
    }

    pub fn rollback_last(&mut self, kind: KernelKind) -> bool {
        let Some(history) = self.history.get_mut(&kind) else {
            return false;
        };
        if history.len() <= 1 {
            return false;
        }
        history.pop_back();
        if let Some(previous) = history.back() {
            let Ok(exec) = ExecutableBuffer::from_bytes(&previous.bytes) else {
                return false;
            };
            self.enabled.insert(
                kind,
                KernelVersion {
                    request: previous.request,
                    bytes: previous.bytes.clone(),
                    wins_per_hour: previous.wins_per_hour,
                    exec,
                },
            );
            return true;
        }
        false
    }
}

impl Default for StageCManager {
    fn default() -> Self {
        Self::new()
    }
}

#[derive(Debug)]
pub struct ExecutableBuffer {
    ptr: NonNull<u8>,
    len: usize,
}

impl ExecutableBuffer {
    pub fn from_bytes(bytes: &[u8]) -> io::Result<Self> {
        let len = bytes.len().max(1);
        let map = unsafe {
            libc::mmap(
                std::ptr::null_mut(),
                len,
                libc::PROT_READ | libc::PROT_WRITE | libc::PROT_EXEC,
                libc::MAP_PRIVATE | libc::MAP_ANON | map_jit_flag(),
                -1,
                0,
            )
        };
        if map == libc::MAP_FAILED {
            return Err(io::Error::last_os_error());
        }
        let ptr = NonNull::new(map as *mut u8).ok_or_else(io::Error::last_os_error)?;
        // SAFETY: `ptr` points to valid writable mapping of at least `len` bytes.
        unsafe { std::ptr::copy_nonoverlapping(bytes.as_ptr(), ptr.as_ptr(), bytes.len()) };
        icache_invalidate(ptr.as_ptr() as *const c_void, bytes.len());
        Ok(Self { ptr, len })
    }

    pub fn as_ptr(&self) -> *const u8 {
        self.ptr.as_ptr() as *const u8
    }
}

impl Drop for ExecutableBuffer {
    fn drop(&mut self) {
        let _ = unsafe { libc::munmap(self.ptr.as_ptr() as *mut c_void, self.len) };
    }
}

#[cfg(target_os = "macos")]
fn map_jit_flag() -> i32 {
    libc::MAP_JIT
}

#[cfg(not(target_os = "macos"))]
fn map_jit_flag() -> i32 {
    0
}

#[cfg(target_os = "macos")]
fn icache_invalidate(start: *const c_void, len: usize) {
    unsafe extern "C" {
        fn sys_icache_invalidate(start: *const c_void, len: usize);
    }
    // SAFETY: macOS API invalidates icache for executable pages we just wrote.
    unsafe { sys_icache_invalidate(start, len) };
}

#[cfg(not(target_os = "macos"))]
fn icache_invalidate(_start: *const c_void, _len: usize) {}
