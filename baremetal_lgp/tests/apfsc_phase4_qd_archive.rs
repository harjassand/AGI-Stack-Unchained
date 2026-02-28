use baremetal_lgp::apfsc::qd_archive::{load_cells, upsert_cell};
use baremetal_lgp::apfsc::types::{MorphologyDescriptor, QdCellRecord};
use tempfile::tempdir;

fn cell(score: f64, novelty: f64) -> QdCellRecord {
    QdCellRecord {
        cell_id: "".to_string(),
        descriptor: MorphologyDescriptor {
            paradigm_signature_hash: "p".to_string(),
            scheduler_class: "s".to_string(),
            memory_law_kind: "m".to_string(),
            macro_density_bin: "low".to_string(),
            state_bytes_bin: "small".to_string(),
            family_profile_bin: "mixed".to_string(),
        },
        occupant_candidate_hash: format!("cand_{score}"),
        public_quality_score: score,
        novelty_score: novelty,
        last_updated_epoch: 1,
    }
}

#[test]
fn qd_archive_replaces_only_on_dominance() {
    let tmp = tempdir().expect("tmp");
    let root = tmp.path().join(".apfsc");

    assert!(upsert_cell(&root, "snap", cell(1.0, 0.1)).expect("insert"));
    assert!(!upsert_cell(&root, "snap", cell(0.8, 0.2)).expect("no replace"));
    assert!(upsert_cell(&root, "snap", cell(1.5, 0.2)).expect("replace"));

    let rows = load_cells(&root, "snap").expect("load");
    assert_eq!(rows.len(), 1);
    assert!(rows[0].public_quality_score >= 1.5);
}
