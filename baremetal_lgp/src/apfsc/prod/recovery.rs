use std::collections::BTreeSet;
use std::path::{Path, PathBuf};

use rusqlite::{params, Connection, OptionalExtension};

use crate::apfsc::artifacts::{read_pointer, write_pointer};
use crate::apfsc::candidate::{
    list_candidates, load_candidate, rebase_active_candidate_to_snapshot,
};
use crate::apfsc::config::Phase1Config;
use crate::apfsc::constellation::load_active_constellation;
use crate::apfsc::errors::{ApfscError, Result};
use crate::apfsc::orchestrator::{run_phase2_epoch, run_phase3_epoch, run_phase4_epoch};
use crate::apfsc::prod::control_db::{list_jobs_by_state, with_busy_retry};
use crate::apfsc::prod::gc::{gc_candidates, DEFAULT_TOMBSTONE_DAYS};
use crate::apfsc::prod::jobs::now_unix_s;
use crate::apfsc::prod::journal::{
    append_journal, has_commit_marker, load_journal, JobState, JournalRecord,
};
use crate::apfsc::prod::leases::{
    acquire_epoch_critical_section, release_epoch_critical_section, renew_epoch_critical_section,
};
use crate::apfsc::scir::ast::ScirOp;
use crate::apfsc::types::EpochReport;
use crate::oracle3::compile::{synthesize_alien_jit_blob_from_seed, AlienSeedRecord};

const LEASE_TTL_S: u64 = 300;
const AUTO_GC_INTERVAL_EPOCHS: u32 = 25;

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize, PartialEq)]
pub struct RecoveryReceipt {
    pub recovered_jobs: Vec<String>,
    pub restarted_jobs: Vec<String>,
    pub resumed_runs: Vec<String>,
    pub failed_runs: Vec<String>,
    pub ts: u64,
}

pub fn startup_recovery(root: &Path, conn: &Connection) -> Result<RecoveryReceipt> {
    rehydrate_alien_seed_records(root)?;

    let pending = list_jobs_by_state(conn, &["Leased", "Running", "RecoveryPending"])?;
    let mut recovered = Vec::new();
    let mut restarted = Vec::new();
    let mut resumed_runs = Vec::new();
    let mut failed_runs = Vec::new();

    for (job_id, _state) in pending {
        if has_commit_marker(root, &job_id)? {
            with_busy_retry(|| {
                conn.execute(
                    "UPDATE jobs SET state='Committed', finished_at=datetime('now') WHERE job_id=?1",
                    params![job_id],
                )
            })?;
            recovered.push(job_id);
        } else {
            with_busy_retry(|| {
                conn.execute(
                    "UPDATE jobs SET state='RecoveryPending' WHERE job_id=?1",
                    params![job_id],
                )
            })?;
            append_journal(
                root,
                &JournalRecord {
                    job_id: job_id.clone(),
                    run_id: None,
                    idempotency_key: format!("recover:{}", job_id),
                    stage: "startup_recovery".to_string(),
                    target_entity_hash: None,
                    planned_effects: vec!["restart_from_last_safe_stage".to_string()],
                    created_at: now_unix_s(),
                    state: JobState::RecoveryPending,
                    receipt_hash: None,
                    commit_marker: None,
                },
            )?;
            restarted.push(job_id);
        }
    }

    let runs: Vec<(String, String, i64, i64)> = with_busy_retry(|| {
        let mut stmt = conn.prepare(
            "SELECT run_id, profile,
                    cast(target_epochs as integer),
                    cast(completed_epochs as integer)
             FROM runs
             WHERE state IN ('Running', 'RecoveryPending')
             ORDER BY created_at, run_id",
        )?;
        let mapped = stmt.query_map([], |r| {
            Ok((
                r.get::<_, String>(0)?,
                r.get::<_, String>(1)?,
                r.get::<_, i64>(2)?,
                r.get::<_, i64>(3)?,
            ))
        })?;
        let mut out = Vec::new();
        for row in mapped {
            out.push(row?);
        }
        Ok(out)
    })?;

    for (run_id, profile, target_epochs_raw, completed_epochs_raw) in runs {
        let target_epochs = target_epochs_raw.max(0) as u32;
        let completed_epochs = completed_epochs_raw.max(0) as u32;
        let committed_epochs = last_committed_epoch(root, &run_id)?;
        let safe_epoch = committed_epochs.max(completed_epochs);

        if safe_epoch >= target_epochs {
            with_busy_retry(|| {
                conn.execute(
                    "UPDATE runs
                     SET state='Succeeded', completed_epochs=?2, last_stage='run_complete',
                         updated_at=datetime('now')
                     WHERE run_id=?1",
                    params![run_id, target_epochs as i64],
                )
            })?;
            if !has_run_commit_marker(root, &run_id)? {
                let idk = run_idempotency_key(conn, &run_id)?;
                append_journal(
                    root,
                    &JournalRecord {
                        job_id: format!("run:{}", run_id),
                        run_id: Some(run_id.clone()),
                        idempotency_key: idk,
                        stage: "run_complete".to_string(),
                        target_entity_hash: None,
                        planned_effects: vec!["resume_noop".to_string()],
                        created_at: now_unix_s(),
                        state: JobState::Committed,
                        receipt_hash: None,
                        commit_marker: Some(format!("run_commit:{}", run_id)),
                    },
                )?;
            }
            resumed_runs.push(run_id);
            continue;
        }

        with_busy_retry(|| {
            conn.execute(
                "UPDATE runs
                 SET state='RecoveryPending', completed_epochs=?2, last_stage='startup_recovery',
                     updated_at=datetime('now')
                 WHERE run_id=?1",
                params![run_id, safe_epoch as i64],
            )
        })?;
        append_journal(
            root,
            &JournalRecord {
                job_id: format!("run:{}", run_id),
                run_id: Some(run_id.clone()),
                idempotency_key: run_idempotency_key(conn, &run_id)?,
                stage: "startup_recovery".to_string(),
                target_entity_hash: None,
                planned_effects: vec![format!("resume_from_epoch:{}", safe_epoch + 1)],
                created_at: now_unix_s(),
                state: JobState::RecoveryPending,
                receipt_hash: None,
                commit_marker: None,
            },
        )?;

        match resume_run(root, conn, &run_id, &profile, safe_epoch, target_epochs) {
            Ok(_) => resumed_runs.push(run_id),
            Err(_) => failed_runs.push(run_id),
        }
    }

    Ok(RecoveryReceipt {
        recovered_jobs: recovered,
        restarted_jobs: restarted,
        resumed_runs,
        failed_runs,
        ts: now_unix_s(),
    })
}

fn rehydrate_alien_seed_records(root: &Path) -> Result<()> {
    let mut candidate_hashes = BTreeSet::new();
    for pointer in [
        "active_candidate",
        "rollback_candidate",
        "active_incubator_pointer",
    ] {
        if let Ok(hash) = crate::apfsc::artifacts::read_pointer(root, pointer) {
            if !hash.is_empty() {
                candidate_hashes.insert(hash);
            }
        }
    }
    if candidate_hashes.is_empty() {
        return Ok(());
    }

    let runtime_dir = root.join("runtime").join("alien_jit");
    std::fs::create_dir_all(&runtime_dir)
        .map_err(|e| ApfscError::Protocol(format!("create {}: {e}", runtime_dir.display())))?;

    for candidate_hash in candidate_hashes {
        let bundle = match load_candidate(root, &candidate_hash) {
            Ok(v) => v,
            Err(_) => continue,
        };
        let mut count = 0usize;
        for node in &bundle.arch_program.nodes {
            if let ScirOp::Alien {
                seed_hash,
                mutation_vector,
                fused_ops_hint,
            } = &node.op
            {
                let seed = AlienSeedRecord {
                    seed_hash: seed_hash.clone(),
                    ops_added: mutation_vector.ops_added.clone(),
                    ops_removed: mutation_vector.ops_removed.clone(),
                    fused_ops_hint: *fused_ops_hint,
                    compile_seed: 0,
                    max_fixpoint_iters: 64,
                    epsilon: 1.0 / 1024.0,
                };
                let blob = synthesize_alien_jit_blob_from_seed(&seed);
                crate::apfsc::artifacts::write_json_atomic(
                    &runtime_dir.join(format!("{}-node{}.json", candidate_hash, node.id)),
                    &blob,
                )?;
                count += 1;
            }
        }
        if count > 0 {
            crate::apfsc::artifacts::append_jsonl_atomic(
                &root.join("archives").join("alien_rehydration.jsonl"),
                &serde_json::json!({
                    "candidate_hash": candidate_hash,
                    "blob_count": count,
                    "ts": now_unix_s(),
                }),
            )?;
        }
    }
    Ok(())
}

pub fn resume_run(
    root: &Path,
    conn: &Connection,
    run_id: &str,
    profile: &str,
    completed_epochs: u32,
    target_epochs: u32,
) -> Result<()> {
    if !run_state_allows_progress(conn, run_id)? {
        return Err(ApfscError::Validation(format!(
            "run {} no longer active (operator override or terminal state)",
            run_id
        )));
    }

    // Omega/silent mode can restart with stale disk pointers while candidate state was volatile.
    // Rehydrate or reseed candidate pointers before entering the epoch loop.
    let _ = ensure_runtime_active_candidate(root, profile)?;

    if target_epochs <= completed_epochs {
        with_busy_retry(|| {
            conn.execute(
                "UPDATE runs
                 SET state='Succeeded', completed_epochs=?2, last_stage='run_complete',
                     updated_at=datetime('now')
                 WHERE run_id=?1",
                params![run_id, target_epochs as i64],
            )
        })?;
        return Ok(());
    }

    let owner_id = format!("run:{}", run_id);
    let idk = run_idempotency_key(conn, run_id)?;
    if !acquire_epoch_critical_section(conn, &owner_id, LEASE_TTL_S, now_unix_s())? {
        return Err(ApfscError::Validation(
            "failed to acquire orchestrator/judge/activation leases".to_string(),
        ));
    }

    let run_result = (|| -> Result<()> {
        for epoch in (completed_epochs + 1)..=target_epochs {
            if !run_state_allows_progress(conn, run_id)? {
                return Err(ApfscError::Validation(
                    "run aborted by operator override".to_string(),
                ));
            }
            if !renew_epoch_critical_section(conn, &owner_id, LEASE_TTL_S, now_unix_s())? {
                return Err(ApfscError::Validation(
                    "lost epoch critical-section lease while resuming run".to_string(),
                ));
            }

            append_journal(
                root,
                &JournalRecord {
                    job_id: format!("run:{}", run_id),
                    run_id: Some(run_id.to_string()),
                    idempotency_key: idk.clone(),
                    stage: format!("epoch:{}:begin", epoch),
                    target_entity_hash: None,
                    planned_effects: vec![format!("epoch_execute:{}", epoch)],
                    created_at: now_unix_s(),
                    state: JobState::Running,
                    receipt_hash: None,
                    commit_marker: None,
                },
            )?;

            let receipt = run_single_epoch(root, profile)?;
            let receipt_hash = crate::apfsc::artifacts::digest_json(&receipt)?;

            append_journal(
                root,
                &JournalRecord {
                    job_id: format!("run:{}", run_id),
                    run_id: Some(run_id.to_string()),
                    idempotency_key: idk.clone(),
                    stage: format!("epoch:{}:commit", epoch),
                    target_entity_hash: None,
                    planned_effects: vec![format!("epoch_commit:{}", epoch)],
                    created_at: now_unix_s(),
                    state: JobState::Running,
                    receipt_hash: Some(receipt_hash.clone()),
                    commit_marker: Some(format!("epoch_commit:{}:{}", run_id, epoch)),
                },
            )?;

            with_busy_retry(|| {
                conn.execute(
                    "UPDATE runs
                     SET completed_epochs=?2, last_receipt_hash=?3, last_stage=?4, state='Running',
                         updated_at=datetime('now')
                     WHERE run_id=?1",
                    params![
                        run_id,
                        epoch as i64,
                        receipt_hash,
                        format!("epoch:{}:commit", epoch)
                    ],
                )
            })?;

            if epoch % AUTO_GC_INTERVAL_EPOCHS == 0 {
                let gc_report = gc_candidates(root, false)?;
                append_journal(
                    root,
                    &JournalRecord {
                        job_id: format!("run:{}", run_id),
                        run_id: Some(run_id.to_string()),
                        idempotency_key: idk.clone(),
                        stage: format!("epoch:{}:gc", epoch),
                        target_entity_hash: None,
                        planned_effects: vec![format!(
                            "gc_candidates:tombstone_days={}",
                            DEFAULT_TOMBSTONE_DAYS
                        )],
                        created_at: now_unix_s(),
                        state: JobState::Running,
                        receipt_hash: Some(crate::apfsc::artifacts::digest_json(&gc_report)?),
                        commit_marker: Some(format!("epoch_gc:{}:{}", run_id, epoch)),
                    },
                )?;
            }

            let _ = crate::apfsc::searchlaw_eval::advance_thermal_spike_epoch(root);
        }

        with_busy_retry(|| {
            conn.execute(
                "UPDATE runs
                 SET state='Succeeded', completed_epochs=?2, last_stage='run_complete',
                     updated_at=datetime('now')
                 WHERE run_id=?1",
                params![run_id, target_epochs as i64],
            )
        })?;

        append_journal(
            root,
            &JournalRecord {
                job_id: format!("run:{}", run_id),
                run_id: Some(run_id.to_string()),
                idempotency_key: idk,
                stage: "run_complete".to_string(),
                target_entity_hash: None,
                planned_effects: vec!["commit".to_string()],
                created_at: now_unix_s(),
                state: JobState::Committed,
                receipt_hash: None,
                commit_marker: Some(format!("run_commit:{}", run_id)),
            },
        )?;
        Ok(())
    })();

    let release_res = release_epoch_critical_section(conn, &owner_id);
    match run_result {
        Ok(()) => {
            release_res?;
            Ok(())
        }
        Err(err) => {
            let _ = release_res;
            let _ = with_busy_retry(|| {
                conn.execute(
                    "UPDATE runs
                     SET state='RecoveryPending', last_stage='resume_failed', updated_at=datetime('now')
                     WHERE run_id=?1",
                    params![run_id],
                )
            });
            let _ = append_journal(
                root,
                &JournalRecord {
                    job_id: format!("run:{}", run_id),
                    run_id: Some(run_id.to_string()),
                    idempotency_key: run_idempotency_key(conn, run_id)
                        .unwrap_or_else(|_| format!("run:{}", run_id)),
                    stage: "run_resume_failed".to_string(),
                    target_entity_hash: None,
                    planned_effects: vec!["retry_after_restart".to_string()],
                    created_at: now_unix_s(),
                    state: JobState::RecoveryPending,
                    receipt_hash: None,
                    commit_marker: None,
                },
            );
            Err(err)
        }
    }
}

fn run_state_allows_progress(conn: &Connection, run_id: &str) -> Result<bool> {
    let state: Option<String> = with_busy_retry(|| {
        conn.query_row(
            "SELECT state FROM runs WHERE run_id=?1",
            params![run_id],
            |r| r.get(0),
        )
        .optional()
    })?;
    Ok(matches!(
        state.as_deref(),
        Some("Running" | "RecoveryPending")
    ))
}

fn runtime_config_candidates(root: &Path, profile: &str) -> Vec<PathBuf> {
    let cfg_dir = root.join("config");
    if matches!(profile, "phase4" | "prod" | "production") {
        vec![
            cfg_dir.join("phase4_crucible_16g.toml"),
            cfg_dir.join("phase4.toml"),
            cfg_dir.join("phase4_frontier.toml"),
            cfg_dir.join("phase4_frontier_probe.toml"),
            cfg_dir.join("phase4_smoke.toml"),
        ]
    } else {
        vec![
            cfg_dir.join(format!("{profile}.toml")),
            cfg_dir.join(format!("{profile}_frontier.toml")),
            cfg_dir.join("phase4_frontier.toml"),
            cfg_dir.join("phase4_frontier_probe.toml"),
            cfg_dir.join("phase4_smoke.toml"),
        ]
    }
}

fn load_runtime_phase_config(root: &Path, profile: &str) -> Phase1Config {
    for path in runtime_config_candidates(root, profile) {
        if !path.exists() {
            continue;
        }
        if let Ok(cfg) = Phase1Config::from_path(&path) {
            return cfg;
        }
    }
    Phase1Config::default()
}

fn pointer_candidate(root: &Path, name: &str) -> Option<(String, String)> {
    let candidate_hash = read_pointer(root, name).ok()?;
    if candidate_hash.is_empty() {
        return None;
    }
    let bundle = load_candidate(root, &candidate_hash).ok()?;
    Some((candidate_hash, bundle.manifest.snapshot_hash))
}

fn any_candidate(root: &Path) -> Result<Option<(String, String)>> {
    for candidate_hash in list_candidates(root)? {
        let bundle = match load_candidate(root, &candidate_hash) {
            Ok(v) => v,
            Err(_) => continue,
        };
        return Ok(Some((candidate_hash, bundle.manifest.snapshot_hash)));
    }
    Ok(None)
}

fn preferred_runtime_snapshot(root: &Path) -> Option<String> {
    if let Ok(constellation) = load_active_constellation(root) {
        if !constellation.snapshot_hash.is_empty() {
            return Some(constellation.snapshot_hash);
        }
    }
    read_pointer(root, "active_snapshot")
        .ok()
        .filter(|s| !s.is_empty())
}

fn align_active_candidate_snapshot(root: &Path, candidate_hash: &str) -> Result<String> {
    let Some(target_snapshot) = preferred_runtime_snapshot(root) else {
        return Ok(candidate_hash.to_string());
    };
    let bundle = load_candidate(root, candidate_hash)?;
    if bundle.manifest.snapshot_hash == target_snapshot {
        write_pointer(root, "active_snapshot", &target_snapshot)?;
        return Ok(candidate_hash.to_string());
    }
    let rebased = rebase_active_candidate_to_snapshot(root, &target_snapshot)?
        .unwrap_or_else(|| candidate_hash.to_string());
    write_pointer(root, "active_snapshot", &target_snapshot)?;
    Ok(rebased)
}

fn ensure_runtime_active_candidate(root: &Path, profile: &str) -> Result<String> {
    if let Some((active, snapshot)) = pointer_candidate(root, "active_candidate") {
        let _ = write_pointer(root, "active_snapshot", &snapshot);
        return align_active_candidate_snapshot(root, &active);
    }
    if let Some((rollback, snapshot)) = pointer_candidate(root, "rollback_candidate") {
        write_pointer(root, "active_candidate", &rollback)?;
        write_pointer(root, "active_snapshot", &snapshot)?;
        return align_active_candidate_snapshot(root, &rollback);
    }
    if let Some((candidate_hash, snapshot)) = any_candidate(root)? {
        write_pointer(root, "active_candidate", &candidate_hash)?;
        write_pointer(root, "rollback_candidate", &candidate_hash)?;
        write_pointer(root, "active_snapshot", &snapshot)?;
        return align_active_candidate_snapshot(root, &candidate_hash);
    }

    let cfg = load_runtime_phase_config(root, profile);
    let seeded = crate::apfsc::seed::seed_init(root, &cfg, None, false)?;
    align_active_candidate_snapshot(root, &seeded)
}

fn run_single_epoch(root: &Path, profile: &str) -> Result<EpochReport> {
    let cfg = load_runtime_phase_config(root, profile);
    match profile {
        "phase2" => run_phase2_epoch(root, &cfg, None),
        "phase3" => run_phase3_epoch(root, &cfg, None),
        "phase4" | "prod" | "production" => run_phase4_epoch(root, &cfg, None),
        _ => Err(ApfscError::Validation(format!(
            "unsupported run profile: {}",
            profile
        ))),
    }
}

fn last_committed_epoch(root: &Path, run_id: &str) -> Result<u32> {
    let rows = load_journal(root)?;
    let mut max_epoch = 0u32;
    let prefix = format!("epoch_commit:{}:", run_id);
    for row in rows {
        if row.run_id.as_deref() != Some(run_id) {
            continue;
        }
        let marker = match row.commit_marker.as_deref() {
            Some(m) => m,
            None => continue,
        };
        if !marker.starts_with(&prefix) {
            continue;
        }
        if let Some(epoch_str) = marker.rsplit(':').next() {
            if let Ok(epoch) = epoch_str.parse::<u32>() {
                max_epoch = max_epoch.max(epoch);
            }
        }
    }
    Ok(max_epoch)
}

fn has_run_commit_marker(root: &Path, run_id: &str) -> Result<bool> {
    let marker = format!("run_commit:{}", run_id);
    let rows = load_journal(root)?;
    Ok(rows.iter().rev().any(|r| {
        r.run_id.as_deref() == Some(run_id) && r.commit_marker.as_deref() == Some(&marker)
    }))
}

fn run_idempotency_key(conn: &Connection, run_id: &str) -> Result<String> {
    with_busy_retry(|| {
        conn.query_row(
            "SELECT idempotency_key FROM runs WHERE run_id=?1",
            [run_id],
            |r| r.get(0),
        )
    })
}
