use std::collections::BTreeMap;

use crate::hash::sha256;

use super::ast::{Expr, IrError, Value};
use super::gas::{sha256_gas_cost, GasCounter};

pub struct EvalContext<'a> {
    pub vars: BTreeMap<String, Value>,
    pub gas: GasCounter,
    pub safe_fn: &'a dyn Fn(&Value, &Value) -> Result<bool, IrError>,
}

pub fn eval(expr: &Expr, ctx: &mut EvalContext<'_>) -> Result<Value, IrError> {
    ctx.gas.charge(1)?;
    match expr {
        Expr::Int(i) => Ok(Value::Int(*i)),
        Expr::Bool(b) => Ok(Value::Bool(*b)),
        Expr::Bytes(bytes) => Ok(Value::Bytes(bytes.clone())),
        Expr::Str(s) => Ok(Value::Str(s.clone())),
        Expr::Var(name) => ctx
            .vars
            .get(name)
            .cloned()
            .ok_or_else(|| IrError::Eval(format!("missing variable: {name}"))),
        Expr::Let { name, value, body } => {
            let val = eval(value, ctx)?;
            let prev = ctx.vars.insert(name.clone(), val);
            let result = eval(body, ctx);
            if let Some(p) = prev {
                ctx.vars.insert(name.clone(), p);
            } else {
                ctx.vars.remove(name);
            }
            result
        }
        Expr::If { cond, then_branch, else_branch } => {
            let c = eval(cond, ctx)?;
            match c {
                Value::Bool(true) => eval(then_branch, ctx),
                Value::Bool(false) => eval(else_branch, ctx),
                _ => Err(IrError::Eval("if condition must be bool".to_string())),
            }
        }
        Expr::And(list) => {
            for item in list {
                let v = eval(item, ctx)?;
                match v {
                    Value::Bool(true) => continue,
                    Value::Bool(false) => return Ok(Value::Bool(false)),
                    _ => return Err(IrError::Eval("And expects bool".to_string())),
                }
            }
            Ok(Value::Bool(true))
        }
        Expr::Or(list) => {
            for item in list {
                let v = eval(item, ctx)?;
                match v {
                    Value::Bool(true) => return Ok(Value::Bool(true)),
                    Value::Bool(false) => continue,
                    _ => return Err(IrError::Eval("Or expects bool".to_string())),
                }
            }
            Ok(Value::Bool(false))
        }
        Expr::Not(inner) => match eval(inner, ctx)? {
            Value::Bool(b) => Ok(Value::Bool(!b)),
            _ => Err(IrError::Eval("Not expects bool".to_string())),
        },
        Expr::Eq(a, b) => cmp_int(a, b, ctx, |x, y| x == y),
        Expr::Neq(a, b) => cmp_int(a, b, ctx, |x, y| x != y),
        Expr::Lt(a, b) => cmp_int(a, b, ctx, |x, y| x < y),
        Expr::Le(a, b) => cmp_int(a, b, ctx, |x, y| x <= y),
        Expr::Gt(a, b) => cmp_int(a, b, ctx, |x, y| x > y),
        Expr::Ge(a, b) => cmp_int(a, b, ctx, |x, y| x >= y),
        Expr::MapGet(map_expr, key_expr, default_expr) => {
            let map = eval(map_expr, ctx)?;
            let key = eval(key_expr, ctx)?;
            let key = match key {
                Value::Str(s) => s,
                _ => return Err(IrError::Eval("MapGet key must be string".to_string())),
            };
            match map {
                Value::Map(map) => {
                    if let Some(val) = map.get(&key) {
                        Ok(val.clone())
                    } else {
                        eval(default_expr, ctx)
                    }
                }
                _ => Err(IrError::Eval("MapGet expects map".to_string())),
            }
        }
        Expr::MapHas(map_expr, key_expr) => {
            let map = eval(map_expr, ctx)?;
            let key = eval(key_expr, ctx)?;
            let key = match key {
                Value::Str(s) => s,
                _ => return Err(IrError::Eval("MapHas key must be string".to_string())),
            };
            match map {
                Value::Map(map) => Ok(Value::Bool(map.contains_key(&key))),
                _ => Err(IrError::Eval("MapHas expects map".to_string())),
            }
        }
        Expr::ListGet(list_expr, idx_expr, default_expr) => {
            let list = eval(list_expr, ctx)?;
            let idx = eval(idx_expr, ctx)?;
            let idx = match idx {
                Value::Int(i) => i,
                _ => return Err(IrError::Eval("ListGet index must be int".to_string())),
            };
            match list {
                Value::List(list) => {
                    if idx >= 0 {
                        let idx = idx as usize;
                        if idx < list.len() {
                            Ok(list[idx].clone())
                        } else {
                            eval(default_expr, ctx)
                        }
                    } else {
                        eval(default_expr, ctx)
                    }
                }
                _ => Err(IrError::Eval("ListGet expects list".to_string())),
            }
        }
        Expr::ListLen(expr) => match eval(expr, ctx)? {
            Value::List(list) => Ok(Value::Int(list.len() as i64)),
            _ => Err(IrError::Eval("ListLen expects list".to_string())),
        },
        Expr::Sha256(expr) => match eval(expr, ctx)? {
            Value::Bytes(bytes) => {
                ctx.gas.charge(sha256_gas_cost(bytes.len()))?;
                Ok(Value::Bytes(sha256(&bytes).to_vec()))
            }
            _ => Err(IrError::Eval("Sha256 expects bytes".to_string())),
        },
        Expr::BytesConcat(list) => {
            let mut out = Vec::new();
            for item in list {
                match eval(item, ctx)? {
                    Value::Bytes(bytes) => out.extend_from_slice(&bytes),
                    _ => return Err(IrError::Eval("BytesConcat expects bytes".to_string())),
                }
            }
            Ok(Value::Bytes(out))
        }
        Expr::ForRange { var, start, end, fuel, init, body } => {
            let mut acc = eval(init, ctx)?;
            let mut remaining = *fuel;
            let mut i = *start;
            while i < *end {
                if remaining <= 0 {
                    return Err(IrError::Eval("ForRange fuel exhausted".to_string()));
                }
                remaining -= 1;
                ctx.gas.charge(1)?;

                let prev_i = ctx.vars.insert(var.clone(), Value::Int(i));
                let prev_acc = ctx.vars.insert("acc".to_string(), acc);
                let result = eval(body, ctx);
                if let Some(p) = prev_i {
                    ctx.vars.insert(var.clone(), p);
                } else {
                    ctx.vars.remove(var);
                }
                if let Some(p) = prev_acc {
                    ctx.vars.insert("acc".to_string(), p);
                } else {
                    ctx.vars.remove("acc");
                }
                acc = result?;
                i += 1;
            }
            Ok(acc)
        }
        Expr::Safe => {
            let x = ctx
                .vars
                .get("x")
                .ok_or_else(|| IrError::Eval("SAFE missing x".to_string()))?;
            let state = ctx
                .vars
                .get("state")
                .ok_or_else(|| IrError::Eval("SAFE missing state".to_string()))?;
            let ok = (ctx.safe_fn)(x, state)?;
            Ok(Value::Bool(ok))
        }
    }
}

fn cmp_int(
    a: &Expr,
    b: &Expr,
    ctx: &mut EvalContext<'_>,
    cmp: fn(i64, i64) -> bool,
) -> Result<Value, IrError> {
    let left = eval(a, ctx)?;
    let right = eval(b, ctx)?;
    match (left, right) {
        (Value::Int(x), Value::Int(y)) => Ok(Value::Bool(cmp(x, y))),
        _ => Err(IrError::Eval("comparison expects ints".to_string())),
    }
}
