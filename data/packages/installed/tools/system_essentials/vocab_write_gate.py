"""vocab_write_gate.py — 어휘 빌드 입력 쓰기의 초크포인트 (쓰기 순간 = 빌드 의무 발생 시점)

★왜 (2026-09-01, ep2519 사슬 수리): 어휘의 대부분(패키지 액션)이 RED 구역 밖에 살아,
빌드 의무가 가이드 문장(new_action_checklist.md)에만 얹혀 있었다 — 07-03 설계 문서
(SELF_MODIFICATION_SAFETY_DESIGN.md §6)가 "Phase 2 범위"로 미룬 잔여 위험 그대로.
ep2519 는 그 틈에서 어휘를 고치고도 파생물(ibl_nodes.yaml·tool.json)이 낡은 채 턴이
끝났다 — 시스템이 제 낱말을 못 보는 조용한 부정합.

두 안전판을 여기서 든다(허가 술어는 넓히지 않는다 — 안전판 술어만):
  1. syntax_guard  — 이 몸의 패키지 .py 쓰기 전 compile() 사전검증(그랜트 무관).
     깨진 handler.py 는 브릭이 아니라 "그 도구가 조용히 사라지는" 부정합을 만든다.
  2. enforce_on_write — 라이브 빌드 입력에 쓴 직후 sync_live_derived(재생성 집행).
     무엇이 트리거인지는 손으로 고르지 않고 빌더(--inputs-regex)에게 묻는다.

격리 사본 쓰기는 2에 안 걸린다 — verify/apply/discard 가 같은 관문을 이미 문다.
copy(폴더)·move·delete 는 이 초크포인트 밖이다: 부팅·일일점검 순찰(파생물 신선도)이
그 잔여를 덮는다. 정본: docs/SELF_MODIFICATION_SAFETY_DESIGN.md §6.
"""
import os
import re
import subprocess
import sys

_PATTERN_CACHE = {}   # repo → compiled regex | None (핸들러 리로드가 캐시 수명)


def _inputs_pattern(repo: str):
    """빌더의 입력 정규식 — 트리거의 단일 출처는 빌더다(hand-picked-sweep 부류 방지)."""
    pat = _PATTERN_CACHE.get(repo, "__miss__")
    if pat != "__miss__":
        return pat
    build = os.path.join(repo, "scripts", "build_ibl_nodes.py")
    pat = None
    if os.path.exists(build):
        try:
            py = sys.executable or "python3"
            r = subprocess.run([py, build, "--inputs-regex"], cwd=repo,
                               capture_output=True, text=True, timeout=30)
            if r.returncode == 0 and (r.stdout or "").strip():
                pat = re.compile(r.stdout.strip().splitlines()[-1])
        except (OSError, re.error, subprocess.SubprocessError):
            pat = None
    _PATTERN_CACHE[repo] = pat
    return pat


def syntax_guard(real_path: str, new_content, body_root_of, repo_root) -> str | None:
    """이 몸(라이브·격리 사본 포함)의 패키지 .py 쓰기 전 구문검증. 거부면 메시지, 아니면 None.

    body_root_of = red_zone_family 의 가족 판정(단일 출처를 빌리지 복제하지 않는다)."""
    try:
        if not (repo_root and real_path.endswith(".py") and isinstance(new_content, str)):
            return None
        root = body_root_of(real_path, repo_root)
        if root is None:
            return None          # 이 몸 밖 — 남의 저장소는 종전대로
        rel = os.path.relpath(real_path, root).replace(os.sep, "/")
        if not rel.startswith("data/packages/"):
            return None          # RED .py 는 _red_write_prepare 의 기존 검증이 문다
        compile(new_content, real_path, "exec")
        return None
    except SyntaxError as e:
        return (f"Error: 패키지 쓰기 거부 — 새 내용에 파이썬 구문 오류가 있습니다: "
                f"line {e.lineno}: {e.msg}\n수정 후 다시 시도하세요(파일은 무변경).")
    except Exception:
        return None              # 판정 실패는 쓰기를 막지 않는다 — 순찰이 잔여를 덮는다


def note(rec) -> str:
    """관문 레코드의 한 줄 보고 — 문자열을 돌려주는 op(edit/copy)의 꼬리에 붙인다."""
    return ("\n[live_derived] " + ("✓ " if rec.get("passed") else "✗ ")
            + str(rec.get("detail") or "")[:600])


def enforce_on_write(repo: str, path: str, staging, is_live):
    """라이브 빌드 입력에 쓴 직후 호출 — 해당 없으면 None, 해당하면 live_derived 관문 레코드.

    staging = repair_staging 모듈(sync_live_derived 의 집), is_live = handler 의
    _red_is_live_path(격리 사본 판정의 단일 출처)."""
    try:
        if not repo:
            return None
        real = os.path.realpath(path)
        if not is_live(real):
            return None          # 격리 사본 — verify/apply/discard 가 문다
        rel = os.path.relpath(real, os.path.realpath(repo)).replace(os.sep, "/")
        if rel.startswith(".."):
            return None
        pattern = _inputs_pattern(repo)
        if pattern is None or not pattern.match(rel):
            return None
        return staging.sync_live_derived(repo)
    except Exception as e:
        return {"gate": "live_derived", "passed": False, "regenerated": [],
                "detail": f"쓰기 지점 빌드 집행 실패: {e}"}
