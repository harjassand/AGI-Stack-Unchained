use crate::search::archive::Elite;
use crate::search::evaluate::{EvaluatedCandidate, ExecConfig};
use crate::search::ir::CandidateCfg;
use crate::vm::VmProgram;

#[derive(Clone, Debug)]
pub struct Champion {
    pub elite: Elite,
    pub full_mean: f32,
    pub full_var: f32,
}

pub trait StabilityOracle {
    fn run_stability(
        &mut self,
        candidate: &CandidateCfg,
        program: &VmProgram,
        stability_runs: u32,
    ) -> Option<(f32, f32)>;
}

pub fn maybe_update_champion<S>(
    champion: &mut Option<Champion>,
    evaluated: &EvaluatedCandidate,
    exec_cfg: &ExecConfig,
    stability: &mut S,
) -> bool
where
    S: StabilityOracle,
{
    let Some(mut mean_new) = evaluated.report.full_mean else {
        return false;
    };

    let mut var_new = evaluated.report.full_var;
    if var_new.is_none() && mean_new >= exec_cfg.stability_threshold {
        if let Some((stability_mean, stability_var)) = stability.run_stability(
            &evaluated.child_cfg,
            &evaluated.program,
            exec_cfg.stability_runs,
        ) {
            mean_new = stability_mean;
            var_new = Some(stability_var);
        }
    }
    let Some(var_new) = var_new else {
        return false;
    };

    match champion {
        None => {
            *champion = Some(Champion {
                elite: evaluated.to_elite(),
                full_mean: mean_new,
                full_var: var_new,
            });
            true
        }
        Some(current)
            if mean_new >= current.full_mean + 0.01
                && var_new <= current.full_var * 1.10 + 1e-6 =>
        {
            *current = Champion {
                elite: evaluated.to_elite(),
                full_mean: mean_new,
                full_var: var_new,
            };
            true
        }
        Some(_) => false,
    }
}
