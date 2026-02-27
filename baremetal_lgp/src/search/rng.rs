use core::f32::consts::TAU;
use core::ops::Range;

#[derive(Clone, Debug)]
pub struct Rng {
    state: u64,
    spare_normal: Option<f32>,
}

impl Rng {
    pub fn new(seed: u64) -> Self {
        // Xorshift* cannot use zero state.
        let state = if seed == 0 {
            0x9E37_79B9_7F4A_7C15
        } else {
            seed
        };
        Self {
            state,
            spare_normal: None,
        }
    }

    pub fn from_entropy() -> Self {
        let mut bytes = [0_u8; 8];
        if getrandom::getrandom(&mut bytes).is_ok() {
            return Self::new(u64::from_le_bytes(bytes));
        }
        let nanos = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map_or(0_u64, |d| d.as_nanos() as u64);
        Self::new(nanos ^ 0xD6E8_FDDA_AE9D_3A57)
    }

    pub fn next_u64(&mut self) -> u64 {
        // xorshift64*
        let mut x = self.state;
        x ^= x >> 12;
        x ^= x << 25;
        x ^= x >> 27;
        self.state = x;
        x.wrapping_mul(0x2545_F491_4F6C_DD1D)
    }

    pub fn next_u32(&mut self) -> u32 {
        (self.next_u64() >> 32) as u32
    }

    pub fn next_f32(&mut self) -> f32 {
        // [0, 1)
        const SCALE: f32 = 1.0 / ((1_u32 << 24) as f32);
        let upper = self.next_u32() >> 8;
        (upper as f32) * SCALE
    }

    pub fn gen_bool(&mut self, probability: f32) -> bool {
        if probability <= 0.0 {
            return false;
        }
        if probability >= 1.0 {
            return true;
        }
        self.next_f32() < probability
    }

    pub fn gen_range_usize(&mut self, range: Range<usize>) -> usize {
        let width = range.end.saturating_sub(range.start);
        if width == 0 {
            return range.start;
        }
        range.start + (self.next_u64() as usize % width)
    }

    pub fn gen_range_u32(&mut self, range: Range<u32>) -> u32 {
        let width = range.end.saturating_sub(range.start);
        if width == 0 {
            return range.start;
        }
        range.start + (self.next_u32() % width)
    }

    pub fn gen_range_i32_inclusive(&mut self, low: i32, high: i32) -> i32 {
        if low >= high {
            return low;
        }
        let width = (high as i64 - low as i64 + 1_i64) as u32;
        low + (self.next_u32() % width) as i32
    }

    pub fn choose_index(&mut self, len: usize) -> Option<usize> {
        if len == 0 {
            return None;
        }
        Some(self.gen_range_usize(0..len))
    }

    pub fn sample_weighted_index(&mut self, weights: &[f32]) -> Option<usize> {
        if weights.is_empty() {
            return None;
        }
        let total = weights
            .iter()
            .copied()
            .map(|w| if w.is_sign_negative() { 0.0 } else { w })
            .sum::<f32>();
        if total <= f32::EPSILON {
            return self.choose_index(weights.len());
        }
        let mut ticket = self.next_f32() * total;
        for (idx, weight) in weights.iter().copied().enumerate() {
            let w = if weight.is_sign_negative() {
                0.0
            } else {
                weight
            };
            if ticket <= w {
                return Some(idx);
            }
            ticket -= w;
        }
        Some(weights.len() - 1)
    }

    pub fn sample_normal(&mut self, sigma: f32) -> f32 {
        if sigma <= 0.0 {
            return 0.0;
        }
        if let Some(spare) = self.spare_normal.take() {
            return spare * sigma;
        }
        let u1 = (1.0 - self.next_f32()).max(f32::MIN_POSITIVE);
        let u2 = self.next_f32();
        let r = (-2.0 * u1.ln()).sqrt();
        let theta = TAU * u2;
        let z0 = r * theta.cos();
        let z1 = r * theta.sin();
        self.spare_normal = Some(z1);
        z0 * sigma
    }
}
