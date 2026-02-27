use baremetal_lgp::abi;
use baremetal_lgp::isa::encoding::{imm14_s, ring_addr};
use baremetal_lgp::isa::op::Op;
use baremetal_lgp::vm::gas::instruction_cost;

#[test]
fn agent1_vm_contract_smoke() {
    assert_eq!(abi::SCRATCH_WORDS, 16_384);
    assert_eq!(imm14_s(0x3FFF), -1);
    assert_eq!(ring_addr(0, 0x3FFF), abi::SCRATCH_MASK_U32 as usize);

    let meta = [0_u32; 16];
    assert_eq!(instruction_cost(Op::Call, 0, &meta), 2);
}
