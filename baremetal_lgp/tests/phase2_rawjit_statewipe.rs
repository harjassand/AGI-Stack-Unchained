#![cfg(all(target_os = "macos", target_arch = "aarch64"))]

use baremetal_lgp::jit2::raw_runner::{
    raw_thread_init, run_raw_candidate, EpisodeLayout, EpisodeSpec,
};
use baremetal_lgp::jit2::sniper::WorkerWatch;

const A64_RET: u32 = 0xD65F03C0;
const A64_INVALID: u32 = 0x0000_0000;

fn enc_add_imm_x(rd: u8, rn: u8, imm12: u16, shift12: bool) -> u32 {
    let shift = if shift12 { 1_u32 } else { 0_u32 };
    0x9100_0000
        | (shift << 22)
        | ((u32::from(imm12) & 0x0FFF) << 10)
        | (u32::from(rn & 31) << 5)
        | u32::from(rd & 31)
}

fn enc_movz_w(rd: u8, imm16: u16, lsl: u8) -> u32 {
    let hw = u32::from(lsl / 16) & 0x3;
    0x5280_0000 | (hw << 21) | (u32::from(imm16) << 5) | u32::from(rd & 31)
}

fn enc_movk_w(rd: u8, imm16: u16, lsl: u8) -> u32 {
    let hw = u32::from(lsl / 16) & 0x3;
    0x7280_0000 | (hw << 21) | (u32::from(imm16) << 5) | u32::from(rd & 31)
}

fn enc_str_w(rt: u8, rn: u8, imm12_words: u16) -> u32 {
    0xB900_0000
        | ((u32::from(imm12_words) & 0x0FFF) << 10)
        | (u32::from(rn & 31) << 5)
        | u32::from(rt & 31)
}

fn make_spec(meta_f32_0: f32, target_value: f32) -> EpisodeSpec {
    let layout = EpisodeLayout {
        in_base: 0,
        in_len: 8,
        out_base: 512,
        out_len: 8,
        work_base: 1024,
        work_len: 8,
    };

    let mut meta_u32 = [0u32; 16];
    meta_u32[0] = layout.in_base as u32;
    meta_u32[1] = layout.in_len as u32;
    meta_u32[2] = layout.out_base as u32;
    meta_u32[3] = layout.out_len as u32;
    meta_u32[4] = layout.work_base as u32;
    meta_u32[5] = layout.work_len as u32;

    let mut meta_f32 = [0.0f32; 16];
    meta_f32[0] = meta_f32_0;

    EpisodeSpec {
        family: 0,
        layout,
        in_data: vec![0.0; 8],
        target: vec![target_value; 8],
        oracle_meta_u32: meta_u32,
        oracle_meta_f32: meta_f32,
        expected_output_len: 8,
        d_hint: 8,
        flags: 0,
        hidden_seed: 999,
        robustness_bonus_scale: 0.0,
    }
}

fn candidate_write_meta_f32(bits: u32, trap_after_write: bool) -> Vec<u32> {
    // runtime_state.meta_f32[0] offset = 65536 + 192 = 65728 bytes
    // x1 = x0 + 65536 + 192
    let mut words = vec![
        enc_add_imm_x(1, 0, 16, true),
        enc_add_imm_x(1, 1, 192, false),
        enc_movz_w(2, (bits & 0xFFFF) as u16, 0),
        enc_movk_w(2, ((bits >> 16) & 0xFFFF) as u16, 16),
        enc_str_w(2, 1, 0),
    ];
    if trap_after_write {
        words.push(A64_INVALID);
    } else {
        words.push(A64_RET);
    }
    words
}

fn candidate_clobber_meta_out_len_to_zero() -> Vec<u32> {
    // runtime_state.meta_u32[3] offset = 65536 + 140 = 65676 bytes
    // x1 = x0 + 65536 + 140; store 0 into [x1].
    vec![
        enc_add_imm_x(1, 0, 16, true),
        enc_add_imm_x(1, 1, 140, false),
        enc_movz_w(2, 0, 0),
        enc_str_w(2, 1, 0),
        A64_RET,
    ]
}

#[test]
fn phase2_rawjit_statewipe_full_wipe_and_oracle_owned_scoring() {
    let watch = Box::leak(Box::new(WorkerWatch::new()));
    let mut ctx = raw_thread_init(watch);

    let poison_success = candidate_write_meta_f32(0x4228_0000, false); // 42.0f
    let poison_trap = candidate_write_meta_f32(0x42C6_0000, true); // 99.0f then trap
    let safe_ret = [A64_RET];

    let spec = make_spec(3.5, 0.0);

    let first = run_raw_candidate(&mut ctx, &poison_success, &spec);
    assert!(first.returned);
    assert_eq!(ctx.state.meta_f32[0], 42.0);

    let second = run_raw_candidate(&mut ctx, &safe_ret, &spec);
    assert!(second.returned);
    assert_eq!(ctx.state.meta_f32[0], 3.5);

    let third = run_raw_candidate(&mut ctx, &poison_trap, &spec);
    assert!(!third.returned);
    assert!(third.trap.is_some());
    assert_eq!(ctx.state.meta_f32[0], 99.0);

    let fourth = run_raw_candidate(&mut ctx, &safe_ret, &spec);
    assert!(fourth.returned);
    assert_eq!(ctx.state.meta_f32[0], 3.5);

    // Oracle-owned scoring locals test: candidate mutates meta_u32[out_len] to 0.
    // Score must still use the oracle-owned expected_output_len=8 and target vec.
    let score_spec = make_spec(7.0, 1.0);
    let clobber_out_len = candidate_clobber_meta_out_len_to_zero();
    let scored = run_raw_candidate(&mut ctx, &clobber_out_len, &score_spec);
    assert!(scored.returned);
    assert!(
        scored.score < -0.5,
        "score unexpectedly high; scorer may be reading post-run meta: {}",
        scored.score
    );
}
