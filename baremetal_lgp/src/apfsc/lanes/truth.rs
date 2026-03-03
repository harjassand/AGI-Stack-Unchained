use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::Instant;

use rayon::prelude::*;

use crate::apfsc::candidate::{clone_with_mutation, rehash_candidate, CandidateBundle};
use crate::apfsc::config::Phase1Config;
use crate::apfsc::errors::Result;
use crate::apfsc::schedule_pack::with_predicted_cost;
use crate::apfsc::scir::ast::{AlienMutationVector, ScirNode, ScirOp};
use crate::apfsc::types::{PredictedCost, PromotionClass};

#[derive(Debug, Clone, Copy, serde::Serialize, serde::Deserialize, PartialEq, Eq)]
pub struct TruthGenerateProfile {
    pub calls: u64,
    pub total_ms: u64,
    pub last_ms: u64,
}

static TRUTH_GENERATE_CALLS: AtomicU64 = AtomicU64::new(0);
static TRUTH_GENERATE_TOTAL_MS: AtomicU64 = AtomicU64::new(0);
static TRUTH_GENERATE_LAST_MS: AtomicU64 = AtomicU64::new(0);

struct TruthGenerateTimer {
    started: Instant,
}

impl TruthGenerateTimer {
    fn new() -> Self {
        Self {
            started: Instant::now(),
        }
    }
}

impl Drop for TruthGenerateTimer {
    fn drop(&mut self) {
        let elapsed_ms = self
            .started
            .elapsed()
            .as_millis()
            .min(u128::from(u64::MAX)) as u64;
        TRUTH_GENERATE_CALLS.fetch_add(1, Ordering::Relaxed);
        TRUTH_GENERATE_TOTAL_MS.fetch_add(elapsed_ms, Ordering::Relaxed);
        TRUTH_GENERATE_LAST_MS.store(elapsed_ms, Ordering::Relaxed);
    }
}

pub fn truth_generate_profile() -> TruthGenerateProfile {
    TruthGenerateProfile {
        calls: TRUTH_GENERATE_CALLS.load(Ordering::Relaxed),
        total_ms: TRUTH_GENERATE_TOTAL_MS.load(Ordering::Relaxed),
        last_ms: TRUTH_GENERATE_LAST_MS.load(Ordering::Relaxed),
    }
}

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize, PartialEq, Eq)]
pub struct DiscoveryConstraint {
    pub discovery_id: String,
    pub discovery_class: String,
    pub symbolic_pde_equation: String,
}

pub fn generate(active: &CandidateBundle, cfg: &Phase1Config) -> Result<Vec<CandidateBundle>> {
    let _timer = TruthGenerateTimer::new();
    let mut out = Vec::new();
    let root = inferred_root();
    let arxiv_staleness_threshold_seconds =
        crate::apfsc::afferent::arxiv_staleness_threshold_seconds(cfg, 6 * 60 * 60);
    let _ = crate::apfsc::afferent::refresh_arxiv_external_snapshot_if_stale(
        &root,
        arxiv_staleness_threshold_seconds,
        24,
    );
    let tensor_seed = crate::apfsc::afferent::load_external_tensor_seed(&root);
    let discovery_constraints = runtime_discovery_constraints();
    let discovery_hint = discovery_constraints.first().map(|d| {
        let short_id = d.discovery_id.chars().take(12).collect::<String>();
        format!("{}:{}", d.discovery_class, short_id)
    });
    // Standard structural/parametric queue.
    // Keep one explicit Alien opcode candidate early so low-budget truth lanes still emit it.
    out.push(mutation_add_alien_opcode(active, "alien_opcode_truth")?);
    out.push(mutation_add_afferent_node(active, 0, "afferent_cpu_load")?);
    out.push(mutation_add_afferent_node(active, 1, "afferent_thermal")?);
    out.push(mutation_add_afferent_node(
        active,
        3,
        "afferent_exogenous_cortex_arxiv",
    )?);
    out.push(mutation_add_ectoderm_primitives(active)?);
    out.push(mutation_add_lag(active)?);
    out.push(mutation_scan_medium(active)?);
    out.push(mutation_add_feature_node(
        active,
        "run_length_bucket",
        ScirOp::RunLengthBucket { buckets: 8 },
    )?);
    out.push(mutation_add_feature_node(
        active,
        "mod_counter_4",
        ScirOp::ModCounter { modulus: 4 },
    )?);
    out.push(mutation_add_feature_node(
        active,
        "delimiter_reset_newline",
        ScirOp::DelimiterReset { byte: b'\n' },
    )?);
    out.push(mutation_add_feature_node(
        active,
        "rolling_hash_2",
        ScirOp::RollingHash { n: 2, buckets: 16 },
    )?);
    out.push(mutation_add_feature_node(
        active,
        "rolling_hash_3",
        ScirOp::RollingHash { n: 3, buckets: 16 },
    )?);
    out.push(mutation_identity_macro_swap(active)?);
    out.push(mutation_scale_heads(
        active,
        0.95,
        "increase_readout_regularization",
    )?);
    out.push(mutation_scale_heads(
        active,
        1.05,
        "decrease_readout_regularization",
    )?);
    out.push(mutation_widen_concat_block(active)?);
    out.push(mutation_adjust_tile_bytes(active, cfg)?);

    // Alien queue remains enabled so Symbolic/HDC/Sparse compete under the same gates.
    out.push(mutation_add_alien_sidecar(
        active,
        "splice_SymbolicTapeExecutor_truth",
        ScirOp::SymbolicTape { cells: 16 },
        16,
        false,
    )?);
    out.push(mutation_add_alien_sidecar(
        active,
        "splice_SparseRouter_truth",
        ScirOp::SparseRouter {
            experts: 16,
            topk: 2,
        },
        16,
        true,
    )?);
    let hdc_dim = active
        .arch_program
        .nodes
        .iter()
        .find(|n| n.id == active.arch_program.outputs.feature_node)
        .map(|n| n.out_dim)
        .unwrap_or(16);
    out.push(mutation_add_alien_sidecar(
        active,
        "splice_HdcPermute_truth",
        ScirOp::HdcPermute { shift: 3 },
        hdc_dim,
        true,
    )?);
    let class_r = class_r_budget(cfg);
    for idx in 0..class_r {
        if is_hamiltonian_slot(idx, class_r) {
            out.push(mutation_add_class_r_hamiltonian_particle(
                active,
                cfg,
                idx as u32,
                discovery_hint.as_deref(),
            )?);
        } else if is_pde_slot(idx, class_r) {
            out.push(mutation_add_class_r_pde_particle(
                active,
                cfg,
                idx as u32,
                discovery_hint.as_deref(),
                tensor_seed.as_ref(),
            )?);
        } else {
            out.push(mutation_add_class_r_particle(active, idx as u32)?);
        }
    }
    let class_h = class_h_budget(cfg);
    for idx in 0..class_h {
        out.push(mutation_add_class_h_hypothesis_particle(
            active,
            cfg,
            idx as u32,
            discovery_hint.as_deref(),
        )?);
    }
    let class_m = class_m_budget(cfg);
    for idx in 0..class_m {
        out.push(mutation_add_class_m_probe_particle(
            active,
            cfg,
            idx as u32,
            discovery_hint.as_deref(),
            tensor_seed.as_ref(),
        )?);
        out.push(mutation_add_demon_lane_worker_particle(
            active,
            cfg,
            idx as u32,
            discovery_hint.as_deref(),
            tensor_seed.as_ref(),
        )?);
    }
    out.truncate(
        cfg.lanes
            .max_truth_candidates
            .min(cfg.lanes.max_public_candidates / 2),
    );
    Ok(out)
}

fn class_r_budget(cfg: &Phase1Config) -> usize {
    let cap = ((cfg.lanes.max_public_candidates as f64) * 0.02).ceil() as usize;
    cap.max(1)
}

fn class_h_budget(cfg: &Phase1Config) -> usize {
    let cap = ((cfg.lanes.max_public_candidates as f64) * 0.01).ceil() as usize;
    cap.max(1)
}

fn class_m_budget(cfg: &Phase1Config) -> usize {
    let cap = ((cfg.lanes.max_public_candidates as f64) * 0.01).ceil() as usize;
    cap.max(1)
}

fn is_hamiltonian_slot(idx: usize, budget: usize) -> bool {
    // Reserve ~40% of Class-R particles for physically grounded symmetry objectives.
    if budget <= 1 {
        true
    } else {
        idx < ((budget as f64) * 0.4).ceil() as usize
    }
}

fn is_pde_slot(idx: usize, budget: usize) -> bool {
    if budget <= 2 {
        return false;
    }
    let hamiltonian = ((budget as f64) * 0.4).ceil() as usize;
    let pde_budget = ((budget as f64) * 0.3).ceil() as usize;
    idx >= hamiltonian && idx < hamiltonian.saturating_add(pde_budget)
}

pub fn generate_phase3(
    active: &CandidateBundle,
    cfg: &Phase1Config,
) -> Result<Vec<CandidateBundle>> {
    let mut out = generate(active, cfg)?;

    let mut schedule = active.schedule_pack.clone();
    schedule.scheduler_class = Some(crate::apfsc::types::SchedulerClass::EventSparse);
    schedule.memory_law = Some(crate::apfsc::types::MemoryLawKind::RingSlots);
    schedule.learning_law = Some(crate::apfsc::types::LearningLawKind::ResidualAdaGrad);
    out.push(clone_with_mutation(
        active,
        "truth",
        "phase3_warm_scheduler_shift",
        PromotionClass::PWarm,
        active.arch_program.clone(),
        active.head_pack.clone(),
        active.state_pack.clone(),
        schedule,
        active.bridge_pack.clone(),
        BTreeMap::new(),
    )?);

    let mut schedule_a = active.schedule_pack.clone();
    schedule_a.scheduler_class = Some(crate::apfsc::types::SchedulerClass::SerialScan);
    schedule_a.memory_law = Some(crate::apfsc::types::MemoryLawKind::FlatState);
    schedule_a.learning_law = Some(crate::apfsc::types::LearningLawKind::HeadOnlyAdaGrad);
    out.push(clone_with_mutation(
        active,
        "truth",
        "phase3_structural_same_signature",
        PromotionClass::A,
        active.arch_program.clone(),
        active.head_pack.clone(),
        active.state_pack.clone(),
        schedule_a,
        active.bridge_pack.clone(),
        BTreeMap::new(),
    )?);

    out.truncate(cfg.lanes.max_truth_candidates.max(2));
    Ok(out)
}

fn mutation_add_alien_sidecar(
    active: &CandidateBundle,
    label: &str,
    op: ScirOp,
    out_dim: u32,
    input_from_feature: bool,
) -> Result<CandidateBundle> {
    let mut program = active.arch_program.clone();
    let feature = program.outputs.feature_node;
    let feature_dim = program
        .nodes
        .iter()
        .find(|n| n.id == feature)
        .map(|n| n.out_dim)
        .unwrap_or(1);
    let next = program
        .nodes
        .iter()
        .map(|n| n.id)
        .max()
        .unwrap_or(0)
        .saturating_add(1);

    let inputs = if input_from_feature {
        vec![feature]
    } else {
        Vec::new()
    };
    program.nodes.push(ScirNode {
        id: next,
        op,
        inputs,
        out_dim,
        mutable: false,
    });

    let join_id = next + 1;
    program.nodes.push(ScirNode {
        id: join_id,
        op: ScirOp::Concat,
        inputs: vec![feature, next],
        out_dim: feature_dim + out_dim,
        mutable: false,
    });
    program.outputs.feature_node = join_id;

    let mut head_pack = active.head_pack.clone();
    head_pack.native_head.in_dim += out_dim;
    head_pack
        .native_head
        .weights
        .extend(vec![0.0; (256 * out_dim) as usize]);
    head_pack.nuisance_head.in_dim += out_dim;
    head_pack
        .nuisance_head
        .weights
        .extend(vec![0.0; (256 * out_dim) as usize]);
    head_pack.residual_head.in_dim += out_dim;
    head_pack
        .residual_head
        .weights
        .extend(vec![0.0; (256 * out_dim) as usize]);

    let mut state = active.state_pack.clone();
    state.resid_weights.extend(vec![0.0; out_dim as usize]);

    clone_with_mutation(
        active,
        "truth",
        label,
        PromotionClass::A,
        program,
        head_pack,
        state,
        active.schedule_pack.clone(),
        None,
        BTreeMap::new(),
    )
}

fn mutation_add_alien_opcode(active: &CandidateBundle, label: &str) -> Result<CandidateBundle> {
    let mut program = active.arch_program.clone();
    let feature = program.outputs.feature_node;
    let feature_dim = program
        .nodes
        .iter()
        .find(|n| n.id == feature)
        .map(|n| n.out_dim)
        .unwrap_or(16);
    let next = program
        .nodes
        .iter()
        .map(|n| n.id)
        .max()
        .unwrap_or(0)
        .saturating_add(1);
    let alien_hash =
        crate::apfsc::artifacts::digest_json(&(active.manifest.candidate_hash.clone(), label))?;
    program.nodes.push(ScirNode {
        id: next,
        op: ScirOp::Alien {
            seed_hash: alien_hash,
            mutation_vector: AlienMutationVector {
                ops_added: vec![
                    "Alien::ImplicitFixedPoint".to_string(),
                    "Opcode[Self-Mutate]".to_string(),
                ],
                ops_removed: vec!["Dense::ExplicitUnroll".to_string()],
            },
            fused_ops_hint: 4,
        },
        inputs: vec![feature],
        out_dim: feature_dim,
        mutable: false,
    });
    program.outputs.feature_node = next;
    clone_with_mutation(
        active,
        "truth",
        label,
        PromotionClass::A,
        program,
        active.head_pack.clone(),
        active.state_pack.clone(),
        active.schedule_pack.clone(),
        None,
        BTreeMap::new(),
    )
}

fn mutation_add_ectoderm_primitives(active: &CandidateBundle) -> Result<CandidateBundle> {
    let mut program = active.arch_program.clone();
    let feature = program.outputs.feature_node;
    let mut next = program
        .nodes
        .iter()
        .map(|n| n.id)
        .max()
        .unwrap_or(0)
        .saturating_add(1);
    let mut new_probe_nodes = Vec::new();
    for channel in 0..=2u8 {
        let id = next;
        next = next.saturating_add(1);
        program.nodes.push(ScirNode {
            id,
            op: ScirOp::EctodermPrimitive { channel },
            inputs: vec![feature],
            out_dim: 1,
            mutable: false,
        });
        new_probe_nodes.push(id);
    }
    for pid in new_probe_nodes {
        if !program.outputs.probe_nodes.contains(&pid) {
            program.outputs.probe_nodes.push(pid);
        }
    }

    let mut cand = clone_with_mutation(
        active,
        "truth",
        "inject_ectoderm_primitives",
        PromotionClass::PCold,
        program,
        active.head_pack.clone(),
        active.state_pack.clone(),
        active.schedule_pack.clone(),
        None,
        BTreeMap::new(),
    )?;
    cand.build_meta.notes = Some(
        "Ectoderm primitives: dynamic action sinks for allowance, class-r difficulty, pioneer timeslice"
            .to_string(),
    );
    rehash_candidate(&mut cand)?;
    Ok(cand)
}

fn mutation_add_afferent_node(
    active: &CandidateBundle,
    channel: u8,
    label: &str,
) -> Result<CandidateBundle> {
    let mut program = active.arch_program.clone();
    let feature = program.outputs.feature_node;
    let feature_dim = program
        .nodes
        .iter()
        .find(|n| n.id == feature)
        .map(|n| n.out_dim)
        .unwrap_or(1);
    let next = program
        .nodes
        .iter()
        .map(|n| n.id)
        .max()
        .unwrap_or(0)
        .saturating_add(1);
    program.nodes.push(ScirNode {
        id: next,
        op: ScirOp::AfferentNode { channel },
        inputs: Vec::new(),
        out_dim: feature_dim,
        mutable: false,
    });
    let join = next.saturating_add(1);
    program.nodes.push(ScirNode {
        id: join,
        op: ScirOp::Concat,
        inputs: vec![feature, next],
        out_dim: feature_dim.saturating_mul(2),
        mutable: false,
    });
    program.outputs.feature_node = join;

    let mut head_pack = active.head_pack.clone();
    head_pack.native_head.in_dim = head_pack.native_head.in_dim.saturating_add(feature_dim);
    head_pack
        .native_head
        .weights
        .extend(vec![0.0; (256 * feature_dim) as usize]);
    head_pack.nuisance_head.in_dim = head_pack.nuisance_head.in_dim.saturating_add(feature_dim);
    head_pack
        .nuisance_head
        .weights
        .extend(vec![0.0; (256 * feature_dim) as usize]);
    head_pack.residual_head.in_dim = head_pack.residual_head.in_dim.saturating_add(feature_dim);
    head_pack
        .residual_head
        .weights
        .extend(vec![0.0; (256 * feature_dim) as usize]);

    let mut state = active.state_pack.clone();
    state.resid_weights.extend(vec![0.0; feature_dim as usize]);

    let mut cand = clone_with_mutation(
        active,
        "truth",
        label,
        PromotionClass::A,
        program,
        head_pack,
        state,
        active.schedule_pack.clone(),
        None,
        BTreeMap::new(),
    )?;
    let source = if channel == 3 {
        "exogenous cortex (arXiv cond-mat.supr-con + physics.chem-ph)"
    } else {
        "host telemetry snapshot"
    };
    cand.build_meta.notes = Some(format!(
        "AfferentNode channel {channel} wired from {source}"
    ));
    rehash_candidate(&mut cand)?;
    Ok(cand)
}

fn mutation_add_class_r_particle(
    active: &CandidateBundle,
    ordinal: u32,
) -> Result<CandidateBundle> {
    let mut program = active.arch_program.clone();
    let feature = program.outputs.feature_node;
    let feature_dim = program
        .nodes
        .iter()
        .find(|n| n.id == feature)
        .map(|n| n.out_dim)
        .unwrap_or(16);
    let next = program
        .nodes
        .iter()
        .map(|n| n.id)
        .max()
        .unwrap_or(0)
        .saturating_add(1);
    let seed_hash = crate::apfsc::artifacts::digest_json(&(
        "class_r",
        active.manifest.candidate_hash.clone(),
        ordinal,
    ))?;
    program.nodes.push(ScirNode {
        id: next,
        op: ScirOp::Alien {
            seed_hash,
            mutation_vector: AlienMutationVector {
                ops_added: vec![
                    "ClassR::AdversarialFractalNoise".to_string(),
                    "ClassR::CompressionWeaknessProbe".to_string(),
                ],
                ops_removed: vec!["Classical::StaticCurriculumBias".to_string()],
            },
            fused_ops_hint: 6,
        },
        inputs: vec![feature],
        out_dim: feature_dim,
        mutable: false,
    });
    program.outputs.feature_node = next;
    clone_with_mutation(
        active,
        "truth",
        &format!("class_r_particle_{}", ordinal),
        PromotionClass::PCold,
        program,
        active.head_pack.clone(),
        active.state_pack.clone(),
        active.schedule_pack.clone(),
        None,
        BTreeMap::new(),
    )
}

fn mutation_add_class_r_hamiltonian_particle(
    active: &CandidateBundle,
    cfg: &Phase1Config,
    ordinal: u32,
    discovery_hint: Option<&str>,
) -> Result<CandidateBundle> {
    let mut program = active.arch_program.clone();
    let feature = program.outputs.feature_node;
    let feature_dim = program
        .nodes
        .iter()
        .find(|n| n.id == feature)
        .map(|n| n.out_dim)
        .unwrap_or(16);
    let next = program
        .nodes
        .iter()
        .map(|n| n.id)
        .max()
        .unwrap_or(0)
        .saturating_add(1);
    let seed_hash = crate::apfsc::artifacts::digest_json(&(
        "class_r_hamiltonian",
        active.manifest.candidate_hash.clone(),
        ordinal,
    ))?;
    let difficulty = cfg
        .phase4
        .class_r_hamiltonian_difficulty_multiplier
        .clamp(0.25, 8.0);
    let fused_ops_hint = (8.0 * difficulty).round().clamp(4.0, 64.0) as u32;
    let mut ops_added = vec![
        "ClassR::HamiltonianSynth".to_string(),
        "ClassR::EnergyConservation".to_string(),
        "ClassR::NoetherGaugeEquivariance".to_string(),
        "ClassR::SymmetryEvenFn_FxEqFnegx".to_string(),
        "ClassR::GroundStateEigenvalueProbe".to_string(),
        format!("ClassR::HamiltonianDifficulty:{difficulty:.3}"),
    ];
    if difficulty >= 1.5 {
        ops_added.push("ClassR::ExtropyShock::Posit16Sim".to_string());
    }
    if difficulty >= 2.5 {
        ops_added.push("ClassR::ExtropyShock::Int4Gate".to_string());
    }
    if difficulty >= 4.0 {
        ops_added.push("ClassR::ExtropyShock::Int2Gate".to_string());
    }
    if let Some(hint) = discovery_hint {
        ops_added.push(format!("ClassR::DiscoveryConstraint::{hint}"));
    }
    program.nodes.push(ScirNode {
        id: next,
        op: ScirOp::Alien {
            seed_hash,
            mutation_vector: AlienMutationVector {
                ops_added,
                ops_removed: vec!["Classical::AsymmetricNoiseOnly".to_string()],
            },
            fused_ops_hint,
        },
        inputs: vec![feature],
        out_dim: feature_dim,
        mutable: false,
    });
    program.outputs.feature_node = next;
    let mut cand = clone_with_mutation(
        active,
        "truth",
        &format!("class_r_hamiltonian_particle_{}", ordinal),
        PromotionClass::PCold,
        program,
        active.head_pack.clone(),
        active.state_pack.clone(),
        active.schedule_pack.clone(),
        None,
        BTreeMap::new(),
    )?;
    cand.build_meta.notes = Some(format!(
        "HamiltonianSynth: symmetric manifold probe (energy conservation + gauge equivariance) difficulty={difficulty:.3}"
    ));
    rehash_candidate(&mut cand)?;
    Ok(cand)
}

fn mutation_add_class_r_pde_particle(
    active: &CandidateBundle,
    cfg: &Phase1Config,
    ordinal: u32,
    discovery_hint: Option<&str>,
    tensor_seed: Option<&crate::apfsc::afferent::AfferentTensorSeed>,
) -> Result<CandidateBundle> {
    let mut program = active.arch_program.clone();
    let feature = program.outputs.feature_node;
    let feature_dim = program
        .nodes
        .iter()
        .find(|n| n.id == feature)
        .map(|n| n.out_dim)
        .unwrap_or(16);
    let boundary = append_holographic_mera_boundary_node(
        active,
        &mut program,
        feature,
        feature_dim,
        "class_r_pde",
        ordinal,
        None,
        discovery_hint,
        tensor_seed,
    )?;
    let difficulty = cfg
        .phase4
        .class_r_hamiltonian_difficulty_multiplier
        .clamp(0.25, 8.0);
    let recursion_depth = (48.0 * difficulty).round().clamp(16.0, 4096.0) as u32;
    let next = program
        .nodes
        .iter()
        .map(|n| n.id)
        .max()
        .unwrap_or(0)
        .saturating_add(1);
    program.nodes.push(ScirNode {
        id: next,
        op: ScirOp::AlephZero { recursion_depth },
        inputs: vec![boundary],
        out_dim: feature_dim,
        mutable: false,
    });
    program.outputs.feature_node = next;
    let mut cand = clone_with_mutation(
        active,
        "truth",
        &format!("class_r_pde_particle_{}", ordinal),
        PromotionClass::PCold,
        program,
        active.head_pack.clone(),
        active.state_pack.clone(),
        active.schedule_pack.clone(),
        None,
        BTreeMap::new(),
    )?;
    cand.build_meta.notes = Some(format!(
        "PDE holographic substrate: MERA tensor network boundary projection (AdS/CFT shadow) + AlephZero depth={recursion_depth}; complexity_target=O(N log N); baseline_constraint={}",
        discovery_hint.unwrap_or("phase12_base")
    ));
    rehash_candidate(&mut cand)?;
    Ok(cand)
}

fn mutation_add_class_h_hypothesis_particle(
    active: &CandidateBundle,
    cfg: &Phase1Config,
    ordinal: u32,
    discovery_hint: Option<&str>,
) -> Result<CandidateBundle> {
    let mut program = active.arch_program.clone();
    let feature = program.outputs.feature_node;
    let feature_dim = program
        .nodes
        .iter()
        .find(|n| n.id == feature)
        .map(|n| n.out_dim)
        .unwrap_or(16);
    let next = program
        .nodes
        .iter()
        .map(|n| n.id)
        .max()
        .unwrap_or(0)
        .saturating_add(1);
    let difficulty = cfg
        .phase4
        .class_r_hamiltonian_difficulty_multiplier
        .clamp(0.25, 8.0);
    let hypothesis = if let Some(hint) = discovery_hint {
        let lower = hint.to_ascii_lowercase();
        if lower.contains("plasma") || lower.contains("tokamak") || lower.contains("fusion") {
            "fusion_tokamak_equivariance"
        } else if lower.contains("material") || lower.contains("resonance") {
            "room_temp_superconductor"
        } else if ordinal % 2 == 0 {
            "room_temp_superconductor"
        } else {
            "fusion_tokamak_equivariance"
        }
    } else if ordinal % 2 == 0 {
        "room_temp_superconductor"
    } else {
        "fusion_tokamak_equivariance"
    };
    let recursion_depth = (64.0 * difficulty).round().clamp(24.0, 4096.0) as u32;
    program.nodes.push(ScirNode {
        id: next,
        op: ScirOp::AlephZero { recursion_depth },
        inputs: vec![feature],
        out_dim: feature_dim,
        mutable: false,
    });
    program.outputs.feature_node = next;
    let mut cand = clone_with_mutation(
        active,
        "truth",
        &format!("class_h_hypothesis_{}_{}", hypothesis, ordinal),
        PromotionClass::PCold,
        program,
        active.head_pack.clone(),
        active.state_pack.clone(),
        active.schedule_pack.clone(),
        None,
        BTreeMap::new(),
    )?;
    cand.build_meta.notes = Some(format!(
        "Class-H hypothesis synthesis: target={hypothesis}, boundary=PDE-constraint-mutation, aleph_depth={recursion_depth}, inherited_constraint={}",
        discovery_hint.unwrap_or("phase12_base")
    ));
    rehash_candidate(&mut cand)?;
    Ok(cand)
}

fn mutation_add_class_m_probe_particle(
    active: &CandidateBundle,
    cfg: &Phase1Config,
    ordinal: u32,
    discovery_hint: Option<&str>,
    tensor_seed: Option<&crate::apfsc::afferent::AfferentTensorSeed>,
) -> Result<CandidateBundle> {
    let mut program = active.arch_program.clone();
    let feature = program.outputs.feature_node;
    let feature_dim = program
        .nodes
        .iter()
        .find(|n| n.id == feature)
        .map(|n| n.out_dim)
        .unwrap_or(16);
    let difficulty = cfg
        .phase4
        .class_r_hamiltonian_difficulty_multiplier
        .clamp(0.25, 8.0);
    let target = class_m_target_from_hint(ordinal, discovery_hint);
    let boundary = append_holographic_mera_boundary_node(
        active,
        &mut program,
        feature,
        feature_dim,
        "class_m_material",
        ordinal,
        Some(target),
        discovery_hint,
        tensor_seed,
    )?;
    let recursion_depth = (80.0 * difficulty).round().clamp(32.0, 4096.0) as u32;
    let next = program
        .nodes
        .iter()
        .map(|n| n.id)
        .max()
        .unwrap_or(0)
        .saturating_add(1);
    program.nodes.push(ScirNode {
        id: next,
        op: ScirOp::AlephZero { recursion_depth },
        inputs: vec![boundary],
        out_dim: feature_dim,
        mutable: false,
    });
    program.outputs.feature_node = next;

    let mut cand = clone_with_mutation(
        active,
        "truth",
        &format!("class_m_probe_{}_{}", target, ordinal),
        PromotionClass::PCold,
        program,
        active.head_pack.clone(),
        active.state_pack.clone(),
        active.schedule_pack.clone(),
        None,
        BTreeMap::new(),
    )?;
    cand.build_meta.notes = Some(format!(
        "Class-M material synthesis: objective=GroundStateEigenvector (no temporal rollout), output_geometry=Boundary2D(u,v,shadow_amp,Element_ID)->xyz, topology=MERA, complexity_target=O(N log N), target={target}; fitness_baseline={}",
        discovery_hint.unwrap_or("class_h_default")
    ));
    rehash_candidate(&mut cand)?;
    Ok(cand)
}

fn mutation_add_demon_lane_worker_particle(
    active: &CandidateBundle,
    cfg: &Phase1Config,
    ordinal: u32,
    discovery_hint: Option<&str>,
    tensor_seed: Option<&crate::apfsc::afferent::AfferentTensorSeed>,
) -> Result<CandidateBundle> {
    let mut program = active.arch_program.clone();
    let feature = program.outputs.feature_node;
    let feature_dim = program
        .nodes
        .iter()
        .find(|n| n.id == feature)
        .map(|n| n.out_dim)
        .unwrap_or(16);
    let target = class_m_target_from_hint(ordinal, discovery_hint);
    let boundary = append_holographic_mera_boundary_node(
        active,
        &mut program,
        feature,
        feature_dim,
        "demon_lane_class_m",
        ordinal,
        Some(target),
        discovery_hint,
        tensor_seed,
    )?;
    let demon_id = program
        .nodes
        .iter()
        .map(|n| n.id)
        .max()
        .unwrap_or(0)
        .saturating_add(1);
    let demon_hash = crate::apfsc::artifacts::digest_json(&(
        "demon_lane",
        active.manifest.candidate_hash.clone(),
        ordinal,
        target,
    ))?;
    program.nodes.push(ScirNode {
        id: demon_id,
        op: ScirOp::Alien {
            seed_hash: demon_hash,
            mutation_vector: AlienMutationVector {
                ops_added: vec![
                    "DemonLane::PolyphasicWorker".to_string(),
                    "DemonLane::Cosmology::SolarFlareThermalShock".to_string(),
                    "DemonLane::Cosmology::NeutronStarGravity".to_string(),
                    "DemonLane::Cosmology::AbsoluteZeroCryoShock".to_string(),
                    "ClassM::AdversarialEigenStateStress".to_string(),
                ],
                ops_removed: vec!["Classical::SingleRegimeValidation".to_string()],
            },
            fused_ops_hint: 24,
        },
        inputs: vec![boundary],
        out_dim: feature_dim,
        mutable: false,
    });
    let recursion_depth = (96.0
        * cfg
            .phase4
            .class_r_hamiltonian_difficulty_multiplier
            .clamp(0.25, 8.0))
    .round()
    .clamp(48.0, 4096.0) as u32;
    let aleph_id = demon_id.saturating_add(1);
    program.nodes.push(ScirNode {
        id: aleph_id,
        op: ScirOp::AlephZero { recursion_depth },
        inputs: vec![demon_id],
        out_dim: feature_dim,
        mutable: false,
    });
    program.outputs.feature_node = aleph_id;
    let mut cand = clone_with_mutation(
        active,
        "truth",
        &format!("demon_lane_class_m_{}_{}", target, ordinal),
        PromotionClass::PCold,
        program,
        active.head_pack.clone(),
        active.state_pack.clone(),
        active.schedule_pack.clone(),
        None,
        BTreeMap::new(),
    )?;
    cand.build_meta.notes = Some(format!(
        "Demon Lane adversarial cosmology worker: validates {target} against solar-flare thermal shock, neutron-star gravity, and absolute-zero affine stress"
    ));
    rehash_candidate(&mut cand)?;
    Ok(cand)
}

fn class_m_target_from_hint<'a>(ordinal: u32, discovery_hint: Option<&'a str>) -> &'a str {
    if let Some(hint) = discovery_hint {
        let lower = hint.to_ascii_lowercase();
        if lower.contains("plasma") || lower.contains("tokamak") || lower.contains("fusion") {
            return "fusion_tokamak_lattice";
        }
        return "room_temp_superconductor_lattice";
    }
    if ordinal.is_multiple_of(2) {
        "room_temp_superconductor_lattice"
    } else {
        "fusion_tokamak_lattice"
    }
}

#[allow(clippy::too_many_arguments)]
fn append_holographic_mera_boundary_node(
    active: &CandidateBundle,
    program: &mut crate::apfsc::scir::ast::ScirProgram,
    input_node: u32,
    out_dim: u32,
    scope: &str,
    ordinal: u32,
    class_m_target: Option<&str>,
    discovery_hint: Option<&str>,
    tensor_seed: Option<&crate::apfsc::afferent::AfferentTensorSeed>,
) -> Result<u32> {
    let tensor_seed_signature = tensor_seed.map(|seed| {
        seed.atomic_numbers
            .iter()
            .take(24)
            .map(|z| z.to_string())
            .collect::<Vec<_>>()
            .join("_")
    });
    let next = program
        .nodes
        .iter()
        .map(|n| n.id)
        .max()
        .unwrap_or(0)
        .saturating_add(1);
    let seed_hash = crate::apfsc::artifacts::digest_json(&(
        "holographic_mera",
        scope,
        active.manifest.candidate_hash.clone(),
        ordinal,
        class_m_target.unwrap_or("none"),
        tensor_seed_signature,
    ))?;
    let mut ops_added = vec![
        "PDE::TensorNetwork::MERA".to_string(),
        "PDE::BoundaryProjection::AdS_CFT_2D".to_string(),
        "PDE::ComplexityTarget::O(NlogN)".to_string(),
        "PDE::NoVoxel3DVolumeSimulation".to_string(),
    ];
    if let Some(target) = class_m_target {
        ops_added.push(format!("ClassM::Target::{target}"));
        ops_added.push("ClassM::Objective::EigenvalueApproximation".to_string());
        ops_added.push("ClassM::Oracle::GroundStateEigenvector".to_string());
    }
    if let Some(hint) = discovery_hint {
        ops_added.push(format!("DiscoveryConstraint::{hint}"));
    }
    let mut fused_ops_hint: u32 = if class_m_target.is_some() { 20 } else { 14 };
    if let Some(seed) = tensor_seed {
        let seed_z = seed
            .atomic_numbers
            .iter()
            .take(16)
            .map(|v| v.to_string())
            .collect::<Vec<_>>()
            .join("_");
        ops_added.push("MERA::BoundaryPriming::Channel3AfferentTensorSeed".to_string());
        ops_added.push(format!("MERA::BoundarySeed::Formula::{}", seed.formula));
        ops_added.push(format!("MERA::BoundarySeed::AtomicZ::{}", seed_z));
        if let Some(lattice) = &seed.lattice_hint {
            ops_added.push(format!("MERA::BoundarySeed::Lattice::{lattice}"));
        }
        if let Some(tc_kelvin) = seed.tc_kelvin {
            ops_added.push(format!("MERA::BoundarySeed::TcKelvin::{tc_kelvin:.3}"));
        }
        fused_ops_hint = fused_ops_hint.saturating_add(seed.atomic_numbers.len().min(10) as u32);
    }
    program.nodes.push(ScirNode {
        id: next,
        op: ScirOp::Alien {
            seed_hash,
            mutation_vector: AlienMutationVector {
                ops_added,
                ops_removed: vec![
                    "PDE::NavierStokesVoxel3D".to_string(),
                    "PDE::BruteForceVolumeGrid".to_string(),
                ],
            },
            fused_ops_hint,
        },
        inputs: vec![input_node],
        out_dim,
        mutable: false,
    });
    Ok(next)
}

fn inferred_root() -> PathBuf {
    if let Ok(root) = std::env::var("APFSC_ROOT") {
        return PathBuf::from(root);
    }
    if let Ok(home) = std::env::var("HOME") {
        return Path::new(&home).join(".apfsc");
    }
    PathBuf::from(".apfsc")
}

pub fn load_discovery_constraints(root: &Path, limit: usize) -> Result<Vec<DiscoveryConstraint>> {
    let mut out = Vec::<DiscoveryConstraint>::new();
    let mut rows = Vec::<(u64, PathBuf)>::new();
    collect_discovery_json_recursive(&root.join("discoveries"), &mut rows)?;
    rows.sort_by(|a, b| b.0.cmp(&a.0));
    for (_, path) in rows {
        if path.file_name().and_then(|s| s.to_str()) == Some("stream.jsonl") {
            continue;
        }
        let value = match crate::apfsc::artifacts::read_json::<serde_json::Value>(&path) {
            Ok(v) => v,
            Err(_) => continue,
        };
        let Some(eq) = value
            .get("symbolic_pde_equation")
            .and_then(|v| v.as_str())
            .map(ToString::to_string)
        else {
            continue;
        };
        let discovery_id = value
            .get("discovery_id")
            .and_then(|v| v.as_str())
            .map(ToString::to_string)
            .unwrap_or_else(|| {
                path.file_stem()
                    .and_then(|s| s.to_str())
                    .unwrap_or("discovery_unknown")
                    .to_string()
            });
        let discovery_class = value
            .get("discovery_class")
            .and_then(|v| v.as_str())
            .unwrap_or("Fractal PDE Closure")
            .to_string();
        out.push(DiscoveryConstraint {
            discovery_id,
            discovery_class,
            symbolic_pde_equation: eq,
        });
        if out.len() >= limit.max(1) {
            break;
        }
    }
    Ok(out)
}

fn collect_discovery_json_recursive(dir: &Path, rows: &mut Vec<(u64, PathBuf)>) -> Result<()> {
    if !dir.exists() {
        return Ok(());
    }
    for entry in fs::read_dir(dir).map_err(|e| crate::apfsc::errors::io_err(dir, e))? {
        let entry = entry.map_err(|e| crate::apfsc::errors::io_err(dir, e))?;
        let path = entry.path();
        let file_type = entry
            .file_type()
            .map_err(|e| crate::apfsc::errors::io_err(&path, e))?;
        if file_type.is_dir() {
            collect_discovery_json_recursive(&path, rows)?;
            continue;
        }
        if !file_type.is_file() || path.extension().and_then(|s| s.to_str()) != Some("json") {
            continue;
        }
        let modified = entry
            .metadata()
            .map_err(|e| crate::apfsc::errors::io_err(&path, e))?
            .modified()
            .ok()
            .and_then(|t| t.duration_since(std::time::UNIX_EPOCH).ok())
            .map(|d| d.as_secs())
            .unwrap_or(0);
        rows.push((modified, path));
    }
    Ok(())
}

fn runtime_discovery_constraints() -> Vec<DiscoveryConstraint> {
    let root = inferred_root();
    let runtime_path = root.join("runtime").join("discovery_constraints.json");
    if runtime_path.exists() {
        if let Ok(v) = crate::apfsc::artifacts::read_json::<Vec<DiscoveryConstraint>>(&runtime_path)
        {
            if !v.is_empty() {
                return v;
            }
        }
    }
    load_discovery_constraints(&root, 8).unwrap_or_default()
}

fn mutation_add_lag(active: &CandidateBundle) -> Result<CandidateBundle> {
    let mut program = active.arch_program.clone();
    if let Some(node) = program
        .nodes
        .iter_mut()
        .find(|n| matches!(n.op, ScirOp::LagBytes { .. }))
    {
        if let ScirOp::LagBytes { lags } = &mut node.op {
            if !lags.contains(&16) {
                lags.push(16);
                lags.sort();
                node.out_dim = lags.len() as u32;
                adjust_concat_dims(&mut program);
            }
        }
    }
    clone_with_mutation(
        active,
        "truth",
        "add_lag_feature",
        PromotionClass::S,
        program,
        active.head_pack.clone(),
        active.state_pack.clone(),
        active.schedule_pack.clone(),
        None,
        BTreeMap::new(),
    )
}

fn mutation_scan_medium(active: &CandidateBundle) -> Result<CandidateBundle> {
    let mut program = active.arch_program.clone();
    if let Some(scan) = program
        .nodes
        .iter_mut()
        .find(|n| matches!(n.op, ScirOp::SimpleScan { .. }))
    {
        if let ScirOp::SimpleScan { hidden_dim, .. } = &mut scan.op {
            *hidden_dim = (*hidden_dim + 16).min(128);
            scan.out_dim = *hidden_dim;
            adjust_concat_dims(&mut program);
        }
    }
    clone_with_mutation(
        active,
        "truth",
        "swap_simple_scan_medium",
        PromotionClass::A,
        program,
        active.head_pack.clone(),
        active.state_pack.clone(),
        active.schedule_pack.clone(),
        None,
        BTreeMap::new(),
    )
}

fn mutation_add_feature_node(
    active: &CandidateBundle,
    label: &str,
    op: ScirOp,
) -> Result<CandidateBundle> {
    let mut program = active.arch_program.clone();
    let feature = program.outputs.feature_node;
    let feature_dim = program
        .nodes
        .iter()
        .find(|n| n.id == feature)
        .map(|n| n.out_dim)
        .unwrap_or(1);

    let next = program
        .nodes
        .iter()
        .map(|n| n.id)
        .max()
        .unwrap_or(0)
        .saturating_add(1);

    let out_dim = match &op {
        ScirOp::RunLengthBucket { buckets } => *buckets,
        ScirOp::ModCounter { modulus } => *modulus,
        ScirOp::DelimiterReset { .. } => 1,
        ScirOp::RollingHash { buckets, .. } => *buckets,
        _ => 1,
    };

    program.nodes.push(ScirNode {
        id: next,
        op,
        inputs: Vec::new(),
        out_dim,
        mutable: false,
    });

    let join_id = next + 1;
    program.nodes.push(ScirNode {
        id: join_id,
        op: ScirOp::Concat,
        inputs: vec![feature, next],
        out_dim: feature_dim + out_dim,
        mutable: false,
    });
    program.outputs.feature_node = join_id;

    let mut head_pack = active.head_pack.clone();
    head_pack.native_head.in_dim += out_dim;
    head_pack
        .native_head
        .weights
        .extend(vec![0.0; (256 * out_dim) as usize]);
    head_pack.nuisance_head.in_dim += out_dim;
    head_pack
        .nuisance_head
        .weights
        .extend(vec![0.0; (256 * out_dim) as usize]);
    head_pack.residual_head.in_dim += out_dim;
    head_pack
        .residual_head
        .weights
        .extend(vec![0.0; (256 * out_dim) as usize]);

    let mut state = active.state_pack.clone();
    state.resid_weights.extend(vec![0.0; out_dim as usize]);

    clone_with_mutation(
        active,
        "truth",
        label,
        PromotionClass::A,
        program,
        head_pack,
        state,
        active.schedule_pack.clone(),
        None,
        BTreeMap::new(),
    )
}

fn mutation_identity_macro_swap(active: &CandidateBundle) -> Result<CandidateBundle> {
    let mut program = active.arch_program.clone();
    let feature = program.outputs.feature_node;
    let dim = program
        .nodes
        .iter()
        .find(|n| n.id == feature)
        .map(|n| n.out_dim)
        .unwrap_or(1);
    let id = program
        .nodes
        .iter()
        .map(|n| n.id)
        .max()
        .unwrap_or(0)
        .saturating_add(1);
    program.nodes.push(ScirNode {
        id,
        op: ScirOp::Linear {
            in_dim: dim,
            out_dim: dim,
            bias: false,
        },
        inputs: vec![feature],
        out_dim: dim,
        mutable: false,
    });
    program.outputs.feature_node = id;
    clone_with_mutation(
        active,
        "truth",
        "macro_swap_identity",
        PromotionClass::S,
        program,
        active.head_pack.clone(),
        active.state_pack.clone(),
        active.schedule_pack.clone(),
        None,
        BTreeMap::new(),
    )
}

fn mutation_scale_heads(
    active: &CandidateBundle,
    scale: f32,
    label: &str,
) -> Result<CandidateBundle> {
    let mut heads = active.head_pack.clone();
    for w in &mut heads.native_head.weights {
        *w *= scale;
    }
    for w in &mut heads.nuisance_head.weights {
        *w *= scale;
    }
    for w in &mut heads.residual_head.weights {
        *w *= scale;
    }

    clone_with_mutation(
        active,
        "truth",
        label,
        PromotionClass::S,
        active.arch_program.clone(),
        heads,
        active.state_pack.clone(),
        active.schedule_pack.clone(),
        None,
        BTreeMap::new(),
    )
}

fn mutation_widen_concat_block(active: &CandidateBundle) -> Result<CandidateBundle> {
    let mut state = active.state_pack.clone();
    state.core_weights.extend(vec![0.0; 16]);
    clone_with_mutation(
        active,
        "truth",
        "widen_feature_concat_safe_block",
        PromotionClass::A,
        active.arch_program.clone(),
        active.head_pack.clone(),
        state,
        active.schedule_pack.clone(),
        None,
        BTreeMap::new(),
    )
}

fn mutation_adjust_tile_bytes(
    active: &CandidateBundle,
    cfg: &Phase1Config,
) -> Result<CandidateBundle> {
    let mut schedule = active.schedule_pack.clone();
    let new_tile = (schedule.tile_bytes / 2).max(64 * 1024);
    schedule.tile_bytes = new_tile.min(cfg.limits.state_tile_bytes_max);
    schedule = with_predicted_cost(
        schedule,
        PredictedCost {
            wall_ms: 5.0,
            peak_rss_bytes: cfg.limits.state_tile_bytes_max,
            risk_score: 0.1,
        },
    );
    clone_with_mutation(
        active,
        "truth",
        "adjust_tile_bytes",
        PromotionClass::S,
        active.arch_program.clone(),
        active.head_pack.clone(),
        active.state_pack.clone(),
        schedule,
        None,
        BTreeMap::new(),
    )
}

fn adjust_concat_dims(program: &mut crate::apfsc::scir::ast::ScirProgram) {
    let mut dims = BTreeMap::<u32, u32>::new();
    for node in &mut program.nodes {
        let dim = match &node.op {
            ScirOp::ByteEmbedding { dim, .. } => *dim,
            ScirOp::LagBytes { lags } => lags.len() as u32,
            ScirOp::SimpleScan { hidden_dim, .. } => *hidden_dim,
            ScirOp::Concat => node
                .inputs
                .iter()
                .map(|i| *dims.get(i).unwrap_or(&0))
                .sum::<u32>(),
            _ => node.out_dim,
        };
        node.out_dim = dim;
        dims.insert(node.id, dim);
    }
}

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize, PartialEq)]
pub struct DemonLaneScenarioResult {
    pub scenario: String,
    pub ground_state_eigen: f64,
    pub spectral_gap: f64,
    pub stability_margin: f64,
    pub base_failure_threshold: f64,
    pub parsimony_penalty: f64,
    pub failure_threshold: f64,
    pub thermodynamic_surprisal: f64,
    pub survived: bool,
}

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize, PartialEq)]
pub struct DemonLaneVerdict {
    pub candidate_hash: String,
    pub ast_node_count: u32,
    pub parsimony_penalty: f64,
    pub baseline_ground_state: f64,
    pub survival_margin: f64,
    pub survived: bool,
    pub conductivity_gain: f32,
    pub thermal_stability_gain: f32,
    pub quantum_latency_gain: f32,
    pub scenarios: Vec<DemonLaneScenarioResult>,
}

#[derive(Clone, Copy)]
struct DemonScenario {
    name: &'static str,
    thermal_scale: f64,
    gravity_scale: f64,
    cryo_scale: f64,
}

pub fn demon_lane_verify_class_m(candidate: &CandidateBundle) -> DemonLaneVerdict {
    let signature = candidate_signature(candidate);
    let ast_node_count = candidate.arch_program.nodes.len() as u32;
    let parsimony_penalty = f64::from(ast_node_count) * 0.0001;
    let neutral = DemonScenario {
        name: "baseline",
        thermal_scale: 1.0,
        gravity_scale: 1.0,
        cryo_scale: 0.0,
    };
    let (baseline_ground_state, _) = demon_ground_state_and_gap(&signature, neutral);
    let scenarios = vec![
        DemonScenario {
            name: "solar_flare_thermal_shock",
            thermal_scale: 4.6,
            gravity_scale: 1.2,
            cryo_scale: 0.1,
        },
        DemonScenario {
            name: "neutron_star_gravity_well",
            thermal_scale: 1.1,
            gravity_scale: 11.5,
            cryo_scale: 0.2,
        },
        DemonScenario {
            name: "absolute_zero_cryo_shock",
            thermal_scale: 0.15,
            gravity_scale: 1.0,
            cryo_scale: 2.8,
        },
    ];

    let mut results = scenarios
        .par_iter()
        .map(|scenario| {
            let (ground, gap) = demon_ground_state_and_gap(&signature, *scenario);
            let delta =
                (ground - baseline_ground_state).abs() / baseline_ground_state.abs().max(1.0e-6);
            let stability_margin = (1.0 - delta).clamp(-8.0, 1.0);
            let gap_threshold = 1.0e-4 / scenario.gravity_scale.max(1.0);
            let base_failure_threshold = (stability_margin + 0.35).min(gap - gap_threshold);
            let failure_threshold = base_failure_threshold - parsimony_penalty;
            let survived = ground.is_finite() && gap.is_finite() && failure_threshold >= 0.0;
            DemonLaneScenarioResult {
                scenario: scenario.name.to_string(),
                ground_state_eigen: ground,
                spectral_gap: gap,
                stability_margin,
                base_failure_threshold,
                parsimony_penalty,
                failure_threshold,
                thermodynamic_surprisal: (-failure_threshold).max(0.0),
                survived,
            }
        })
        .collect::<Vec<_>>();
    results.sort_by(|a, b| a.scenario.cmp(&b.scenario));

    let survived = results.iter().all(|r| r.survived);
    let survival_margin = if results.is_empty() {
        -1.0
    } else {
        results
            .iter()
            .map(|r| r.failure_threshold)
            .fold(f64::INFINITY, f64::min)
    };
    let mean_margin = if results.is_empty() {
        0.0
    } else {
        results
            .iter()
            .map(|r| r.stability_margin.max(0.0))
            .sum::<f64>()
            / results.len() as f64
    };
    let mean_gap = if results.is_empty() {
        0.0
    } else {
        results.iter().map(|r| r.spectral_gap.max(0.0)).sum::<f64>() / results.len() as f64
    };

    DemonLaneVerdict {
        candidate_hash: candidate.manifest.candidate_hash.clone(),
        ast_node_count,
        parsimony_penalty,
        baseline_ground_state,
        survival_margin,
        survived,
        conductivity_gain: (mean_margin * 2.5).clamp(0.0, 4.0) as f32,
        thermal_stability_gain: (mean_margin * 3.0).clamp(0.0, 4.0) as f32,
        quantum_latency_gain: (mean_gap * 18.0).clamp(0.0, 4.0) as f32,
        scenarios: results,
    }
}

fn candidate_signature(candidate: &CandidateBundle) -> Vec<f64> {
    let mut out = Vec::with_capacity(candidate.arch_program.nodes.len().max(1));
    for (idx, node) in candidate.arch_program.nodes.iter().enumerate() {
        let op_weight = match &node.op {
            ScirOp::AlephZero { .. } => 1.45,
            ScirOp::Alien { .. } => 1.30,
            ScirOp::Subcortex { .. } => 1.20,
            ScirOp::SparseRouter { .. } | ScirOp::SparseEventQueue { .. } => 1.10,
            ScirOp::HdcBind
            | ScirOp::HdcBundle
            | ScirOp::HdcPermute { .. }
            | ScirOp::HdcThreshold { .. } => 1.05,
            _ => 1.0,
        };
        let topology = (node.inputs.len() as f64 + 1.0).ln_1p();
        let dim = (node.out_dim.max(1) as f64).ln_1p();
        let phase = ((idx as f64 + 1.0) * 0.137).sin().abs() * 0.12 + 0.94;
        out.push((dim * op_weight + topology) * phase);
    }
    if out.is_empty() {
        out.push(1.0);
    }
    out
}

fn demon_ground_state_and_gap(signature: &[f64], scenario: DemonScenario) -> (f64, f64) {
    let n = signature.len().max(1);
    let mut psi = vec![0.0f64; n];
    for i in 0..n {
        let idx_phase = i as f64 / n as f64;
        let onsite = signature[i] * scenario.thermal_scale + idx_phase * scenario.gravity_scale
            - scenario.cryo_scale;
        psi[i] = onsite.tanh();
    }
    let coupling = (0.08 + scenario.gravity_scale.log10().max(0.0) * 0.04).clamp(0.05, 0.35);
    let iters =
        (24.0 + scenario.thermal_scale * 3.0 + scenario.gravity_scale + scenario.cryo_scale * 4.0)
            .round()
            .clamp(16.0, 96.0) as usize;
    for _ in 0..iters {
        let mut next = vec![0.0f64; n];
        for i in 0..n {
            let left = psi[(i + n - 1) % n];
            let center = psi[i];
            let right = psi[(i + 1) % n];
            let onsite = signature[i] * scenario.thermal_scale - scenario.cryo_scale;
            next[i] = ((1.0 - coupling) * (onsite * center.tanh())
                + coupling * 0.5 * (left + right))
                .tanh();
        }
        let norm = next.iter().map(|v| v * v).sum::<f64>().sqrt().max(1.0e-9);
        for v in &mut next {
            *v /= norm;
        }
        psi = next;
    }

    let mut energies = psi
        .iter()
        .enumerate()
        .map(|(i, amp)| amp * amp * (1.0 + signature[i].abs() * 0.15))
        .collect::<Vec<_>>();
    energies.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
    let ground = *energies.first().unwrap_or(&1.0);
    let gap = if energies.len() > 1 {
        (energies[1] - energies[0]).max(0.0)
    } else {
        0.0
    };
    (ground, gap)
}
