use std::sync::{Mutex, OnceLock};

use baremetal_lgp::oracle3::ast::{AstNode, AstOp, AstProgram, AstShape};
use baremetal_lgp::oracle3::compile::{compile_chunkpack, FULL_COMPILE_CFG, SPEC_VERSION};
use baremetal_lgp::oracle3::cost::{compute_cost, CostViolation, CAP_NODES};
use baremetal_lgp::oracle3::spec::{InputDistSpec, PiecewiseScheduleSpec, RegimeSpec};
use baremetal_lgp::oracle3::validity::{evaluate_validity, ValidityVerdict, DELTA_VALID};
use baremetal_lgp::oracle3::{score_candidate_on_chunk, ExecEngine, ExecFault, ExecOutcome};

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

fn test_lock() -> std::sync::MutexGuard<'static, ()> {
    static LOCK: OnceLock<Mutex<()>> = OnceLock::new();
    LOCK.get_or_init(|| Mutex::new(()))
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner())
}

#[test]
fn agentb_cost_model_rejects_node_overflow() {
    let _guard = test_lock();
    let nodes = (0..(CAP_NODES as usize + 1))
        .map(|_| AstNode {
            op: AstOp::ConstF32(0.0),
            shape: AstShape::Scalar,
        })
        .collect::<Vec<_>>();

    let spec = RegimeSpec {
        version: SPEC_VERSION,
        spec_seed_salt: 0,
        input_len: 1,
        output_len: 1,
        meta_u32_len: 16,
        meta_f32_len: 16,
        episode_param_count: 0,
        input_dist: InputDistSpec::Uniform { lo: 0.0, hi: 1.0 },
        ast: AstProgram { nodes, output: 0 },
        schedule: PiecewiseScheduleSpec { segments: vec![] },
    };

    let result = compute_cost(&spec);
    assert!(matches!(result, Err(CostViolation::NodesExceeded { .. })));
}

#[test]
fn agentb_cost_model_counts_affine_mac_exactly() {
    let _guard = test_lock();
    let spec = RegimeSpec {
        version: SPEC_VERSION,
        spec_seed_salt: 1,
        input_len: 64,
        output_len: 32,
        meta_u32_len: 16,
        meta_f32_len: 16,
        episode_param_count: 0,
        input_dist: InputDistSpec::Uniform { lo: 0.0, hi: 1.0 },
        ast: AstProgram {
            nodes: vec![
                AstNode {
                    op: AstOp::InputVector,
                    shape: AstShape::Vector(64),
                },
                AstNode {
                    op: AstOp::Affine {
                        x: 0,
                        w_offset: 0,
                        b_offset: 0,
                        out_len: 32,
                        in_len: 64,
                    },
                    shape: AstShape::Vector(32),
                },
            ],
            output: 1,
        },
        schedule: PiecewiseScheduleSpec { segments: vec![] },
    };

    let cost = compute_cost(&spec).expect("cost should compute");
    assert_eq!(cost.affine_mac, 2048);
}

#[test]
fn chunkpack_compile_is_bitwise_deterministic() {
    let _guard = test_lock();
    let spec = scale2_spec();
    let chunk1 = compile_chunkpack(&spec, 12345, FULL_COMPILE_CFG).expect("compile 1");
    let chunk2 = compile_chunkpack(&spec, 12345, FULL_COMPILE_CFG).expect("compile 2");

    assert_eq!(chunk1.digest, chunk2.digest);
    assert_eq!(chunk1.inputs, chunk2.inputs);
    assert_eq!(chunk1.targets, chunk2.targets);
    assert_eq!(chunk1.meta_u32, chunk2.meta_u32);
    assert_eq!(chunk1.meta_f32, chunk2.meta_f32);
}

#[test]
fn sigalrm_is_zero_score_and_single_attempt() {
    let _guard = test_lock();
    struct MockExecEngine {
        outcomes: Vec<ExecOutcome>,
        calls: u32,
    }

    impl ExecEngine<()> for MockExecEngine {
        fn run_episode(
            &mut self,
            _candidate: &(),
            _chunk: &baremetal_lgp::oracle3::chunkpack::ChunkPack,
            _episode: u32,
            _output: &mut [f32],
        ) -> ExecOutcome {
            self.calls = self.calls.saturating_add(1);
            let idx = (self.calls - 1) as usize;
            self.outcomes
                .get(idx)
                .copied()
                .unwrap_or(ExecOutcome::Success)
        }
    }

    let spec = scale2_spec();
    let chunk = compile_chunkpack(&spec, 999, FULL_COMPILE_CFG).expect("compile");

    let mut mock = MockExecEngine {
        outcomes: vec![ExecOutcome::Fault(ExecFault::Sigalrm)],
        calls: 0,
    };

    let report = score_candidate_on_chunk(&mut mock, &(), &chunk);
    assert_eq!(report.score_mean, 0.0);
    assert!(report.faulted);
    assert_eq!(report.sigalrm, 1);
    assert_eq!(mock.calls, 1);
}

#[test]
fn validity_gate_rejects_noise_regime() {
    let _guard = test_lock();
    let spec = RegimeSpec {
        version: SPEC_VERSION,
        spec_seed_salt: 11,
        input_len: 1,
        output_len: 1,
        meta_u32_len: 16,
        meta_f32_len: 16,
        episode_param_count: 0,
        input_dist: InputDistSpec::Uniform { lo: -1.0, hi: 1.0 },
        ast: AstProgram {
            nodes: vec![AstNode {
                op: AstOp::ConstVec { len: 1, value: 0.0 },
                shape: AstShape::Vector(1),
            }],
            output: 0,
        },
        schedule: PiecewiseScheduleSpec { segments: vec![] },
    };

    let verdict = evaluate_validity(
        &spec,
        &baremetal_lgp::oracle3::validity::phase1_vm_champ_set(),
    );
    assert!(matches!(
        verdict,
        ValidityVerdict::InvalidBaseline { .. } | ValidityVerdict::InvalidLeak { .. }
    ));
}

#[test]
fn validity_gate_accepts_simple_affine_regime() {
    let _guard = test_lock();
    let spec = scale2_spec();
    let verdict = evaluate_validity(
        &spec,
        &baremetal_lgp::oracle3::validity::phase1_vm_champ_set(),
    );

    match verdict {
        ValidityVerdict::Valid { s_star, s_rand, .. } => {
            assert!(s_star >= s_rand + DELTA_VALID);
        }
        other => panic!(
            "expected valid verdict, got {:?}",
            std::mem::discriminant(&other)
        ),
    }
}
