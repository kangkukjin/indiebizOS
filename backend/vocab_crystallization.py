"""
vocab_crystallization.py — 어휘 결정화 감지기 (§4 마찰 신호 텔레메트리)

철학: "빈도가 작업을 자율주행→수동→앱으로 결정화한다"에서 *감지* 절반을 자동화한다.
세는 것은 사용 빈도가 아니라 ibl.md "IBL 설계 철학" §4 의 **마찰 신호**다:

  A. raw-코드 추락(bypass) — 에이전트가 IBL 어휘 없이 쉘(run_command)로만 일한 에피소드.
     같은 계열 명령이 반복되면 어휘 승격 후보이자, 카탈로그가 관련 액션을 못 보여줬다는
     굶주림(starvation) 경보를 겸한다 (어휘가 있는데 못 찾았거나, 어휘가 없거나).
  B. 실패→폴백(fallback) — 같은 에피소드에서 IBL 액션이 실패한 뒤 쉘로 도망간 사례.
     어휘가 약속을 못 지킨 지점 (버그 또는 파라미터 계약 결함).
  C. 깨지기 쉬운 긴 조합(recurring combo) — 반복 등장하는 다단 IBL 파이프라인.
     §5 의 "단어 주조" 후보 (반복되는 레시피 = 결정화 대상).
  D. 인자 마찰(param friction) — 같은 액션에 같은 미인식 파라미터 키가 반복.
     오류가 아니라 alias 후보 또는 결핍 파라미터 신호 (인자 층 어휘 진화의 입력).
     소스: ibl_param_vocab.log_param_friction → data/param_friction.jsonl.

하지 않는 것 (설계 가드):
  - 은퇴 깃발 없음 — "사용 0" 은 신호가 아니다 (계절성·유지보수 어휘 오살 방지).
  - 자동 승격 없음 — 감지는 시스템, 결정은 사용자 (augmentation-over-autonomy).
  - 만성 실패 액션 집계 없음 — run_maintenance_bundle 항목 1(_check_failure_alerts) 담당.

데이터 소스: episode_log(world_pulse.db) 의 구조화 stdout 라인만 쓴다 —
  도구/액션 호출:  [HH:MM:SS] [agent] [tool:run_command|node:action] (입력…) -> OK|… (Nms)
  IBL 코드 원문:   [IBL_DEBUG] code=[node:action]{…} >> …
  (ibl_execution_logs 테이블은 2026-07-03 현재 호출자 없는 죽은 배관이라 쓰지 않는다.)

카덴스: 주 1회 (ibl_description_audit 선례). run_maintenance_bundle 항목 6.
산출: data/vocab_crystallization_flags.json + self_checks(__telemetry__:vocab_crystallization)
      + 후보가 있으면 알림 1건. 판단·승격은 사용자와 다음 어휘 정리 세션의 몫.
"""
from __future__ import annotations

import json
import re
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List

from logging_utils import get_logger
from runtime_utils import get_base_path

logger = get_logger("vocab_crystallization")

_STATE_PATH = get_base_path() / "data" / "vocab_crystallization_state.json"
_FLAGS_PATH = get_base_path() / "data" / "vocab_crystallization_flags.json"
_PULSE_DB = get_base_path() / "data" / "world_pulse.db"

_CADENCE_DAYS = 7      # 주 1회
_WINDOW_DAYS = 7       # 감사 창
_MIN_RECUR = 3         # "반복" 판정 최소 횟수

# 화살표 라인: [21:40:06] [system_ai] [tool:run_command|self:list] (입력…) -> OK (41ms)
_ARROW_RE = re.compile(
    r"^\[\d{2}:\d{2}:\d{2}\] \[[^\]]*\] \[([^\]]+)\] \((.*)\) -> (\S+) \((\d+)ms\)\s*$"
)
_IBL_CODE_RE = re.compile(r"^\[IBL_DEBUG\] code=(.*)$")
_STEP_RE = re.compile(r"\[(\w+:\w+)\]")

# claude_code 프로바이더 라인 (2026-07-21 실명 수리 — 화살표는 in-process 전용이라
# 주력 프로바이더의 Bash 42·execute_ibl 162/7일이 통째로 불가시였다. 형식 사양은
# providers/claude_code.py 759·817행: input JSON은 300자에서 잘릴 수 있음(…접미),
# tool_result 는 (error) 태그 + 300자 preview):
#   [ClaudeCode/집사] tool_use Bash {"command": "ADB=...", ...}
#   [ClaudeCode/집사] tool_use mcp__indiebizos__execute_ibl {"code": "[self:read]{...}"}
#   [ClaudeCode/집사] tool_result (error) Exit code 1 ...
_CC_TOOLUSE_RE = re.compile(r"^\[ClaudeCode/[^\]]*\] tool_use (\S+) ?(.*)$")
_CC_TOOLRESULT_RE = re.compile(r"^\[ClaudeCode/[^\]]*\] tool_result( \(error\))? ?(.*)$")
# 잘린 JSON 대비 — json.loads 대신 값 앞부분만 정규식으로 뜯는다(집계 키·shape 추출에 충분).
_CC_CMD_RE = re.compile(r'"command"\s*:\s*"([^"]*)')
_CC_CODE_RE = re.compile(r'"code"\s*:\s*"(.*)')
# tool_result preview 안의 IBL-수준 실패 (도구 호출은 성공했지만 내용이 실패인 부류)
_CC_RESULT_FAIL_RE = re.compile(
    r'\\?"success\\?"\s*:\s*false|\'success\'\s*:\s*False|_param_hint|timed out',
    re.IGNORECASE)


def _should_run(force: bool = False) -> bool:
    if force:
        return True
    try:
        state = json.loads(_STATE_PATH.read_text(encoding="utf-8"))
        last = datetime.fromisoformat(state["last_run"])
        return datetime.now() - last >= timedelta(days=_CADENCE_DAYS)
    except Exception:
        return True  # 상태 없음/깨짐 → 실행


def _save_state() -> None:
    _STATE_PATH.write_text(
        json.dumps({"last_run": datetime.now().isoformat()}, ensure_ascii=False),
        encoding="utf-8",
    )


def _parse_episode(log: str) -> Dict[str, Any]:
    """한 에피소드의 stdout 에서 (쉘 호출, IBL 호출, IBL 실패, IBL 코드) 추출.

    두 로그 방언을 모두 읽는다:
      · in-process(Gemini 등): 화살표 라인 + [IBL_DEBUG] (엔진 실행 래퍼가 찍음)
      · claude_code: [ClaudeCode/X] tool_use/tool_result (프로바이더가 찍음 —
        MCP→HTTP 경로라 화살표 래퍼를 안 지나 2026-07-21까지 통째로 불가시였음)
    라인 순서 = 시간 순서이므로 '실패 후 쉘' 판정은 인덱스 비교로 충분하다.
    claude_code 의 use↔result 페어링은 FIFO 근사 — 병렬 호출이 완료 순서로 섞이면
    개별 귀속이 어긋날 수 있지만, 집계(A)·'실패 후 쉘'(B) 판정에는 충분하다.
    """
    shell_calls: List[tuple] = []   # (line_idx, cmd)
    ibl_calls: List[tuple] = []     # (line_idx, "node:action", ok)
    ibl_codes: List[str] = []
    cc_pending: List[dict] = []     # claude_code tool_use 대기열 (FIFO)
    for idx, line in enumerate(log.split("\n")):
        s = line.strip()
        m = _IBL_CODE_RE.match(s)
        if m:
            ibl_codes.append(m.group(1).strip())
            continue
        m = _ARROW_RE.match(s)
        if m:
            marker, arg, token = m.group(1), m.group(2), m.group(3)
            if marker == "tool:run_command":
                shell_calls.append((idx, arg))
            elif ":" in marker and not marker.startswith("tool:"):
                ibl_calls.append((idx, marker, token == "OK"))
            continue
        m = _CC_TOOLUSE_RE.match(s)
        if m:
            tool_name, input_repr = m.group(1), m.group(2)
            base = tool_name.rsplit("__", 1)[-1]
            entry = {"idx": idx, "kind": "other"}
            if base == "Bash":
                cm = _CC_CMD_RE.search(input_repr)
                # JSON 이스케이프 \n·\" 을 공백으로 펴서 첫 토큰 집계가 덜 깨지게
                cmd = (cm.group(1) if cm else "?").replace("\\n", " ").replace('\\"', '"')
                shell_calls.append((idx, cmd))
                entry["kind"] = "shell"
            elif base == "execute_ibl":
                cm = _CC_CODE_RE.search(input_repr)
                code = (cm.group(1) if cm else "").replace('\\"', '"').rstrip('"}')
                if code:
                    ibl_codes.append(code)
                entry.update(kind="ibl",
                             actions=_STEP_RE.findall(input_repr) or ["?:?"])
            cc_pending.append(entry)
            continue
        m = _CC_TOOLRESULT_RE.match(s)
        if m and cc_pending:
            err_tag, preview = m.group(1), m.group(2)
            entry = cc_pending.pop(0)  # FIFO 근사
            if entry["kind"] == "ibl":
                ok = not err_tag and not _CC_RESULT_FAIL_RE.search(preview or "")
                for na in entry["actions"]:
                    ibl_calls.append((entry["idx"], na, ok))
    # 결과 라인을 못 받은 잔여 IBL use(로그 절단 등)는 성공으로 간주해 집계에만 넣는다
    for entry in cc_pending:
        if entry["kind"] == "ibl":
            for na in entry["actions"]:
                ibl_calls.append((entry["idx"], na, True))
    return {"shell": shell_calls, "ibl": ibl_calls, "codes": ibl_codes}


def _cmd_head(cmd: str) -> str:
    """쉘 명령의 집계 키 — 첫 토큰(경로면 basename). 앞의 VAR=값 할당은 건너뛴다."""
    tokens = cmd.split() or ["?"]
    for t in tokens:
        if not re.match(r"^\w+=", t):
            return t.rsplit("/", 1)[-1]
    return tokens[0].split("=", 1)[0]  # 전부 할당이면 변수명으로


def scan(days: int = _WINDOW_DAYS) -> Dict[str, Any]:
    """최근 N일 에피소드에서 마찰 신호 A/B/C 를 수집 (카덴스 무관 순수 스캔)."""
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    conn = sqlite3.connect(str(_PULSE_DB))
    try:
        rows = conn.execute(
            "SELECT id, started_at, user_message, log FROM episode_log "
            "WHERE started_at >= ? ORDER BY id",
            (cutoff,),
        ).fetchall()
    finally:
        conn.close()

    bypass_heads: Counter = Counter()          # A: 쉘-전용 에피소드의 명령 계열
    bypass_examples: defaultdict = defaultdict(list)
    fallbacks: List[Dict] = []                 # B: IBL 실패 → 쉘
    combo_counts: Counter = Counter()          # C: 다단 파이프라인 shape
    combo_example: Dict[str, str] = {}
    n_shell = n_ibl = 0

    for ep_id, started, user_msg, log in rows:
        if not log:
            continue
        p = _parse_episode(log)
        n_shell += len(p["shell"])
        n_ibl += len(p["ibl"])

        # A. 순수 우회: 쉘은 썼는데 IBL 호출이 0
        if p["shell"] and not p["ibl"]:
            for _, cmd in p["shell"]:
                head = _cmd_head(cmd)
                bypass_heads[head] += 1
                if len(bypass_examples[head]) < 3:
                    bypass_examples[head].append(
                        {"episode": ep_id, "user_message": (user_msg or "")[:80],
                         "cmd": cmd[:120]}
                    )

        # B. 실패→폴백: IBL 실패 라인 뒤에 쉘 라인
        fail_idxs = [i for i, _, ok in p["ibl"] if not ok]
        if fail_idxs and p["shell"]:
            first_fail = min(fail_idxs)
            after = [(i, c) for i, c in p["shell"] if i > first_fail]
            if after:
                failed_actions = [a for i, a, ok in p["ibl"] if not ok]
                fallbacks.append(
                    {"episode": ep_id, "started_at": started,
                     "user_message": (user_msg or "")[:80],
                     "failed_actions": failed_actions[:5],
                     "shell_cmd": after[0][1][:120]}
                )

        # C. 반복되는 다단 조합 (파이프라인 연산자 포함 코드만)
        for code in p["codes"]:
            if not any(op in code for op in (">>", " & ", "??")):
                continue
            steps = _STEP_RE.findall(code)
            if len(steps) < 2:
                continue
            shape = " → ".join(steps)
            combo_counts[shape] += 1
            combo_example.setdefault(shape, code[:200])

    recurring = [
        {"shape": s, "count": c, "example": combo_example[s]}
        for s, c in combo_counts.most_common()
        if c >= _MIN_RECUR
    ]
    bypass = [
        {"cmd_head": h, "count": c, "examples": bypass_examples[h]}
        for h, c in bypass_heads.most_common()
        if c >= _MIN_RECUR
    ]

    # D. 인자 마찰 — (액션, 미인식 키) 반복 집계 (런타임 경고 층이 남긴 이벤트)
    friction_counts: Counter = Counter()
    try:
        from ibl_param_vocab import read_param_friction
        for e in read_param_friction(days=days):
            for k in e.get("unknown") or []:
                friction_counts[(e.get("action", "?"), k)] += 1
    except Exception:
        pass
    param_friction = [
        {"action": a, "key": k, "count": c}
        for (a, k), c in friction_counts.most_common()
        if c >= _MIN_RECUR
    ]

    return {
        "generated_at": datetime.now().isoformat(),
        "window_days": days,
        "episodes_scanned": len(rows),
        "calls": {"ibl": n_ibl, "shell": n_shell},
        "bypass_ratio": round(n_shell / (n_shell + n_ibl), 3) if (n_shell + n_ibl) else 0.0,
        "raw_bypass": bypass,          # A — 승격 후보 + 굶주림 경보
        "fallbacks": fallbacks,        # B — 어휘가 약속을 못 지킨 지점
        "recurring_combos": recurring,  # C — 단어 주조 후보
        "param_friction": param_friction,  # D — alias 후보/결핍 파라미터 신호
    }


def run_crystallization_scan(force: bool = False) -> Dict[str, Any]:
    """주간 카덴스 게이트로 스캔하고 self_checks 형식 1건을 반환.

    run_maintenance_bundle 항목 6 으로 합류한다. 매일 호출돼도 주 1회만 실제 실행.
    """
    if not _should_run(force):
        return {"skipped": "cadence"}

    result = scan()
    _save_state()
    _FLAGS_PATH.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    n_candidates = (
        len(result["raw_bypass"]) + len(result["fallbacks"])
        + len(result["recurring_combos"]) + len(result["param_friction"])
    )
    if n_candidates:
        summary = (
            f"우회 계열 {len(result['raw_bypass'])} / 폴백 {len(result['fallbacks'])} / "
            f"반복 조합 {len(result['recurring_combos'])} / "
            f"인자 마찰 {len(result['param_friction'])} — {_FLAGS_PATH.name} 참조"
        )
        logger.warning(f"[Crystallization] 어휘 결정화 후보 {n_candidates}건: {summary}")
        try:
            from notification_manager import get_notification_manager
            get_notification_manager().info(
                "어휘 결정화 후보", summary, source="vocab_crystallization"
            )
        except Exception:
            pass
    else:
        logger.info(
            f"[Crystallization] 에피소드 {result['episodes_scanned']}개 감사 — 마찰 신호 0"
        )

    return {
        "node": "__telemetry__",
        "action": "vocab_crystallization",
        "success": True,  # 후보 발견은 고장이 아니라 정보 — success 는 스캔 자체의 성패
        "response_ms": 0,
        "error_message": None,
        "data_quality": (
            f"에피소드 {result['episodes_scanned']} / IBL {result['calls']['ibl']} / "
            f"쉘 {result['calls']['shell']} / 후보 {n_candidates}"
        ),
    }
