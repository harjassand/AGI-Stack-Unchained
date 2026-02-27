// Hard candidate bounds
pub const RAW_MAX_WORDS: usize = 4096; // 16KB code max
pub const RAW_MIN_WORDS: usize = 1;

// JIT arena
pub const JIT_SLOTS_PER_THREAD: usize = 8;
pub const JIT_SLOT_BYTES: usize = RAW_MAX_WORDS * 4;

// Slot wiping word: RET (AArch64)
pub const A64_RET: u32 = 0xD65F03C0;

// Dedicated JIT stack (execution stack, not signal stack)
pub const JIT_STACK_BYTES: usize = 256 * 1024; // 256KB
pub const JIT_STACK_GUARD_BYTES: usize = 16 * 1024; // 16KB guard each side

// Alternate signal stack
pub const ALTSTACK_BYTES: usize = 64 * 1024;

// Sniper timeouts
pub const MAX_STALL_US: u64 = 2_000; // 2ms (tunable)
pub const SNIPER_SPIN_PAUSE: u32 = 200; // tight-loop pause (tunable)

// RuntimeState wipe rules
pub const WIPE_SCRATCH: bool = true;
pub const WIPE_META: bool = true;
pub const WIPE_REGS: bool = true;
