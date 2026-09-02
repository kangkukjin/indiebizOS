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


def test_에피소드통계가_회수폴링을_문법오류로_세지_않는다(monkeypatch, capsys, tmp_path):
    """계기가 정상 사용을 결함으로 신고하던 자리 (2026-09-01).

    `execute_ibl{code: "", recover: "티켓"}` 는 실행이 아니라 조회다. 빈 code 는 파서를
    통과할 수 없어 옛 판은 이걸 '문법오류'로 셌고, 09-01 주행의 회수 9회가 "그 주행에서
    실제로 깨진 문장 9건"으로 읽혔다 — 계기가 오독을 만들었다. 회수는 따로 세고 조합
    지표에서 뺀다(그 수 자체가 '결과를 기다리며 쓴 왕복 수'라는 관측이다).
    """
    import sqlite3
    mod = _load("에피소드통계")
    db = tmp_path / "world_pulse.db"
    conn = sqlite3.connect(db)
    conn.execute("""CREATE TABLE episode_log (id INTEGER PRIMARY KEY, started_at TEXT,
                    ended_at TEXT, agent TEXT, user_message TEXT, log TEXT, total_ms INTEGER,
                    task_id TEXT, source TEXT, owner TEXT, run_id TEXT, parent_run_id TEXT)""")
    conn.execute("""CREATE TABLE episode_summary (id INTEGER PRIMARY KEY, episode_id INTEGER,
                    started_at TEXT, agent TEXT, user_message TEXT, hippocampus_score REAL,
                    unconscious_decision TEXT, consciousness_ms INTEGER, execution_rounds INTEGER,
                    total_ms INTEGER, evaluation_result TEXT, steps TEXT, source TEXT, run_id TEXT)""")
    log = "\n".join([
        '[ClaudeCode/시스템 AI] tool_use mcp__indiebizos__execute_ibl '
        '{"code": "[self:time]{} >> [table:take]{n: 1}", "verbose": false}',
        '[ClaudeCode/시스템 AI] tool_use mcp__indiebizos__execute_ibl '
        '{"code": "", "recover": "593e5a2d9058"}',
        '[ClaudeCode/시스템 AI] tool_use mcp__indiebizos__execute_ibl '
        '{"code": "", "recover": "593e5a2d9058"}',
        '[ClaudeCode/시스템 AI] tool_use mcp__indiebizos__execute_ibl '
        '{"code": "[self:time]{ 깨진", "verbose": false}',
    ])
    conn.execute("INSERT INTO episode_log (id, started_at, agent, log, total_ms, source) "
                 "VALUES (1, '2026-09-01T06:00:00', 'system_ai', ?, 1000, 'usage')", (log,))
    conn.commit(); conn.close()
    monkeypatch.setattr(mod, "DB", db)
    out = _run_main(mod, monkeypatch, capsys, {"last": 5})
    row = out["items"][0]
    assert row["회수"] == 2, row
    assert row["IBL"] == 4, "회수도 execute_ibl 호출이라 IBL 총수에는 남는다"
    assert row["문장"] == 1, "회수는 문장이 아니다 — 조합 지표에서 빠져야 한다"
    assert "회수폴링" not in row["상태"], "진짜 문법오류가 있으면 그쪽이 상태다"
    assert row["상태"] == "문법오류 1", row["상태"]     # 깨진 문장 1건만 결함이다
    assert "회수 폴링" in out["message"]


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


def test_json_ledger_set_requires_value_key(tmp_path, monkeypatch, capsys):
    # 사고 재현(2026-08-30): value 대신 items 로 부른 set 이 대상을 조용히 null 로
    # 덮고 성공을 보고했다. 이제 value 키 부재는 정직 거절 — 파일은 그대로여야 한다.
    import pytest
    module = _load("json원장")
    monkeypatch.setattr(module, "_ROOT", tmp_path)
    path = "outputs/policy.json"
    _run_main(module, monkeypatch, capsys, {
        "path": path, "op": "set", "target": "explore_first", "value": True,
    })

    for bad in [
        {"path": path, "op": "set", "target": "explore_first", "items": [False]},
        {"path": path, "op": "set"},  # target 도 value 도 없음 = 파일 전체 null 폭탄이던 경로
    ]:
        with pytest.raises(SystemExit):
            _run_main(module, monkeypatch, capsys, bad)
        refused = json.loads(capsys.readouterr().out)
        assert refused["success"] is False and "value" in refused["error"]
        saved = json.loads((tmp_path / path).read_text(encoding="utf-8"))
        assert saved == {"explore_first": True}

    # 명시적 null 은 여전히 표현 가능 — 키 부재와 null 값은 다른 사건이다
    ok = _run_main(module, monkeypatch, capsys, {
        "path": path, "op": "set", "target": "explore_first", "value": None,
    })
    assert ok["success"]
    saved = json.loads((tmp_path / path).read_text(encoding="utf-8"))
    assert saved == {"explore_first": None}


def test_json_ledger_set_refuses_root_replace_and_key_typo(tmp_path, monkeypatch, capsys):
    # 사고 재현(2026-08-31): {op:"set", key:"explore_first", value:[…]} — target 이 비어
    # 파일 전체가 105B 배열로 덮였고 봉투는 success 였다. 이제 둘 다 정직 거절, 파일 불변.
    import pytest
    module = _load("json원장")
    monkeypatch.setattr(module, "_ROOT", tmp_path)
    path = "outputs/rotation.json"
    _run_main(module, monkeypatch, capsys, {
        "path": path, "op": "upsert", "target": "queue", "key": "slug",
        "item": {"slug": "wonju", "verdict": "관심"},
    })
    before = json.loads((tmp_path / path).read_text(encoding="utf-8"))
    for bad, needle in [
        ({"path": path, "op": "set", "key": "explore_first", "value": ["asan"]}, "target"),
        ({"path": path, "op": "set", "value": ["asan"]}, "replace_root"),
    ]:
        with pytest.raises(SystemExit):
            _run_main(module, monkeypatch, capsys, bad)
        refused = json.loads(capsys.readouterr().out)
        assert refused["success"] is False and needle in refused["error"]
        assert json.loads((tmp_path / path).read_text(encoding="utf-8")) == before
    # target 을 주면 최상위 키 갱신, replace_root 를 명시하면 루트 교체 — 둘 다 여전히 가능
    ok = _run_main(module, monkeypatch, capsys, {
        "path": path, "op": "set", "target": "explore_first", "value": ["asan"],
    })
    assert ok["success"]
    saved = json.loads((tmp_path / path).read_text(encoding="utf-8"))
    assert saved["explore_first"] == ["asan"] and saved["queue"] == before["queue"]
    ok = _run_main(module, monkeypatch, capsys, {
        "path": path, "op": "set", "value": {"fresh": True}, "replace_root": True,
    })
    assert ok["success"]
    assert json.loads((tmp_path / path).read_text(encoding="utf-8")) == {"fresh": True}


def test_json_ledger_enum_fields_and_list_limits(tmp_path, monkeypatch, capsys):
    # 판정 문장("노원=보류 / 도봉=관심")이 verdict 에 들어와 재방문 규칙이 한 번도 안 걸리던 자리 —
    # 스키마를 산문이 아니라 관문이 집행한다. 태그 상한(list_limits)도 같은 부류.
    import pytest
    module = _load("json원장")
    monkeypatch.setattr(module, "_ROOT", tmp_path)
    path = "outputs/rotation.json"
    enums = {"verdict": ["미판정", "관심", "보류", "기각"]}
    ok = _run_main(module, monkeypatch, capsys, {
        "path": path, "op": "upsert", "target": "queue", "key": "slug",
        "item": {"slug": "nowon", "verdict": "관심", "sub_verdicts": {"노원": "보류", "도봉": "관심"}},
        "enum_fields": enums,
    })
    assert ok["success"]
    with pytest.raises(SystemExit):
        _run_main(module, monkeypatch, capsys, {
            "path": path, "op": "upsert", "target": "queue", "key": "slug",
            "item": {"slug": "nowon", "verdict": "노원=보류 / 도봉=관심"}, "enum_fields": enums,
        })
    refused = json.loads(capsys.readouterr().out)
    assert refused["success"] is False and "sub_verdicts" in refused["error"]
    saved = json.loads((tmp_path / path).read_text(encoding="utf-8"))
    assert saved["queue"][0]["verdict"] == "관심"
    limits = {"tags": {"max_items": 2, "max_item_len": 5}}
    with pytest.raises(SystemExit):
        _run_main(module, monkeypatch, capsys, {
            "path": "outputs/cov.json", "op": "append", "item": {"tags": ["짧다", "이건 너무 긴 태그다"]},
            "list_limits": limits,
        })
    refused = json.loads(capsys.readouterr().out)
    assert refused["success"] is False and "5자" in refused["error"]
    with pytest.raises(SystemExit):
        _run_main(module, monkeypatch, capsys, {
            "path": "outputs/cov.json", "op": "append", "item": {"tags": ["a", "b", "c"]},
            "list_limits": limits,
        })
    assert not (tmp_path / "outputs/cov.json").exists()


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


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__]))
