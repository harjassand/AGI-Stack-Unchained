use serde::{Deserialize, Serialize};

use crate::apfsc::types::{CandidateId, ConstellationId, FamilyId, SnapshotId};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ChallengeStubReceipt {
    pub candidate_hash: CandidateId,
    pub incumbent_hash: CandidateId,
    pub snapshot_hash: SnapshotId,
    pub constellation_id: ConstellationId,
    pub per_family_bpb: std::collections::BTreeMap<FamilyId, f64>,
    pub replay_hash: String,
}
