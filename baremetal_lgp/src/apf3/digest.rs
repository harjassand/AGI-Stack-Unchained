use blake3::Hasher;
use serde::{Deserialize, Serialize};

pub const TAG_APF3_GRAPH_V1: &[u8] = b"APF3_GRAPH_V1";
pub const TAG_APF3_DIFF_V1: &[u8] = b"APF3_DIFF_V1";
pub const TAG_APF3_PACK_V1: &[u8] = b"APF3_PACK_V1";
pub const TAG_APF3_RUN_V1: &[u8] = b"APF3_RUN_V1";

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct Digest32(pub [u8; 32]);

impl Digest32 {
    pub fn zero() -> Self {
        Self([0_u8; 32])
    }

    pub fn hex(&self) -> String {
        let mut out = String::with_capacity(64);
        for byte in self.0 {
            out.push(nibble_to_hex((byte >> 4) & 0x0f));
            out.push(nibble_to_hex(byte & 0x0f));
        }
        out
    }
}

impl Default for Digest32 {
    fn default() -> Self {
        Self::zero()
    }
}

fn nibble_to_hex(n: u8) -> char {
    match n {
        0..=9 => (b'0' + n) as char,
        10..=15 => (b'a' + (n - 10)) as char,
        _ => '0',
    }
}

pub struct DigestBuilder(Hasher);

impl DigestBuilder {
    pub fn new(tag: &'static [u8]) -> Self {
        let mut h = Hasher::new();
        h.update(tag);
        Self(h)
    }

    pub fn bool(&mut self, x: bool) {
        self.0.update(&[if x { 1 } else { 0 }]);
    }

    pub fn u64(&mut self, x: u64) {
        self.0.update(&x.to_le_bytes());
    }

    pub fn u32(&mut self, x: u32) {
        self.0.update(&x.to_le_bytes());
    }

    pub fn i64(&mut self, x: i64) {
        self.0.update(&x.to_le_bytes());
    }

    pub fn f32(&mut self, x: f32) {
        self.u32(x.to_bits());
    }

    pub fn f64(&mut self, x: f64) {
        self.u64(x.to_bits());
    }

    pub fn bytes(&mut self, b: &[u8]) {
        self.u64(b.len() as u64);
        self.0.update(b);
    }

    pub fn digest32(&mut self, d: Digest32) {
        self.bytes(&d.0);
    }

    pub fn finish(self) -> Digest32 {
        Digest32(*self.0.finalize().as_bytes())
    }
}
