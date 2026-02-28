use crate::apfsc::types::ScirV2Program;

pub fn bounded_extract_equivalents(
    program: &ScirV2Program,
    max_nodes: u32,
    max_extractions: u32,
) -> Vec<ScirV2Program> {
    let mut out = Vec::new();
    if max_nodes == 0 || max_extractions == 0 {
        return out;
    }
    out.push(program.clone());

    let mut variant = program.clone();
    variant.core_blocks.sort_by(|a, b| a.id.cmp(&b.id));
    for block in &mut variant.core_blocks {
        block.ops.sort_by(|a, b| a.op.cmp(&b.op));
    }
    if out.len() < max_extractions as usize {
        out.push(variant);
    }
    out
}
