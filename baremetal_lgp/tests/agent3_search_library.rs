use std::fs;
use std::path::PathBuf;

use baremetal_lgp::library::bank::{LibraryBank, LibraryProgram};
use baremetal_lgp::library::promote::{promote_slot, PromoteError};
use baremetal_lgp::outer_loop::bandit::Exp3Bandit;
use baremetal_lgp::search::archive::{Archive, ArchiveInsert, Elite};
use baremetal_lgp::search::descriptors::{
    bin_id, bucket_code, bucket_entropy, bucket_fuel, bucket_ratio, build_descriptor,
    output_entropy_sketch, Descriptor, DescriptorInputs,
};
use baremetal_lgp::search::ir::{Block, CandidateCfg, Opcode, Terminator};
use baremetal_lgp::search::mutate::{mutate_candidate, MUTATION_OPERATOR_COUNT};
use baremetal_lgp::search::rng::Rng;

fn seed_candidate(score: f32) -> Elite {
    Elite {
        score,
        candidate: CandidateCfg::default(),
        code_size_words: 1,
        fuel_used: 1,
        desc: Descriptor {
            fuel_bucket: 0,
            code_bucket: 0,
            branch_bucket: 0,
            write_bucket: 0,
            entropy_bucket: 0,
            regime_profile: 0,
        },
    }
}

#[test]
fn agent3_descriptor_bin_id_packs_exact_bits() {
    let d = Descriptor {
        fuel_bucket: 3,
        code_bucket: 2,
        branch_bucket: 1,
        write_bucket: 0,
        entropy_bucket: 3,
        regime_profile: 0b1010,
    };
    let packed = bin_id(&d);
    let expected =
        3_u16 | (2_u16 << 2) | (1_u16 << 4) | (0_u16 << 6) | (3_u16 << 8) | (0b1010_u16 << 10);
    assert_eq!(packed, expected);
}

#[test]
fn agent3_bucket_boundaries_match_contract() {
    assert_eq!(bucket_fuel(0.25), 0);
    assert_eq!(bucket_fuel(0.50), 1);
    assert_eq!(bucket_fuel(0.75), 2);
    assert_eq!(bucket_fuel(0.751), 3);

    assert_eq!(bucket_code(128), 0);
    assert_eq!(bucket_code(256), 1);
    assert_eq!(bucket_code(512), 2);
    assert_eq!(bucket_code(513), 3);

    assert_eq!(bucket_ratio(0.05), 0);
    assert_eq!(bucket_ratio(0.15), 1);
    assert_eq!(bucket_ratio(0.30), 2);
    assert_eq!(bucket_ratio(0.31), 3);

    assert_eq!(bucket_entropy(1.0), 0);
    assert_eq!(bucket_entropy(2.0), 1);
    assert_eq!(bucket_entropy(3.0), 2);
    assert_eq!(bucket_entropy(3.1), 3);
}

#[test]
fn agent3_entropy_sketch_is_low_for_constant_outputs() {
    let out = vec![0.0_f32; 64];
    let entropy = output_entropy_sketch(&out);
    assert!(entropy <= 1e-6);
}

#[test]
fn agent3_descriptor_builder_maps_all_components() {
    let desc = build_descriptor(DescriptorInputs {
        fuel_used: 50,
        fuel_max: 100,
        code_size_words: 300,
        branch_count: 20,
        store_count: 5,
        total_insns: 100,
        output_entropy: 2.2,
        regime_profile_bits: 14,
    });
    assert_eq!(desc.fuel_bucket, 1);
    assert_eq!(desc.code_bucket, 2);
    assert_eq!(desc.branch_bucket, 2);
    assert_eq!(desc.write_bucket, 0);
    assert_eq!(desc.entropy_bucket, 2);
    assert_eq!(desc.regime_profile, 14);
}

#[test]
fn agent3_archive_insert_replace_rules_hold() {
    let mut archive = Archive::new();
    let bin = 123_u16;
    assert_eq!(
        archive.insert(bin, seed_candidate(1.0)),
        ArchiveInsert::Inserted
    );
    assert_eq!(archive.filled, 1);
    assert_eq!(
        archive.insert(bin, seed_candidate(0.9)),
        ArchiveInsert::Kept
    );
    assert_eq!(
        archive.insert(bin, seed_candidate(1.1)),
        ArchiveInsert::Replaced
    );
    assert_eq!(archive.filled, 1);
}

#[test]
fn agent3_mutation_can_force_calllib_insertion_pattern() {
    let parent = CandidateCfg::default();
    let archive = Archive::new();
    let mut rng = Rng::new(42);
    let mut weights = [0.0_f32; MUTATION_OPERATOR_COUNT];
    // Force insert CALL_LIB operator.
    weights[7] = 1.0;
    let child = mutate_candidate(&parent, &archive, &mut rng, &weights);
    assert!(child.verify().is_ok());
    assert!(child.blocks.len() >= parent.blocks.len() + 1);

    let mut found_pattern = false;
    for block in &child.blocks {
        let has_in = block
            .insns
            .iter()
            .any(|insn| insn.opcode == Opcode::LdMU32 && insn.imm14 == 0);
        let has_out = block
            .insns
            .iter()
            .any(|insn| insn.opcode == Opcode::LdMU32 && insn.imm14 == 2);
        let has_call = block
            .insns
            .iter()
            .any(|insn| insn.opcode == Opcode::CallLib);
        if has_in && has_out && has_call {
            found_pattern = true;
            break;
        }
    }
    assert!(
        found_pattern,
        "CALL_LIB insertion block pattern was not found"
    );
}

#[test]
fn agent3_library_seeds_expected_slots() {
    let bank = LibraryBank::new_seeded();
    assert_eq!(bank.slots.len(), 256);
    for idx in 0..20 {
        assert!(bank.slots[idx].is_some(), "slot {idx} should be seeded");
    }
    for idx in 20..256 {
        assert!(bank.slots[idx].is_none(), "slot {idx} should be empty");
    }
}

#[test]
fn agent3_promote_slot_validates_inputs() {
    let mut bank = LibraryBank::new_seeded();
    let program = LibraryProgram::new(vec![1, 2, 3], [0.0; 128]);
    promote_slot(&mut bank, 42, program, true).expect("promotion should work");
    assert_eq!(bank.epoch, 1);

    let bad = LibraryProgram::new(vec![0_u32; 2048], [0.0; 128]);
    let err = promote_slot(&mut bank, 43, bad, false).expect_err("must reject oversized program");
    assert!(matches!(err, PromoteError::InvalidProgram(_)));
}

#[test]
fn agent3_bandit_updates_and_persists_weights() {
    let mut bandit = Exp3Bandit::new(
        [1.0 / MUTATION_OPERATOR_COUNT as f32; MUTATION_OPERATOR_COUNT],
        0.12,
    );
    bandit.update_from_reward(2, 0.4);
    bandit.update_from_reward(7, -0.2);
    let sum = bandit.weights.iter().sum::<f32>();
    assert!((sum - 1.0).abs() < 1e-4);

    let temp = unique_temp_dir("agent3_bandit");
    fs::create_dir_all(&temp).expect("create temp dir");
    bandit.write_weights_file(&temp).expect("write weights");
    let body = fs::read_to_string(temp.join("mutation_weights.json")).expect("read file");
    assert!(body.contains("\"weights\""));
}

#[test]
fn agent3_loop_term_transform_can_insert_bridge_jump() {
    let mut parent = CandidateCfg::default();
    parent.blocks = vec![
        Block {
            insns: Vec::new(),
            term: Terminator::Loop {
                reg: 0,
                body_target: 1,
                exit_target: 2,
                imm14: 0,
            },
        },
        Block {
            insns: Vec::new(),
            term: Terminator::Halt,
        },
        Block {
            insns: Vec::new(),
            term: Terminator::Halt,
        },
    ];
    parent.entry = 0;
    let archive = Archive::new();
    let mut weights = [0.0_f32; MUTATION_OPERATOR_COUNT];
    weights[8] = 1.0;

    let mut saw_bridge = false;
    for seed in 1..2048_u64 {
        let mut rng = Rng::new(seed);
        let child = mutate_candidate(&parent, &archive, &mut rng, &weights);
        if child.blocks.len() <= parent.blocks.len() {
            continue;
        }
        let bridge_target = child.blocks.last().and_then(|b| match b.term {
            Terminator::Jump { target, .. } => Some(target),
            _ => None,
        });
        if bridge_target == Some(1) {
            saw_bridge = true;
            break;
        }
    }
    assert!(
        saw_bridge,
        "expected loop transform to create a bridge jump block"
    );
}

fn unique_temp_dir(prefix: &str) -> PathBuf {
    let mut path = std::env::temp_dir();
    let pid = std::process::id();
    let nanos = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map_or(0_u128, |d| d.as_nanos());
    path.push(format!("{prefix}_{pid}_{nanos}"));
    path
}
