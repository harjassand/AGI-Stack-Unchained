#pragma once

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

enum {
  RUNTIME_SCRATCH_WORDS_F32 = 16384,
  RUNTIME_F_REGS = 16,
  RUNTIME_I_REGS = 16,
  RUNTIME_META_U32 = 16,
  RUNTIME_META_F32 = 16,
};

typedef struct __attribute__((aligned(16))) {
  float scratch[RUNTIME_SCRATCH_WORDS_F32];
  float fregs[RUNTIME_F_REGS];
  int32_t iregs[RUNTIME_I_REGS];
  uint32_t meta_u32[RUNTIME_META_U32];
  float meta_f32[RUNTIME_META_F32];
  uint32_t status_u32;
  uint32_t _pad[3];
} runtime_state_t;

typedef enum {
  TRAP_NONE = 0,
  TRAP_SIGILL = 1,
  TRAP_SIGSEGV = 2,
  TRAP_SIGBUS = 3,
  TRAP_SIGALRM = 4,
  TRAP_OTHER = 15,
} trap_kind_t;

typedef struct {
  uint32_t kind;
  uint32_t sig;
  uint64_t fault_pc;
  uint64_t fault_addr;
} trap_info_t;

void jit_trap_thread_init(void);

int run_jit_candidate(void (*entry)(void*), void* runtime_state_ptr,
                      trap_info_t* out_trap);

// Test helpers (macOS AArch64 only; stubs elsewhere).
void jit_test_snapshot_regs(uint64_t* out_gpr11, uint8_t* out_q8_q15_bytes);
void jit_test_set_sentinels(void);
void jit_test_read_sentinels(uint64_t* out_gpr11, uint8_t* out_q8_q15_bytes);
void jit_test_clobber_entry(void* runtime_state_ptr);
void jit_test_clobber_and_trap_entry(void* runtime_state_ptr);

#ifdef __cplusplus
}
#endif
