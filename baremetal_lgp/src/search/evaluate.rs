use crate::library::bank::LibraryBank;
use crate::search::archive::{Archive, ArchiveInsert, Elite};
use crate::search::descriptors::{
    bin_id, build_descriptor, output_entropy_sketch, Descriptor, DescriptorInputs,
};
use crate::search::ir::{CandidateCfg, Opcode};
use crate::search::mutate::{mutate_candidate, DEFAULT_MUTATION_WEIGHTS, MUTATION_OPERATOR_COUNT};
use crate::search::rng::Rng;
use crate::vm::{VmProgram, VmWorker};

#[derive(Clone, Debug)]
pub struct ExecConfig {
    pub fuel_max: u32,
    pub stability_runs: u32,
    pub stability_threshold: f32,
}

impl Default for ExecConfig {
    fn default() -> Self {
        Self {
            fuel_max: 200_000,
            stability_runs: 3,
            stability_threshold: 0.0,
        }
    }
}

#[derive(Clone, Debug)]
pub struct EvalReport {
    pub proxy_mean: f32,
    pub proxy_fuel_used: u32,
    pub full_mean: Option<f32>,
    pub full_var: Option<f32>,
    pub full_fuel_used: Option<u32>,
    pub regime_profile_bits: u8,
    pub output_snapshot: Vec<f32>,
}

impl Default for EvalReport {
    fn default() -> Self {
        Self {
            proxy_mean: 0.0,
            proxy_fuel_used: 0,
            full_mean: None,
            full_var: None,
            full_fuel_used: None,
            regime_profile_bits: 0,
            output_snapshot: Vec::new(),
        }
    }
}

pub trait Linker {
    fn link(&mut self, candidate: &CandidateCfg) -> VmProgram;
}

pub trait Oracle {
    fn eval_candidate(
        &mut self,
        worker: &mut VmWorker,
        program: &VmProgram,
        library: &LibraryBank,
        cfg: &ExecConfig,
    ) -> EvalReport;
}

pub struct EvaluationHarness<'a, L, O> {
    pub linker: &'a mut L,
    pub oracle: &'a mut O,
    pub worker: &'a mut VmWorker,
    pub library: &'a LibraryBank,
    pub exec_cfg: &'a ExecConfig,
}

#[derive(Clone, Copy, Debug, Default)]
pub struct InstructionProfile {
    pub branch_count: u32,
    pub store_count: u32,
    pub total_insns: u32,
}

#[derive(Clone, Debug)]
pub struct EvaluatedCandidate {
    pub child_cfg: CandidateCfg,
    pub program: VmProgram,
    pub report: EvalReport,
    pub profile: InstructionProfile,
    pub desc: Descriptor,
    pub bin: u16,
    pub score: f32,
    pub fuel_used: u32,
    pub code_size_words: u32,
}

impl EvaluatedCandidate {
    pub fn to_elite(&self) -> Elite {
        Elite {
            score: self.score,
            candidate: self.child_cfg.clone(),
            code_size_words: self.code_size_words,
            fuel_used: self.fuel_used,
            desc: self.desc,
        }
    }
}

pub fn evaluate_child<L, O>(
    parent_cfg: &CandidateCfg,
    archive: &Archive,
    rng: &mut Rng,
    harness: &mut EvaluationHarness<'_, L, O>,
    mutation_weights: Option<&[f32; MUTATION_OPERATOR_COUNT]>,
) -> EvaluatedCandidate
where
    L: Linker,
    O: Oracle,
{
    let weights = mutation_weights.unwrap_or(&DEFAULT_MUTATION_WEIGHTS);
    let mut child_cfg = CandidateCfg::default();
    mutate_candidate(parent_cfg, archive, rng, weights, &mut child_cfg);
    let program = harness.linker.link(&child_cfg);
    let report =
        harness
            .oracle
            .eval_candidate(harness.worker, &program, harness.library, harness.exec_cfg);
    let profile = scan_instruction_profile(&program.words);

    let code_size_words = program.words.len() as u32;
    let fuel_used = report.full_fuel_used.unwrap_or(report.proxy_fuel_used);
    let entropy = output_entropy_sketch(&report.output_snapshot);
    let descriptor = build_descriptor(DescriptorInputs {
        fuel_used,
        fuel_max: harness.exec_cfg.fuel_max,
        code_size_words,
        branch_count: profile.branch_count,
        store_count: profile.store_count,
        total_insns: profile.total_insns,
        output_entropy: entropy,
        regime_profile_bits: report.regime_profile_bits,
    });

    EvaluatedCandidate {
        child_cfg,
        program,
        score: report.full_mean.unwrap_or(report.proxy_mean),
        fuel_used,
        code_size_words,
        profile,
        bin: bin_id(&descriptor),
        desc: descriptor,
        report,
    }
}

pub fn update_archive(archive: &mut Archive, evaluated: &EvaluatedCandidate) -> ArchiveInsert {
    archive.insert(evaluated.bin, evaluated.to_elite())
}

pub fn scan_instruction_profile(words: &[u32]) -> InstructionProfile {
    let mut profile = InstructionProfile::default();
    for &word in words {
        let opcode = (word & 0x3F) as u8;
        profile.total_insns = profile.total_insns.saturating_add(1);
        let Some(op) = Opcode::from_u8(opcode) else {
            continue;
        };
        if matches!(
            op,
            Opcode::Jmp | Opcode::Jz | Opcode::Jnz | Opcode::Loop | Opcode::Call | Opcode::Ret
        ) {
            profile.branch_count = profile.branch_count.saturating_add(1);
        }
        if matches!(op, Opcode::StF) {
            profile.store_count = profile.store_count.saturating_add(1);
        }
    }
    profile
}
