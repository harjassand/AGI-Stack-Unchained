use std::collections::BTreeMap;
use std::path::Path;

use serde::{Deserialize, Serialize};

use crate::apfsc::constants;
use crate::apfsc::errors::{io_err, Result};
use crate::apfsc::types::{FamilyWeights, NormalizationPolicy, ProtectionFloor, TransferAdaptSpec};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Phase1Config {
    #[serde(default)]
    pub root: RootConfig,
    #[serde(default)]
    pub protocol: ProtocolConfig,
    #[serde(default)]
    pub bank: BankConfig,
    #[serde(default)]
    pub limits: LimitsConfig,
    #[serde(default)]
    pub train: TrainConfig,
    #[serde(default)]
    pub judge: JudgeConfig,
    #[serde(default)]
    pub lanes: LanesConfig,
    #[serde(default)]
    pub incubator: IncubatorConfig,
    #[serde(default)]
    pub witness: WitnessConfig,
    #[serde(default)]
    pub phase2: Phase2Config,
    #[serde(default)]
    pub phase3: Phase3Config,
    #[serde(default)]
    pub phase4: Phase4Config,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct RootConfig {
    #[serde(default = "default_artifact_root")]
    pub artifact_root: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ProtocolConfig {
    #[serde(default = "default_protocol_version")]
    pub version: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct BankConfig {
    #[serde(default = "default_window_len")]
    pub window_len: u32,
    #[serde(default = "default_stride")]
    pub stride: u32,
    #[serde(default = "constants::default_split_ratios")]
    pub split_ratios: BTreeMap<String, f64>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct LimitsConfig {
    #[serde(default = "default_rss_hard_limit_bytes")]
    pub rss_hard_limit_bytes: u64,
    #[serde(default = "default_rss_abort_limit_bytes")]
    pub rss_abort_limit_bytes: u64,
    #[serde(default = "default_max_concurrent_mapped_bytes")]
    pub max_concurrent_mapped_bytes: u64,
    #[serde(default = "default_segment_bytes")]
    pub segment_bytes: u64,
    #[serde(default = "default_state_tile_bytes_max")]
    pub state_tile_bytes_max: u64,
    #[serde(default = "default_param_bits_max")]
    pub max_param_bits: u64,
    #[serde(default = "default_max_public_workers")]
    pub max_public_workers: u32,
    #[serde(default = "default_max_incubator_workers")]
    pub max_incubator_workers: u32,
    #[serde(default = "default_max_canary_workers")]
    pub max_canary_workers: u32,
    #[serde(default = "default_max_transfer_workers")]
    pub max_transfer_workers: u32,
    #[serde(default = "default_max_robust_workers")]
    pub max_robust_workers: u32,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct TrainConfig {
    #[serde(default = "default_train_steps")]
    pub steps: u32,
    #[serde(default = "default_train_lr")]
    pub lr: f32,
    #[serde(default = "default_train_eps")]
    pub eps: f32,
    #[serde(default = "default_train_l2")]
    pub l2: f32,
    #[serde(default = "default_train_clip_grad")]
    pub clip_grad: f32,
    #[serde(default = "default_train_batch_windows")]
    pub batch_windows: usize,
    #[serde(default)]
    pub shuffle: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct JudgeConfig {
    #[serde(default = "default_public_min_delta_bits")]
    pub public_min_delta_bits: f64,
    #[serde(default = "default_holdout_min_delta_bits")]
    pub holdout_min_delta_bits: f64,
    #[serde(default)]
    pub anchor_max_regress_bits: f64,
    #[serde(default)]
    pub mini_transfer_min_delta_bits: f64,
    #[serde(default = "default_require_canary_for_a")]
    pub require_canary_for_a: bool,
    #[serde(default = "default_max_holdout_admissions")]
    pub max_holdout_admissions: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct LanesConfig {
    #[serde(default = "default_max_truth_candidates")]
    pub max_truth_candidates: usize,
    #[serde(default = "default_max_equivalence_candidates")]
    pub max_equivalence_candidates: usize,
    #[serde(default = "default_max_incubator_candidates")]
    pub max_incubator_candidates: usize,
    #[serde(default = "default_max_public_candidates")]
    pub max_public_candidates: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct IncubatorConfig {
    #[serde(default = "default_incubator_min_utility_bits")]
    pub incubator_min_utility_bits: f64,
    #[serde(default = "default_incubator_lambda_code")]
    pub lambda_code: f64,
    #[serde(default = "default_incubator_lambda_risk")]
    pub lambda_risk: f64,
    #[serde(default = "default_incubator_shadow_steps")]
    pub shadow_steps: u32,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct WitnessConfig {
    #[serde(default = "default_witness_count")]
    pub count: usize,
    #[serde(default = "default_witness_rotation")]
    pub rotation: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Phase2NormalizationConfig {
    #[serde(default = "default_codelen_ref_bytes")]
    pub codelen_ref_bytes: u64,
    #[serde(default = "default_transfer_ref_bytes")]
    pub transfer_ref_bytes: u64,
    #[serde(default)]
    pub public_eval_max_bytes: Option<u64>,
    #[serde(default)]
    pub public_eval_seed: u64,
    #[serde(default)]
    pub holdout_eval_max_bytes: Option<u64>,
    #[serde(default)]
    pub canary_eval_max_bytes: Option<u64>,
    #[serde(default = "default_public_static_margin_bpb")]
    pub public_static_margin_bpb: f64,
    #[serde(default = "default_holdout_static_margin_bpb")]
    pub holdout_static_margin_bpb: f64,
    #[serde(default = "default_holdout_transfer_margin_bpb")]
    pub holdout_transfer_margin_bpb: f64,
    #[serde(default = "default_holdout_robust_margin_bpb")]
    pub holdout_robust_margin_bpb: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Phase2Config {
    #[serde(default)]
    pub enabled: bool,
    #[serde(default = "default_phase2_profile_name")]
    pub profile_name: String,
    #[serde(default = "default_true")]
    pub constellation_required: bool,
    #[serde(default = "default_min_improved_families")]
    pub min_improved_families: u32,
    #[serde(default = "default_min_nonprotected_improved_families")]
    pub min_nonprotected_improved_families: u32,
    #[serde(default = "default_true")]
    pub require_target_subset_hit: bool,
    #[serde(default = "default_target_subset")]
    pub target_subset: Vec<String>,
    #[serde(default)]
    pub normalization: Phase2NormalizationConfig,
    #[serde(default = "default_phase2_weights")]
    pub weights: BTreeMap<String, FamilyWeights>,
    #[serde(default = "default_phase2_floors")]
    pub floors: BTreeMap<String, ProtectionFloor>,
    #[serde(default = "default_phase2_transfer")]
    pub transfer: TransferAdaptSpec,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Phase3BudgetConfig {
    #[serde(default = "default_phase3_budget_truth")]
    pub truth: f64,
    #[serde(default = "default_phase3_budget_equivalence")]
    pub equivalence: f64,
    #[serde(default = "default_phase3_budget_incubator")]
    pub incubator: f64,
    #[serde(default = "default_phase3_budget_cold_frontier")]
    pub cold_frontier: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Phase3LimitsConfig {
    #[serde(default = "default_phase3_max_scir_core_ops")]
    pub max_scir_core_ops: u32,
    #[serde(default = "default_phase3_max_macro_calls_per_program")]
    pub max_macro_calls_per_program: u32,
    #[serde(default = "default_phase3_max_macro_expansion_ops")]
    pub max_macro_expansion_ops: u32,
    #[serde(default = "default_phase3_max_macro_depth")]
    pub max_macro_depth: u32,
    #[serde(default = "default_phase3_max_egraph_nodes")]
    pub max_egraph_nodes: u32,
    #[serde(default = "default_phase3_max_egraph_extractions")]
    pub max_egraph_extractions: u32,
    #[serde(default = "default_phase3_max_paradigm_public_candidates")]
    pub max_paradigm_public_candidates: usize,
    #[serde(default = "default_phase3_max_pwarm_holdout_admissions")]
    pub max_pwarm_holdout_admissions: usize,
    #[serde(default = "default_phase3_max_pcold_holdout_admissions")]
    pub max_pcold_holdout_admissions: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Phase3PromotionConfig {
    #[serde(default = "default_s_class_min_static_delta_bpb")]
    pub s_class_min_static_delta_bpb: f64,
    #[serde(default = "default_p_warm_min_static_delta_bpb")]
    pub p_warm_min_static_delta_bpb: f64,
    #[serde(default = "default_p_warm_min_transfer_delta_bpb")]
    pub p_warm_min_transfer_delta_bpb: f64,
    #[serde(default = "default_p_warm_max_robust_regress_bpb")]
    pub p_warm_max_robust_regress_bpb: f64,
    #[serde(default = "default_p_warm_min_recent_family_gain_bpb")]
    pub p_warm_min_recent_family_gain_bpb: f64,
    #[serde(default = "default_p_cold_min_static_delta_bpb")]
    pub p_cold_min_static_delta_bpb: f64,
    #[serde(default = "default_p_cold_min_transfer_delta_bpb")]
    pub p_cold_min_transfer_delta_bpb: f64,
    #[serde(default = "default_p_cold_min_recent_family_gain_bpb")]
    pub p_cold_min_recent_family_gain_bpb: f64,
    #[serde(default = "default_p_cold_max_anchor_regret_bpb")]
    pub p_cold_max_anchor_regret_bpb: f64,
    #[serde(default = "default_p_cold_max_error_streak")]
    pub p_cold_max_error_streak: u32,
    #[serde(default = "default_p_cold_min_improved_families")]
    pub p_cold_min_improved_families: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Phase3MacroConfig {
    #[serde(default = "default_phase3_min_macro_support")]
    pub min_macro_support: u32,
    #[serde(default = "default_phase3_min_macro_public_gain_bpb")]
    pub min_macro_public_gain_bpb: f64,
    #[serde(default = "default_phase3_min_macro_reduction_ratio")]
    pub min_macro_reduction_ratio: f64,
    #[serde(default = "default_phase3_max_induced_macros_per_epoch")]
    pub max_induced_macros_per_epoch: u32,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Phase3BackendConfig {
    #[serde(default = "default_true")]
    pub allow_graph_backend_public: bool,
    #[serde(default = "default_true")]
    pub allow_graph_backend_canary: bool,
    #[serde(default)]
    pub allow_graph_backend_holdout: bool,
    #[serde(default = "default_true")]
    pub require_exact_backend_equiv: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Phase3CanaryConfig {
    #[serde(default = "default_phase3_canary_warm_windows")]
    pub warm_windows: u32,
    #[serde(default = "default_phase3_canary_cold_windows")]
    pub cold_windows: u32,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Phase3Config {
    #[serde(default = "default_phase3_profile_name")]
    pub profile: String,
    #[serde(default = "default_true")]
    pub allow_p_warm: bool,
    #[serde(default = "default_true")]
    pub allow_p_cold: bool,
    #[serde(default = "default_phase3_fresh_horizon_epochs")]
    pub fresh_horizon_epochs: u64,
    #[serde(default)]
    pub budgets: Phase3BudgetConfig,
    #[serde(default)]
    pub limits: Phase3LimitsConfig,
    #[serde(default)]
    pub promotion: Phase3PromotionConfig,
    #[serde(default, rename = "macro")]
    pub macro_cfg: Phase3MacroConfig,
    #[serde(default)]
    pub backend: Phase3BackendConfig,
    #[serde(default)]
    pub canary: Phase3CanaryConfig,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Phase4Config {
    #[serde(default = "default_true")]
    pub enable_hidden_challenge_gate: bool,
    #[serde(default = "default_phase4_challenge_min_bucket_score")]
    pub challenge_min_bucket_score: i32,
    #[serde(default = "default_phase4_challenge_retire_after_epochs")]
    pub challenge_retire_after_epochs: u64,
    #[serde(default = "default_phase4_holdout_retire_after_epochs")]
    pub holdout_retire_after_epochs: u64,

    #[serde(default = "default_true")]
    pub enable_formal_pack: bool,
    #[serde(default = "default_true")]
    pub enable_tool_pack: bool,
    #[serde(default = "default_true")]
    pub enable_recombination: bool,
    #[serde(default = "default_true")]
    pub enable_qd_archive: bool,
    #[serde(default = "default_true")]
    pub enable_searchlaw: bool,
    #[serde(default = "default_true")]
    pub enable_need_tokens: bool,
    #[serde(default = "default_true")]
    pub enable_credit_debt: bool,

    #[serde(default = "default_phase4_max_hidden_challenge_families")]
    pub max_hidden_challenge_families: usize,
    #[serde(default = "default_phase4_max_searchlaw_public_candidates")]
    pub max_searchlaw_public_candidates: usize,
    #[serde(default = "default_phase4_max_searchlaw_ab_candidates")]
    pub max_searchlaw_ab_candidates: usize,
    #[serde(default = "default_phase4_searchlaw_min_ab_epochs")]
    pub searchlaw_min_ab_epochs: u32,
    #[serde(default = "default_phase4_searchlaw_max_ab_epochs")]
    pub searchlaw_max_ab_epochs: u32,
    #[serde(default = "default_phase4_searchlaw_required_yield_improvement")]
    pub searchlaw_required_yield_improvement: f64,
    #[serde(default = "default_phase4_searchlaw_max_safety_regression")]
    pub searchlaw_max_safety_regression: f64,

    #[serde(default = "default_phase4_max_portfolio_branches")]
    pub max_portfolio_branches: usize,
    #[serde(default = "default_phase4_max_branch_local_debt_credits")]
    pub max_branch_local_debt_credits: i32,
    #[serde(default = "default_phase4_max_global_debt_credits")]
    pub max_global_debt_credits: i32,
    #[serde(default = "default_phase4_max_idle_epochs_before_cull")]
    pub max_idle_epochs_before_cull: u32,

    #[serde(default = "default_phase4_max_qd_cells")]
    pub max_qd_cells: usize,
    #[serde(default = "default_phase4_max_needtokens_per_epoch")]
    pub max_needtokens_per_epoch: usize,
    #[serde(default = "default_phase4_max_recombination_parents")]
    pub max_recombination_parents: usize,

    #[serde(default = "default_phase4_yield_points_s")]
    pub yield_points_s: i32,
    #[serde(default = "default_phase4_yield_points_a")]
    pub yield_points_a: i32,
    #[serde(default = "default_phase4_yield_points_pwarm")]
    pub yield_points_pwarm: i32,
    #[serde(default = "default_phase4_yield_points_pcold")]
    pub yield_points_pcold: i32,
    #[serde(default = "default_phase4_yield_points_challenge_bonus")]
    pub yield_points_challenge_bonus: i32,
}

impl Default for Phase1Config {
    fn default() -> Self {
        Self {
            root: RootConfig::default(),
            protocol: ProtocolConfig::default(),
            bank: BankConfig::default(),
            limits: LimitsConfig::default(),
            train: TrainConfig::default(),
            judge: JudgeConfig::default(),
            lanes: LanesConfig::default(),
            incubator: IncubatorConfig::default(),
            witness: WitnessConfig::default(),
            phase2: Phase2Config::default(),
            phase3: Phase3Config::default(),
            phase4: Phase4Config::default(),
        }
    }
}

impl Default for RootConfig {
    fn default() -> Self {
        Self {
            artifact_root: default_artifact_root(),
        }
    }
}

impl Default for ProtocolConfig {
    fn default() -> Self {
        Self {
            version: default_protocol_version(),
        }
    }
}

impl Default for BankConfig {
    fn default() -> Self {
        Self {
            window_len: default_window_len(),
            stride: default_stride(),
            split_ratios: constants::default_split_ratios(),
        }
    }
}

impl Default for LimitsConfig {
    fn default() -> Self {
        Self {
            rss_hard_limit_bytes: default_rss_hard_limit_bytes(),
            rss_abort_limit_bytes: default_rss_abort_limit_bytes(),
            max_concurrent_mapped_bytes: default_max_concurrent_mapped_bytes(),
            segment_bytes: default_segment_bytes(),
            state_tile_bytes_max: default_state_tile_bytes_max(),
            max_param_bits: default_param_bits_max(),
            max_public_workers: default_max_public_workers(),
            max_incubator_workers: default_max_incubator_workers(),
            max_canary_workers: default_max_canary_workers(),
            max_transfer_workers: default_max_transfer_workers(),
            max_robust_workers: default_max_robust_workers(),
        }
    }
}

impl Default for TrainConfig {
    fn default() -> Self {
        Self {
            steps: default_train_steps(),
            lr: default_train_lr(),
            eps: default_train_eps(),
            l2: default_train_l2(),
            clip_grad: default_train_clip_grad(),
            batch_windows: default_train_batch_windows(),
            shuffle: false,
        }
    }
}

impl Default for JudgeConfig {
    fn default() -> Self {
        Self {
            public_min_delta_bits: default_public_min_delta_bits(),
            holdout_min_delta_bits: default_holdout_min_delta_bits(),
            anchor_max_regress_bits: 0.0,
            mini_transfer_min_delta_bits: 0.0,
            require_canary_for_a: default_require_canary_for_a(),
            max_holdout_admissions: default_max_holdout_admissions(),
        }
    }
}

impl Default for LanesConfig {
    fn default() -> Self {
        Self {
            max_truth_candidates: default_max_truth_candidates(),
            max_equivalence_candidates: default_max_equivalence_candidates(),
            max_incubator_candidates: default_max_incubator_candidates(),
            max_public_candidates: default_max_public_candidates(),
        }
    }
}

impl Default for IncubatorConfig {
    fn default() -> Self {
        Self {
            incubator_min_utility_bits: default_incubator_min_utility_bits(),
            lambda_code: default_incubator_lambda_code(),
            lambda_risk: default_incubator_lambda_risk(),
            shadow_steps: default_incubator_shadow_steps(),
        }
    }
}

impl Default for WitnessConfig {
    fn default() -> Self {
        Self {
            count: default_witness_count(),
            rotation: default_witness_rotation(),
        }
    }
}

impl Default for Phase2NormalizationConfig {
    fn default() -> Self {
        Self {
            codelen_ref_bytes: default_codelen_ref_bytes(),
            transfer_ref_bytes: default_transfer_ref_bytes(),
            public_eval_max_bytes: None,
            public_eval_seed: 0,
            holdout_eval_max_bytes: None,
            canary_eval_max_bytes: None,
            public_static_margin_bpb: default_public_static_margin_bpb(),
            holdout_static_margin_bpb: default_holdout_static_margin_bpb(),
            holdout_transfer_margin_bpb: default_holdout_transfer_margin_bpb(),
            holdout_robust_margin_bpb: default_holdout_robust_margin_bpb(),
        }
    }
}

impl Default for Phase2Config {
    fn default() -> Self {
        Self {
            enabled: false,
            profile_name: default_phase2_profile_name(),
            constellation_required: true,
            min_improved_families: default_min_improved_families(),
            min_nonprotected_improved_families: default_min_nonprotected_improved_families(),
            require_target_subset_hit: true,
            target_subset: default_target_subset(),
            normalization: Phase2NormalizationConfig::default(),
            weights: default_phase2_weights(),
            floors: default_phase2_floors(),
            transfer: default_phase2_transfer(),
        }
    }
}

impl Default for Phase3BudgetConfig {
    fn default() -> Self {
        Self {
            truth: default_phase3_budget_truth(),
            equivalence: default_phase3_budget_equivalence(),
            incubator: default_phase3_budget_incubator(),
            cold_frontier: default_phase3_budget_cold_frontier(),
        }
    }
}

impl Default for Phase3LimitsConfig {
    fn default() -> Self {
        Self {
            max_scir_core_ops: default_phase3_max_scir_core_ops(),
            max_macro_calls_per_program: default_phase3_max_macro_calls_per_program(),
            max_macro_expansion_ops: default_phase3_max_macro_expansion_ops(),
            max_macro_depth: default_phase3_max_macro_depth(),
            max_egraph_nodes: default_phase3_max_egraph_nodes(),
            max_egraph_extractions: default_phase3_max_egraph_extractions(),
            max_paradigm_public_candidates: default_phase3_max_paradigm_public_candidates(),
            max_pwarm_holdout_admissions: default_phase3_max_pwarm_holdout_admissions(),
            max_pcold_holdout_admissions: default_phase3_max_pcold_holdout_admissions(),
        }
    }
}

impl Default for Phase3PromotionConfig {
    fn default() -> Self {
        Self {
            s_class_min_static_delta_bpb: default_s_class_min_static_delta_bpb(),
            p_warm_min_static_delta_bpb: default_p_warm_min_static_delta_bpb(),
            p_warm_min_transfer_delta_bpb: default_p_warm_min_transfer_delta_bpb(),
            p_warm_max_robust_regress_bpb: default_p_warm_max_robust_regress_bpb(),
            p_warm_min_recent_family_gain_bpb: default_p_warm_min_recent_family_gain_bpb(),
            p_cold_min_static_delta_bpb: default_p_cold_min_static_delta_bpb(),
            p_cold_min_transfer_delta_bpb: default_p_cold_min_transfer_delta_bpb(),
            p_cold_min_recent_family_gain_bpb: default_p_cold_min_recent_family_gain_bpb(),
            p_cold_max_anchor_regret_bpb: default_p_cold_max_anchor_regret_bpb(),
            p_cold_max_error_streak: default_p_cold_max_error_streak(),
            p_cold_min_improved_families: default_p_cold_min_improved_families(),
        }
    }
}

impl Default for Phase3MacroConfig {
    fn default() -> Self {
        Self {
            min_macro_support: default_phase3_min_macro_support(),
            min_macro_public_gain_bpb: default_phase3_min_macro_public_gain_bpb(),
            min_macro_reduction_ratio: default_phase3_min_macro_reduction_ratio(),
            max_induced_macros_per_epoch: default_phase3_max_induced_macros_per_epoch(),
        }
    }
}

impl Default for Phase3BackendConfig {
    fn default() -> Self {
        Self {
            allow_graph_backend_public: true,
            allow_graph_backend_canary: true,
            allow_graph_backend_holdout: false,
            require_exact_backend_equiv: true,
        }
    }
}

impl Default for Phase3CanaryConfig {
    fn default() -> Self {
        Self {
            warm_windows: default_phase3_canary_warm_windows(),
            cold_windows: default_phase3_canary_cold_windows(),
        }
    }
}

impl Default for Phase3Config {
    fn default() -> Self {
        Self {
            profile: default_phase3_profile_name(),
            allow_p_warm: true,
            allow_p_cold: true,
            fresh_horizon_epochs: default_phase3_fresh_horizon_epochs(),
            budgets: Phase3BudgetConfig::default(),
            limits: Phase3LimitsConfig::default(),
            promotion: Phase3PromotionConfig::default(),
            macro_cfg: Phase3MacroConfig::default(),
            backend: Phase3BackendConfig::default(),
            canary: Phase3CanaryConfig::default(),
        }
    }
}

impl Default for Phase4Config {
    fn default() -> Self {
        Self {
            enable_hidden_challenge_gate: true,
            challenge_min_bucket_score: default_phase4_challenge_min_bucket_score(),
            challenge_retire_after_epochs: default_phase4_challenge_retire_after_epochs(),
            holdout_retire_after_epochs: default_phase4_holdout_retire_after_epochs(),
            enable_formal_pack: true,
            enable_tool_pack: true,
            enable_recombination: true,
            enable_qd_archive: true,
            enable_searchlaw: true,
            enable_need_tokens: true,
            enable_credit_debt: true,
            max_hidden_challenge_families: default_phase4_max_hidden_challenge_families(),
            max_searchlaw_public_candidates: default_phase4_max_searchlaw_public_candidates(),
            max_searchlaw_ab_candidates: default_phase4_max_searchlaw_ab_candidates(),
            searchlaw_min_ab_epochs: default_phase4_searchlaw_min_ab_epochs(),
            searchlaw_max_ab_epochs: default_phase4_searchlaw_max_ab_epochs(),
            searchlaw_required_yield_improvement:
                default_phase4_searchlaw_required_yield_improvement(),
            searchlaw_max_safety_regression: default_phase4_searchlaw_max_safety_regression(),
            max_portfolio_branches: default_phase4_max_portfolio_branches(),
            max_branch_local_debt_credits: default_phase4_max_branch_local_debt_credits(),
            max_global_debt_credits: default_phase4_max_global_debt_credits(),
            max_idle_epochs_before_cull: default_phase4_max_idle_epochs_before_cull(),
            max_qd_cells: default_phase4_max_qd_cells(),
            max_needtokens_per_epoch: default_phase4_max_needtokens_per_epoch(),
            max_recombination_parents: default_phase4_max_recombination_parents(),
            yield_points_s: default_phase4_yield_points_s(),
            yield_points_a: default_phase4_yield_points_a(),
            yield_points_pwarm: default_phase4_yield_points_pwarm(),
            yield_points_pcold: default_phase4_yield_points_pcold(),
            yield_points_challenge_bonus: default_phase4_yield_points_challenge_bonus(),
        }
    }
}

impl Phase1Config {
    pub fn from_path(path: &Path) -> Result<Self> {
        let body = std::fs::read_to_string(path).map_err(|e| io_err(path, e))?;
        Ok(toml::from_str(&body)?)
    }

    pub fn to_toml_string(&self) -> Result<String> {
        Ok(toml::to_string_pretty(self)?)
    }

    pub fn phase2_policy(&self) -> NormalizationPolicy {
        NormalizationPolicy {
            codelen_ref_bytes: self.phase2.normalization.codelen_ref_bytes,
            transfer_ref_bytes: self.phase2.normalization.transfer_ref_bytes,
            public_eval_max_bytes: self.phase2.normalization.public_eval_max_bytes,
            public_eval_seed: self.phase2.normalization.public_eval_seed,
            holdout_eval_max_bytes: self.phase2.normalization.holdout_eval_max_bytes,
            canary_eval_max_bytes: self.phase2.normalization.canary_eval_max_bytes,
            min_improved_families: self.phase2.min_improved_families,
            min_nonprotected_improved_families: self.phase2.min_nonprotected_improved_families,
            require_target_subset_hit: self.phase2.require_target_subset_hit,
            target_subset: self.phase2.target_subset.clone(),
            public_static_margin_bpb: self.phase2.normalization.public_static_margin_bpb,
            holdout_static_margin_bpb: self.phase2.normalization.holdout_static_margin_bpb,
            holdout_transfer_margin_bpb: self.phase2.normalization.holdout_transfer_margin_bpb,
            holdout_robust_margin_bpb: self.phase2.normalization.holdout_robust_margin_bpb,
        }
    }
}

fn default_artifact_root() -> String {
    constants::DEFAULT_ARTIFACT_ROOT.to_string()
}

fn default_protocol_version() -> String {
    constants::DEFAULT_PROTOCOL_VERSION.to_string()
}

fn default_window_len() -> u32 {
    constants::DEFAULT_WINDOW_LEN
}

fn default_stride() -> u32 {
    constants::DEFAULT_STRIDE
}

fn default_rss_hard_limit_bytes() -> u64 {
    constants::RSS_HARD_LIMIT_BYTES
}

fn default_rss_abort_limit_bytes() -> u64 {
    constants::RSS_ABORT_LIMIT_BYTES
}

fn default_max_concurrent_mapped_bytes() -> u64 {
    constants::MAX_CONCURRENT_MAPPED_BYTES
}

fn default_segment_bytes() -> u64 {
    constants::SEGMENT_BYTES
}

fn default_state_tile_bytes_max() -> u64 {
    constants::STATE_TILE_BYTES_MAX
}

fn default_param_bits_max() -> u64 {
    constants::PARAM_BITS_MAX
}

fn default_max_public_workers() -> u32 {
    constants::MAX_PUBLIC_WORKERS
}

fn default_max_incubator_workers() -> u32 {
    constants::MAX_INCUBATOR_WORKERS
}

fn default_max_canary_workers() -> u32 {
    constants::MAX_CANARY_WORKERS
}

fn default_max_transfer_workers() -> u32 {
    constants::MAX_TRANSFER_WORKERS
}

fn default_max_robust_workers() -> u32 {
    constants::MAX_ROBUST_WORKERS
}

fn default_train_steps() -> u32 {
    200
}

fn default_train_lr() -> f32 {
    0.05
}

fn default_train_eps() -> f32 {
    1e-8
}

fn default_train_l2() -> f32 {
    1e-5
}

fn default_train_clip_grad() -> f32 {
    1.0
}

fn default_train_batch_windows() -> usize {
    8
}

fn default_public_min_delta_bits() -> f64 {
    32.0
}

fn default_holdout_min_delta_bits() -> f64 {
    16.0
}

fn default_require_canary_for_a() -> bool {
    true
}

fn default_max_holdout_admissions() -> usize {
    constants::MAX_HOLDOUT_ADMISSIONS
}

fn default_max_truth_candidates() -> usize {
    12
}

fn default_max_equivalence_candidates() -> usize {
    8
}

fn default_max_incubator_candidates() -> usize {
    8
}

fn default_max_public_candidates() -> usize {
    constants::MAX_PUBLIC_CANDIDATES
}

fn default_incubator_min_utility_bits() -> f64 {
    8.0
}

fn default_incubator_lambda_code() -> f64 {
    0.1
}

fn default_incubator_lambda_risk() -> f64 {
    0.1
}

fn default_incubator_shadow_steps() -> u32 {
    100
}

fn default_witness_count() -> usize {
    constants::DEFAULT_WITNESS_COUNT
}

fn default_witness_rotation() -> usize {
    constants::DEFAULT_WITNESS_ROTATION
}

fn default_true() -> bool {
    true
}

fn default_phase2_profile_name() -> String {
    "phase2".to_string()
}

fn default_min_improved_families() -> u32 {
    2
}

fn default_min_nonprotected_improved_families() -> u32 {
    1
}

fn default_target_subset() -> Vec<String> {
    vec![
        "det_micro".to_string(),
        "sensor_temporal".to_string(),
        "phys_sim".to_string(),
    ]
}

fn default_codelen_ref_bytes() -> u64 {
    constants::CODELEN_REF_BYTES
}

fn default_transfer_ref_bytes() -> u64 {
    constants::TRANSFER_REF_BYTES
}

fn default_public_static_margin_bpb() -> f64 {
    0.001
}

fn default_holdout_static_margin_bpb() -> f64 {
    0.001
}

fn default_holdout_transfer_margin_bpb() -> f64 {
    0.0
}

fn default_holdout_robust_margin_bpb() -> f64 {
    0.0
}

fn default_family_weight() -> FamilyWeights {
    FamilyWeights {
        static_weight: 0.25,
        transfer_weight: 0.25,
        robust_weight: 0.25,
    }
}

fn default_phase2_weights() -> BTreeMap<String, FamilyWeights> {
    let mut out = BTreeMap::new();
    out.insert("det_micro".to_string(), default_family_weight());
    out.insert("text_code".to_string(), default_family_weight());
    out.insert("sensor_temporal".to_string(), default_family_weight());
    out.insert("phys_sim".to_string(), default_family_weight());
    out
}

fn protected_floor() -> ProtectionFloor {
    ProtectionFloor {
        protected: true,
        max_static_regress_bpb: 0.001,
        max_transfer_regress_bpb: 0.002,
        max_robust_regress_bpb: 0.002,
        min_family_improve_bpb: 0.0005,
    }
}

fn nonprotected_floor() -> ProtectionFloor {
    ProtectionFloor {
        protected: false,
        max_static_regress_bpb: 0.002,
        max_transfer_regress_bpb: 0.003,
        max_robust_regress_bpb: 0.003,
        min_family_improve_bpb: 0.0005,
    }
}

fn default_phase2_floors() -> BTreeMap<String, ProtectionFloor> {
    let mut out = BTreeMap::new();
    out.insert("det_micro".to_string(), protected_floor());
    out.insert("text_code".to_string(), protected_floor());
    out.insert("sensor_temporal".to_string(), nonprotected_floor());
    out.insert("phys_sim".to_string(), nonprotected_floor());
    out
}

fn default_phase2_transfer() -> TransferAdaptSpec {
    TransferAdaptSpec {
        steps: 64,
        lr: 0.03,
        eps: 1e-8,
        l2: 1e-5,
        clip_grad: 1.0,
        batch_windows: 8,
        max_fast_weight_bytes: constants::MAX_TRANSFER_FAST_WEIGHT_BYTES,
        max_delta_bits: constants::MAX_TRANSFER_DELTA_BITS,
        reset_ephemeral_state: true,
        mutable_surfaces: vec![
            "nuisance_head".to_string(),
            "residual_head".to_string(),
            "resid_weights".to_string(),
            "fast_weights".to_string(),
        ],
    }
}

fn default_phase3_profile_name() -> String {
    "phase3".to_string()
}

fn default_phase3_fresh_horizon_epochs() -> u64 {
    8
}

fn default_phase3_budget_truth() -> f64 {
    0.35
}

fn default_phase3_budget_equivalence() -> f64 {
    0.20
}

fn default_phase3_budget_incubator() -> f64 {
    0.25
}

fn default_phase3_budget_cold_frontier() -> f64 {
    0.20
}

fn default_phase3_max_scir_core_ops() -> u32 {
    constants::MAX_SCIR_CORE_OPS
}

fn default_phase3_max_macro_calls_per_program() -> u32 {
    constants::MAX_MACRO_CALLS_PER_PROGRAM
}

fn default_phase3_max_macro_expansion_ops() -> u32 {
    constants::MAX_MACRO_EXPANSION_OPS
}

fn default_phase3_max_macro_depth() -> u32 {
    constants::MAX_MACRO_DEPTH
}

fn default_phase3_max_egraph_nodes() -> u32 {
    constants::MAX_EGRAPH_NODES
}

fn default_phase3_max_egraph_extractions() -> u32 {
    constants::MAX_EGRAPH_EXTRACTIONS
}

fn default_phase3_max_paradigm_public_candidates() -> usize {
    constants::MAX_PARADIGM_PUBLIC_CANDIDATES
}

fn default_phase3_max_pwarm_holdout_admissions() -> usize {
    constants::MAX_PWARM_HOLDOUT_ADMISSIONS
}

fn default_phase3_max_pcold_holdout_admissions() -> usize {
    constants::MAX_PCOLD_HOLDOUT_ADMISSIONS
}

fn default_p_warm_min_static_delta_bpb() -> f64 {
    0.0020
}

fn default_s_class_min_static_delta_bpb() -> f64 {
    0.0
}

fn default_p_warm_min_transfer_delta_bpb() -> f64 {
    0.0010
}

fn default_p_warm_max_robust_regress_bpb() -> f64 {
    0.0005
}

fn default_p_warm_min_recent_family_gain_bpb() -> f64 {
    0.0010
}

fn default_p_cold_min_static_delta_bpb() -> f64 {
    0.0060
}

fn default_p_cold_min_transfer_delta_bpb() -> f64 {
    0.0030
}

fn default_p_cold_min_recent_family_gain_bpb() -> f64 {
    0.0025
}

fn default_p_cold_max_anchor_regret_bpb() -> f64 {
    0.0010
}

fn default_p_cold_max_error_streak() -> u32 {
    3
}

fn default_p_cold_min_improved_families() -> usize {
    2
}

fn default_phase3_min_macro_support() -> u32 {
    constants::MIN_MACRO_SUPPORT
}

fn default_phase3_min_macro_public_gain_bpb() -> f64 {
    constants::MIN_MACRO_PUBLIC_GAIN_BPB
}

fn default_phase3_min_macro_reduction_ratio() -> f64 {
    constants::MIN_MACRO_REDUCTION_RATIO
}

fn default_phase3_max_induced_macros_per_epoch() -> u32 {
    constants::MAX_INDUCED_MACROS_PER_EPOCH
}

fn default_phase3_canary_warm_windows() -> u32 {
    constants::MAX_PARADIGM_CANARY_WINDOWS_WARM
}

fn default_phase3_canary_cold_windows() -> u32 {
    constants::MAX_PARADIGM_CANARY_WINDOWS_COLD
}

fn default_phase4_challenge_min_bucket_score() -> i32 {
    0
}

fn default_phase4_challenge_retire_after_epochs() -> u64 {
    constants::CHALLENGE_RETIRE_AFTER_EPOCHS
}

fn default_phase4_holdout_retire_after_epochs() -> u64 {
    constants::HOLDOUT_RETIRE_AFTER_EPOCHS
}

fn default_phase4_max_hidden_challenge_families() -> usize {
    constants::MAX_HIDDEN_CHALLENGE_FAMILIES
}

fn default_phase4_max_searchlaw_public_candidates() -> usize {
    constants::MAX_SEARCHLAW_PUBLIC_CANDIDATES
}

fn default_phase4_max_searchlaw_ab_candidates() -> usize {
    constants::MAX_SEARCHLAW_AB_CANDIDATES
}

fn default_phase4_searchlaw_min_ab_epochs() -> u32 {
    constants::SEARCHLAW_MIN_AB_EPOCHS
}

fn default_phase4_searchlaw_max_ab_epochs() -> u32 {
    constants::SEARCHLAW_MAX_AB_EPOCHS
}

fn default_phase4_searchlaw_required_yield_improvement() -> f64 {
    constants::SEARCHLAW_REQUIRED_YIELD_IMPROVEMENT
}

fn default_phase4_searchlaw_max_safety_regression() -> f64 {
    constants::SEARCHLAW_MAX_SAFETY_REGRESSION
}

fn default_phase4_max_portfolio_branches() -> usize {
    constants::MAX_PORTFOLIO_BRANCHES
}

fn default_phase4_max_branch_local_debt_credits() -> i32 {
    constants::MAX_BRANCH_LOCAL_DEBT_CREDITS
}

fn default_phase4_max_global_debt_credits() -> i32 {
    constants::MAX_GLOBAL_DEBT_CREDITS
}

fn default_phase4_max_idle_epochs_before_cull() -> u32 {
    constants::MAX_IDLE_EPOCHS_BEFORE_CULL
}

fn default_phase4_max_qd_cells() -> usize {
    constants::MAX_QD_CELLS
}

fn default_phase4_max_needtokens_per_epoch() -> usize {
    constants::MAX_NEEDTOKENS_PER_EPOCH
}

fn default_phase4_max_recombination_parents() -> usize {
    constants::MAX_RECOMBINATION_PARENTS
}

fn default_phase4_yield_points_s() -> i32 {
    1
}

fn default_phase4_yield_points_a() -> i32 {
    2
}

fn default_phase4_yield_points_pwarm() -> i32 {
    3
}

fn default_phase4_yield_points_pcold() -> i32 {
    4
}

fn default_phase4_yield_points_challenge_bonus() -> i32 {
    1
}
