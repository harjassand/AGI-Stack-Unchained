use std::collections::BTreeMap;
use std::fmt;

use crate::base64::decode_base64;
use crate::canonical_json::GcjValue;

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Expr {
    Int(i64),
    Bool(bool),
    Bytes(Vec<u8>),
    Str(String),
    Var(String),
    Let { name: String, value: Box<Expr>, body: Box<Expr> },
    If { cond: Box<Expr>, then_branch: Box<Expr>, else_branch: Box<Expr> },
    And(Vec<Expr>),
    Or(Vec<Expr>),
    Not(Box<Expr>),
    Eq(Box<Expr>, Box<Expr>),
    Neq(Box<Expr>, Box<Expr>),
    Lt(Box<Expr>, Box<Expr>),
    Le(Box<Expr>, Box<Expr>),
    Gt(Box<Expr>, Box<Expr>),
    Ge(Box<Expr>, Box<Expr>),
    MapGet(Box<Expr>, Box<Expr>, Box<Expr>),
    MapHas(Box<Expr>, Box<Expr>),
    ListGet(Box<Expr>, Box<Expr>, Box<Expr>),
    ListLen(Box<Expr>),
    Sha256(Box<Expr>),
    BytesConcat(Vec<Expr>),
    ForRange {
        var: String,
        start: i64,
        end: i64,
        fuel: i64,
        init: Box<Expr>,
        body: Box<Expr>,
    },
    Safe,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Value {
    Null,
    Bool(bool),
    Int(i64),
    Str(String),
    Bytes(Vec<u8>),
    List(Vec<Value>),
    Map(BTreeMap<String, Value>),
}

#[derive(Debug)]
pub enum IrError {
    Parse(String),
    Eval(String),
}

impl fmt::Display for IrError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            IrError::Parse(msg) => write!(f, "{msg}"),
            IrError::Eval(msg) => write!(f, "{msg}"),
        }
    }
}

impl Expr {
    pub fn from_gcj(value: &GcjValue) -> Result<Self, IrError> {
        let map = match value {
            GcjValue::Object(map) => map,
            _ => return Err(IrError::Parse("expected object expression".to_string())),
        };
        if map.len() != 1 {
            return Err(IrError::Parse("expression object must have exactly one key".to_string()));
        }
        let (key, payload) = map.iter().next().unwrap();
        match key.as_str() {
            "Int" => match payload {
                GcjValue::Int(i) => Ok(Expr::Int(*i)),
                _ => Err(IrError::Parse("Int expects integer".to_string())),
            },
            "Bool" => match payload {
                GcjValue::Bool(b) => Ok(Expr::Bool(*b)),
                _ => Err(IrError::Parse("Bool expects boolean".to_string())),
            },
            "Bytes" => match payload {
                GcjValue::Str(s) => decode_base64(s)
                    .map(Expr::Bytes)
                    .map_err(|e| IrError::Parse(format!("invalid base64: {e}"))),
                _ => Err(IrError::Parse("Bytes expects base64 string".to_string())),
            },
            "Str" => match payload {
                GcjValue::Str(s) => Ok(Expr::Str(s.clone())),
                _ => Err(IrError::Parse("Str expects string".to_string())),
            },
            "Var" => match payload {
                GcjValue::Str(s) => Ok(Expr::Var(s.clone())),
                _ => Err(IrError::Parse("Var expects string".to_string())),
            },
            "Safe" => match payload {
                GcjValue::Null => Ok(Expr::Safe),
                _ => Err(IrError::Parse("Safe expects null".to_string())),
            },
            "Let" => {
                let obj = expect_object(payload, "Let")?;
                let name = expect_string(obj.get("name"), "Let.name")?;
                let value_expr = Expr::from_gcj(expect_value(obj.get("value"), "Let.value")?)?;
                let body_expr = Expr::from_gcj(expect_value(obj.get("body"), "Let.body")?)?;
                Ok(Expr::Let {
                    name,
                    value: Box::new(value_expr),
                    body: Box::new(body_expr),
                })
            }
            "If" => {
                let obj = expect_object(payload, "If")?;
                let cond = Expr::from_gcj(expect_value(obj.get("cond"), "If.cond")?)?;
                let then_branch = Expr::from_gcj(expect_value(obj.get("then"), "If.then")?)?;
                let else_branch = Expr::from_gcj(expect_value(obj.get("else"), "If.else")?)?;
                Ok(Expr::If {
                    cond: Box::new(cond),
                    then_branch: Box::new(then_branch),
                    else_branch: Box::new(else_branch),
                })
            }
            "And" => Ok(Expr::And(parse_list(payload, "And")?)),
            "Or" => Ok(Expr::Or(parse_list(payload, "Or")?)),
            "Not" => Ok(Expr::Not(Box::new(Expr::from_gcj(payload)?))),
            "Eq" => Ok(parse_bin(payload, Expr::Eq, "Eq")?),
            "Neq" => Ok(parse_bin(payload, Expr::Neq, "Neq")?),
            "Lt" => Ok(parse_bin(payload, Expr::Lt, "Lt")?),
            "Le" => Ok(parse_bin(payload, Expr::Le, "Le")?),
            "Gt" => Ok(parse_bin(payload, Expr::Gt, "Gt")?),
            "Ge" => Ok(parse_bin(payload, Expr::Ge, "Ge")?),
            "MapGet" => Ok(parse_ternary(payload, Expr::MapGet, "MapGet")?),
            "MapHas" => Ok(parse_bin(payload, Expr::MapHas, "MapHas")?),
            "ListGet" => Ok(parse_ternary(payload, Expr::ListGet, "ListGet")?),
            "ListLen" => Ok(Expr::ListLen(Box::new(Expr::from_gcj(payload)?))),
            "Sha256" => Ok(Expr::Sha256(Box::new(Expr::from_gcj(payload)?))),
            "BytesConcat" => Ok(Expr::BytesConcat(parse_list(payload, "BytesConcat")?)),
            "ForRange" => {
                let obj = expect_object(payload, "ForRange")?;
                let var = expect_string(obj.get("var"), "ForRange.var")?;
                let start = expect_int(obj.get("start"), "ForRange.start")?;
                let end = expect_int(obj.get("end"), "ForRange.end")?;
                let fuel = expect_int(obj.get("fuel"), "ForRange.fuel")?;
                if fuel < 0 {
                    return Err(IrError::Parse("ForRange.fuel must be non-negative".to_string()));
                }
                let init = Expr::from_gcj(expect_value(obj.get("init"), "ForRange.init")?)?;
                let body = Expr::from_gcj(expect_value(obj.get("body"), "ForRange.body")?)?;
                Ok(Expr::ForRange {
                    var,
                    start,
                    end,
                    fuel,
                    init: Box::new(init),
                    body: Box::new(body),
                })
            }
            _ => Err(IrError::Parse(format!("unknown expression: {key}"))),
        }
    }
}

pub fn value_from_gcj(value: &GcjValue) -> Value {
    match value {
        GcjValue::Null => Value::Null,
        GcjValue::Bool(b) => Value::Bool(*b),
        GcjValue::Int(i) => Value::Int(*i),
        GcjValue::Str(s) => Value::Str(s.clone()),
        GcjValue::Array(items) => Value::List(items.iter().map(value_from_gcj).collect()),
        GcjValue::Object(map) => {
            let mut out = BTreeMap::new();
            for (k, v) in map {
                out.insert(k.clone(), value_from_gcj(v));
            }
            Value::Map(out)
        }
    }
}

pub fn expr_to_gcj(expr: &Expr) -> GcjValue {
    use GcjValue::{Array, Object};
    let mut map = BTreeMap::new();
    match expr {
        Expr::Int(i) => {
            map.insert("Int".to_string(), GcjValue::Int(*i));
        }
        Expr::Bool(b) => {
            map.insert("Bool".to_string(), GcjValue::Bool(*b));
        }
        Expr::Bytes(bytes) => {
            map.insert("Bytes".to_string(), GcjValue::Str(encode_base64(bytes)));
        }
        Expr::Str(s) => {
            map.insert("Str".to_string(), GcjValue::Str(s.clone()));
        }
        Expr::Var(name) => {
            map.insert("Var".to_string(), GcjValue::Str(name.clone()));
        }
        Expr::Safe => {
            map.insert("Safe".to_string(), GcjValue::Null);
        }
        Expr::Let { name, value, body } => {
            let mut inner = BTreeMap::new();
            inner.insert("body".to_string(), expr_to_gcj(body));
            inner.insert("name".to_string(), GcjValue::Str(name.clone()));
            inner.insert("value".to_string(), expr_to_gcj(value));
            map.insert("Let".to_string(), Object(inner));
        }
        Expr::If { cond, then_branch, else_branch } => {
            let mut inner = BTreeMap::new();
            inner.insert("cond".to_string(), expr_to_gcj(cond));
            inner.insert("else".to_string(), expr_to_gcj(else_branch));
            inner.insert("then".to_string(), expr_to_gcj(then_branch));
            map.insert("If".to_string(), Object(inner));
        }
        Expr::And(list) => {
            map.insert("And".to_string(), Array(list.iter().map(expr_to_gcj).collect()));
        }
        Expr::Or(list) => {
            map.insert("Or".to_string(), Array(list.iter().map(expr_to_gcj).collect()));
        }
        Expr::Not(inner) => {
            map.insert("Not".to_string(), expr_to_gcj(inner));
        }
        Expr::Eq(a, b) => {
            map.insert("Eq".to_string(), Array(vec![expr_to_gcj(a), expr_to_gcj(b)]));
        }
        Expr::Neq(a, b) => {
            map.insert("Neq".to_string(), Array(vec![expr_to_gcj(a), expr_to_gcj(b)]));
        }
        Expr::Lt(a, b) => {
            map.insert("Lt".to_string(), Array(vec![expr_to_gcj(a), expr_to_gcj(b)]));
        }
        Expr::Le(a, b) => {
            map.insert("Le".to_string(), Array(vec![expr_to_gcj(a), expr_to_gcj(b)]));
        }
        Expr::Gt(a, b) => {
            map.insert("Gt".to_string(), Array(vec![expr_to_gcj(a), expr_to_gcj(b)]));
        }
        Expr::Ge(a, b) => {
            map.insert("Ge".to_string(), Array(vec![expr_to_gcj(a), expr_to_gcj(b)]));
        }
        Expr::MapGet(a, b, c) => {
            map.insert("MapGet".to_string(), Array(vec![expr_to_gcj(a), expr_to_gcj(b), expr_to_gcj(c)]));
        }
        Expr::MapHas(a, b) => {
            map.insert("MapHas".to_string(), Array(vec![expr_to_gcj(a), expr_to_gcj(b)]));
        }
        Expr::ListGet(a, b, c) => {
            map.insert("ListGet".to_string(), Array(vec![expr_to_gcj(a), expr_to_gcj(b), expr_to_gcj(c)]));
        }
        Expr::ListLen(a) => {
            map.insert("ListLen".to_string(), expr_to_gcj(a));
        }
        Expr::Sha256(a) => {
            map.insert("Sha256".to_string(), expr_to_gcj(a));
        }
        Expr::BytesConcat(list) => {
            map.insert("BytesConcat".to_string(), Array(list.iter().map(expr_to_gcj).collect()));
        }
        Expr::ForRange { var, start, end, fuel, init, body } => {
            let mut inner = BTreeMap::new();
            inner.insert("body".to_string(), expr_to_gcj(body));
            inner.insert("end".to_string(), GcjValue::Int(*end));
            inner.insert("fuel".to_string(), GcjValue::Int(*fuel));
            inner.insert("init".to_string(), expr_to_gcj(init));
            inner.insert("start".to_string(), GcjValue::Int(*start));
            inner.insert("var".to_string(), GcjValue::Str(var.clone()));
            map.insert("ForRange".to_string(), Object(inner));
        }
    };
    GcjValue::Object(map)
}

fn parse_list(value: &GcjValue, name: &str) -> Result<Vec<Expr>, IrError> {
    match value {
        GcjValue::Array(items) => items.iter().map(Expr::from_gcj).collect(),
        _ => Err(IrError::Parse(format!("{name} expects array"))),
    }
}

fn parse_bin(value: &GcjValue, ctor: fn(Box<Expr>, Box<Expr>) -> Expr, name: &str) -> Result<Expr, IrError> {
    match value {
        GcjValue::Array(items) if items.len() == 2 => {
            let a = Expr::from_gcj(&items[0])?;
            let b = Expr::from_gcj(&items[1])?;
            Ok(ctor(Box::new(a), Box::new(b)))
        }
        _ => Err(IrError::Parse(format!("{name} expects array of 2"))),
    }
}

fn parse_ternary(
    value: &GcjValue,
    ctor: fn(Box<Expr>, Box<Expr>, Box<Expr>) -> Expr,
    name: &str,
) -> Result<Expr, IrError> {
    match value {
        GcjValue::Array(items) if items.len() == 3 => {
            let a = Expr::from_gcj(&items[0])?;
            let b = Expr::from_gcj(&items[1])?;
            let c = Expr::from_gcj(&items[2])?;
            Ok(ctor(Box::new(a), Box::new(b), Box::new(c)))
        }
        _ => Err(IrError::Parse(format!("{name} expects array of 3"))),
    }
}

fn expect_object<'a>(value: &'a GcjValue, name: &str) -> Result<&'a BTreeMap<String, GcjValue>, IrError> {
    match value {
        GcjValue::Object(map) => Ok(map),
        _ => Err(IrError::Parse(format!("{name} expects object"))),
    }
}

fn expect_value<'a>(value: Option<&'a GcjValue>, name: &str) -> Result<&'a GcjValue, IrError> {
    value.ok_or_else(|| IrError::Parse(format!("missing {name}")))
}

fn expect_string(value: Option<&GcjValue>, name: &str) -> Result<String, IrError> {
    match value {
        Some(GcjValue::Str(s)) => Ok(s.clone()),
        _ => Err(IrError::Parse(format!("{name} expects string"))),
    }
}

fn expect_int(value: Option<&GcjValue>, name: &str) -> Result<i64, IrError> {
    match value {
        Some(GcjValue::Int(i)) => Ok(*i),
        _ => Err(IrError::Parse(format!("{name} expects int"))),
    }
}

fn encode_base64(bytes: &[u8]) -> String {
    const TABLE: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let mut out = String::new();
    let mut i = 0;
    while i < bytes.len() {
        let b0 = bytes[i];
        let b1 = if i + 1 < bytes.len() { bytes[i + 1] } else { 0 };
        let b2 = if i + 2 < bytes.len() { bytes[i + 2] } else { 0 };

        let triple = ((b0 as u32) << 16) | ((b1 as u32) << 8) | (b2 as u32);
        out.push(TABLE[((triple >> 18) & 0x3f) as usize] as char);
        out.push(TABLE[((triple >> 12) & 0x3f) as usize] as char);

        if i + 1 < bytes.len() {
            out.push(TABLE[((triple >> 6) & 0x3f) as usize] as char);
        } else {
            out.push('=');
        }
        if i + 2 < bytes.len() {
            out.push(TABLE[(triple & 0x3f) as usize] as char);
        } else {
            out.push('=');
        }
        i += 3;
    }
    out
}
