use super::ast::{AstOp, AstShape};
use super::spec::RegimeSpec;

pub const EPS_DIV: f32 = 1.0e-6;

pub const CAP_NODES: u32 = 1024;
pub const CAP_VEC_ELEMS_TOTAL: u64 = 2_000_000;
pub const CAP_AFFINE_MAC: u64 = 50_000_000;
pub const CAP_PEAK_WORDS: u64 = 4_000_000;
pub const CAP_TOTAL_COST: u64 = 150_000_000;

pub const W_NODE: u64 = 100;
pub const W_VEC_ELEM: u64 = 1;
pub const W_AFFINE_MAC: u64 = 2;
pub const W_PEAK_WORD: u64 = 1;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct AstCost {
    pub nodes: u32,
    pub vec_elems_total: u64,
    pub affine_mac: u64,
    pub peak_words_overapprox: u64,
    pub total_cost: u64,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum CostViolation {
    NodesExceeded {
        nodes: u32,
        cap: u32,
    },
    VecElemsTotalExceeded {
        vec_elems_total: u64,
        cap: u64,
    },
    AffineMacExceeded {
        affine_mac: u64,
        cap: u64,
    },
    PeakWordsExceeded {
        peak_words_overapprox: u64,
        cap: u64,
    },
    TotalCostExceeded {
        total_cost: u64,
        cap: u64,
    },
}

pub fn compute_cost(spec: &RegimeSpec) -> Result<AstCost, CostViolation> {
    let nodes = spec.ast.nodes.len() as u32;
    let mut vec_elems_total = 0_u64;
    let mut affine_mac = 0_u64;
    let mut peak_words_overapprox = 0_u64;

    for node in &spec.ast.nodes {
        match node.shape {
            AstShape::Scalar => {
                peak_words_overapprox = peak_words_overapprox.saturating_add(1);
            }
            AstShape::Vector(len) => {
                let len_u64 = u64::from(len);
                vec_elems_total = vec_elems_total.saturating_add(len_u64);
                peak_words_overapprox = peak_words_overapprox.saturating_add(len_u64);
            }
        }

        if let AstOp::Affine {
            in_len, out_len, ..
        } = node.op
        {
            affine_mac =
                affine_mac.saturating_add(u64::from(in_len).saturating_mul(u64::from(out_len)));
        }
    }

    let total_cost = u64::from(nodes)
        .saturating_mul(W_NODE)
        .saturating_add(vec_elems_total.saturating_mul(W_VEC_ELEM))
        .saturating_add(affine_mac.saturating_mul(W_AFFINE_MAC))
        .saturating_add(peak_words_overapprox.saturating_mul(W_PEAK_WORD));

    let cost = AstCost {
        nodes,
        vec_elems_total,
        affine_mac,
        peak_words_overapprox,
        total_cost,
    };

    if cost.nodes > CAP_NODES {
        return Err(CostViolation::NodesExceeded {
            nodes: cost.nodes,
            cap: CAP_NODES,
        });
    }
    if cost.vec_elems_total > CAP_VEC_ELEMS_TOTAL {
        return Err(CostViolation::VecElemsTotalExceeded {
            vec_elems_total: cost.vec_elems_total,
            cap: CAP_VEC_ELEMS_TOTAL,
        });
    }
    if cost.affine_mac > CAP_AFFINE_MAC {
        return Err(CostViolation::AffineMacExceeded {
            affine_mac: cost.affine_mac,
            cap: CAP_AFFINE_MAC,
        });
    }
    if cost.peak_words_overapprox > CAP_PEAK_WORDS {
        return Err(CostViolation::PeakWordsExceeded {
            peak_words_overapprox: cost.peak_words_overapprox,
            cap: CAP_PEAK_WORDS,
        });
    }
    if cost.total_cost > CAP_TOTAL_COST {
        return Err(CostViolation::TotalCostExceeded {
            total_cost: cost.total_cost,
            cap: CAP_TOTAL_COST,
        });
    }

    Ok(cost)
}
