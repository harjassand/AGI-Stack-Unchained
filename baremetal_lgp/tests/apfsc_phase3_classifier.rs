use baremetal_lgp::apfsc::paradigm::classify_promotion_class;
use baremetal_lgp::apfsc::types::{
    LearningLawKind, MemoryLawKind, ParadigmSignature, PromotionClass, SchedulerClass,
};

fn sig(core: &str, scheduler: SchedulerClass) -> ParadigmSignature {
    ParadigmSignature {
        primitive_family_hash: "pfh".to_string(),
        scheduler_class: scheduler,
        memory_law: MemoryLawKind::FlatState,
        learning_law: LearningLawKind::HeadOnlyAdaGrad,
        state_schema_hash: "state".to_string(),
        native_head_semantics_hash: "head".to_string(),
        canonical_core_hash: core.to_string(),
    }
}

#[test]
fn classifier_produces_a_pwarm_pcold() {
    let incumbent = sig("core_a", SchedulerClass::SerialScan);

    let a = classify_promotion_class(&incumbent, &incumbent, true, true, false).expect("A");
    assert_eq!(a, PromotionClass::A);

    let warm_sig = sig("core_b", SchedulerClass::EventSparse);
    let pwarm = classify_promotion_class(&incumbent, &warm_sig, true, true, false).expect("PWarm");
    assert_eq!(pwarm, PromotionClass::PWarm);

    let cold_sig = sig("core_c", SchedulerClass::TwoPassMemory);
    let pcold = classify_promotion_class(&incumbent, &cold_sig, true, false, true).expect("PCold");
    assert_eq!(pcold, PromotionClass::PCold);
}
