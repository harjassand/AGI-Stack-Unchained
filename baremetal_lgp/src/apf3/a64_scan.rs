#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ScanError {
    DeniedInstruction {
        idx: usize,
        word: u32,
        reason: &'static str,
    },
    BranchOutOfSlot {
        idx: usize,
        word: u32,
        target_idx: isize,
    },
    RetNotFinal {
        idx: usize,
        word: u32,
    },
}

const A64_NOP: u32 = 0xD503_201F;

pub fn scan_block(words: &[u32]) -> Result<(), ScanError> {
    let mut ret_idx: Option<usize> = None;

    for (idx, &word) in words.iter().enumerate() {
        if let Some(reason) = deny_reason(word) {
            return Err(ScanError::DeniedInstruction { idx, word, reason });
        }

        if is_br(word) {
            return Err(ScanError::DeniedInstruction {
                idx,
                word,
                reason: "indirect BR denied",
            });
        }
        if is_blr(word) {
            return Err(ScanError::DeniedInstruction {
                idx,
                word,
                reason: "indirect BLR denied",
            });
        }

        if is_ret(word) {
            let rn = ((word >> 5) & 0x1f) as u8;
            if rn != 30 {
                return Err(ScanError::DeniedInstruction {
                    idx,
                    word,
                    reason: "RET allowed only with X30",
                });
            }
            if ret_idx.is_none() {
                ret_idx = Some(idx);
            }
        }

        if let Some(target_idx) = decode_branch_target_idx(idx, word) {
            if target_idx < 0 || target_idx >= words.len() as isize {
                return Err(ScanError::BranchOutOfSlot {
                    idx,
                    word,
                    target_idx,
                });
            }
        }
    }

    if let Some(ret_at) = ret_idx {
        for &after in &words[ret_at + 1..] {
            if after != A64_NOP {
                return Err(ScanError::RetNotFinal {
                    idx: ret_at,
                    word: words[ret_at],
                });
            }
        }
    }

    Ok(())
}

fn deny_reason(word: u32) -> Option<&'static str> {
    if is_svc(word) {
        return Some("SVC denied");
    }
    if is_hvc(word) {
        return Some("HVC denied");
    }
    if is_smc(word) {
        return Some("SMC denied");
    }
    if is_brk(word) {
        return Some("BRK denied");
    }
    if is_hlt(word) {
        return Some("HLT denied");
    }
    if word == 0xD69F_03E0 {
        return Some("ERET denied");
    }
    if is_mrs(word) {
        return Some("MRS denied");
    }
    if is_msr(word) {
        return Some("MSR denied");
    }
    if is_adr(word) {
        return Some("ADR denied");
    }
    if is_adrp(word) {
        return Some("ADRP denied");
    }
    if is_ldr_literal(word) {
        return Some("LDR literal denied");
    }
    if is_broad_system(word) {
        return Some("system instruction denied");
    }

    None
}

fn decode_branch_target_idx(idx: usize, word: u32) -> Option<isize> {
    if is_b(word) || is_bl(word) {
        let imm26 = (word & 0x03ff_ffff) as i64;
        let off_words = sign_extend(imm26, 26);
        return Some(idx as isize + off_words as isize);
    }

    if is_b_cond(word) {
        let imm19 = ((word >> 5) & 0x7ffff) as i64;
        let off_words = sign_extend(imm19, 19);
        return Some(idx as isize + off_words as isize);
    }

    if is_cbz(word) || is_cbnz(word) {
        let imm19 = ((word >> 5) & 0x7ffff) as i64;
        let off_words = sign_extend(imm19, 19);
        return Some(idx as isize + off_words as isize);
    }

    if is_tbz(word) || is_tbnz(word) {
        let imm14 = ((word >> 5) & 0x3fff) as i64;
        let off_words = sign_extend(imm14, 14);
        return Some(idx as isize + off_words as isize);
    }

    None
}

#[inline(always)]
fn sign_extend(value: i64, bits: u32) -> i64 {
    let shift = 64 - bits;
    (value << shift) >> shift
}

#[inline(always)]
fn is_svc(w: u32) -> bool {
    (w & 0xFFE0_001F) == 0xD400_0001
}

#[inline(always)]
fn is_hvc(w: u32) -> bool {
    (w & 0xFFE0_001F) == 0xD400_0002
}

#[inline(always)]
fn is_smc(w: u32) -> bool {
    (w & 0xFFE0_001F) == 0xD400_0003
}

#[inline(always)]
fn is_brk(w: u32) -> bool {
    (w & 0xFFE0_001F) == 0xD420_0000
}

#[inline(always)]
fn is_hlt(w: u32) -> bool {
    (w & 0xFFE0_001F) == 0xD440_0000
}

#[inline(always)]
fn is_mrs(w: u32) -> bool {
    (w & 0xFFC0_0000) == 0xD530_0000
}

#[inline(always)]
fn is_msr(w: u32) -> bool {
    (w & 0xFFC0_0000) == 0xD510_0000
}

#[inline(always)]
fn is_adr(w: u32) -> bool {
    (w & 0x9F00_0000) == 0x1000_0000
}

#[inline(always)]
fn is_adrp(w: u32) -> bool {
    (w & 0x9F00_0000) == 0x9000_0000
}

#[inline(always)]
fn is_ldr_literal(w: u32) -> bool {
    (w & 0x3B00_0000) == 0x1800_0000
}

#[inline(always)]
fn is_br(w: u32) -> bool {
    (w & 0xFFFF_FC1F) == 0xD61F_0000
}

#[inline(always)]
fn is_blr(w: u32) -> bool {
    (w & 0xFFFF_FC1F) == 0xD63F_0000
}

#[inline(always)]
fn is_ret(w: u32) -> bool {
    (w & 0xFFFF_FC1F) == 0xD65F_0000
}

#[inline(always)]
fn is_broad_system(w: u32) -> bool {
    (w & 0xFF00_0000) == 0xD500_0000 && w != A64_NOP
}

#[inline(always)]
fn is_b(w: u32) -> bool {
    (w & 0x7C00_0000) == 0x1400_0000
}

#[inline(always)]
fn is_bl(w: u32) -> bool {
    (w & 0x7C00_0000) == 0x9400_0000
}

#[inline(always)]
fn is_b_cond(w: u32) -> bool {
    (w & 0xFF00_0010) == 0x5400_0000
}

#[inline(always)]
fn is_cbz(w: u32) -> bool {
    (w & 0x7F00_0000) == 0x3400_0000
}

#[inline(always)]
fn is_cbnz(w: u32) -> bool {
    (w & 0x7F00_0000) == 0x3500_0000
}

#[inline(always)]
fn is_tbz(w: u32) -> bool {
    (w & 0x7F00_0000) == 0x3600_0000
}

#[inline(always)]
fn is_tbnz(w: u32) -> bool {
    (w & 0x7F00_0000) == 0x3700_0000
}
