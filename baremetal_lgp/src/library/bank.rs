use crate::abi::{CONST_POOL_WORDS, LIB_MAX_INSNS, LIB_SLOTS};
use crate::bytecode::program::BytecodeProgram;
use crate::library::LibraryImage;
use crate::vm::VmProgram;

#[derive(Clone, Debug)]
pub struct LibraryProgram {
    pub program: BytecodeProgram,
}

impl LibraryProgram {
    pub fn new(words: Vec<u32>, const_pool: [f32; CONST_POOL_WORDS]) -> Self {
        Self {
            program: BytecodeProgram {
                words,
                const_pool,
                #[cfg(feature = "trace")]
                pc_to_block: Vec::new(),
            },
        }
    }
}

impl From<BytecodeProgram> for LibraryProgram {
    fn from(value: BytecodeProgram) -> Self {
        Self { program: value }
    }
}

impl From<&LibraryProgram> for VmProgram {
    fn from(value: &LibraryProgram) -> Self {
        value.program.clone()
    }
}

#[derive(Clone, Debug)]
pub struct LibraryBank {
    pub slots: Vec<Option<LibraryProgram>>,
    pub epoch: u32,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum LibraryError {
    InvalidSlot(usize),
    ProgramTooLarge(usize),
}

impl Default for LibraryBank {
    fn default() -> Self {
        Self::empty(0)
    }
}

impl LibraryBank {
    pub fn empty(epoch: u32) -> Self {
        Self {
            slots: vec![None; LIB_SLOTS],
            epoch,
        }
    }

    pub fn new_seeded() -> Self {
        crate::library::seed::seed_library_bank()
    }

    pub fn get(&self, slot: usize) -> Option<&LibraryProgram> {
        self.slots.get(slot).and_then(Option::as_ref)
    }

    pub fn get_slot(&self, slot: usize) -> Option<&BytecodeProgram> {
        self.get(slot).map(|prog| &prog.program)
    }

    pub fn set_slot(&mut self, slot: usize, prog: BytecodeProgram) -> Result<(), usize> {
        self.replace_slot(slot, Some(LibraryProgram::from(prog)))
            .map_err(|_| slot)
    }

    pub fn replace_slot(
        &mut self,
        slot: usize,
        program: Option<LibraryProgram>,
    ) -> Result<(), LibraryError> {
        if slot >= LIB_SLOTS {
            return Err(LibraryError::InvalidSlot(slot));
        }
        if let Some(program_ref) = &program {
            validate_program(program_ref)?;
        }
        self.slots[slot] = program;
        Ok(())
    }

    pub fn into_image(&self) -> LibraryImage {
        let slots = self
            .slots
            .iter()
            .map(|slot| slot.as_ref().map(VmProgram::from))
            .collect();
        LibraryImage { slots }
    }
}

pub fn validate_program(program: &LibraryProgram) -> Result<(), LibraryError> {
    let words_len = program.program.words.len();
    if words_len > LIB_MAX_INSNS {
        return Err(LibraryError::ProgramTooLarge(words_len));
    }
    Ok(())
}
