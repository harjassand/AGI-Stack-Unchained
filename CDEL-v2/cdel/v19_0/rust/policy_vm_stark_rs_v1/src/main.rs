use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;
use std::env;
use std::fs;
use std::path::PathBuf;
use winterfell::crypto::{hashers::Blake3_256, DefaultRandomCoin, MerkleTree};
use winterfell::math::{fields::f128::BaseElement, FieldElement, ToElements};
use winterfell::matrix::ColMatrix;
use winterfell::{
    verify, AcceptableOptions, Air, AirContext, Assertion, AuxRandElements, BatchingMethod,
    CompositionPoly, CompositionPolyTrace, ConstraintCompositionCoefficients,
    DefaultConstraintCommitment, DefaultConstraintEvaluator, DefaultTraceLde, EvaluationFrame,
    FieldExtension, PartitionOptions, Proof, ProofOptions, Prover, StarkDomain, TraceInfo,
    TracePolyTable, TraceTable, TransitionConstraintDegree,
};

const COL_PC: usize = 0;
const COL_STACK_DEPTH: usize = 1;
const COL_ACTION_CODE: usize = 2;
const COL_CAMPAIGN_INDEX: usize = 3;
const COL_PRIORITY_Q32: usize = 4;
const COL_EMITTED: usize = 5;
const COL_STEPS: usize = 6;
const COL_ACTIVE: usize = 7;
const COL_OP_NOP: usize = 8;
const COL_OP_PUSH: usize = 9;
const COL_OP_CMP_Q32: usize = 10;
const COL_OP_CMP_U64: usize = 11;
const COL_OP_JZ: usize = 12;
const COL_OP_JMP: usize = 13;
const COL_OP_SET: usize = 14;
const COL_OP_EMIT: usize = 15;
const COL_JUMP_TARGET: usize = 16;
const COL_COND_B: usize = 17;
const COL_SET_VALUE: usize = 18;
const COL_SET_IS_ACTION: usize = 19;
const COL_SET_IS_CAMPAIGN: usize = 20;
const COL_SET_IS_PRIORITY: usize = 21;
const TRACE_WIDTH: usize = 22;

const OPCODE_NOP: u8 = 0;
const OPCODE_PUSH_CONST: u8 = 1;
const OPCODE_CMP_Q32: u8 = 2;
const OPCODE_CMP_U64: u8 = 3;
const OPCODE_JZ: u8 = 4;
const OPCODE_JMP: u8 = 5;
const OPCODE_SET_PLAN_FIELD: u8 = 6;
const OPCODE_EMIT_PLAN: u8 = 7;

const FIELD_ACTION_KIND: u8 = 0;
const FIELD_CAMPAIGN_ID: u8 = 1;
const FIELD_PRIORITY_Q32: u8 = 2;
const FIELD_UNUSED: u8 = 255;

#[derive(Clone, Debug, Deserialize)]
struct ProofOptionsInput {
    num_queries: u32,
    blowup_factor: u32,
    grinding_factor: u32,
    field_extension: String,
    fri_folding_factor: u32,
    fri_remainder_max_degree: u32,
    batching_constraints: String,
    batching_deep: String,
    num_partitions: u32,
    hash_rate: u32,
}

#[derive(Clone, Debug, Deserialize)]
struct InitialStateInput {
    pc_u32: u32,
    stack_depth_u32: u32,
    action_kind_code_u8: u8,
    campaign_id_index_u16: u16,
    priority_q32_i64: i64,
}

#[derive(Clone, Debug, Deserialize)]
struct PublicOutputsInput {
    action_kind_code_u8: u8,
    campaign_id_index_u16: u16,
    priority_q32_i64: i64,
    steps_executed_u64: u64,
}

#[derive(Clone, Debug, Deserialize)]
struct VmRowInput {
    pc_u32: u32,
    next_pc_u32: u32,
    op_code_u8: u8,
    jump_target_u32: u32,
    cond_b: bool,
    stack_before_depth_u32: u32,
    stack_after_depth_u32: u32,
    set_field_code_u8: u8,
    set_value_i64: i64,
}

#[derive(Clone, Debug, Deserialize)]
struct CliInput {
    schema_version: String,
    statement_hash_lo_u64: u64,
    statement_hash_hi_u64: u64,
    budget_hash_lo_u64: u64,
    budget_hash_hi_u64: u64,
    trace_hash_lo_u64: u64,
    trace_hash_hi_u64: u64,
    final_stack_hash_lo_u64: u64,
    final_stack_hash_hi_u64: u64,
    proof_options: ProofOptionsInput,
    initial_state: InitialStateInput,
    public_outputs: PublicOutputsInput,
    vm_rows: Option<Vec<VmRowInput>>,
}

#[derive(Clone, Debug, Serialize)]
struct CliReceipt {
    schema_version: String,
    mode: String,
    status: String,
    reason: String,
    proof_bytes_len_u64: u64,
}

#[derive(Clone, Debug)]
struct PublicInputs {
    init_pc_u64: u64,
    init_stack_depth_u64: u64,
    init_action_code_u64: u64,
    init_campaign_index_u64: u64,
    init_priority_q32_i64: i64,
    final_action_code_u64: u64,
    final_campaign_index_u64: u64,
    final_priority_q32_i64: i64,
    final_steps_u64: u64,
    final_emitted_u64: u64,
    statement_hash_lo_u64: u64,
    statement_hash_hi_u64: u64,
    budget_hash_lo_u64: u64,
    budget_hash_hi_u64: u64,
    trace_hash_lo_u64: u64,
    trace_hash_hi_u64: u64,
    final_stack_hash_lo_u64: u64,
    final_stack_hash_hi_u64: u64,
}

impl ToElements<BaseElement> for PublicInputs {
    fn to_elements(&self) -> Vec<BaseElement> {
        vec![
            BaseElement::new(self.init_pc_u64 as u128),
            BaseElement::new(self.init_stack_depth_u64 as u128),
            BaseElement::new(self.init_action_code_u64 as u128),
            BaseElement::new(self.init_campaign_index_u64 as u128),
            fe_from_i64(self.init_priority_q32_i64),
            BaseElement::new(self.final_action_code_u64 as u128),
            BaseElement::new(self.final_campaign_index_u64 as u128),
            fe_from_i64(self.final_priority_q32_i64),
            BaseElement::new(self.final_steps_u64 as u128),
            BaseElement::new(self.final_emitted_u64 as u128),
            BaseElement::new(self.statement_hash_lo_u64 as u128),
            BaseElement::new(self.statement_hash_hi_u64 as u128),
            BaseElement::new(self.budget_hash_lo_u64 as u128),
            BaseElement::new(self.budget_hash_hi_u64 as u128),
            BaseElement::new(self.trace_hash_lo_u64 as u128),
            BaseElement::new(self.trace_hash_hi_u64 as u128),
            BaseElement::new(self.final_stack_hash_lo_u64 as u128),
            BaseElement::new(self.final_stack_hash_hi_u64 as u128),
        ]
    }
}

struct VmAir {
    context: AirContext<BaseElement>,
    pub_inputs: PublicInputs,
}

impl Air for VmAir {
    type BaseField = BaseElement;
    type PublicInputs = PublicInputs;

    fn new(trace_info: TraceInfo, pub_inputs: PublicInputs, options: ProofOptions) -> Self {
        if trace_info.width() != TRACE_WIDTH {
            panic!("trace width mismatch");
        }
        let degree_spec: [usize; 30] = [
            2, 1, 2, 2, 1, 1, 1, 1, 1, 1, 2, 1, 1, 1, 1, 1, 2, 2, 1, 1, 1, 2, 2, 2, 2, 1, 1, 1, 3,
            2,
        ];
        let degrees = degree_spec
            .into_iter()
            .map(TransitionConstraintDegree::new)
            .collect::<Vec<_>>();
        Self {
            context: AirContext::new(trace_info, degrees, 11, options),
            pub_inputs,
        }
    }

    fn context(&self) -> &AirContext<Self::BaseField> {
        &self.context
    }

    fn evaluate_transition<E: FieldElement + From<Self::BaseField>>(
        &self,
        frame: &EvaluationFrame<E>,
        _periodic_values: &[E],
        result: &mut [E],
    ) {
        let current = frame.current();
        let next = frame.next();

        let one = E::ONE;
        let zero = E::ZERO;

        let active = current[COL_ACTIVE];
        let emitted = current[COL_EMITTED];
        let cond_b = current[COL_COND_B];
        let op_nop = current[COL_OP_NOP];
        let op_push = current[COL_OP_PUSH];
        let op_cmp_q32 = current[COL_OP_CMP_Q32];
        let op_cmp_u64 = current[COL_OP_CMP_U64];
        let op_jz = current[COL_OP_JZ];
        let op_jmp = current[COL_OP_JMP];
        let op_set = current[COL_OP_SET];
        let op_emit = current[COL_OP_EMIT];
        let set_is_action = current[COL_SET_IS_ACTION];
        let set_is_campaign = current[COL_SET_IS_CAMPAIGN];
        let set_is_priority = current[COL_SET_IS_PRIORITY];

        let mut i = 0usize;
        result[i] = active * (active - one);
        i += 1;
        result[i] = cond_b * (cond_b - one);
        i += 1;
        result[i] = emitted * (emitted - one);
        i += 1;

        for selector in [
            op_nop, op_push, op_cmp_q32, op_cmp_u64, op_jz, op_jmp, op_set, op_emit,
        ] {
            result[i] = selector * (selector - one);
            i += 1;
        }
        result[i] =
            op_nop + op_push + op_cmp_q32 + op_cmp_u64 + op_jz + op_jmp + op_set + op_emit - one;
        i += 1;

        result[i] = set_is_action * (set_is_action - one);
        i += 1;
        result[i] = set_is_campaign * (set_is_campaign - one);
        i += 1;
        result[i] = set_is_priority * (set_is_priority - one);
        i += 1;
        result[i] = set_is_action + set_is_campaign + set_is_priority - op_set;
        i += 1;

        let pc = current[COL_PC];
        let next_pc = current[COL_JUMP_TARGET];
        let base_pc = pc + one;
        let jz_next = cond_b * base_pc + (one - cond_b) * next_pc;
        let computed_pc = base_pc + op_jmp * (next_pc - base_pc) + op_jz * (jz_next - base_pc);

        let inactive = one - active;
        result[i] = inactive * (next[COL_PC] - current[COL_PC]);
        i += 1;
        result[i] = inactive * (next[COL_STACK_DEPTH] - current[COL_STACK_DEPTH]);
        i += 1;
        result[i] = inactive * (next[COL_ACTION_CODE] - current[COL_ACTION_CODE]);
        i += 1;
        result[i] = inactive * (next[COL_CAMPAIGN_INDEX] - current[COL_CAMPAIGN_INDEX]);
        i += 1;
        result[i] = inactive * (next[COL_PRIORITY_Q32] - current[COL_PRIORITY_Q32]);
        i += 1;
        result[i] = inactive * (next[COL_EMITTED] - current[COL_EMITTED]);
        i += 1;
        result[i] = inactive * (next[COL_STEPS] - current[COL_STEPS]);
        i += 1;

        result[i] = active * (next[COL_PC] - computed_pc);
        i += 1;

        let minus_one = zero - one;
        let stack_delta = op_push
            + op_emit
            + op_cmp_q32 * minus_one
            + op_cmp_u64 * minus_one
            + op_jz * minus_one
            + op_set * minus_one;
        result[i] = active * (next[COL_STACK_DEPTH] - (current[COL_STACK_DEPTH] + stack_delta));
        i += 1;

        let set_value = current[COL_SET_VALUE];
        let next_action = current[COL_ACTION_CODE]
            + op_set * set_is_action * (set_value - current[COL_ACTION_CODE]);
        let next_campaign = current[COL_CAMPAIGN_INDEX]
            + op_set * set_is_campaign * (set_value - current[COL_CAMPAIGN_INDEX]);
        let next_priority = current[COL_PRIORITY_Q32]
            + op_set * set_is_priority * (set_value - current[COL_PRIORITY_Q32]);
        result[i] = active * (next[COL_ACTION_CODE] - next_action);
        i += 1;
        result[i] = active * (next[COL_CAMPAIGN_INDEX] - next_campaign);
        i += 1;
        result[i] = active * (next[COL_PRIORITY_Q32] - next_priority);
        i += 1;

        let emitted_next = emitted + op_emit * (one - emitted);
        result[i] = active * (next[COL_EMITTED] - emitted_next);
        i += 1;

        result[i] = active * (next[COL_STEPS] - (current[COL_STEPS] + one));
    }

    fn get_assertions(&self) -> Vec<Assertion<Self::BaseField>> {
        let last = self.trace_length() - 1;
        vec![
            Assertion::single(
                COL_PC,
                0,
                BaseElement::new(self.pub_inputs.init_pc_u64 as u128),
            ),
            Assertion::single(
                COL_STACK_DEPTH,
                0,
                BaseElement::new(self.pub_inputs.init_stack_depth_u64 as u128),
            ),
            Assertion::single(
                COL_ACTION_CODE,
                0,
                BaseElement::new(self.pub_inputs.init_action_code_u64 as u128),
            ),
            Assertion::single(
                COL_CAMPAIGN_INDEX,
                0,
                BaseElement::new(self.pub_inputs.init_campaign_index_u64 as u128),
            ),
            Assertion::single(
                COL_PRIORITY_Q32,
                0,
                fe_from_i64(self.pub_inputs.init_priority_q32_i64),
            ),
            Assertion::single(COL_STEPS, 0, BaseElement::ZERO),
            Assertion::single(COL_EMITTED, 0, BaseElement::ZERO),
            Assertion::single(
                COL_ACTION_CODE,
                last,
                BaseElement::new(self.pub_inputs.final_action_code_u64 as u128),
            ),
            Assertion::single(
                COL_CAMPAIGN_INDEX,
                last,
                BaseElement::new(self.pub_inputs.final_campaign_index_u64 as u128),
            ),
            Assertion::single(
                COL_PRIORITY_Q32,
                last,
                fe_from_i64(self.pub_inputs.final_priority_q32_i64),
            ),
            Assertion::single(
                COL_STEPS,
                last,
                BaseElement::new(self.pub_inputs.final_steps_u64 as u128),
            ),
        ]
    }
}

struct VmProver {
    options: ProofOptions,
    pub_inputs: PublicInputs,
}

impl VmProver {
    fn new(options: ProofOptions, pub_inputs: PublicInputs) -> Self {
        Self {
            options,
            pub_inputs,
        }
    }
}

impl Prover for VmProver {
    type BaseField = BaseElement;
    type Air = VmAir;
    type Trace = TraceTable<Self::BaseField>;
    type HashFn = Blake3_256<Self::BaseField>;
    type VC = MerkleTree<Self::HashFn>;
    type RandomCoin = DefaultRandomCoin<Self::HashFn>;
    type TraceLde<E: FieldElement<BaseField = Self::BaseField>> =
        DefaultTraceLde<E, Self::HashFn, Self::VC>;
    type ConstraintCommitment<E: FieldElement<BaseField = Self::BaseField>> =
        DefaultConstraintCommitment<E, Self::HashFn, Self::VC>;
    type ConstraintEvaluator<'a, E: FieldElement<BaseField = Self::BaseField>> =
        DefaultConstraintEvaluator<'a, Self::Air, E>;

    fn get_pub_inputs(&self, _trace: &Self::Trace) -> PublicInputs {
        self.pub_inputs.clone()
    }

    fn options(&self) -> &ProofOptions {
        &self.options
    }

    fn new_trace_lde<E: FieldElement<BaseField = Self::BaseField>>(
        &self,
        trace_info: &TraceInfo,
        main_trace: &ColMatrix<Self::BaseField>,
        domain: &StarkDomain<Self::BaseField>,
        partition_option: PartitionOptions,
    ) -> (Self::TraceLde<E>, TracePolyTable<E>) {
        DefaultTraceLde::new(trace_info, main_trace, domain, partition_option)
    }

    fn build_constraint_commitment<E: FieldElement<BaseField = Self::BaseField>>(
        &self,
        composition_poly_trace: CompositionPolyTrace<E>,
        num_constraint_composition_columns: usize,
        domain: &StarkDomain<Self::BaseField>,
        partition_options: PartitionOptions,
    ) -> (Self::ConstraintCommitment<E>, CompositionPoly<E>) {
        DefaultConstraintCommitment::new(
            composition_poly_trace,
            num_constraint_composition_columns,
            domain,
            partition_options,
        )
    }

    fn new_evaluator<'a, E: FieldElement<BaseField = Self::BaseField>>(
        &self,
        air: &'a Self::Air,
        aux_rand_elements: Option<AuxRandElements<E>>,
        composition_coefficients: ConstraintCompositionCoefficients<E>,
    ) -> Self::ConstraintEvaluator<'a, E> {
        DefaultConstraintEvaluator::new(air, aux_rand_elements, composition_coefficients)
    }
}

fn fe_from_i64(value: i64) -> BaseElement {
    if value >= 0 {
        BaseElement::new(value as u128)
    } else {
        BaseElement::ZERO - BaseElement::new((-value) as u128)
    }
}

fn parse_extension(value: &str) -> Result<FieldExtension, String> {
    match value.trim() {
        "None" => Ok(FieldExtension::None),
        "Quadratic" => Ok(FieldExtension::Quadratic),
        "Cubic" => Ok(FieldExtension::Cubic),
        _ => Err("unsupported field_extension".to_string()),
    }
}

fn parse_batching(value: &str) -> Result<BatchingMethod, String> {
    match value.trim() {
        "Linear" => Ok(BatchingMethod::Linear),
        "Algebraic" => Ok(BatchingMethod::Algebraic),
        "Horner" => Ok(BatchingMethod::Horner),
        _ => Err("unsupported batching method".to_string()),
    }
}

fn build_proof_options(input: &ProofOptionsInput) -> Result<ProofOptions, String> {
    let field_extension = parse_extension(&input.field_extension)?;
    let batching_constraints = parse_batching(&input.batching_constraints)?;
    let batching_deep = parse_batching(&input.batching_deep)?;
    let options = ProofOptions::new(
        input.num_queries as usize,
        input.blowup_factor as usize,
        input.grinding_factor,
        field_extension,
        input.fri_folding_factor as usize,
        input.fri_remainder_max_degree as usize,
        batching_constraints,
        batching_deep,
    )
    .with_partitions(input.num_partitions as usize, input.hash_rate as usize);
    Ok(options)
}

fn build_public_inputs(input: &CliInput) -> PublicInputs {
    PublicInputs {
        init_pc_u64: input.initial_state.pc_u32 as u64,
        init_stack_depth_u64: input.initial_state.stack_depth_u32 as u64,
        init_action_code_u64: input.initial_state.action_kind_code_u8 as u64,
        init_campaign_index_u64: input.initial_state.campaign_id_index_u16 as u64,
        init_priority_q32_i64: input.initial_state.priority_q32_i64,
        final_action_code_u64: input.public_outputs.action_kind_code_u8 as u64,
        final_campaign_index_u64: input.public_outputs.campaign_id_index_u16 as u64,
        final_priority_q32_i64: input.public_outputs.priority_q32_i64,
        final_steps_u64: input.public_outputs.steps_executed_u64,
        final_emitted_u64: 1,
        statement_hash_lo_u64: input.statement_hash_lo_u64,
        statement_hash_hi_u64: input.statement_hash_hi_u64,
        budget_hash_lo_u64: input.budget_hash_lo_u64,
        budget_hash_hi_u64: input.budget_hash_hi_u64,
        trace_hash_lo_u64: input.trace_hash_lo_u64,
        trace_hash_hi_u64: input.trace_hash_hi_u64,
        final_stack_hash_lo_u64: input.final_stack_hash_lo_u64,
        final_stack_hash_hi_u64: input.final_stack_hash_hi_u64,
    }
}

fn next_power_of_two_at_least(value: usize) -> usize {
    let min_value = if value < 8 { 8 } else { value };
    min_value.next_power_of_two()
}

fn set_trace_row(
    trace: &mut TraceTable<BaseElement>,
    step: usize,
    state: &(u64, i64, u8, u16, i64, bool, u64),
    row: &(u8, u32, bool, i64, u8),
    active: bool,
) {
    let (pc_u64, stack_depth_i64, action_code, campaign_idx, priority_q32, emitted_b, steps_u64) =
        *state;
    let (op_code_u8, jump_target_u32, cond_b, set_value_i64, set_field_code_u8) = *row;

    let mut selectors = [0u64; 8];
    selectors[op_code_u8 as usize] = 1;

    let set_is_action =
        if op_code_u8 == OPCODE_SET_PLAN_FIELD && set_field_code_u8 == FIELD_ACTION_KIND {
            1u64
        } else {
            0u64
        };
    let set_is_campaign =
        if op_code_u8 == OPCODE_SET_PLAN_FIELD && set_field_code_u8 == FIELD_CAMPAIGN_ID {
            1u64
        } else {
            0u64
        };
    let set_is_priority =
        if op_code_u8 == OPCODE_SET_PLAN_FIELD && set_field_code_u8 == FIELD_PRIORITY_Q32 {
            1u64
        } else {
            0u64
        };

    trace.set(COL_PC, step, BaseElement::new(pc_u64 as u128));
    trace.set(COL_STACK_DEPTH, step, fe_from_i64(stack_depth_i64));
    trace.set(COL_ACTION_CODE, step, BaseElement::new(action_code as u128));
    trace.set(
        COL_CAMPAIGN_INDEX,
        step,
        BaseElement::new(campaign_idx as u128),
    );
    trace.set(COL_PRIORITY_Q32, step, fe_from_i64(priority_q32));
    trace.set(
        COL_EMITTED,
        step,
        BaseElement::new(if emitted_b { 1 } else { 0 }),
    );
    trace.set(COL_STEPS, step, BaseElement::new(steps_u64 as u128));
    trace.set(
        COL_ACTIVE,
        step,
        BaseElement::new(if active { 1 } else { 0 }),
    );
    trace.set(
        COL_OP_NOP,
        step,
        BaseElement::new(selectors[OPCODE_NOP as usize] as u128),
    );
    trace.set(
        COL_OP_PUSH,
        step,
        BaseElement::new(selectors[OPCODE_PUSH_CONST as usize] as u128),
    );
    trace.set(
        COL_OP_CMP_Q32,
        step,
        BaseElement::new(selectors[OPCODE_CMP_Q32 as usize] as u128),
    );
    trace.set(
        COL_OP_CMP_U64,
        step,
        BaseElement::new(selectors[OPCODE_CMP_U64 as usize] as u128),
    );
    trace.set(
        COL_OP_JZ,
        step,
        BaseElement::new(selectors[OPCODE_JZ as usize] as u128),
    );
    trace.set(
        COL_OP_JMP,
        step,
        BaseElement::new(selectors[OPCODE_JMP as usize] as u128),
    );
    trace.set(
        COL_OP_SET,
        step,
        BaseElement::new(selectors[OPCODE_SET_PLAN_FIELD as usize] as u128),
    );
    trace.set(
        COL_OP_EMIT,
        step,
        BaseElement::new(selectors[OPCODE_EMIT_PLAN as usize] as u128),
    );
    trace.set(
        COL_JUMP_TARGET,
        step,
        BaseElement::new(jump_target_u32 as u128),
    );
    trace.set(
        COL_COND_B,
        step,
        BaseElement::new(if cond_b { 1 } else { 0 }),
    );
    trace.set(COL_SET_VALUE, step, fe_from_i64(set_value_i64));
    trace.set(
        COL_SET_IS_ACTION,
        step,
        BaseElement::new(set_is_action as u128),
    );
    trace.set(
        COL_SET_IS_CAMPAIGN,
        step,
        BaseElement::new(set_is_campaign as u128),
    );
    trace.set(
        COL_SET_IS_PRIORITY,
        step,
        BaseElement::new(set_is_priority as u128),
    );
}

fn build_trace(input: &CliInput) -> Result<(TraceTable<BaseElement>, PublicInputs), String> {
    let rows = input
        .vm_rows
        .as_ref()
        .ok_or_else(|| "vm_rows is required for prove mode".to_string())?;
    if rows.is_empty() {
        return Err("vm_rows cannot be empty".to_string());
    }

    let trace_length = next_power_of_two_at_least(rows.len() + 1);
    let mut trace = TraceTable::new(TRACE_WIDTH, trace_length);

    let mut state = (
        input.initial_state.pc_u32 as u64,
        input.initial_state.stack_depth_u32 as i64,
        input.initial_state.action_kind_code_u8,
        input.initial_state.campaign_id_index_u16,
        input.initial_state.priority_q32_i64,
        false,
        0u64,
    );

    for step in 0..(trace_length - 1) {
        if step < rows.len() {
            let row = &rows[step];
            if row.pc_u32 as u64 != state.0 {
                return Err("pc_u32 does not match deterministic transition".to_string());
            }
            if row.stack_before_depth_u32 as i64 != state.1 {
                return Err(
                    "stack_before_depth_u32 does not match deterministic transition".to_string(),
                );
            }
            if row.op_code_u8 > OPCODE_EMIT_PLAN {
                return Err("unsupported op_code_u8 in STARK profile".to_string());
            }
            if row.op_code_u8 == OPCODE_SET_PLAN_FIELD
                && row.set_field_code_u8 != FIELD_ACTION_KIND
                && row.set_field_code_u8 != FIELD_CAMPAIGN_ID
                && row.set_field_code_u8 != FIELD_PRIORITY_Q32
            {
                return Err("unsupported set_field_code_u8".to_string());
            }
            if row.op_code_u8 != OPCODE_SET_PLAN_FIELD && row.set_field_code_u8 != FIELD_UNUSED {
                return Err(
                    "set_field_code_u8 must be 255 for non-SET_PLAN_FIELD opcodes".to_string(),
                );
            }
            let row_tuple = (
                row.op_code_u8,
                row.jump_target_u32,
                row.cond_b,
                row.set_value_i64,
                row.set_field_code_u8,
            );
            set_trace_row(&mut trace, step, &state, &row_tuple, true);

            let base_next_pc = (row.pc_u32 as u64).saturating_add(1);
            let expected_next_pc = match row.op_code_u8 {
                OPCODE_JMP => row.jump_target_u32 as u64,
                OPCODE_JZ => {
                    if row.cond_b {
                        base_next_pc
                    } else {
                        row.jump_target_u32 as u64
                    }
                }
                _ => base_next_pc,
            };
            if row.next_pc_u32 as u64 != expected_next_pc {
                return Err("next_pc_u32 mismatch".to_string());
            }
            let stack_delta = match row.op_code_u8 {
                OPCODE_PUSH_CONST => 1i64,
                OPCODE_EMIT_PLAN => 1i64,
                OPCODE_CMP_Q32 | OPCODE_CMP_U64 | OPCODE_JZ | OPCODE_SET_PLAN_FIELD => -1i64,
                _ => 0i64,
            };
            let expected_stack_after = state.1 + stack_delta;
            if row.stack_after_depth_u32 as i64 != expected_stack_after {
                return Err("stack_after_depth_u32 mismatch".to_string());
            }

            let mut next_state = state;
            next_state.0 = expected_next_pc;
            next_state.1 = expected_stack_after;
            if row.op_code_u8 == OPCODE_SET_PLAN_FIELD {
                match row.set_field_code_u8 {
                    FIELD_ACTION_KIND => {
                        if row.set_value_i64 < 0 || row.set_value_i64 > 255 {
                            return Err("action code out of range".to_string());
                        }
                        next_state.2 = row.set_value_i64 as u8;
                    }
                    FIELD_CAMPAIGN_ID => {
                        if row.set_value_i64 < 0 || row.set_value_i64 > 65535 {
                            return Err("campaign index out of range".to_string());
                        }
                        next_state.3 = row.set_value_i64 as u16;
                    }
                    FIELD_PRIORITY_Q32 => {
                        next_state.4 = row.set_value_i64;
                    }
                    _ => return Err("unsupported set field".to_string()),
                }
            }
            if row.op_code_u8 == OPCODE_EMIT_PLAN {
                next_state.5 = true;
            }
            next_state.6 = next_state.6.saturating_add(1);
            state = next_state;
        } else {
            let row_tuple = (OPCODE_NOP, state.0 as u32, false, 0i64, FIELD_UNUSED);
            set_trace_row(&mut trace, step, &state, &row_tuple, false);
        }
    }

    let last_row_tuple = (OPCODE_NOP, state.0 as u32, false, 0i64, FIELD_UNUSED);
    set_trace_row(&mut trace, trace_length - 1, &state, &last_row_tuple, false);

    if state.2 != input.public_outputs.action_kind_code_u8 {
        return Err("final action_kind_code_u8 mismatch".to_string());
    }
    if state.3 != input.public_outputs.campaign_id_index_u16 {
        return Err("final campaign_id_index_u16 mismatch".to_string());
    }
    if state.4 != input.public_outputs.priority_q32_i64 {
        return Err("final priority_q32_i64 mismatch".to_string());
    }
    if state.6 != input.public_outputs.steps_executed_u64 {
        return Err("final steps_executed_u64 mismatch".to_string());
    }
    if !state.5 {
        return Err("trace must terminate with EMIT_PLAN for STARK profile".to_string());
    }

    Ok((trace, build_public_inputs(input)))
}

fn parse_args() -> Result<BTreeMap<String, String>, String> {
    let args: Vec<String> = env::args().collect();
    let mut out: BTreeMap<String, String> = BTreeMap::new();
    let mut i = 1usize;
    while i < args.len() {
        let key = args[i].clone();
        if !key.starts_with("--") {
            return Err(format!("invalid flag: {key}"));
        }
        if i + 1 >= args.len() {
            return Err(format!("missing value for {key}"));
        }
        out.insert(key, args[i + 1].clone());
        i += 2;
    }
    Ok(out)
}

fn require_arg(args: &BTreeMap<String, String>, key: &str) -> Result<String, String> {
    args.get(key)
        .map(|v| v.to_string())
        .ok_or_else(|| format!("missing {key}"))
}

fn write_receipt(
    path: &PathBuf,
    mode: &str,
    status: &str,
    reason: &str,
    proof_len: u64,
) -> Result<(), String> {
    let payload = CliReceipt {
        schema_version: "policy_vm_stark_rs_receipt_v1".to_string(),
        mode: mode.to_string(),
        status: status.to_string(),
        reason: reason.to_string(),
        proof_bytes_len_u64: proof_len,
    };
    let encoded =
        serde_json::to_vec(&payload).map_err(|err| format!("receipt encode failed: {err}"))?;
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|err| format!("receipt parent mkdir failed: {err}"))?;
    }
    fs::write(path, encoded).map_err(|err| format!("receipt write failed: {err}"))
}

fn run() -> Result<(), String> {
    let args = parse_args()?;
    let mode = require_arg(&args, "--mode")?;
    let input_path = PathBuf::from(require_arg(&args, "--input-json")?);
    let input_payload =
        fs::read_to_string(&input_path).map_err(|err| format!("input read failed: {err}"))?;
    let input: CliInput = serde_json::from_str(&input_payload)
        .map_err(|err| format!("input decode failed: {err}"))?;
    if input.schema_version != "policy_vm_stark_cli_input_v1" {
        return Err("unsupported schema_version".to_string());
    }
    let options = build_proof_options(&input.proof_options)?;

    if mode == "prove" {
        let proof_out = PathBuf::from(require_arg(&args, "--proof-out")?);
        let receipt_out = PathBuf::from(require_arg(&args, "--receipt-out")?);
        let (trace, pub_inputs) = build_trace(&input)?;
        let prover = VmProver::new(options.clone(), pub_inputs.clone());
        let proof = prover
            .prove(trace)
            .map_err(|err| format!("proof generation failed: {err}"))?;
        let proof_bytes = proof.to_bytes();
        if let Some(parent) = proof_out.parent() {
            fs::create_dir_all(parent)
                .map_err(|err| format!("proof parent mkdir failed: {err}"))?;
        }
        fs::write(&proof_out, &proof_bytes).map_err(|err| format!("proof write failed: {err}"))?;
        let acceptable = AcceptableOptions::OptionSet(vec![options]);
        verify::<
            VmAir,
            Blake3_256<BaseElement>,
            DefaultRandomCoin<Blake3_256<BaseElement>>,
            MerkleTree<Blake3_256<BaseElement>>,
        >(proof, pub_inputs, &acceptable)
        .map_err(|err| format!("self-verify failed: {err}"))?;
        write_receipt(
            &receipt_out,
            "prove",
            "PASS",
            "OK",
            proof_bytes.len() as u64,
        )?;
        return Ok(());
    }

    if mode == "verify" {
        let proof_in = PathBuf::from(require_arg(&args, "--proof-in")?);
        let receipt_out = PathBuf::from(require_arg(&args, "--receipt-out")?);
        let proof_bytes = fs::read(&proof_in).map_err(|err| format!("proof read failed: {err}"))?;
        let proof =
            Proof::from_bytes(&proof_bytes).map_err(|err| format!("proof decode failed: {err}"))?;
        let pub_inputs = build_public_inputs(&input);
        let acceptable = AcceptableOptions::OptionSet(vec![options]);
        verify::<
            VmAir,
            Blake3_256<BaseElement>,
            DefaultRandomCoin<Blake3_256<BaseElement>>,
            MerkleTree<Blake3_256<BaseElement>>,
        >(proof, pub_inputs, &acceptable)
        .map_err(|err| format!("proof verification failed: {err}"))?;
        write_receipt(
            &receipt_out,
            "verify",
            "PASS",
            "OK",
            proof_bytes.len() as u64,
        )?;
        return Ok(());
    }

    Err("unsupported --mode".to_string())
}

fn main() {
    if let Err(err) = run() {
        eprintln!("{err}");
        std::process::exit(1);
    }
}
