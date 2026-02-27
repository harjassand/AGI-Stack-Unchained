use crate::search::archive::{Archive, Elite};
use crate::search::rng::Rng;

pub const TOURNAMENT_K: usize = 8;
pub const CHAMPION_INJECTION_P: f32 = 0.20;

pub fn select_parent<'a>(
    archive: &'a Archive,
    champion: Option<&'a Elite>,
    rng: &mut Rng,
) -> Option<&'a Elite> {
    if archive.filled == 0 {
        return champion;
    }

    if let Some(champ) = champion {
        if rng.gen_bool(CHAMPION_INJECTION_P) {
            return Some(champ);
        }
    }

    let mut best: Option<&Elite> = None;
    let rounds = TOURNAMENT_K.min(archive.filled as usize);
    for _ in 0..rounds {
        let Some(bin) = archive.random_filled_bin(rng) else {
            continue;
        };
        let Some(candidate) = archive.get(bin) else {
            continue;
        };
        match best {
            None => best = Some(candidate),
            Some(current) if candidate.score > current.score => best = Some(candidate),
            Some(_) => {}
        }
    }

    best.or(champion)
}
