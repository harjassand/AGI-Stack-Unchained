use baremetal_lgp::jit2::raw_runner::SNIPER_USEC;
use baremetal_lgp::oracle3::ast::{AstNode, AstOp, AstProgram, AstShape};
use baremetal_lgp::oracle3::compile::{compile_chunkpack, FULL_COMPILE_CFG, SPEC_VERSION};
use baremetal_lgp::oracle3::spec::{InputDistSpec, PiecewiseScheduleSpec, RegimeSpec};
use baremetal_lgp::oracle3::{score_candidate_on_chunk, RawJitExecEngine};

fn scale2_spec() -> RegimeSpec {
    RegimeSpec {
        version: SPEC_VERSION,
        spec_seed_salt: 7,
        input_len: 1,
        output_len: 1,
        meta_u32_len: 16,
        meta_f32_len: 16,
        episode_param_count: 4,
        input_dist: InputDistSpec::Uniform { lo: -1.0, hi: 1.0 },
        ast: AstProgram {
            nodes: vec![
                AstNode {
                    op: AstOp::InputVector,
                    shape: AstShape::Vector(1),
                },
                AstNode {
                    op: AstOp::ConstF32(2.0),
                    shape: AstShape::Scalar,
                },
                AstNode {
                    op: AstOp::Mul { a: 0, b: 1 },
                    shape: AstShape::Vector(1),
                },
            ],
            output: 2,
        },
        schedule: PiecewiseScheduleSpec { segments: vec![] },
    }
}

#[cfg(all(target_os = "macos", target_arch = "aarch64"))]
#[test]
fn dod_phase3_sigalrm_is_solver_failure() {
    let chunk = compile_chunkpack(&scale2_spec(), 4242, FULL_COMPILE_CFG).expect("compile chunk");
    let mut engine = RawJitExecEngine::new(SNIPER_USEC);

    // AArch64: "b ." infinite loop.
    let loop_forever = vec![0x1400_0000_u32];
    let report = score_candidate_on_chunk(&mut engine, &loop_forever, &chunk);

    assert_eq!(report.score_mean, 0.0);
    assert!(report.faulted);
    assert!(report.sigalrm >= 1);
    assert_eq!(report.episodes_scored, 0);
}

#[test]
fn dod_phase3_chunkpack_digest_matches() {
    let spec = scale2_spec();
    let chunk1 = compile_chunkpack(&spec, 2026, FULL_COMPILE_CFG).expect("compile 1");
    let chunk2 = compile_chunkpack(&spec, 2026, FULL_COMPILE_CFG).expect("compile 2");
    assert_eq!(chunk1.digest, chunk2.digest);
}
