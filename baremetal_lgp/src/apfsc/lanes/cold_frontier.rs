use std::collections::BTreeMap;

use crate::apfsc::candidate::{clone_with_mutation, set_phase2_build_meta, CandidateBundle};
use crate::apfsc::config::Phase1Config;
use crate::apfsc::errors::Result;
use crate::apfsc::scir::ast::{ScirNode, ScirOp};
use crate::apfsc::types::{
    LearningLawKind, MemoryLawKind, PromotionClass, SchedulerClass, WarmRefinementPack,
};

pub fn generate(active: &CandidateBundle, cfg: &Phase1Config) -> Result<Vec<CandidateBundle>> {
    let mut out = Vec::new();

    let mut schedule_warm = active.schedule_pack.clone();
    schedule_warm.scheduler_class = Some(SchedulerClass::EventSparse);
    schedule_warm.memory_law = Some(MemoryLawKind::RingSlots);
    schedule_warm.learning_law = Some(LearningLawKind::ResidualAdaGrad);
    let warm_bridge = WarmRefinementPack {
        observable_map_hash: Some("warm_observable_v1".to_string()),
        state_map_hash: Some("warm_state_v1".to_string()),
        tolerance_spec_hash: Some("warm_tol_v1".to_string()),
        protected_head_ids: vec!["native_head".to_string()],
        protected_families: vec!["det_micro".to_string(), "text_code".to_string()],
        max_anchor_regress_bits: 0.0,
        max_public_regress_bits: 0.0,
        migration_policy: "warm_transition_v1".to_string(),
    };
    // Standard warm scheduler shift.
    let mut warm_standard = clone_with_mutation(
        active,
        "cold_frontier",
        "pwarm_event_sparse",
        PromotionClass::PWarm,
        active.arch_program.clone(),
        active.head_pack.clone(),
        active.state_pack.clone(),
        schedule_warm.clone(),
        Some(warm_bridge.clone()),
        BTreeMap::new(),
    )?;
    set_phase2_build_meta(
        &mut warm_standard,
        vec!["event_sparse".to_string()],
        "cold_frontier",
        "phase4_cold_frontier",
    )?;
    out.push(warm_standard);

    // Alien warm candidate.
    let mut warm = alien_structural_candidate(
        active,
        "pwarm_splice_SparseEventRouter",
        PromotionClass::PWarm,
        schedule_warm,
        Some(warm_bridge),
        ScirOp::SparseEventQueue { slots: 16 },
        16,
        false,
    )?;
    set_phase2_build_meta(
        &mut warm,
        vec!["event_sparse".to_string()],
        "cold_frontier",
        "phase4_cold_frontier",
    )?;
    out.push(warm);

    let mut schedule_cold = active.schedule_pack.clone();
    schedule_cold.scheduler_class = Some(SchedulerClass::TwoPassMemory);
    schedule_cold.memory_law = Some(MemoryLawKind::SelectiveState);
    schedule_cold.learning_law = Some(LearningLawKind::FastWeightDelta);
    // Standard cold scheduler shift.
    let mut cold_standard = clone_with_mutation(
        active,
        "cold_frontier",
        "pcold_formal_alg",
        PromotionClass::PCold,
        active.arch_program.clone(),
        active.head_pack.clone(),
        active.state_pack.clone(),
        schedule_cold.clone(),
        None,
        BTreeMap::new(),
    )?;
    set_phase2_build_meta(
        &mut cold_standard,
        vec!["formal_alg".to_string()],
        "cold_frontier",
        "phase4_cold_frontier",
    )?;
    out.push(cold_standard);

    // Alien cold candidates.
    let mut cold = alien_structural_candidate(
        active,
        "pcold_splice_SymbolicTapeExecutor",
        PromotionClass::PCold,
        schedule_cold.clone(),
        None,
        ScirOp::SymbolicTape { cells: 16 },
        16,
        false,
    )?;
    set_phase2_build_meta(
        &mut cold,
        vec!["formal_alg".to_string()],
        "cold_frontier",
        "phase4_cold_frontier",
    )?;
    out.push(cold);

    let hdc_dim = active
        .arch_program
        .nodes
        .iter()
        .find(|n| n.id == active.arch_program.outputs.feature_node)
        .map(|n| n.out_dim)
        .unwrap_or(16);
    let mut hdc = alien_structural_candidate(
        active,
        "pcold_splice_HdcAssociativeMemory",
        PromotionClass::PCold,
        schedule_cold,
        None,
        ScirOp::HdcPermute { shift: 3 },
        hdc_dim,
        true,
    )?;
    set_phase2_build_meta(
        &mut hdc,
        vec!["formal_alg".to_string(), "event_sparse".to_string()],
        "cold_frontier",
        "phase4_cold_frontier",
    )?;
    out.push(hdc);

    let max_frontier = ((cfg.phase3.budgets.cold_frontier * cfg.lanes.max_public_candidates as f64)
        .round() as usize)
        .max(1);
    out.truncate(max_frontier);
    Ok(out)
}

#[allow(clippy::too_many_arguments)]
fn alien_structural_candidate(
    active: &CandidateBundle,
    mutation: &str,
    class: PromotionClass,
    schedule: crate::apfsc::types::SchedulePack,
    bridge: Option<WarmRefinementPack>,
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
        "cold_frontier",
        mutation,
        class,
        program,
        head_pack,
        state,
        schedule,
        bridge,
        BTreeMap::new(),
    )
}
