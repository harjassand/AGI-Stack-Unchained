#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Descriptor {
    pub fuel_bucket: u8,
    pub code_bucket: u8,
    pub branch_bucket: u8,
    pub write_bucket: u8,
    pub entropy_bucket: u8,
    pub regime_profile: u8,
}

#[derive(Clone, Copy, Debug)]
pub struct DescriptorInputs {
    pub fuel_used: u32,
    pub fuel_max: u32,
    pub code_size_words: u32,
    pub branch_count: u32,
    pub store_count: u32,
    pub total_insns: u32,
    pub output_entropy: f32,
    pub regime_profile_bits: u8,
}

pub fn bin_id(d: &Descriptor) -> u16 {
    (u16::from(d.fuel_bucket & 0x03))
        | ((u16::from(d.code_bucket & 0x03)) << 2)
        | ((u16::from(d.branch_bucket & 0x03)) << 4)
        | ((u16::from(d.write_bucket & 0x03)) << 6)
        | ((u16::from(d.entropy_bucket & 0x03)) << 8)
        | ((u16::from(d.regime_profile & 0x0F)) << 10)
}

pub fn build_descriptor(inputs: DescriptorInputs) -> Descriptor {
    let total = inputs.total_insns.max(1);
    let fuel_ratio = if inputs.fuel_max == 0 {
        1.0
    } else {
        inputs.fuel_used as f32 / inputs.fuel_max as f32
    };
    let branch_ratio = inputs.branch_count as f32 / total as f32;
    let write_ratio = inputs.store_count as f32 / total as f32;

    Descriptor {
        fuel_bucket: bucket_fuel(fuel_ratio),
        code_bucket: bucket_code(inputs.code_size_words),
        branch_bucket: bucket_ratio(branch_ratio),
        write_bucket: bucket_ratio(write_ratio),
        entropy_bucket: bucket_entropy(inputs.output_entropy),
        regime_profile: inputs.regime_profile_bits & 0x0F,
    }
}

pub fn bucket_fuel(ratio: f32) -> u8 {
    if ratio <= 0.25 {
        0
    } else if ratio <= 0.50 {
        1
    } else if ratio <= 0.75 {
        2
    } else {
        3
    }
}

pub fn bucket_code(words: u32) -> u8 {
    if words <= 128 {
        0
    } else if words <= 256 {
        1
    } else if words <= 512 {
        2
    } else {
        3
    }
}

pub fn bucket_ratio(ratio: f32) -> u8 {
    if ratio <= 0.05 {
        0
    } else if ratio <= 0.15 {
        1
    } else if ratio <= 0.30 {
        2
    } else {
        3
    }
}

pub fn bucket_entropy(entropy: f32) -> u8 {
    if entropy <= 1.0 {
        0
    } else if entropy <= 2.0 {
        1
    } else if entropy <= 3.0 {
        2
    } else {
        3
    }
}

pub fn output_entropy_sketch(output: &[f32]) -> f32 {
    if output.is_empty() {
        return 0.0;
    }

    let sample_count = output.len().min(64);
    let mut counts = [0_u32; 16];

    for i in 0..sample_count {
        let idx = sample_index_uniform(output.len(), sample_count, i);
        let x = output[idx].clamp(-2.0, 2.0);
        let raw = ((x + 2.0) * 4.0).floor() as i32;
        let bin = raw.clamp(0, 15) as usize;
        counts[bin] += 1;
    }

    let total = sample_count as f32;
    let mut entropy = 0.0_f32;
    for &count in &counts {
        if count == 0 {
            continue;
        }
        let p = count as f32 / total;
        entropy -= p * p.log2();
    }
    entropy
}

fn sample_index_uniform(len: usize, sample_count: usize, sample_idx: usize) -> usize {
    if sample_count <= 1 || len <= 1 {
        return 0;
    }
    (sample_idx * (len - 1)) / (sample_count - 1)
}
