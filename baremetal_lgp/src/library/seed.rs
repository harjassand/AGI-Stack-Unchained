use crate::contracts::abi::{META_IN_BASE, META_OUT_BASE, META_OUT_LEN, META_WORK_BASE};
use crate::contracts::constants::LIB_SLOTS;
use crate::library::bank::{validate_program, LibraryBank, LibraryProgram};
use crate::search::ir::Opcode;

pub fn seed_library_bank() -> LibraryBank {
    let mut bank = LibraryBank::empty(0);
    let motifs = seeded_motifs();
    for (slot, program) in motifs.into_iter().enumerate() {
        if slot >= LIB_SLOTS {
            break;
        }
        if validate_program(&program).is_ok() {
            bank.slots[slot] = Some(program);
        }
    }
    bank
}

fn seeded_motifs() -> Vec<LibraryProgram> {
    vec![
        motif_vec_wrapper(Opcode::VAdd, 64),  // 0 real VADD wrapper
        motif_vec_wrapper(Opcode::VMul, 64),  // 1 real VMUL wrapper
        motif_vec_wrapper(Opcode::VFma, 64),  // 2 real VFMA wrapper
        motif_vec_wrapper(Opcode::VDot, 64),  // 3 real VDOT wrapper
        motif_vec_wrapper(Opcode::VCAdd, 32), // 4 complex VCADD wrapper
        motif_vec_wrapper(Opcode::VCMul, 32), // 5 complex VCMUL wrapper
        motif_vec_wrapper(Opcode::VCDot, 32), // 6 complex VCDOT wrapper
        motif_output_clear_loop(),            // 7 output clear loop
        motif_simple_normalization(),         // 8 output normalization
        motif_integrator_step(),              // 9 stable integrator skeleton
        motif_vec_wrapper(Opcode::VAdd, 128), // 10
        motif_vec_wrapper(Opcode::VMul, 128), // 11
        motif_vec_wrapper(Opcode::VFma, 128), // 12
        motif_vec_wrapper(Opcode::VDot, 96),  // 13
        motif_vec_wrapper(Opcode::VCAdd, 16), // 14
        motif_vec_wrapper(Opcode::VCMul, 16), // 15
        motif_vec_wrapper(Opcode::VCDot, 16), // 16
        motif_copy_in_to_out(),               // 17
        motif_nonlinear_postprocess(),        // 18
        motif_reduce_pair(),                  // 19
    ]
}

fn motif_vec_wrapper(op: Opcode, len: u16) -> LibraryProgram {
    program(
        vec![
            word(Opcode::LdMU32, 0, 0, 0, META_OUT_BASE as u16),
            word(Opcode::LdMU32, 1, 0, 0, META_IN_BASE as u16),
            word(Opcode::LdMU32, 2, 0, 0, META_WORK_BASE as u16),
            word(op, 0, 1, 2, len),
            word(Opcode::Ret, 0, 0, 0, 0),
        ],
        &[],
    )
}

fn motif_output_clear_loop() -> LibraryProgram {
    // i0=out_base, i1=out_len, i2=1, f0=0.0; store+increment loop.
    let loop_back = ((-3_i32) & 0x3FFF) as u16;
    program(
        vec![
            word(Opcode::LdMU32, 0, 0, 0, META_OUT_BASE as u16),
            word(Opcode::LdMU32, 1, 0, 0, META_OUT_LEN as u16),
            word(Opcode::IConst, 2, 0, 0, 1),
            word(Opcode::FConst, 0, 0, 0, 0),
            word(Opcode::StF, 0, 0, 0, 0),
            word(Opcode::IAdd, 0, 0, 2, 0),
            word(Opcode::Loop, 0, 1, 0, loop_back),
            word(Opcode::Ret, 0, 0, 0, 0),
        ],
        &[(0, 0.0)],
    )
}

fn motif_simple_normalization() -> LibraryProgram {
    let loop_back = ((-6_i32) & 0x3FFF) as u16;
    program(
        vec![
            word(Opcode::LdMU32, 0, 0, 0, META_OUT_BASE as u16),
            word(Opcode::LdMU32, 1, 0, 0, META_OUT_LEN as u16),
            word(Opcode::IConst, 2, 0, 0, 1),
            word(Opcode::FConst, 0, 0, 0, 1), // scale=0.5
            word(Opcode::LdF, 1, 0, 0, 0),
            word(Opcode::FMul, 1, 1, 0, 0),
            word(Opcode::StF, 1, 0, 0, 0),
            word(Opcode::IAdd, 0, 0, 2, 0),
            word(Opcode::Loop, 0, 1, 0, loop_back),
            word(Opcode::Ret, 0, 0, 0, 0),
        ],
        &[(1, 0.5)],
    )
}

fn motif_integrator_step() -> LibraryProgram {
    program(
        vec![
            word(Opcode::LdMU32, 0, 0, 0, META_OUT_BASE as u16),
            word(Opcode::LdMU32, 1, 0, 0, META_IN_BASE as u16),
            word(Opcode::FConst, 0, 0, 0, 2), // dt
            word(Opcode::LdF, 1, 1, 0, 0),
            word(Opcode::FMul, 1, 1, 0, 0),
            word(Opcode::LdF, 2, 0, 0, 0),
            word(Opcode::FAdd, 2, 2, 1, 0),
            word(Opcode::StF, 2, 0, 0, 0),
            word(Opcode::Ret, 0, 0, 0, 0),
        ],
        &[(2, 0.01)],
    )
}

fn motif_copy_in_to_out() -> LibraryProgram {
    program(
        vec![
            word(Opcode::LdMU32, 0, 0, 0, META_IN_BASE as u16),
            word(Opcode::LdMU32, 1, 0, 0, META_OUT_BASE as u16),
            word(Opcode::LdF, 0, 0, 0, 0),
            word(Opcode::StF, 0, 1, 0, 0),
            word(Opcode::Ret, 0, 0, 0, 0),
        ],
        &[],
    )
}

fn motif_nonlinear_postprocess() -> LibraryProgram {
    program(
        vec![
            word(Opcode::LdMU32, 0, 0, 0, META_OUT_BASE as u16),
            word(Opcode::LdF, 1, 0, 0, 0),
            word(Opcode::FTanh, 1, 1, 0, 0),
            word(Opcode::FSigm, 1, 1, 0, 0),
            word(Opcode::StF, 1, 0, 0, 0),
            word(Opcode::Ret, 0, 0, 0, 0),
        ],
        &[],
    )
}

fn motif_reduce_pair() -> LibraryProgram {
    program(
        vec![
            word(Opcode::LdMU32, 0, 0, 0, META_IN_BASE as u16),
            word(Opcode::LdMU32, 1, 0, 0, META_WORK_BASE as u16),
            word(Opcode::VDot, 0, 0, 1, 32),
            word(Opcode::LdMU32, 2, 0, 0, META_OUT_BASE as u16),
            word(Opcode::StF, 0, 2, 0, 0),
            word(Opcode::Ret, 0, 0, 0, 0),
        ],
        &[],
    )
}

fn program(words: Vec<u32>, const_entries: &[(usize, f32)]) -> LibraryProgram {
    let mut const_pool = [0.0_f32; 128];
    for &(idx, value) in const_entries {
        if idx < const_pool.len() {
            const_pool[idx] = value;
        }
    }
    LibraryProgram::new(words, const_pool)
}

fn word(op: Opcode, rd: u8, ra: u8, rb: u8, imm14: u16) -> u32 {
    (op as u32)
        | ((u32::from(rd & 0x0F)) << 6)
        | ((u32::from(ra & 0x0F)) << 10)
        | ((u32::from(rb & 0x0F)) << 14)
        | ((u32::from(imm14 & 0x3FFF)) << 18)
}
