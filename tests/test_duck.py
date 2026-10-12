from __future__ import annotations

from breakout import duck


def test_connect_in_memory_and_pragmas():
    con = duck.connect()
    assert con.execute("select 42").fetchone() == (42,)
    assert con.execute("select current_setting('preserve_insertion_order')").fetchone() == (False,)


def test_connect_file_creates_parent(tmp_path):
    db = tmp_path / "sub" / "w.duckdb"
    con = duck.connect(db)
    con.execute("create table t as select 1 a")
    con.close()
    assert db.exists()


def test_is_remote():
    assert duck.is_remote("https://x/y.parquet")
    assert duck.is_remote("hf://datasets/a/b")
    assert not duck.is_remote("data/lake/x.parquet")
