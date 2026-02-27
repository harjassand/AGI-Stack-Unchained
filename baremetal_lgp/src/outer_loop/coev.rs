use std::collections::HashMap;

use crate::agent_b::{AgentBState, DELTA_BREAK};
use crate::jit2::mutate::mutate_words;
use crate::oracle::SplitMix64;
use crate::oracle3::chunkpack::ChunkPack;
use crate::oracle3::compile::{compile_chunkpack, FULL_COMPILE_CFG};
use crate::oracle3::spec::{spec_hash_32, RegimeSpec};
use crate::oracle3::{score_candidate_on_chunk, ExecEngine};

pub const K1: u32 = 8;
pub const K2: u32 = 4;
pub const K3: u32 = 4;
pub const CHUNK_EVALS: u32 = 50_000;
pub const DELTA_A_PROMOTE: f32 = 0.01;
pub const A_LEAGUE_K: usize = 8;

#[derive(Clone, Debug, PartialEq, Eq, Hash)]
pub enum OpponentSource {
    BCurrent,
    BLeague { index: u32 },
    Anchor { index: u32 },
}

#[derive(Clone, Debug)]
pub struct ChunkJob {
    pub opponent: OpponentSource,
    pub compile_seed: u64,
    pub evals: u32,
    pub is_proxy: bool,
}

#[derive(Clone)]
pub struct AState {
    pub champion: Vec<u32>,
    pub league: Vec<Vec<u32>>,
}

pub struct EpochRunReport {
    pub epoch: u32,
    pub a_champion_score: f32,
    pub b_current_fitness: f32,
    pub b_current_spec_hash: [u8; 32],
    pub sigalrm_count: u32,
    pub fault_count: u32,
    pub compiled_chunks: u32,
    pub schedule_hash: [u8; 32],
    pub evals: u64,
}

#[derive(Clone, Debug, PartialEq, Eq, Hash)]
struct ChunkCacheKey {
    opponent: OpponentSource,
    compile_seed: u64,
    spec_hash: [u8; 32],
}

pub fn build_epoch_schedule(
    epoch_seed: u64,
    b_league_len: usize,
    anchor_len: usize,
) -> Vec<ChunkJob> {
    let mut jobs = Vec::with_capacity((K1 + K2 + K3) as usize);

    for i in 0..K1 {
        jobs.push(ChunkJob {
            opponent: OpponentSource::BCurrent,
            compile_seed: mix64(epoch_seed ^ 0x11_u64 ^ u64::from(i)),
            evals: CHUNK_EVALS,
            is_proxy: false,
        });
    }

    for i in 0..K2 {
        let idx = if b_league_len == 0 {
            0
        } else {
            (mix64(epoch_seed ^ 0x22_u64 ^ u64::from(i)) as usize % b_league_len) as u32
        };
        jobs.push(ChunkJob {
            opponent: OpponentSource::BLeague { index: idx },
            compile_seed: mix64(epoch_seed ^ 0x33_u64 ^ u64::from(i)),
            evals: CHUNK_EVALS,
            is_proxy: false,
        });
    }

    for i in 0..K3 {
        let idx = if anchor_len == 0 {
            0
        } else {
            (i as usize % anchor_len) as u32
        };
        jobs.push(ChunkJob {
            opponent: OpponentSource::Anchor { index: idx },
            compile_seed: mix64(epoch_seed ^ 0x44_u64 ^ u64::from(i)),
            evals: CHUNK_EVALS,
            is_proxy: false,
        });
    }

    jobs
}

pub fn schedule_hash(schedule: &[ChunkJob]) -> [u8; 32] {
    let mut hasher = blake3::Hasher::new();
    for job in schedule {
        match job.opponent {
            OpponentSource::BCurrent => {
                hasher.update(&[0]);
                hasher.update(&0_u32.to_le_bytes());
            }
            OpponentSource::BLeague { index } => {
                hasher.update(&[1]);
                hasher.update(&index.to_le_bytes());
            }
            OpponentSource::Anchor { index } => {
                hasher.update(&[2]);
                hasher.update(&index.to_le_bytes());
            }
        }
        hasher.update(&job.compile_seed.to_le_bytes());
        hasher.update(&job.evals.to_le_bytes());
        hasher.update(&[u8::from(job.is_proxy)]);
    }
    *hasher.finalize().as_bytes()
}

pub fn run_epoch<E: ExecEngine<Vec<u32>>>(
    epoch: u32,
    seed: u64,
    a_state: &mut AState,
    b_state: &mut AgentBState,
    anchors: &[RegimeSpec],
    engine: &mut E,
    rng: &mut SplitMix64,
) -> EpochRunReport {
    let _ = DELTA_BREAK; // keep explicit link to B margin constant.

    let b_step = b_state.step(&a_state.champion, &a_state.league, engine);

    let b_league_len = b_state.league_specs().len();
    let schedule =
        build_epoch_schedule(mix64(seed ^ u64::from(epoch)), b_league_len, anchors.len());
    let schedule_digest = schedule_hash(&schedule);

    let mut cache: HashMap<ChunkCacheKey, ChunkPack> = HashMap::new();
    let mut compiled_chunks = 0_u32;

    for job in &schedule {
        if let Some(spec) = select_opponent_spec(job, b_state, anchors) {
            let spec_hash = spec_hash_32(&spec);
            let key = ChunkCacheKey {
                opponent: job.opponent.clone(),
                compile_seed: job.compile_seed,
                spec_hash,
            };
            cache.entry(key).or_insert_with(|| {
                compiled_chunks = compiled_chunks.saturating_add(1);
                compile_chunkpack(&spec, job.compile_seed, FULL_COMPILE_CFG)
                    .expect("phase3 scheduled chunk compile must succeed")
            });
        }
    }

    let mut champ_reports = Vec::new();
    let mut sigalrm_count = 0_u32;
    let mut fault_count = 0_u32;

    for job in &schedule {
        let Some(spec) = select_opponent_spec(job, b_state, anchors) else {
            continue;
        };
        let key = ChunkCacheKey {
            opponent: job.opponent.clone(),
            compile_seed: job.compile_seed,
            spec_hash: spec_hash_32(&spec),
        };
        let chunk = cache
            .get(&key)
            .expect("phase3 chunk cache missing scheduled key");
        let report = score_candidate_on_chunk(engine, &a_state.champion, chunk);
        sigalrm_count = sigalrm_count.saturating_add(report.sigalrm);
        if report.faulted {
            fault_count = fault_count.saturating_add(1);
        }
        champ_reports.push((job.opponent.clone(), report.score_mean, report.faulted));
    }

    let mut best_candidate = None::<(Vec<u32>, f32)>;
    for _ in 0..8 {
        let challenger = mutate_words(rng, &a_state.champion, None);
        if let Some((mean, faulted, improved_sources)) = evaluate_candidate_across_schedule(
            &challenger,
            &champ_reports,
            &schedule,
            &cache,
            b_state,
            anchors,
            engine,
        ) {
            if !faulted && improved_sources.0 && improved_sources.1 && improved_sources.2 {
                let replace = best_candidate
                    .as_ref()
                    .map_or(true, |(_, best)| mean > *best);
                if replace {
                    best_candidate = Some((challenger, mean));
                }
            }
        }
    }

    if let Some((winner, _mean)) = best_candidate {
        let prev = a_state.champion.clone();
        a_state.champion = winner;
        a_state.league.push(prev);
        if a_state.league.len() > A_LEAGUE_K {
            let drop = a_state.league.len() - A_LEAGUE_K;
            a_state.league.drain(0..drop);
        }
    }

    let a_champion_score = if champ_reports.is_empty() {
        0.0
    } else {
        champ_reports.iter().map(|(_, s, _)| *s).sum::<f32>() / champ_reports.len() as f32
    };

    let b_current_spec_hash = spec_hash_32(&b_state.current);

    EpochRunReport {
        epoch,
        a_champion_score,
        b_current_fitness: b_step.fitness,
        b_current_spec_hash,
        sigalrm_count,
        fault_count,
        compiled_chunks,
        schedule_hash: schedule_digest,
        evals: schedule.len() as u64,
    }
}

fn evaluate_candidate_across_schedule<E: ExecEngine<Vec<u32>>>(
    candidate: &Vec<u32>,
    champion_reports: &[(OpponentSource, f32, bool)],
    schedule: &[ChunkJob],
    cache: &HashMap<ChunkCacheKey, ChunkPack>,
    b_state: &AgentBState,
    anchors: &[RegimeSpec],
    engine: &mut E,
) -> Option<(f32, bool, (bool, bool, bool))> {
    if schedule.is_empty() {
        return None;
    }

    let mut sum = 0.0_f32;
    let mut faulted = false;
    let mut improved_b_current = false;
    let mut improved_b_league = false;
    let mut improved_anchor = false;

    for (idx, job) in schedule.iter().enumerate() {
        let spec = select_opponent_spec(job, b_state, anchors)?;
        let key = ChunkCacheKey {
            opponent: job.opponent.clone(),
            compile_seed: job.compile_seed,
            spec_hash: spec_hash_32(&spec),
        };
        let chunk = cache.get(&key)?;
        let report = score_candidate_on_chunk(engine, candidate, chunk);
        if report.faulted {
            faulted = true;
        }
        sum += report.score_mean;

        let base = champion_reports.get(idx).map_or(0.0, |entry| entry.1);
        if report.score_mean >= base + DELTA_A_PROMOTE {
            match job.opponent {
                OpponentSource::BCurrent => improved_b_current = true,
                OpponentSource::BLeague { .. } => improved_b_league = true,
                OpponentSource::Anchor { .. } => improved_anchor = true,
            }
        }
    }

    let mean = sum / schedule.len() as f32;
    Some((
        mean,
        faulted,
        (improved_b_current, improved_b_league, improved_anchor),
    ))
}

fn select_opponent_spec(
    job: &ChunkJob,
    b_state: &AgentBState,
    anchors: &[RegimeSpec],
) -> Option<RegimeSpec> {
    match job.opponent {
        OpponentSource::BCurrent => Some(b_state.current.clone()),
        OpponentSource::BLeague { index } => {
            let league = b_state.league_specs();
            if league.is_empty() {
                Some(b_state.current.clone())
            } else {
                Some(league[index as usize % league.len()].clone())
            }
        }
        OpponentSource::Anchor { index } => {
            if anchors.is_empty() {
                Some(default_anchor_spec())
            } else {
                Some(anchors[index as usize % anchors.len()].clone())
            }
        }
    }
}

fn default_anchor_spec() -> RegimeSpec {
    RegimeSpec {
        version: 3,
        spec_seed_salt: 0,
        input_len: 1,
        output_len: 1,
        meta_u32_len: 16,
        meta_f32_len: 16,
        episode_param_count: 4,
        input_dist: crate::oracle3::spec::InputDistSpec::Uniform { lo: -1.0, hi: 1.0 },
        ast: crate::oracle3::ast::AstProgram {
            nodes: vec![
                crate::oracle3::ast::AstNode {
                    op: crate::oracle3::ast::AstOp::InputVector,
                    shape: crate::oracle3::ast::AstShape::Vector(1),
                },
                crate::oracle3::ast::AstNode {
                    op: crate::oracle3::ast::AstOp::ConstF32(1.0),
                    shape: crate::oracle3::ast::AstShape::Scalar,
                },
                crate::oracle3::ast::AstNode {
                    op: crate::oracle3::ast::AstOp::Mul { a: 0, b: 1 },
                    shape: crate::oracle3::ast::AstShape::Vector(1),
                },
            ],
            output: 2,
        },
        schedule: crate::oracle3::spec::PiecewiseScheduleSpec {
            segments: Vec::new(),
        },
    }
}

fn mix64(mut z: u64) -> u64 {
    z = z.wrapping_add(0x9E37_79B9_7F4A_7C15);
    z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
    z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
    z ^ (z >> 31)
}
