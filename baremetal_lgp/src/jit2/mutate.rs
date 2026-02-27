use crate::oracle::SplitMix64;

use super::constants::{A64_RET, RAW_MAX_WORDS, RAW_MIN_WORDS};

const A64_NOP: u32 = 0xD503201F;
const SAFE_POOL: [u32; 4] = [A64_RET, A64_NOP, 0xAA1F03E0, 0xD5033F9F]; // RET, NOP, MOV x0,xzr, DSB SY

#[derive(Clone, Copy, Debug)]
pub enum MutationOp {
    Bitflip,
    WordReplace,
    SwapRange,
    InsertRange,
    DeleteRange,
    CrossoverSplice,
    SuffixEnforce,
}

pub fn mutate_words(rng: &mut SplitMix64, parent: &[u32], donor: Option<&[u32]>) -> Vec<u32> {
    let mut out = if parent.is_empty() {
        vec![A64_RET]
    } else {
        parent.to_vec()
    };

    let op = match rng.next_usize(7) {
        0 => MutationOp::Bitflip,
        1 => MutationOp::WordReplace,
        2 => MutationOp::SwapRange,
        3 => MutationOp::InsertRange,
        4 => MutationOp::DeleteRange,
        5 => MutationOp::CrossoverSplice,
        _ => MutationOp::SuffixEnforce,
    };

    match op {
        MutationOp::Bitflip => bitflip(rng, &mut out),
        MutationOp::WordReplace => word_replace(rng, &mut out),
        MutationOp::SwapRange => swap_range(rng, &mut out),
        MutationOp::InsertRange => insert_range(rng, &mut out),
        MutationOp::DeleteRange => delete_range(rng, &mut out),
        MutationOp::CrossoverSplice => crossover_splice(rng, &mut out, donor),
        MutationOp::SuffixEnforce => {}
    }

    clamp_len(&mut out);
    sanitize_words(&mut out);
    suffix_enforce(rng, &mut out);
    clamp_len(&mut out);
    out
}

fn bitflip(rng: &mut SplitMix64, words: &mut [u32]) {
    if words.is_empty() {
        return;
    }
    let idx = rng.next_usize(words.len());
    let bit = rng.next_usize(32) as u32;
    words[idx] ^= 1_u32 << bit;
}

fn word_replace(rng: &mut SplitMix64, words: &mut [u32]) {
    if words.is_empty() {
        return;
    }
    let idx = rng.next_usize(words.len());
    let use_pool = rng.next_f32() < 0.6;
    words[idx] = if use_pool {
        SAFE_POOL[rng.next_usize(SAFE_POOL.len())]
    } else {
        rng.next_u64() as u32
    };
}

fn swap_range(rng: &mut SplitMix64, words: &mut [u32]) {
    if words.len() < 2 {
        return;
    }
    let max_span = words.len().min(8);
    let span = 1 + rng.next_usize(max_span);
    if words.len() < span * 2 {
        return;
    }

    let a = rng.next_usize(words.len() - span + 1);
    let mut b = rng.next_usize(words.len() - span + 1);
    if a == b {
        b = (b + span).min(words.len() - span);
    }

    for i in 0..span {
        words.swap(a + i, b + i);
    }
}

fn insert_range(rng: &mut SplitMix64, words: &mut Vec<u32>) {
    if words.len() >= RAW_MAX_WORDS {
        return;
    }
    let count = 1 + rng.next_usize(8);
    let pos = rng.next_usize(words.len() + 1);
    let mut insert = Vec::with_capacity(count);
    for _ in 0..count {
        insert.push(rng.next_u64() as u32);
    }
    words.splice(pos..pos, insert);
}

fn delete_range(rng: &mut SplitMix64, words: &mut Vec<u32>) {
    if words.len() <= RAW_MIN_WORDS {
        return;
    }
    let max_del = words.len().min(8);
    let count = 1 + rng.next_usize(max_del);
    let actual = count.min(words.len().saturating_sub(RAW_MIN_WORDS));
    if actual == 0 {
        return;
    }
    let start = rng.next_usize(words.len() - actual + 1);
    words.drain(start..start + actual);
}

fn crossover_splice(rng: &mut SplitMix64, words: &mut Vec<u32>, donor: Option<&[u32]>) {
    let donor = donor.unwrap_or(words);
    if donor.is_empty() {
        return;
    }

    let mut child = Vec::new();
    let left_keep = rng.next_usize(words.len().saturating_add(1));
    let right_drop = rng.next_usize(words.len().saturating_add(1));

    let donor_start = rng.next_usize(donor.len());
    let donor_span = 1 + rng.next_usize(donor.len().min(8));
    let donor_end = donor_start.saturating_add(donor_span).min(donor.len());

    child.extend_from_slice(&words[..left_keep.min(words.len())]);
    child.extend_from_slice(&donor[donor_start..donor_end]);

    let keep_from = right_drop.min(words.len());
    child.extend_from_slice(&words[keep_from..]);

    *words = child;
}

fn suffix_enforce(rng: &mut SplitMix64, words: &mut Vec<u32>) {
    if words.is_empty() {
        words.push(A64_RET);
        return;
    }

    let suffix = (1 + rng.next_usize(4)).min(words.len());
    let start = words.len() - suffix;
    for w in &mut words[start..] {
        *w = A64_RET;
    }
}

fn clamp_len(words: &mut Vec<u32>) {
    if words.len() > RAW_MAX_WORDS {
        words.truncate(RAW_MAX_WORDS);
    }
    if words.is_empty() {
        words.push(A64_RET);
    }
}

fn sanitize_words(words: &mut [u32]) {
    for word in words.iter_mut() {
        *word = sanitize_word(*word);
    }
}

#[inline(always)]
fn sanitize_word(word: u32) -> u32 {
    match word {
        A64_RET | A64_NOP | 0xAA1F03E0 | 0xD5033F9F => word,
        _ => A64_NOP,
    }
}
