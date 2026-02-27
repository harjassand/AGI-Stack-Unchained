use std::cmp::{Ordering, Reverse};
use std::collections::{BinaryHeap, HashMap};
use std::fs;
use std::io;
use std::path::{Path, PathBuf};

use crate::search::ir::CandidateCfg;
use crate::types::CandidateId;

#[derive(Clone, Debug, Default)]
pub struct TraceSummary {
    pub blocks: Vec<u16>,
    pub edges: Vec<(u16, u16)>,
    pub checkpoints: u32,
    pub score: f32,
    pub fuel_used: u32,
}

impl TraceSummary {
    pub fn to_bytes(&self) -> Vec<u8> {
        let mut bytes = Vec::with_capacity(32 + self.blocks.len() * 2 + self.edges.len() * 4);
        bytes.extend_from_slice(b"TRCE");
        bytes.extend_from_slice(&1_u32.to_le_bytes());
        bytes.extend_from_slice(&self.score.to_le_bytes());
        bytes.extend_from_slice(&self.fuel_used.to_le_bytes());
        bytes.extend_from_slice(&self.checkpoints.to_le_bytes());
        bytes.extend_from_slice(&(self.blocks.len() as u32).to_le_bytes());
        for &block in &self.blocks {
            bytes.extend_from_slice(&block.to_le_bytes());
        }
        bytes.extend_from_slice(&(self.edges.len() as u32).to_le_bytes());
        for &(from, to) in &self.edges {
            bytes.extend_from_slice(&from.to_le_bytes());
            bytes.extend_from_slice(&to.to_le_bytes());
        }
        bytes
    }
}

pub trait TraceOracle {
    fn run_trace(&mut self, candidate: &CandidateCfg) -> TraceSummary;
}

#[derive(Clone, Copy, Debug, PartialEq)]
struct HeapEntry {
    score: f32,
    id: u64,
}

impl Eq for HeapEntry {}

impl Ord for HeapEntry {
    fn cmp(&self, other: &Self) -> Ordering {
        self.score
            .total_cmp(&other.score)
            .then_with(|| self.id.cmp(&other.id))
    }
}

impl PartialOrd for HeapEntry {
    fn partial_cmp(&self, other: &Self) -> Option<Ordering> {
        Some(self.cmp(other))
    }
}

#[derive(Debug)]
pub struct TopKTraceManager {
    k: usize,
    run_dir: PathBuf,
    entries: HashMap<u64, f32>,
    heap: BinaryHeap<Reverse<HeapEntry>>,
}

impl TopKTraceManager {
    pub fn new(run_dir: impl AsRef<Path>, k: usize) -> io::Result<Self> {
        let traces_dir = run_dir.as_ref().join("traces");
        fs::create_dir_all(&traces_dir)?;
        Ok(Self {
            k,
            run_dir: run_dir.as_ref().to_path_buf(),
            entries: HashMap::new(),
            heap: BinaryHeap::new(),
        })
    }

    pub fn consider<T: TraceOracle>(
        &mut self,
        candidate_id: CandidateId,
        rank_score: f32,
        candidate: &CandidateCfg,
        tracer: &mut T,
    ) -> io::Result<bool> {
        if self.k == 0 {
            return Ok(false);
        }
        let id = candidate_id.0;
        let was_present = self.entries.contains_key(&id);
        let mut qualifies = was_present || self.entries.len() < self.k;

        if !qualifies {
            self.compact_heap_head();
            if let Some(Reverse(min_entry)) = self.heap.peek() {
                qualifies = rank_score > min_entry.score;
            }
        }

        if !qualifies {
            return Ok(false);
        }

        let should_update = self
            .entries
            .get(&id)
            .is_none_or(|old| rank_score > *old + f32::EPSILON);
        if should_update {
            self.entries.insert(id, rank_score);
            self.heap.push(Reverse(HeapEntry {
                score: rank_score,
                id,
            }));
        }

        self.trim_to_k();
        let is_now_present = self.entries.contains_key(&id);
        let entered_topk = !was_present && is_now_present;
        if entered_topk {
            let summary = tracer.run_trace(candidate);
            self.write_trace_file(&format!("{id}.bin"), &summary)?;
        }
        Ok(entered_topk)
    }

    pub fn write_champion_trace(
        &self,
        candidate_id: CandidateId,
        summary: &TraceSummary,
    ) -> io::Result<()> {
        self.write_trace_file(&format!("champion_{}.bin", candidate_id.0), summary)
    }

    fn trim_to_k(&mut self) {
        while self.entries.len() > self.k {
            self.compact_heap_head();
            let Some(Reverse(min_entry)) = self.heap.pop() else {
                break;
            };
            if self
                .entries
                .get(&min_entry.id)
                .is_some_and(|score| (*score - min_entry.score).abs() <= f32::EPSILON)
            {
                self.entries.remove(&min_entry.id);
            }
        }
    }

    fn compact_heap_head(&mut self) {
        while let Some(Reverse(head)) = self.heap.peek().copied() {
            let fresh = self
                .entries
                .get(&head.id)
                .is_some_and(|score| (*score - head.score).abs() <= f32::EPSILON);
            if fresh {
                break;
            }
            self.heap.pop();
        }
    }

    fn write_trace_file(&self, name: &str, summary: &TraceSummary) -> io::Result<()> {
        let path = self.run_dir.join("traces").join(name);
        fs::write(path, summary.to_bytes())
    }
}
