pub mod archive;
pub mod champion;
pub mod descriptors;
pub mod digest;
pub mod evaluate;
pub mod ir;
pub mod mutate;
pub mod rng;
pub mod select;
pub mod topk_trace;

use crate::search::archive::{Archive, Elite};
use crate::search::champion::{maybe_update_champion, Champion, StabilityOracle};
use crate::search::evaluate::{
    evaluate_child, update_archive, EvalReport, EvaluatedCandidate, EvaluationHarness, ExecConfig,
    Linker, Oracle,
};
use crate::search::ir::CandidateCfg;
use crate::search::mutate::{DEFAULT_MUTATION_WEIGHTS, MUTATION_OPERATOR_COUNT};
use crate::search::rng::Rng;
use crate::search::select::select_parent;
use crate::types::CandidateId;

#[derive(Debug)]
pub struct SearchState {
    pub archive: Archive,
    pub champion: Option<Champion>,
    pub mutation_weights: [f32; MUTATION_OPERATOR_COUNT],
    rng: Rng,
    next_candidate_id: u64,
}

pub struct StepContext<'a, L, O, S> {
    pub harness: EvaluationHarness<'a, L, O>,
    pub stability: &'a mut S,
    pub exec_cfg: &'a ExecConfig,
}

impl SearchState {
    pub fn new(seed: u64) -> Self {
        Self {
            archive: Archive::new(),
            champion: None,
            mutation_weights: DEFAULT_MUTATION_WEIGHTS,
            rng: Rng::new(seed),
            next_candidate_id: 1,
        }
    }

    pub fn with_entropy_seed() -> Self {
        let mut entropy = [0_u8; 8];
        let seed = if getrandom::getrandom(&mut entropy).is_ok() {
            u64::from_le_bytes(entropy)
        } else {
            0xA076_1D64_78BD_642F
        };
        Self::new(seed)
    }

    pub fn next_candidate_id(&mut self) -> CandidateId {
        let id = CandidateId(self.next_candidate_id);
        self.next_candidate_id = self.next_candidate_id.saturating_add(1);
        id
    }

    pub fn upsert_seed(&mut self, elite: Elite, full_mean: Option<f32>, full_var: Option<f32>) {
        let bin = descriptors::bin_id(&elite.desc);
        self.archive.insert(bin, elite.clone());
        if let (Some(mean), Some(var)) = (full_mean, full_var) {
            self.champion = Some(Champion {
                elite,
                full_mean: mean,
                full_var: var,
            });
        }
    }

    pub fn evaluate_step<L, O, S>(
        &mut self,
        parent_fallback: &CandidateCfg,
        step: &mut StepContext<'_, L, O, S>,
    ) -> EvaluatedCandidate
    where
        L: Linker,
        O: Oracle,
        S: StabilityOracle,
    {
        let parent = select_parent(
            &self.archive,
            self.champion.as_ref().map(|c| &c.elite),
            &mut self.rng,
        )
        .map_or(parent_fallback, |elite| &elite.candidate);

        let evaluated = evaluate_child(
            parent,
            &self.archive,
            &mut self.rng,
            &mut step.harness,
            Some(&self.mutation_weights),
        );
        update_archive(&mut self.archive, &evaluated);
        let _ = maybe_update_champion(
            &mut self.champion,
            &evaluated,
            step.exec_cfg,
            step.stability,
        );
        evaluated
    }
}

pub fn report_score(report: &EvalReport) -> f32 {
    report.full_mean.unwrap_or(report.proxy_mean)
}
