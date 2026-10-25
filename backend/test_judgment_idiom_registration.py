"""판정 관용구의 정적 계약·이름 호출·메타데이터 재등록 회귀. 외부 API는 격리한다."""
import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

import pytest
import boot_paths  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
CATALOG = json.loads((ROOT / "data/idioms/curated.json").read_text())
NAMES = ("관련자료골라읽기", "의미로본문찾기")
ENTRIES = {e["name"]: e for e in CATALOG["idioms"] if e["name"] in NAMES}


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_inferred_returns_and_catalog_examples():
    from curate_idioms import validate_catalog
    from ibl_typecheck import typecheck_code
    infos = validate_catalog({"idioms": list(ENTRIES.values())})
    for name, entry in ENTRIES.items():
        assert infos[name]["returns"] == "items⟨열 미상⟩"
        result = typecheck_code(f"[def: {name}]{{\n{entry['body']}\n}}\n"
                                + entry["example"] + ' >> [table:select]{columns:["url"]}')
        assert result["ok"] and not result.get("abstained"), result


class Registry:
    def __init__(self, path):
        self.path = path

    def _get_connection(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def find_phrase_by_alias(self, name):
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM ibl_examples WHERE alias=?", (name,)).fetchone()
            return dict(row) if row else None


def test_metadata_refresh_preserves_history_and_is_idempotent(tmp_path, monkeypatch):
    import ibl_usage_db
    from register_idiom import refresh_idiom_metadata
    db = Registry(tmp_path / "usage.db")
    refreshed = []
    monkeypatch.setattr(ibl_usage_db, "_tree_refresh", lambda topic, **kw: refreshed.append(topic))
    with db._get_connection() as conn:
        conn.execute("CREATE TABLE ibl_examples(id INTEGER PRIMARY KEY, alias, intent, ibl_code, "
                     "returns, signature, topic, always_on, success_count, fail_count)")
        for i, (name, entry) in enumerate(ENTRIES.items(), 1):
            conn.execute("INSERT INTO ibl_examples VALUES(?,?,?,?,?,?,?,?,?,?)",
                         (i, name, entry["when"], entry["body"], "scalar", "[]", "수집", 1, 7, 2))
    for name in NAMES:
        before = db.find_phrase_by_alias(name)
        assert refresh_idiom_metadata(db, name)
        after = db.find_phrase_by_alias(name)
        assert after["returns"] == "items⟨열 미상⟩"
        assert {k: v for k, v in after.items() if k not in ("returns", "signature")} == {
            k: v for k, v in before.items() if k not in ("returns", "signature")}
        assert not refresh_idiom_metadata(db, name)
    assert refreshed == ["수집"] * 4








if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
