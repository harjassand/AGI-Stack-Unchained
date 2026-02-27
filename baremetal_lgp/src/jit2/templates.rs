use super::constants::A64_RET;

const A64_NOP: u32 = 0xD503201F;

pub struct Template {
    pub name: &'static str,
    pub words: Vec<u32>,
    pub enforce_suffix_ret: bool,
}

pub fn default_templates() -> Vec<Template> {
    let mut nops_then_ret = vec![A64_NOP; 8];
    nops_then_ret.push(A64_RET);

    vec![
        Template {
            name: "ret_only",
            words: vec![A64_RET],
            enforce_suffix_ret: true,
        },
        Template {
            name: "two_ret",
            words: vec![A64_RET, A64_RET],
            enforce_suffix_ret: true,
        },
        Template {
            name: "nops_then_ret",
            words: nops_then_ret,
            enforce_suffix_ret: true,
        },
    ]
}
