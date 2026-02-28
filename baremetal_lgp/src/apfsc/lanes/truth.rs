use std::collections::BTreeMap;

use crate::apfsc::candidate::{clone_with_mutation, CandidateBundle};
use crate::apfsc::config::Phase1Config;
use crate::apfsc::errors::Result;
use crate::apfsc::schedule_pack::with_predicted_cost;
use crate::apfsc::scir::ast::{ScirNode, ScirOp};
use crate::apfsc::types::{PredictedCost, PromotionClass};

pub fn generate(active: &CandidateBundle, cfg: &Phase1Config) -> Result<Vec<CandidateBundle>> {
    let mut out = Vec::new();

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

    out.truncate(
        cfg.lanes
            .max_truth_candidates
            .min(cfg.lanes.max_public_candidates / 2),
    );
    Ok(out)
}

pub fn generate_phase3(active: &CandidateBundle, cfg: &Phase1Config) -> Result<Vec<CandidateBundle>> {
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
