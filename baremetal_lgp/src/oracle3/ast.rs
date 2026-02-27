use serde::{Deserialize, Serialize};

pub type NodeId = u32;

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct AstProgram {
    pub nodes: Vec<AstNode>,
    pub output: NodeId,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct AstNode {
    pub op: AstOp,
    pub shape: AstShape,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub enum AstShape {
    Scalar,
    Vector(u32),
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub enum AstOp {
    InputVector,
    MetaParamVector {
        count: u32,
    },
    ConstF32(f32),
    ConstVec {
        len: u32,
        value: f32,
    },

    Add {
        a: NodeId,
        b: NodeId,
    },
    Sub {
        a: NodeId,
        b: NodeId,
    },
    Mul {
        a: NodeId,
        b: NodeId,
    },
    Div {
        num: NodeId,
        den: NodeId,
    },

    Tanh {
        x: NodeId,
    },
    Sigmoid {
        x: NodeId,
    },

    Affine {
        x: NodeId,
        w_offset: u32,
        b_offset: u32,
        out_len: u32,
        in_len: u32,
    },

    Dot {
        a: NodeId,
        b: NodeId,
    },
    Broadcast {
        x: NodeId,
        len: u32,
    },
}

#[derive(Debug, Clone, PartialEq)]
pub enum AstEvalError {
    OutputNodeOutOfRange {
        output: NodeId,
        node_count: usize,
    },
    NodeRefOutOfRange {
        node: usize,
        ref_id: NodeId,
        prior_nodes: usize,
    },
    DeclaredShapeMismatch {
        node: usize,
        declared: AstShape,
        actual: AstShape,
    },
    InputShapeMismatch {
        expected: u32,
        got: usize,
    },
    OutputShapeMismatch {
        expected: u32,
        got: AstShape,
    },
    VectorLengthMismatch {
        node: usize,
        a_len: usize,
        b_len: usize,
    },
    InvalidBroadcastSource {
        node: usize,
        got: AstShape,
    },
    InvalidAffineInput {
        node: usize,
        expected: u32,
        got: AstShape,
    },
    MetaRangeOutOfBounds {
        node: usize,
        needed: usize,
        meta_len: usize,
    },
    NonFiniteProduced {
        node: usize,
    },
}

#[cfg(any(test, feature = "ast_call_counter"))]
pub static AST_EVAL_CALLS: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);

#[derive(Clone)]
enum AstValue {
    Scalar(f32),
    Vector(Vec<f32>),
}

impl AstValue {
    fn shape(&self) -> AstShape {
        match self {
            AstValue::Scalar(_) => AstShape::Scalar,
            AstValue::Vector(v) => AstShape::Vector(v.len() as u32),
        }
    }

    fn is_finite(&self) -> bool {
        match self {
            AstValue::Scalar(v) => v.is_finite(),
            AstValue::Vector(v) => v.iter().all(|x| x.is_finite()),
        }
    }
}

pub fn eval_program(
    program: &AstProgram,
    input: &[f32],
    meta_f32: &[f32],
    input_len: u32,
    output_len: u32,
    eps_div: f32,
) -> Result<Vec<f32>, AstEvalError> {
    #[cfg(any(test, feature = "ast_call_counter"))]
    AST_EVAL_CALLS.fetch_add(1, std::sync::atomic::Ordering::Relaxed);

    if input.len() != input_len as usize {
        return Err(AstEvalError::InputShapeMismatch {
            expected: input_len,
            got: input.len(),
        });
    }

    let mut values = Vec::with_capacity(program.nodes.len());
    for (idx, node) in program.nodes.iter().enumerate() {
        let value = eval_node(idx, node, &values, input, meta_f32, input_len, eps_div)?;
        let actual = value.shape();
        if actual != node.shape {
            return Err(AstEvalError::DeclaredShapeMismatch {
                node: idx,
                declared: node.shape.clone(),
                actual,
            });
        }
        if !value.is_finite() {
            return Err(AstEvalError::NonFiniteProduced { node: idx });
        }
        values.push(value);
    }

    let out_idx = usize::try_from(program.output).unwrap_or(usize::MAX);
    if out_idx >= values.len() {
        return Err(AstEvalError::OutputNodeOutOfRange {
            output: program.output,
            node_count: values.len(),
        });
    }

    match &values[out_idx] {
        AstValue::Vector(v) if v.len() == output_len as usize => Ok(v.clone()),
        other => Err(AstEvalError::OutputShapeMismatch {
            expected: output_len,
            got: other.shape(),
        }),
    }
}

fn eval_node(
    idx: usize,
    node: &AstNode,
    values: &[AstValue],
    input: &[f32],
    meta_f32: &[f32],
    input_len: u32,
    eps_div: f32,
) -> Result<AstValue, AstEvalError> {
    let get = |id: NodeId| -> Result<&AstValue, AstEvalError> {
        let ref_idx = usize::try_from(id).unwrap_or(usize::MAX);
        if ref_idx >= idx {
            return Err(AstEvalError::NodeRefOutOfRange {
                node: idx,
                ref_id: id,
                prior_nodes: idx,
            });
        }
        Ok(&values[ref_idx])
    };

    let v = match &node.op {
        AstOp::InputVector => AstValue::Vector(input.to_vec()),
        AstOp::MetaParamVector { count } => {
            let c = *count as usize;
            if c > meta_f32.len() {
                return Err(AstEvalError::MetaRangeOutOfBounds {
                    node: idx,
                    needed: c,
                    meta_len: meta_f32.len(),
                });
            }
            AstValue::Vector(meta_f32[..c].to_vec())
        }
        AstOp::ConstF32(v) => AstValue::Scalar(*v),
        AstOp::ConstVec { len, value } => AstValue::Vector(vec![*value; *len as usize]),
        AstOp::Add { a, b } => binary_elemwise(idx, get(*a)?, get(*b)?, |x, y| x + y)?,
        AstOp::Sub { a, b } => binary_elemwise(idx, get(*a)?, get(*b)?, |x, y| x - y)?,
        AstOp::Mul { a, b } => binary_elemwise(idx, get(*a)?, get(*b)?, |x, y| x * y)?,
        AstOp::Div { num, den } => {
            binary_elemwise(idx, get(*num)?, get(*den)?, |x, y| x / (y.abs() + eps_div))?
        }
        AstOp::Tanh { x } => unary_elemwise(get(*x)?, |v| v.tanh()),
        AstOp::Sigmoid { x } => unary_elemwise(get(*x)?, |v| 1.0 / (1.0 + (-v).exp())),
        AstOp::Affine {
            x,
            w_offset,
            b_offset,
            out_len,
            in_len,
        } => {
            let xval = get(*x)?;
            let AstValue::Vector(xv) = xval else {
                return Err(AstEvalError::InvalidAffineInput {
                    node: idx,
                    expected: *in_len,
                    got: xval.shape(),
                });
            };
            if xv.len() != *in_len as usize {
                return Err(AstEvalError::InvalidAffineInput {
                    node: idx,
                    expected: *in_len,
                    got: AstShape::Vector(xv.len() as u32),
                });
            }

            let weights = (*in_len as usize).saturating_mul(*out_len as usize);
            let w_start = *w_offset as usize;
            let b_start = *b_offset as usize;
            let w_end = w_start.saturating_add(weights);
            let b_end = b_start.saturating_add(*out_len as usize);
            let needed = w_end.max(b_end);
            if needed > meta_f32.len() {
                return Err(AstEvalError::MetaRangeOutOfBounds {
                    node: idx,
                    needed,
                    meta_len: meta_f32.len(),
                });
            }

            let mut out = vec![0.0_f32; *out_len as usize];
            let mut row = w_start;
            for o in 0..(*out_len as usize) {
                let mut acc = meta_f32[b_start + o];
                for &xv_i in xv {
                    acc += xv_i * meta_f32[row];
                    row += 1;
                }
                out[o] = acc;
            }
            AstValue::Vector(out)
        }
        AstOp::Dot { a, b } => {
            let av = get(*a)?;
            let bv = get(*b)?;
            let (AstValue::Vector(lhs), AstValue::Vector(rhs)) = (av, bv) else {
                return Err(AstEvalError::VectorLengthMismatch {
                    node: idx,
                    a_len: usize::from(!matches!(av, AstValue::Vector(_))),
                    b_len: usize::from(!matches!(bv, AstValue::Vector(_))),
                });
            };
            if lhs.len() != rhs.len() {
                return Err(AstEvalError::VectorLengthMismatch {
                    node: idx,
                    a_len: lhs.len(),
                    b_len: rhs.len(),
                });
            }
            let mut acc = 0.0_f32;
            for i in 0..lhs.len() {
                acc += lhs[i] * rhs[i];
            }
            AstValue::Scalar(acc)
        }
        AstOp::Broadcast { x, len } => {
            let xval = get(*x)?;
            let AstValue::Scalar(v) = xval else {
                return Err(AstEvalError::InvalidBroadcastSource {
                    node: idx,
                    got: xval.shape(),
                });
            };
            AstValue::Vector(vec![*v; *len as usize])
        }
    };

    // InputVector is shape-constrained by the spec, not by the node payload.
    if matches!(node.op, AstOp::InputVector) {
        let declared = &node.shape;
        let expected = AstShape::Vector(input_len);
        if declared != &expected {
            return Err(AstEvalError::DeclaredShapeMismatch {
                node: idx,
                declared: declared.clone(),
                actual: expected,
            });
        }
    }

    Ok(v)
}

fn unary_elemwise(value: &AstValue, op: impl Fn(f32) -> f32) -> AstValue {
    match value {
        AstValue::Scalar(v) => AstValue::Scalar(op(*v)),
        AstValue::Vector(v) => AstValue::Vector(v.iter().copied().map(op).collect()),
    }
}

fn binary_elemwise(
    node: usize,
    a: &AstValue,
    b: &AstValue,
    op: impl Fn(f32, f32) -> f32,
) -> Result<AstValue, AstEvalError> {
    let out = match (a, b) {
        (AstValue::Scalar(x), AstValue::Scalar(y)) => AstValue::Scalar(op(*x, *y)),
        (AstValue::Vector(lhs), AstValue::Scalar(y)) => {
            AstValue::Vector(lhs.iter().copied().map(|x| op(x, *y)).collect())
        }
        (AstValue::Scalar(x), AstValue::Vector(rhs)) => {
            AstValue::Vector(rhs.iter().copied().map(|y| op(*x, y)).collect())
        }
        (AstValue::Vector(lhs), AstValue::Vector(rhs)) => {
            if lhs.len() != rhs.len() {
                return Err(AstEvalError::VectorLengthMismatch {
                    node,
                    a_len: lhs.len(),
                    b_len: rhs.len(),
                });
            }
            let mut out = vec![0.0_f32; lhs.len()];
            for i in 0..lhs.len() {
                out[i] = op(lhs[i], rhs[i]);
            }
            AstValue::Vector(out)
        }
    };
    Ok(out)
}
