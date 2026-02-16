use std::env;
use std::fs;
use std::path::PathBuf;

use verifier::immutable_core::verify_immutable_core;
use verifier::promotion::PromotionReceipt;
use verifier::verify::{Receipt, REASON_KERNEL_INTERNAL_ERROR};

fn main() {
    let args: Vec<String> = env::args().collect();
    if args.len() < 2 {
        eprintln!(
            "usage: verifier verify --bundle-dir <path> --parent-bundle-dir <path_or_empty> --meta-dir <path> --out <path>\n       verifier verify-promotion --bundle-dir <path> --meta-core-root <path> --out <path>\n       verifier immutable-core-verify --repo_root <path> --lock_path <path> --out <path>"
        );
        std::process::exit(1);
    }

    if args[1] == "verify-promotion" {
        run_verify_promotion(&args);
        return;
    }
    if args[1] == "immutable-core-verify" {
        run_immutable_core_verify(&args);
        return;
    }
    if args[1] != "verify" {
        eprintln!(
            "usage: verifier verify --bundle-dir <path> --parent-bundle-dir <path_or_empty> --meta-dir <path> --out <path>\n       verifier verify-promotion --bundle-dir <path> --meta-core-root <path> --out <path>\n       verifier immutable-core-verify --repo_root <path> --lock_path <path> --out <path>"
        );
        std::process::exit(1);
    }

    let mut bundle_dir: Option<PathBuf> = None;
    let mut parent_dir: Option<PathBuf> = None;
    let mut meta_dir: Option<PathBuf> = None;
    let mut out_path: Option<PathBuf> = None;

    let mut i = 2;
    while i < args.len() {
        match args[i].as_str() {
            "--bundle-dir" => {
                i += 1;
                bundle_dir = args.get(i).map(PathBuf::from);
            }
            "--parent-bundle-dir" => {
                i += 1;
                let val = args.get(i).cloned().unwrap_or_default();
                if val.is_empty() {
                    parent_dir = None;
                } else {
                    parent_dir = Some(PathBuf::from(val));
                }
            }
            "--meta-dir" => {
                i += 1;
                meta_dir = args.get(i).map(PathBuf::from);
            }
            "--out" => {
                i += 1;
                out_path = args.get(i).map(PathBuf::from);
            }
            _ => {}
        }
        i += 1;
    }

    let Some(bundle_dir) = bundle_dir else {
        exit_internal(out_path, "missing --bundle-dir");
        return;
    };
    let Some(meta_dir) = meta_dir else {
        exit_internal(out_path, "missing --meta-dir");
        return;
    };
    let Some(out_path) = out_path else {
        exit_internal(None, "missing --out");
        return;
    };

    let receipt = verifier::verify_bundle(&bundle_dir, parent_dir.as_deref(), &meta_dir);
    if let Err(err) = fs::write(&out_path, receipt.canonical_bytes()) {
        eprintln!("failed to write receipt: {err}");
        std::process::exit(1);
    }

    let exit_code = if receipt.verdict == "VALID" {
        0
    } else if receipt.reason_code == REASON_KERNEL_INTERNAL_ERROR {
        1
    } else {
        2
    };
    std::process::exit(exit_code);
}

fn run_verify_promotion(args: &[String]) {
    let mut bundle_dir: Option<PathBuf> = None;
    let mut meta_core_root: Option<PathBuf> = None;
    let mut out_path: Option<PathBuf> = None;

    let mut i = 2;
    while i < args.len() {
        match args[i].as_str() {
            "--bundle-dir" => {
                i += 1;
                bundle_dir = args.get(i).map(PathBuf::from);
            }
            "--meta-core-root" => {
                i += 1;
                meta_core_root = args.get(i).map(PathBuf::from);
            }
            "--out" => {
                i += 1;
                out_path = args.get(i).map(PathBuf::from);
            }
            _ => {}
        }
        i += 1;
    }

    let Some(bundle_dir) = bundle_dir else {
        exit_internal_promo(out_path, "missing --bundle-dir");
        return;
    };
    let Some(meta_core_root) = meta_core_root else {
        exit_internal_promo(out_path, "missing --meta-core-root");
        return;
    };
    let Some(out_path) = out_path else {
        exit_internal_promo(None, "missing --out");
        return;
    };

    let receipt = verifier::promotion::verify_promotion_bundle(&bundle_dir, &meta_core_root);
    if let Err(err) = fs::write(&out_path, receipt.canonical_bytes()) {
        eprintln!("failed to write receipt: {err}");
        std::process::exit(1);
    }

    let exit_code = if receipt.verdict == "VALID" { 0 } else { 2 };
    std::process::exit(exit_code);
}

fn run_immutable_core_verify(args: &[String]) {
    let mut repo_root: Option<PathBuf> = None;
    let mut lock_path: Option<PathBuf> = None;
    let mut out_path: Option<PathBuf> = None;

    let mut i = 2;
    while i < args.len() {
        match args[i].as_str() {
            "--repo_root" => {
                i += 1;
                repo_root = args.get(i).map(PathBuf::from);
            }
            "--lock_path" => {
                i += 1;
                lock_path = args.get(i).map(PathBuf::from);
            }
            "--out" => {
                i += 1;
                out_path = args.get(i).map(PathBuf::from);
            }
            _ => {}
        }
        i += 1;
    }

    let Some(repo_root) = repo_root else {
        eprintln!("missing --repo_root");
        std::process::exit(1);
    };
    let Some(lock_path) = lock_path else {
        eprintln!("missing --lock_path");
        std::process::exit(1);
    };
    let Some(out_path) = out_path else {
        eprintln!("missing --out");
        std::process::exit(1);
    };

    let receipt = verify_immutable_core(&repo_root, &lock_path);
    if let Err(err) = fs::write(&out_path, receipt.canonical_bytes()) {
        eprintln!("failed to write receipt: {err}");
        std::process::exit(1);
    }

    let exit_code = if receipt.verdict == "VALID" { 0 } else { 2 };
    std::process::exit(exit_code);
}

fn exit_internal_promo(out_path: Option<PathBuf>, msg: &str) {
    eprintln!("{msg}");
    if let Some(out_path) = out_path {
        let receipt = PromotionReceipt::new("INVALID".to_string(), vec![REASON_KERNEL_INTERNAL_ERROR.to_string()], None);
        let _ = fs::write(out_path, receipt.canonical_bytes());
    }
    std::process::exit(1);
}

fn exit_internal(out_path: Option<PathBuf>, msg: &str) {
    eprintln!("{msg}");
    if let Some(out_path) = out_path {
        let receipt = Receipt {
            verdict: "INVALID".to_string(),
            bundle_hash: "0000000000000000000000000000000000000000000000000000000000000000".to_string(),
            meta_hash: "0000000000000000000000000000000000000000000000000000000000000000".to_string(),
            kernel_hash: "0000000000000000000000000000000000000000000000000000000000000000".to_string(),
            toolchain_merkle_root: "0000000000000000000000000000000000000000000000000000000000000000".to_string(),
            reason_code: REASON_KERNEL_INTERNAL_ERROR.to_string(),
            details: Default::default(),
        };
        let _ = fs::write(out_path, receipt.canonical_bytes());
    }
    std::process::exit(1);
}
