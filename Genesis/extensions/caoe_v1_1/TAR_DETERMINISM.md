# Deterministic Tar Rules (v1.1)

These rules apply to CAOE candidate bundles and related artifacts.

Required properties
- Entries sorted lexicographically by name.
- No symlinks or hardlinks.
- No pax headers.
- `mtime = 0` for all entries.
- `uid = 0`, `gid = 0` for all entries.
- `uname = "root"`, `gname = "root"` for all entries.
- File mode `0644`, directory mode `0755`.
- No absolute paths and no `..` path segments.

Validation MUST fail-closed on any deviation.
