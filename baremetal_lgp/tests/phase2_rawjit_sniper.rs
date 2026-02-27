#![cfg(all(target_os = "macos", target_arch = "aarch64"))]

use baremetal_lgp::jit2::raw_runner::{
    raw_thread_init, run_raw_candidate, EpisodeLayout, EpisodeSpec,
};
use baremetal_lgp::jit2::sniper::WorkerWatch;
use baremetal_lgp::jit2::templates::default_templates;

const TRAP_SIGALRM: u32 = 4;

fn make_episode_spec() -> EpisodeSpec {
    let layout = EpisodeLayout {
        in_base: 16,
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
        family: 1,
        layout,
        in_data: vec![0.0; 8],
        target: vec![0.0; 8],
        oracle_meta_u32: meta_u32,
        oracle_meta_f32: [0.0; 16],
        expected_output_len: 8,
        d_hint: 8,
        flags: 0,
        hidden_seed: 456,
        robustness_bonus_scale: 0.0,
    }
}

#[test]
fn phase2_rawjit_sniper_interrupts_hang_and_recovers() {
    let watch = Box::leak(Box::new(WorkerWatch::new()));
    let mut ctx = raw_thread_init(watch);
    let spec = make_episode_spec();

    // AArch64: b . (infinite self-branch)
    let loop_forever = [0x1400_0000_u32];
    let trapped = run_raw_candidate(&mut ctx, &loop_forever, &spec);
    assert!(!trapped.returned);
    assert!(trapped.timeout);
    assert_eq!(trapped.trap.expect("timeout trap").kind, TRAP_SIGALRM);

    let templates = default_templates();
    let safe = &templates
        .iter()
        .find(|t| t.name == "ret_only")
        .expect("ret_only template")
        .words;

    let ok = run_raw_candidate(&mut ctx, safe, &spec);
    assert!(ok.returned);
    assert!(ok.trap.is_none());
}
