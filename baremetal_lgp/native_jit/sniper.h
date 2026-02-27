#pragma once

#include <pthread.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

void sniper_start_once(uint64_t max_stall_us);
void sniper_register_worker(pthread_t tid, uint64_t* progress_ptr,
                            uint32_t* armed_ptr);

#ifdef __cplusplus
}
#endif
