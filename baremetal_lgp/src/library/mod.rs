pub mod bank;

use crate::vm::VmProgram;

#[derive(Clone, Debug, Default)]
pub struct LibraryImage {
    pub slots: Vec<Option<VmProgram>>,
}
