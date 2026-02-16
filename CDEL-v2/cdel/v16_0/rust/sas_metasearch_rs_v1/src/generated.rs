pub struct PriorRow {
    pub theory_kind: &'static str,
    pub norm_pow_p: u8,
    pub weight_q32: u32,
}

pub const K_MAX_DEV_EVALS: u64 = 4u64;

pub const PRIOR_TABLE: &[PriorRow] = &[
    PriorRow { theory_kind: "CANDIDATE_CENTRAL_POWERLAW_V1", norm_pow_p: 1, weight_q32: 39768216u32 },
    PriorRow { theory_kind: "CANDIDATE_CENTRAL_POWERLAW_V1", norm_pow_p: 2, weight_q32: 39768216u32 },
    PriorRow { theory_kind: "CANDIDATE_CENTRAL_POWERLAW_V1", norm_pow_p: 3, weight_q32: 4016589786u32 },
    PriorRow { theory_kind: "CANDIDATE_CENTRAL_POWERLAW_V1", norm_pow_p: 4, weight_q32: 39768216u32 },
    PriorRow { theory_kind: "CANDIDATE_NBODY_POWERLAW_V1", norm_pow_p: 1, weight_q32: 39768216u32 },
    PriorRow { theory_kind: "CANDIDATE_NBODY_POWERLAW_V1", norm_pow_p: 2, weight_q32: 39768216u32 },
    PriorRow { theory_kind: "CANDIDATE_NBODY_POWERLAW_V1", norm_pow_p: 3, weight_q32: 39768215u32 },
    PriorRow { theory_kind: "CANDIDATE_NBODY_POWERLAW_V1", norm_pow_p: 4, weight_q32: 39768215u32 },
];
