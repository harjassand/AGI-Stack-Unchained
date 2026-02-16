use crate::ir::ast::{Expr, IrError};

#[derive(Clone, Debug)]
pub struct IrLimits {
    pub max_ast_depth: u64,
    pub max_nodes: u64,
    pub max_fuel: i64,
    pub max_gas: u64,
}

pub fn check_limits(expr: &Expr, limits: &IrLimits) -> Result<(), IrError> {
    let depth = depth(expr);
    if depth > limits.max_ast_depth {
        return Err(IrError::Parse("AST depth limit exceeded".to_string()));
    }
    let nodes = count_nodes(expr);
    if nodes > limits.max_nodes {
        return Err(IrError::Parse("AST node limit exceeded".to_string()));
    }
    check_fuel(expr, limits.max_fuel)?;
    Ok(())
}

fn depth(expr: &Expr) -> u64 {
    match expr {
        Expr::Int(_) | Expr::Bool(_) | Expr::Bytes(_) | Expr::Str(_) | Expr::Var(_) | Expr::Safe => 1,
        Expr::Let { value, body, .. } => 1 + depth(value).max(depth(body)),
        Expr::If { cond, then_branch, else_branch } => 1 + depth(cond).max(depth(then_branch)).max(depth(else_branch)),
        Expr::And(list) | Expr::Or(list) | Expr::BytesConcat(list) => {
            1 + list.iter().map(depth).max().unwrap_or(0)
        }
        Expr::Not(inner)
        | Expr::ListLen(inner)
        | Expr::Sha256(inner) => 1 + depth(inner),
        Expr::Eq(a, b)
        | Expr::Neq(a, b)
        | Expr::Lt(a, b)
        | Expr::Le(a, b)
        | Expr::Gt(a, b)
        | Expr::Ge(a, b)
        | Expr::MapHas(a, b) => 1 + depth(a).max(depth(b)),
        Expr::MapGet(a, b, c) | Expr::ListGet(a, b, c) => 1 + depth(a).max(depth(b)).max(depth(c)),
        Expr::ForRange { init, body, .. } => 1 + depth(init).max(depth(body)),
    }
}

fn count_nodes(expr: &Expr) -> u64 {
    match expr {
        Expr::Int(_) | Expr::Bool(_) | Expr::Bytes(_) | Expr::Str(_) | Expr::Var(_) | Expr::Safe => 1,
        Expr::Let { value, body, .. } => 1 + count_nodes(value) + count_nodes(body),
        Expr::If { cond, then_branch, else_branch } => 1 + count_nodes(cond) + count_nodes(then_branch) + count_nodes(else_branch),
        Expr::And(list) | Expr::Or(list) | Expr::BytesConcat(list) => {
            1 + list.iter().map(count_nodes).sum::<u64>()
        }
        Expr::Not(inner)
        | Expr::ListLen(inner)
        | Expr::Sha256(inner) => 1 + count_nodes(inner),
        Expr::Eq(a, b)
        | Expr::Neq(a, b)
        | Expr::Lt(a, b)
        | Expr::Le(a, b)
        | Expr::Gt(a, b)
        | Expr::Ge(a, b)
        | Expr::MapHas(a, b) => 1 + count_nodes(a) + count_nodes(b),
        Expr::MapGet(a, b, c) | Expr::ListGet(a, b, c) => 1 + count_nodes(a) + count_nodes(b) + count_nodes(c),
        Expr::ForRange { init, body, .. } => 1 + count_nodes(init) + count_nodes(body),
    }
}

fn check_fuel(expr: &Expr, max_fuel: i64) -> Result<(), IrError> {
    match expr {
        Expr::ForRange { fuel, init, body, .. } => {
            if *fuel > max_fuel {
                return Err(IrError::Parse("ForRange fuel exceeds max_fuel".to_string()));
            }
            check_fuel(init, max_fuel)?;
            check_fuel(body, max_fuel)?;
        }
        Expr::Let { value, body, .. } => {
            check_fuel(value, max_fuel)?;
            check_fuel(body, max_fuel)?;
        }
        Expr::If { cond, then_branch, else_branch } => {
            check_fuel(cond, max_fuel)?;
            check_fuel(then_branch, max_fuel)?;
            check_fuel(else_branch, max_fuel)?;
        }
        Expr::And(list) | Expr::Or(list) | Expr::BytesConcat(list) => {
            for item in list {
                check_fuel(item, max_fuel)?;
            }
        }
        Expr::Not(inner)
        | Expr::ListLen(inner)
        | Expr::Sha256(inner) => check_fuel(inner, max_fuel)?,
        Expr::Eq(a, b)
        | Expr::Neq(a, b)
        | Expr::Lt(a, b)
        | Expr::Le(a, b)
        | Expr::Gt(a, b)
        | Expr::Ge(a, b)
        | Expr::MapHas(a, b) => {
            check_fuel(a, max_fuel)?;
            check_fuel(b, max_fuel)?;
        }
        Expr::MapGet(a, b, c) | Expr::ListGet(a, b, c) => {
            check_fuel(a, max_fuel)?;
            check_fuel(b, max_fuel)?;
            check_fuel(c, max_fuel)?;
        }
        Expr::Int(_) | Expr::Bool(_) | Expr::Bytes(_) | Expr::Str(_) | Expr::Var(_) | Expr::Safe => {}
    }
    Ok(())
}
