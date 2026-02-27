#[cfg(target_os = "macos")]
#[link(name = "Accelerate", kind = "framework")]
extern "C" {
    fn vDSP_vadd(
        a: *const f32,
        ia: isize,
        b: *const f32,
        ib: isize,
        c: *mut f32,
        ic: isize,
        n: usize,
    );
    fn vDSP_vmul(
        a: *const f32,
        ia: isize,
        b: *const f32,
        ib: isize,
        c: *mut f32,
        ic: isize,
        n: usize,
    );
    fn vDSP_vma(
        a: *const f32,
        ia: isize,
        b: *const f32,
        ib: isize,
        c: *const f32,
        ic: isize,
        d: *mut f32,
        id: isize,
        n: usize,
    );
    fn cblas_sdot(n: i32, x: *const f32, incx: i32, y: *const f32, incy: i32) -> f32;
    fn cblas_cdotc_sub(
        n: i32,
        x: *const libc::c_void,
        incx: i32,
        y: *const libc::c_void,
        incy: i32,
        dotc: *mut libc::c_void,
    );
}

/// # Safety
///
/// `dst`, `x`, and `y` must be valid for `len` contiguous `f32` elements.
/// The destination region must not overlap immutable source regions in an
/// unsupported way for the backend routine.
#[inline]
pub unsafe fn vadd(dst: *mut f32, x: *const f32, y: *const f32, len: usize) {
    #[cfg(target_os = "macos")]
    {
        vDSP_vadd(x, 1, y, 1, dst, 1, len);
    }
    #[cfg(not(target_os = "macos"))]
    {
        let _ = (dst, x, y, len);
    }
}

/// # Safety
///
/// `dst`, `x`, and `y` must be valid for `len` contiguous `f32` elements.
/// The destination region must not overlap immutable source regions in an
/// unsupported way for the backend routine.
#[inline]
pub unsafe fn vmul(dst: *mut f32, x: *const f32, y: *const f32, len: usize) {
    #[cfg(target_os = "macos")]
    {
        vDSP_vmul(x, 1, y, 1, dst, 1, len);
    }
    #[cfg(not(target_os = "macos"))]
    {
        let _ = (dst, x, y, len);
    }
}

/// # Safety
///
/// `dst`, `x`, and `y` must be valid for `len` contiguous `f32` elements.
/// The destination region must not overlap immutable source regions in an
/// unsupported way for the backend routine.
#[inline]
pub unsafe fn vfma(dst: *mut f32, x: *const f32, y: *const f32, len: usize) {
    #[cfg(target_os = "macos")]
    {
        vDSP_vma(x, 1, y, 1, dst, 1, dst, 1, len);
    }
    #[cfg(not(target_os = "macos"))]
    {
        let _ = (dst, x, y, len);
    }
}

/// # Safety
///
/// `x` and `y` must be valid for `len` contiguous `f32` elements.
#[inline]
pub unsafe fn dot(x: *const f32, y: *const f32, len: usize) -> f32 {
    #[cfg(target_os = "macos")]
    {
        if let Ok(n) = i32::try_from(len) {
            return cblas_sdot(n, x, 1, y, 1);
        }
    }
    #[cfg(not(target_os = "macos"))]
    {
        let _ = (x, y, len);
    }
    0.0
}

/// # Safety
///
/// `x` and `y` must point to interleaved complex arrays of length `len_c`
/// complex values (`2 * len_c` underlying `f32` elements).
#[inline]
pub unsafe fn cdotc_interleaved(x: *const f32, y: *const f32, len_c: usize) -> (f32, f32) {
    #[cfg(target_os = "macos")]
    {
        if let Ok(n) = i32::try_from(len_c) {
            let mut out = [0.0f32; 2];
            cblas_cdotc_sub(
                n,
                x.cast::<libc::c_void>(),
                1,
                y.cast::<libc::c_void>(),
                1,
                out.as_mut_ptr().cast::<libc::c_void>(),
            );
            return (out[0], out[1]);
        }
    }
    #[cfg(not(target_os = "macos"))]
    {
        let _ = (x, y, len_c);
    }
    (0.0, 0.0)
}
