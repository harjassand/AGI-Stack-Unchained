use crate::apfsc::artifacts::digest_json;
use crate::apfsc::candidate::CandidateBundle;
use crate::apfsc::errors::{ApfscError, Result};
use crate::apfsc::types::{
    LearningLawKind, MemoryLawKind, ParadigmSignature, PromotionClass, SchedulerClass,
};

pub fn compute_paradigm_signature(
    candidate: &CandidateBundle,
    canonical_core_hash: &str,
) -> Result<ParadigmSignature> {
    let primitive_family_hash = digest_json(&candidate.arch_program)?;
    let state_schema_hash = digest_json(&(
        candidate.state_pack.core_weights.len(),
        candidate.state_pack.resid_weights.len(),
        candidate.state_pack.init_state.len(),
    ))?;
    let native_head_semantics_hash = digest_json(&candidate.head_pack.native_head)?;

    Ok(ParadigmSignature {
        primitive_family_hash,
        scheduler_class: candidate
            .schedule_pack
            .scheduler_class
            .unwrap_or(SchedulerClass::SerialScan),
        memory_law: candidate
            .schedule_pack
            .memory_law
            .unwrap_or(MemoryLawKind::FlatState),
        learning_law: candidate
            .schedule_pack
            .learning_law
            .unwrap_or(LearningLawKind::HeadOnlyAdaGrad),
        state_schema_hash,
        native_head_semantics_hash,
        canonical_core_hash: canonical_core_hash.to_string(),
    })
}

pub fn classify_promotion_class(
    incumbent: &ParadigmSignature,
    candidate: &ParadigmSignature,
    structural_changed: bool,
    warm_bridge_pass: bool,
    cold_boundary_available: bool,
) -> Result<PromotionClass> {
    if incumbent == candidate {
        if structural_changed {
            return Ok(PromotionClass::A);
        }
        return Ok(PromotionClass::S);
    }

    if warm_bridge_pass {
        return Ok(PromotionClass::PWarm);
    }

    if cold_boundary_available {
        return Ok(PromotionClass::PCold);
    }

    Err(ApfscError::Validation(
        crate::apfsc::types::JudgeRejectReason::ParadigmClassMismatch.as_reason(),
    ))
}

pub fn structural_change_detected(incumbent_canonical_hash: &str, candidate_canonical_hash: &str) -> bool {
    incumbent_canonical_hash != candidate_canonical_hash
}
