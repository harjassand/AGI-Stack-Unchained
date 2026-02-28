use baremetal_lgp::apf3::a64_scan::{scan_block, ScanError};

const NOP: u32 = 0xD503_201F;

fn enc_b(off_words: i32) -> u32 {
    let imm26 = (off_words as i64) & 0x03FF_FFFF;
    0x1400_0000 | (imm26 as u32)
}

#[test]
fn apf3_branch_out_of_slot_is_rejected() {
    let block = [enc_b(8), NOP, NOP];
    let err = scan_block(&block).expect_err("forward branch beyond block must fail");
    assert!(matches!(err, ScanError::BranchOutOfSlot { .. }));
}

#[test]
fn apf3_branch_within_slot_passes() {
    // idx=1 branches back to idx=0.
    let block = [NOP, enc_b(-1), 0xD65F_03C0];
    scan_block(&block).expect("in-slot backward branch should pass");
}
