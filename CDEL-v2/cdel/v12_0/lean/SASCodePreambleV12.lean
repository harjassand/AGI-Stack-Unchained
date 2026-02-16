import Std

def SASCodeSorted (xs : List Nat) : Prop :=
  List.Pairwise (fun a b => a <= b) xs

def AllLe (m : Nat) (xs : List Nat) : Prop :=
  ∀ a ∈ xs, a <= m

def AllGe (m : Nat) (xs : List Nat) : Prop :=
  ∀ a ∈ xs, m <= a


def bubblePass : List Nat -> List Nat
| [] => []
| [x] => [x]
| x :: y :: xs =>
    if x <= y then x :: bubblePass (y :: xs) else y :: bubblePass (x :: xs)


def bubbleIter : Nat -> List Nat -> List Nat
| Nat.zero, xs => xs
| Nat.succ n, xs => bubbleIter n (bubblePass xs)


def bubbleSort (xs : List Nat) : List Nat :=
  bubbleIter xs.length xs


/-- Auxiliary: returns the bubble pass without the final maximum and the maximum. -/
def bubblePassAux : List Nat -> List Nat × Nat
| [] => ([], 0)
| [x] => ([], x)
| x :: y :: xs =>
    if x <= y then
      let (ys, m) := bubblePassAux (y :: xs)
      (x :: ys, m)
    else
      let (ys, m) := bubblePassAux (x :: xs)
      (y :: ys, m)


/-- Split a list into alternating elements. -/
def split : List Nat -> List Nat × List Nat
| [] => ([], [])
| [x] => ([x], [])
| x :: y :: xs =>
    let (l, r) := split xs
    (x :: l, y :: r)


def merge : List Nat -> List Nat -> List Nat
| [], ys => ys
| xs, [] => xs
| x :: xs, y :: ys =>
    if x <= y then x :: merge xs (y :: ys) else y :: merge (x :: xs) ys

theorem split_length_le : ∀ xs,
    let (l, r) := split xs
    l.length <= xs.length ∧ r.length <= xs.length
| [] => by simp [split]
| [x] => by simp [split]
| x :: y :: xs => by
    cases hrec : split xs with
    | mk l r =>
      have ih := split_length_le xs
      have ih' : l.length <= xs.length ∧ r.length <= xs.length := by
        simpa [hrec] using ih
      have hl : l.length <= xs.length + 1 := Nat.le_trans ih'.1 (Nat.le_succ _)
      have hr : r.length <= xs.length + 1 := Nat.le_trans ih'.2 (Nat.le_succ _)
      simp [split, hrec]
      exact ⟨hl, hr⟩


theorem split_length_lt : ∀ xs, 2 <= xs.length ->
    let (l, r) := split xs
    l.length < xs.length ∧ r.length < xs.length
| [], h => by cases h
| [x], h => by
    cases h with
    | step h1 =>
        cases h1
| x :: y :: xs, _ => by
    cases hrec : split xs with
    | mk l r =>
      have ih := split_length_le xs
      have ih' : l.length <= xs.length ∧ r.length <= xs.length := by
        simpa [hrec] using ih
      have hl : l.length < xs.length + 1 := Nat.lt_succ_of_le ih'.1
      have hr : r.length < xs.length + 1 := Nat.lt_succ_of_le ih'.2
      simp [split, hrec]
      exact ⟨hl, hr⟩


theorem split_length_lt_full : ∀ x y xs l r,
    split (x :: y :: xs) = (l, r) ->
    l.length < (x :: y :: xs).length ∧ r.length < (x :: y :: xs).length
| x, y, xs, l, r, hsplit => by
    cases hrec : split xs with
    | mk l' r' =>
      have hle := split_length_le xs
      have hle' : l'.length <= xs.length ∧ r'.length <= xs.length := by
        simpa [hrec] using hle
      have hsplit' : (x :: l', y :: r') = (l, r) := by
        simpa [split, hrec] using hsplit
      have hl_eq : l = x :: l' := by
        have := congrArg Prod.fst hsplit'
        simpa using this.symm
      have hr_eq : r = y :: r' := by
        have := congrArg Prod.snd hsplit'
        simpa using this.symm
      have hl_le : l.length <= xs.length + 1 := by
        have : l'.length + 1 <= xs.length + 1 := Nat.succ_le_succ hle'.1
        simpa [hl_eq] using this
      have hr_le : r.length <= xs.length + 1 := by
        have : r'.length + 1 <= xs.length + 1 := Nat.succ_le_succ hle'.2
        simpa [hr_eq] using this
      have hl_lt : l.length < (x :: y :: xs).length := by
        have hlt : l.length < xs.length + 1 + 1 := Nat.lt_succ_of_le hl_le
        simpa using hlt
      have hr_lt : r.length < (x :: y :: xs).length := by
        have hlt : r.length < xs.length + 1 + 1 := Nat.lt_succ_of_le hr_le
        simpa using hlt
      exact ⟨hl_lt, hr_lt⟩




def mergeSort (xs : List Nat) : List Nat :=
  match xs with
  | [] => []
  | [x] => [x]
  | x :: y :: xs =>
      match hsplit : split (x :: y :: xs) with
      | (l, r) => merge (mergeSort l) (mergeSort r)
termination_by
  xs.length

decreasing_by
  all_goals
    have hlt := split_length_lt (x :: y :: xs) (by simp)
    have hlt' : l.length < (x :: y :: xs).length ∧ r.length < (x :: y :: xs).length := by
      simpa [hsplit] using hlt
    first
    | exact hlt'.1
    | exact hlt'.2


def sort_ref (xs : List Nat) : List Nat := bubbleSort xs

def sort_cand (xs : List Nat) : List Nat := mergeSort xs


theorem allLe_perm {m : Nat} {xs ys : List Nat} (h : AllLe m xs) (p : List.Perm ys xs) :
    AllLe m ys := by
  intro a ha
  have : a ∈ xs := (p.mem_iff).1 ha
  exact h a this


theorem allLe_append_left {m : Nat} {xs ys : List Nat} (h : AllLe m (xs ++ ys)) : AllLe m xs := by
  intro a ha
  exact h a (by simp [ha])


theorem allLe_cons {m a : Nat} {xs : List Nat} : AllLe m (a :: xs) ↔ a <= m ∧ AllLe m xs := by
  constructor
  · intro h
    have ha : a <= m := h a (by simp)
    have hxs : AllLe m xs := by
      intro b hb
      exact h b (by simp [hb])
    exact ⟨ha, hxs⟩
  · rintro ⟨ha, hxs⟩ b hb
    simp at hb
    rcases hb with rfl | hb
    · exact ha
    · exact hxs b hb


theorem sorted_tail {x : Nat} {xs : List Nat} (h : SASCodeSorted (x :: xs)) : SASCodeSorted xs := by
  have hpair : List.Pairwise (fun a b => a <= b) (x :: xs) := by
    dsimp [SASCodeSorted] at h
    exact h
  have htail : List.Pairwise (fun a b => a <= b) xs := List.Pairwise.tail hpair
  dsimp [SASCodeSorted]
  exact htail


theorem sorted_head_le {x : Nat} {xs : List Nat} (h : SASCodeSorted (x :: xs)) : AllGe x xs := by
  intro a ha
  have hpair : List.Pairwise (fun a b => a <= b) (x :: xs) := by
    dsimp [SASCodeSorted] at h
    exact h
  exact List.rel_of_pairwise_cons hpair ha


theorem bubblePassAux_len : ∀ xs, xs ≠ [] ->
    let res := bubblePassAux xs
    res.1.length + 1 = xs.length
| [], h => by cases h rfl
| [x], _ => by
    simp [bubblePassAux]
| x :: y :: xs, _ => by
    by_cases hxy : x <= y
    · have hne : (y :: xs) ≠ [] := by simp
      have ih := bubblePassAux_len (y :: xs) hne
      cases hrec : bubblePassAux (y :: xs) with
      | mk ys m =>
        have ih' : ys.length + 1 = (y :: xs).length := by
          simpa [hrec] using ih
        simp [bubblePassAux, hxy, hrec, ih']
    · have hne : (x :: xs) ≠ [] := by simp
      have ih := bubblePassAux_len (x :: xs) hne
      cases hrec : bubblePassAux (x :: xs) with
      | mk ys m =>
        have ih' : ys.length + 1 = (x :: xs).length := by
          simpa [hrec] using ih
        simp [bubblePassAux, hxy, hrec, ih']


theorem bubblePassAux_allLe : ∀ xs, xs ≠ [] ->
    let res := bubblePassAux xs
    AllLe res.2 xs
| [], h => by cases h rfl
| [x], _ => by
    simp [bubblePassAux, AllLe]
| x :: y :: xs, _ => by
    by_cases hxy : x <= y
    · have hne : (y :: xs) ≠ [] := by simp
      have ih := bubblePassAux_allLe (y :: xs) hne
      cases hrec : bubblePassAux (y :: xs) with
      | mk ys m =>
        have ih' : AllLe m (y :: xs) := by
          simpa [hrec] using ih
        have hy : y <= m := ih' y (by simp)
        have hx : x <= m := Nat.le_trans hxy hy
        have hgoal : AllLe m (x :: y :: xs) := by
          intro a ha
          have ha' : a = x ∨ a ∈ y :: xs := List.mem_cons.1 ha
          cases ha' with
          | inl hax =>
              subst hax
              exact hx
          | inr hayxs =>
              exact ih' a hayxs
        simpa [bubblePassAux, hxy, hrec] using hgoal
    · have hne : (x :: xs) ≠ [] := by simp
      have ih := bubblePassAux_allLe (x :: xs) hne
      cases hrec : bubblePassAux (x :: xs) with
      | mk ys m =>
        have ih' : AllLe m (x :: xs) := by
          simpa [hrec] using ih
        have hx : x <= m := ih' x (by simp)
        have hy : y <= m := Nat.le_trans (Nat.le_of_not_ge hxy) hx
        have hgoal : AllLe m (x :: y :: xs) := by
          intro a ha
          have ha' : a = x ∨ a ∈ y :: xs := List.mem_cons.1 ha
          cases ha' with
          | inl hax =>
              subst hax
              exact hx
          | inr hayxs =>
              have ha'' : a = y ∨ a ∈ xs := List.mem_cons.1 hayxs
              cases ha'' with
              | inl hay =>
                  subst hay
                  exact hy
              | inr haxs =>
                  exact ih' a (by simp [haxs])
        simpa [bubblePassAux, hxy, hrec] using hgoal


theorem bubblePass_eq_aux : ∀ xs, xs ≠ [] ->
    bubblePass xs = (bubblePassAux xs).1 ++ [ (bubblePassAux xs).2 ]
| [], h => by cases h rfl
| [x], _ => by
    simp [bubblePass, bubblePassAux]
| x :: y :: xs, _ => by
    by_cases hxy : x <= y
    · have hne : (y :: xs) ≠ [] := by simp
      have ih := bubblePass_eq_aux (y :: xs) hne
      simp [bubblePass, bubblePassAux, hxy, ih]
    · have hne : (x :: xs) ≠ [] := by simp
      have ih := bubblePass_eq_aux (x :: xs) hne
      simp [bubblePass, bubblePassAux, hxy, ih]


theorem bubblePassAux_perm : ∀ xs, xs ≠ [] ->
    List.Perm ((bubblePassAux xs).1 ++ [ (bubblePassAux xs).2 ]) xs
| [], h => by cases h rfl
| [x], _ => by
    simp [bubblePassAux]
| x :: y :: xs, _ => by
    by_cases hxy : x <= y
    · have hne : (y :: xs) ≠ [] := by simp
      have ih := bubblePassAux_perm (y :: xs) hne
      cases hrec : bubblePassAux (y :: xs) with
      | mk ys m =>
        have ih' : List.Perm (ys ++ [m]) (y :: xs) := by
          simpa [hrec] using ih
        have ih'' : List.Perm (x :: (ys ++ [m])) (x :: y :: xs) := ih'.cons x
        simpa [bubblePassAux, hxy, hrec] using ih''
    · have hne : (x :: xs) ≠ [] := by simp
      have ih := bubblePassAux_perm (x :: xs) hne
      cases hrec : bubblePassAux (x :: xs) with
      | mk ys m =>
        have ih' : List.Perm (ys ++ [m]) (x :: xs) := by
          simpa [hrec] using ih
        have ih'' : List.Perm (y :: (ys ++ [m])) (y :: x :: xs) := ih'.cons y
        have swap : List.Perm (y :: x :: xs) (x :: y :: xs) := by
          simpa using (List.Perm.swap x y xs)
        have result : List.Perm (y :: (ys ++ [m])) (x :: y :: xs) := ih''.trans swap
        simpa [bubblePassAux, hxy, hrec] using result


theorem bubblePass_perm (xs : List Nat) : List.Perm (bubblePass xs) xs := by
  cases xs with
  | nil => simp [bubblePass]
  | cons x xs =>
      cases xs with
      | nil => simp [bubblePass]
      | cons y ys =>
          have hne : (x :: y :: ys) ≠ [] := by simp
          have hp := bubblePassAux_perm (x :: y :: ys) hne
          have hEq := bubblePass_eq_aux (x :: y :: ys) hne
          simpa [hEq] using hp


theorem bubbleIter_perm : ∀ n xs, List.Perm (bubbleIter n xs) xs
| Nat.zero, xs => by simp [bubbleIter]
| Nat.succ n, xs => by
    have hp : List.Perm (bubblePass xs) xs := bubblePass_perm xs
    have ih : List.Perm (bubbleIter n (bubblePass xs)) (bubblePass xs) := bubbleIter_perm n (bubblePass xs)
    exact ih.trans hp


theorem bubblePass_append_max : ∀ ys m, AllLe m ys -> bubblePass (ys ++ [m]) = bubblePass ys ++ [m]
| [], m, _ => by simp [bubblePass]
| [x], m, h => by
    have hx : x <= m := h x (by simp)
    simp [bubblePass, hx]
| x :: y :: xs, m, h => by
    have hx : x <= m := (allLe_cons.mp h).1
    have htail : AllLe m (y :: xs) := (allLe_cons.mp h).2
    by_cases hxy : x <= y
    · have ih := bubblePass_append_max (y :: xs) m htail
      simpa [bubblePass, hxy, List.cons_append] using ih
    · have htail2 : AllLe m (x :: xs) := by
        intro a ha
        simp at ha
        cases ha with
        | inl hax =>
            subst hax
            exact hx
        | inr haxs =>
            exact htail a (by simp [haxs])
      have ih := bubblePass_append_max (x :: xs) m htail2
      simpa [bubblePass, hxy, List.cons_append] using ih


theorem bubbleIter_append_max : ∀ n ys m, AllLe m ys -> bubbleIter n (ys ++ [m]) = bubbleIter n ys ++ [m]
| Nat.zero, ys, m, _ => by simp [bubbleIter]
| Nat.succ n, ys, m, h => by
    have hpass := bubblePass_append_max ys m h
    have hperm : List.Perm (bubblePass ys) ys := bubblePass_perm ys
    have h_all : AllLe m (bubblePass ys) := allLe_perm h hperm
    have ih := bubbleIter_append_max n (bubblePass ys) m h_all
    simp [bubbleIter, hpass, ih]


theorem bubble_perm (xs : List Nat) : List.Perm (bubbleSort xs) xs := by
  simpa [bubbleSort] using (bubbleIter_perm xs.length xs)


theorem bubble_sorted_len : ∀ n xs, xs.length = n -> SASCodeSorted (bubbleIter n xs)
| 0, xs, hlen => by
    have : xs = [] := by
      cases xs with
      | nil => rfl
      | cons a l => simp at hlen
    subst this
    simp [bubbleIter, SASCodeSorted]
| 1, xs, hlen => by
    cases xs with
    | nil => simp at hlen
    | cons a l =>
        cases l with
        | nil => simp [bubbleIter, bubblePass, SASCodeSorted]
        | cons b l =>
            simp at hlen
| Nat.succ (Nat.succ n), xs, hlen => by
    cases xs with
    | nil => simp at hlen
    | cons a xs =>
        cases xs with
        | nil => simp at hlen
        | cons b xs =>
            have hne : (a :: b :: xs) ≠ [] := by simp
            cases hrec : bubblePassAux (a :: b :: xs) with
            | mk ys m =>
                have hlen_aux := bubblePassAux_len (a :: b :: xs) hne
                have hlen_aux' : ys.length + 1 = (a :: b :: xs).length := by
                  simpa [hrec] using hlen_aux
                have hlen_ys : ys.length = Nat.succ n := by
                  have hlen_aux'' : Nat.succ ys.length = Nat.succ (Nat.succ n) := by
                    simpa [Nat.succ_eq_add_one, hlen] using hlen_aux'
                  exact Nat.succ.inj hlen_aux''
                have h_all : AllLe m (a :: b :: xs) := by
                  have h := bubblePassAux_allLe (a :: b :: xs) hne
                  simpa [hrec] using h
                have h_perm : List.Perm (ys ++ [m]) (a :: b :: xs) := by
                  have h := bubblePassAux_perm (a :: b :: xs) hne
                  simpa [hrec] using h
                have h_all_out : AllLe m (ys ++ [m]) := allLe_perm h_all h_perm
                have h_all_ys : AllLe m ys := allLe_append_left h_all_out
                have hpass_eq : bubblePass (a :: b :: xs) = ys ++ [m] := by
                  have h := bubblePass_eq_aux (a :: b :: xs) hne
                  simpa [hrec] using h
                have h_iter : bubbleIter (Nat.succ (Nat.succ n)) (a :: b :: xs) =
                    bubbleIter (Nat.succ n) ys ++ [m] := by
                  simp [bubbleIter, hpass_eq]
                  have h := bubbleIter_append_max (Nat.succ n) ys m h_all_ys
                  simpa using h
                have hsorted_ys : SASCodeSorted (bubbleIter (Nat.succ n) ys) :=
                  bubble_sorted_len (Nat.succ n) ys (by simpa [hlen_ys])
                have h_all_sorted : AllLe m (bubbleIter (Nat.succ n) ys) := by
                  have hperm_iter : List.Perm (bubbleIter (Nat.succ n) ys) ys :=
                    bubbleIter_perm (Nat.succ n) ys
                  exact allLe_perm h_all_ys hperm_iter
                have hpair : List.Pairwise (fun a b => a <= b) (bubbleIter (Nat.succ n) ys ++ [m]) := by
                  apply (List.pairwise_append (R:=fun a b => a <= b)).2
                  refine ⟨?h1, ?h2, ?hcross⟩
                  · simpa [SASCodeSorted] using hsorted_ys
                  · simp
                  · intro a ha b hb
                    simp at hb
                    rcases hb with rfl
                    exact h_all_sorted a ha
                have hsorted : SASCodeSorted (bubbleIter (Nat.succ n) ys ++ [m]) := by
                  simpa [SASCodeSorted] using hpair
                simpa [h_iter] using hsorted


theorem bubble_sorted (xs : List Nat) : SASCodeSorted (bubbleSort xs) := by
  have := bubble_sorted_len xs.length xs rfl
  simpa [bubbleSort] using this


/-- merge permutes its inputs. -/
theorem merge_perm_aux : ∀ xs ys, List.Perm (merge xs ys) (xs ++ ys)
| [], ys => by
    simp [merge]
| xs, [] => by
    cases xs <;> simp [merge]
| x :: xs, y :: ys => by
    by_cases hxy : x <= y
    · have ih := merge_perm_aux xs (y :: ys)
      have ih' : List.Perm (x :: merge xs (y :: ys)) (x :: (xs ++ y :: ys)) := ih.cons x
      simpa [merge, hxy, List.cons_append] using ih'
    · have ih := merge_perm_aux (x :: xs) ys
      have ih' : List.Perm (y :: merge (x :: xs) ys) (y :: ((x :: xs) ++ ys)) := ih.cons y
      have pm : List.Perm (y :: ((x :: xs) ++ ys)) ((x :: xs) ++ y :: ys) := by
        have pm' : List.Perm ((x :: xs) ++ y :: ys) (y :: (x :: xs ++ ys)) := by
          simpa using (List.perm_middle (l₁:=x :: xs) (a:=y) (l₂:=ys))
        exact pm'.symm
      have result := ih'.trans pm
      simpa [merge, hxy] using result


theorem merge_pairwise : ∀ (xs ys : List Nat), SASCodeSorted xs -> SASCodeSorted ys -> SASCodeSorted (merge xs ys)
| [], ys, _, hys => by
    dsimp [SASCodeSorted] at hys
    dsimp [SASCodeSorted]
    simpa [merge] using hys
| xs, [], hxs, _ => by
    cases xs with
    | nil =>
        dsimp [SASCodeSorted] at hxs
        dsimp [SASCodeSorted]
        simpa [merge] using hxs
    | cons x xs =>
        dsimp [SASCodeSorted] at hxs
        dsimp [SASCodeSorted]
        simpa [merge] using hxs
| x :: xs, y :: ys, hxs, hys => by
    by_cases hxy : x <= y
    · have hxs_tail : SASCodeSorted xs := sorted_tail hxs
      have hx_le_xs : AllGe x xs := sorted_head_le hxs
      have hy_le_ys : AllGe y ys := sorted_head_le hys
      have hx_le_merge : AllGe x (merge xs (y :: ys)) := by
        intro z hz
        have hz' : z ∈ xs ++ y :: ys := (merge_perm_aux xs (y :: ys)).mem_iff.mp hz
        have hz'' : z ∈ xs ∨ z ∈ y :: ys := by
          simpa [List.mem_append] using hz'
        cases hz'' with
        | inl hzxs =>
            exact hx_le_xs z hzxs
        | inr hzy =>
            have hzy' : z = y ∨ z ∈ ys := by
              simpa using hzy
            cases hzy' with
            | inl hzy_eq =>
                subst hzy_eq
                exact hxy
            | inr hzys =>
                have hy_le_z : y <= z := hy_le_ys z hzys
                exact Nat.le_trans hxy hy_le_z
      have htail : SASCodeSorted (merge xs (y :: ys)) := merge_pairwise xs (y :: ys) hxs_tail hys
      have hpair : List.Pairwise (fun a b => a <= b) (x :: merge xs (y :: ys)) := by
        apply List.Pairwise.cons
        · intro z hz
          exact hx_le_merge z hz
        · simpa [SASCodeSorted] using htail
      have hsorted : SASCodeSorted (merge (x :: xs) (y :: ys)) := by
        dsimp [SASCodeSorted]
        simpa [merge, hxy] using hpair
      exact hsorted
    · have hys_tail : SASCodeSorted ys := sorted_tail hys
      have hx_le_xs : AllGe x xs := sorted_head_le hxs
      have hy_le_ys : AllGe y ys := sorted_head_le hys
      have hyx : y <= x := Nat.le_of_not_ge hxy
      have hy_le_merge : AllGe y (merge (x :: xs) ys) := by
        intro z hz
        have hz' : z ∈ x :: xs ++ ys := (merge_perm_aux (x :: xs) ys).mem_iff.mp hz
        have hz'' : z = x ∨ z ∈ xs ∨ z ∈ ys := by
          simpa [List.mem_append] using hz'
        rcases hz'' with hzx | hrest
        · subst hzx
          exact hyx
        · rcases hrest with hzxs | hzys
          · have hx_le_z : x <= z := hx_le_xs z hzxs
            exact Nat.le_trans hyx hx_le_z
          · exact hy_le_ys z hzys
      have htail : SASCodeSorted (merge (x :: xs) ys) := merge_pairwise (x :: xs) ys hxs hys_tail
      have hpair : List.Pairwise (fun a b => a <= b) (y :: merge (x :: xs) ys) := by
        apply List.Pairwise.cons
        · intro z hz
          exact hy_le_merge z hz
        · simpa [SASCodeSorted] using htail
      have hsorted : SASCodeSorted (merge (x :: xs) (y :: ys)) := by
        dsimp [SASCodeSorted]
        simpa [merge, hxy] using hpair
      exact hsorted


theorem split_perm : ∀ xs, let (l, r) := split xs; List.Perm (l ++ r) xs
| [] => by simp [split]
| [x] => by simp [split]
| x :: y :: xs => by
    cases hrec : split xs with
    | mk l r =>
      have ih := split_perm xs
      have ih' : List.Perm (l ++ r) xs := by simpa [hrec] using ih
      have pm : List.Perm (l ++ y :: r) (y :: l ++ r) := by
        simpa using (List.perm_middle (l₁:=l) (a:=y) (l₂:=r))
      have p2 : List.Perm (y :: l ++ r) (y :: xs) := ih'.cons y
      have p3 : List.Perm (l ++ y :: r) (y :: xs) := pm.trans p2
      have p4 : List.Perm (x :: (l ++ y :: r)) (x :: y :: xs) := p3.cons x
      simpa [split, hrec] using p4


theorem merge_perm : ∀ xs, List.Perm (mergeSort xs) xs
| [] => by simp [mergeSort]
| [x] => by simp [mergeSort]
| x :: y :: xs => by
    cases hsplit : split (x :: y :: xs) with
    | mk l r =>
        have hperm_split : List.Perm (l ++ r) (x :: y :: xs) := by
          simpa [hsplit] using (split_perm (x :: y :: xs))
        have hperm_l : List.Perm (mergeSort l) l := merge_perm l
        have hperm_r : List.Perm (mergeSort r) r := merge_perm r
        have hperm_merge : List.Perm (merge (mergeSort l) (mergeSort r)) (mergeSort l ++ mergeSort r) :=
          merge_perm_aux (mergeSort l) (mergeSort r)
        have hperm_lr : List.Perm (mergeSort l ++ mergeSort r) (l ++ r) :=
          (hperm_l.append hperm_r)
        have hperm_all : List.Perm (merge (mergeSort l) (mergeSort r)) (l ++ r) :=
          hperm_merge.trans hperm_lr
        have hperm_all' : List.Perm (mergeSort (x :: y :: xs)) (l ++ r) := by
          simpa [mergeSort, hsplit] using hperm_all
        exact hperm_all'.trans hperm_split
termination_by
  xs => xs.length

decreasing_by
  all_goals
    have hlt := split_length_lt_full x y xs l r hsplit
    first
    | exact hlt.1
    | exact hlt.2


theorem merge_sorted : ∀ xs, SASCodeSorted (mergeSort xs)
| [] => by simp [mergeSort, SASCodeSorted]
| [x] => by simp [mergeSort, SASCodeSorted]
| x :: y :: xs => by
    cases hsplit : split (x :: y :: xs) with
    | mk l r =>
        have hsorted_l : SASCodeSorted (mergeSort l) := merge_sorted l
        have hsorted_r : SASCodeSorted (mergeSort r) := merge_sorted r
        have hsorted_merge : SASCodeSorted (merge (mergeSort l) (mergeSort r)) :=
          merge_pairwise (mergeSort l) (mergeSort r) hsorted_l hsorted_r
        simpa [mergeSort, hsplit] using hsorted_merge
termination_by
  xs => xs.length

decreasing_by
  all_goals
    have hlt := split_length_lt_full x y xs l r hsplit
    first
    | exact hlt.1
    | exact hlt.2


theorem sorted_perm_unique {a b : List Nat} :
    SASCodeSorted a -> SASCodeSorted b -> List.Perm a b -> a = b := by
  intro ha hb hp
  apply List.Perm.eq_of_pairwise (l₁:=a) (l₂:=b) (le:=fun x y => x <= y)
  · intro x y _ _ hxy hyx
    exact Nat.le_antisymm hxy hyx
  · simpa [SASCodeSorted] using ha
  · simpa [SASCodeSorted] using hb
  · exact hp
