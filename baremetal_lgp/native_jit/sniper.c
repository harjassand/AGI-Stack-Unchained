#include "sniper.h"

#include <pthread.h>
#include <signal.h>
#include <stdint.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

#define MAX_WORKERS 256
#define SNIPER_SPIN_PAUSE 200u

typedef struct {
  pthread_t tid;
  uint64_t* progress_ptr;
  uint32_t* armed_ptr;
  uint64_t last_progress;
  uint64_t last_cycle;
  int in_use;
} sniper_worker_t;

static sniper_worker_t g_workers[MAX_WORKERS];
static pthread_mutex_t g_workers_mu = PTHREAD_MUTEX_INITIALIZER;

static pthread_once_t g_start_once = PTHREAD_ONCE_INIT;
static pthread_t g_sniper_thread;

static uint64_t g_cycles_per_us = 1;
static uint64_t g_threshold_cycles = 0;

#if defined(__aarch64__)
static inline uint64_t read_cntvct(void) {
  uint64_t v = 0;
  asm volatile("mrs %0, cntvct_el0" : "=r"(v));
  return v;
}

static inline uint64_t read_cntfrq(void) {
  uint64_t v = 0;
  asm volatile("mrs %0, cntfrq_el0" : "=r"(v));
  return v;
}
#else
static inline uint64_t read_cntvct(void) {
  struct timespec ts;
  clock_gettime(CLOCK_MONOTONIC, &ts);
  return ((uint64_t)ts.tv_sec * 1000000000ull) + (uint64_t)ts.tv_nsec;
}

static inline uint64_t read_cntfrq(void) {
  return 1000000000ull;
}
#endif

static inline void spin_pause(void) {
#if defined(__aarch64__)
  for (uint32_t i = 0; i < SNIPER_SPIN_PAUSE; ++i) {
    asm volatile("yield" ::: "memory");
  }
#else
  usleep(50);
#endif
}

static void* sniper_loop(void* arg) {
  (void)arg;

  for (;;) {
    uint64_t now = read_cntvct();

    pthread_mutex_lock(&g_workers_mu);
    for (int i = 0; i < MAX_WORKERS; ++i) {
      sniper_worker_t* w = &g_workers[i];
      if (!w->in_use) {
        continue;
      }

      uint32_t armed = __atomic_load_n(w->armed_ptr, __ATOMIC_RELAXED);
      uint64_t progress = __atomic_load_n(w->progress_ptr, __ATOMIC_RELAXED);

      if (armed == 1) {
        if (progress != w->last_progress) {
          w->last_progress = progress;
          w->last_cycle = now;
        } else {
          uint64_t elapsed = now - w->last_cycle;
          if (elapsed > g_threshold_cycles) {
            pthread_kill(w->tid, SIGALRM);
            w->last_cycle = now;
          }
        }
      } else {
        w->last_progress = progress;
        w->last_cycle = now;
      }
    }
    pthread_mutex_unlock(&g_workers_mu);

    spin_pause();
  }

  return NULL;
}

static void sniper_init_once(void) {
  uint64_t freq = read_cntfrq();
  if (freq == 0) {
    freq = 1;
  }

  g_cycles_per_us = freq / 1000000ull;
  if (g_cycles_per_us == 0) {
    g_cycles_per_us = 1;
  }

  if (g_threshold_cycles == 0) {
    g_threshold_cycles = 2000ull * g_cycles_per_us;
  }

  pthread_create(&g_sniper_thread, NULL, sniper_loop, NULL);
  pthread_detach(g_sniper_thread);
}

void sniper_start_once(uint64_t max_stall_us) {
  if (max_stall_us == 0) {
    max_stall_us = 1;
  }

  uint64_t freq = read_cntfrq();
  uint64_t cycles_per_us = freq / 1000000ull;
  if (cycles_per_us == 0) {
    cycles_per_us = 1;
  }
  g_threshold_cycles = max_stall_us * cycles_per_us;

  pthread_once(&g_start_once, sniper_init_once);
}

void sniper_register_worker(pthread_t tid, uint64_t* progress_ptr,
                            uint32_t* armed_ptr) {
  if (progress_ptr == NULL || armed_ptr == NULL) {
    return;
  }

  pthread_mutex_lock(&g_workers_mu);
  for (int i = 0; i < MAX_WORKERS; ++i) {
    sniper_worker_t* w = &g_workers[i];
    if (!w->in_use) {
      w->tid = tid;
      w->progress_ptr = progress_ptr;
      w->armed_ptr = armed_ptr;
      w->last_progress = __atomic_load_n(progress_ptr, __ATOMIC_RELAXED);
      w->last_cycle = read_cntvct();
      w->in_use = 1;
      break;
    }
  }
  pthread_mutex_unlock(&g_workers_mu);
}
