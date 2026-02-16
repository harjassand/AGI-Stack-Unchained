/--
SAS-System v14.0 Lean preamble.
This models the pinned workmeter target and the loop-summary candidate semantics.
-/

structure WorkmeterJob where
  dim : Nat
  norm_pow : Nat
  pair_terms : Nat
  hooke_terms : Nat
  deriving Repr, DecidableEq

structure WorkmeterOut where
  sqrt_calls : Nat
  div_calls : Nat
  pair_terms_evaluated : Nat
  work_cost_total : Nat
  deriving Repr, DecidableEq

structure IR where
  candidate_id : String
  ir_sha256 : String
  deriving Repr, DecidableEq

def loopAdd : Nat -> Nat -> Nat -> Nat
  | 0, _, acc => acc
  | Nat.succ n, c, acc => loopAdd n c (acc + c)

theorem loopAdd_eq (n c acc : Nat) :
    loopAdd n c acc = acc + n * c := by
  induction n generalizing acc with
  | zero =>
      simp [loopAdd]
  | succ n ih =>
      simp [loopAdd, ih, Nat.succ_mul, Nat.add_assoc, Nat.add_left_comm, Nat.add_comm]

def ref_sqrt_calls (j : WorkmeterJob) : Nat :=
  let s0 := 0
  let s1 := loopAdd j.pair_terms 1 s0
  let s2 := loopAdd j.hooke_terms 1 s1
  s2

def ref_div_calls (j : WorkmeterJob) : Nat :=
  let d0 := 0
  let d1 := loopAdd (j.pair_terms * j.dim) 1 d0
  let d2 := loopAdd (j.hooke_terms * j.dim) 1 d1
  d2

def ref_pair_terms_eval (j : WorkmeterJob) : Nat :=
  let p0 := 0
  let p1 := loopAdd j.pair_terms 1 p0
  let p2 := loopAdd j.hooke_terms 1 p1
  p2

def ref_mul_calls (j : WorkmeterJob) : Nat :=
  let m0 := 0
  let m1 := loopAdd (j.pair_terms * j.dim) 1 m0
  let m2 := if 1 < j.norm_pow then loopAdd (j.pair_terms * (j.norm_pow - 1)) 1 m1 else m1
  let m3 := loopAdd (j.pair_terms * j.dim) 1 m2
  let m4 := loopAdd (j.hooke_terms * j.dim) 1 m3
  let m5 := if 1 < (2 : Nat) then loopAdd (j.hooke_terms * ((2 : Nat) - 1)) 1 m4 else m4
  let m6 := loopAdd (j.hooke_terms * j.dim) 1 m5
  m6

def ref_add_calls (j : WorkmeterJob) : Nat :=
  let a0 := 0
  let a1 := loopAdd (j.pair_terms * j.dim) 1 a0
  let a2 := if 0 < j.dim then loopAdd (j.pair_terms * (j.dim - 1)) 1 a1 else a1
  let a3 := loopAdd (j.pair_terms * j.dim) 1 a2
  let a4 := loopAdd (j.hooke_terms * j.dim) 1 a3
  let a5 := if 0 < j.dim then loopAdd (j.hooke_terms * (j.dim - 1)) 1 a4 else a4
  let a6 := loopAdd (j.hooke_terms * j.dim) 1 a5
  a6

def cand_sqrt_calls (j : WorkmeterJob) : Nat :=
  0 + j.pair_terms * 1 + j.hooke_terms * 1

def cand_div_calls (j : WorkmeterJob) : Nat :=
  0 + (j.pair_terms * j.dim) * 1 + (j.hooke_terms * j.dim) * 1

def cand_pair_terms_eval (j : WorkmeterJob) : Nat :=
  0 + j.pair_terms * 1 + j.hooke_terms * 1

def cand_mul_calls (j : WorkmeterJob) : Nat :=
  let m1 := 0 + (j.pair_terms * j.dim) * 1
  let m2 := if 1 < j.norm_pow then m1 + (j.pair_terms * (j.norm_pow - 1)) * 1 else m1
  let m3 := m2 + (j.pair_terms * j.dim) * 1
  let m4 := m3 + (j.hooke_terms * j.dim) * 1
  let m5 := if 1 < (2 : Nat) then m4 + (j.hooke_terms * ((2 : Nat) - 1)) * 1 else m4
  let m6 := m5 + (j.hooke_terms * j.dim) * 1
  m6

def cand_add_calls (j : WorkmeterJob) : Nat :=
  let a1 := 0 + (j.pair_terms * j.dim) * 1
  let a2 := if 0 < j.dim then a1 + (j.pair_terms * (j.dim - 1)) * 1 else a1
  let a3 := a2 + (j.pair_terms * j.dim) * 1
  let a4 := a3 + (j.hooke_terms * j.dim) * 1
  let a5 := if 0 < j.dim then a4 + (j.hooke_terms * (j.dim - 1)) * 1 else a4
  let a6 := a5 + (j.hooke_terms * j.dim) * 1
  a6

def eval_ref (j : WorkmeterJob) : WorkmeterOut :=
  let sqrt_calls := ref_sqrt_calls j
  let div_calls := ref_div_calls j
  let pair_terms_evaluated := ref_pair_terms_eval j
  let mul_calls := ref_mul_calls j
  let add_calls := ref_add_calls j
  let work_cost_total := 50 * sqrt_calls + 20 * div_calls + 3 * mul_calls + add_calls + 5 * pair_terms_evaluated
  {
    sqrt_calls := sqrt_calls
    div_calls := div_calls
    pair_terms_evaluated := pair_terms_evaluated
    work_cost_total := work_cost_total
  }

def eval_cand (j : WorkmeterJob) : WorkmeterOut :=
  let sqrt_calls := cand_sqrt_calls j
  let div_calls := cand_div_calls j
  let pair_terms_evaluated := cand_pair_terms_eval j
  let mul_calls := cand_mul_calls j
  let add_calls := cand_add_calls j
  let work_cost_total := 50 * sqrt_calls + 20 * div_calls + 3 * mul_calls + add_calls + 5 * pair_terms_evaluated
  {
    sqrt_calls := sqrt_calls
    div_calls := div_calls
    pair_terms_evaluated := pair_terms_evaluated
    work_cost_total := work_cost_total
  }

def eval_ir (ir : IR) (j : WorkmeterJob) : WorkmeterOut :=
  if ir.candidate_id = "LOOP_SUMMARY_RS_V1" then
    eval_cand j
  else
    eval_ref j

def ref_ir : IR :=
  {
    candidate_id := "DIRECT_PORT_RS_V1"
    ir_sha256 := "sha256:f9412ce5f2db6a16d5c07e39774bd48420084e429aac0d4db4311da8a348b4ae"
  }

def cand_ir : IR :=
  {
    candidate_id := "LOOP_SUMMARY_RS_V1"
    ir_sha256 := "sha256:c278bd05829ad80f7caed99be72c276d87f374293e15efd6604d2274bb9ec25c"
  }

theorem sqrt_eq (j : WorkmeterJob) : ref_sqrt_calls j = cand_sqrt_calls j := by
  simp [ref_sqrt_calls, cand_sqrt_calls, loopAdd_eq, Nat.add_assoc, Nat.add_comm, Nat.add_left_comm]

theorem div_eq (j : WorkmeterJob) : ref_div_calls j = cand_div_calls j := by
  simp [ref_div_calls, cand_div_calls, loopAdd_eq, Nat.add_assoc, Nat.add_comm, Nat.add_left_comm]

theorem pair_eq (j : WorkmeterJob) : ref_pair_terms_eval j = cand_pair_terms_eval j := by
  simp [ref_pair_terms_eval, cand_pair_terms_eval, loopAdd_eq, Nat.add_assoc, Nat.add_comm, Nat.add_left_comm]

theorem mul_eq (j : WorkmeterJob) : ref_mul_calls j = cand_mul_calls j := by
  simp [ref_mul_calls, cand_mul_calls, loopAdd_eq, Nat.add_assoc, Nat.add_comm, Nat.add_left_comm]

theorem add_eq (j : WorkmeterJob) : ref_add_calls j = cand_add_calls j := by
  simp [ref_add_calls, cand_add_calls, loopAdd_eq, Nat.add_assoc, Nat.add_comm, Nat.add_left_comm]

theorem cand_eq_ref : ∀ j, eval_ir cand_ir j = eval_ir ref_ir j := by
  intro j
  have hsqrt : ref_sqrt_calls j = cand_sqrt_calls j := sqrt_eq j
  have hdiv : ref_div_calls j = cand_div_calls j := div_eq j
  have hpair : ref_pair_terms_eval j = cand_pair_terms_eval j := pair_eq j
  have hmul : ref_mul_calls j = cand_mul_calls j := mul_eq j
  have hadd : ref_add_calls j = cand_add_calls j := add_eq j
  simp [eval_ir, cand_ir, ref_ir, eval_cand, eval_ref, hsqrt, hdiv, hpair, hmul, hadd]
