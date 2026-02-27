Agent 1 owns (and ONLY agent allowed to modify):

baremetal_lgp/src/abi.rs
baremetal_lgp/src/isa/**
baremetal_lgp/src/bytecode/**
baremetal_lgp/src/cfg/**
baremetal_lgp/src/vm/**
baremetal_lgp/src/accel/**
baremetal_lgp/src/jit/**
baremetal_lgp/tests/agent1_*.rs

Agent 2 owns (and ONLY agent allowed to modify):

baremetal_lgp/src/oracle/**
baremetal_lgp/tests/agent2_*.rs

Agent 3 owns (and ONLY agent allowed to modify):

baremetal_lgp/src/search/**
baremetal_lgp/src/library/**
baremetal_lgp/src/outer_loop/**
baremetal_lgp/src/bin/** (or baremetal_lgp/src/bin/*.rs)
baremetal_lgp/scripts/**
baremetal_lgp/benches/**
baremetal_lgp/tests/agent3_*.rs

Shared files that must be modified only in the bootstrap commit (before parallel work):

baremetal_lgp/Cargo.toml
baremetal_lgp/src/lib.rs
baremetal_lgp/README.md
baremetal_lgp/OWNERS.md

After bootstrap, agents must not edit these shared files. If an interface change is needed, Agent 3 or Agent 2 writes a request in baremetal_lgp/rfcs/RFC_*.md (Agent 3 creates file; Agent 1 applies code change if required).
