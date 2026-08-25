"""매일 보고서의 반복 우회를 결정화한 등록 스크립트 회귀 테스트."""
import importlib.util
import io
import json
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "data" / "scripts"


def _load(name):
    path = SCRIPT_DIR / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"test_{name}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_main(module, monkeypatch, capsys, args):
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(args, ensure_ascii=False)))
    module.main()
    return json.loads(capsys.readouterr().out)


def test_report_scripts_are_registered_and_present():
    registry = yaml.safe_load((SCRIPT_DIR / "registry.yaml").read_text(encoding="utf-8"))
    for sid in ("arxiv최신피드", "github저장소메타", "json원장"):
        assert sid in registry
        assert (SCRIPT_DIR / registry[sid]["file"]).is_file()
        assert registry[sid]["interpreter"] == "python"


def test_json_ledger_append_upsert_and_rolling(tmp_path, monkeypatch, capsys):
    module = _load("json원장")
    monkeypatch.setattr(module, "_ROOT", tmp_path)
    path = "outputs/ledger.json"

    first = _run_main(module, monkeypatch, capsys, {
        "path": path, "op": "append",
        "items": [{"id": "a", "v": 1}, {"id": "b", "v": 2}],
    })
    assert first["success"] and first["count"] == 2

    second = _run_main(module, monkeypatch, capsys, {
        "path": path, "op": "upsert", "key": "id", "max_items": 2,
        "items": [{"id": "a", "v": 3}, {"id": "c", "v": 4}],
    })
    assert second["success"] and second["count"] == 2
    saved = json.loads((tmp_path / path).read_text(encoding="utf-8"))
    assert saved == [{"id": "a", "v": 3}, {"id": "c", "v": 4}]


def test_json_ledger_nested_target(monkeypatch, capsys, tmp_path):
    module = _load("json원장")
    monkeypatch.setattr(module, "_ROOT", tmp_path)
    result = _run_main(module, monkeypatch, capsys, {
        "path": "outputs/covered.json", "op": "upsert", "target": "covered",
        "key": "id", "item": {"id": "v1", "verdict": "used"},
    })
    assert result["success"]
    saved = json.loads((tmp_path / "outputs/covered.json").read_text(encoding="utf-8"))
    assert saved["covered"] == [{"id": "v1", "verdict": "used"}]


def test_github_repo_batch_returns_structured_items(monkeypatch, capsys):
    module = _load("github저장소메타")
    calls = []

    def fake_get(url, params=None):
        calls.append((url, params))
        name = url.split("/repos/")[-1]
        return {"full_name": name, "html_url": f"https://github.com/{name}",
                "stargazers_count": 7, "forks_count": 2,
                "pushed_at": "2026-08-25T00:00:00Z"}, None

    monkeypatch.setattr(module, "_get", fake_get)
    result = _run_main(module, monkeypatch, capsys, {
        "repos": ["a/one", "https://github.com/b/two.git", "a/one"],
    })
    assert result["success"] and result["count"] == 2
    assert {x["full_name"] for x in result["items"]} == {"a/one", "b/two"}
    assert len(calls) == 2


def test_arxiv_feed_retries_parse_failure(monkeypatch):
    module = _load("arxiv최신피드")
    atom = b'''<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom"
          xmlns:arxiv="http://arxiv.org/schemas/atom">
      <entry><id>http://arxiv.org/abs/2608.00001v1</id><title>Probe</title>
      <published>2026-08-25T00:00:00Z</published><updated>2026-08-25T00:00:00Z</updated>
      <author><name>A</name></author><summary>S</summary>
      <arxiv:primary_category term="cs.AI" /></entry>
    </feed>'''

    class Response:
        status_code = 200

        def __init__(self, content):
            self.content = content

    responses = iter([Response(b""), Response(atom)])
    monkeypatch.setattr(module.requests, "get", lambda *a, **k: next(responses))
    monkeypatch.setattr(module.time, "sleep", lambda _seconds: None)
    feed, error = module._fetch("cat:cs.AI", "submittedDate", 10)
    assert error is None and len(feed.entries) == 1

