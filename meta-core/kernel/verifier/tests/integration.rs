use std::fs;
use std::path::Path;

use verifier::verify::{
    verify_bundle, REASON_BLOB_HASH_MISMATCH, REASON_DOMINANCE_CHECK_FAILED,
    REASON_IR_STATIC_CHECK_FAILED, REASON_MANIFEST_SCHEMA_INVALID,
};

#[test]
fn valid_bundle_matches_golden() {
    let bundle = Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/valid_bundle");
    let parent = Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/parent_bundle");
    let meta_dir = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../meta_constitution/v1");

    let receipt = verify_bundle(&bundle, Some(&parent), &meta_dir);
    assert_eq!(receipt.verdict, "VALID");

    let golden = fs::read(Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/golden/valid_receipt.json")).unwrap();
    assert_eq!(receipt.canonical_bytes(), golden);
}

#[test]
fn invalid_bundle_tamper_reason() {
    let bundle = Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/invalid_bundle_tamper");
    let parent = Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/parent_bundle");
    let meta_dir = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../meta_constitution/v1");

    let receipt = verify_bundle(&bundle, Some(&parent), &meta_dir);
    assert_eq!(receipt.verdict, "INVALID");
    assert_eq!(receipt.reason_code, REASON_BLOB_HASH_MISMATCH);
}

#[test]
fn invalid_bundle_schema_reason() {
    let bundle = Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/invalid_bundle_schema");
    let parent = Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/parent_bundle");
    let meta_dir = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../meta_constitution/v1");

    let receipt = verify_bundle(&bundle, Some(&parent), &meta_dir);
    assert_eq!(receipt.verdict, "INVALID");
    assert_eq!(receipt.reason_code, REASON_MANIFEST_SCHEMA_INVALID);
}

#[test]
fn safe_allows_three_children() {
    let bundle = Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/valid_bundle_safe_three");
    let meta_dir = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../meta_constitution/v1");

    let receipt = verify_bundle(&bundle, None, &meta_dir);
    assert_eq!(receipt.verdict, "VALID");
}

#[test]
fn missing_safe_child_fails() {
    let bundle = Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/invalid_bundle_no_safe");
    let meta_dir = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../meta_constitution/v1");

    let receipt = verify_bundle(&bundle, None, &meta_dir);
    assert_eq!(receipt.verdict, "INVALID");
    assert_eq!(receipt.reason_code, REASON_IR_STATIC_CHECK_FAILED);
}

#[test]
fn dominance_requires_condextra_inputs() {
    let bundle =
        Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/invalid_bundle_dominance_missing_condextra_inputs");
    let parent = Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/parent_bundle");
    let meta_dir = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../meta_constitution/v1");

    let receipt = verify_bundle(&bundle, Some(&parent), &meta_dir);
    assert_eq!(receipt.verdict, "INVALID");
    assert_eq!(receipt.reason_code, REASON_DOMINANCE_CHECK_FAILED);
}
