use std::path::{Path, PathBuf};

use baremetal_lgp::apfsc::artifacts::{
    digest_bytes, digest_json, ensure_layout, write_bytes_atomic, write_json_atomic,
};
use baremetal_lgp::apfsc::bank::{build_bank, WindowBank};
use baremetal_lgp::apfsc::config::Phase1Config;
use baremetal_lgp::apfsc::errors::{io_err, ApfscError, Result};
use baremetal_lgp::apfsc::ingress::manifest::finalize_manifest;
use baremetal_lgp::apfsc::ingress::reality::ingest_reality;
use baremetal_lgp::apfsc::protocol::now_unix_s;
use baremetal_lgp::apfsc::types::{FamilyKind, PackKind, PackManifest, Provenance, RealityRole};
use clap::{Parser, ValueEnum};
use serde::Serialize;

#[derive(Debug, Clone, ValueEnum)]
enum InputFormat {
    Auto,
    Bin,
    Csv,
}

#[derive(Debug, Clone, ValueEnum)]
enum FamilyKindArg {
    AlgorithmicSymbolic,
    TextCodeLog,
    SensoryTemporal,
    PhysicalSimulation,
}

#[derive(Debug, Clone, ValueEnum)]
enum RealityRoleArg {
    Base,
    Transfer,
    Robust,
    ChallengeStub,
}

#[derive(Debug, Parser)]
struct Args {
    #[arg(long, default_value = ".apfsc")]
    root: PathBuf,
    #[arg(long)]
    input: PathBuf,
    #[arg(long)]
    family_id: String,
    #[arg(long, value_enum, default_value_t = InputFormat::Auto)]
    format: InputFormat,
    #[arg(long, value_enum, default_value_t = FamilyKindArg::TextCodeLog)]
    family_kind: FamilyKindArg,
    #[arg(long, value_enum, default_value_t = RealityRoleArg::Base)]
    role: RealityRoleArg,
    #[arg(long)]
    variant_id: Option<String>,
    #[arg(long)]
    base_family_id: Option<String>,
    #[arg(long, default_value = "external_file")]
    source_name: String,
    #[arg(long, default_value = "filesystem")]
    source_type: String,
    #[arg(long)]
    description: Option<String>,
    #[arg(long, default_value_t = 1_048_576)]
    chunk_bytes: usize,
    #[arg(long)]
    config: Option<PathBuf>,
    #[arg(long)]
    out: Option<PathBuf>,
    #[arg(long, default_value_t = false)]
    ingest: bool,
}

#[derive(Debug, Clone, Serialize)]
struct ExternalChunkRef {
    chunk_index: u64,
    chunk_hash: String,
    offset: u64,
    len: u64,
}

#[derive(Debug, Clone, Serialize)]
struct ExternalLawsIndex {
    index_hash: String,
    family_id: String,
    source_file: String,
    format: String,
    payload_hash: String,
    payload_bytes: u64,
    chunk_bytes: usize,
    chunks: Vec<ExternalChunkRef>,
    pack_hash: String,
    windowbank_manifest_hash: String,
    created_unix_s: u64,
}

fn main() -> std::result::Result<(), String> {
    let args = Args::parse();
    run(args).map_err(|e| e.to_string())
}

fn run(args: Args) -> Result<()> {
    if args.chunk_bytes == 0 {
        return Err(ApfscError::Validation(
            "chunk_bytes must be greater than zero".to_string(),
        ));
    }

    let cfg = if let Some(path) = &args.config {
        Phase1Config::from_path(path)?
    } else {
        Phase1Config::default()
    };
    ensure_layout(&args.root)?;

    let format = resolve_format(&args.input, &args.format);
    let payload = load_external_payload(&args.input, &format)?;
    if payload.len() <= cfg.bank.window_len as usize {
        return Err(ApfscError::Validation(format!(
            "external payload too small for window_len={} (bytes={})",
            cfg.bank.window_len,
            payload.len()
        )));
    }
    let payload_hash = digest_bytes(&payload);

    let role = to_role(&args.role);
    let family_kind = to_family_kind(&args.family_kind);
    let variant_id = args
        .variant_id
        .clone()
        .unwrap_or_else(|| default_variant_for_role(role));
    let description = args
        .description
        .clone()
        .unwrap_or_else(|| format!("external ingest from {}", args.input.display()));

    let raw_manifest = PackManifest {
        pack_kind: PackKind::Reality,
        pack_hash: String::new(),
        protocol_version: cfg.protocol.version.clone(),
        created_unix_s: now_unix_s(),
        family_id: Some(args.family_id.clone()),
        provenance: Provenance {
            source_name: args.source_name.clone(),
            source_type: args.source_type.clone(),
            attestation: None,
            notes: Some("generated_by=apfsc_ingest_external".to_string()),
        },
        payload_hashes: vec![payload_hash.clone()],
        meta: serde_json::json!({
            "family_id": args.family_id.clone(),
            "family_kind": family_kind_key(family_kind),
            "role": role_key(role),
            "variant_id": variant_id,
            "base_family_id": args.base_family_id.clone(),
            "description": description,
            "external_ingress": {
                "format": format_key(&format),
                "source_file": args.input.display().to_string(),
                "chunk_bytes": args.chunk_bytes,
                "payload_bytes": payload.len(),
                "payload_hash": payload_hash,
            }
        }),
    };
    let manifest = finalize_manifest(raw_manifest, vec![payload_hash.clone()])?;

    // Deterministically chunk payload and store content-addressed external-law chunks.
    let chunks = persist_external_chunks(&args.root, &payload, args.chunk_bytes)?;

    // Build a deterministic WindowBank from the external payload.
    let bank = build_bank(
        &args.family_id,
        &manifest.pack_hash,
        &payload,
        cfg.bank.window_len,
        cfg.bank.stride,
        &cfg.bank.split_ratios,
    )?;
    persist_laws_windowbank(&args.root, &args.family_id, &manifest.pack_hash, &bank)?;

    // Persist content-addressed payload + manifest under laws/.
    let payload_path = args.root.join("laws").join("payloads").join(format!("{payload_hash}.bin"));
    if !payload_path.exists() {
        if let Some(parent) = payload_path.parent() {
            std::fs::create_dir_all(parent).map_err(|e| io_err(parent, e))?;
        }
        write_bytes_atomic(&payload_path, &payload)?;
    }
    let laws_manifest_path = args
        .root
        .join("laws")
        .join("manifests")
        .join(format!("{}.json", manifest.pack_hash));
    if let Some(parent) = laws_manifest_path.parent() {
        std::fs::create_dir_all(parent).map_err(|e| io_err(parent, e))?;
    }
    write_json_atomic(&laws_manifest_path, &manifest)?;

    let mut index = ExternalLawsIndex {
        index_hash: String::new(),
        family_id: args.family_id.clone(),
        source_file: args.input.display().to_string(),
        format: format_key(&format).to_string(),
        payload_hash: payload_hash.clone(),
        payload_bytes: payload.len() as u64,
        chunk_bytes: args.chunk_bytes,
        chunks,
        pack_hash: manifest.pack_hash.clone(),
        windowbank_manifest_hash: bank.manifest.manifest_hash.clone(),
        created_unix_s: now_unix_s(),
    };
    index.index_hash = digest_json(&(
        &index.family_id,
        &index.payload_hash,
        &index.pack_hash,
        &index.windowbank_manifest_hash,
        &index.chunks,
    ))?;
    let laws_index_path = args
        .root
        .join("laws")
        .join("index")
        .join(format!("{}.json", index.index_hash));
    if let Some(parent) = laws_index_path.parent() {
        std::fs::create_dir_all(parent).map_err(|e| io_err(parent, e))?;
    }
    write_json_atomic(&laws_index_path, &index)?;

    // Emit pack payload + manifest for canonical daemon ingestion.
    let out_dir = args.out.unwrap_or_else(|| {
        args.root.join("external_ingress").join(format!(
            "{}-{}",
            sanitize_component(&args.family_id),
            &manifest.pack_hash[..12.min(manifest.pack_hash.len())]
        ))
    });
    std::fs::create_dir_all(&out_dir).map_err(|e| io_err(&out_dir, e))?;
    let out_payload_path = out_dir.join("payload.bin");
    let out_manifest_path = out_dir.join("manifest.json");
    write_bytes_atomic(&out_payload_path, &payload)?;
    write_json_atomic(&out_manifest_path, &manifest)?;

    if args.ingest {
        let receipt = ingest_reality(&args.root, &cfg, &out_manifest_path)?;
        println!(
            "ingested external reality pack {} into active snapshot",
            receipt.pack_hash
        );
    }

    println!("external ingest artifact directory: {}", out_dir.display());
    println!("manifest path: {}", out_manifest_path.display());
    println!("laws index: {}", laws_index_path.display());
    println!(
        "ingest command: apfsc_ingest_reality --root {} --manifest {}",
        args.root.display(),
        out_manifest_path.display()
    );
    Ok(())
}

fn resolve_format(input: &Path, arg: &InputFormat) -> InputFormat {
    match arg {
        InputFormat::Auto => {
            if input
                .extension()
                .and_then(|s| s.to_str())
                .map(|s| s.eq_ignore_ascii_case("csv"))
                .unwrap_or(false)
            {
                InputFormat::Csv
            } else {
                InputFormat::Bin
            }
        }
        other => other.clone(),
    }
}

fn load_external_payload(path: &Path, format: &InputFormat) -> Result<Vec<u8>> {
    match format {
        InputFormat::Bin => std::fs::read(path).map_err(|e| io_err(path, e)),
        InputFormat::Csv => {
            let text = std::fs::read_to_string(path).map_err(|e| io_err(path, e))?;
            let normalized = normalize_csv(&text);
            if normalized.is_empty() {
                return Err(ApfscError::Validation(
                    "CSV payload is empty after normalization".to_string(),
                ));
            }
            Ok(normalized.into_bytes())
        }
        InputFormat::Auto => Err(ApfscError::Validation(
            "auto format should be resolved before payload load".to_string(),
        )),
    }
}

fn normalize_csv(csv: &str) -> String {
    let mut out = String::new();
    for raw in csv.lines() {
        let line = raw.trim();
        if line.is_empty() {
            continue;
        }
        let mut first = true;
        for cell in line.split(',') {
            if !first {
                out.push(',');
            }
            out.push_str(cell.trim());
            first = false;
        }
        out.push('\n');
    }
    out
}

fn persist_external_chunks(root: &Path, payload: &[u8], chunk_bytes: usize) -> Result<Vec<ExternalChunkRef>> {
    let chunks_dir = root.join("laws").join("chunks");
    std::fs::create_dir_all(&chunks_dir).map_err(|e| io_err(&chunks_dir, e))?;
    let mut refs = Vec::new();
    for (idx, chunk) in payload.chunks(chunk_bytes).enumerate() {
        let chunk_hash = digest_bytes(chunk);
        let chunk_path = chunks_dir.join(format!("{chunk_hash}.bin"));
        if !chunk_path.exists() {
            write_bytes_atomic(&chunk_path, chunk)?;
        }
        refs.push(ExternalChunkRef {
            chunk_index: idx as u64,
            chunk_hash,
            offset: (idx * chunk_bytes) as u64,
            len: chunk.len() as u64,
        });
    }
    Ok(refs)
}

fn persist_laws_windowbank(
    root: &Path,
    family_id: &str,
    pack_hash: &str,
    bank: &WindowBank,
) -> Result<()> {
    let dir = root
        .join("laws")
        .join("windowbanks")
        .join(family_id)
        .join(pack_hash);
    std::fs::create_dir_all(&dir).map_err(|e| io_err(&dir, e))?;
    write_json_atomic(&dir.join("manifest.json"), &bank.manifest)?;
    write_jsonl(&dir.join("train_windows.jsonl"), &bank.train)?;
    write_jsonl(&dir.join("public_windows.jsonl"), &bank.public)?;
    write_jsonl(&dir.join("holdout_windows.jsonl"), &bank.holdout)?;
    write_jsonl(&dir.join("anchor_windows.jsonl"), &bank.anchor)?;
    write_jsonl(&dir.join("canary_windows.jsonl"), &bank.canary)?;
    write_jsonl(&dir.join("transfer_train_windows.jsonl"), &bank.transfer_train)?;
    write_jsonl(&dir.join("transfer_eval_windows.jsonl"), &bank.transfer_eval)?;
    write_jsonl(&dir.join("robust_public_windows.jsonl"), &bank.robust_public)?;
    write_jsonl(&dir.join("robust_holdout_windows.jsonl"), &bank.robust_holdout)?;
    write_jsonl(&dir.join("challenge_stub_windows.jsonl"), &bank.challenge_stub)?;
    Ok(())
}

fn write_jsonl<T: Serialize>(path: &Path, rows: &[T]) -> Result<()> {
    let mut out = Vec::new();
    for row in rows {
        out.extend(serde_json::to_vec(row)?);
        out.push(b'\n');
    }
    write_bytes_atomic(path, &out)
}

fn sanitize_component(s: &str) -> String {
    s.chars()
        .map(|c| if c.is_ascii_alphanumeric() || c == '-' || c == '_' { c } else { '_' })
        .collect()
}

fn to_role(v: &RealityRoleArg) -> RealityRole {
    match v {
        RealityRoleArg::Base => RealityRole::Base,
        RealityRoleArg::Transfer => RealityRole::Transfer,
        RealityRoleArg::Robust => RealityRole::Robust,
        RealityRoleArg::ChallengeStub => RealityRole::ChallengeStub,
    }
}

fn to_family_kind(v: &FamilyKindArg) -> FamilyKind {
    match v {
        FamilyKindArg::AlgorithmicSymbolic => FamilyKind::AlgorithmicSymbolic,
        FamilyKindArg::TextCodeLog => FamilyKind::TextCodeLog,
        FamilyKindArg::SensoryTemporal => FamilyKind::SensoryTemporal,
        FamilyKindArg::PhysicalSimulation => FamilyKind::PhysicalSimulation,
    }
}

fn role_key(role: RealityRole) -> &'static str {
    match role {
        RealityRole::Base => "base",
        RealityRole::Transfer => "transfer",
        RealityRole::Robust => "robust",
        RealityRole::ChallengeStub => "challenge_stub",
    }
}

fn family_kind_key(kind: FamilyKind) -> &'static str {
    match kind {
        FamilyKind::AlgorithmicSymbolic => "algorithmic_symbolic",
        FamilyKind::TextCodeLog => "text_code_log",
        FamilyKind::SensoryTemporal => "sensory_temporal",
        FamilyKind::PhysicalSimulation => "physical_simulation",
    }
}

fn format_key(format: &InputFormat) -> &'static str {
    match format {
        InputFormat::Auto => "auto",
        InputFormat::Bin => "bin",
        InputFormat::Csv => "csv",
    }
}

fn default_variant_for_role(role: RealityRole) -> String {
    match role {
        RealityRole::Base => "base".to_string(),
        RealityRole::Transfer => "transfer".to_string(),
        RealityRole::Robust => "robust".to_string(),
        RealityRole::ChallengeStub => "challenge_stub".to_string(),
    }
}
