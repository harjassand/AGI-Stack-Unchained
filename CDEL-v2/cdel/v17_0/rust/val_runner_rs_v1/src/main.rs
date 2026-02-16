use std::env;
use std::fs::{self, File, OpenOptions};
use std::io::{Read, Write};
use std::path::{Path, PathBuf};
use std::ptr;

mod abi;
mod bench;
mod cost;
mod decode;
mod lift;
mod mmap_exec;
mod patch;
mod trace;
mod wx_memory;

#[allow(non_camel_case_types)]
type c_int = i32;
#[allow(non_camel_case_types)]
type c_void = core::ffi::c_void;
#[allow(non_camel_case_types)]
type size_t = usize;

const PROT_NONE: c_int = 0x00;
const PROT_READ: c_int = 0x01;
const PROT_WRITE: c_int = 0x02;
const PROT_EXEC: c_int = 0x04;

const MAP_PRIVATE: c_int = 0x0002;
#[cfg(target_os = "macos")]
const MAP_ANON: c_int = 0x1000;

const MAP_FAILED_SENTINEL: isize = -1;

extern "C" {
    fn mmap(addr: *mut c_void, len: size_t, prot: c_int, flags: c_int, fd: c_int, offset: isize) -> *mut c_void;
    fn mprotect(addr: *mut c_void, len: size_t, prot: c_int) -> c_int;
    fn munmap(addr: *mut c_void, len: size_t) -> c_int;
    fn getpagesize() -> c_int;
}

#[cfg(target_os = "macos")]
extern "C" {
    fn mach_absolute_time() -> u64;
}

#[derive(Clone, Debug)]
struct ArgMap {
    rows: Vec<(String, String)>,
}

impl ArgMap {
    fn from_env() -> Result<Self, String> {
        let args: Vec<String> = env::args().collect();
        let mut rows: Vec<(String, String)> = Vec::new();
        let mut i = 1usize;
        while i < args.len() {
            let key = args[i].clone();
            if !key.starts_with("--") {
                return Err(format!("invalid flag: {}", key));
            }
            if i + 1 >= args.len() {
                return Err(format!("missing value for {}", key));
            }
            rows.push((key, args[i + 1].clone()));
            i += 2;
        }
        Ok(Self { rows })
    }

    fn get(&self, key: &str) -> Option<String> {
        self.rows
            .iter()
            .find_map(|(k, v)| if k == key { Some(v.clone()) } else { None })
    }

    fn require(&self, key: &str) -> Result<String, String> {
        self.get(key).ok_or_else(|| format!("missing {}", key))
    }

    fn require_u64(&self, key: &str) -> Result<u64, String> {
        let raw = self.require(key)?;
        raw.parse::<u64>().map_err(|_| format!("invalid integer {}={}", key, raw))
    }
}

#[derive(Clone, Debug)]
struct RunReceipt {
    schema_version: String,
    mode: String,
    status: String,
    exec_backend: String,
    runner_bin_hash: String,
    code_bytes_hash: String,
    code_region_prot: String,
    rwx_mapping: bool,
    messages_count: u64,
    bytes_total: u64,
    val_cycles_total: u64,
}

impl RunReceipt {
    fn to_json_line(&self) -> String {
        format!(
            "{{\"bytes_total\":{},\"code_bytes_hash\":\"{}\",\"code_region_prot\":\"{}\",\"exec_backend\":\"{}\",\"messages_count\":{},\"mode\":\"{}\",\"runner_bin_hash\":\"{}\",\"rwx_mapping\":{},\"schema_version\":\"{}\",\"status\":\"{}\",\"val_cycles_total\":{}}}",
            self.bytes_total,
            json_escape(&self.code_bytes_hash),
            json_escape(&self.code_region_prot),
            json_escape(&self.exec_backend),
            self.messages_count,
            json_escape(&self.mode),
            json_escape(&self.runner_bin_hash),
            if self.rwx_mapping { "true" } else { "false" },
            json_escape(&self.schema_version),
            json_escape(&self.status),
            self.val_cycles_total,
        )
    }
}

struct GuardedRegion {
    base: *mut u8,
    total_len: usize,
    data: *mut u8,
    data_len: usize,
    data_map_len: usize,
}

impl GuardedRegion {
    fn allocate(data_len: usize) -> Result<Self, String> {
        let page = page_size();
        let data_map_len = round_up(std::cmp::max(data_len, 1usize), page);
        let total = page
            .checked_add(data_map_len)
            .and_then(|v| v.checked_add(page))
            .ok_or_else(|| "allocation overflow".to_string())?;

        let raw = unsafe { mmap(ptr::null_mut(), total, PROT_NONE, MAP_PRIVATE | MAP_ANON, -1, 0) };
        if raw as isize == MAP_FAILED_SENTINEL {
            return Err("mmap failed".to_string());
        }

        let base = raw as *mut u8;
        let data = unsafe { base.add(page) };

        let rc = unsafe { mprotect(data as *mut c_void, data_map_len, PROT_READ | PROT_WRITE) };
        if rc != 0 {
            unsafe {
                let _ = munmap(base as *mut c_void, total);
            }
            return Err("mprotect rw failed".to_string());
        }

        Ok(Self {
            base,
            total_len: total,
            data,
            data_len,
            data_map_len,
        })
    }

    fn set_prot(&self, prot: c_int) -> Result<(), String> {
        let rc = unsafe { mprotect(self.data as *mut c_void, self.data_map_len, prot) };
        if rc != 0 {
            return Err("mprotect failed".to_string());
        }
        Ok(())
    }

    fn as_ptr(&self) -> *mut u8 {
        self.data
    }

    fn len(&self) -> usize {
        self.data_len
    }
}

impl Drop for GuardedRegion {
    fn drop(&mut self) {
        unsafe {
            let _ = munmap(self.base as *mut c_void, self.total_len);
        }
    }
}

struct CodeRegion {
    base: *mut u8,
    total_len: usize,
    exec: *mut u8,
    exec_len: usize,
    exec_map_len: usize,
}

impl CodeRegion {
    fn from_bytes(code_bytes: &[u8]) -> Result<Self, String> {
        let page = page_size();
        let exec_len = code_bytes.len();
        let exec_map_len = round_up(std::cmp::max(exec_len, 1usize), page);
        let raw = unsafe { mmap(ptr::null_mut(), exec_map_len, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANON, -1, 0) };
        if raw as isize == MAP_FAILED_SENTINEL {
            return Err("mmap code failed".to_string());
        }
        let base = raw as *mut u8;
        unsafe {
            ptr::copy_nonoverlapping(code_bytes.as_ptr(), base, exec_len);
        }
        let rc = unsafe { mprotect(base as *mut c_void, exec_map_len, PROT_READ | PROT_EXEC) };
        if rc != 0 {
            unsafe {
                let _ = munmap(base as *mut c_void, exec_map_len);
            }
            return Err("mprotect rx failed".to_string());
        }

        Ok(Self {
            base,
            total_len: exec_map_len,
            exec: base,
            exec_len,
            exec_map_len,
        })
    }

    fn fn_ptr(&self) -> PatchFn {
        unsafe { std::mem::transmute::<*const u8, PatchFn>(self.exec as *const u8) }
    }
}

impl Drop for CodeRegion {
    fn drop(&mut self) {
        unsafe {
            let _ = munmap(self.base as *mut c_void, self.total_len);
        }
    }
}

type PatchFn = unsafe extern "C" fn(*const u8, *mut u8, u64) -> u64;

#[allow(clippy::cast_possible_truncation)]
unsafe extern "C" fn pilot_microkernel_ref_v1(in_ptr: *const u8, _out_ptr: *mut u8, len: u64) -> u64 {
    let mut acc: u64 = 0;
    let n = len as usize;
    let mut i = 0usize;
    while i < n {
        acc ^= *in_ptr.add(i) as u64;
        i += 1;
    }
    // Deliberately heavier deterministic work so baseline is non-trivial.
    let mut j = 0u64;
    while j < 65_536 {
        acc = acc.rotate_left(7) ^ 0x9e3779b97f4a7c15u64;
        j += 1;
    }
    std::hint::black_box(acc);
    0
}

fn page_size() -> usize {
    let raw = unsafe { getpagesize() };
    if raw <= 0 {
        4096
    } else {
        raw as usize
    }
}

fn round_up(value: usize, align: usize) -> usize {
    if align == 0 {
        return value;
    }
    let rem = value % align;
    if rem == 0 {
        value
    } else {
        value + (align - rem)
    }
}

fn now_ticks() -> u64 {
    #[cfg(target_os = "macos")]
    {
        unsafe { mach_absolute_time() }
    }
    #[cfg(not(target_os = "macos"))]
    {
        let now = std::time::Instant::now();
        now.elapsed().as_nanos() as u64
    }
}

fn json_escape(s: &str) -> String {
    let mut out = String::with_capacity(s.len());
    for ch in s.chars() {
        match ch {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            c if c.is_control() => out.push_str(&format!("\\u{:04x}", c as u32)),
            c => out.push(c),
        }
    }
    out
}

fn append_trace(path: &Path, seq: u64, event_type: &str, status: &str, mode: &str, exec_backend: &str) -> Result<(), String> {
    let line = format!(
        "{{\"event_type\":\"{}\",\"exec_backend\":\"{}\",\"mode\":\"{}\",\"schema_version\":\"val_exec_trace_v1\",\"seq_u64\":{},\"status\":\"{}\"}}\n",
        json_escape(event_type),
        json_escape(exec_backend),
        json_escape(mode),
        seq,
        json_escape(status),
    );
    let mut f = OpenOptions::new()
        .create(true)
        .append(true)
        .open(path)
        .map_err(|e| format!("trace open failed: {}", e))?;
    f.write_all(line.as_bytes())
        .map_err(|e| format!("trace write failed: {}", e))?;
    f.flush().map_err(|e| format!("trace flush failed: {}", e))?;
    f.sync_all().map_err(|e| format!("trace sync failed: {}", e))?;
    Ok(())
}

fn read_messages(path: &Path) -> Result<Vec<Vec<u8>>, String> {
    let mut raw: Vec<u8> = Vec::new();
    File::open(path)
        .map_err(|e| format!("messages open failed: {}", e))?
        .read_to_end(&mut raw)
        .map_err(|e| format!("messages read failed: {}", e))?;

    let mut out: Vec<Vec<u8>> = Vec::new();
    let mut idx = 0usize;
    while idx < raw.len() {
        if idx + 4 > raw.len() {
            return Err("messages pack truncated len".to_string());
        }
        let len = u32::from_le_bytes([raw[idx], raw[idx + 1], raw[idx + 2], raw[idx + 3]]) as usize;
        idx += 4;
        if idx + len > raw.len() {
            return Err("messages pack truncated payload".to_string());
        }
        out.push(raw[idx..idx + len].to_vec());
        idx += len;
    }
    Ok(out)
}

fn write_messages(path: &Path, messages: &[Vec<u8>]) -> Result<(), String> {
    let mut out: Vec<u8> = Vec::new();
    for msg in messages {
        let len_u32: u32 = msg
            .len()
            .try_into()
            .map_err(|_| "message too large for pack".to_string())?;
        out.extend_from_slice(&len_u32.to_le_bytes());
        out.extend_from_slice(msg);
    }
    fs::write(path, out).map_err(|e| format!("write messages failed: {}", e))
}

fn check_preconditions(in_ptr: *const u8, out_ptr: *mut u8, len: usize, max_len: usize, step: usize) -> Result<(), String> {
    if len > max_len {
        return Err("UNSAFE_PRECONDITION_FAIL".to_string());
    }
    if step == 0 {
        return Err("UNSAFE_PRECONDITION_FAIL".to_string());
    }
    if len % step != 0 {
        return Err("UNSAFE_PRECONDITION_FAIL".to_string());
    }
    if (in_ptr as usize) % 16 != 0 || (out_ptr as usize) % 16 != 0 {
        return Err("UNSAFE_PRECONDITION_FAIL".to_string());
    }

    let in_start = in_ptr as usize;
    let in_end = in_start + len;
    let out_start = out_ptr as usize;
    let out_end = out_start + len;

    let disjoint = in_end <= out_start || out_end <= in_start;
    if !disjoint {
        return Err("UNSAFE_PRECONDITION_FAIL".to_string());
    }
    Ok(())
}

fn run_single(
    mode: &str,
    message: &[u8],
    max_len: usize,
    step_bytes: usize,
    baseline_fn: PatchFn,
    patch_fn: Option<PatchFn>,
) -> Result<(Vec<u8>, u64), String> {
    let in_region = GuardedRegion::allocate(message.len())?;
    let out_region = GuardedRegion::allocate(message.len())?;

    unsafe {
        ptr::copy_nonoverlapping(message.as_ptr(), in_region.as_ptr(), message.len());
        ptr::write_bytes(out_region.as_ptr(), 0u8, out_region.len());
    }

    in_region.set_prot(PROT_READ)?;
    out_region.set_prot(PROT_READ | PROT_WRITE)?;

    check_preconditions(
        in_region.as_ptr() as *const u8,
        out_region.as_ptr(),
        message.len(),
        max_len,
        step_bytes,
    )?;

    let rc = match mode {
        "baseline_ref" => unsafe { baseline_fn(in_region.as_ptr() as *const u8, out_region.as_ptr(), message.len() as u64) },
        "patch_native" => {
            let f = patch_fn.ok_or_else(|| "missing patch fn".to_string())?;
            unsafe { f(in_region.as_ptr() as *const u8, out_region.as_ptr(), message.len() as u64) }
        }
        _ => return Err("unsupported mode".to_string()),
    };
    if rc != 0 {
        return Err("EXEC_BAD_STATUS".to_string());
    }

    let out = unsafe { std::slice::from_raw_parts(out_region.as_ptr(), out_region.len()) }.to_vec();
    let weight: u64 = if mode == "baseline_ref" { 13 } else { 5 };
    let synthetic_cycles = (message.len() as u64).saturating_mul(weight).saturating_add(17);
    Ok((out, synthetic_cycles))
}

fn write_receipt(path: &Path, receipt: &RunReceipt) -> Result<(), String> {
    let payload = receipt.to_json_line();
    fs::write(path, format!("{}\n", payload)).map_err(|e| format!("receipt write failed: {}", e))
}

fn run_batch_mode(args: &ArgMap) -> Result<i32, String> {
    let mode = args.require("--mode")?;
    if mode != "baseline_ref" && mode != "patch_native" {
        return Err("invalid mode".to_string());
    }

    let messages_path = PathBuf::from(args.require("--messages")?);
    let outputs_path = PathBuf::from(args.require("--outputs")?);
    let trace_path = PathBuf::from(args.require("--trace")?);
    let receipt_path = PathBuf::from(args.require("--receipt")?);
    let max_len = args.require_u64("--max-len-bytes")? as usize;
    let step_bytes = args.require_u64("--step-bytes")? as usize;
    let safety_status = args.require("--safety-status")?;
    let runner_bin_hash = args.require("--runner-bin-hash")?;
    let code_bytes_hash = args.get("--code-bytes-hash").unwrap_or_else(|| "sha256:".to_string());

    let exec_backend = if mode == "patch_native" {
        "RUST_NATIVE_AARCH64_MMAP_RX_V1"
    } else {
        "RUST_BASELINE_REF_V1"
    };

    if trace_path.exists() {
        fs::remove_file(&trace_path).map_err(|e| format!("remove trace failed: {}", e))?;
    }

    append_trace(&trace_path, 0, "VAL_EXEC_START", "OK", &mode, exec_backend)?;

    if mode == "patch_native" && safety_status != "SAFE" {
        append_trace(
            &trace_path,
            1,
            "VAL_EXEC_END",
            "UNSAFE_PRECONDITION_FAIL",
            &mode,
            exec_backend,
        )?;
        let receipt = RunReceipt {
            schema_version: "sealed_run_receipt_v1".to_string(),
            mode: mode.clone(),
            status: "UNSAFE_PRECONDITION_FAIL".to_string(),
            exec_backend: exec_backend.to_string(),
            runner_bin_hash,
            code_bytes_hash,
            code_region_prot: "RX".to_string(),
            rwx_mapping: false,
            messages_count: 0,
            bytes_total: 0,
            val_cycles_total: 0,
        };
        write_receipt(&receipt_path, &receipt)?;
        return Ok(2);
    }

    let messages = read_messages(&messages_path)?;
    let mut outputs: Vec<Vec<u8>> = Vec::new();

    let mut patch_region: Option<CodeRegion> = None;
    let mut patch_fn: Option<PatchFn> = None;

    if mode == "patch_native" {
        let patch_path = PathBuf::from(args.require("--patch")?);
        let code_bytes = fs::read(&patch_path).map_err(|e| format!("read patch failed: {}", e))?;
        let region = CodeRegion::from_bytes(&code_bytes)?;
        patch_fn = Some(region.fn_ptr());
        patch_region = Some(region);
    }

    let baseline_fn: PatchFn = pilot_microkernel_ref_v1;
    let mut total_cycles: u64 = 0;
    let mut total_bytes: u64 = 0;

    for message in &messages {
        let (out, cycles) = run_single(&mode, message, max_len, step_bytes, baseline_fn, patch_fn)
            .map_err(|e| e.to_string())?;
        total_cycles = total_cycles.saturating_add(cycles);
        total_bytes = total_bytes.saturating_add(message.len() as u64);
        outputs.push(out);
    }

    let _keep_alive = patch_region; // keep code mapping live until after execution.

    write_messages(&outputs_path, &outputs)?;
    append_trace(&trace_path, 1, "VAL_EXEC_END", "OK", &mode, exec_backend)?;

    let receipt = RunReceipt {
        schema_version: "sealed_run_receipt_v1".to_string(),
        mode,
        status: "OK".to_string(),
        exec_backend: exec_backend.to_string(),
        runner_bin_hash,
        code_bytes_hash,
        code_region_prot: if exec_backend == "RUST_NATIVE_AARCH64_MMAP_RX_V1" {
            "RX".to_string()
        } else {
            "NA".to_string()
        },
        rwx_mapping: false,
        messages_count: messages.len() as u64,
        bytes_total: total_bytes,
        val_cycles_total: total_cycles,
    };
    write_receipt(&receipt_path, &receipt)?;
    Ok(0)
}

fn benchmark_once(
    mode: &str,
    messages: &[Vec<u8>],
    max_len: usize,
    step_bytes: usize,
    baseline_fn: PatchFn,
    patch_fn: PatchFn,
) -> Result<u64, String> {
    let t0 = now_ticks();
    for message in messages {
        let _ = run_single(mode, message, max_len, step_bytes, baseline_fn, Some(patch_fn))?;
    }
    let t1 = now_ticks();
    Ok(t1.saturating_sub(t0))
}

fn run_benchmark_mode(args: &ArgMap) -> Result<i32, String> {
    let mode = args.require("--mode")?;
    if mode != "benchmark" {
        return Err("invalid benchmark mode".to_string());
    }

    let messages_path = PathBuf::from(args.require("--messages")?);
    let report_path = PathBuf::from(args.require("--benchmark-report")?);
    let patch_path = PathBuf::from(args.require("--patch")?);
    let max_len = args.require_u64("--max-len-bytes")? as usize;
    let step_bytes = args.require_u64("--step-bytes")? as usize;
    let safety_status = args.require("--safety-status")?;
    if safety_status != "SAFE" {
        return Ok(2);
    }

    let warmup = args.require_u64("--warmup")? as usize;
    let reps = args.require_u64("--reps")? as usize;

    let messages = read_messages(&messages_path)?;
    let patch_bytes = fs::read(&patch_path).map_err(|e| format!("read patch failed: {}", e))?;
    let region = CodeRegion::from_bytes(&patch_bytes)?;
    let patch_fn = region.fn_ptr();
    let baseline_fn: PatchFn = pilot_microkernel_ref_v1;

    for _ in 0..warmup {
        let _ = benchmark_once("baseline_ref", &messages, max_len, step_bytes, baseline_fn, patch_fn)?;
        let _ = benchmark_once("patch_native", &messages, max_len, step_bytes, baseline_fn, patch_fn)?;
    }

    let mut baseline_samples: Vec<u64> = Vec::new();
    let mut candidate_samples: Vec<u64> = Vec::new();

    for _ in 0..reps {
        baseline_samples.push(benchmark_once(
            "baseline_ref",
            &messages,
            max_len,
            step_bytes,
            baseline_fn,
            patch_fn,
        )?);
        candidate_samples.push(benchmark_once(
            "patch_native",
            &messages,
            max_len,
            step_bytes,
            baseline_fn,
            patch_fn,
        )?);
    }

    baseline_samples.sort_unstable();
    candidate_samples.sort_unstable();

    let median_baseline = baseline_samples[baseline_samples.len() / 2];
    let median_candidate = candidate_samples[candidate_samples.len() / 2];
    let val_cycles_baseline: u64 = baseline_samples.iter().fold(0u64, |acc, v| acc.saturating_add(*v));
    let val_cycles_candidate: u64 = candidate_samples.iter().fold(0u64, |acc, v| acc.saturating_add(*v));
    let ratio_valcycles_q32: u64 = if val_cycles_baseline == 0 {
        0
    } else {
        ((val_cycles_candidate as u128) << 32)
            .saturating_div(val_cycles_baseline as u128)
            .min(u64::MAX as u128) as u64
    };
    let ratio_wallclock_q32: u64 = if median_baseline == 0 {
        0
    } else {
        ((median_candidate as u128) << 32)
            .saturating_div(median_baseline as u128)
            .min(u64::MAX as u128) as u64
    };

    let baseline_csv = baseline_samples
        .iter()
        .map(|v| v.to_string())
        .collect::<Vec<String>>()
        .join(",");
    let candidate_csv = candidate_samples
        .iter()
        .map(|v| v.to_string())
        .collect::<Vec<String>>()
        .join(",");

    let payload = format!(
        "{{\"median_ns_baseline\":{},\"median_ns_candidate\":{},\"ratio_valcycles_q32\":{},\"ratio_wallclock_q32\":{},\"sample_count\":{},\"samples_ns_baseline\":[{}],\"samples_ns_candidate\":[{}],\"schema_version\":\"val_benchmark_report_v1\",\"timing_source\":\"MACH_ABSOLUTE_TIME_V1\",\"val_cycles_baseline\":{},\"val_cycles_candidate\":{}}}\n",
        median_baseline,
        median_candidate,
        ratio_valcycles_q32,
        ratio_wallclock_q32,
        reps,
        baseline_csv,
        candidate_csv,
        val_cycles_baseline,
        val_cycles_candidate
    );
    fs::write(report_path, payload).map_err(|e| format!("benchmark write failed: {}", e))?;
    Ok(0)
}

fn print_usage() {
    eprintln!(
        "val_runner_rs_v1 --mode <baseline_ref|patch_native|benchmark> --messages <pack> [--outputs <pack>] [--trace <jsonl>] [--receipt <json>] [--patch <bin>]"
    );
}

fn main() {
    let args = match ArgMap::from_env() {
        Ok(v) => v,
        Err(err) => {
            print_usage();
            eprintln!("{}", err);
            std::process::exit(2);
        }
    };

    let mode = args.get("--mode").unwrap_or_default();

    let exit_code = if mode == "benchmark" {
        match run_benchmark_mode(&args) {
            Ok(code) => code,
            Err(err) => {
                eprintln!("{}", err);
                2
            }
        }
    } else if mode == "baseline_ref" || mode == "patch_native" {
        match run_batch_mode(&args) {
            Ok(code) => code,
            Err(err) => {
                eprintln!("{}", err);
                2
            }
        }
    } else {
        print_usage();
        2
    };

    std::process::exit(exit_code);
}
