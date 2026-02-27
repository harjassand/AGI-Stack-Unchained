#[derive(Debug)]
pub struct JitBuf {
    pub ptr: *mut u8,
    pub len: usize,
}

#[cfg(all(feature = "jit", target_os = "macos"))]
extern "C" {
    fn pthread_jit_write_protect_np(enabled: libc::c_int);
    fn sys_icache_invalidate(start: *const libc::c_void, len: usize);
}

#[cfg(all(feature = "jit", target_os = "macos"))]
pub fn jit_alloc(len: usize) -> JitBuf {
    let alloc_len = len.max(1);
    let flags = libc::MAP_PRIVATE | libc::MAP_ANON | 0x0800; // MAP_JIT

    // SAFETY: mmap arguments are valid; checked against MAP_FAILED below.
    let ptr = unsafe {
        libc::mmap(
            core::ptr::null_mut(),
            alloc_len,
            libc::PROT_READ | libc::PROT_WRITE | libc::PROT_EXEC,
            flags,
            -1,
            0,
        )
    };
    assert_ne!(ptr, libc::MAP_FAILED, "mmap(MAP_JIT) failed");

    JitBuf {
        ptr: ptr.cast::<u8>(),
        len: alloc_len,
    }
}

#[cfg(not(all(feature = "jit", target_os = "macos")))]
pub fn jit_alloc(len: usize) -> JitBuf {
    let alloc_len = len.max(1);
    let raw = vec![0u8; alloc_len].into_boxed_slice();
    let leaked = Box::leak(raw);
    JitBuf {
        ptr: leaked.as_mut_ptr(),
        len: alloc_len,
    }
}

/// # Safety
///
/// `bytes.len()` must be less than or equal to `buf.len`. `buf` must point to
/// writable JIT memory returned by `jit_alloc`.
#[cfg(all(feature = "jit", target_os = "macos"))]
pub unsafe fn jit_write(buf: &JitBuf, bytes: &[u8]) {
    assert!(bytes.len() <= buf.len, "jit_write overflow");

    // SAFETY: Apple API requires this toggle around writes into MAP_JIT pages.
    pthread_jit_write_protect_np(0);
    core::ptr::copy_nonoverlapping(bytes.as_ptr(), buf.ptr, bytes.len());
    sys_icache_invalidate(buf.ptr.cast::<libc::c_void>(), buf.len);
    pthread_jit_write_protect_np(1);
}

/// # Safety
///
/// `bytes.len()` must be less than or equal to `buf.len`. `buf` must point to
/// writable memory returned by `jit_alloc`.
#[cfg(not(all(feature = "jit", target_os = "macos")))]
pub unsafe fn jit_write(buf: &JitBuf, bytes: &[u8]) {
    assert!(bytes.len() <= buf.len, "jit_write overflow");
    core::ptr::copy_nonoverlapping(bytes.as_ptr(), buf.ptr, bytes.len());
}

/// # Safety
///
/// `buf.ptr` must point to valid executable code with signature
/// `extern "C" fn(*mut f32, *const f32, *const f32, usize)` and all pointers
/// must be valid for `len` elements.
#[cfg(all(feature = "jit", target_os = "macos"))]
pub unsafe fn jit_exec_vadd(buf: &JitBuf, dst: *mut f32, a: *const f32, b: *const f32, len: usize) {
    type JitFn = unsafe extern "C" fn(*mut f32, *const f32, *const f32, usize);
    let f: JitFn = core::mem::transmute(buf.ptr);
    f(dst, a, b, len);
}

/// # Safety
///
/// `dst`, `a`, and `b` must be valid for `len` contiguous `f32` elements.
#[cfg(not(all(feature = "jit", target_os = "macos")))]
pub unsafe fn jit_exec_vadd(
    _buf: &JitBuf,
    dst: *mut f32,
    a: *const f32,
    b: *const f32,
    len: usize,
) {
    for i in 0..len {
        *dst.add(i) = *a.add(i) + *b.add(i);
    }
}

#[cfg(all(feature = "jit", target_os = "macos"))]
impl Drop for JitBuf {
    fn drop(&mut self) {
        if !self.ptr.is_null() && self.len > 0 {
            // SAFETY: buffer was allocated by mmap in jit_alloc.
            unsafe {
                let _ = libc::munmap(self.ptr.cast::<libc::c_void>(), self.len);
            }
        }
    }
}
