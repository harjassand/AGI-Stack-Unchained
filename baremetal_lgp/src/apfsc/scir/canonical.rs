use crate::apfsc::types::{CoreBlock, CoreOp, ScirV2Program};

pub fn canonicalize_v2(mut p: ScirV2Program) -> ScirV2Program {
    p.channels.sort_by(|a, b| a.id.cmp(&b.id));

    for CoreBlock { ops, .. } in &mut p.core_blocks {
        ops.retain(|op| op.op != "Identity");
        for CoreOp { args, .. } in ops {
            let mut ordered = std::collections::BTreeMap::new();
            for (k, v) in args.iter() {
                ordered.insert(k.clone(), v.clone());
            }
            *args = ordered;
        }
    }
    p.core_blocks.retain(|b| !b.ops.is_empty());
    p.core_blocks.sort_by(|a, b| a.id.cmp(&b.id));

    p.macro_calls.sort_by(|a, b| a.call_id.cmp(&b.call_id));
    p.readouts.sort_by(|a, b| a.id.cmp(&b.id));
    p.adapt_hooks.sort_by(|a, b| a.id.cmp(&b.id));

    p
}
