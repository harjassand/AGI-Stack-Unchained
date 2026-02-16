from __future__ import annotations

from self_improve_code_v1.domains.flagship_code_rsi_v1.noop_guard_v1 import is_semantic_noop


def test_semantic_noop_detector() -> None:
    diff_comment = """diff --git a/a.py b/a.py
--- a/a.py
+++ b/a.py
@@ -1,1 +1,2 @@
 x = 1
+# comment only
"""
    assert is_semantic_noop(diff_comment)

    diff_ws = """diff --git a/a.py b/a.py
--- a/a.py
+++ b/a.py
@@ -1,1 +1,1 @@
-x = 1
+x = 1 
"""
    assert is_semantic_noop(diff_ws)

    diff_code = """diff --git a/a.py b/a.py
--- a/a.py
+++ b/a.py
@@ -1,1 +1,1 @@
-x = 1
+x = 2
"""
    assert not is_semantic_noop(diff_code)
