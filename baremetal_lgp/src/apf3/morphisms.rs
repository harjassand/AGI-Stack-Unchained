use std::collections::HashSet;

use serde::{Deserialize, Serialize};

use crate::apf3::aal_exec::AALExecutor;
use crate::apf3::aal_ir::{
    AALGraph, ActKind, ActParamTemplate, MemInit, MemSpec, NodeId, NodeKind, ParamInit, ParamRef,
    ParamSpec,
};
use crate::apf3::digest::{Digest32, DigestBuilder, TAG_APF3_DIFF_V1};
use crate::apf3::metachunkpack::MetaChunkPack;
use crate::apf3::nativeblock::NativeBlockRegistry;

#[derive(Clone, Serialize, Deserialize)]
pub struct ArchitectureDiff {
    pub version: u32,
    pub base_graph: Digest32,
    pub morphisms: Vec<Morphism>,
}

#[derive(Clone, Serialize, Deserialize)]
pub enum Morphism {
    InsertResidualBlock {
        anchor: (NodeId, u16),
        template: ResidualTemplate,
        alpha_init: f32,
    },
    WidenLayer {
        layer: NodeId,
        add_out: u32,
    },
    AddMemorySlot {
        len: u32,
        init_closed: bool,
    },
    AddHead {
        anchor: NodeId,
        head_dim: u32,
        init_zero: bool,
    },
    SwapActivationIdentityApprox {
        node: NodeId,
        new_act: ActParamTemplate,
    },
}

#[derive(Clone, Serialize, Deserialize)]
pub enum ResidualTemplate {
    LinearActLinear { hidden: u32, act: ActKind },
    NativeBlock { spec_digest: Digest32, len: u32 },
}

#[derive(Clone, Debug)]
pub struct AllowedMorphisms {
    pub insert_residual: bool,
    pub widen_layer: bool,
    pub add_memory_slot: bool,
    pub add_head: bool,
    pub swap_activation: bool,
}

impl Default for AllowedMorphisms {
    fn default() -> Self {
        Self {
            insert_residual: true,
            widen_layer: true,
            add_memory_slot: true,
            add_head: true,
            swap_activation: true,
        }
    }
}

#[derive(Debug, Clone)]
pub enum DiffError {
    BaseDigestMismatch,
    UnknownAnchor,
    UnknownNode(NodeId),
    InvalidConstraint(&'static str),
}

#[derive(Debug)]
pub struct IdentityFail {
    pub pack_digest: Digest32,
    pub before_score: f32,
    pub after_score: f32,
}

impl ArchitectureDiff {
    pub fn digest(&self) -> Digest32 {
        let mut b = DigestBuilder::new(TAG_APF3_DIFF_V1);
        b.u32(self.version);
        b.digest32(self.base_graph);
        b.u64(self.morphisms.len() as u64);
        for morph in &self.morphisms {
            hash_morphism(&mut b, morph);
        }
        b.finish()
    }

    pub fn validate(
        &self,
        allowed: &AllowedMorphisms,
        base_digest: Digest32,
    ) -> Result<(), DiffError> {
        if self.base_graph != base_digest {
            return Err(DiffError::BaseDigestMismatch);
        }

        for morph in &self.morphisms {
            match morph {
                Morphism::InsertResidualBlock { alpha_init, .. } => {
                    if !allowed.insert_residual {
                        return Err(DiffError::InvalidConstraint(
                            "InsertResidualBlock not allowed",
                        ));
                    }
                    if alpha_init.to_bits() != 0.0_f32.to_bits() {
                        return Err(DiffError::InvalidConstraint(
                            "residual alpha_init must be 0.0",
                        ));
                    }
                }
                Morphism::WidenLayer { add_out, .. } => {
                    if !allowed.widen_layer {
                        return Err(DiffError::InvalidConstraint("WidenLayer not allowed"));
                    }
                    if *add_out == 0 {
                        return Err(DiffError::InvalidConstraint("add_out must be > 0"));
                    }
                }
                Morphism::AddMemorySlot { len, init_closed } => {
                    if !allowed.add_memory_slot {
                        return Err(DiffError::InvalidConstraint("AddMemorySlot not allowed"));
                    }
                    if !*init_closed || *len == 0 {
                        return Err(DiffError::InvalidConstraint(
                            "memory slot must be closed and nonzero",
                        ));
                    }
                }
                Morphism::AddHead {
                    head_dim,
                    init_zero,
                    ..
                } => {
                    if !allowed.add_head {
                        return Err(DiffError::InvalidConstraint("AddHead not allowed"));
                    }
                    if !*init_zero || *head_dim == 0 {
                        return Err(DiffError::InvalidConstraint(
                            "AddHead requires init_zero=true and head_dim>0",
                        ));
                    }
                }
                Morphism::SwapActivationIdentityApprox { .. } => {
                    if !allowed.swap_activation {
                        return Err(DiffError::InvalidConstraint(
                            "SwapActivationIdentityApprox not allowed",
                        ));
                    }
                }
            }
        }

        Ok(())
    }

    pub fn validate_against_graph(
        &self,
        allowed: &AllowedMorphisms,
        base: &AALGraph,
    ) -> Result<(), DiffError> {
        self.validate(allowed, base.digest())?;
        for morph in &self.morphisms {
            match morph {
                Morphism::InsertResidualBlock {
                    anchor, template, ..
                } => {
                    if base.node_kind(anchor.0).is_none() {
                        return Err(DiffError::UnknownAnchor);
                    }
                    if infer_port_len(base, anchor.0, anchor.1).is_none() {
                        return Err(DiffError::InvalidConstraint(
                            "unable to infer anchor vector len",
                        ));
                    }
                    match template {
                        ResidualTemplate::LinearActLinear { hidden, .. } => {
                            if *hidden == 0 {
                                return Err(DiffError::InvalidConstraint(
                                    "residual hidden must be > 0",
                                ));
                            }
                        }
                        ResidualTemplate::NativeBlock { len, .. } => {
                            if *len == 0 {
                                return Err(DiffError::InvalidConstraint(
                                    "native residual len must be > 0",
                                ));
                            }
                        }
                    }
                }
                Morphism::WidenLayer { layer, .. } => {
                    let node = base
                        .node_kind(*layer)
                        .ok_or(DiffError::UnknownNode(*layer))?;
                    if !matches!(node, NodeKind::Linear { .. }) {
                        return Err(DiffError::InvalidConstraint(
                            "WidenLayer currently supports Linear nodes only",
                        ));
                    }
                    if node_has_consumers(base, *layer) || node_is_output(base, *layer) {
                        return Err(DiffError::InvalidConstraint(
                            "WidenLayer only allowed for detached linear nodes in v1",
                        ));
                    }
                }
                Morphism::AddMemorySlot { .. } => {}
                Morphism::AddHead { anchor, .. } => {
                    if base.node_kind(*anchor).is_none() {
                        return Err(DiffError::UnknownNode(*anchor));
                    }
                    if infer_port_len(base, *anchor, 0).is_none() {
                        return Err(DiffError::InvalidConstraint(
                            "unable to infer anchor vector len",
                        ));
                    }
                }
                Morphism::SwapActivationIdentityApprox { node, new_act } => {
                    let kind = base.node_kind(*node).ok_or(DiffError::UnknownNode(*node))?;
                    if !matches!(kind, NodeKind::ActTanh | NodeKind::ActSigmoid) {
                        return Err(DiffError::InvalidConstraint(
                            "activation swap only allowed on activation nodes",
                        ));
                    }
                    if new_act.a.to_bits() != 1.0_f32.to_bits()
                        || new_act.b.to_bits() != 0.0_f32.to_bits()
                        || new_act.c.to_bits() != 1.0_f32.to_bits()
                    {
                        return Err(DiffError::InvalidConstraint(
                            "swap activation must use identity-init parameters (a=1,b=0,c=1)",
                        ));
                    }
                }
            }
        }
        Ok(())
    }

    pub fn apply(
        &self,
        base: &AALGraph,
        registry: Option<&NativeBlockRegistry>,
    ) -> Result<AALGraph, DiffError> {
        let mut graph = base.clone();
        for morph in &self.morphisms {
            apply_morphism(&mut graph, morph, registry)?;
        }
        Ok(graph)
    }
}

pub fn identity_check(
    exec: &mut AALExecutor,
    before: &AALGraph,
    after: &AALGraph,
    probe_packs: &[MetaChunkPack],
    eps: f32,
    registry: Option<&NativeBlockRegistry>,
) -> Result<(), IdentityFail> {
    for pack in probe_packs {
        let b = exec.eval_pack(before, pack, registry);
        let a = exec.eval_pack(after, pack, registry);

        if b.query_scores.len() != a.query_scores.len() {
            return Err(IdentityFail {
                pack_digest: pack.pack_digest,
                before_score: b.query_score_mean,
                after_score: a.query_score_mean,
            });
        }
        let mut failed = false;
        for (lhs, rhs) in b.query_scores.iter().zip(a.query_scores.iter()) {
            if (*lhs - *rhs).abs() > eps {
                failed = true;
                break;
            }
        }
        if failed {
            return Err(IdentityFail {
                pack_digest: pack.pack_digest,
                before_score: b.query_score_mean,
                after_score: a.query_score_mean,
            });
        }
    }
    Ok(())
}

fn apply_morphism(
    graph: &mut AALGraph,
    morph: &Morphism,
    registry: Option<&NativeBlockRegistry>,
) -> Result<(), DiffError> {
    match morph {
        Morphism::InsertResidualBlock {
            anchor,
            template,
            alpha_init,
        } => {
            if graph.node_kind(anchor.0).is_none() {
                return Err(DiffError::UnknownAnchor);
            }
            if alpha_init.to_bits() != 0.0_f32.to_bits() {
                return Err(DiffError::InvalidConstraint(
                    "residual alpha_init must be 0.0",
                ));
            }

            let next = next_node_id(graph);
            graph
                .nodes
                .push((next, NodeKind::ConstF32 { v: *alpha_init }));

            let in_len = infer_port_len(graph, anchor.0, anchor.1).ok_or(
                DiffError::InvalidConstraint("unable to infer anchor vector len"),
            )?;

            match template {
                ResidualTemplate::LinearActLinear { hidden, act } => {
                    let hid = (*hidden).max(1);
                    let p_w1 = ParamRef(graph.params.params.len() as u32);
                    graph.params.params.push(ParamSpec {
                        len: in_len.saturating_mul(hid),
                        init: ParamInit::Zeros,
                    });
                    let p_b1 = ParamRef(graph.params.params.len() as u32);
                    graph.params.params.push(ParamSpec {
                        len: hid,
                        init: ParamInit::Zeros,
                    });
                    let p_w2 = ParamRef(graph.params.params.len() as u32);
                    graph.params.params.push(ParamSpec {
                        len: hid.saturating_mul(in_len),
                        init: ParamInit::Zeros,
                    });
                    let p_b2 = ParamRef(graph.params.params.len() as u32);
                    graph.params.params.push(ParamSpec {
                        len: in_len,
                        init: ParamInit::Zeros,
                    });

                    let a = next_node_id(graph);
                    graph.nodes.push((
                        a,
                        NodeKind::Linear {
                            in_len,
                            out_len: hid,
                            w: p_w1,
                            b: p_b1,
                        },
                    ));
                    let b = next_node_id(graph);
                    graph.nodes.push((
                        b,
                        match act {
                            ActKind::Tanh => NodeKind::ActTanh,
                            ActKind::Sigmoid => NodeKind::ActSigmoid,
                        },
                    ));
                    let c = next_node_id(graph);
                    graph.nodes.push((
                        c,
                        NodeKind::Linear {
                            in_len: hid,
                            out_len: in_len,
                            w: p_w2,
                            b: p_b2,
                        },
                    ));
                    graph.edges.push(crate::apf3::aal_ir::Edge {
                        src: *anchor,
                        dst: (a, 0),
                    });
                    graph.edges.push(crate::apf3::aal_ir::Edge {
                        src: (a, 0),
                        dst: (b, 0),
                    });
                    graph.edges.push(crate::apf3::aal_ir::Edge {
                        src: (b, 0),
                        dst: (c, 0),
                    });
                }
                ResidualTemplate::NativeBlock { spec_digest, len } => {
                    let reg = registry.ok_or(DiffError::InvalidConstraint(
                        "native residual requires native block registry",
                    ))?;
                    if !reg.contains(*spec_digest) {
                        return Err(DiffError::InvalidConstraint(
                            "native residual references unknown spec digest",
                        ));
                    }
                    if *len != in_len {
                        return Err(DiffError::InvalidConstraint(
                            "native residual len must match anchor len",
                        ));
                    }
                    let n = next_node_id(graph);
                    graph.nodes.push((
                        n,
                        NodeKind::NativeBlock {
                            spec_digest: *spec_digest,
                            len: *len,
                        },
                    ));
                    graph.edges.push(crate::apf3::aal_ir::Edge {
                        src: *anchor,
                        dst: (n, 0),
                    });
                }
            }
        }
        Morphism::WidenLayer { layer, add_out } => {
            let node = graph
                .node_kind(*layer)
                .ok_or(DiffError::UnknownNode(*layer))?
                .clone();
            if *add_out == 0 {
                return Err(DiffError::InvalidConstraint("add_out must be > 0"));
            }
            if node_has_consumers(graph, *layer) || node_is_output(graph, *layer) {
                return Err(DiffError::InvalidConstraint(
                    "WidenLayer only allowed for detached linear nodes in v1",
                ));
            }
            let (in_len, out_len, w_ref, b_ref) = match node {
                NodeKind::Linear {
                    in_len,
                    out_len,
                    w,
                    b,
                } => (in_len, out_len, w, b),
                _ => {
                    return Err(DiffError::InvalidConstraint(
                        "WidenLayer currently supports Linear nodes only",
                    ));
                }
            };
            let w_idx = w_ref.0 as usize;
            let b_idx = b_ref.0 as usize;
            if w_idx >= graph.params.params.len() || b_idx >= graph.params.params.len() {
                return Err(DiffError::InvalidConstraint(
                    "WidenLayer references missing params",
                ));
            }
            let w_expected = in_len.saturating_mul(out_len);
            if graph.params.params[w_idx].len != w_expected
                || graph.params.params[b_idx].len != out_len
            {
                return Err(DiffError::InvalidConstraint(
                    "WidenLayer requires consistent linear parameter shapes",
                ));
            }
            graph.params.params[w_idx].len =
                in_len.saturating_mul(out_len.saturating_add(*add_out));
            graph.params.params[b_idx].len = out_len.saturating_add(*add_out);

            for (node_id, kind) in &mut graph.nodes {
                if *node_id == *layer {
                    if let NodeKind::Linear { out_len, .. } = kind {
                        *out_len = out_len.saturating_add(*add_out);
                    }
                }
            }
        }
        Morphism::AddMemorySlot { len, init_closed } => {
            if !*init_closed || *len == 0 {
                return Err(DiffError::InvalidConstraint(
                    "memory slot must be closed and nonzero",
                ));
            }
            graph.mem.push(MemSpec {
                len: *len,
                init: MemInit::Zeros,
            });
        }
        Morphism::AddHead {
            anchor,
            head_dim,
            init_zero,
        } => {
            if !*init_zero || *head_dim == 0 {
                return Err(DiffError::InvalidConstraint(
                    "AddHead requires init_zero=true and head_dim>0",
                ));
            }
            if graph.node_kind(*anchor).is_none() {
                return Err(DiffError::UnknownNode(*anchor));
            }
            let in_len = infer_port_len(graph, *anchor, 0).ok_or(DiffError::InvalidConstraint(
                "unable to infer anchor vector len",
            ))?;

            let p_w = ParamRef(graph.params.params.len() as u32);
            graph.params.params.push(ParamSpec {
                len: in_len.saturating_mul(*head_dim),
                init: ParamInit::Zeros,
            });
            let p_b = ParamRef(graph.params.params.len() as u32);
            graph.params.params.push(ParamSpec {
                len: *head_dim,
                init: ParamInit::Zeros,
            });

            let n = next_node_id(graph);
            graph.nodes.push((
                n,
                NodeKind::Linear {
                    in_len,
                    out_len: *head_dim,
                    w: p_w,
                    b: p_b,
                },
            ));
            graph.edges.push(crate::apf3::aal_ir::Edge {
                src: (*anchor, 0),
                dst: (n, 0),
            });
        }
        Morphism::SwapActivationIdentityApprox { node, .. } => {
            if graph.node_kind(*node).is_none() {
                return Err(DiffError::UnknownNode(*node));
            }
            // Identity-init activation swap is currently represented as no-op.
        }
    }

    Ok(())
}

fn next_node_id(graph: &AALGraph) -> NodeId {
    let next = graph
        .nodes
        .iter()
        .map(|(id, _)| id.0)
        .max()
        .unwrap_or(0)
        .saturating_add(1);
    NodeId(next)
}

fn node_has_consumers(graph: &AALGraph, node: NodeId) -> bool {
    graph.edges.iter().any(|e| e.src.0 == node)
}

fn node_is_output(graph: &AALGraph, node: NodeId) -> bool {
    graph.outputs.iter().any(|(n, _)| *n == node)
}

fn infer_port_len(graph: &AALGraph, node: NodeId, port: u16) -> Option<u32> {
    infer_port_len_inner(graph, node, port, &mut HashSet::new())
}

fn infer_port_len_inner(
    graph: &AALGraph,
    node: NodeId,
    port: u16,
    seen: &mut HashSet<(NodeId, u16)>,
) -> Option<u32> {
    if !seen.insert((node, port)) {
        return None;
    }
    let kind = graph.node_kind(node)?;
    let out = match kind {
        NodeKind::Input {
            ty: crate::apf3::aal_ir::ValueTy::VecF32 { len },
            ..
        } if port == 0 => Some(*len),
        NodeKind::Target {
            ty: crate::apf3::aal_ir::ValueTy::VecF32 { len },
            ..
        } if port == 0 => Some(*len),
        NodeKind::Linear { out_len, .. } if port == 0 => Some(*out_len),
        NodeKind::ReadMem { len, .. } if port == 0 => Some(*len),
        NodeKind::NativeBlock { len, .. } if port == 0 => Some(*len),
        NodeKind::ActTanh | NodeKind::ActSigmoid | NodeKind::Add | NodeKind::Mul if port == 0 => {
            let src = graph
                .edges
                .iter()
                .find(|e| e.dst == (node, 0))
                .map(|e| e.src)?;
            infer_port_len_inner(graph, src.0, src.1, seen)
        }
        _ => None,
    };
    seen.remove(&(node, port));
    out
}

fn hash_morphism(b: &mut DigestBuilder, morph: &Morphism) {
    match morph {
        Morphism::InsertResidualBlock {
            anchor,
            template,
            alpha_init,
        } => {
            b.u32(0);
            b.u32(anchor.0 .0);
            b.u32(anchor.1 as u32);
            b.f32(*alpha_init);
            match template {
                ResidualTemplate::LinearActLinear { hidden, act } => {
                    b.u32(0);
                    b.u32(*hidden);
                    b.u32(match act {
                        ActKind::Tanh => 0,
                        ActKind::Sigmoid => 1,
                    });
                }
                ResidualTemplate::NativeBlock { spec_digest, len } => {
                    b.u32(1);
                    b.digest32(*spec_digest);
                    b.u32(*len);
                }
            }
        }
        Morphism::WidenLayer { layer, add_out } => {
            b.u32(1);
            b.u32(layer.0);
            b.u32(*add_out);
        }
        Morphism::AddMemorySlot { len, init_closed } => {
            b.u32(2);
            b.u32(*len);
            b.bool(*init_closed);
        }
        Morphism::AddHead {
            anchor,
            head_dim,
            init_zero,
        } => {
            b.u32(3);
            b.u32(anchor.0);
            b.u32(*head_dim);
            b.bool(*init_zero);
        }
        Morphism::SwapActivationIdentityApprox { node, new_act } => {
            b.u32(4);
            b.u32(node.0);
            b.f32(new_act.a);
            b.f32(new_act.b);
            b.f32(new_act.c);
        }
    }
}
