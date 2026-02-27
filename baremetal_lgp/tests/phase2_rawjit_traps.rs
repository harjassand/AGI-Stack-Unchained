#![cfg(all(target_os = "macos", target_arch = "aarch64"))]

use baremetal_lgp::jit2::ffi::{self, TrapInfo};
use baremetal_lgp::jit2::raw_runner::{
    raw_thread_init, run_raw_candidate, EpisodeLayout, EpisodeSpec,
};
use baremetal_lgp::jit2::sniper::WorkerWatch;
use baremetal_lgp::jit2::templates::default_templates;

const TRAP_SIGILL: u32 = 1;
const TRAP_SIGSEGV: u32 = 2;
const TRAP_SIGBUS: u32 = 3;

unsafe extern "C" {
    fn jit_test_raise_sigbus_entry(runtime_state_ptr: *mut std::ffi::c_void);
}

fn make_episode_spec() -> EpisodeSpec {
    let layout = EpisodeLayout {
        in_base: 0,
        in_len: 8,
        out_base: 1024,
        out_len: 8,
        work_base: 2048,
        work_len: 8,
    };

    let mut meta_u32 = [0u32; 16];
    meta_u32[0] = layout.in_base as u32;
    meta_u32[1] = layout.in_len as u32;
    meta_u32[2] = layout.out_base as u32;
    meta_u32[3] = layout.out_len as u32;
    meta_u32[4] = layout.work_base as u32;
    meta_u32[5] = layout.work_len as u32;

    EpisodeSpec {
        family: 0,
        layout,
        in_data: vec![0.0; 8],
        target: vec![0.0; 8],
        oracle_meta_u32: meta_u32,
        oracle_meta_f32: [0.0; 16],
        expected_output_len: 8,
        d_hint: 8,
        flags: 0,
        hidden_seed: 123,
        robustness_bonus_scale: 0.0,
    }
}

#[test]
fn phase2_rawjit_traps_sigill_and_recovers() {
    let watch = Box::leak(Box::new(WorkerWatch::new()));
    let mut ctx = raw_thread_init(watch);
    let spec = make_episode_spec();

    let templates = default_templates();
    for template in &templates {
        let ok = run_raw_candidate(&mut ctx, &template.words, &spec);
        assert!(
            ok.returned && ok.trap.is_none(),
            "template {} should run trap-free",
            template.name
        );
    }

    let invalid = [0x0000_0000_u32];
    let bad = run_raw_candidate(&mut ctx, &invalid, &spec);
    assert!(!bad.returned);
    let trap = bad.trap.expect("expected SIGILL trap");
    assert_eq!(trap.kind, TRAP_SIGILL);

    // Force SIGSEGV via null write from raw words:
    // movz x1, #0 ; str w0, [x1] ; ret
    let segv_words = [0xD2800001_u32, 0xB9000020_u32, 0xD65F03C0_u32];
    let segv = run_raw_candidate(&mut ctx, &segv_words, &spec);
    assert!(!segv.returned);
    assert_eq!(segv.trap.expect("expected SIGSEGV trap").kind, TRAP_SIGSEGV);

    let ret_only = &templates
        .iter()
        .find(|t| t.name == "ret_only")
        .expect("ret_only template")
        .words;
    let ok_again = run_raw_candidate(&mut ctx, ret_only, &spec);
    assert!(ok_again.returned);
    assert!(ok_again.trap.is_none());

    // Force SIGBUS via a dedicated C entry helper and ensure recovery.
    let mut trap = TrapInfo::default();
    // SAFETY: helper has expected ABI and intentionally raises SIGBUS.
    let rc = unsafe {
        ffi::run_jit_candidate(
            jit_test_raise_sigbus_entry,
            (&mut *ctx.state as *mut baremetal_lgp::jit2::abi::RuntimeState)
                .cast::<std::ffi::c_void>(),
            &mut trap as *mut TrapInfo,
        )
    };
    assert_ne!(rc, 0);
    assert_eq!(trap.kind, TRAP_SIGBUS);

    let ok_after_bus = run_raw_candidate(&mut ctx, ret_only, &spec);
    assert!(ok_after_bus.returned);
    assert!(ok_after_bus.trap.is_none());
}
