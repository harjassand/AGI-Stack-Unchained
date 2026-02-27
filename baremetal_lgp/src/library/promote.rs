use crate::library::bank::{validate_program, LibraryBank, LibraryError, LibraryProgram};

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum PromoteError {
    InvalidSlot(usize),
    InvalidProgram(LibraryError),
}

pub fn promote_slot(
    bank: &mut LibraryBank,
    slot: usize,
    program: LibraryProgram,
    bump_epoch: bool,
) -> Result<(), PromoteError> {
    validate_program(&program).map_err(PromoteError::InvalidProgram)?;
    bank.replace_slot(slot, Some(program))
        .map_err(|err| match err {
            LibraryError::InvalidSlot(idx) => PromoteError::InvalidSlot(idx),
            other => PromoteError::InvalidProgram(other),
        })?;
    if bump_epoch {
        bank.epoch = bank.epoch.saturating_add(1);
    }
    Ok(())
}
