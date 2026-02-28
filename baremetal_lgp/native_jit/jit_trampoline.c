#include "jit_trampoline.h"

#include <pthread.h>
#include <setjmp.h>
#include <signal.h>
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/types.h>
#include <ucontext.h>
#include <unistd.h>

#define ALTSTACK_BYTES (64u * 1024u)
#define JIT_STACK_BYTES (256u * 1024u)
#define JIT_STACK_GUARD_BYTES (16u * 1024u)
#define MAP_ANON_FALLBACK 0x1000

static _Thread_local sigjmp_buf g_env;
static _Thread_local int g_armed = 0;
static _Thread_local trap_info_t g_last_trap = {0, 0, 0, 0};

static _Thread_local uint8_t* g_altstack_mem = NULL;
static _Thread_local uint8_t* g_jit_stack_map = NULL;
static _Thread_local uint8_t* g_jit_stack_base = NULL;
static _Thread_local size_t g_jit_stack_len = 0;
static _Thread_local size_t g_jit_stack_map_len = 0;
static _Thread_local void* g_saved_host_sp = NULL;

static pthread_once_t g_sigaction_once = PTHREAD_ONCE_INIT;

static inline size_t align_up(size_t value, size_t align) {
  if (align == 0) {
    return value;
  }
  size_t rem = value % align;
  if (rem == 0) {
    return value;
  }
  return value + (align - rem);
}

static inline uint32_t trap_kind_from_sig(int sig) {
  switch (sig) {
    case SIGILL:
      return TRAP_SIGILL;
    case SIGSEGV:
      return TRAP_SIGSEGV;
    case SIGBUS:
      return TRAP_SIGBUS;
    case SIGALRM:
      return TRAP_SIGALRM;
    default:
      return TRAP_OTHER;
  }
}

static inline uint64_t best_effort_pc(void* uctx_void) {
#if defined(__APPLE__) && defined(__aarch64__)
  ucontext_t* uctx = (ucontext_t*)uctx_void;
  if (uctx == NULL || uctx->uc_mcontext == NULL) {
    return 0;
  }
  return (uint64_t)uctx->uc_mcontext->__ss.__pc;
#else
  (void)uctx_void;
  return 0;
#endif
}

static void fatal_signal_outside_jit(int sig) {
  _exit(128 + sig);
}

static void jit_signal_handler(int sig, siginfo_t* info, void* uctx) {
  if (!g_armed) {
    if (sig == SIGALRM) {
      return;
    }
    fatal_signal_outside_jit(sig);
  }

  g_last_trap.kind = trap_kind_from_sig(sig);
  g_last_trap.sig = (uint32_t)sig;
  g_last_trap.fault_addr =
      info != NULL ? (uint64_t)(uintptr_t)info->si_addr : 0;
  g_last_trap.fault_pc = best_effort_pc(uctx);

  siglongjmp(g_env, 1);
}

static void install_sigactions_once(void) {
  struct sigaction sa;
  memset(&sa, 0, sizeof(sa));
  sa.sa_flags = SA_SIGINFO | SA_ONSTACK;
  sa.sa_sigaction = jit_signal_handler;
  sigemptyset(&sa.sa_mask);

  sigaction(SIGILL, &sa, NULL);
  sigaction(SIGSEGV, &sa, NULL);
  sigaction(SIGBUS, &sa, NULL);
  sigaction(SIGALRM, &sa, NULL);
  sigaction(SIGTRAP, &sa, NULL);
  sigaction(SIGFPE, &sa, NULL);
  sigaction(SIGSYS, &sa, NULL);
  sigaction(SIGABRT, &sa, NULL);
}

static void ensure_altstack(void) {
  if (g_altstack_mem != NULL) {
    return;
  }

  void* mem = mmap(NULL, ALTSTACK_BYTES, PROT_READ | PROT_WRITE,
                   MAP_PRIVATE | MAP_ANON_FALLBACK, -1, 0);
  if (mem == MAP_FAILED) {
    _exit(201);
  }

  stack_t ss;
  memset(&ss, 0, sizeof(ss));
  ss.ss_sp = mem;
  ss.ss_size = ALTSTACK_BYTES;
  ss.ss_flags = 0;

  if (sigaltstack(&ss, NULL) != 0) {
    _exit(202);
  }

  g_altstack_mem = (uint8_t*)mem;
}

static void ensure_jit_stack(void) {
  if (g_jit_stack_base != NULL) {
    return;
  }

  long page_size = sysconf(_SC_PAGESIZE);
  if (page_size <= 0) {
    page_size = 4096;
  }

  size_t guard = align_up(JIT_STACK_GUARD_BYTES, (size_t)page_size);
  size_t stack_len = align_up(JIT_STACK_BYTES, (size_t)page_size);
  size_t total = stack_len + (2u * guard);

  void* map = mmap(NULL, total, PROT_READ | PROT_WRITE,
                   MAP_PRIVATE | MAP_ANON_FALLBACK, -1, 0);
  if (map == MAP_FAILED) {
    _exit(203);
  }

  uint8_t* base = (uint8_t*)map;
  if (mprotect(base, guard, PROT_NONE) != 0) {
    _exit(204);
  }
  if (mprotect(base + guard + stack_len, guard, PROT_NONE) != 0) {
    _exit(205);
  }

  g_jit_stack_map = base;
  g_jit_stack_base = base + guard;
  g_jit_stack_len = stack_len;
  g_jit_stack_map_len = total;
}

#if defined(__aarch64__)
typedef struct __attribute__((aligned(16))) {
  uint64_t gpr[11];
  uint64_t _pad;
  __uint128_t simd[8];
} RegSave;

static inline void save_regs(RegSave* regs) {
  asm volatile(
      "stp x19, x20, [%0, #0]\n"
      "stp x21, x22, [%0, #16]\n"
      "stp x23, x24, [%0, #32]\n"
      "stp x25, x26, [%0, #48]\n"
      "stp x27, x28, [%0, #64]\n"
      "str x29, [%0, #80]\n"
      "stp q8, q9, [%1, #0]\n"
      "stp q10, q11, [%1, #32]\n"
      "stp q12, q13, [%1, #64]\n"
      "stp q14, q15, [%1, #96]\n"
      :
      : "r"(regs->gpr), "r"(regs->simd)
      : "memory");
}

static inline void restore_regs(const RegSave* regs) {
  asm volatile(
      "ldp x19, x20, [%0, #0]\n"
      "ldp x21, x22, [%0, #16]\n"
      "ldp x23, x24, [%0, #32]\n"
      "ldp x25, x26, [%0, #48]\n"
      "ldp x27, x28, [%0, #64]\n"
      "ldr x29, [%0, #80]\n"
      "ldp q8, q9, [%1, #0]\n"
      "ldp q10, q11, [%1, #32]\n"
      "ldp q12, q13, [%1, #64]\n"
      "ldp q14, q15, [%1, #96]\n"
      :
      : "r"(regs->gpr), "r"(regs->simd)
      : "memory");
}

static inline void call_entry_on_jit_stack(void (*entry)(void*), void* arg,
                                           void* stack_top) {
  void* orig_sp = NULL;
  asm volatile("mov %0, sp" : "=r"(orig_sp) : : "memory");
  g_saved_host_sp = orig_sp;

  asm volatile(
      "mov sp, %0\n"
      "mov x0, %1\n"
      "blr %2\n"
      :
      : "r"(stack_top), "r"(arg), "r"(entry)
      : "x0", "x1", "x2", "x3", "x4", "x5", "x6", "x7", "x8", "x9", "x10",
        "x11", "x12", "x13", "x14", "x15", "x16", "x17", "x30", "v0", "v1",
        "v2", "v3", "v4", "v5", "v6", "v7", "v16", "v17", "v18", "v19",
        "v20", "v21", "v22", "v23", "v24", "v25", "v26", "v27", "v28",
        "v29", "v30", "v31", "memory");

  void* restore_sp = g_saved_host_sp;
  asm volatile("mov sp, %0" : : "r"(restore_sp) : "memory");
}

static inline int32_t call_entry_i32_on_jit_stack(int32_t (*entry)(void*),
                                                   void* arg,
                                                   void* stack_top) {
  int32_t ret = 0;
  void* orig_sp = NULL;
  asm volatile("mov %0, sp" : "=r"(orig_sp) : : "memory");
  g_saved_host_sp = orig_sp;

  asm volatile(
      "mov sp, %1\n"
      "mov x0, %2\n"
      "blr %3\n"
      "mov %w0, w0\n"
      : "=r"(ret)
      : "r"(stack_top), "r"(arg), "r"(entry)
      : "x0", "x1", "x2", "x3", "x4", "x5", "x6", "x7", "x8", "x9", "x10",
        "x11", "x12", "x13", "x14", "x15", "x16", "x17", "x30", "v0", "v1",
        "v2", "v3", "v4", "v5", "v6", "v7", "v16", "v17", "v18", "v19",
        "v20", "v21", "v22", "v23", "v24", "v25", "v26", "v27", "v28",
        "v29", "v30", "v31", "memory");

  void* restore_sp = g_saved_host_sp;
  asm volatile("mov sp, %0" : : "r"(restore_sp) : "memory");
  return ret;
}
#else
typedef struct {
  uint64_t unused;
} RegSave;

static inline void save_regs(RegSave* regs) {
  (void)regs;
}

static inline void restore_regs(const RegSave* regs) {
  (void)regs;
}

static inline void call_entry_on_jit_stack(void (*entry)(void*), void* arg,
                                           void* stack_top) {
  (void)stack_top;
  entry(arg);
}

static inline int32_t call_entry_i32_on_jit_stack(int32_t (*entry)(void*),
                                                   void* arg,
                                                   void* stack_top) {
  (void)stack_top;
  return entry(arg);
}
#endif

void jit_trap_thread_init(void) {
  pthread_once(&g_sigaction_once, install_sigactions_once);
  ensure_altstack();
  ensure_jit_stack();
  g_armed = 0;
  memset(&g_last_trap, 0, sizeof(g_last_trap));
}

int run_jit_candidate(void (*entry)(void*), void* runtime_state_ptr,
                      trap_info_t* out_trap) {
  if (out_trap != NULL) {
    memset(out_trap, 0, sizeof(*out_trap));
  }

  if (entry == NULL) {
    if (out_trap != NULL) {
      out_trap->kind = TRAP_OTHER;
    }
    return 1;
  }

  if (g_jit_stack_base == NULL || g_altstack_mem == NULL) {
    jit_trap_thread_init();
  }

  RegSave regs;
  save_regs(&regs);

  memset(&g_last_trap, 0, sizeof(g_last_trap));

  if (sigsetjmp(g_env, 1) == 0) {
    g_armed = 1;
    uintptr_t top_raw = (uintptr_t)(g_jit_stack_base + g_jit_stack_len);
    top_raw &= ~(uintptr_t)0xF;
    if (top_raw >= 16u) {
      top_raw -= 16u;
    }

    call_entry_on_jit_stack(entry, runtime_state_ptr, (void*)top_raw);

    g_armed = 0;
    restore_regs(&regs);
    return 0;
  }

  g_armed = 0;
  if (out_trap != NULL) {
    *out_trap = g_last_trap;
  }
  restore_regs(&regs);
  return 1;
}

int run_jit_candidate_i32_on_stack(int32_t (*entry)(void*),
                                   void* runtime_state_ptr, void* stack_top,
                                   trap_info_t* out_trap,
                                   int32_t* out_status) {
  if (out_trap != NULL) {
    memset(out_trap, 0, sizeof(*out_trap));
  }
  if (out_status != NULL) {
    *out_status = 0;
  }

  if (entry == NULL) {
    if (out_trap != NULL) {
      out_trap->kind = TRAP_OTHER;
    }
    return 1;
  }

  if (g_jit_stack_base == NULL || g_altstack_mem == NULL) {
    jit_trap_thread_init();
  }

  uintptr_t top_raw = (uintptr_t)(g_jit_stack_base + g_jit_stack_len);
  top_raw &= ~(uintptr_t)0xF;
  if (top_raw >= 16u) {
    top_raw -= 16u;
  }
  if (stack_top != NULL) {
    uintptr_t explicit_top = ((uintptr_t)stack_top) & ~(uintptr_t)0xF;
    if (explicit_top >= 16u) {
      explicit_top -= 16u;
      top_raw = explicit_top;
    }
  }

  RegSave regs;
  save_regs(&regs);
  memset(&g_last_trap, 0, sizeof(g_last_trap));

  if (sigsetjmp(g_env, 1) == 0) {
    g_armed = 1;
    int32_t status = call_entry_i32_on_jit_stack(entry, runtime_state_ptr,
                                                 (void*)top_raw);
    if (out_status != NULL) {
      *out_status = status;
    }
    g_armed = 0;
    restore_regs(&regs);
    return 0;
  }

  g_armed = 0;
  if (out_trap != NULL) {
    *out_trap = g_last_trap;
  }
  restore_regs(&regs);
  return 1;
}

void jit_test_snapshot_regs(uint64_t* out_gpr11, uint8_t* out_q8_q15_bytes) {
  if (out_gpr11 == NULL || out_q8_q15_bytes == NULL) {
    return;
  }

#if defined(__aarch64__)
  asm volatile(
      "str x19, [%0, #0]\n"
      "str x20, [%0, #8]\n"
      "str x21, [%0, #16]\n"
      "str x22, [%0, #24]\n"
      "str x23, [%0, #32]\n"
      "str x24, [%0, #40]\n"
      "str x25, [%0, #48]\n"
      "str x26, [%0, #56]\n"
      "str x27, [%0, #64]\n"
      "str x28, [%0, #72]\n"
      "str x29, [%0, #80]\n"
      "str q8, [%1, #0]\n"
      "str q9, [%1, #16]\n"
      "str q10, [%1, #32]\n"
      "str q11, [%1, #48]\n"
      "str q12, [%1, #64]\n"
      "str q13, [%1, #80]\n"
      "str q14, [%1, #96]\n"
      "str q15, [%1, #112]\n"
      :
      : "r"(out_gpr11), "r"(out_q8_q15_bytes)
      : "memory");
#else
  memset(out_gpr11, 0, 11 * sizeof(uint64_t));
  memset(out_q8_q15_bytes, 0, 8 * 16);
#endif
}

void jit_test_set_sentinels(void) {}

void jit_test_read_sentinels(uint64_t* out_gpr11, uint8_t* out_q8_q15_bytes) {
  jit_test_snapshot_regs(out_gpr11, out_q8_q15_bytes);
}

#if defined(__aarch64__)
void jit_test_clobber_entry(void* runtime_state_ptr) {
  (void)runtime_state_ptr;
  __asm__ volatile(
      "mov x19, xzr\n"
      "mov x20, xzr\n"
      "mov x21, xzr\n"
      "mov x22, xzr\n"
      "mov x23, xzr\n"
      "mov x24, xzr\n"
      "mov x25, xzr\n"
      "mov x26, xzr\n"
      "mov x27, xzr\n"
      "mov x28, xzr\n"
      "movi v8.16b, #0\n"
      "movi v9.16b, #0\n"
      "movi v10.16b, #0\n"
      "movi v11.16b, #0\n"
      "movi v12.16b, #0\n"
      "movi v13.16b, #0\n"
      "movi v14.16b, #0\n"
      "movi v15.16b, #0\n"
      :
      :
      : "x19", "x20", "x21", "x22", "x23", "x24", "x25", "x26", "x27", "x28",
        "v8", "v9", "v10", "v11", "v12", "v13", "v14", "v15", "memory");
}

void jit_test_clobber_and_trap_entry(void* runtime_state_ptr) {
  (void)runtime_state_ptr;
  __asm__ volatile(
      "mov x19, xzr\n"
      "mov x20, xzr\n"
      "mov x21, xzr\n"
      "mov x22, xzr\n"
      "mov x23, xzr\n"
      "mov x24, xzr\n"
      "mov x25, xzr\n"
      "mov x26, xzr\n"
      "mov x27, xzr\n"
      "mov x28, xzr\n"
      "mov x29, xzr\n"
      "movi v8.16b, #0\n"
      "movi v9.16b, #0\n"
      "movi v10.16b, #0\n"
      "movi v11.16b, #0\n"
      "movi v12.16b, #0\n"
      "movi v13.16b, #0\n"
      "movi v14.16b, #0\n"
      "movi v15.16b, #0\n"
      ".inst 0x00000000\n"
      :
      :
      : "x19", "x20", "x21", "x22", "x23", "x24", "x25", "x26", "x27", "x28",
        "v8", "v9", "v10", "v11", "v12", "v13", "v14", "v15", "memory");
  __builtin_unreachable();
}
#else
void jit_test_clobber_entry(void* runtime_state_ptr) {
  (void)runtime_state_ptr;
}

void jit_test_clobber_and_trap_entry(void* runtime_state_ptr) {
  (void)runtime_state_ptr;
}
#endif

void jit_test_raise_sigbus_entry(void* runtime_state_ptr) {
  (void)runtime_state_ptr;
  raise(SIGBUS);
}
