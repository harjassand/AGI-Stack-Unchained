use baremetal_lgp::apf3::a64_scan::{scan_block, ScanError};

const NOP: u32 = 0xD503_201F;
const RET_X30: u32 = 0xD65F_03C0;

#[test]
fn apf3_scan_rejects_denylist_and_accepts_safe_patterns() {
    let denied = [
        0xD400_0001_u32, // SVC
        0x1000_0000_u32, // ADR
        0x9000_0000_u32, // ADRP
        0xD61F_0000_u32, // BR x0
        0xD63F_0000_u32, // BLR x0
        0xD530_0000_u32, // MRS
        0xD510_0000_u32, // MSR
        0x1800_0000_u32, // LDR literal class
    ];

    for &w in &denied {
        let err = scan_block(&[w]).expect_err("denylisted instruction must fail");
        match err {
            ScanError::DeniedInstruction { .. } => {}
            _ => panic!("unexpected error type: {err:?}"),
        }
    }

    scan_block(&[NOP, NOP]).expect("NOP-only block should pass");
    scan_block(&[NOP, RET_X30]).expect("RET x30 in final position should pass");

    let err = scan_block(&[RET_X30, NOP, 0xAA1F_03E0]).expect_err("RET not final should fail");
    assert!(matches!(err, ScanError::RetNotFinal { .. }));
}
