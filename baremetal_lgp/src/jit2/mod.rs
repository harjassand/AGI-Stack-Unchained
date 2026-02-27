pub mod abi;
pub mod arena;
pub mod constants;
pub mod ffi;
pub mod mutate;
pub mod promote;
pub mod raw_runner;
pub mod sniper;
pub mod swap;
pub mod templates;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum SubstrateMode {
    VmBaseline,
    MacroAsmBootstrap,
    RawAArch64,
}
