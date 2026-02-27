use std::ptr;

use super::constants::{A64_RET, JIT_SLOTS_PER_THREAD, JIT_SLOT_BYTES, RAW_MAX_WORDS};
use super::ffi;

pub struct JitArena {
    base: *mut u8,
    len: usize,
    slot_ptrs: [*mut u8; JIT_SLOTS_PER_THREAD],
    next_slot: usize,
}

impl JitArena {
    pub fn new() -> Result<Self, String> {
        let page = page_size();
        let raw_len = JIT_SLOTS_PER_THREAD
            .checked_mul(JIT_SLOT_BYTES)
            .ok_or_else(|| "jit arena size overflow".to_string())?;
        let len = align_up(raw_len, page);

        #[cfg(all(target_os = "macos", target_arch = "aarch64"))]
        let flags = libc::MAP_PRIVATE | libc::MAP_ANON | 0x0800; // MAP_JIT
        #[cfg(not(all(target_os = "macos", target_arch = "aarch64")))]
        let flags = libc::MAP_PRIVATE | libc::MAP_ANON;

        // SAFETY: mmap arguments are valid and checked against MAP_FAILED.
        let mapped = unsafe {
            libc::mmap(
                ptr::null_mut(),
                len,
                libc::PROT_READ | libc::PROT_WRITE | libc::PROT_EXEC,
                flags,
                -1,
                0,
            )
        };
        if mapped == libc::MAP_FAILED {
            return Err("mmap for jit arena failed".to_string());
        }

        let base = mapped.cast::<u8>();
        let mut slot_ptrs = [ptr::null_mut(); JIT_SLOTS_PER_THREAD];
        for (idx, slot) in slot_ptrs.iter_mut().enumerate() {
            // SAFETY: idx * JIT_SLOT_BYTES is always in-bounds for the mapping.
            *slot = unsafe { base.add(idx * JIT_SLOT_BYTES) };
        }

        let mut arena = Self {
            base,
            len,
            slot_ptrs,
            next_slot: 1,
        };

        for slot_idx in 0..JIT_SLOTS_PER_THREAD {
            let slot = arena.slot_ptrs[slot_idx];
            arena.write_words(slot, &[A64_RET])?;
        }

        Ok(arena)
    }

    #[inline(always)]
    pub fn active_slot_ptr(&self) -> *mut u8 {
        self.slot_ptrs[0]
    }

    #[inline(always)]
    pub fn candidate_slot_ptr(&mut self) -> *mut u8 {
        self.next_slot = 1;
        self.slot_ptrs[self.next_slot]
    }

    pub fn install_active(&mut self, words: &[u32]) -> Result<(), String> {
        self.write_words(self.active_slot_ptr(), words)
    }

    pub fn write_candidate(&mut self, words: &[u32]) -> Result<*mut u8, String> {
        let slot = self.candidate_slot_ptr();
        self.write_words(slot, words)?;
        Ok(slot)
    }

    pub fn write_words(&mut self, slot_ptr: *mut u8, words: &[u32]) -> Result<(), String> {
        if words.is_empty() {
            return Err("raw candidate must contain at least one word".to_string());
        }
        if words.len() > RAW_MAX_WORDS {
            return Err(format!(
                "raw candidate too long: {} > {RAW_MAX_WORDS}",
                words.len()
            ));
        }

        // SAFETY: slot_ptr points to a slot owned by this arena and sized JIT_SLOT_BYTES.
        unsafe {
            // Disable write-protect before writing JIT bytes.
            ffi::jit_write_protect(false);

            let dst_words = slot_ptr.cast::<u32>();
            ptr::copy_nonoverlapping(words.as_ptr(), dst_words, words.len());
            for idx in words.len()..RAW_MAX_WORDS {
                *dst_words.add(idx) = A64_RET;
            }

            ffi::jit_icache_invalidate(slot_ptr, JIT_SLOT_BYTES);
            // Re-enable write-protect before execution.
            ffi::jit_write_protect(true);
        }

        Ok(())
    }
}

impl Drop for JitArena {
    fn drop(&mut self) {
        if !self.base.is_null() && self.len > 0 {
            // SAFETY: memory region was allocated by mmap in JitArena::new.
            unsafe {
                let _ = libc::munmap(self.base.cast::<libc::c_void>(), self.len);
            }
        }
    }
}

fn page_size() -> usize {
    // SAFETY: sysconf with _SC_PAGESIZE has no side effects.
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
