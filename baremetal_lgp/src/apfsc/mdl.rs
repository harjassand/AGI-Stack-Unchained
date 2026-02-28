use crate::apfsc::bytecoder::ScoreSummary;

pub fn gain_bits_vs_incumbent(incumbent: &ScoreSummary, candidate: &ScoreSummary) -> f64 {
    incumbent.total_bits - candidate.total_bits
}

pub fn regress_bits_vs_incumbent(incumbent: &ScoreSummary, candidate: &ScoreSummary) -> f64 {
    (candidate.total_bits - incumbent.total_bits).max(0.0)
}
