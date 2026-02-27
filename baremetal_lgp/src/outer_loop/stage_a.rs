use std::ffi::{c_void, CStr, CString};
use std::os::unix::ffi::OsStrExt;
use std::path::Path;
use std::sync::Arc;

use parking_lot::RwLock;

pub type FastFn = extern "C" fn(f32) -> f32;

#[derive(Clone, Copy, Debug)]
pub struct NonLinearDispatch {
    pub fast_tanh: FastFn,
    pub fast_sigm: FastFn,
}

impl Default for NonLinearDispatch {
    fn default() -> Self {
        Self {
            fast_tanh: default_fast_tanh,
            fast_sigm: default_fast_sigm,
        }
    }
}

#[derive(Debug)]
pub struct StageAModule {
    handle: *mut c_void,
    dispatch: NonLinearDispatch,
}

unsafe impl Send for StageAModule {}
unsafe impl Sync for StageAModule {}

impl Drop for StageAModule {
    fn drop(&mut self) {
        if !self.handle.is_null() {
            // SAFETY: `handle` comes from `dlopen` and is released once here.
            let _ = unsafe { libc::dlclose(self.handle) };
        }
    }
}

#[derive(Debug)]
pub struct StageARegistry {
    active: Arc<RwLock<NonLinearDispatch>>,
    loaded: Option<StageAModule>,
}

#[derive(Debug)]
pub enum StageAError {
    InvalidPath,
    OpenFailed(String),
    MissingSymbol(&'static str, String),
}

impl StageARegistry {
    pub fn new() -> Self {
        Self {
            active: Arc::new(RwLock::new(NonLinearDispatch::default())),
            loaded: None,
        }
    }

    pub fn active_dispatch(&self) -> NonLinearDispatch {
        *self.active.read()
    }

    pub fn load_module(path: impl AsRef<Path>) -> Result<StageAModule, StageAError> {
        let bytes = path.as_ref().as_os_str().as_bytes();
        let c_path = CString::new(bytes).map_err(|_| StageAError::InvalidPath)?;
        // SAFETY: `c_path` is NUL-terminated and valid for the duration of call.
        let handle = unsafe { libc::dlopen(c_path.as_ptr(), libc::RTLD_NOW | libc::RTLD_LOCAL) };
        if handle.is_null() {
            return Err(StageAError::OpenFailed(dl_error_message()));
        }

        // SAFETY: Symbol name is valid C string; handle was returned by dlopen.
        let tanh_ptr = unsafe { libc::dlsym(handle, c"fast_tanh".as_ptr()) };
        if tanh_ptr.is_null() {
            // SAFETY: handle is valid and must be released on failure.
            let _ = unsafe { libc::dlclose(handle) };
            return Err(StageAError::MissingSymbol("fast_tanh", dl_error_message()));
        }

        // SAFETY: Symbol name is valid C string; handle was returned by dlopen.
        let sigm_ptr = unsafe { libc::dlsym(handle, c"fast_sigm".as_ptr()) };
        if sigm_ptr.is_null() {
            // SAFETY: handle is valid and must be released on failure.
            let _ = unsafe { libc::dlclose(handle) };
            return Err(StageAError::MissingSymbol("fast_sigm", dl_error_message()));
        }

        // SAFETY: The module contract requires these symbols to have FastFn signature.
        let fast_tanh: FastFn = unsafe { std::mem::transmute(tanh_ptr) };
        // SAFETY: The module contract requires these symbols to have FastFn signature.
        let fast_sigm: FastFn = unsafe { std::mem::transmute(sigm_ptr) };

        Ok(StageAModule {
            handle,
            dispatch: NonLinearDispatch {
                fast_tanh,
                fast_sigm,
            },
        })
    }

    pub fn promote_if_shadow_passes<F>(
        &mut self,
        module: StageAModule,
        mut wins_per_hour: F,
    ) -> bool
    where
        F: FnMut(NonLinearDispatch, u32) -> f32,
    {
        let baseline = wins_per_hour(self.active_dispatch(), 256);
        let candidate = wins_per_hour(module.dispatch, 256);
        if candidate > baseline {
            *self.active.write() = module.dispatch;
            self.loaded = Some(module);
            return true;
        }
        false
    }
}

impl Default for StageARegistry {
    fn default() -> Self {
        Self::new()
    }
}

extern "C" fn default_fast_tanh(x: f32) -> f32 {
    x.tanh()
}

extern "C" fn default_fast_sigm(x: f32) -> f32 {
    1.0 / (1.0 + (-x).exp())
}

fn dl_error_message() -> String {
    // SAFETY: dlerror returns either null or a valid C string pointer owned by libc.
    let ptr = unsafe { libc::dlerror() };
    if ptr.is_null() {
        return "unknown dlerror".to_string();
    }
    // SAFETY: pointer comes from dlerror and points to NUL-terminated string.
    unsafe { CStr::from_ptr(ptr) }
        .to_string_lossy()
        .into_owned()
}
