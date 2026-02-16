from pathlib import Path

from cdel.config import load_config, write_default_config
from cdel.ledger import index as idx
from cdel.adoption.storage import init_storage as init_adoption_storage
from cdel.ledger.storage import init_storage


def init_repo(tmp_path: Path, budget: int = 100000) -> object:
    write_default_config(tmp_path, budget)
    cfg = load_config(tmp_path)
    init_storage(cfg)
    init_adoption_storage(cfg)
    conn = idx.connect(str(cfg.sqlite_path))
    idx.init_schema(conn)
    idx.set_budget(conn, budget)
    conn.commit()
    return cfg
