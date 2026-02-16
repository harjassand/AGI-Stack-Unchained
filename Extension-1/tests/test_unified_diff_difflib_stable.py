from self_improve_code_v1.patch.unified_diff_v1 import unified_diff


def test_unified_diff_stable():
    before = "a=1\nb=2\n"
    after = "a=1\nb=3\n"
    diff = unified_diff({"foo.py": (before, after)})
    expected = (
        "--- a/foo.py\n"
        "+++ b/foo.py\n"
        "@@ -1,2 +1,2 @@\n"
        " a=1\n"
        "-b=2\n"
        "+b=3\n"
    )
    assert diff == expected
