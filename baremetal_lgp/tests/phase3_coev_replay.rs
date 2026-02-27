#[cfg(all(target_os = "macos", target_arch = "aarch64"))]
#[test]
fn phase3_workers1_replay_is_deterministic_by_digest() {
    let bin = env!("CARGO_BIN_EXE_lgp_coev_hotloop");

    let dir1 = unique_temp_dir("phase3_replay_a");
    let dir2 = unique_temp_dir("phase3_replay_b");

    std::fs::create_dir_all(&dir1).expect("mkdir dir1");
    std::fs::create_dir_all(&dir2).expect("mkdir dir2");

    run_once(bin, &dir1);
    run_once(bin, &dir2);

    let digest1 = std::fs::read_to_string(dir1.join("run_digest.txt")).expect("read digest1");
    let digest2 = std::fs::read_to_string(dir2.join("run_digest.txt")).expect("read digest2");
    assert_eq!(digest1, digest2, "workers=1 replay digest mismatch");

    let b_current_1 = std::fs::read_to_string(dir1.join("b_current.json")).expect("read b1");
    let b_current_2 = std::fs::read_to_string(dir2.join("b_current.json")).expect("read b2");
    assert_eq!(b_current_1, b_current_2, "b_current mismatch across replay");

    let _ = std::fs::remove_dir_all(&dir1);
    let _ = std::fs::remove_dir_all(&dir2);
}

#[cfg(all(target_os = "macos", target_arch = "aarch64"))]
fn run_once(bin: &str, run_dir: &std::path::Path) {
    let status = std::process::Command::new(bin)
        .arg("--seed")
        .arg("777")
        .arg("--run-dir")
        .arg(run_dir)
        .arg("--epochs")
        .arg("1")
        .arg("--workers")
        .arg("1")
        .arg("--a-evals-per-epoch")
        .arg("64")
        .status()
        .expect("run lgp_coev_hotloop");
    assert!(status.success(), "lgp_coev_hotloop run failed");
}

#[cfg(all(target_os = "macos", target_arch = "aarch64"))]
fn unique_temp_dir(prefix: &str) -> std::path::PathBuf {
    let mut path = std::env::temp_dir();
    let pid = std::process::id();
    let nanos = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map_or(0_u128, |d| d.as_nanos());
    path.push(format!("{prefix}_{pid}_{nanos}"));
    path
}
