pub mod bank;
pub mod promote;
pub mod seed;

use crate::vm::VmProgram;

#[derive(Clone, Debug, Default)]
pub struct LibraryImage {
    pub slots: Vec<Option<VmProgram>>,
}

impl From<&bank::LibraryBank> for LibraryImage {
    fn from(value: &bank::LibraryBank) -> Self {
        value.into_image()
    }
}
