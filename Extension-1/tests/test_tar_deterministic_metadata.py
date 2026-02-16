import tarfile

from self_improve_code_v1.package.tar_deterministic_v1 import write_deterministic_tar


def test_tar_deterministic(tmp_path):
    entries = {"manifest.json": b"{}", "patch.diff": b""}
    t1 = tmp_path / "a.tar"
    t2 = tmp_path / "b.tar"
    write_deterministic_tar(str(t1), entries)
    write_deterministic_tar(str(t2), entries)
    assert t1.read_bytes() == t2.read_bytes()

    with tarfile.open(t1, "r") as tf:
        members = tf.getmembers()
        assert [m.name for m in members] == ["manifest.json", "patch.diff"]
        for m in members:
            assert m.mtime == 0
            assert m.uid == 0
            assert m.gid == 0
            assert m.uname == "root"
            assert m.gname == "root"
