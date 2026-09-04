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
    for sid in ("arxiv최신피드", "github저장소메타"):
        assert sid in registry
        assert (SCRIPT_DIR / registry[sid]["file"]).is_file()
        assert registry[sid]["interpreter"] == "python"


# json원장 스크립트 시험은 [self:ledger] 승격(2026-09-04)과 함께 backend/test_ledger_vocab.py 로 이관.


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__]))
