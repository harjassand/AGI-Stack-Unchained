use baremetal_lgp::oracle::scoring::worst_score;

#[test]
fn agent2_oracle_contract_smoke() {
    assert!(worst_score().is_infinite());
    assert!(worst_score().is_sign_negative());
}
