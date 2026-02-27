use std::io;
use std::path::{Path, PathBuf};

use crate::library::bank::{LibraryBank, LibraryProgram};
use crate::library::promote::promote_slot;
use crate::outer_loop::bandit::Exp3Bandit;
use crate::outer_loop::stage_a::{StageAModule, StageARegistry};
use crate::outer_loop::stage_c::{KernelRequest, StageCManager};
use crate::search::mutate::{DEFAULT_MUTATION_WEIGHTS, MUTATION_OPERATOR_COUNT};
use crate::types::CandidateId;

#[derive(Clone, Copy, Debug, Default)]
pub struct ArchiveSnapshotSummary {
    pub filled_bins: u32,
    pub wins_per_hour: f32,
    pub eval_throughput: f32,
}

#[derive(Clone, Copy, Debug)]
pub struct ChampionHistoryPoint {
    pub candidate_id: CandidateId,
    pub full_mean: f32,
    pub full_var: f32,
}

#[derive(Clone, Copy, Debug)]
pub struct TraceDiffSummary {
    pub candidate_id: CandidateId,
    pub divergence_score: f32,
}

#[derive(Clone, Debug)]
pub struct LibraryPromotion {
    pub slot: usize,
    pub program: LibraryProgram,
}

#[derive(Clone, Debug, Default)]
pub struct ArchitectDecision {
    pub mutation_weights: [f32; MUTATION_OPERATOR_COUNT],
    pub promotions: Vec<LibraryPromotion>,
    pub stage_a_module: Option<PathBuf>,
    pub stage_c_requests: Vec<KernelRequest>,
}

#[derive(Debug)]
pub struct Architect {
    pub bandit: Exp3Bandit,
    pub stage_a: StageARegistry,
    pub stage_c: StageCManager,
}

impl Architect {
    pub fn new() -> Self {
        Self {
            bandit: Exp3Bandit::new(DEFAULT_MUTATION_WEIGHTS, 0.12),
            stage_a: StageARegistry::new(),
            stage_c: StageCManager::new(),
        }
    }

    pub fn decide(
        &mut self,
        archive: ArchiveSnapshotSummary,
        champion_history: &[ChampionHistoryPoint],
        trace_diffs: &[TraceDiffSummary],
    ) -> ArchitectDecision {
        let rewards = derive_bandit_rewards(archive, champion_history, trace_diffs);
        self.bandit.apply_batch_updates(&rewards);

        ArchitectDecision {
            mutation_weights: self.bandit.weights,
            promotions: Vec::new(),
            stage_a_module: None,
            stage_c_requests: suggest_stage_c_requests(trace_diffs),
        }
    }

    pub fn write_mutation_weights(&self, run_dir: impl AsRef<Path>) -> io::Result<()> {
        self.bandit.write_weights_file(run_dir)
    }

    pub fn apply_promotions(
        &self,
        library: &mut LibraryBank,
        promotions: &[LibraryPromotion],
    ) -> usize {
        let mut applied = 0usize;
        for promotion in promotions {
            if promote_slot(library, promotion.slot, promotion.program.clone(), true).is_ok() {
                applied = applied.saturating_add(1);
            }
        }
        applied
    }

    pub fn try_stage_a_swap<F>(&mut self, module_path: impl AsRef<Path>, wins_per_hour: F) -> bool
    where
        F: FnMut(crate::outer_loop::stage_a::NonLinearDispatch, u32) -> f32,
    {
        let Ok(module) = StageARegistry::load_module(module_path) else {
            return false;
        };
        self.stage_a.promote_if_shadow_passes(module, wins_per_hour)
    }

    pub fn inject_stage_a_module<F>(&mut self, module: StageAModule, wins_per_hour: F) -> bool
    where
        F: FnMut(crate::outer_loop::stage_a::NonLinearDispatch, u32) -> f32,
    {
        self.stage_a.promote_if_shadow_passes(module, wins_per_hour)
    }
}

impl Default for Architect {
    fn default() -> Self {
        Self::new()
    }
}

fn derive_bandit_rewards(
    archive: ArchiveSnapshotSummary,
    champion_history: &[ChampionHistoryPoint],
    trace_diffs: &[TraceDiffSummary],
) -> Vec<(usize, f32)> {
    let mut rewards = Vec::new();
    let base_reward = (archive.wins_per_hour / 10_000.0).clamp(-1.0, 1.0);
    rewards.push((0, base_reward));

    if champion_history.len() >= 2 {
        let newest = champion_history[champion_history.len() - 1];
        let prev = champion_history[champion_history.len() - 2];
        let delta = (newest.full_mean - prev.full_mean).clamp(-1.0, 1.0);
        rewards.push((7, delta));
        rewards.push((8, -newest.full_var.clamp(0.0, 1.0)));
    }

    if !trace_diffs.is_empty() {
        let avg_div =
            trace_diffs.iter().map(|d| d.divergence_score).sum::<f32>() / trace_diffs.len() as f32;
        rewards.push((4, avg_div.clamp(-1.0, 1.0)));
        rewards.push((6, avg_div.clamp(-1.0, 1.0)));
    }
    rewards
}

fn suggest_stage_c_requests(trace_diffs: &[TraceDiffSummary]) -> Vec<KernelRequest> {
    if trace_diffs.is_empty() {
        return Vec::new();
    }
    vec![
        KernelRequest {
            kind: crate::outer_loop::stage_c::KernelKind::VAdd,
            len: 64,
        },
        KernelRequest {
            kind: crate::outer_loop::stage_c::KernelKind::VMul,
            len: 64,
        },
    ]
}
