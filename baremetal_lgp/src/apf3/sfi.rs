use core::ptr;

#[derive(Clone, Copy, Debug)]
pub struct SfiLayout {
    pub window_size: usize,
    pub stack_size: usize,
    pub state_size: usize,
    pub heap_size: usize,
}

pub struct SfiContext {
    pub base: *mut u8,
    pub layout: SfiLayout,
    pub stack_lo: *mut u8,
    pub stack_hi: *mut u8,
    pub state: *mut u8,
    pub heap: *mut u8,
    heap_cur: usize,
    heap_end: usize,
}

impl SfiContext {
    pub fn new(layout: SfiLayout) -> Result<Self, String> {
        if layout.window_size == 0 || layout.stack_size == 0 {
            return Err("invalid SFI layout: zero-sized region".to_string());
        }

        let needed = layout
            .stack_size
            .checked_add(layout.state_size)
            .and_then(|v| v.checked_add(layout.heap_size))
            .ok_or_else(|| "SFI layout overflow".to_string())?;
        if needed > layout.window_size {
            return Err("SFI layout exceeds reserved window".to_string());
        }

        let page = page_size();
        let window_size = align_up(layout.window_size, page);

        let map_flags = libc::MAP_PRIVATE | map_anon_flag();

        // SAFETY: mmap is called with validated size and null hint address.
        let base = unsafe {
            libc::mmap(
                ptr::null_mut(),
                window_size,
                libc::PROT_NONE,
                map_flags,
                -1,
                0,
            )
        };
        if base == libc::MAP_FAILED {
            return Err("failed to reserve SFI window".to_string());
        }

        let base = base.cast::<u8>();

        let stack_size = align_up(layout.stack_size, page);
        let state_size = align_up(layout.state_size.max(1), page);
        let heap_size = align_up(layout.heap_size.max(1), page);

        let stack_lo = base;
        let state = unsafe { base.add(stack_size) };
        let heap = unsafe { state.add(state_size) };

        map_rw_fixed(stack_lo, stack_size)?;
        map_rw_fixed(state, state_size)?;
        map_rw_fixed(heap, heap_size)?;

        let stack_hi = unsafe { stack_lo.add(stack_size) };
        let heap_cur = heap as usize;
        let heap_end = heap_cur.saturating_add(heap_size);

        Ok(Self {
            base,
            layout: SfiLayout {
                window_size,
                stack_size,
                state_size,
                heap_size,
            },
            stack_lo,
            stack_hi,
            state,
            heap,
            heap_cur,
            heap_end,
        })
    }

    pub fn alloc_heap(&mut self, size: usize, align: usize) -> *mut u8 {
        if size == 0 {
            return self.heap;
        }

        let align = align.max(1).next_power_of_two();
        let mask = align - 1;
        let aligned = (self.heap_cur + mask) & !mask;
        let end = match aligned.checked_add(size) {
            Some(v) => v,
            None => return ptr::null_mut(),
        };
        if end > self.heap_end {
            return ptr::null_mut();
        }
        self.heap_cur = end;
        aligned as *mut u8
    }

    pub fn stack_ptr_top(&self) -> *mut u8 {
        let top = (self.stack_hi as usize) & !0xF;
        top.saturating_sub(16) as *mut u8
    }

    pub fn contains_range(&self, ptr: *const u8, len: usize) -> bool {
        let start = ptr as usize;
        let end = match start.checked_add(len) {
            Some(v) => v,
            None => return false,
        };
        let base = self.base as usize;
        let limit = base.saturating_add(self.layout.window_size);
        start >= base && end <= limit
    }
}

impl Drop for SfiContext {
    fn drop(&mut self) {
        if !self.base.is_null() && self.layout.window_size != 0 {
            // SAFETY: mapping was created by mmap in SfiContext::new.
            unsafe {
                let _ = libc::munmap(self.base.cast::<libc::c_void>(), self.layout.window_size);
            }
        }
    }
}

fn map_rw_fixed(addr: *mut u8, len: usize) -> Result<(), String> {
    let flags = libc::MAP_PRIVATE | map_anon_flag() | libc::MAP_FIXED;
    // SAFETY: fixed-address subregion lies fully in previously reserved mapping.
    let mapped = unsafe {
        libc::mmap(
            addr.cast::<libc::c_void>(),
            len,
            libc::PROT_READ | libc::PROT_WRITE,
            flags,
            -1,
            0,
        )
    };
    if mapped == libc::MAP_FAILED || mapped.cast::<u8>() != addr {
        return Err("failed to map SFI subregion".to_string());
    }
    Ok(())
}

fn map_anon_flag() -> libc::c_int {
    #[cfg(any(
        target_os = "macos",
        target_os = "ios",
        target_os = "freebsd",
        target_os = "openbsd",
        target_os = "netbsd"
    ))]
    {
        libc::MAP_ANON
    }

    #[cfg(not(any(
        target_os = "macos",
        target_os = "ios",
        target_os = "freebsd",
        target_os = "openbsd",
        target_os = "netbsd"
    )))]
    {
        libc::MAP_ANONYMOUS
    }
}

fn page_size() -> usize {
    // SAFETY: sysconf call has no side-effects.
    let raw = unsafe { libc::sysconf(libc::_SC_PAGESIZE) };
    if raw <= 0 {
        4096
    } else {
        raw as usize
    }
}

fn align_up(value: usize, align: usize) -> usize {
    if align == 0 {
        return value;
    }
    let rem = value % align;
    if rem == 0 {
        value
    } else {
        value + (align - rem)
    }
}

#[cfg(test)]
mod tests {
    use super::{SfiContext, SfiLayout};

    #[test]
    fn sfi_alloc_heap_alignment_and_bounds() {
        let mut sfi = SfiContext::new(SfiLayout {
            window_size: 1 << 24,
            stack_size: 1 << 20,
            state_size: 1 << 20,
            heap_size: 1 << 20,
        })
        .expect("sfi create");

        let p1 = sfi.alloc_heap(13, 8);
        assert!(!p1.is_null());
        assert_eq!((p1 as usize) % 8, 0);
        assert!(sfi.contains_range(p1.cast::<u8>(), 13));

        let p2 = sfi.alloc_heap(32, 64);
        assert!(!p2.is_null());
        assert_eq!((p2 as usize) % 64, 0);
        assert!(sfi.contains_range(p2.cast::<u8>(), 32));

        let too_big = sfi.alloc_heap(1 << 30, 16);
        assert!(too_big.is_null());
    }
}
