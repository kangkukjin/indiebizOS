"""[self:script] 백그라운드 진행 가시성 관문 (2026-09-10).

실사고: 나레이션생성(콜랩 T4, 165조각)이 55분 도는 동안 status 폴링이 26라운드 내내 'running' 만
돌려받았다. 러너가 stdout/stderr 를 파이프에 가둬 끝날 때 한 번에 쓰고, 로그 파일은 종료 뒤에야
생겼기 때문. 처방 = 러너가 stderr 를 로그에 **실시간**으로 흘리고, status 가 그 꼬리를 `progress` 로 싣는다.

관문 3:
  1. 실행 중 로그 파일에 스크립트의 stderr 진행 줄이 **끝나기 전에** 보인다.
  2. op_status 가 running 행에 progress(마지막 줄들)를 싣는다.
  3. 끝난 뒤 로그는 옛 형식(`# id exit=… / --- stdout --- / --- stderr ---`) 그대로다 — 옛 독자 보존.
  + 나레이션생성.py 의 원격 코드가 프롬프트를 1회만 만들고 배치로 부르는지(구조 관문).
"""
import ast
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boot_paths  # noqa: E402,F401

_ROOT = Path(__file__).resolve().parent.parent
_PKG = _ROOT / "data" / "packages" / "installed" / "tools" / "system_essentials"
_RUNNER = _PKG / "_bg_runner.py"

spec = importlib.util.spec_from_file_location("script_ops_progress_t", _PKG / "script_ops.py")
S = importlib.util.module_from_spec(spec)
spec.loader.exec_module(S)

_SLOW = """\
import sys, time, json
for i in range(1, 4):
    print(f"[진행] {i}/3", file=sys.stderr, flush=True)
    time.sleep(0.6)
print(json.dumps({"items": [{"title": "끝"}], "message": "완료"}))
"""


def _job(tmp_path, timeout=30):
    script = tmp_path / "slow.py"
    script.write_text(_SLOW, encoding="utf-8")
    job_dir = tmp_path / "jobs"
    job_dir.mkdir()
    job_id = "slow-20260910_000000"
    log = tmp_path / f"{job_id}.log"
    job = {"job_id": job_id, "id": "slow", "status": "starting", "started_at": "2026-09-10T00:00:00",
           "timeout": timeout, "log": str(log), "interpreter": sys.executable, "script": str(script),
           "stdin": None}
    job_path = job_dir / f"{job_id}.json"
    job_path.write_text(json.dumps(job, ensure_ascii=False), encoding="utf-8")
    return job_path, log, job_dir


def test_러너가_stderr_를_실시간으로_로그에_흘린다(tmp_path):
    job_path, log, _ = _job(tmp_path)
    p = subprocess.Popen([sys.executable, str(_RUNNER), str(job_path)],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        seen_live = None
        deadline = time.time() + 5
        while time.time() < deadline:
            if log.exists() and "[진행] 1/3" in log.read_text(encoding="utf-8"):
                seen_live = json.loads(job_path.read_text(encoding="utf-8"))["status"]
                break
            time.sleep(0.1)
        assert seen_live == "running", "끝나기 전에 진행 줄이 로그에 보여야 한다"
        p.wait(timeout=15)
    finally:
        if p.poll() is None:
            p.kill()
    final = log.read_text(encoding="utf-8")
    assert re.match(r"# slow-20260910_000000 exit=0 \d+ms\n--- stdout ---\n", final), final[:120]
    assert "--- stderr ---\n" in final and "[진행] 3/3" in final.split("--- stderr ---", 1)[1]
    job = json.loads(job_path.read_text(encoding="utf-8"))
    assert job["status"] == "done" and job["result"]["items"][0]["title"] == "끝"


def test_status_가_running_행에_progress_를_싣는다(tmp_path, monkeypatch):
    job_path, log, job_dir = _job(tmp_path)
    monkeypatch.setattr(S, "_JOB_DIR", job_dir)
    monkeypatch.setattr(S, "_pid_alive", lambda pid: True)
    job = json.loads(job_path.read_text(encoding="utf-8"))
    job.update({"status": "running", "runner_pid": os.getpid()})
    job_path.write_text(json.dumps(job, ensure_ascii=False), encoding="utf-8")
    # 러너가 쓰는 살아있는 로그 모양
    log.write_text("# slow-20260910_000000 running since 2026-09-10T00:00:00\n"
                   "--- stderr (진행, 실시간) ---\n[   12s] 콜랩 세션 여는 중\n[  300s] [gen] 40/165 …\n",
                   encoding="utf-8")
    res = S.op_status({"job_id": "slow-20260910_000000"})
    assert res["success"] and res["status"] == "running"
    assert res["items"][0]["progress"] == ["[   12s] 콜랩 세션 여는 중", "[  300s] [gen] 40/165 …"]
    assert res["text"].endswith("[  300s] [gen] 40/165 …")
    # 로그가 아직 없으면 progress 키 자체가 없다(빈 배열로 속이지 않는다)
    log.unlink()
    res = S.op_status({"job_id": "slow-20260910_000000"})
    assert "progress" not in res["items"][0]


def _remote_code():
    src = (_ROOT / "data" / "scripts" / "나레이션생성.py").read_text(encoding="utf-8")
    return re.search(r"REMOTE = r'''(.*?)'''", src, re.S).group(1)


def test_나레이션_원격코드_프롬프트_1회_배치_진행줄():
    """구조 관문: 조각마다 참조 음성을 다시 인코딩하던 뿌리(165회)가 되돌아오지 않게."""
    tree = ast.parse(_remote_code())
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)]
    names = [c.func.attr for c in calls]
    assert names.count("create_voice_clone_prompt") == 1
    gen = [c for c in calls if c.func.attr == "generate_voice_clone"]
    assert len(gen) == 1
    kws = {k.arg for k in gen[0].keywords}
    assert "voice_clone_prompt" in kws and "ref_audio" not in kws, "호출마다 ref_audio 를 다시 주면 프롬프트 재계산"
    # 프롬프트 생성은 루프 밖(모듈 최상위)이어야 한다
    top = {type(n) for n in tree.body}
    prompt_assign = [n for n in tree.body if isinstance(n, ast.Assign)
                     and any(isinstance(t, ast.Name) and t.id == "prompt" for t in n.targets)]
    assert prompt_assign, "prompt = create_voice_clone_prompt(...) 가 최상위에 있어야 한다"
    src = _remote_code()
    assert 'job.get("batch")' in src and "out.tar" in src and "모델 적재 완료" in src


def test_나레이션_예산은_글자수_실측속도_캡_이고_감시는_무소식(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/true")
    spec2 = importlib.util.spec_from_file_location("narr_t", _ROOT / "data" / "scripts" / "나레이션생성.py")
    N = importlib.util.module_from_spec(spec2)
    spec2.loader.exec_module(N)
    assert N.DEFAULT_BATCH >= 2 and 0 < N.SEC_PER_CHAR < 2 and N.STALL_GEN < N.LOAD_BUDGET + N.STALL_LOAD
    main_src = ast.get_source_segment(Path(N.__file__).read_text(encoding="utf-8"),
                                      next(n for n in ast.parse(Path(N.__file__).read_text(encoding="utf-8")).body
                                           if isinstance(n, ast.FunctionDef) and n.name == "main"))
    assert "SEC_PER_CHAR * total_chars" in main_src and "len(jobs)" not in main_src.split("cap = ")[1].split("\n")[0]
    assert "run_exec_streaming" in main_src
    pieces = N.split_sentences("가. 나. 다.", max_chars=5)
    assert pieces == ["가. 나.", "다."]


def test_나레이션_토큰갱신은_회수_앞과_정리_앞에_있다(monkeypatch):
    """09-10 실사고: 세션 토큰 1시간 만료 → 55분 생성 뒤 download·정리·stop 전부 401. VM 은 켜진 채 남았다.
    갱신 호출이 (a) 회수(download) 앞 (b) finally 의 정리·stop 앞에 있어야 한다 — 순서를 소스 위치로 본다."""
    src = (_ROOT / "data" / "scripts" / "나레이션생성.py").read_text(encoding="utf-8")
    main_src = src[src.index("def main("):]
    i_refresh = main_src.index("refresh_session_token()")
    i_download = main_src.index('"download"')
    assert i_refresh < i_download, "회수 앞에 토큰 갱신이 없다"
    fin = main_src[main_src.index("finally:"):]
    assert fin.index("refresh_session_token()") < fin.index('"stop"'), "정지 앞에 토큰 갱신이 없다"
    assert "list_assignments" in src and "token_expires_in_seconds" in src


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
