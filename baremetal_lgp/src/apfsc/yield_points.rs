use crate::apfsc::config::Phase1Config;
use crate::apfsc::types::PromotionClass;

pub fn points_for_class(class: PromotionClass, challenge_bonus: bool, cfg: &Phase1Config) -> i32 {
    let base = match class {
        PromotionClass::S => cfg.phase4.yield_points_s,
        PromotionClass::A => cfg.phase4.yield_points_a,
        PromotionClass::PWarm => cfg.phase4.yield_points_pwarm,
        PromotionClass::PCold => cfg.phase4.yield_points_pcold,
        PromotionClass::G | PromotionClass::GDisabled => 0,
    };
    if challenge_bonus {
        base + cfg.phase4.yield_points_challenge_bonus
    } else {
        base
    }
}
