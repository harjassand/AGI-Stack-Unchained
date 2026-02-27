use crate::search::descriptors::Descriptor;
use crate::search::ir::CandidateCfg;
use crate::search::rng::Rng;

pub const ARCHIVE_BINS: usize = 16_384;

#[derive(Clone, Debug)]
pub struct Elite {
    pub score: f32,
    pub candidate: CandidateCfg,
    pub code_size_words: u32,
    pub fuel_used: u32,
    pub desc: Descriptor,
}

#[derive(Clone, Debug)]
pub struct Archive {
    pub bins: Vec<Option<Elite>>,
    pub filled: u32,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ArchiveInsert {
    Inserted,
    Replaced,
    Kept,
}

impl Archive {
    pub fn new() -> Self {
        Self {
            bins: vec![None; ARCHIVE_BINS],
            filled: 0,
        }
    }

    pub fn insert(&mut self, bin: u16, elite: Elite) -> ArchiveInsert {
        let idx = usize::from(bin);
        let Some(slot) = self.bins.get_mut(idx) else {
            return ArchiveInsert::Kept;
        };

        match slot {
            None => {
                *slot = Some(elite);
                self.filled = self.filled.saturating_add(1);
                ArchiveInsert::Inserted
            }
            Some(existing) if elite.score > existing.score => {
                *slot = Some(elite);
                ArchiveInsert::Replaced
            }
            Some(_) => ArchiveInsert::Kept,
        }
    }

    pub fn get(&self, bin: u16) -> Option<&Elite> {
        self.bins.get(usize::from(bin)).and_then(Option::as_ref)
    }

    pub fn filled_bins(&self) -> Vec<u16> {
        let mut bins = Vec::with_capacity(self.filled as usize);
        for (idx, slot) in self.bins.iter().enumerate() {
            if slot.is_some() {
                bins.push(idx as u16);
            }
        }
        bins
    }

    pub fn random_filled_bin(&self, rng: &mut Rng) -> Option<u16> {
        if self.filled == 0 {
            return None;
        }
        let chosen = rng.gen_range_usize(0..self.filled as usize);
        let mut seen = 0usize;
        for (idx, slot) in self.bins.iter().enumerate() {
            if slot.is_none() {
                continue;
            }
            if seen == chosen {
                return Some(idx as u16);
            }
            seen += 1;
        }
        None
    }

    pub fn best(&self) -> Option<&Elite> {
        self.bins
            .iter()
            .filter_map(Option::as_ref)
            .max_by(|a, b| a.score.total_cmp(&b.score))
    }
}

impl Default for Archive {
    fn default() -> Self {
        Self::new()
    }
}
