"""셸 그림자 관문 회귀 (2026-09-05, ep2862·2866 실측 뒤 근본 처방).

재현한 결함: "IBL 등가물이 있는 일을 Bash 로 하지 마라"가 산문뿐이라 두 수리 주행에서 Bash 27건 중 18건이
grep·sed -n·cat 이었고, 127줄 블록 제거는 /tmp 파이썬 스크립트로 갔다(쓰기 원장·RED 격리·해마 밖).
Read·Grep 네이티브를 이름 골라 막았더니 물이 Bash 로 옮겨간 것 — 손으로 고른 스윕은 샌다.

고정하는 계약:
  S1  관문표는 어휘 단일 소스에서 파생된다 — data/shell_shadow.json 의 낱말은 전부 레지스트리에 있고,
      shell_shadow: 를 선언한 낱말은 전부 표에 있다(코드에 낱말 이름 없음).
  S2  그림자 명령(grep·sed -n·cat -n·tail·ls·find·rm·리다이렉션·sqlite3·sed -i)은 거절되고 거절문이
      **그 명령을 옮긴 IBL 문장**을 싣는다(인자→param 은 argmap 데이터가 정한다).
  S3  셸의 몫은 통과한다 — git·pytest·빌드 스크립트·파이프 안의 필터(git diff | grep)·임시 폴더 읽기/쓰기·
      파일을 쓰지 않는 인라인 파이썬.
  S4  파일을 쓰는 인라인 파이썬·임시 스크립트(같은 명령의 히어독 포함)는 편집 낱말의 그림자다.
  S5  네이티브 Write/Edit 는 임시 폴더 밖이면 거절, 안이면 통과.
  S6  Claude Code 명령은 `--settings` 로 PreToolUse 훅을 싣고, 훅 __main__ 은 거절 시 exit 2 + stderr 사유.
      정책 지문이 훅을 포함한다(옛 세션이 fresh 가 된다).
  S7  in-process run_command 도 같은 판정기로 거절한다(error_type: shell_shadow).
  S8  절단 표지(truncated)의 승격 경고는 같은 낱말 안의 다음 걸음을 싣는다.
  S9  낱말 상위집합: [self:grep] context/ignore_case · [self:read] numbered/tail · [self:edit] start_line/end_line.

실행: .venv/bin/python -m pytest backend/test_shell_shadow_gate.py -q
"""
import importlib.util
import json
import os
import subprocess
import sys

import pytest

BACKEND = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BACKEND)
sys.path.insert(0, BACKEND)
import boot_paths  # noqa: E402,F401

import shell_shadow_gate as G  # noqa: E402

_ESS = os.path.join(ROOT, "data", "packages", "installed", "tools", "system_essentials")
_TABLE = G.load_table(ROOT)


def _ess(name):
    spec = importlib.util.spec_from_file_location(f"{name}_shadow_test", os.path.join(_ESS, f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _judge(cmd, cwd=ROOT):
    return G.judge_shell(cmd, cwd=cwd, root=ROOT, table=_TABLE)


# ---------------------------------------------------------------- S1 표는 어휘에서
def test_s1_table_derived_from_vocabulary():
    import yaml
    shadows = _TABLE.get("shadows") or {}
    assert shadows, "data/shell_shadow.json 이 비었다 — build_ibl_nodes.py 를 돌려라"
    nodes = yaml.safe_load(open(os.path.join(ROOT, "data", "ibl_nodes.yaml"), encoding="utf-8"))["nodes"]
    declared = {f"{n}:{a}" for n, nd in nodes.items() for a, ad in (nd.get("actions") or {}).items()
                if isinstance(ad, dict) and isinstance(ad.get("shell_shadow"), dict)}
    assert set(shadows) == declared
    assert all(spec.get("heads") or spec.get("native") or spec.get("redirect") or spec.get("python_write")
               for spec in shadows.values())
    # 관문 *코드* 에 낱말 이름이 없다 — 문서열(docstring)은 내력 설명이라 제외, 실행되는 문자열 상수만 본다
    import ast
    tree = ast.parse(open(os.path.join(BACKEND, "base", "shell_shadow_gate.py"), encoding="utf-8").read())
    docstrings = {ast.get_docstring(n, clean=False) for n in ast.walk(tree)
                  if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef))}
    for n in ast.walk(tree):
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value not in docstrings:
            assert "[self:" not in n.value and "[sense:" not in n.value, n.value


# ---------------------------------------------------------------- S2 그림자는 거절 + 옮긴 문장
@pytest.mark.parametrize("cmd, word, frag", [
    ('grep -rn "yttv|icon" data/packages --include=*.yaml | head -20', "self:grep",
     '[self:grep]{file_pattern: "*.yaml", pattern: "yttv|icon", path: "data/packages"}'),
    ("grep -n -A3 -i needle backend/x.py", "self:grep", "context: 3"),
    ("rg 'def foo' backend", "self:grep", 'pattern: "def foo", path: "backend"'),
    ("sed -n '330,334p' data/system_docs/technical.md", "self:read", "start_line: 330, end_line: 334"),
    ("cat -n backend/surface/x.py", "self:read", "numbered: true"),
    ("tail -40 data/script_runs/시험.log", "self:read", "tail: 40"),
    ("head -n 12 data/x.md", "self:read", "limit: 12"),
    ("ls backend/surface/ | grep -i launcher", "self:list", '[self:list]{path: "backend/surface/"}'),
    ('find . -maxdepth 3 -type d -name "android"', "self:file_find", 'pattern: "android", path: "."'),
    ("rm -f data/ibl_usage.db", "self:delete", '[self:delete]{path: "data/ibl_usage.db"}'),
    ('echo "hi" > data/outputs/x.txt', "self:write", '[self:write]{path: "data/outputs/x.txt"'),
    ('sqlite3 data/world_pulse.db "select 1"', "sense:sqlite", 'query: "select 1"'),
    ("sed -i '' 's/a/b/' data/guides/x.md", "self:edit", 'path: "data/guides/x.md"'),
    ("cp data/a.txt data/b.txt", "self:copy", 'src: "data/a.txt", dest: "data/b.txt"'),
    # 몸 자신의 리로드 API 를 셸로 두드리는 꼴(ep2904 ×4) — url_contains 가 curl 을 이 경로에서만 그림자로
    ('curl -s -X POST http://localhost:8765/packages/reload -o /dev/null -w "%{http_code}\n"', "self:package",
     '[self:package]{op: "reload"}'),
    ("curl -s -X POST http://127.0.0.1:8765/packages/reload -H 'Content-Type: application/json' | head -c 400",
     "self:package", '[self:package]{op: "reload"}'),
])
def test_s2_shadow_commands_denied_with_translation(cmd, word, frag):
    v = _judge(cmd)
    assert v and f"[{word}]" in v, (cmd, v)
    assert frag in v, (cmd, v)


# ---------------------------------------------------------------- S3 셸의 몫은 통과
@pytest.mark.parametrize("cmd", [
    "git -C /x log --oneline -3",
    "git diff data/x.py | grep '^-' | head",
    ".venv/bin/python -m pytest backend/test_x.py -q",
    "python3 scripts/build_ibl_nodes.py --check 2>&1 | tail -5",
    "curl -s http://127.0.0.1:8765/health",
    "echo hi > /tmp/x.txt",
    "cat /tmp/x.txt",
    "ls /tmp",
    "wc -l backend/surface/*.py",
    "python3 - <<'EOF'\nimport json\nd=json.load(open('data/training/x.json'))\nprint(len(d))\nEOF",
    "cd /Users/x && echo ok 2>/dev/null",
])
def test_s3_shell_own_work_passes(cmd):
    assert _judge(cmd) is None, cmd


# ---------------------------------------------------------------- S2b fd 리다이렉션은 인자가 아니다
@pytest.mark.parametrize("cmd, good, bad", [
    ("ls -d /Applications/Blender.app 2>/dev/null", 'path: "/Applications/Blender.app"', '"2"'),
    ("tail -5 data/script_runs/x.log 2>&1", 'tail: 5, path: "data/script_runs/x.log"', '"2"'),
    ("cat -n backend/x.py 2> /dev/null", 'numbered: true, path: "backend/x.py"', '"2"'),
])
def test_s2b_fd_redirect_digit_not_an_argument(cmd, good, bad):
    """ep2904: 거절문이 path: ["…", "2"] 를 가르쳐 재시도 문장을 틀리게 했다."""
    v = _judge(cmd)
    assert v and good in v, (cmd, v)
    assert bad not in v, (cmd, v)


# ---------------------------------------------------------------- S4 파일을 쓰는 파이썬
def test_s4_inline_python_that_writes_is_edit_shadow(tmp_path):
    v = _judge("python3 - <<'EOF'\nimport pathlib\np=pathlib.Path('data/guides/x.md'); p.write_text('x')\nEOF")
    assert v and "[self:edit]" in v and "start_line" in v
    # 같은 명령 안에서 히어독으로 쓰고 바로 돌리는 꼴(ep2862) — 파일이 아직 없어도 본문을 본다
    v2 = _judge("cat > /tmp/_probe_rm.py <<'PYEOF'\nimport pathlib\npathlib.Path('data/x.yaml').write_text('')\nPYEOF\npython3 /tmp/_probe_rm.py --apply")
    assert v2 and "[self:edit]" in v2
    # 임시 폴더에 이미 있는 스크립트도 본문을 본다
    script = tmp_path / "w.py"
    script.write_text("open('data/x.txt','w').write('x')\n", encoding="utf-8")
    assert _judge(f"python3 {script} --apply") and "[self:edit]" in _judge(f"python3 {script} --apply")
    script.write_text("print(open('data/x.txt').read())\n", encoding="utf-8")
    assert _judge(f"python3 {script}") is None


# ---------------------------------------------------------------- S5 네이티브 Write/Edit
def test_s5_native_write_edit_gated_by_path():
    v = G.judge_native("Edit", {"file_path": os.path.join(ROOT, "backend", "x.py"), "old_string": "a", "new_string": "b"},
                       cwd=ROOT, root=ROOT, table=_TABLE)
    assert v and "[self:edit]" in v and "old_string" in v
    w = G.judge_native("Write", {"file_path": os.path.join(ROOT, "data", "outputs", "x.md"), "content": "a"},
                       cwd=ROOT, root=ROOT, table=_TABLE)
    assert w and "[self:write]" in w
    assert G.judge_native("Write", {"file_path": "/tmp/x.py", "content": "a"}, cwd=ROOT, root=ROOT, table=_TABLE) is None
    assert G.judge_native("Bash", {"command": "ls"}, cwd=ROOT, root=ROOT, table=_TABLE) is None


# ---------------------------------------------------------------- S6 실행기 배선 + 훅 진입
def test_s6_claude_code_command_carries_hook_and_main_denies():
    from providers.claude_code import ClaudeCodeProvider as P
    inst = object.__new__(P)
    inst._binary_path = "claude"; inst.model = None; inst.system_prompt = "S"
    cmd = inst._build_command(stream=True, mcp_config_path="/tmp/x.json")
    settings = json.loads(cmd[cmd.index("--settings") + 1])
    hook = settings["hooks"]["PreToolUse"][0]
    assert hook["matcher"] == P.SHADOW_HOOK_MATCHER and "shell_shadow_gate.py" in hook["hooks"][0]["command"]
    assert "--settings" not in inst._build_command(stream=False, mcp_config_path=None, tools_mode="none")
    assert "그림자 관문" in P.TOOL_POLICY
    # 지문이 훅을 포함한다
    blob_fp = P.tool_policy_fingerprint()
    old = P.SHADOW_HOOK_MATCHER
    try:
        P.SHADOW_HOOK_MATCHER = old + "|Probe"
        assert P.tool_policy_fingerprint() != blob_fp
    finally:
        P.SHADOW_HOOK_MATCHER = old
    # 훅 __main__: 거절 = exit 2 + stderr 사유 / 통과 = exit 0
    gate = os.path.join(BACKEND, "base", "shell_shadow_gate.py")
    ev = {"tool_name": "Bash", "tool_input": {"command": "grep -rn x data/"}, "cwd": ROOT}
    p = subprocess.run([sys.executable, gate, ROOT], input=json.dumps(ev), capture_output=True, text=True)
    assert p.returncode == 2 and "[self:grep]" in p.stderr
    ev["tool_input"]["command"] = "git status --short"
    p = subprocess.run([sys.executable, gate, ROOT], input=json.dumps(ev), capture_output=True, text=True)
    assert p.returncode == 0 and not p.stderr


# ---------------------------------------------------------------- S7 in-process run_command
def test_s7_run_command_uses_same_judge():
    H = _ess("handler")

    class Ctx:
        tool_name = "run_command"; project_path = ROOT; agent_id = "probe"
    out = json.loads(H.execute({"command": "grep -rn 'def run' data/packages"}, Ctx()))
    assert out["success"] is False and out.get("error_type") == "shell_shadow" and "[self:grep]" in out["error"]


# ---------------------------------------------------------------- S8 절단 뒤 다음 걸음
def test_s8_truncated_marker_carries_next_step():
    from ibl_honesty import describe_promoted, TRUNCATED_NEXT_STEP
    assert TRUNCATED_NEXT_STEP in describe_promoted(["truncated"])
    assert TRUNCATED_NEXT_STEP not in describe_promoted(["passthrough_rows"])


# ---------------------------------------------------------------- S9 낱말 상위집합
def test_s9_grep_context_ignore_case_read_numbered_tail_edit_range(tmp_path):
    G2 = _ess("fs_grep")
    (tmp_path / "a.py").write_text("l1\nl2\nNEEDLE here\nl4\nl5\nneedle lower\n", encoding="utf-8")
    r = json.loads(G2.run({"pattern": "NEEDLE", "path": str(tmp_path), "context": 1}, str(tmp_path)))
    assert r["items"][0]["문맥"] == "2  l2\n3> NEEDLE here\n4  l4"
    assert "a.py-2- l2" in r["text"] and "a.py:3: NEEDLE here" in r["text"]
    r = json.loads(G2.run({"pattern": "needle", "path": str(tmp_path), "ignore_case": True, "output_mode": "count"}, str(tmp_path)))
    assert r["items"][0]["매칭 수"] == 2
    r = json.loads(G2.run({"pattern": "니들없음", "path": str(tmp_path), "ignore_case": True, "context": 2}, str(tmp_path)))
    assert r["total"] == 0
    E = _ess("fs_edit")
    assert E.replace_line_range("a\nb\nc\nd\ne\n", 2, 4, "") == {"content": "a\ne\n", "note": "줄 2~4(3줄) 삭제"}
    assert E.replace_line_range("a\nb\nc\n", 2, 2, "X\nY")["content"] == "a\nX\nY\nc\n"
    assert "error" in E.replace_line_range("a\nb\n", 1, 1, "X", old_string="zzz")
    assert "error" in E.replace_line_range("a\nb\n", 5, 5, "X")
    H = _ess("handler")
    p = tmp_path / "t.txt"
    p.write_text("a\nb\nc\nd\ne\n", encoding="utf-8")

    class Ctx:
        tool_name = "read_op"; project_path = str(tmp_path); agent_id = "probe"
    out = H.execute({"path": str(p), "numbered": True, "tail": 2}, Ctx())
    assert out.startswith("[줄 4-5 / 전체 5줄") and "4\td\n5\te\n" in out
    Ctx.tool_name = "edit_file"
    out = H.execute({"path": str(p), "start_line": 2, "end_line": 3, "new_string": ""}, Ctx())
    assert "줄 2~3(2줄) 삭제" in out and p.read_text(encoding="utf-8") == "a\nd\ne\n"
    out = H.execute({"path": str(p), "new_string": "z"}, Ctx())
    assert out.startswith("Error: old_string 또는 start_line")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
