use crate::abi::LIB_SLOTS;
use crate::bytecode::program::BytecodeProgram;

#[derive(Clone, Debug)]
pub struct LibraryBank {
    pub slots: [Option<BytecodeProgram>; LIB_SLOTS],
}

impl Default for LibraryBank {
    fn default() -> Self {
        Self {
            slots: std::array::from_fn(|_| None),
        }
    }
}

impl LibraryBank {
    pub fn get_slot(&self, slot: usize) -> Option<&BytecodeProgram> {
        self.slots.get(slot).and_then(Option::as_ref)
    }

    pub fn set_slot(&mut self, slot: usize, prog: BytecodeProgram) -> Result<(), usize> {
        let Some(dst) = self.slots.get_mut(slot) else {
            return Err(slot);
        };
        *dst = Some(prog);
        Ok(())
    }
}
