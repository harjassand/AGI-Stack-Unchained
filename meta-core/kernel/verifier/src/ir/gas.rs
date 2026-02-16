use crate::ir::ast::IrError;

#[derive(Clone, Debug)]
pub struct GasCounter {
    used: u64,
    limit: u64,
}

impl GasCounter {
    pub fn new(limit: u64) -> Self {
        Self { used: 0, limit }
    }

    pub fn charge(&mut self, amount: u64) -> Result<(), IrError> {
        self.used = self.used.saturating_add(amount);
        if self.used > self.limit {
            return Err(IrError::Eval("gas limit exceeded".to_string()));
        }
        Ok(())
    }

    pub fn used(&self) -> u64 {
        self.used
    }
}

pub fn sha256_gas_cost(len: usize) -> u64 {
    let blocks = (len as u64 + 63) / 64;
    50 + blocks
}
