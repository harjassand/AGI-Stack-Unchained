pub mod accelerate;
pub mod thresholds;

use crate::abi::{SCRATCH_MASK_I32, SCRATCH_WORDS};
use thresholds::{ACCEL_COMPLEX_DOT_MIN, ACCEL_DOT_MIN, ACCEL_REAL_MIN};

#[inline]
fn ring_index(base: i32, offset: usize) -> usize {
    (base.wrapping_add(i32::try_from(offset).unwrap_or(i32::MAX)) & SCRATCH_MASK_I32) as usize
}

#[inline]
fn until_wrap(idx: usize) -> usize {
    SCRATCH_WORDS - idx
}

#[inline]
fn ranges_overlap(a_start: usize, a_len: usize, b_start: usize, b_len: usize) -> bool {
    let a_end = a_start.saturating_add(a_len);
    let b_end = b_start.saturating_add(b_len);
    a_start < b_end && b_start < a_end
}

pub fn vadd_ring(scratch: &mut [f32; SCRATCH_WORDS], dst: i32, x: i32, y: i32, len: usize) {
    run_real_ring_op(scratch, dst, x, y, len, RealOp::Add);
}

pub fn vmul_ring(scratch: &mut [f32; SCRATCH_WORDS], dst: i32, x: i32, y: i32, len: usize) {
    run_real_ring_op(scratch, dst, x, y, len, RealOp::Mul);
}

pub fn vfma_ring(scratch: &mut [f32; SCRATCH_WORDS], dst: i32, x: i32, y: i32, len: usize) {
    run_real_ring_op(scratch, dst, x, y, len, RealOp::Fma);
}

#[derive(Copy, Clone)]
enum RealOp {
    Add,
    Mul,
    Fma,
}

fn run_real_ring_op(
    scratch: &mut [f32; SCRATCH_WORDS],
    dst: i32,
    x: i32,
    y: i32,
    len: usize,
    op: RealOp,
) {
    let mut done = 0usize;
    while done < len {
        let di = ring_index(dst, done);
        let xi = ring_index(x, done);
        let yi = ring_index(y, done);

        let rem = len - done;
        let chunk = rem
            .min(until_wrap(di))
            .min(until_wrap(xi))
            .min(until_wrap(yi));

        let disjoint = !ranges_overlap(di, chunk, xi, chunk)
            && !ranges_overlap(di, chunk, yi, chunk)
            && !ranges_overlap(xi, chunk, yi, chunk);

        if chunk >= ACCEL_REAL_MIN && disjoint {
            // SAFETY: chunk is contiguous for all slices and ranges are disjoint.
            unsafe {
                let dst_ptr = scratch.as_mut_ptr().add(di);
                let x_ptr = scratch.as_ptr().add(xi);
                let y_ptr = scratch.as_ptr().add(yi);
                match op {
                    RealOp::Add => accelerate::vadd(dst_ptr, x_ptr, y_ptr, chunk),
                    RealOp::Mul => accelerate::vmul(dst_ptr, x_ptr, y_ptr, chunk),
                    RealOp::Fma => accelerate::vfma(dst_ptr, x_ptr, y_ptr, chunk),
                }
            }
        } else {
            for j in 0..chunk {
                let d = di + j;
                let xv = scratch[xi + j];
                let yv = scratch[yi + j];
                scratch[d] = match op {
                    RealOp::Add => xv + yv,
                    RealOp::Mul => xv * yv,
                    RealOp::Fma => scratch[d] + (xv * yv),
                };
            }
        }

        done += chunk;
    }
}

pub fn vdot_ring(scratch: &[f32; SCRATCH_WORDS], x: i32, y: i32, len: usize) -> f32 {
    let x0 = ring_index(x, 0);
    let y0 = ring_index(y, 0);

    if len >= ACCEL_DOT_MIN && x0 + len <= SCRATCH_WORDS && y0 + len <= SCRATCH_WORDS {
        // SAFETY: x and y are contiguous and in-bounds.
        unsafe {
            return accelerate::dot(scratch.as_ptr().add(x0), scratch.as_ptr().add(y0), len);
        }
    }

    let mut acc = 0.0f32;
    for i in 0..len {
        let xi = ring_index(x, i);
        let yi = ring_index(y, i);
        acc += scratch[xi] * scratch[yi];
    }
    acc
}

pub fn vcadd_ring(scratch: &mut [f32; SCRATCH_WORDS], dst: i32, x: i32, y: i32, len_c: usize) {
    for c in 0..len_c {
        let w = c * 2;
        let dr = ring_index(dst, w);
        let di = ring_index(dst, w + 1);
        let xr = scratch[ring_index(x, w)];
        let xi = scratch[ring_index(x, w + 1)];
        let yr = scratch[ring_index(y, w)];
        let yi = scratch[ring_index(y, w + 1)];
        scratch[dr] = xr + yr;
        scratch[di] = xi + yi;
    }
}

pub fn vcmul_ring(scratch: &mut [f32; SCRATCH_WORDS], dst: i32, x: i32, y: i32, len_c: usize) {
    for c in 0..len_c {
        let w = c * 2;
        let dr = ring_index(dst, w);
        let di = ring_index(dst, w + 1);
        let xr = scratch[ring_index(x, w)];
        let xi = scratch[ring_index(x, w + 1)];
        let yr = scratch[ring_index(y, w)];
        let yi = scratch[ring_index(y, w + 1)];
        scratch[dr] = (xr * yr) - (xi * yi);
        scratch[di] = (xr * yi) + (xi * yr);
    }
}

pub fn vcdot_ring(scratch: &[f32; SCRATCH_WORDS], x: i32, y: i32, len_c: usize) -> (f32, f32) {
    let words = len_c.saturating_mul(2);
    let x0 = ring_index(x, 0);
    let y0 = ring_index(y, 0);

    if len_c >= ACCEL_COMPLEX_DOT_MIN && x0 + words <= SCRATCH_WORDS && y0 + words <= SCRATCH_WORDS
    {
        // SAFETY: x and y are contiguous and in-bounds for interleaved len_c values.
        unsafe {
            return accelerate::cdotc_interleaved(
                scratch.as_ptr().add(x0),
                scratch.as_ptr().add(y0),
                len_c,
            );
        }
    }

    let mut re = 0.0f32;
    let mut im = 0.0f32;
    for c in 0..len_c {
        let w = c * 2;
        let xr = scratch[ring_index(x, w)];
        let xi = scratch[ring_index(x, w + 1)];
        let yr = scratch[ring_index(y, w)];
        let yi = scratch[ring_index(y, w + 1)];
        re += (xr * yr) + (xi * yi);
        im += (xr * yi) - (xi * yr);
    }
    (re, im)
}
