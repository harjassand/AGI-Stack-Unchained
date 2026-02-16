#![forbid(unsafe_code)]
use std::io::{self, Read};
use pyo3::prelude::*;
use pyo3::types::PyBytes;
use cdel_workmeter_rs_v1::compute;

fn main() {
    let mut input = String::new();
    io::stdin().read_to_string(&mut input).unwrap();
    Python::with_gil(|py| {
        let bytes = PyBytes::new(py, input.as_bytes());
        let out = compute(py, bytes).unwrap();
        let out_bytes = out.as_ref(py).as_bytes();
        println!("{}", String::from_utf8_lossy(out_bytes));
    });
}
