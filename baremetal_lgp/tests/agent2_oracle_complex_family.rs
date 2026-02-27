use baremetal_lgp::oracle::regimes::complex_linear;
use baremetal_lgp::oracle::scoring;
use baremetal_lgp::oracle::SplitMix64;
use baremetal_lgp::types::StopReason;

#[test]
fn complex_family_targets_are_nontrivial_and_mse_scoring_is_ordered() {
    let mut rng = SplitMix64::new(0xBADC0DE);
    let episode = complex_linear::sample(&mut rng, 0.5);

    assert_eq!(episode.family, 2);
    assert_eq!(episode.out_len, episode.target.len());
    assert!(
        episode.target.iter().any(|value| value.abs() > 1.0e-4),
        "complex target should be nontrivial"
    );

    let perfect =
        scoring::score_episode(&episode.target, &episode.target, 100, StopReason::Halt, 0.0);
    let zero_output = vec![0.0_f32; episode.target.len()];
    let imperfect =
        scoring::score_episode(&zero_output, &episode.target, 100, StopReason::Halt, 0.0);

    assert!(
        perfect > imperfect,
        "perfect={perfect}, imperfect={imperfect}"
    );
    assert!(scoring::mse(&zero_output, &episode.target) > 0.0);
    assert_eq!(
        scoring::score_episode(
            &zero_output,
            &episode.target,
            100,
            StopReason::FuelExhausted,
            0.0
        ),
        -1.0e9
    );
}
