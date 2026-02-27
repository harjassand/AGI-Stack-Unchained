use baremetal_lgp::abi::CONST_POOL_WORDS;
use baremetal_lgp::bytecode::program::BytecodeProgram;
use baremetal_lgp::isa::encoding::encode;
use baremetal_lgp::isa::op::Op;
use baremetal_lgp::library::bank::LibraryBank;
use baremetal_lgp::vm::{run_candidate, ExecConfig, StopReason, VmWorker};

fn imm14_from_i32(v: i32) -> u16 {
    ((v as i16) as u16) & 0x3FFF
}

fn mk_prog(words: Vec<u32>, const_pool: [f32; CONST_POOL_WORDS]) -> BytecodeProgram {
    BytecodeProgram {
        #[cfg(feature = "trace")]
        pc_to_block: vec![0; words.len()],
        words,
        const_pool,
    }
}

fn approx_eq(a: f32, b: f32) {
    assert!((a - b).abs() < 1e-2, "left={a}, right={b}");
}

#[test]
fn agent1_vm_imm14_ring_addressing_full_scratch() {
    let mut cp = [0.0f32; CONST_POOL_WORDS];
    cp[0] = 3.5;

    let words = vec![
        encode(Op::IConst, 0, 0, 0, 0),
        encode(Op::FConst, 1, 0, 0, 0),
        encode(Op::StF, 1, 0, 0, imm14_from_i32(-4096)),
        encode(Op::LdF, 2, 0, 0, imm14_from_i32(-4096)),
        encode(Op::Halt, 0, 0, 0, 0),
    ];
    let prog = mk_prog(words, cp);

    let mut worker = VmWorker::default();
    let lib = LibraryBank::default();
    let cfg = ExecConfig {
        fuel_max: 500,
        trace: false,
        trace_budget_bytes: 0,
    };

    let res = run_candidate(&mut worker, &prog, &lib, &cfg);
    assert_eq!(res.stop_reason, StopReason::Halt);
    approx_eq(worker.scratch[12_288], 3.5);
    approx_eq(worker.f[2], 3.5);
}

#[test]
fn agent1_vm_call_lib_round_trip() {
    let mut lib_cp = [0.0f32; CONST_POOL_WORDS];
    lib_cp[0] = 9.25;

    let lib_prog = mk_prog(
        vec![
            encode(Op::FConst, 0, 0, 0, 0),
            encode(Op::StF, 0, 0, 0, 0),
            encode(Op::Ret, 0, 0, 0, 0),
        ],
        lib_cp,
    );

    let cand_prog = mk_prog(
        vec![
            encode(Op::IConst, 0, 0, 0, 20),
            encode(Op::CallLib, 0, 0, 0, 0),
            encode(Op::LdF, 3, 0, 0, 0),
            encode(Op::Halt, 0, 0, 0, 0),
        ],
        [0.0; CONST_POOL_WORDS],
    );

    let mut bank = LibraryBank::default();
    bank.set_slot(0, lib_prog).expect("slot 0");

    let mut worker = VmWorker::default();
    let cfg = ExecConfig {
        fuel_max: 500,
        trace: false,
        trace_budget_bytes: 0,
    };

    let res = run_candidate(&mut worker, &cand_prog, &bank, &cfg);
    assert_eq!(res.stop_reason, StopReason::Halt);
    approx_eq(worker.scratch[20], 9.25);
    approx_eq(worker.f[3], 9.25);
}

#[test]
fn agent1_vm_vcmul_correctness() {
    let prog = mk_prog(
        vec![
            encode(Op::IConst, 0, 0, 0, 100),
            encode(Op::IConst, 1, 0, 0, 0),
            encode(Op::IConst, 2, 0, 0, 50),
            encode(Op::VCMul, 0, 1, 2, 3),
            encode(Op::Halt, 0, 0, 0, 0),
        ],
        [0.0; CONST_POOL_WORDS],
    );

    let mut worker = VmWorker::default();

    let x = [(1.0f32, 2.0f32), (3.0f32, -1.0f32), (-2.0f32, 0.5f32)];
    let y = [(4.0f32, -1.0f32), (-2.0f32, 2.0f32), (0.25f32, 3.0f32)];

    for (i, (re, im)) in x.iter().copied().enumerate() {
        worker.scratch[i * 2] = re;
        worker.scratch[i * 2 + 1] = im;
    }
    for (i, (re, im)) in y.iter().copied().enumerate() {
        worker.scratch[50 + (i * 2)] = re;
        worker.scratch[50 + (i * 2 + 1)] = im;
    }

    let lib = LibraryBank::default();
    let cfg = ExecConfig {
        fuel_max: 500,
        trace: false,
        trace_budget_bytes: 0,
    };

    let res = run_candidate(&mut worker, &prog, &lib, &cfg);
    assert_eq!(res.stop_reason, StopReason::Halt);

    let expected = [(6.0f32, 7.0f32), (-4.0f32, 8.0f32), (-2.0f32, -5.875f32)];
    for (i, (re, im)) in expected.iter().copied().enumerate() {
        approx_eq(worker.scratch[100 + i * 2], re);
        approx_eq(worker.scratch[100 + i * 2 + 1], im);
    }
}

#[test]
fn agent1_vm_vadd_threshold_path_correctness() {
    let len = 128u16;
    let prog = mk_prog(
        vec![
            encode(Op::IConst, 0, 0, 0, 700),
            encode(Op::IConst, 1, 0, 0, 100),
            encode(Op::IConst, 2, 0, 0, 300),
            encode(Op::VAdd, 0, 1, 2, len),
            encode(Op::Halt, 0, 0, 0, 0),
        ],
        [0.0; CONST_POOL_WORDS],
    );

    let mut worker = VmWorker::default();
    for i in 0..usize::from(len) {
        worker.scratch[100 + i] = (i as f32) * 0.25;
        worker.scratch[300 + i] = (i as f32) * 0.5;
    }

    let lib = LibraryBank::default();
    let cfg = ExecConfig {
        fuel_max: 5000,
        trace: false,
        trace_budget_bytes: 0,
    };

    let res = run_candidate(&mut worker, &prog, &lib, &cfg);
    assert_eq!(res.stop_reason, StopReason::Halt);

    for i in 0..usize::from(len) {
        let expected = worker.scratch[100 + i] + worker.scratch[300 + i];
        approx_eq(worker.scratch[700 + i], expected);
    }
}

#[test]
fn agent1_vm_vdot_threshold_path_correctness() {
    let len = 256u16;
    let prog = mk_prog(
        vec![
            encode(Op::IConst, 1, 0, 0, 1000),
            encode(Op::IConst, 2, 0, 0, 1400),
            encode(Op::VDot, 5, 1, 2, len),
            encode(Op::Halt, 0, 0, 0, 0),
        ],
        [0.0; CONST_POOL_WORDS],
    );

    let mut worker = VmWorker::default();
    let mut expected = 0.0f32;
    for i in 0..usize::from(len) {
        let x = (i as f32) * 0.1 - 2.0;
        let y = (i as f32) * 0.05 + 1.0;
        worker.scratch[1000 + i] = x;
        worker.scratch[1400 + i] = y;
        expected += x * y;
    }

    let lib = LibraryBank::default();
    let cfg = ExecConfig {
        fuel_max: 5000,
        trace: false,
        trace_budget_bytes: 0,
    };

    let res = run_candidate(&mut worker, &prog, &lib, &cfg);
    assert_eq!(res.stop_reason, StopReason::Halt);
    approx_eq(worker.f[5], expected);
}
