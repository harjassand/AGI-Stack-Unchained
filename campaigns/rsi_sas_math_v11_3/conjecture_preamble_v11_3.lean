/-
v11_3 combinatorial substrate: custom recursive list of Nat.
No imports. No syntax extensions. No set_option. No macros.
-/

inductive LNat where
| nil : LNat
| cons : Nat -> LNat -> LNat

def lappend : LNat -> LNat -> LNat
| LNat.nil, ys => ys
| LNat.cons x xs, ys => LNat.cons x (lappend xs ys)

def llen : LNat -> Nat
| LNat.nil => 0
| LNat.cons _ xs => Nat.succ (llen xs)

def lsum : LNat -> Nat
| LNat.nil => 0
| LNat.cons x xs => x + lsum xs

def lrev : LNat -> LNat
| LNat.nil => LNat.nil
| LNat.cons x xs => lappend (lrev xs) (LNat.cons x LNat.nil)

def lmap (f : Nat -> Nat) : LNat -> LNat
| LNat.nil => LNat.nil
| LNat.cons x xs => LNat.cons (f x) (lmap f xs)

def range : Nat -> LNat
| 0 => LNat.nil
| Nat.succ n => lappend (range n) (LNat.cons n LNat.nil)

def lsorted : LNat -> Prop
| LNat.nil => True
| LNat.cons _ LNat.nil => True
| LNat.cons x (LNat.cons y ys) => x <= y ∧ lsorted (LNat.cons y ys)

def linsert (a : Nat) : LNat -> LNat
| LNat.nil => LNat.cons a LNat.nil
| LNat.cons x xs =>
    if a <= x then
      LNat.cons a (LNat.cons x xs)
    else
      LNat.cons x (linsert a xs)

def lsort : LNat -> LNat
| LNat.nil => LNat.nil
| LNat.cons x xs => linsert x (lsort xs)
