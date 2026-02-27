#[inline]
fn enc_movz(rd: u8, imm16: u16, lsl: u8) -> u32 {
    let hw = u32::from(lsl / 16) & 0x3;
    0xD2800000 | (hw << 21) | (u32::from(imm16) << 5) | u32::from(rd)
}

#[inline]
fn enc_movk(rd: u8, imm16: u16, lsl: u8) -> u32 {
    let hw = u32::from(lsl / 16) & 0x3;
    0xF2800000 | (hw << 21) | (u32::from(imm16) << 5) | u32::from(rd)
}

#[inline]
fn enc_br(rn: u8) -> u32 {
    0xD61F0000 | (u32::from(rn) << 5)
}

extern "C" fn rust_vadd_kernel(dst: *mut f32, a: *const f32, b: *const f32, len: usize) {
    // SAFETY: caller provides valid pointers for len f32 values.
    unsafe {
        for i in 0..len {
            *dst.add(i) = *a.add(i) + *b.add(i);
        }
    }
}

pub fn emit_vadd_stub(target: usize) -> Vec<u8> {
    let x9 = 9u8;
    let words = [
        enc_movz(x9, (target & 0xFFFF) as u16, 0),
        enc_movk(x9, ((target >> 16) & 0xFFFF) as u16, 16),
        enc_movk(x9, ((target >> 32) & 0xFFFF) as u16, 32),
        enc_movk(x9, ((target >> 48) & 0xFFFF) as u16, 48),
        enc_br(x9),
    ];

    let mut bytes = Vec::with_capacity(words.len() * 4);
    for w in words {
        bytes.extend_from_slice(&w.to_le_bytes());
    }
    bytes
}

pub fn emit_default_vadd_stub() -> Vec<u8> {
    emit_vadd_stub(rust_vadd_kernel as *const () as usize)
}
