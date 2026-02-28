use std::collections::{BTreeSet, HashMap, VecDeque};

use serde::{Deserialize, Serialize};

use crate::apf3::digest::{Digest32, DigestBuilder, TAG_APF3_GRAPH_V1};
use crate::apf3::nativeblock::NativeBlockRegistry;

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub enum ValueTy {
    F32,
    VecF32 { len: u32 },
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, PartialOrd, Ord, Serialize, Deserialize)]
pub struct NodeId(pub u32);

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Edge {
    pub src: (NodeId, u16),
    pub dst: (NodeId, u16),
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, PartialOrd, Ord, Serialize, Deserialize)]
pub struct ParamRef(pub u32);

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, PartialOrd, Ord, Serialize, Deserialize)]
pub struct MemSlotId(pub u32);

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ParamBankSpec {
    pub params: Vec<ParamSpec>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ParamSpec {
    pub len: u32,
    pub init: ParamInit,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub enum ParamInit {
    Zeros,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct MemSpec {
    pub len: u32,
    pub init: MemInit,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub enum MemInit {
    Zeros,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub enum ActKind {
    Tanh,
    Sigmoid,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ActParamTemplate {
    pub a: f32,
    pub b: f32,
    pub c: f32,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub enum NodeKind {
    Input {
        index: u32,
        ty: ValueTy,
    },
    Target {
        index: u32,
        ty: ValueTy,
    },
    ConstF32 {
        v: f32,
    },
    Add,
    Mul,
    Linear {
        in_len: u32,
        out_len: u32,
        w: ParamRef,
        b: ParamRef,
    },
    ActTanh,
    ActSigmoid,
    ReadMem {
        slot: MemSlotId,
        len: u32,
    },
    WriteMem {
        slot: MemSlotId,
        len: u32,
    },
    DeltaUpdate {
        lr: f32,
        w: ParamRef,
        x: (NodeId, u16),
        err: (NodeId, u16),
    },
    NativeBlock {
        spec_digest: Digest32,
        len: u32,
    },
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct AALGraph {
    pub version: u32,
    pub nodes: Vec<(NodeId, NodeKind)>,
    pub edges: Vec<Edge>,
    pub params: ParamBankSpec,
    pub mem: Vec<MemSpec>,
    pub outputs: Vec<(NodeId, u16)>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum GraphValidationError {
    DuplicateNodeId(NodeId),
    MissingNode(NodeId),
    MissingPort(NodeId, u16),
    MissingInput(NodeId, u16),
    DuplicateInputEdge(NodeId, u16),
    TypeMismatch(&'static str),
    InvalidParamRef(ParamRef),
    InvalidMemSlot(MemSlotId),
    CyclicGraph,
    NativeBlockMissing(Digest32),
}

impl AALGraph {
    pub fn digest(&self) -> Digest32 {
        let mut b = DigestBuilder::new(TAG_APF3_GRAPH_V1);
        b.u32(self.version);

        let mut nodes = self.nodes.clone();
        nodes.sort_by_key(|(id, _)| *id);

        b.u64(nodes.len() as u64);
        for (id, kind) in nodes {
            b.u32(id.0);
            hash_node_kind(&mut b, &kind);
        }

        let mut edges = self.edges.clone();
        edges.sort_by_key(|e| (e.src.0, e.src.1, e.dst.0, e.dst.1));
        b.u64(edges.len() as u64);
        for edge in edges {
            b.u32(edge.src.0 .0);
            b.u32(edge.src.1 as u32);
            b.u32(edge.dst.0 .0);
            b.u32(edge.dst.1 as u32);
        }

        b.u64(self.params.params.len() as u64);
        for p in &self.params.params {
            b.u32(p.len);
            match p.init {
                ParamInit::Zeros => b.u32(0),
            }
        }

        b.u64(self.mem.len() as u64);
        for m in &self.mem {
            b.u32(m.len);
            match m.init {
                MemInit::Zeros => b.u32(0),
            }
        }

        b.u64(self.outputs.len() as u64);
        for (id, port) in &self.outputs {
            b.u32(id.0);
            b.u32(*port as u32);
        }

        b.finish()
    }

    pub fn validate(&self) -> Result<(), GraphValidationError> {
        self.validate_with_registry(None)
    }

    pub fn validate_with_registry(
        &self,
        registry: Option<&NativeBlockRegistry>,
    ) -> Result<(), GraphValidationError> {
        let mut node_map = HashMap::with_capacity(self.nodes.len());
        for (id, kind) in &self.nodes {
            if node_map.insert(*id, kind).is_some() {
                return Err(GraphValidationError::DuplicateNodeId(*id));
            }
        }

        let mut incoming: HashMap<NodeId, Vec<(u16, NodeId, u16)>> = HashMap::new();
        for edge in &self.edges {
            if !node_map.contains_key(&edge.src.0) {
                return Err(GraphValidationError::MissingNode(edge.src.0));
            }
            if !node_map.contains_key(&edge.dst.0) {
                return Err(GraphValidationError::MissingNode(edge.dst.0));
            }
            incoming
                .entry(edge.dst.0)
                .or_default()
                .push((edge.dst.1, edge.src.0, edge.src.1));
        }

        for (dst_node, edges) in &incoming {
            let mut seen = BTreeSet::new();
            for (dst_port, _, _) in edges {
                if !seen.insert(*dst_port) {
                    return Err(GraphValidationError::DuplicateInputEdge(
                        *dst_node, *dst_port,
                    ));
                }
            }
        }

        let topo = self.topo_order()?;
        let mut out_types: HashMap<(NodeId, u16), ValueTy> = HashMap::new();

        for node_id in topo {
            let kind = node_map
                .get(&node_id)
                .ok_or(GraphValidationError::MissingNode(node_id))?;
            let inputs = incoming.get(&node_id).cloned().unwrap_or_default();
            let mut in_by_port: HashMap<u16, ValueTy> = HashMap::new();

            for (dst_port, src_id, src_port) in inputs {
                let src_ty = out_types
                    .get(&(src_id, src_port))
                    .copied()
                    .ok_or(GraphValidationError::MissingPort(src_id, src_port))?;
                if in_by_port.insert(dst_port, src_ty).is_some() {
                    return Err(GraphValidationError::DuplicateInputEdge(node_id, dst_port));
                }
            }

            let node_out = validate_node(
                node_id,
                kind,
                &in_by_port,
                &out_types,
                &self.params,
                &self.mem,
                registry,
            )?;
            for (port, ty) in node_out {
                out_types.insert((node_id, port), ty);
            }
        }

        for &(node, port) in &self.outputs {
            if !out_types.contains_key(&(node, port)) {
                return Err(GraphValidationError::MissingPort(node, port));
            }
        }

        Ok(())
    }

    pub fn topo_order(&self) -> Result<Vec<NodeId>, GraphValidationError> {
        let mut node_ids = BTreeSet::new();
        for (node_id, _) in &self.nodes {
            node_ids.insert(*node_id);
        }

        let mut indeg: HashMap<NodeId, usize> = node_ids.iter().copied().map(|n| (n, 0)).collect();
        let mut succ: HashMap<NodeId, Vec<NodeId>> = HashMap::new();

        for edge in &self.edges {
            if !indeg.contains_key(&edge.src.0) {
                return Err(GraphValidationError::MissingNode(edge.src.0));
            }
            if !indeg.contains_key(&edge.dst.0) {
                return Err(GraphValidationError::MissingNode(edge.dst.0));
            }
            succ.entry(edge.src.0).or_default().push(edge.dst.0);
            *indeg.entry(edge.dst.0).or_insert(0) += 1;
        }

        let mut q = VecDeque::new();
        for node in &node_ids {
            if indeg.get(node).copied().unwrap_or(0) == 0 {
                q.push_back(*node);
            }
        }

        let mut out = Vec::with_capacity(node_ids.len());
        while let Some(node) = q.pop_front() {
            out.push(node);
            if let Some(children) = succ.get(&node) {
                for &c in children {
                    if let Some(v) = indeg.get_mut(&c) {
                        *v = v.saturating_sub(1);
                        if *v == 0 {
                            q.push_back(c);
                        }
                    }
                }
            }
        }

        if out.len() != node_ids.len() {
            return Err(GraphValidationError::CyclicGraph);
        }

        Ok(out)
    }

    pub fn node_kind(&self, id: NodeId) -> Option<&NodeKind> {
        self.nodes.iter().find_map(|(n, k)| (*n == id).then_some(k))
    }
}

fn validate_node(
    node_id: NodeId,
    node: &NodeKind,
    inputs: &HashMap<u16, ValueTy>,
    out_types: &HashMap<(NodeId, u16), ValueTy>,
    params: &ParamBankSpec,
    mem: &[MemSpec],
    registry: Option<&NativeBlockRegistry>,
) -> Result<Vec<(u16, ValueTy)>, GraphValidationError> {
    match node {
        NodeKind::Input { ty, .. } | NodeKind::Target { ty, .. } => Ok(vec![(0, *ty)]),
        NodeKind::ConstF32 { .. } => Ok(vec![(0, ValueTy::F32)]),
        NodeKind::Add | NodeKind::Mul => {
            let a = input_ty(inputs, 0, node_id)?;
            let b = input_ty(inputs, 1, node_id)?;
            if a != b {
                return Err(GraphValidationError::TypeMismatch(
                    "Add/Mul inputs must match",
                ));
            }
            Ok(vec![(0, a)])
        }
        NodeKind::Linear {
            in_len,
            out_len,
            w,
            b,
        } => {
            let x = input_ty(inputs, 0, node_id)?;
            if x != (ValueTy::VecF32 { len: *in_len }) {
                return Err(GraphValidationError::TypeMismatch(
                    "Linear input must match in_len",
                ));
            }

            let w_idx = w.0 as usize;
            let b_idx = b.0 as usize;
            if w_idx >= params.params.len() {
                return Err(GraphValidationError::InvalidParamRef(*w));
            }
            if b_idx >= params.params.len() {
                return Err(GraphValidationError::InvalidParamRef(*b));
            }
            let expected_w = in_len.saturating_mul(*out_len);
            if params.params[w_idx].len != expected_w || params.params[b_idx].len != *out_len {
                return Err(GraphValidationError::TypeMismatch(
                    "Linear parameter shape mismatch",
                ));
            }

            Ok(vec![(0, ValueTy::VecF32 { len: *out_len })])
        }
        NodeKind::ActTanh | NodeKind::ActSigmoid => {
            let x = input_ty(inputs, 0, node_id)?;
            Ok(vec![(0, x)])
        }
        NodeKind::ReadMem { slot, len } => {
            let idx = slot.0 as usize;
            if idx >= mem.len() {
                return Err(GraphValidationError::InvalidMemSlot(*slot));
            }
            if mem[idx].len != *len {
                return Err(GraphValidationError::TypeMismatch("ReadMem len mismatch"));
            }
            Ok(vec![(0, ValueTy::VecF32 { len: *len })])
        }
        NodeKind::WriteMem { slot, len } => {
            let idx = slot.0 as usize;
            if idx >= mem.len() {
                return Err(GraphValidationError::InvalidMemSlot(*slot));
            }
            if mem[idx].len != *len {
                return Err(GraphValidationError::TypeMismatch("WriteMem len mismatch"));
            }
            let x = input_ty(inputs, 0, node_id)?;
            if x != (ValueTy::VecF32 { len: *len }) {
                return Err(GraphValidationError::TypeMismatch(
                    "WriteMem input type mismatch",
                ));
            }
            Ok(Vec::new())
        }
        NodeKind::DeltaUpdate { w, x, err, .. } => {
            let w_idx = w.0 as usize;
            if w_idx >= params.params.len() {
                return Err(GraphValidationError::InvalidParamRef(*w));
            }

            let x_ty = out_types
                .get(&(*x))
                .copied()
                .ok_or(GraphValidationError::MissingPort(x.0, x.1))?;
            let err_ty = out_types
                .get(&(*err))
                .copied()
                .ok_or(GraphValidationError::MissingPort(err.0, err.1))?;

            let (x_len, e_len) = match (x_ty, err_ty) {
                (ValueTy::VecF32 { len: a }, ValueTy::VecF32 { len: b }) => (a, b),
                _ => {
                    return Err(GraphValidationError::TypeMismatch(
                        "DeltaUpdate references must be vectors",
                    ));
                }
            };

            if params.params[w_idx].len != x_len.saturating_mul(e_len) {
                return Err(GraphValidationError::TypeMismatch(
                    "DeltaUpdate param length must equal outer(err,x)",
                ));
            }

            Ok(Vec::new())
        }
        NodeKind::NativeBlock { spec_digest, len } => {
            if let Some(reg) = registry {
                if !reg.contains(*spec_digest) {
                    return Err(GraphValidationError::NativeBlockMissing(*spec_digest));
                }
            }

            let x = input_ty(inputs, 0, node_id)?;
            if x != (ValueTy::VecF32 { len: *len }) {
                return Err(GraphValidationError::TypeMismatch(
                    "NativeBlock input must match len",
                ));
            }
            Ok(vec![(0, ValueTy::VecF32 { len: *len })])
        }
    }
}

fn input_ty(
    inputs: &HashMap<u16, ValueTy>,
    port: u16,
    node_id: NodeId,
) -> Result<ValueTy, GraphValidationError> {
    inputs
        .get(&port)
        .copied()
        .ok_or(GraphValidationError::MissingInput(node_id, port))
}

fn hash_node_kind(b: &mut DigestBuilder, kind: &NodeKind) {
    match kind {
        NodeKind::Input { index, ty } => {
            b.u32(0);
            b.u32(*index);
            hash_ty(b, *ty);
        }
        NodeKind::Target { index, ty } => {
            b.u32(1);
            b.u32(*index);
            hash_ty(b, *ty);
        }
        NodeKind::ConstF32 { v } => {
            b.u32(2);
            b.f32(*v);
        }
        NodeKind::Add => b.u32(3),
        NodeKind::Mul => b.u32(4),
        NodeKind::Linear {
            in_len,
            out_len,
            w,
            b: bias,
        } => {
            b.u32(5);
            b.u32(*in_len);
            b.u32(*out_len);
            b.u32(w.0);
            b.u32(bias.0);
        }
        NodeKind::ActTanh => b.u32(6),
        NodeKind::ActSigmoid => b.u32(7),
        NodeKind::ReadMem { slot, len } => {
            b.u32(8);
            b.u32(slot.0);
            b.u32(*len);
        }
        NodeKind::WriteMem { slot, len } => {
            b.u32(9);
            b.u32(slot.0);
            b.u32(*len);
        }
        NodeKind::DeltaUpdate { lr, w, x, err } => {
            b.u32(10);
            b.f32(*lr);
            b.u32(w.0);
            b.u32(x.0 .0);
            b.u32(x.1 as u32);
            b.u32(err.0 .0);
            b.u32(err.1 as u32);
        }
        NodeKind::NativeBlock { spec_digest, len } => {
            b.u32(11);
            b.digest32(*spec_digest);
            b.u32(*len);
        }
    }
}

fn hash_ty(b: &mut DigestBuilder, ty: ValueTy) {
    match ty {
        ValueTy::F32 => b.u32(0),
        ValueTy::VecF32 { len } => {
            b.u32(1);
            b.u32(len);
        }
    }
}
