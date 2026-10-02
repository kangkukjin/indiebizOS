"""수리 판정은 **수리한 쪽의 입**이 닫는다 — 판정 소유 배터리 (2026-08-25).

사용자 확정: "수리한 에이전트가 말하도록 해야지."

배경: RED 수리는 자기 턴이 죽은 뒤에 결말이 나므로(분리 워치독·분리 수행자가 result.json
에 적는다), 그 결말을 다음 턴의 입이 대신 닫는다. 옛 게이트는 '시스템 AI 만'이었다 —
수리 주체가 시스템 AI 하나라는 전제였고, 그 전제는 같은 날 그랜트 한도가 정본대로
복원되며 깨졌다(ep1915 수리 — 프로젝트 에이전트도 사람 명령이면 수리한다).
게이트를 신원('내가 시스템 AI 인가')에서 소유('이 판정이 내 것인가')로 옮긴다.

★왜 관문이 필요한가: 회수는 **한 번뿐**이다(announced_at). 엉뚱한 입이 먼저 주우면
표식만 찍히고 정작 명령한 창에서는 영영 안 보인다 — 침묵하는 실패라 눈으로는 못 잡는다.

  O1 열쇠 규칙 — 신원 없는 몸=시스템 AI, 프로젝트 에이전트=project:agent(id 는 프로젝트 안에서만 유일)
  O2 판정 회수는 주인 것만 (옛 기록=표식 없음=시스템 AI 로 착지 — 하위호환)
  O3 남의 판정에는 **표식을 찍지 않는다** (한 번뿐인 회수를 남이 태워버리지 않는다)
  O4 미적용 스테이징도 같은 스코프
  O5 규칙은 한 벌 — 생산자(handler·repair_staging)가 red_report 의 열쇠를 빌려 쓴다
  O6 지연 결말의 주인은 **세션 원장**에서 온다 (분리 수행자에겐 수리한 턴의 컨텍스트가 없다)
"""
import ast
import hashlib
import json
import os
import time

import pytest

import red_report as rr

REPO_SYSTEM_ESSENTIALS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "packages", "installed", "tools", "system_essentials")


def _put_result(repo, key, owner=None, outcome="healthy"):
    d = os.path.join(repo, "data", "system_ai_state", "red_backups", key)
    os.makedirs(d, exist_ok=True)
    payload = {"outcome": outcome, "files": ["backend/x.py"], "finished_at": 9e9}
    if owner is not None:
        payload["owner"] = owner
    with open(os.path.join(d, "result.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f)
    return os.path.join(d, "result.json")


def _put_session(repo, key, owner=None, status="staging"):
    d = os.path.join(repo, "data", "system_ai_state", "repair_sessions")
    os.makedirs(d, exist_ok=True)
    sess = {"key": key, "status": status, "files": {"/a/b.py": {"rel": "backend/b.py"}}}
    if owner is not None:
        sess["owner"] = owner
    with open(os.path.join(d, f"{key}.json"), "w", encoding="utf-8") as f:
        json.dump(sess, f)


def test_o1_owner_key_rule():
    assert rr.owner_key("", "") == rr.OWNER_SYSTEM_AI          # 시스템 AI 는 agent_id 를 안 세운다
    assert rr.owner_key("  ", "정보센터") == rr.OWNER_SYSTEM_AI  # 공백도 신원이 아니다
    assert rr.owner_key("agent_001", "정보센터") == "정보센터:agent_001"
    assert rr.owner_key("agent_001", "") == "agent_001"
    # ★프로젝트를 앞에 붙이는 이유 — 같은 id 가 다른 프로젝트에도 산다
    assert rr.owner_key("agent_001", "가계부") != rr.owner_key("agent_001", "정보센터")
    # ★시스템 AI 는 자리에 따라 신원이 반쯤 선다(채팅 턴=미세팅 / 상주 루프=system_ai:system).
    #   같은 몸이 두 열쇠를 받으면 판정이 어긋나 영영 침묵하므로 하나로 접는다.
    assert rr.owner_key("system_ai", "system") == rr.OWNER_SYSTEM_AI
    assert rr.owner_key("system_ai", "") == rr.OWNER_SYSTEM_AI


def test_o2_collect_pending_is_owner_scoped(tmp_path):
    repo = str(tmp_path)
    _put_result(repo, "t_sys", owner=None)                       # 옛 기록 — 표식 없음
    _put_result(repo, "t_data", owner="정보센터:agent_001")
    _put_result(repo, "t_other", owner="가계부:agent_001")

    mine = rr.collect_pending(repo, owner="정보센터:agent_001")
    assert [d["outcome"] for d in mine] == ["healthy"] and len(mine) == 1
    assert mine[0]["owner"] == "정보센터:agent_001"

    # 표식 없는 옛 판정은 종전 규약대로 시스템 AI 가 받는다(회수 유실 방지)
    sys_items = rr.collect_pending(repo, owner=rr.OWNER_SYSTEM_AI)
    assert len(sys_items) == 1 and "t_sys" in sys_items[0]["_path"]

    assert len(rr.collect_pending(repo)) == 3                     # owner=None = 전부(감사용)


def test_o3_foreign_verdicts_are_not_marked_announced(tmp_path):
    """★한 번뿐인 회수를 남이 태우지 않는다 — 이게 깨지면 판정이 조용히 사라진다."""
    repo = str(tmp_path)
    mine = _put_result(repo, "t_data", owner="정보센터:agent_001")
    theirs = _put_result(repo, "t_sys", owner=rr.OWNER_SYSTEM_AI)

    scent = rr.pending_scent(repo, owner="정보센터:agent_001")
    assert "<repair_outcome" in scent

    assert json.load(open(mine, encoding="utf-8")).get("announced_at")        # 내 것은 닫혔다
    assert not json.load(open(theirs, encoding="utf-8")).get("announced_at")  # 남의 것은 그대로

    # 주인이 다음 턴에 오면 자기 판정을 여전히 받는다
    assert "<repair_outcome" in rr.pending_scent(repo, owner=rr.OWNER_SYSTEM_AI)
    # 그리고 회수는 한 번뿐 — 두 번째는 조용하다
    assert rr.pending_scent(repo, owner=rr.OWNER_SYSTEM_AI) == ""


def test_o4_unapplied_staging_is_owner_scoped(tmp_path):
    repo = str(tmp_path)
    _put_session(repo, "s_data", owner="정보센터:agent_001")
    _put_session(repo, "s_other", owner="가계부:agent_001")
    _put_session(repo, "s_old", owner=None)

    mine = rr.collect_unapplied(repo, min_age_s=0, owner="정보센터:agent_001")
    assert [s["key"] for s in mine] == ["s_data"]
    assert [s["key"] for s in rr.collect_unapplied(repo, min_age_s=0,
                                                   owner=rr.OWNER_SYSTEM_AI)] == ["s_old"]


@pytest.mark.parametrize('live,staged,op,expected', [
    (b'new', b'new', 'write', 'matching'),  # 다른 작업에서 이미 반영한 내용
    (b'base', b'new', 'write', 'base_unchanged'),
    (b'newer', b'new', 'write', 'diverged'),  # 반영 뒤 추가 개발도 미반영으로 단정하지 않음
    (b'base', None, 'write', 'unknown'),  # 격리 파일 유실은 미반영 증거가 아님
    (None, b'new', 'write', 'diverged'),  # 원본 파일이 별도로 삭제됨
    (None, None, 'delete', 'matching'),
    (b'base', None, 'delete', 'base_unchanged'),
])
def test_staged_observation_compares_bytes_without_changing_ledger(
        tmp_path, live, staged, op, expected):
    target = tmp_path / 'backend' / 'example.py'
    isolated = tmp_path / '.worktrees' / 'repair' / 'backend' / 'example.py'
    for path, content in ((target, live), (isolated, staged)):
        path.parent.mkdir(parents=True, exist_ok=True)
        if content is not None:
            path.write_bytes(content)
    root = tmp_path / 'data/system_ai_state/repair_sessions'
    root.mkdir(parents=True)
    record = {'rel': 'backend/example.py', 'staged': str(isolated), 'op': op,
              'base_sha': hashlib.sha256(b'base').hexdigest()}
    ledger = root / 'repair.json'
    ledger.write_text(json.dumps({'key': 'repair', 'status': 'staging',
                                  'files': {str(target): record}}))
    before = ledger.read_bytes()
    os.utime(ledger, (1, time.time() - 120))
    observation = rr.collect_unapplied(str(tmp_path))[0]['live_comparison']
    assert observation[expected] == 1 and sum(observation.values()) == 1
    scent = rr.pending_scent(str(tmp_path))
    assert '기능 부재·활성화·커밋 여부는 별도 확인' in scent
    assert '지금 시스템에 없다' not in scent
    assert ledger.read_bytes() == before
    assert (target.read_bytes() if target.exists() else None) == live


def test_new_file_and_unobservable_staging(tmp_path, monkeypatch):
    staged = tmp_path / 'staged.py'
    staged.write_bytes(b'new')
    rec = {'rel': 'new.py', 'staged': str(staged), 'op': 'write', 'base_sha': None}
    assert rr.staged_live_comparison(str(tmp_path), {'files': {'new.py': rec}})['base_unchanged'] == 1
    rec.pop('base_sha')  # 옛 원장: 시작 지문을 모른다
    assert rr.staged_live_comparison(str(tmp_path), {'files': {'new.py': rec}})['unknown'] == 1
    rec['rel'] = '../outside.py'
    assert rr.staged_live_comparison(str(tmp_path), {'files': {'new.py': rec}})['unknown'] == 1
    rec['rel'] = 'new.py'
    from pathlib import Path
    def denied(*args, **kwargs):
        raise PermissionError('unreadable')
    monkeypatch.setattr(Path, 'open', denied)
    assert rr.staged_live_comparison(str(tmp_path), {'files': {'new.py': rec}})['unknown'] == 1


def test_old_schedule_is_review_candidate_not_dead_worker(tmp_path):
    _put_session(str(tmp_path), 'scheduled', status='apply_scheduled')
    ledger = tmp_path / 'data/system_ai_state/repair_sessions/scheduled.json'
    now = time.time()
    assert rr.collect_unapplied(str(tmp_path), min_age_s=0) == []
    os.utime(ledger, (now - rr.SCHEDULED_STALE_S - 1,) * 2)
    scent = rr.pending_scent(str(tmp_path))
    assert 'scheduled_review="true"' in scent
    assert '수행자·영수증을 확인' in scent
    assert '수행자가 죽어' not in scent


def test_status_tool_uses_same_observation_as_recall(tmp_path):
    from test_repair_staging import _load_handler
    _put_session(str(tmp_path), 'repair')
    tool = _load_handler()._staging_mod().op_status(
        {'_repo_root': str(tmp_path), '_grant_key': 'repair'})
    recalled = rr.collect_unapplied(str(tmp_path), min_age_s=0)[0]
    assert tool['items'][0]['live_comparison'] == recalled['live_comparison']
    assert recalled['live_comparison']['unknown'] == 1
    assert '기능 부재·활성화·커밋 판정이 아닙니다' in tool['message']


def test_o5_producers_borrow_the_single_rule():
    """생산자가 열쇠를 **자기 손으로 조립하지 않는다** — 두 벌이면 반드시 어긋나고,
    어긋나면 판정이 아무 입에도 안 걸려 영영 침묵한다(침묵 실패라 눈으로 못 잡는다)."""
    for name in ("handler.py", "repair_staging.py"):
        src = open(os.path.join(REPO_SYSTEM_ESSENTIALS, name), encoding="utf-8").read()
        assert "from red_report import current_owner" in src, (
            f"{name} 이 red_report 의 열쇠를 안 빌린다 — 규칙이 두 벌이 됐다")
        tree = ast.parse(src)
        fns = [n for n in ast.walk(tree)
               if isinstance(n, ast.FunctionDef) and n.name == "_repair_owner"]
        assert len(fns) == 1, f"{name} 의 _repair_owner 가 {len(fns)}개다"
        called = {n.func.id for n in ast.walk(fns[0])
                  if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
        assert "current_owner" in called
        assert "owner_key" not in called, (
            f"{name} 이 열쇠를 직접 조립한다 — current_owner 하나만 쓸 것")


def test_o6_deferred_verdict_owner_comes_from_the_session_ledger():
    """지연 적용은 분리 프로세스(red_apply)가 수행한다 — 거기서 컨텍스트를 물으면
    언제나 '시스템 AI' 라는 오답이 나온다. 주인은 세션 원장에서 실려 와야 한다."""
    src = open(os.path.join(REPO_SYSTEM_ESSENTIALS, "repair_staging.py"), encoding="utf-8").read()
    tree = ast.parse(src)

    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "_write_deferred_result")
    assert "owner" in [a.arg for a in fn.args.args], "_write_deferred_result 가 주인을 못 받는다"
    called = {n.func.id for n in ast.walk(fn) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert "_repair_owner" not in called, (
        "지연 결말이 수행자 프로세스의 컨텍스트를 묻는다 — 거기엔 수리한 에이전트가 없다")

    perform = next(n for n in ast.walk(tree)
                   if isinstance(n, ast.FunctionDef) and n.name == "perform_scheduled_apply")
    writes = [n for n in ast.walk(perform)
              if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "_write_deferred_result"]
    assert writes, "예약 수행에 결말 기록이 없다"
    for w in writes:
        assert any(k.arg == "owner" for k in w.keywords), (
            f"{w.lineno}행의 결말 기록이 주인을 안 넘긴다 — 그 판정은 남의 창으로 간다")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
