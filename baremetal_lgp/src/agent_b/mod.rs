use crate::oracle::SplitMix64;
use crate::oracle3::ast::{AstNode, AstOp, AstProgram, AstShape};
use crate::oracle3::compile::{compile_chunkpack, CompileCfg, FULL_COMPILE_CFG, SPEC_VERSION};
use crate::oracle3::cost::{compute_cost, AstCost};
use crate::oracle3::spec::{InputDistSpec, PiecewiseScheduleSpec, RegimeSpec, ScheduleSegment};
use crate::oracle3::validity::{evaluate_validity, phase1_vm_champ_set, ValidityVerdict};
use crate::oracle3::{score_candidate_on_chunk, ExecEngine};

pub const B_LEAGUE_K: usize = 8;
pub const B_BINS: usize = 1024;
pub const A_LEAGUE_SAMPLE: usize = 4;
pub const MIN_A_BREAK: usize = 3;
pub const DELTA_BREAK: f32 = 0.02;
pub const INVALID_FITNESS: f32 = -1.0e9;
pub const B_FULL_COMPILE_SEED: u64 = 0xB3A7_1EED_0000_0100;

#[derive(Clone)]
struct LeagueEntry {
    spec: RegimeSpec,
    fitness: f32,
}

#[derive(Clone)]
struct ArchiveEntry {
    spec: RegimeSpec,
    fitness: f32,
}

pub struct AgentBState {
    pub current: RegimeSpec,
    league: Vec<LeagueEntry>,
    archive: Vec<Option<ArchiveEntry>>,
    rng: SplitMix64,
}

pub struct BStepReport {
    pub fitness: f32,
    pub promoted: bool,
    pub validity: ValidityVerdict,
}

impl AgentBState {
    pub fn new(seed: u64) -> Self {
        let current = default_regime_spec();
        Self {
            current,
            league: Vec::new(),
            archive: vec![None; B_BINS],
            rng: SplitMix64::new(seed),
        }
    }

    pub fn league_specs(&self) -> Vec<RegimeSpec> {
        self.league.iter().map(|entry| entry.spec.clone()).collect()
    }

    pub fn step<E: ExecEngine<Vec<u32>>>(
        &mut self,
        a_current: &Vec<u32>,
        a_league: &[Vec<u32>],
        engine: &mut E,
    ) -> BStepReport {
        let mut candidate = self.current.clone();
        mutate_spec(
            &mut candidate,
            &mut self.rng,
            FULL_COMPILE_CFG.episode_count,
        );

        let validity = evaluate_validity(&candidate, &phase1_vm_champ_set());
        let ValidityVerdict::Valid { .. } = validity else {
            return BStepReport {
                fitness: INVALID_FITNESS,
                promoted: false,
                validity,
            };
        };

        let fitness = compute_fitness(&candidate, a_current, a_league, engine, FULL_COMPILE_CFG);
        if fitness <= INVALID_FITNESS {
            return BStepReport {
                fitness,
                promoted: false,
                validity,
            };
        }

        let promoted = maybe_promote_current(
            &self.current,
            &candidate,
            a_current,
            a_league,
            engine,
            FULL_COMPILE_CFG,
        );

        self.update_archive(&candidate, fitness);
        self.update_league(candidate.clone(), fitness);
        if promoted {
            self.current = candidate;
        }

        BStepReport {
            fitness,
            promoted,
            validity,
        }
    }

    fn update_archive(&mut self, spec: &RegimeSpec, fitness: f32) {
        let cost = compute_cost(spec).unwrap_or(AstCost {
            nodes: 0,
            vec_elems_total: 0,
            affine_mac: 0,
            peak_words_overapprox: 0,
            total_cost: 0,
        });
        let bin = archive_bin(spec, &cost);
        let replace = self.archive[bin]
            .as_ref()
            .map_or(true, |entry| fitness > entry.fitness);
        if replace {
            self.archive[bin] = Some(ArchiveEntry {
                spec: spec.clone(),
                fitness,
            });
        }
    }

    fn update_league(&mut self, spec: RegimeSpec, fitness: f32) {
        self.league.push(LeagueEntry { spec, fitness });
        self.league.sort_by(|a, b| {
            b.fitness
                .partial_cmp(&a.fitness)
                .unwrap_or(std::cmp::Ordering::Equal)
        });
        self.league.truncate(B_LEAGUE_K);
    }

    pub fn sample_spec_for_index(&self, index: usize) -> Option<RegimeSpec> {
        if index == 0 {
            return Some(self.current.clone());
        }
        self.league
            .get(index.saturating_sub(1))
            .map(|entry| entry.spec.clone())
    }

    pub fn best_archive_specs(&self, max: usize) -> Vec<RegimeSpec> {
        let mut entries: Vec<&ArchiveEntry> = self.archive.iter().flatten().collect();
        entries.sort_by(|a, b| {
            b.fitness
                .partial_cmp(&a.fitness)
                .unwrap_or(std::cmp::Ordering::Equal)
        });
        entries
            .into_iter()
            .take(max)
            .map(|entry| entry.spec.clone())
            .collect()
    }
}

fn compute_fitness<E: ExecEngine<Vec<u32>>>(
    spec: &RegimeSpec,
    a_current: &Vec<u32>,
    a_league: &[Vec<u32>],
    engine: &mut E,
    cfg: CompileCfg,
) -> f32 {
    let Ok(chunk) = compile_chunkpack(spec, B_FULL_COMPILE_SEED, cfg) else {
        return INVALID_FITNESS;
    };

    let mut scores = Vec::with_capacity(1 + A_LEAGUE_SAMPLE);
    scores.push(score_candidate_on_chunk(engine, a_current, &chunk).score_mean);

    for cand in a_league.iter().take(A_LEAGUE_SAMPLE) {
        scores.push(score_candidate_on_chunk(engine, cand, &chunk).score_mean);
    }

    if scores.is_empty() {
        return INVALID_FITNESS;
    }

    let s_a = scores.iter().sum::<f32>() / scores.len() as f32;
    1.0 - s_a
}

fn maybe_promote_current<E: ExecEngine<Vec<u32>>>(
    current: &RegimeSpec,
    candidate: &RegimeSpec,
    a_current: &Vec<u32>,
    a_league: &[Vec<u32>],
    engine: &mut E,
    cfg: CompileCfg,
) -> bool {
    let Ok(curr_chunk) = compile_chunkpack(current, B_FULL_COMPILE_SEED, cfg) else {
        return false;
    };
    let Ok(next_chunk) = compile_chunkpack(candidate, B_FULL_COMPILE_SEED, cfg) else {
        return false;
    };

    let mut breaks = 0usize;

    let curr_score = score_candidate_on_chunk(engine, a_current, &curr_chunk).score_mean;
    let next_score = score_candidate_on_chunk(engine, a_current, &next_chunk).score_mean;
    if next_score <= curr_score - DELTA_BREAK {
        breaks += 1;
    }

    for cand in a_league.iter().take(A_LEAGUE_SAMPLE) {
        let curr = score_candidate_on_chunk(engine, cand, &curr_chunk).score_mean;
        let next = score_candidate_on_chunk(engine, cand, &next_chunk).score_mean;
        if next <= curr - DELTA_BREAK {
            breaks += 1;
        }
    }

    breaks >= MIN_A_BREAK
}

fn archive_bin(spec: &RegimeSpec, cost: &AstCost) -> usize {
    let node_bucket = ilog2_u64(u64::from(cost.nodes));
    let affine_bucket = ilog2_u64(cost.affine_mac);
    let schedule_bucket = spec.schedule.segments.len().min(63) as u64;
    let io_bucket = ilog2_u64(u64::from(spec.input_len.max(1)));

    let mut h = 0x9E37_79B9_7F4A_7C15_u64;
    h ^= node_bucket.wrapping_mul(0xBF58_476D_1CE4_E5B9);
    h ^= affine_bucket.wrapping_mul(0x94D0_49BB_1331_11EB);
    h ^= schedule_bucket.wrapping_mul(0xD6E8_FDDA_AE9D_3A57);
    h ^= io_bucket.wrapping_mul(0xA5A5_A5A5_A5A5_A5A5);
    (h as usize) % B_BINS
}

fn ilog2_u64(v: u64) -> u64 {
    if v <= 1 {
        0
    } else {
        63 - u64::from(v.leading_zeros())
    }
}

pub fn default_regime_spec() -> RegimeSpec {
    RegimeSpec {
        version: SPEC_VERSION,
        spec_seed_salt: 0,
        input_len: 1,
        output_len: 1,
        meta_u32_len: 16,
        meta_f32_len: 16,
        episode_param_count: 4,
        input_dist: InputDistSpec::Uniform { lo: -1.0, hi: 1.0 },
        ast: AstProgram {
            nodes: vec![
                AstNode {
                    op: AstOp::InputVector,
                    shape: AstShape::Vector(1),
                },
                AstNode {
                    op: AstOp::ConstF32(2.0),
                    shape: AstShape::Scalar,
                },
                AstNode {
                    op: AstOp::Mul { a: 0, b: 1 },
                    shape: AstShape::Vector(1),
                },
            ],
            output: 2,
        },
        schedule: PiecewiseScheduleSpec {
            segments: Vec::new(),
        },
    }
}

fn mutate_spec(spec: &mut RegimeSpec, rng: &mut SplitMix64, episode_count: u32) {
    spec.spec_seed_salt = rng.next_u64();

    match rng.next_usize(6) {
        0 => mut_input_dist_params(spec, rng),
        1 => mut_schedule_segments(spec, rng, episode_count),
        2 => mut_ast_local_edit(spec, rng),
        3 => mut_ast_insert_affine(spec),
        4 => mut_ast_prune_subgraph(spec),
        _ => mut_io_lengths(spec, rng),
    }
}

fn mut_input_dist_params(spec: &mut RegimeSpec, rng: &mut SplitMix64) {
    spec.input_dist = match spec.input_dist.clone() {
        InputDistSpec::Uniform { lo, hi } => {
            let dlo = rng.range_f32(-0.25, 0.25);
            let dhi = rng.range_f32(-0.25, 0.25);
            let mut next_lo = (lo + dlo).clamp(-8.0, 8.0);
            let mut next_hi = (hi + dhi).clamp(-8.0, 8.0);
            if next_hi <= next_lo {
                std::mem::swap(&mut next_lo, &mut next_hi);
                next_hi = (next_lo + 0.1).clamp(-8.0, 8.0);
            }
            InputDistSpec::Uniform {
                lo: next_lo,
                hi: next_hi,
            }
        }
        InputDistSpec::Normal { mean, std } => {
            let mean = (mean + rng.range_f32(-0.25, 0.25)).clamp(-8.0, 8.0);
            let std = (std + rng.range_f32(-0.1, 0.1)).abs().clamp(0.01, 8.0);
            InputDistSpec::Normal { mean, std }
        }
        InputDistSpec::Rademacher { scale } => {
            let scale = (scale + rng.range_f32(-0.2, 0.2)).abs().clamp(0.01, 8.0);
            InputDistSpec::Rademacher { scale }
        }
    };
}

fn mut_schedule_segments(spec: &mut RegimeSpec, rng: &mut SplitMix64, episode_count: u32) {
    let mode = rng.next_usize(3);
    match mode {
        0 => {
            let start = rng.next_usize(episode_count.max(1) as usize) as u32;
            let span = (1 + rng.next_usize(episode_count.max(1) as usize)) as u32;
            let end = start.saturating_add(span).min(episode_count.max(start + 1));
            spec.schedule.segments.push(ScheduleSegment {
                start_episode: start,
                end_episode: end.max(start + 1),
                param_scale: rng.range_f32(0.5, 1.5),
                input_scale: rng.range_f32(0.5, 1.5),
            });
        }
        1 => {
            if !spec.schedule.segments.is_empty() {
                let idx = rng.next_usize(spec.schedule.segments.len());
                spec.schedule.segments.remove(idx);
            }
        }
        _ => {
            let len = spec.schedule.segments.len();
            if len > 0 {
                let idx = rng.next_usize(len);
                if let Some(seg) = spec.schedule.segments.get_mut(idx) {
                    seg.param_scale = (seg.param_scale + rng.range_f32(-0.2, 0.2)).clamp(0.1, 4.0);
                    seg.input_scale = (seg.input_scale + rng.range_f32(-0.2, 0.2)).clamp(0.1, 4.0);
                }
            }
        }
    }

    spec.schedule
        .segments
        .sort_by_key(|segment| segment.start_episode);
    spec.schedule
        .segments
        .retain(|seg| seg.start_episode < seg.end_episode);

    // Make non-overlapping deterministically.
    let mut prev_end = 0_u32;
    for seg in &mut spec.schedule.segments {
        if seg.start_episode < prev_end {
            seg.start_episode = prev_end;
        }
        if seg.end_episode <= seg.start_episode {
            seg.end_episode = seg.start_episode + 1;
        }
        prev_end = seg.end_episode;
    }
}

fn mut_ast_local_edit(spec: &mut RegimeSpec, rng: &mut SplitMix64) {
    if spec.ast.nodes.len() < 2 {
        return;
    }

    let idx = rng.next_usize(spec.ast.nodes.len());
    let shape = spec.ast.nodes[idx].shape.clone();

    let mut candidate_ids = Vec::new();
    for i in 0..idx {
        if spec.ast.nodes[i].shape == shape || matches!(spec.ast.nodes[i].shape, AstShape::Scalar) {
            candidate_ids.push(i as u32);
        }
    }
    if candidate_ids.is_empty() {
        return;
    }

    if rng.gen_bool(0.5) {
        let x = candidate_ids[rng.next_usize(candidate_ids.len())];
        spec.ast.nodes[idx].op = if rng.gen_bool(0.5) {
            AstOp::Tanh { x }
        } else {
            AstOp::Sigmoid { x }
        };
    } else {
        let a = candidate_ids[rng.next_usize(candidate_ids.len())];
        let b = candidate_ids[rng.next_usize(candidate_ids.len())];
        spec.ast.nodes[idx].op = match rng.next_usize(4) {
            0 => AstOp::Add { a, b },
            1 => AstOp::Sub { a, b },
            2 => AstOp::Mul { a, b },
            _ => AstOp::Div { num: a, den: b },
        };
    }
}

fn mut_ast_insert_affine(spec: &mut RegimeSpec) {
    let in_len = spec.input_len;
    let out_len = spec.output_len;
    let weights = in_len.saturating_mul(out_len);
    let needed = weights.saturating_add(out_len);
    if needed > spec.meta_f32_len {
        return;
    }

    let x = find_input_vector_node(spec).unwrap_or(0);
    let node = AstNode {
        op: AstOp::Affine {
            x,
            w_offset: 0,
            b_offset: weights,
            out_len,
            in_len,
        },
        shape: AstShape::Vector(out_len),
    };
    spec.ast.nodes.push(node);
    spec.ast.output = (spec.ast.nodes.len() - 1) as u32;
}

fn find_input_vector_node(spec: &RegimeSpec) -> Option<u32> {
    spec.ast.nodes.iter().enumerate().find_map(|(idx, node)| {
        if matches!(node.op, AstOp::InputVector) && node.shape == AstShape::Vector(spec.input_len) {
            Some(idx as u32)
        } else {
            None
        }
    })
}

fn mut_ast_prune_subgraph(spec: &mut RegimeSpec) {
    if spec.ast.nodes.is_empty() {
        return;
    }

    let mut used = vec![false; spec.ast.nodes.len()];
    mark_used(spec.ast.output as usize, &spec.ast.nodes, &mut used);

    let mut remap = vec![u32::MAX; spec.ast.nodes.len()];
    let mut compact = Vec::with_capacity(spec.ast.nodes.len());
    for (idx, node) in spec.ast.nodes.iter().enumerate() {
        if used[idx] {
            remap[idx] = compact.len() as u32;
            compact.push(node.clone());
        }
    }
    if compact.len() == spec.ast.nodes.len() {
        return;
    }

    for node in &mut compact {
        remap_node_ids(node, &remap);
    }

    spec.ast.output = remap[spec.ast.output as usize];
    spec.ast.nodes = compact;
}

fn mark_used(idx: usize, nodes: &[AstNode], used: &mut [bool]) {
    if idx >= nodes.len() || used[idx] {
        return;
    }
    used[idx] = true;
    match nodes[idx].op {
        AstOp::Add { a, b } | AstOp::Sub { a, b } | AstOp::Mul { a, b } | AstOp::Dot { a, b } => {
            mark_used(a as usize, nodes, used);
            mark_used(b as usize, nodes, used);
        }
        AstOp::Div { num, den } => {
            mark_used(num as usize, nodes, used);
            mark_used(den as usize, nodes, used);
        }
        AstOp::Tanh { x }
        | AstOp::Sigmoid { x }
        | AstOp::Broadcast { x, .. }
        | AstOp::Affine { x, .. } => mark_used(x as usize, nodes, used),
        AstOp::InputVector
        | AstOp::MetaParamVector { .. }
        | AstOp::ConstF32(_)
        | AstOp::ConstVec { .. } => {}
    }
}

fn remap_node_ids(node: &mut AstNode, remap: &[u32]) {
    match &mut node.op {
        AstOp::Add { a, b } | AstOp::Sub { a, b } | AstOp::Mul { a, b } | AstOp::Dot { a, b } => {
            *a = remap[*a as usize];
            *b = remap[*b as usize];
        }
        AstOp::Div { num, den } => {
            *num = remap[*num as usize];
            *den = remap[*den as usize];
        }
        AstOp::Tanh { x }
        | AstOp::Sigmoid { x }
        | AstOp::Broadcast { x, .. }
        | AstOp::Affine { x, .. } => {
            *x = remap[*x as usize];
        }
        AstOp::InputVector
        | AstOp::MetaParamVector { .. }
        | AstOp::ConstF32(_)
        | AstOp::ConstVec { .. } => {}
    }
}

fn mut_io_lengths(spec: &mut RegimeSpec, rng: &mut SplitMix64) {
    let delta_in = if rng.gen_bool(0.5) { 1_i32 } else { -1_i32 };
    let delta_out = if rng.gen_bool(0.5) { 1_i32 } else { -1_i32 };

    let next_in = (spec.input_len as i32 + delta_in).clamp(1, 4) as u32;
    let next_out = (spec.output_len as i32 + delta_out).clamp(1, 4) as u32;

    spec.input_len = next_in;
    spec.output_len = next_out;

    // Keep AST valid by resetting to a simple shape-safe regime.
    spec.ast = AstProgram {
        nodes: vec![
            AstNode {
                op: AstOp::InputVector,
                shape: AstShape::Vector(next_in),
            },
            AstNode {
                op: AstOp::MetaParamVector { count: next_in },
                shape: AstShape::Vector(next_in),
            },
            AstNode {
                op: AstOp::Dot { a: 0, b: 1 },
                shape: AstShape::Scalar,
            },
            AstNode {
                op: AstOp::Broadcast {
                    x: 2,
                    len: next_out,
                },
                shape: AstShape::Vector(next_out),
            },
        ],
        output: 3,
    };
}

trait SplitMixExt {
    fn gen_bool(&mut self, p: f32) -> bool;
}

impl SplitMixExt for SplitMix64 {
    fn gen_bool(&mut self, p: f32) -> bool {
        self.next_f32() < p.clamp(0.0, 1.0)
    }
}
