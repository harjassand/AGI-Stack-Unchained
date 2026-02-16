#![forbid(unsafe_code)]
use pyo3::prelude::*;
use pyo3::types::PyBytes;
use serde::Deserialize;

#[derive(Deserialize)]
struct Job {
    schema: String,
    spec_version: String,
    dim: i64,
    norm_pow: i64,
    pair_terms: i64,
    hooke_terms: i64,
}

#[pyfunction]
pub fn compute(py: Python, job_json_bytes: &PyBytes) -> PyResult<Py<PyBytes>> {
    let bytes = job_json_bytes.as_bytes();
    let job: Job = serde_json::from_slice(bytes).map_err(|e| pyo3::exceptions::PyValueError::new_err(e.to_string()))?;

    let mut add_calls: i64 = 0;
    let mut dim: i64 = 0;
    let mut div_calls: i64 = 0;
    let mut hooke_terms: i64 = 0;
    let mut mul_calls: i64 = 0;
    let mut norm_pow: i64 = 0;
    let mut pair_terms: i64 = 0;
    let mut pair_terms_evaluated: i64 = 0;
    let mut sqrt_calls: i64 = 0;
    let mut work_cost_total: i64 = 0;

    dim = job.dim;
    norm_pow = job.norm_pow;
    pair_terms = job.pair_terms;
    hooke_terms = job.hooke_terms;
    sqrt_calls = 0i64;
    div_calls = 0i64;
    mul_calls = 0i64;
    add_calls = 0i64;
    pair_terms_evaluated = 0i64;
    add_calls += ((pair_terms * dim) * 1i64);
    mul_calls += ((pair_terms * dim) * 1i64);
    if (0i64 < dim) {
        add_calls += ((pair_terms * (dim - 1i64)) * 1i64);
    } else {
    }
    sqrt_calls += (pair_terms * 1i64);
    if (1i64 < norm_pow) {
        mul_calls += ((pair_terms * (norm_pow - 1i64)) * 1i64);
    } else {
    }
    div_calls += ((pair_terms * dim) * 1i64);
    mul_calls += ((pair_terms * dim) * 1i64);
    add_calls += ((pair_terms * dim) * 1i64);
    pair_terms_evaluated += (pair_terms * 1i64);
    add_calls += ((hooke_terms * dim) * 1i64);
    mul_calls += ((hooke_terms * dim) * 1i64);
    if (0i64 < dim) {
        add_calls += ((hooke_terms * (dim - 1i64)) * 1i64);
    } else {
    }
    sqrt_calls += (hooke_terms * 1i64);
    if (1i64 < 2i64) {
        mul_calls += ((hooke_terms * (2i64 - 1i64)) * 1i64);
    } else {
    }
    div_calls += ((hooke_terms * dim) * 1i64);
    mul_calls += ((hooke_terms * dim) * 1i64);
    add_calls += ((hooke_terms * dim) * 1i64);
    pair_terms_evaluated += (hooke_terms * 1i64);
    work_cost_total = (((((50i64 * sqrt_calls) + (20i64 * div_calls)) + (3i64 * mul_calls)) + (1i64 * add_calls)) + (5i64 * pair_terms_evaluated));

    let out_json = format!("{{\"div_calls\":{},\"pair_terms_evaluated\":{},\"schema\":\"sas_science_workmeter_out_v1\",\"spec_version\":\"v14_0\",\"sqrt_calls\":{},\"work_cost_total\":{}}}", div_calls, pair_terms_evaluated, sqrt_calls, work_cost_total);
    let out_bytes = out_json.as_bytes();
    Ok(PyBytes::new(py, out_bytes).into())
}

#[pymodule]
fn cdel_workmeter_rs_v1(_py: Python, m: &PyModule) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(compute, m)?)?;
    Ok(())
}
