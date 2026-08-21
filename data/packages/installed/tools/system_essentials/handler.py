import os
import sys
import glob
import re
import time
import fnmatch
import unicodedata
import subprocess
import shlex
import shutil
import json
from datetime import datetime
from pathlib import Path
import importlib.util

_CURRENT_DIR = Path(__file__).parent


def _load_sibling(module_name):
    """패키지 형제 모듈 spec-load (real-estate load_module 선례)."""
    spec = importlib.util.spec_from_file_location(module_name, _CURRENT_DIR / f"{module_name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# file_find 무경계 재귀 glob 방지 — 매 호출 홈 전체(node_modules·캐시)를 색인 없이
# stat 하던 게 타임아웃 원인. 절대-dead 가지치기 + 시간 예산으로 바운드.
# ★ 절대-dead 목록은 file_index(포식 substrate)와 *공유* — fs_query 와 같은 단일 출처라
#   드리프트 없음. path-substring 판정이라 ~/Library 통째가 아니라 캐시류만 쳐냄(iCloud 보존).
try:
    from file_index import ABSOLUTE_DEAD_SUBSTR as _DEAD_SUBSTR
except Exception:  # import 경로 미확보 시 폴백(동일 내용)
    _DEAD_SUBSTR = (
        "/System/", "/Applications/", "/Library/Caches/",
        "/Library/Application Support/", "/Library/Containers/",
        "/Library/Group Containers/", "/node_modules/", "/.Trash", ".app/",
        "/__pycache__/", "/site-packages/", "/.venv/", "/venv/",
        "/.git/", "/DerivedData/", "/.gradle/", "/.cargo/", "/.npm/",
    )
_FIND_DEADLINE_S = 25.0  # 엔진 타임아웃 전에 부분결과라도 반환


# ── 파이프 통화 → 파일 복사 ────────────────────────────────────────────────
# "몇 장을 어디에 저장" 은 새 동사가 아니라 *조합*이다 — 고르는 일은 앞 액션과 table
# 변환자가 하고(take/filter/sort), copy 는 받은 것을 그대로 옮긴다.
#   [self:photo]{source:"usb"} >> [table:take]{n:10} >> [self:copy]{dest:"~/Desktop/폰사진"}

def _piped_items(prev_result) -> list:
    """파이프로 온 결과에서 items 목록 추출 (문자열 JSON·dict·list 전부 관용)."""
    data = prev_result
    if isinstance(data, str):
        if not data.strip():
            return []
        try:
            data = json.loads(data)
        except (ValueError, TypeError):
            return []
    if isinstance(data, dict):
        data = data.get("items") or data.get("records") or []
    return [it for it in data if isinstance(it, dict)] if isinstance(data, list) else []


def _copy_piped_items(tool_input: dict, dest: str, project_path: str) -> str:
    """파이프로 온 items 의 파일들을 dest *폴더* 로 복사 (실제 복사는 file_index 단일 소스)."""
    items = _piped_items(tool_input.get("_prev_result"))
    if not items:
        return ("Error: 복사할 항목이 없습니다. src(원본 경로)를 주거나, "
                "앞 액션의 결과를 >> 로 넘기세요.")

    dst_dir = os.path.join(project_path, os.path.expanduser(dest))
    scope_err = _validate_path_in_scope(dst_dir, project_path)
    if scope_err:
        return scope_err

    import file_index
    res = file_index.save_media_files(items, dst_dir)
    saved, failed = res.get("saved") or [], res.get("failed") or []
    if res.get("error"):
        return f"Error: {res['error']}"
    if not saved and not failed:
        return "Error: 항목에 파일 경로가 없습니다 (path 필드 필요)."
    msg = f"{len(saved)}개 파일을 저장했습니다: {res.get('dest')}"
    if saved:
        msg += "\n  " + ", ".join(saved[:5]) + (f" 외 {len(saved) - 5}개" if len(saved) > 5 else "")
    if failed:
        msg += f"\n실패 {len(failed)}개: " + "; ".join(failed[:3])
    return msg


def _is_dead_dir(path):
    """절대-dead(설치트리·캐시) 디렉토리면 True — walk 가 안 들어감(의도 불문 제외)."""
    p = path.rstrip("/") + "/"
    return any(n in p for n in _DEAD_SUBSTR)



def _bounded_find(root, basename_pat, max_results):
    """root 하위를 바운드 재귀 순회 — 정크 가지치기 + dot-dir 스킵(glob ** 와 동일) + 시간 예산.

    무한정 walk 로 시스템을 멈추지 않는다. 시간 초과/상한 도달 시 partial=True 로 알린다.
    """
    deadline = time.time() + _FIND_DEADLINE_S
    # macOS 한글 파일명=NFD(자모분해), 패턴은 보통 NFC → fnmatch 바이트비교가 침묵 누락.
    # 양쪽을 NFC 로 정규화해 비교(mdfind 는 정규화하지만 fnmatch 는 안 함. forage_map #33).
    pat = unicodedata.normalize("NFC", basename_pat)
    pat_lower = pat.lower()
    matches, partial = [], False
    for dirpath, dirs, files in os.walk(root, topdown=True):
        if time.time() > deadline:
            partial = True
            break
        # 가지치기: 절대-dead(공유 목록, path-substring) + dot-dir. 제자리 수정으로 walk 가 안 들어감.
        #   ~/Library 통째가 아니라 캐시류만 → ~/Library/Mobile Documents(iCloud) 는 보존.
        dirs[:] = [d for d in dirs
                   if not d.startswith(".") and not _is_dead_dir(os.path.join(dirpath, d))]
        # 매칭: 파일 + 디렉토리 둘 다 (glob.glob 은 둘 다 매칭했음 — 예: .epub 번들·iCloud 책은 디렉토리).
        # macOS 파일시스템은 대소문자 무시 → 소문자 비교로 맞춤.
        for name in files + dirs:
            nfc = unicodedata.normalize("NFC", name)
            if fnmatch.fnmatch(nfc.lower(), pat_lower):
                matches.append(os.path.join(dirpath, name))
                if len(matches) >= max_results:
                    return matches, True
    return matches, partial

# 시스템 AI 전용 상태 폴더 (data/system_ai_state/)
DATA_PATH = Path(__file__).parent.parent.parent.parent
SYSTEM_AI_STATE_PATH = DATA_PATH / "system_ai_state"


def get_state_paths(project_path: str, agent_id: str = None) -> dict:
    """에이전트별 상태 파일 경로 반환

    - 시스템 AI: data/system_ai_state/
    - 프로젝트 에이전트: projects/{project_id}/agent_{agent_id}_*.json
    """
    project_path = Path(project_path).resolve()

    # 시스템 AI인지 확인 (project_path가 data 폴더 또는 "."인 경우)
    if str(project_path).endswith("data") or project_path == Path(".").resolve():
        state_dir = SYSTEM_AI_STATE_PATH
        prefix = ""
    else:
        # 프로젝트 에이전트는 프로젝트 폴더에 상태 저장
        state_dir = project_path
        # 에이전트별 파일명 접두사 (agent_id가 있으면 사용)
        prefix = f"agent_{agent_id}_" if agent_id else ""

    # 폴더 생성
    state_dir.mkdir(parents=True, exist_ok=True)

    return {
        "todo": state_dir / f"{prefix}todo_state.json",
        "question": state_dir / f"{prefix}question_state.json",
        "plan_mode": state_dir / f"{prefix}plan_mode_state.json",
        "plan_file": state_dir / f"{prefix}current_plan.md"
    }


# 위험한 명령어 패턴 (정규식, 사용자 승인 필요)
# 단어 경계(\b)를 사용하여 'add'에서 'dd'가 매칭되는 등의 오탐 방지
import re

DANGEROUS_PATTERNS_RE = [
    # 파일 삭제/수정
    r'\brm\s', r'\brmdir\b', r'\bunlink\b',
    # 권한 관련
    r'\bsudo\b', r'\bchmod\b', r'\bchown\b', r'\bchgrp\b',
    # 디스크 관련 위험 명령어
    r'\bdd\s', r'\bmkfs\b', r'\bformat\b', r'\bdiskutil\s+erase\b', r'\bdiskutil\s+partitionDisk\b',
    # 시스템 종료/재시작
    r'\bshutdown\b', r'\breboot\b', r'\bhalt\b',
    # 프로세스 종료
    r'\bkill\s', r'\bkillall\b', r'\bpkill\b',
]

_DANGEROUS_RE = re.compile('|'.join(DANGEROUS_PATTERNS_RE), re.IGNORECASE)


# ── 자기개조 안전장치 Floor #1: RED 구역(살아있는 기질) 직접 쓰기 차단 ──
# docs/SELF_MODIFICATION_SAFETY_DESIGN.md. 이 핸들러가 돌고 있는 코어 코드(backend/·
# frontend/·scripts/)를 IBL 매개 쓰기가 직접 덮어쓰면 자해(uvicorn reload 가 개조 중인
# 호출 자체를 절단)·관찰자 오염(자기채점 ACHIEVED)이 난다(에피소드 551 실측). 규칙:
# 개조는 data/ 차원(어휘·yaml·상태)에서 끝내거나, 코어가 정말 필요하면 사람에게 제안.
# repo 루트는 backend+frontend 동시 존재로 독립 탐지 — 설치 위치·경로 깊이에 안 흔들림.
def _find_repo_root():
    p = Path(__file__).resolve()
    for anc in p.parents:
        if (anc / "backend").is_dir() and (anc / "frontend").is_dir():
            return anc
    return None  # 미탐지 시 RED 가드 fail-open(정상 쓰기를 막지 않음 > 안전 과잉)

_REPO_ROOT = _find_repo_root()
_RED_ZONE_DIRS = ("backend", "frontend", "scripts")
# 사람 전용 승인 상태 파일 — 에이전트가 IBL 파일 쓰기로 자가승인하면 게이트가 무의미해진다.
# ([self:install_lib] 공급망 방어 게이트. 승인 채널은 HTTP /install-approvals/* 뿐.)
_PROTECTED_STATE_FILES = ("data/system_ai_state/install_approvals.json",)


# 게이트 자신 — RED 밖(data/)에 살지만 안전장치의 집이라 그랜트 없이는 못 쓴다
# (③검증자 없는 영역 보강, 2026-08-05: 게이트를 지키는 게이트).
_SELF_FILE = os.path.realpath(__file__)


def _safety_watch_files():
    """수정 시 워치독이 기능 스모크(red_safety_selftest)까지 돌려야 하는 안전장치 파일들."""
    out = {_SELF_FILE}
    if _REPO_ROOT is not None:
        for rel in ("backend/datastore/red_grant.py", "backend/datastore/red_watchdog.py",
                    "scripts/red_safety_selftest.py"):
            out.add(os.path.realpath(str(_REPO_ROOT / rel)))
    return out


def _red_grant_active():
    """현재 호출 컨텍스트에 유효한 RED 쓰기 그랜트(헌법 2026-08-05).

    그랜트는 인지 파이프라인의 REPAIR 경로만 발급한다(사람 명령 + 고급 모델 + 의식 각성).
    red_grant 모듈 부재(폰 몸 등)·컨텍스트 부재 시 None = fail-closed."""
    try:
        from red_grant import active_grant
        from thread_context import get_current_task_id, get_current_agent_id
        return active_grant(task_id=get_current_task_id(), agent_id=get_current_agent_id())
    except Exception:
        return None


def _is_static_asset(real: str) -> bool:
    """backend/static/ 아래 비-파이썬 정적 자산인가 — RED 면제 대상.
    프로세스가 import 하지 않고 요청마다 디스크에서 읽어 서빙하므로 reload 절단이
    원리적으로 불가능하다(2026-08-05 구역 재구획 — 자막 수리 하루 지연의 교훈)."""
    if _REPO_ROOT is None:
        return False
    static_root = str(_REPO_ROOT / "backend" / "static")
    return ((real == static_root or real.startswith(static_root + os.sep))
            and not real.endswith(".py"))


def _red_zone_violation(abs_path: str) -> str | None:
    """쓰기 대상 실경로가 RED 구역이면 거부 메시지, 아니면 None.
    realpath 로 정규화 → 심볼릭·../ 우회(data/../backend/…)까지 잡는다.

    헌법 개정(2026-08-05): 사람 승인 게이트(Floor #4) 폐기. 대신
    ①사람 명령 태스크 ②고급 모델 ③의식 각성으로 발급된 그랜트(red_grant)가 있으면
    RED 직접 쓰기를 허용한다 — 쓰기 지점의 기계 안전판(사전 구문검증·백업·워치독
    자동 롤백)이 함께 작동한다. backend/static/ 비-py 정적 자산은 RED 가 아니다."""
    if _REPO_ROOT is None:
        return None
    real = os.path.realpath(abs_path)
    for pf in _PROTECTED_STATE_FILES:
        if real == str(_REPO_ROOT / pf):
            return (
                f"Error: 사람 전용 승인 상태 파일은 IBL 쓰기가 금지됩니다: {pf}\n"
                f"이 파일은 [self:install_lib] 공급망 방어 게이트의 승인 원장입니다. "
                f"승인·거부는 사용자가 HTTP 채널(/install-approvals/*)로만 합니다."
            )
    # 게이트 자신 변조 보호 — data/ 구역이지만 안전장치의 집이라 그랜트 필요
    if real == _SELF_FILE:
        if _red_grant_active():
            return None
        return (
            "Error: 이 파일은 RED 쓰기 게이트 자신입니다 — 그랜트 없는 수정이 금지됩니다.\n"
            "수정하려면 사용자가 수리 경로('#repair' 또는 '시스템 수리' 명시)로 명령해야 하며, "
            "적용 후 안전장치 기능 스모크(red_safety_selftest)를 통과하지 못하면 자동 롤백됩니다."
        )
    for d in _RED_ZONE_DIRS:
        red_root = str(_REPO_ROOT / d)
        if real == red_root or real.startswith(red_root + os.sep):
            if _is_static_asset(real):
                return None  # 정적 자산 — 살아있는 기질이 아님
            if _red_grant_active():
                return None  # 수리 그랜트 — 쓰기 지점 안전판이 이어받는다
            rel = os.path.relpath(real, str(_REPO_ROOT))
            return (
                f"Error: RED 구역(살아있는 기질) 쓰기가 허가되지 않았습니다: {rel}\n"
                f"시스템 자기수정은 ①사용자가 직접 명령한 태스크에서 ②고급 모델+의식 각성"
                f"(REPAIR 경로)으로만 허용됩니다(헌법 2026-08-05). 지금 태스크는 그 조건 밖입니다.\n"
                f"→ 자율 태스크(스케줄러·자가점검 등)가 발견한 문제면 [self:patch]로 "
                f"제안만 남기세요 — 적용은 사용자가 명령할 때 수리 경로가 수행합니다.\n"
                f"→ 사용자 명령을 수행 중인데 이 게이트에 막혔다면, 사용자에게 '#repair' 태그나 "
                f"'시스템 수리' 명시로 재명령해 달라고 답하세요(수리 경로로 재실행됩니다)."
            )
    return None


# ── RED 쓰기 안전판 (헌법 2026-08-05 기계 안전판, Floor #3+#5) ──────────
# 그랜트된 RED 쓰기의 사전 구문검증(브릭 예방) + 원본 백업 + 분리 워치독(자동 롤백).
# 워치독(backend/red_watchdog.py)은 start_new_session 분리 프로세스라 uvicorn 이
# 깨진 import 로 죽어도 살아남아 백업을 복원하고 touch 로 재기동을 유발한다.

def _red_is_live_path(abs_path: str) -> bool:
    """RED 구역 실경로인가(정적 자산 면제·안전장치 파일 승격 반영). 안전판 적용 대상 판정."""
    if _REPO_ROOT is None:
        return False
    real = os.path.realpath(abs_path)
    if real == _SELF_FILE:
        return True  # 게이트 자신 — data/ 구역이지만 RED 대우(백업·워치독)
    if _is_static_asset(real):
        return False
    for d in _RED_ZONE_DIRS:
        red_root = str(_REPO_ROOT / d)
        if real == red_root or real.startswith(red_root + os.sep):
            return True
    return False


def _keeper_pause(task_key: str):
    """backend/*.py 쓰기 직전 keeper 일시정지 — **표식을 사람이 아니라 기계가 소유한다**.

    ★왜(2026-08-17): 종전 규약은 "작업 전 touch, 작업 후 rm" 이었는데, backend 를
    고치는 주체가 그 backend 안에서 산다(자기수리) — 편집이 부른 리로드가 자기 턴을
    끊어 rm 이 실행되지 못한다. 그래서 규약을 지키려던 수리가 표식만 남기고 멎었다.
    이제 세우는 건 여기가, 회수는 리로드 뒤에도 살아 있는 유일한 손인 워치독이,
    그마저 죽으면 keeper 의 만료(PAUSE_TTL)가 한다 — 사람이 기억할 단계가 없다.
    파일 내용의 'auto' 표시는 소유자 구분용(사람이 손으로 세운 빈 표식은 건드리지 않는다).
    """
    if _REPO_ROOT is None:
        return
    try:
        flag = os.path.join(str(_REPO_ROOT), "data", "backend_keeper_off")
        with open(flag, "w", encoding="utf-8") as f:   # 매 쓰기마다 갱신 = 심장박동
            f.write(f"auto {task_key} {int(time.time())}\n")
    except Exception as e:
        print(f"[RED 안전판] keeper 일시정지 표식 실패(계속 진행): {e}")


def _red_backup_dir(grant: dict) -> str:
    key = re.sub(r"[^A-Za-z0-9_-]", "_", (grant.get("task_id") or "notask"))[:48] or "notask"
    bdir = os.path.join(str(_REPO_ROOT), "data", "system_ai_state", "red_backups", key)
    os.makedirs(bdir, exist_ok=True)
    return bdir


def _red_write_prepare(path: str, new_content=None) -> str | None:
    """그랜트된 RED 쓰기 직전 안전판: (py면) 사전 구문검증 + 원본 백업/매니페스트.
    RED 대상이 아니거나 그랜트가 없으면 no-op(None). 오류 시 거부 메시지 반환."""
    abs_path = os.path.realpath(path)
    if not _red_is_live_path(abs_path):
        return None
    grant = _red_grant_active()
    if not grant:
        return None  # 게이트가 이미 막았을 것 — 방어적 no-op
    # 사전 구문검증 — 깨진 .py 가 라이브에 닿기 전에 거른다(브릭의 대부분 = import 시 SyntaxError)
    if abs_path.endswith(".py") and isinstance(new_content, str):
        try:
            compile(new_content, abs_path, "exec")
        except SyntaxError as e:
            return (f"Error: RED 쓰기 거부 — 새 내용에 파이썬 구문 오류가 있습니다: "
                    f"line {e.lineno}: {e.msg}\n수정 후 다시 시도하세요(라이브 파일은 무변경).")
    # 원본 백업 (파일당 최초 1회 = 진짜 원본 보존) + 매니페스트 갱신
    try:
        bdir = _red_backup_dir(grant)
        manifest_path = os.path.join(bdir, "manifest.json")
        manifest = {}
        if os.path.exists(manifest_path):
            try:
                with open(manifest_path, encoding="utf-8") as f:
                    manifest = json.load(f)
            except Exception:
                manifest = {}
        if not manifest:
            _port = os.environ.get("INDIEBIZ_API_PORT", "8765")
            manifest = {"repo": str(_REPO_ROOT), "task_key": grant.get("task_id") or "notask",
                        "health_url": f"http://127.0.0.1:{_port}/health", "files": {}}
        files = manifest.setdefault("files", {})
        if abs_path not in files:
            if os.path.exists(abs_path):
                backup = os.path.join(bdir, f"f{len(files):03d}_{os.path.basename(abs_path)}")
                shutil.copy2(abs_path, backup)
                files[abs_path] = backup
            else:
                files[abs_path] = None  # 신규 파일 — 롤백 = 삭제
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
        # 매니페스트 mtime 갱신 = 워치독 조용 타이머 리셋(연쇄 편집을 한 검사로 묶음)
    except Exception as e:
        return f"Error: RED 백업 실패로 쓰기를 중단합니다(안전판 없이는 안 쓴다): {e}"
    # 쓰기가 확정된 시점에만 keeper 를 재운다 — backend/*.py 만 리로드를 부른다.
    backend_root = str(_REPO_ROOT / "backend")
    if abs_path.endswith(".py") and abs_path.startswith(backend_root + os.sep):
        _keeper_pause(grant.get("task_id") or "notask")
    return None


def _red_write_finalize(path: str):
    """그랜트된 RED 쓰기 직후: backend .py 와 안전장치 파일은 워치독 보장
    (리로드 후 헬스체크 + 안전장치 파일이면 기능 스모크까지 — 실패 시 자동 롤백).
    그 밖의 frontend/scripts 는 라이브 프로세스가 import 하지 않으므로 백업만으로 충분."""
    abs_path = os.path.realpath(path)
    if not (abs_path.endswith(".py") and _red_is_live_path(abs_path)):
        return
    backend_root = str(_REPO_ROOT / "backend")
    is_backend_py = abs_path == backend_root or abs_path.startswith(backend_root + os.sep)
    if not (is_backend_py or abs_path in _safety_watch_files()):
        return
    grant = _red_grant_active()
    if not grant:
        return
    try:
        bdir = _red_backup_dir(grant)
        manifest_path = os.path.join(bdir, "manifest.json")
        pid_path = os.path.join(bdir, "watchdog.pid")
        if os.path.exists(pid_path):
            try:
                with open(pid_path) as f:
                    os.kill(int(f.read().strip()), 0)
                return  # 워치독 생존 — 매니페스트 mtime 변경이 곧 신호
            except Exception:
                pass
        wd_script = str(_REPO_ROOT / "backend" / "datastore" / "red_watchdog.py")
        log = open(os.path.join(bdir, "watchdog.log"), "ab")
        p = subprocess.Popen([sys.executable, wd_script, manifest_path],
                             stdout=log, stderr=log, start_new_session=True,
                             cwd=str(_REPO_ROOT))
        with open(pid_path, "w") as f:
            f.write(str(p.pid))
        print(f"[RED 안전판] 워치독 기동 (pid={p.pid}) — 헬스체크·자동 롤백 대기")
    except Exception as e:
        print(f"[RED 안전판] 워치독 기동 실패 (백업은 확보됨): {e}")


# ── 수리 격리 스테이징 (2026-08-17) ────────────────────────────────────────
# 그랜트된 RED 쓰기는 라이브가 아니라 **격리 사본(worktree)** 으로 간다 — 스테이징
# 중에는 리로드가 없어 편집자가 자기 턴 안에서 살아 있고, 라이브는 검증을 통과한
# 내용만 [self:patch]{op:"apply"} 로 한 번에 받는다. 로직=repair_staging.py.
# git 이 없는 몸(설치본·폰)에서는 세션이 안 열리고 종전 라이브 직행으로 폴백한다.

def _staging_key():
    """현재 그랜트의 세션 키 — 그랜트가 없으면 None(스테이징 대상 아님)."""
    grant = _red_grant_active()
    if not grant or _REPO_ROOT is None:
        return None
    try:
        return _staging_mod().task_key(grant.get("task_id") or "notask")
    except Exception:
        return None


def _staging_mod():
    mod = _SIBLING_MODS.get("repair_staging")
    if mod is None:
        mod = _SIBLING_MODS["repair_staging"] = _load_sibling("repair_staging")
    return mod


def _red_stage(path: str, for_write: bool) -> str:
    """RED 경로를 격리 사본 경로로 바꾼다(해당될 때만). 아니면 원 경로 그대로.

    for_write=True  : 처음 건드리는 파일이면 라이브 원본에서 씨를 뿌리고 스테이징.
    for_write=False : **이미 스테이징된 파일만** 리다이렉트 — 안 건드린 파일을 읽을 때는
                      라이브를 보여준다(격리 사본이 조사 대상을 왜곡하지 않게)."""
    try:
        if not _red_is_live_path(path):
            return path
        key = _staging_key()
        if not key:
            return path
        repo = str(_REPO_ROOT)
        live_abs = os.path.realpath(path)
        st = _staging_mod()
        if for_write:
            return st.stage_file(repo, key, live_abs) or path
        return st.staged_path(repo, key, live_abs) or path
    except Exception as e:
        print(f"[수리 스테이징] 리다이렉션 실패 — 종전 경로로 진행: {e}")
        return path


def _red_can_stage(path: str) -> bool:
    """세션에 적재 가능한 경로인가 — 이동처럼 **양쪽이 다 되어야** 하는 연산의 선판정.
    한쪽만 적재되면 '원본은 라이브에서 사라졌는데 대상은 격리에만 있는' 반쪽 상태가 된다."""
    try:
        key = _staging_key()
        return bool(key) and _staging_mod().can_stage(str(_REPO_ROOT), key, os.path.realpath(path))
    except Exception:
        return False


def _red_stage_delete(path: str) -> bool:
    """RED 파일 삭제를 세션에 적재(라이브 무변경). False 면 호출자가 종전 라이브 경로로."""
    try:
        key = _staging_key()
        if not key:
            return False
        return _staging_mod().stage_delete(str(_REPO_ROOT), key, os.path.realpath(path))
    except Exception as e:
        print(f"[수리 스테이징] 삭제 적재 실패 — 종전 경로로 진행: {e}")
        return False


_STAGED_NOTE = ("라이브는 무변경입니다(리로드 없음). 검증 후 실제로 반영하려면 "
                "[self:patch]{op:\"apply\"} 를 호출하세요 — 부르지 않으면 이 변경은 "
                "라이브에 없습니다.")


def _validate_path_in_scope(path: str, project_path: str) -> str | None:
    """쓰기 대상 경로가 허용 범위인지 검증. 벗어나면 에러 메시지 반환, 정상이면 None

    두 게이트(순서대로):
    1. RED 구역(backend/·frontend/·scripts/) 직접 쓰기 금지 — 절대/상대 무관(Floor #1).
    2. 상대 경로가 ../로 프로젝트 밖으로 나가는 경우 차단(기존 동작).
    절대 경로는 RED 밖이면 허용(시스템 파일·다른 프로젝트 접근).
    """
    # 게이트 1: RED 구역 — 입력이 절대든 상대든, 최종 실경로로 판정(기존 해석과 동일하게 계산)
    abs_for_red = path if os.path.isabs(path) else os.path.join(project_path, path)
    red = _red_zone_violation(abs_for_red)
    if red:
        return red

    # 게이트 2: RED 통과 후 절대 경로면 허용 (시스템 파일 수정, 다른 프로젝트 파일 접근 등)
    if os.path.isabs(path):
        return None

    # 상대 경로: 프로젝트 범위 안에 있는지 확인
    abs_path = os.path.abspath(os.path.join(project_path, path))
    abs_project = os.path.abspath(project_path)
    if not abs_path.startswith(abs_project + os.sep) and abs_path != abs_project:
        return f"Error: 프로젝트 범위를 벗어나는 상대 경로입니다: {path} → {abs_path}"
    return None


# ── 자기개조 Floor #2: RED 개조의 격리 사본 채널 ──
# docs/SELF_MODIFICATION_SAFETY_DESIGN.md. 로직 본체는 형제 모듈 repair_staging.py
# (1500줄 규칙). 자율 태스크는 op:propose 로 제안만 남기고, 사용자 명령 수리(REPAIR)는
# 스테이징에 쌓인 변경을 op:apply 로 검증 후 라이브에 옮긴다.


def is_dangerous_command(command: str) -> bool:
    """명령어가 위험한지 검사 (정규식 단어 경계 사용)"""
    return bool(_DANGEROUS_RE.search(command))

# _get_path/_truthy/_fill_pdf/_fill_docx 는 office_ops.py 로 이동 (2026-07-18 모듈화).
# _get_path 는 다른 분기(read/write/edit/make_directory/propose_patch)도 쓰므로 별칭 유지.
_office = _load_sibling("office_ops")
_get_path = _office._get_path


# ── op 디스패처 (--check 가 AST 로 키 정확 비교) ──
# 로직은 형제 모듈(webapp_registry.py / sheet_ops.py) — 1500줄 규칙, 본체는 형제에.

_SIBLING_MODS = {}


def _sib_op(module_name, fn_name):
    """형제 모듈 lazy-load op 래퍼 — 첫 호출 때 로드해 캐시."""
    def _call(tool_input):
        mod = _SIBLING_MODS.get(module_name)
        if mod is None:
            mod = _SIBLING_MODS[module_name] = _load_sibling(module_name)
        return getattr(mod, fn_name)(tool_input)
    return _call


def _patch_op(fn_name):
    """repair_staging op 래퍼 — 게이트만 아는 것(repo 루트·RED 판정·쓰기 안전판·
    현재 그랜트 키)을 주입해 넘긴다. 형제 모듈이 RED 구역 정의를 복제하지 않게 하는
    이음매다(구역의 단일 출처는 이 파일의 _red_zone_violation 하나)."""
    def _call(tool_input):
        return getattr(_staging_mod(), fn_name)({
            **tool_input,
            # 별칭 흡수(종전 propose_patch 분기가 하던 것) — 형제 모듈은 정규키만 본다
            "path": _get_path(tool_input),
            "old_string": tool_input.get("old_string") or tool_input.get("old"),
            "new_string": tool_input.get("new_string") or tool_input.get("new"),
            "reason": tool_input.get("reason") or tool_input.get("rationale") or "",
            "_repo_root": str(_REPO_ROOT) if _REPO_ROOT is not None else None,
            "_grant_key": _staging_key(),
            "_red_check": _red_zone_violation,
            "_red_prepare": _red_write_prepare,
            "_red_finalize": _red_write_finalize,
        })
    return _call


_OP_DISPATCHERS = {
    "webapp_op": {
        "list": _sib_op("webapp_registry", "op_list"),
        "status": _sib_op("webapp_registry", "op_status"),
        "register": _sib_op("webapp_registry", "op_register"),
        "remove": _sib_op("webapp_registry", "op_remove"),
    },
    "sheet_op": {
        "find": _sib_op("sheet_ops", "op_find"),
        "append": _sib_op("sheet_ops", "op_append"),
        "update": _sib_op("sheet_ops", "op_update"),
    },
    "script_op": {
        "list": _sib_op("script_ops", "op_list"),
        "register": _sib_op("script_ops", "op_register"),
        "run": _sib_op("script_ops", "op_run"),
        "status": _sib_op("script_ops", "op_status"),
        "remove": _sib_op("script_ops", "op_remove"),
    },
    # 몸 변화 회상 — git 원장을 items 로 (전 op 읽기 전용, 원장은 git 이 쓴다)
    "body_op": {
        "changes": _sib_op("body_ops", "op_changes"),
        "log": _sib_op("body_ops", "op_log"),
        "file": _sib_op("body_ops", "op_file"),
        "writes": _sib_op("body_ops", "op_writes"),
        "diff": _sib_op("body_ops", "op_diff"),
    },
    # 자기개조 패치 생애주기 — 제안(자율 태스크) / 적용·현황·폐기(수리 경로).
    # 안전판 콜백(_red_prepare/_red_finalize)은 게이트가 쥔 채 넘긴다(_patch_op).
    "patch_op": {
        "propose": _patch_op("op_propose"),
        "apply": _patch_op("op_apply"),
        "status": _patch_op("op_status"),
        "discard": _patch_op("op_discard"),
    },
}
_OP_DEFAULTS = {"webapp_op": "list", "sheet_op": "find", "script_op": "list",
                "patch_op": "propose", "body_op": "changes"}


def execute(tool_input: dict, context) -> str:
    """ToolContext 기반 신규 시그니처."""
    tool_name = context.tool_name
    project_path = context.project_path
    agent_id = context.agent_id

    # op 디스패처 액션 ([self:webapp]·[self:sheet] — music-player execute 규약)
    # _project_path(상대경로 해석)·_path_guard(쓰기 범위 검증)를 주입 — 형제 모듈이 소비.
    if tool_name in _OP_DISPATCHERS:
        op = tool_input.get("op") or _OP_DEFAULTS.get(tool_name)
        fn = _OP_DISPATCHERS[tool_name].get(op)
        if fn is None:
            return json.dumps({"success": False,
                               "message": f"알 수 없는 op: {op} (가능: {', '.join(_OP_DISPATCHERS[tool_name])})"},
                              ensure_ascii=False)
        try:
            return json.dumps(fn({**tool_input, "_project_path": project_path,
                                  "_path_guard": _validate_path_in_scope}), ensure_ascii=False)
        except Exception as e:
            return json.dumps({"success": False, "error": f"{tool_name} 오류: {e}"}, ensure_ascii=False)

    # 단일 액션 패턴: read {format} 통합 액션. format 명시 또는 확장자 자동 인식.
    if tool_name == "read_op":
        # start_line/end_line (1-기반, 양끝 포함) → offset/limit 흡수 (2026-08-10, ep1014):
        # 모델이 이 철자를 자연스럽게 쓴다. 별칭(이름변경)으로 못 푸는 이유 — offset 은
        # 0-기반이라 start_line=280 은 offset=279 로 *계산*해야 한다 (end 흡수와 같은 부류).
        if (tool_input.get("start_line") is not None
                or tool_input.get("end_line") is not None):
            try:
                _sl = tool_input.get("start_line")
                _el = tool_input.get("end_line")
                _upd = {}
                if _sl is not None and not tool_input.get("offset"):
                    _upd["offset"] = max(0, int(_sl) - 1)
                if _el is not None and tool_input.get("limit") is None:
                    _first = int(_sl) if _sl is not None else int(tool_input.get("offset") or 0) + 1
                    _upd["limit"] = max(1, int(_el) - _first + 1)
                if _upd:
                    tool_input = {**tool_input, **_upd}
            except (TypeError, ValueError):
                pass  # 숫자 아님 — 기존 흐름에 맡김, 런타임 param 경고층이 알림
        # end(끝 줄/블록) → limit 흡수: start 는 액션 aliases(레지스트리)가 offset 으로
        # 변환하지만, end 는 이름변경이 아니라 계산(limit = end − offset)이라 여기서 흡수.
        # (모델이 start/end 를 써 조용히 무시되고 통파일이 오던 silent-ignore 해소.)
        if tool_input.get("end") is not None and tool_input.get("limit") is None:
            try:
                _end_off = int(tool_input.get("offset") or tool_input.get("start") or 0)
                tool_input = {**tool_input, "limit": max(1, int(tool_input["end"]) - _end_off)}
            except (TypeError, ValueError):
                pass  # 숫자 아님 — 기존 흐름(무시)에 맡김, 런타임 param 경고층이 알림
        # 파이프라인 자동 바인딩: path 가 없으면 직전 step 결과에서 파일 경로 추출.
        # "방금 찾은 파일을 읽기"([self:file_find]{...} | take: 1 >> [self:read]) 조합 개통.
        if not (tool_input.get("path") or tool_input.get("file_path") or tool_input.get("target")):
            prev = tool_input.get("_prev_result") or tool_input.get("params", {}).get("_prev_result", "")
            if prev:
                try:
                    from ibl_executors import _extract_path_from_prev
                    extracted = _extract_path_from_prev(prev if isinstance(prev, str) else json.dumps(prev, ensure_ascii=False))
                    if extracted:
                        tool_input = {**tool_input, "path": extracted}
                except Exception:  # noqa: BLE001 — 추출 실패 시 기존 경로 없음 흐름
                    pass
        fmt = (tool_input.get("format") or "").strip().lower()
        if not fmt:
            raw = tool_input.get("path") or ""
            ext = os.path.splitext(raw)[1].lower().lstrip(".")
            if ext == "pdf":
                fmt = "pdf"
            elif ext in ("docx", "doc"):
                fmt = "docx"
            elif ext in ("xlsx", "xlsm"):
                fmt = "xlsx"
            else:
                fmt = "text"
        # 분기 후 tool_name 재할당해 기존 코드로 위임
        if fmt == "pdf":
            tool_name = "read_pdf"
        elif fmt == "docx":
            tool_name = "read_docx"
        elif fmt == "xlsx":
            tool_name = "read_xlsx"
        else:
            tool_name = "read_file"

    try:
        if tool_name == "read_file":
            raw_path = _get_path(tool_input)
            # system_docs/ 경로는 어떤 프로젝트에서든 data/system_docs/로 매핑
            if raw_path.startswith("system_docs/") and not os.path.isabs(raw_path):
                from runtime_utils import get_base_path
                path = str(get_base_path() / "data" / raw_path)
            else:
                path = os.path.join(project_path, raw_path)
            # 이 수리 세션이 이미 고친 RED 파일이면 격리 사본을 보여준다 — 자기가 쓴 것을
            # 되읽을 때 라이브(옛 내용)가 오면 편집이 어긋난다. 안 건드린 파일은 라이브 그대로.
            path = _red_stage(path, for_write=False)
            # client:true — 파일을 바이너리로 읽어 호출한 몸(폰)이 네이티브 저장하도록 b64 봉투로 반환.
            # 폰 /ibl/execute 프록시(phone_api)가 download_in_client+b64 를 가로채 MediaStore(Music)에
            # 네이티브 저장 → 음악앱이 인식(오프라인·백그라운드·잠금화면 재생). 텍스트 read 와 달리
            # 바이너리(mp3·pdf·이미지)를 나른다. 일반 능력: 어떤 맥 파일이든 부른 몸으로. (오디오 브리핑
            # "폰에 저장" 이 소비자 — [self:read]{path, client:true, mime:"audio/mpeg"}@hub)
            if tool_input.get("client"):
                import base64 as _b64
                import mimetypes as _mt
                if not os.path.isfile(path):
                    return json.dumps({"success": False, "error": f"파일을 찾을 수 없습니다: {path}"}, ensure_ascii=False)
                with open(path, 'rb') as _bf:
                    _bytes = _bf.read()
                _fn = os.path.basename(path)
                _mime = (tool_input.get("mime") or "").strip() or _mt.guess_type(_fn)[0] or "application/octet-stream"
                return json.dumps({
                    "success": True, "download_in_client": True,
                    "filename": _fn, "mime": _mime, "bytes": len(_bytes),
                    "b64": _b64.b64encode(_bytes).decode("ascii"),
                    "message": f"{_fn} 을(를) 폰에 저장 준비",
                }, ensure_ascii=False)
            # blocks: 문서를 *타입 있는 문서 IR* items 로 반환(2026-07-03 승격 — 옛 {text}
            # 문단 조각은 표면에서 마크다운이 생으로 보였음). markdown_to_blocks(backend/doc_ir)
            # 가 heading/list/quote/table/code/divider 를 살려 blocks 뷰·render_document 가
            # 그대로 소비. docx·pdf 읽기의 자체 IR 방출과 같은 통화로 3경로 정렬.
            # 원문은 message 로도 보존. 어느 파일이든 쓰는 일반 표시 옵션.
            if tool_input.get("blocks"):
                from doc_ir import markdown_to_blocks
                with open(path, 'r', encoding='utf-8') as f:
                    _txt = f.read()
                _parts = markdown_to_blocks(_txt)
                return json.dumps({"success": True, "items": _parts, "message": _txt,
                                   "path": path, "count": len(_parts)}, ensure_ascii=False)
            offset = tool_input.get("offset", 0) or 0
            limit = tool_input.get("limit")
            file_size = os.path.getsize(path)

            with open(path, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            total_lines = len(lines)

            # offset/limit 적용
            if offset > 0 or limit is not None:
                end = min(offset + limit, total_lines) if limit else total_lines
                selected = lines[offset:end]
                content = ''.join(selected)
                # 표시는 1-기반 양끝 포함 — grep 줄번호·start_line/end_line 과 같은 자로 읽힌다
                # (옛 표기는 0-기반 범위를 "줄"이라 찍어 1씩 어긋났다).
                header = f"[줄 {offset + 1}-{min(end, total_lines)} / 전체 {total_lines}줄, {file_size:,}바이트]\n"
                return header + content
            else:
                # 전체 읽기 — 대용량 파일 방어 (1MB 제한)
                MAX_READ_SIZE = 1_000_000
                content = ''.join(lines)
                if len(content) > MAX_READ_SIZE:
                    content = content[:MAX_READ_SIZE]
                    content += f"\n\n... (파일이 {file_size // 1000}KB로 큽니다. 처음 1MB만 표시. offset/limit으로 부분 읽기를 사용하세요. 전체 {total_lines}줄)"
                return content

        elif tool_name == "write_file":
            raw_path = _get_path(tool_input)
            if not raw_path:
                return json.dumps({"success": False, "error": "파일 경로(path)가 지정되지 않았습니다."}, ensure_ascii=False)
            path = os.path.join(project_path, raw_path)

            # 새 파일 + bare 파일명(디렉토리 없음) → outputs/ 폴더로 자동 리다이렉트
            redirected = False
            if (not os.path.isabs(raw_path)
                    and os.sep not in raw_path and '/' not in raw_path
                    and not os.path.exists(path)):
                raw_path = os.path.join("outputs", raw_path)
                path = os.path.join(project_path, raw_path)
                redirected = True

            scope_err = _validate_path_in_scope(path, project_path)
            if scope_err:
                return scope_err
            _live_target = path                 # 신고용 — 실제 쓰기는 격리 사본에 갈 수 있다
            path = _red_stage(path, for_write=True)
            content = tool_input.get("content")  # 파이프 싱크(구 output op:file 흡수 2026-08-05): 생략 시 _prev_result, ""는 유효
            piped = False
            if content is None:
                content = tool_input.get("_prev_result")
                piped = content is not None
            if content is None:
                return json.dumps({"success": False, "error": "content가 필요합니다 (파이프에서는 직전 step 결과가 자동 저장됨)."}, ensure_ascii=False)
            extracted = None
            items_alongside = None
            if piped:
                # ★2026-08-17 상상훈련 11회차 판정: 파이프 통화에 message(str)가 실존하면
                # 그것이 산문 정본이다 — _emit_items 가 변환 때 message 를 pop 하는 이유가
                # 바로 "message=현재 내용의 산문판" 계약이라, message 를 두고 봉투 JSON 을
                # 쓰면 원시 배관이 파일이 된다(devdocs 검색 저장이 {"success": true, ...}
                # 8.5KB 봉투가 되던 꼬임 실측). 변환 뒤 봉투(message 없음)·items 만 내는
                # 생산자는 현행(JSON=구조가 내용) 유지. 명시 content 는 건드리지 않고,
                # 추출·동반 items 는 결과에 신고(침묵 변형 금지).
                probe = content
                if isinstance(probe, str):
                    try:
                        probe = json.loads(probe)
                    except Exception:
                        probe = None
                if (isinstance(probe, dict) and isinstance(probe.get("message"), str)
                        and probe["message"].strip()):
                    # ★12회차 정련 v4 (스텁 감사 판정 2026-08-17): 짧은 한 줄 message+items 는
                    # 계약 위반이 아니라 생산자 요약 관례("총 20건" — 내용=items)라 봉투 JSON
                    # 유지가 정답. message 추출은 message 가 *문서 모양*(다행 또는 장문)이고
                    # items 밖 dict/list 페이로드가 없을 때만(devdocs 문서·entity 산문 목록 부류).
                    # 오분류는 항상 안전 방향(JSON=구조 보존)으로 떨어진다.
                    _msg = probe["message"]
                    _other_payload = any(
                        isinstance(v, (dict, list)) and v
                        for k, v in probe.items() if k != "items")
                    _doc_shaped = ("\n" in _msg.strip()) or (len(_msg) >= 200)
                    # ★2026-08-21: AI 산문 emitter([table:brief] 등, _ai:true)의 message 는 길이와
                    # 무관하게 산문 정본 — 2문장 brief(190자)가 봉투 JSON 으로 저장되던 구멍.
                    _ai_prose = bool(probe.get("_ai")) and not isinstance(probe.get("items"), list)
                    if not _other_payload and (_doc_shaped or _ai_prose):
                        if isinstance(probe.get("items"), list) and probe["items"]:
                            items_alongside = len(probe["items"])
                        content = _msg
                        extracted = "message"
            if not isinstance(content, str):
                content = json.dumps(content, ensure_ascii=False, indent=2) if isinstance(content, (dict, list)) else str(content)
            _red_err = _red_write_prepare(path, content)  # 그랜트된 RED 쓰기 안전판(구문검증+백업)
            if _red_err:
                return _red_err
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w', encoding='utf-8') as f:
                f.write(content)
            _red_write_finalize(path)  # backend .py 면 워치독(헬스체크·자동 롤백) 보장
            # 쓰기 관문 원장 — 행위자 동반 사건 기록(관측일 뿐, 실패해도 본 쓰기 무영향)
            try:
                from write_ledger import log_write
                log_write(path, event="write", gate="self_write", size=len(content))
            except Exception:
                pass
            abs_path = os.path.abspath(path)
            result = {"success": True, "path": abs_path, "size": len(content)}
            if path != _live_target:   # 격리 사본에 쌓였다 — 라이브는 아직 무변경
                result.update({
                    "staged": True, "live_path": os.path.abspath(_live_target),
                    "note": ("격리 사본에 기록했습니다 — 라이브는 무변경입니다(리로드 없음). "
                             "검증 후 실제로 반영하려면 [self:patch]{op:\"apply\"} 를 "
                             "호출하세요. 적용하지 않으면 이 수정은 라이브에 없습니다."),
                })
            if extracted:
                result["extracted"] = extracted  # message 본문만 저장했음을 신고
                if items_alongside:
                    result["note"] = (f"동반 items {items_alongside}건은 저장하지 않았습니다 — "
                                      "구조 보존이 필요하면 table:spreadsheet/structure 로 저장하세요.")
            if redirected:
                result["redirected_to"] = "outputs/"
            if tool_input.get("spill"):
                # 스필 싱크 (2026-08-22 프로그램급 IBL M1 / 설계 §2.5-1): 뒤 step 에는 통화 대신
                # *참조*만 흐른다 — {items: [], ref: {path, kind, count, bytes}}. 다음 step 이 데이터가
                # 필요하면 [self:read]{path} 로 재개(결정론). 자동 ref 해소는 M5(변환자 _get_items).
                _kind = "text"
                _count = None
                if piped and isinstance(probe, dict) and isinstance(probe.get("items"), list) and extracted is None:
                    _kind, _count = "items", len(probe["items"])
                elif extracted == "message":
                    _kind = "message"
                result["items"] = []
                result["ref"] = {"path": abs_path, "kind": _kind, "count": _count, "bytes": len(content)}
                result["spilled"] = True
            return json.dumps(result, ensure_ascii=False)

        elif tool_name == "fill_op":
            # 양식 채우기(PDF 폼/DOCX 자리표시자) — office_ops 로 이동 (2026-07-18 모듈화).
            return _office.fill_op(tool_input, project_path)

        elif tool_name == "list_directory":
            dir_path = os.path.join(project_path, os.path.expanduser(tool_input.get("dir_path") or tool_input.get("path") or tool_input.get("target") or "."))
            items = os.listdir(dir_path)
            text = "\n".join(items)
            # === 공유 통화 table {columns, rows} (비파괴 ADD) ===
            # 파일 목록 → [이름, 크기, 수정일, 경로]. 디렉터리는 크기 "".
            rows = []
            records = []  # records 통화(보편) — 파일=명사. 선언 returns:records와 일치.
            for name in items:
                full = os.path.join(dir_path, name)
                try:
                    st = os.stat(full)
                    is_dir = os.path.isdir(full)
                    size = "" if is_dir else st.st_size
                    mtime = datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M")
                except OSError:
                    is_dir, size, mtime = False, "", ""
                abs_full = os.path.abspath(full)
                rows.append([name, size, mtime, abs_full])
                records.append({
                    "title": name + ("/" if is_dir else ""),
                    "meta": " · ".join(x for x in [
                        ("디렉터리" if is_dir else (f"{size:,}B" if isinstance(size, int) else None)),
                        (mtime or None),
                    ] if x),
                    "summary": "",
                    "url": abs_full,
                })
            table = {"columns": ["이름", "크기", "수정일", "경로"], "rows": rows}
            return json.dumps({"text": text, "table": table, "items": records}, ensure_ascii=False)

        elif tool_name == "grep_files":
            # 구현=fs_grep.py 형제 모듈 (2026-08-08 분리 — 1500줄 규칙.
            # 전수 계수·결정적 표본·total/truncated 봉투는 그 파일에)
            mod = _SIBLING_MODS.get("fs_grep")
            if mod is None:
                mod = _SIBLING_MODS["fs_grep"] = _load_sibling("fs_grep")
            return mod.run(tool_input, project_path)

        elif tool_name == "get_current_time":
            fmt = tool_input.get("format", "%Y-%m-%d %H:%M:%S")
            return datetime.now().strftime(fmt)

        elif tool_name == "ai_ask":
            # 시스템 AI 원샷 호출 — 도구·다단계 없이 경량 LLM 으로 즉답. [self:ask]
            # 능력=어휘: 앱(선언형/커스텀)이 raw fetch 없이 IBL 로 AI 를 부른다.
            prompt = (tool_input.get("prompt") or "").strip()
            if not prompt:
                return json.dumps({"success": False, "error": "prompt(지시/질문)가 필요합니다."}, ensure_ascii=False)
            # context 명시가 없으면 파이프 입력(_prev_result)을 맥락으로 받는다 → 조합 가능
            # (예: [sense:search_gnews]{...} >> [self:ask]{prompt: "요약해줘"}).
            ctx = tool_input.get("context")
            if ctx is None:
                prev = tool_input.get("_prev_result")
                if prev not in (None, ""):
                    ctx = prev if isinstance(prev, str) else json.dumps(prev, ensure_ascii=False)
            if ctx is not None and not isinstance(ctx, str):
                ctx = json.dumps(ctx, ensure_ascii=False)
            message = f"{ctx}\n\n---\n\n{prompt}" if ctx else prompt
            sys_prompt = (tool_input.get("system") or
                          "당신은 앱에 내장된 유능한 조수입니다. 사용자의 지시에 간결하고 정확하게 답하세요. "
                          "불필요한 서론·맺음말 없이 요청한 결과만 반환하세요.")
            try:
                from consciousness_agent import oneshot_ai_call
                answer = oneshot_ai_call(message, system_prompt=sys_prompt, role="background")
            except Exception as e:
                return json.dumps({"success": False, "error": f"AI 호출 실패: {e}"}, ensure_ascii=False)
            if not answer:
                return json.dumps({"success": False, "error": "AI 응답을 받지 못했습니다(모델 미설정 가능)."}, ensure_ascii=False)
            return json.dumps({"result": answer, "text": answer}, ensure_ascii=False)

        elif tool_name == "glob_files":
            pattern = tool_input.get("pattern")
            if not pattern:  # 메타 검색 모드(구 fs_query 흡수 2026-08-05) — fs_meta.py 분리
                return _load_sibling("fs_meta").meta_query_or_error(tool_input)

            # 검색 루트 결정 (우선순위: path > root_path > project_path)
            # - 절대경로(/...): 그대로 사용 → 컴퓨터 어디든 검색 가능
            # - ~ 시작: 홈 디렉토리로 확장
            # - 상대경로: project_path 기준
            # - 미지정: project_path
            raw_root = tool_input.get("path") or tool_input.get("root_path") or "."
            expanded = os.path.expanduser(raw_root)
            if os.path.isabs(expanded):
                root = expanded
            else:
                root = os.path.join(project_path, expanded)

            try:
                max_results = int(tool_input.get("max_results", 200))
            except (TypeError, ValueError):
                max_results = 200

            partial = False
            if "/" not in pattern and "**" not in pattern:
                # 재귀 basename 검색(지배적 케이스) — 바운드 walk: 정크 가지치기 + 시간예산.
                # glob.glob('~/**/*X*') 의 색인없는 홈 전체 stat(=타임아웃)을 회피.
                matches, partial = _bounded_find(root, pattern, max_results)
            else:
                # 명시 경로/패턴(`/`·`**` 포함) — 보통 앵커돼 빠름. glob 유지.
                search_pattern = pattern if "**" in pattern else f"**/{pattern}"
                try:
                    matches = glob.glob(os.path.join(root, search_pattern), recursive=True)
                except Exception as e:
                    return f"검색 오류: {e}"

            absolute_paths = sorted(os.path.abspath(m) for m in matches)
            total = len(absolute_paths)
            truncated = (total > max_results > 0) or partial
            if total > max_results > 0:
                absolute_paths = absolute_paths[:max_results]

            if absolute_paths:
                header_parts = [f"{total}개 매칭"]
                if partial:
                    header_parts.append(f"(시간예산 {int(_FIND_DEADLINE_S)}초/상한 도달 — 부분 결과. 더 좁은 path 로 재검색하거나 메타 검색(search_term, OS색인) 사용 권장)")
                elif truncated:
                    header_parts.append(f"(상위 {max_results}개만 반환 — 더 많으면 max_results 또는 더 좁은 path 사용)")
                header_parts.append(f"root: {root}")
                header = " | ".join(header_parts)
                text = header + "\n" + "\n".join(absolute_paths)
                # === 공유 통화 table {columns, rows} (비파괴 ADD) ===
                # 매칭 파일 → [이름, 크기, 수정일, 경로]. 디렉터리는 크기 "".
                rows = []
                records = []  # records 통화(보편) — 파일=명사. 선언 returns:records와 일치.
                for p in absolute_paths:
                    try:
                        is_dir = os.path.isdir(p)
                        st = os.stat(p)
                        size = "" if is_dir else st.st_size
                        mtime = datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M")
                    except OSError:
                        is_dir, size, mtime = False, "", ""
                    rows.append([os.path.basename(p), size, mtime, p])
                    records.append({
                        "title": os.path.basename(p) + ("/" if is_dir else ""),
                        "meta": " · ".join(x for x in [
                            ("디렉터리" if is_dir else (f"{size:,}B" if isinstance(size, int) else None)),
                            (mtime or None),
                        ] if x),
                        "summary": "",
                        "url": p,
                        # 원천 필드 병기(2026-08-08) — meta 문자열에만 접으면 파이프가
                        # sort{by:size} 할 재료를 잃는다(침묵 실패 부류).
                        "name": os.path.basename(p),
                        "size": (size if isinstance(size, int) else None),
                        "mtime": mtime,
                        "path": p,
                        "dir": os.path.dirname(p),
                        "is_dir": is_dir,
                    })
                table = {"columns": ["이름", "크기", "수정일", "경로"], "rows": rows}
                # truncated/total 은 기계가 읽는 봉투 키(2026-08-08) — 경고가 text 헤더
                # 문자열에만 살면 파이프에서 소멸해 부분 결과가 전량인 척 저장된다.
                # 변환자(_emit_items/_emit_table)는 봉투를 비파괴 복사하므로 끝까지 생존.
                return json.dumps({"text": text, "table": table, "items": records,
                                   "total": total, "truncated": truncated},
                                  ensure_ascii=False)

            # 결과 없을 때 — 안내 메시지에 path 옵션 힌트 포함
            hint = (
                f"매칭 없음: pattern={pattern!r} root={root}\n"
                "힌트: 프로젝트 밖을 검색하려면 path 파라미터를 사용하세요. "
                '예: {pattern: "*.docx", path: "~/Desktop"} 또는 {pattern: "*.docx", path: "/Users"}'
            )
            # 0건도 통화 봉투로(2026-08-08 ⑯) — 맨 문자열은 ??(폴백)의 빈손 술어가 못 잡는다
            return json.dumps({"success": True, "items": [], "total": 0,
                               "truncated": False, "text": hint}, ensure_ascii=False)

        elif tool_name == "edit_file":
            file_path = os.path.join(project_path, _get_path(tool_input))
            scope_err = _validate_path_in_scope(file_path, project_path)
            if scope_err:
                return scope_err
            # 격리 스테이징 — 읽기·쓰기가 같은 사본을 보게 여기서 한 번만 바꾼다
            # (old_string 대조가 라이브가 아니라 이 세션이 쌓아온 내용 위에서 이뤄진다).
            _live_target = file_path
            file_path = _red_stage(file_path, for_write=True)
            old_string = tool_input["old_string"]
            new_string = tool_input["new_string"]

            # 파일 읽기
            if not os.path.exists(file_path):
                return f"Error: 파일이 존재하지 않습니다: {_get_path(tool_input)}"

            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # old_string이 파일에 있는지 확인
            count = content.count(old_string)
            if count == 0:
                return f"Error: 교체할 문자열을 찾을 수 없습니다. 파일 내용을 다시 확인하세요."
            elif count > 1:
                return f"Error: 교체할 문자열이 {count}번 발견되었습니다. 더 구체적인 문자열을 지정하세요."

            # 교체 수행
            new_content = content.replace(old_string, new_string, 1)

            _red_err = _red_write_prepare(file_path, new_content)  # RED 안전판(구문검증+백업)
            if _red_err:
                return _red_err

            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(new_content)

            _red_write_finalize(file_path)  # backend .py 면 워치독 보장

            # 절대 경로로 반환 (에이전트 간 경로 혼동 방지)
            if file_path != _live_target:
                return json.dumps({
                    "success": True, "staged": True,
                    "path": os.path.abspath(file_path),
                    "live_path": os.path.abspath(_live_target),
                    "message": f"격리 사본을 수정했습니다. {_STAGED_NOTE}"}, ensure_ascii=False)
            return f"Successfully edited {os.path.abspath(file_path)}"

        elif tool_name == "run_command":
            command = tool_input.get("command", "").strip()
            timeout = min(tool_input.get("timeout", 60), 300)  # 최대 300초
            approved = tool_input.get("approved", False)

            if not command:
                return "Error: 명령어가 비어있습니다."

            # 리로드 강제 금지 — touch/kill 로 자기 몸을 재기동하면 그 리로드가 **이 턴을
            # 실행 중인 워커를 죽인다**(에피소드 미종료·화면 작업표시 영구 정지, 08-18 실측).
            # 반영은 [self:patch]{op:"apply"}, 판정은 워치독이 다음 턴에. 로직=repair_staging.
            try:
                _rf = _staging_mod().reload_forcing_violation(
                    command, str(_REPO_ROOT) if _REPO_ROOT is not None else "")
            except Exception:
                _rf = None
            if _rf:
                return json.dumps({"success": False, "error": _rf}, ensure_ascii=False)

            # 위험한 명령어 감지 - 승인되지 않았으면 승인 요청
            if not approved and is_dangerous_command(command):
                return f"__REQUIRES_APPROVAL__:{command}"

            # 명령어 실행
            try:
                result = subprocess.run(
                    command,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    cwd=project_path
                )

                output = ""
                if result.stdout:
                    output += result.stdout
                if result.stderr:
                    output += f"\n[stderr]\n{result.stderr}" if output else result.stderr

                if result.returncode != 0:
                    output += f"\n[exit code: {result.returncode}]"

                return output.strip() if output else "(명령어가 출력 없이 완료됨)"

            except subprocess.TimeoutExpired:
                return f"Error: 명령어 실행 시간 초과 ({timeout}초)"
            except Exception as e:
                return f"Error: 명령어 실행 실패: {e}"

        elif tool_name == "copy_path":
            _src = tool_input.get("src") or tool_input.get("source")  # src 우선(코퍼스/자연어), source 별칭
            _dst = tool_input.get("dest") or tool_input.get("destination")
            # src 생략 + 파이프 통화 = "앞에서 고른 것들을 여기에 저장" (여러 개를 한 번에)
            if not _src and _dst:
                return _copy_piped_items(tool_input, _dst, project_path)
            if not _src or not _dst:
                return "Error: src(원본)와 dest(대상) 경로가 필요합니다."
            src = os.path.join(project_path, os.path.expanduser(_src))
            dst = os.path.join(project_path, os.path.expanduser(_dst))
            scope_err = _validate_path_in_scope(dst, project_path)
            if scope_err:
                return scope_err

            if not os.path.exists(src):
                return f"Error: 원본이 존재하지 않습니다: {src}"

            # RED 안전판 — 디렉토리 단위 RED 복사는 그랜트가 있어도 금지(파급 과대)
            if _red_is_live_path(dst):
                if os.path.isdir(src):
                    return ("Error: RED 구역에는 디렉토리 단위 복사가 금지됩니다"
                            "(수리 그랜트가 있어도). 파일 단위로 나눠서 하세요.")
                # 격리 스테이징 — 쓰기와 같은 층. 라이브 dst 는 apply 때 생긴다.
                _staged_dst = _red_stage(dst, for_write=True)
                if _staged_dst != dst:
                    os.makedirs(os.path.dirname(os.path.abspath(_staged_dst)), exist_ok=True)
                    shutil.copy2(src, _staged_dst)
                    return json.dumps({
                        "success": True, "staged": True,
                        "path": os.path.abspath(_staged_dst),
                        "live_path": os.path.abspath(dst),
                        "message": ("복사를 격리 사본에 적재했습니다: "
                                    f"{os.path.relpath(os.path.abspath(dst), str(_REPO_ROOT))}. "
                                    + _STAGED_NOTE)}, ensure_ascii=False)
                _src_content = None
                if dst.endswith(".py"):
                    try:
                        with open(src, encoding="utf-8") as _f:
                            _src_content = _f.read()
                    except Exception:
                        pass
                _red_err = _red_write_prepare(dst, _src_content)
                if _red_err:
                    return _red_err

            # 대상 상위 디렉토리 생성
            os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)

            if os.path.isdir(src):
                # 폴더 복사 (대상이 이미 있으면 삭제 후 복사)
                if os.path.exists(dst):
                    shutil.rmtree(dst)
                shutil.copytree(src, dst)
                count = sum(len(files) for _, _, files in os.walk(dst))
                return f"폴더를 복사했습니다: {os.path.abspath(dst)} ({count}개 파일)"
            else:
                # 파일 복사
                shutil.copy2(src, dst)
                _red_write_finalize(dst)
                return f"파일을 복사했습니다: {os.path.abspath(dst)}"

        elif tool_name == "move_path":
            _src = tool_input.get("src") or tool_input.get("source")  # src 우선(코퍼스/자연어), source 별칭
            _dst = tool_input.get("dest") or tool_input.get("destination")
            if not _src or not _dst:
                return "Error: src(원본)와 dest(대상) 경로가 필요합니다."
            src = os.path.join(project_path, os.path.expanduser(_src))
            dst = os.path.join(project_path, os.path.expanduser(_dst))
            scope_err = _validate_path_in_scope(dst, project_path)
            if scope_err:
                return scope_err

            if not os.path.exists(src):
                return f"Error: 원본이 존재하지 않습니다: {src}"

            # RED 안전판 — RED 를 향하거나 RED 에서 빠져나가는 이동은 파일 단위만 + 백업
            if _red_is_live_path(dst) or _red_is_live_path(src):
                # 반출(src=RED)도 게이트 대상 — dst 만 검사하던 구멍을 닫는다
                _rv = _red_zone_violation(os.path.realpath(src)) if _red_is_live_path(src) else None
                if _rv:
                    return _rv
                if os.path.isdir(src):
                    return ("Error: RED 구역이 걸린 디렉토리 단위 이동은 금지됩니다"
                            "(수리 그랜트가 있어도). 파일 단위로 나눠서 하세요.")
                # 격리 스테이징 — 이동은 '대상 쓰기 + 원본 삭제' 한 쌍이라 **둘 다 적재
                # 가능할 때만** 격리로 간다(한쪽만 가면 라이브가 반쪽 상태가 된다).
                # 색깔과 무관하게 양쪽을 적재한다: dst 가 GREEN 이어도 원본 삭제를 미룬 채
                # dst 만 라이브에 만들면 apply 없이 '복사'가 되어 이동이 아니게 된다.
                if _red_can_stage(src) and _red_can_stage(dst):
                    _staged_dst = _red_stage(dst, for_write=True)
                    if _staged_dst != dst and _red_stage_delete(src):
                        os.makedirs(os.path.dirname(os.path.abspath(_staged_dst)), exist_ok=True)
                        shutil.copy2(src, _staged_dst)
                        return json.dumps({
                            "success": True, "staged": True,
                            "live_path": os.path.abspath(dst),
                            "message": ("이동을 격리 사본에 적재했습니다: "
                                        f"{os.path.relpath(os.path.abspath(src), str(_REPO_ROOT))} → "
                                        f"{os.path.relpath(os.path.abspath(dst), str(_REPO_ROOT))}. "
                                        + _STAGED_NOTE)}, ensure_ascii=False)
                if _red_is_live_path(src):
                    _red_err = _red_write_prepare(src)  # 사라질 원본 백업
                    if _red_err:
                        return _red_err
                if _red_is_live_path(dst):
                    _src_content = None
                    if dst.endswith(".py"):
                        try:
                            with open(src, encoding="utf-8") as _f:
                                _src_content = _f.read()
                        except Exception:
                            pass
                    _red_err = _red_write_prepare(dst, _src_content)
                    if _red_err:
                        return _red_err

            # 대상 상위 디렉토리 생성
            os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)

            # 대상이 이미 있으면 삭제
            if os.path.exists(dst):
                if os.path.isdir(dst):
                    shutil.rmtree(dst)
                else:
                    os.remove(dst)

            shutil.move(src, dst)
            _red_write_finalize(dst)
            return f"이동 완료: {os.path.abspath(dst)}"

        elif tool_name == "delete_path":
            target = os.path.join(project_path, os.path.expanduser(tool_input["path"]))
            scope_err = _validate_path_in_scope(target, project_path)
            if scope_err:
                return scope_err

            if not os.path.exists(target):
                # missing_ok: 없으면 '이미 없음'을 성공으로 — 지우고 다시 올리는 정기 작업처럼
                # 멱등하게 돌아야 하는 곳에서, 첫 실행이 에러로 파이프를 끊지 않게 한다.
                if tool_input.get("missing_ok"):
                    return f"이미 없습니다: {os.path.abspath(target)}"
                return f"Error: 경로가 존재하지 않습니다: {target}"

            abs_target = os.path.abspath(target)

            # RED 안전판 — 디렉토리 단위 RED 삭제는 그랜트가 있어도 금지, 파일은 백업 후 삭제
            if _red_is_live_path(abs_target):
                if os.path.isdir(target):
                    return ("Error: RED 구역 디렉토리 삭제는 금지됩니다(수리 그랜트가 있어도). "
                            "정말 필요하면 파일 단위로 지우세요.")
                # 격리 스테이징 — 삭제도 쓰기와 같은 층. 검증(고아 import 검사)을 통과한
                # 뒤 apply 가 백업을 뜨고 라이브에서 지운다.
                if _red_stage_delete(abs_target):
                    return json.dumps({
                        "success": True, "staged": True,
                        "live_path": abs_target,
                        "message": ("삭제를 격리 사본에 적재했습니다: "
                                    f"{os.path.relpath(abs_target, str(_REPO_ROOT))}. "
                                    + _STAGED_NOTE)}, ensure_ascii=False)
                _red_err = _red_write_prepare(abs_target)
                if _red_err:
                    return _red_err

            if os.path.isdir(target):
                count = sum(len(files) for _, _, files in os.walk(target))
                shutil.rmtree(target)
                return f"폴더를 삭제했습니다: {abs_target} ({count}개 파일 포함)"
            else:
                os.remove(target)
                return f"파일을 삭제했습니다: {abs_target}"

        elif tool_name == "make_directory":
            raw_path = _get_path(tool_input)
            if not raw_path:
                return json.dumps({"success": False, "error": "폴더 경로(path)가 지정되지 않았습니다."}, ensure_ascii=False)
            target = os.path.join(project_path, os.path.expanduser(raw_path))
            scope_err = _validate_path_in_scope(target, project_path)
            if scope_err:
                return scope_err
            abs_target = os.path.abspath(target)
            if os.path.isfile(abs_target):
                return json.dumps({"success": False, "error": f"같은 이름의 파일이 이미 있습니다: {abs_target}"}, ensure_ascii=False)
            existed = os.path.isdir(abs_target)
            os.makedirs(abs_target, exist_ok=True)
            return json.dumps({"success": True, "path": abs_target, "existed": existed}, ensure_ascii=False)

        elif tool_name == "read_pdf":
            return _office.read_pdf(tool_input, project_path)

        elif tool_name == "read_docx":
            return _office.read_docx(tool_input, project_path)

        elif tool_name == "read_xlsx":
            return _office.read_xlsx(tool_input, project_path)

        elif tool_name == "spreadsheet":
            # [table:spreadsheet] — office_ops 로 이동. 경로 가드는 handler 소유라 주입.
            return _office.spreadsheet(tool_input, project_path, _validate_path_in_scope)

        elif tool_name == "todo_write":
            todos = tool_input.get("todos", [])
            paths = get_state_paths(project_path, agent_id)

            # 상태 저장
            state = {
                "todos": todos,
                "updated_at": datetime.now().isoformat()
            }

            with open(paths["todo"], 'w', encoding='utf-8') as f:
                json.dump(state, f, ensure_ascii=False, indent=2)

            # 결과 포맷팅 (텍스트 기반, Anthropic 스타일)
            result_lines = ["Todo list updated:"]
            for i, todo in enumerate(todos, 1):
                status = todo["status"]
                if status == "in_progress":
                    result_lines.append(f"  {i}. [in_progress] {todo['activeForm']}")
                elif status == "completed":
                    result_lines.append(f"  {i}. [completed] {todo['content']}")
                else:
                    result_lines.append(f"  {i}. [pending] {todo['content']}")

            return "\n".join(result_lines)

        elif tool_name == "ask_user_question":
            # GoalEval 재실행 중에는 사용자에게 질문할 수 없음
            try:
                from thread_context import get_current_task_id
                current_task = get_current_task_id() or ""
                if current_task.startswith("goal_retry_"):
                    return (
                        "현재 평가 재실행 중이므로 사용자에게 질문할 수 없습니다. "
                        "보유한 정보만으로 최선의 답변을 작성하세요. "
                        "확실하지 않은 부분은 가정을 명시하고 진행하세요."
                    )
            except Exception:
                pass

            questions = tool_input.get("questions", [])
            paths = get_state_paths(project_path, agent_id)

            # 질문 상태 저장 (프론트엔드에서 폴링)
            state = {
                "questions": questions,
                "status": "pending",  # pending, answered
                "answers": None,
                "created_at": datetime.now().isoformat()
            }

            with open(paths["question"], 'w', encoding='utf-8') as f:
                json.dump(state, f, ensure_ascii=False, indent=2)

            # 특수 마커와 함께 반환 - 프론트엔드가 질문 UI를 표시
            return "[[QUESTION_PENDING]]사용자에게 질문을 전달했습니다. 응답을 기다리는 중..."

        elif tool_name == "enter_plan_mode":
            paths = get_state_paths(project_path, agent_id)

            # 계획 모드 상태 저장
            state = {
                "active": True,
                "phase": "exploring",  # exploring, designing, reviewing, finalizing
                "entered_at": datetime.now().isoformat(),
                "plan_file": str(paths["plan_file"])
            }

            with open(paths["plan_mode"], 'w', encoding='utf-8') as f:
                json.dump(state, f, ensure_ascii=False, indent=2)

            # 계획 파일 초기화
            with open(paths["plan_file"], 'w', encoding='utf-8') as f:
                f.write(f"# 구현 계획\n\n생성일: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n## 목표\n\n(작성 중...)\n\n## 구현 단계\n\n1. \n\n## 수정할 파일\n\n- \n\n## 테스트 방법\n\n- \n")

            return "[[PLAN_MODE_ENTERED]]계획 모드로 진입했습니다. 코드를 탐색하고 구현 계획을 수립한 후 exit_plan_mode를 호출하세요."

        elif tool_name == "exit_plan_mode":
            paths = get_state_paths(project_path, agent_id)

            # 계획 모드 상태 확인
            if not paths["plan_mode"].exists():
                return "Error: 계획 모드가 활성화되어 있지 않습니다."

            with open(paths["plan_mode"], 'r', encoding='utf-8') as f:
                state = json.load(f)

            if not state.get("active"):
                return "Error: 계획 모드가 활성화되어 있지 않습니다."

            # 계획 파일 읽기
            plan_content = ""
            if paths["plan_file"].exists():
                with open(paths["plan_file"], 'r', encoding='utf-8') as f:
                    plan_content = f.read()

            # 상태 업데이트 - 승인 대기
            state["phase"] = "awaiting_approval"
            state["plan_content"] = plan_content

            with open(paths["plan_mode"], 'w', encoding='utf-8') as f:
                json.dump(state, f, ensure_ascii=False, indent=2)

            return f"[[PLAN_APPROVAL_REQUESTED]]계획 수립이 완료되었습니다. 사용자 승인을 기다리는 중...\n\n---\n{plan_content}"

        else:
            return json.dumps({"success": False, "error": f"Unknown tool: {tool_name}"}, ensure_ascii=False)

    except Exception as e:
        return f"Error: {str(e)}"
