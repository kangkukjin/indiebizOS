#!/usr/bin/env python3
"""에피소드통계 — 주행기록(episode_log/episode_summary)을 items 통화로 집계.

why: 조종실은 IBL 만 쓰는 표면인데, 자기가 감독한 주행의 기록을 읽을 어휘가 없었다
     (data/ibl_nodes_src 전체에 episode 0건). 데이터는 X-Ray·주행기록계(사람용 웹)에만
     열려 있어서, "에피소드 분석해줘" 가 [self:memory] 로 오번역돼 조용히 틀린 답을 냈다.
     ★2026-09-05 이후 **단순 조회는 [sense:sqlite]**(읽기 전용 SQL, episode_log·trajectory_event 직접) —
     이 스크립트가 남는 이유는 두 로그 방언 파싱·IBL 파서 기반 조합 지표라는 *집계 관습*이지 접근이 아니다.
     집계 관습(무엇을 세나)은 자주 바뀌므로 어휘가 아니라 등록 스크립트로 얼린다
     — 반-어휘-증식(설계원칙 5), [self:script] 가이드의 '어휘 신설 압력의 배출구'.

args (stdin JSON):
  last         최근 N 에피소드 (기본 10)
  ids          [1781, 1765] — 특정 주행만 (주면 last 무시)
  agent        에이전트 이름 부분일치 필터
  include_test true 면 시험 주행(source='test')도 포함 (기본 false)
  mode         "episodes"(기본, 주행 한 줄씩) | "totals"(에이전트별 합계)

산출: {"items": [...], "message": "..."} — 행에 결과천자(모델이 도구 결과로 읽은
  문자수, 천 단위. 절단 표식의 숨긴 글자수까지 복원한 정확값 · 옛 '...' 행은 하한
  표지 동반 · in-process 방언=None) 포함. 왕복 수가 아니라 이 수가 시간·비용의
  지렛대다(2026-08-28 실측: 벽시계의 ~98%가 모델 시간).

★숫자의 뜻 (이 스크립트가 무엇을 세는지 — 안 읽으면 오독한다):
  · **IBL 계수·성공/실패·코드 원문의 1차 소스는 궤적(trajectory_event ibl.started/finished +
    ibl_code_corpus)** 이다 (2026-09-07, ep2950~2952 감사). 로그 방언은 궤적이 없는 옛 주행의
    폴백이고, 둘 다 있으면 어긋남을 상태에 신고한다(`로그계수 N≠궤적 M`). 뿌리: 로거가 여러 문장
    code 를 개행째 힌트에 실어 화살표 줄이 쪼개졌고(ep2951 을 IBL 7 로 읽음 — 로거는 같은 날
    고쳤다), 로그는 잘리지만 궤적·코퍼스는 온전하다. `실패` = ibl.finished success=false,
    `fn` = 원문에 쓴 `[fn:이름]` 머리 수(실행 성공·분기·반복 횟수와 다름).
    문자열·주석 속 예시는 제외한다. 구판 한글 누락은 코퍼스로 복원하고, 원문도 없으면
    `fn=null`·`fn미측정`으로 알린다. actions의 100개 미리보기 상한과 무관하게 센다.
  · **문법오류는 턴 변수 문맥 안에서 판정한다** (2026-09-07). 한 턴의 호출들은 앞 호출의
    `$변수` 를 이어 쓰므로 격리 파싱하면 "변수 $x 이(가) 앞에서 할당되지 않았습니다" 가 쏟아진다
    (ep2951: 55건 중 20건 '문법오류', 실제 런타임 실패 4건 — 16건 오탐). 코드를 실행 순서대로
    parse_with_vars 에 앞 호출의 변수를 주입해 판정한다. 코드 소스가 잘린 로그라 문맥이 불완전할
    수 있으면 미할당 오류는 `문맥불명` 으로 따로 세고 문법오류로 신고하지 않는다.
  · 도구 호출은 **두 로그 방언**을 모두 읽는다 (vocab_crystallization._parse_episode 와 같은 문법):
      - 아웃오브프로세스(claude_code): '[ClaudeCode/X] tool_use <도구> <JSON>'
      - in-process(DeepSeek·Gemini 등): 화살표 '[HH:MM:SS] [agent] [node:action] (힌트) -> OK (Nms)'
        + 코드 원문 '[IBL_DEBUG] code=…' (system_tools._log_ibl / system_tools_ibl)
    ★2026-08-24 수리: 옛 판은 tool_use 만 읽어 in-process 주행을 통째로 '형식밖'(도구 0회)
    으로 신고했다 — 실측 최근 300 주행 중 21건이 그 방언이었고, 조종실 주행기록의 IBL
    통계가 그만큼 0으로 왜곡됐다. 안 쓴 게 아니라 못 읽은 것이었다.
  · in-process 의 도구 계수 정본은 **화살표 라인**이다. [IBL_DEBUG] 는 같은 코드가 30초
    안에 되풀이되면 생략되므로(system_tools_ibl._IBL_LOG_WINDOW) 계수로 쓰면 적게 나온다.
    코드를 못 본 호출 수는 상태=코드미기록 N 으로 신고한다(조합 지표에서만 빠진 것).
  · **빈 코드의 조회는 문장이 아니다**: `describe`는 계약조회, `read_result`는 결과열람,
    `recover`는 회수로 나눈다. `IBL`은 이들을 포함한 전체 호출 수이고 `실행`은 비어 있지
    않은 코드를 제출한 수다(성공 횟수 아님). 종류 정보가 없는 구판 빈 호출은 종류미상,
    조회 인자도 없는 명시적인 빈 입력은 빈호출이다. 빈 호출을 문법오류나 회수로 추정하지 않는다.
    궤적의 request_keys 또는 대응 가능한 로그 인자로 분류하며, 원문은 호출마다 복원한다.
    tool_use/IBL_DEBUG의 이중 표현만 합치고 같은 코드를 재실행한 횟수는 보존한다.
  · 도구 줄이 0일 때는 상태로 갈라 적는다 — 도구없음(읽히는 방언인데 안 씀=사실) /
    끊김(Episode ORPHAN) / 로그없음 / 형식밖(모르는 방언 = 0 은 관측이 아니라 무지).
  · IBL 조합 판정은 정규식이 아니라 실제 파서(ibl_parser.parse)로 한다. 파서를 못 부르면
    조합 칸을 비우고 상태에 적는다 — 열등한 숫자를 조용히 내지 않는다.
  · 조합 = 한 문장이 2단계 이상이거나 병렬(&)·폴백(??)·블록을 품은 것.
  · 로그는 상한이 있어 잘린다(현행 표식 episode_logger.TRUNC_MARK_RE, 2026-08-22 이전 행은
    꼬리 '...'). 잘린 코드는 버리지 않고 **보이는 앞부분만으로 하한 집계**한다 — 잘린 자리는
    조합을 숨길 수는 있어도 만들 수는 없으므로 앞부분 지표는 과대보고가 불가능하다.
    앞부분 뒤에 조합 연산자가 보이면('… >> [잘림') 그 문장은 조합 확정이라 한 칸 올려 센다.
    상태=절단하한 N 으로 신고하니, 그 주행의 조합·단계는 '실제 이상은 아닌 값' 으로 읽어라.
    앞부분조차 못 읽으면 그때만 파싱실패.
"""
import hashlib
import json
import re
import sqlite3
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DB = REPO / "data" / "world_pulse.db"

IBL_TOOL = "mcp__indiebizos__execute_ibl"
TOOL_LINE = re.compile(r"^\[[^\]]+\] tool_use (\S+)(?: (.*))?$")
# in-process 방언 — 화살표(도구 계수의 정본)와 코드 원문. 힌트 괄호는 파라미터가 없는
# 액션([self:time]·todo_write)에선 통째로 빠지므로 선택 그룹이다(실측 15줄).
ARROW_LINE = re.compile(
    r"^\[\d{2}:\d{2}:\d{2}\] \[[^\]]*\] \[([^\]]+)\](?: \(.*\))? -> \S+ \(\d+ms\)\s*$")
DEBUG_LINE = re.compile(r"^\[IBL_DEBUG\] code=(.*)$")
RESULT_LINE = re.compile(r"^\[[^\]]+\] tool_result ?(.*)$")
TRUNC_FALLBACK = re.compile(r"…\(\+(\d+)자\)$")   # 로거 표식 예비(파서 못 불렀을 때)
# 여러 문장 IBL 코드는 줄바꿈째 찍히므로 뒤따르는 줄을 이어붙인다. 다른 로그 줄과
# 겹치지 않는 모양만 인정 — 화살표는 '[숫자', 프로바이더 태그는 대문자로 시작한다.
IBL_CONT = re.compile(
    r"^\s*(\[[a-z_]+:[\w]+\]|\$\w|\[(?:if|else|case|try|catch|finally|repeat|goal|on_error)\b)")
# 로그가 '읽을 수 있는 방언'인지의 표지 — 도구 줄이 0일 때 '안 썼다'와 '못 읽었다'를
# 가르는 유일한 근거. 라운드 줄(in-process 에이전트 루프)·ClaudeCode 줄·IBL_DEBUG 중
# 하나라도 있으면 이 스크립트가 읽는 방언이므로 도구 0 은 사실이다.
READABLE = re.compile(r"^\[[^\]]+\] 라운드 \d+|^\[ClaudeCode/|^\[IBL_DEBUG\] code=", re.M)
# 잘린 코드의 절단면에 남은 조합 연산자 — 뒷단은 몰라도 '조합했다' 는 확정이다.
TAIL_OP = re.compile(r"^\s*(>>|\?\?|&|\|)")
# 잘린 JSON 에서 code 값의 시작점 — 뒤따르는 키(files 등)가 잘려도 코드는 온전할 수 있다.
CODE_KEY = re.compile(r'"code"\s*:\s*"')
REQUEST_KINDS = {"describe": "계약조회", "read_result": "결과열람", "recover": "회수"}
CALL_KINDS = ("실행", *REQUEST_KINDS.values(), "빈호출", "종류미상")
BLOCK_KEYS = ("_condition", "_try", "_repeat", "_case", "_goal")


def _load_backend():
    """실제 IBL 파서 + 절단 표식(단일 진실). 없으면 None — 숨기지 않고 상태로 신고한다."""
    be = str(REPO / "backend")
    if be not in sys.path:
        sys.path.insert(0, be)
    try:
        import boot_paths  # noqa: F401
        from ibl_parser import parse_with_vars as parse
    except Exception:
        return None, None
    try:
        from episode_logger import TRUNC_MARK_RE   # 절단 판정은 로거가 소유(모양 한 벌)
    except Exception:
        TRUNC_MARK_RE = None
    return parse, TRUNC_MARK_RE


def _statements(steps):
    """파서가 낸 평탄한 step 목록을 _seq_boundary 로 문장 단위로 되접는다."""
    out, cur = [], []
    for st in steps:
        if cur and isinstance(st, dict) and st.get("_seq_boundary"):
            out.append(cur)
            cur = []
        cur.append(st)
    if cur:
        out.append(cur)
    return out


def _measure(code, parse, variables=None):
    """IBL 코드 한 덩이 → (조합 지표, 이 코드까지의 변수 맵). 파싱 실패는 None 이 아니라 예외로 알린다.

    variables = 앞 호출들이 할당한 `$변수` 맵(parse_with_vars 의 preset_vars) — 턴 안의 호출은 앞
    호출의 변수를 이어 쓰므로 격리 파싱은 미할당 오탐을 낸다(2026-09-07). 반환 맵은 다음 코드에 넘긴다."""
    steps, out_vars = parse(code, dict(variables or {}))
    m = {"문장": 0, "조합": 0, "seq": 0, "par": 0, "fb": 0, "블록": 0, "each": 0, "최대단계": 0}
    for stmt in _statements(steps):
        m["문장"] += 1
        depth = len(stmt)
        par = sum(1 for s in stmt if isinstance(s, dict) and "_parallel" in s)
        fb = sum(1 for s in stmt if isinstance(s, dict) and "_fallback_chain" in s)
        blk = sum(1 for s in stmt if isinstance(s, dict) and any(k in s for k in BLOCK_KEYS))
        m["seq"] += max(0, depth - 1)
        m["par"] += par
        m["fb"] += fb
        m["블록"] += blk
        m["each"] += sum(1 for s in stmt if isinstance(s, dict)
                         and s.get("_node") == "table" and s.get("action") == "each")
        m["최대단계"] = max(m["최대단계"], depth)
        if depth >= 2 or par or fb or blk:
            m["조합"] += 1
    return m, out_vars


def _result_chars(payload, trunc_re):
    """tool_result 한 줄 → 모델이 실제로 받은 문자수.

    로그 절단은 **기록**을 자른 것이지 모델이 받은 결과를 자른 게 아니다 — 표식
    `(+N자)` 가 숨긴 글자수를 정확히 말해 주므로 보이는 몫 + N 이 정확한 값이다.
    옛 표식('...')은 N 이 없어 보이는 몫만 = 하한. 반환 (문자수, 하한여부)."""
    if trunc_re is not None:
        m = trunc_re.search(payload)
        if m:
            return len(trunc_re.sub("", payload)) + int(m.group(1)), False
    m = TRUNC_FALLBACK.search(payload)
    if m:
        return len(payload[:m.start()]) + int(m.group(1)), False
    if payload.rstrip().endswith("..."):
        return len(payload), True
    return len(payload), False


def _collect(log, trunc_re=None):
    """에피소드 로그 → (도구 계수, 관측된 IBL 코드 [(종류, 원문)], 도구 줄 수,
    결과 문자수, 결과 문자수 하한 여부).

    두 방언을 한 번에 읽는다(위 '숫자의 뜻' 참조). 계수는 tool_use/화살표에서만 세고,
    [IBL_DEBUG] 는 코드 원문 공급만 한다 — 디듀프 때문에 계수로 쓰면 적게 나온다.
    ★결과 문자수 = tool_result 로 모델 문맥에 들어간 문자의 합 — 시스템 프롬프트·
    대화·자기 출력은 밖이다. 왕복 수가 아니라 이 수가 시간·비용의 지렛대다
    (2026-08-28 실측: 벽시계의 ~98% 가 모델 시간, 왕복당 모델 시간은 읽는 양에 따라
    20~28초로 움직였다). in-process 방언은 결과 줄이 없어 미측정(None) — 0 과 다르다.
    """
    counts = {"IBL": 0, "Bash": 0, "기타도구": 0}
    codes, tool_lines = [], 0
    rchars, rchars_seen, rchars_lower = 0, False, False
    lines = (log or "").split("\n")
    pending = None
    i = 0
    while i < len(lines):
        line = lines[i]
        i += 1
        mr = RESULT_LINE.match(line)        # ⓪ 도구 결과 — 모델이 읽은 몫
        if mr:
            n, low = _result_chars(mr.group(1), trunc_re)
            rchars += n
            rchars_seen = True
            rchars_lower = rchars_lower or low
            continue
        mt = TOOL_LINE.match(line)          # ① 아웃오브프로세스(claude_code)
        if mt:
            pending = None
            tool_lines += 1
            tool, raw = mt.group(1), mt.group(2) or ""
            if tool == IBL_TOOL:
                counts["IBL"] += 1
                codes.append(("json", raw))
                pending = len(codes) - 1
            elif tool == "Bash":
                counts["Bash"] += 1
            else:
                counts["기타도구"] += 1
            continue
        md = DEBUG_LINE.match(line)         # ② in-process 코드 원문 (계수 아님)
        if md:
            code = md.group(1)
            while i < len(lines) and IBL_CONT.match(lines[i]):
                code += "\n" + lines[i]
                i += 1
            # 같은 호출의 tool_use/DEBUG는 표현만 둘이다. 코드 내용으로 전역
            # 중복 제거하면 실제로 같은 코드를 재실행한 호출까지 사라진다.
            if pending is not None:
                previous_call = _log_call(*codes[pending], trunc_re)
                previous, cut = previous_call["code"], previous_call["cut"]
                debug_code, debug_cut = _code_of("raw", code, trunc_re)
                if previous and (previous == debug_code
                                 or (cut and debug_code.startswith(previous))
                                 or (debug_cut and previous.startswith(debug_code))
                                 or previous.startswith(debug_code + "\n")):
                    if cut and (not debug_cut or len(debug_code) > len(previous)):
                        codes[pending] = ("raw", code)
                    pending = None
                    continue
            codes.append(("raw", code))
            continue
        ma = ARROW_LINE.match(line)         # ③ in-process 도구 계수의 정본
        if ma:
            pending = None
            tool_lines += 1
            marker = ma.group(1)
            if marker == "tool:run_command":
                counts["Bash"] += 1
            elif marker.startswith("tool:"):
                counts["기타도구"] += 1
            else:                            # [node:action] = execute_ibl 한 번
                counts["IBL"] += 1
            continue
    return counts, codes, tool_lines, (rchars if rchars_seen else None), rchars_lower


def _call_kind(code, keys=None):
    if code and code.strip():
        return "실행"
    if keys is None:
        return "종류미상"
    modes = [REQUEST_KINDS[k] for k in keys if k in REQUEST_KINDS]
    return modes[0] if len(modes) == 1 else ("빈호출" if not modes else "종류미상")


def _log_call(kind, raw, trunc_re):
    """호출의 코드와 종류를 복원. 코드 생략형 조회도 정상 입력이다."""
    keys = None
    if kind == "json":
        try:
            payload = json.loads(raw)
            code = payload.get("code") or payload.get("pipeline") or ""
            if not isinstance(code, str):
                raise ValueError("코드가 문자열이 아님")
            keys = [k for k in REQUEST_KINDS if payload.get(k) is not None]
            return {"code": code, "cut": False, "kind": _call_kind(code, keys), "source": "log"}
        except (ValueError, AttributeError):
            pass
    try:
        code, cut = _code_of(kind, raw, trunc_re)
    except ValueError:
        code, cut = None, False
    return {"code": code, "cut": cut, "kind": _call_kind(code, keys), "source": "log"}


def _code_sha(code):
    return hashlib.sha256(code.encode("utf-8", "replace")).hexdigest()


def _select_calls(log_codes, trunc_re, traj, corpus):
    """호출마다 코퍼스 → 일치하는 로그를 선택한다. 누락 하나로 전체 폴백하지 않는다.

    빈 코드의 해시는 모든 조회가 공유한다. 구판 조회 종류는 빈 호출 수까지
    일치할 때만 순서대로 복원하고, 대응이 불명확하면 종류미상으로 남긴다.
    """
    observed = [_log_call(k, r, trunc_re) for k, r in log_codes]
    if traj is None:
        return observed
    events = traj["calls"]
    by_sha = {}
    for call in observed:
        if call["code"] is not None and not call["cut"]:
            by_sha.setdefault(_code_sha(call["code"]), []).append(call)
    empty_sha = _code_sha("")
    empty_logs = list(by_sha.get(empty_sha, []))
    empty_count = sum(e.get("code_chars") == 0 or e.get("code_sha256") == empty_sha for e in events)
    empty_aligned = empty_count == len(empty_logs)
    selected = []
    for event in events:
        sha = event.get("code_sha256")
        code = (corpus or {}).get(sha)
        if event.get("code_chars") == 0 or sha == empty_sha:
            code = ""
        matches = by_sha.get(sha, [])
        log_call = matches[0] if matches and sha != empty_sha else None
        if code == "" and empty_aligned:
            log_call = empty_logs.pop(0)
        if code is not None:
            keys = event.get("request_keys")
            kind = _call_kind(code, keys)
            if keys is None and log_call and not code:
                kind = log_call["kind"]
            selected.append({"code": code, "cut": False, "kind": kind, "source": "corpus"})
        elif log_call:
            selected.append(log_call)
        else:
            selected.append({"code": None, "cut": False,
                             "kind": ("실행" if event.get("code_chars", 0) else
                                      _call_kind(None, event.get("request_keys"))), "source": "missing"})
    return selected


def _code_of(kind, raw, trunc_re):
    """로그 한 줄 → (IBL 코드, 절단여부). 잘린 줄도 보이는 만큼은 돌려준다.

    절단 표식은 두 벌이 관측된다 — 현행(TRUNC_MARK_RE)과 2026-08-22 이전의 꼬리 '...'.
    옛 표식은 창 밖으로 밀려나면 사라지지만, 아직 남은 행이 실측 111건이라 함께 읽는다.
    ★줄이 잘려도 code 값이 다 보이면 그 코드는 완전 관측이다 — 절단면이 뒤따르는 키(files 등)
      안일 수 있기 때문(실측 20건). 그래서 JSON 전체를 복구하지 않고 code 문자열만 이스케이프를
      존중해 훑어, 닫는 따옴표를 만났는지로 코드의 절단 여부를 판정한다.
    """
    cut = bool(trunc_re is not None and trunc_re.search(raw))
    body = trunc_re.sub("", raw) if cut else raw
    if not cut and body.rstrip().endswith("..."):
        cut, body = True, body.rstrip()[:-3]
    if kind != "json":
        return body, cut
    m = CODE_KEY.search(body)
    if not m:
        raise ValueError("code 키가 없음")
    s, out, i, closed = body[m.end():], [], 0, False
    while i < len(s):
        if s[i] == "\\":                 # 이스케이프는 두 자를 한 몸으로 넘긴다
            out.append(s[i:i + 2])
            i += 2
            continue
        if s[i] == '"':
            closed = True                # 닫는 따옴표를 만났다 = 코드는 완전 관측
            break
        out.append(s[i])
        i += 1
    frag = "".join(out)
    for back in range(7):                # 절단이 이스케이프 한가운데면 몇 자 물러선다
        try:
            return json.loads('"' + frag[:len(frag) - back] + '"'), not closed
        except Exception:
            continue
    raise ValueError("code 문자열을 복원하지 못함")


def _measure_prefix(code, parse, variables=None):
    """잘린 코드 → (파싱되는 가장 긴 앞부분의 지표(하한), 변수 맵). 못 읽으면 (None, variables).

    하한이 안전한 이유: 잘린 자리는 조합을 숨길 수는 있어도 만들 수는 없다.
    앞부분 뒤에 조합 연산자가 보이면(예 '… >> [잘림') 그 문장이 조합이라는 건
    관측된 사실이므로 한 칸 올려 센다 — 몇 단계였는지는 여전히 모른다.
    """
    cut = code
    while cut:
        i = cut.rfind("}")
        if i < 0:
            return None, variables
        cut = cut[:i + 1]
        try:
            m, out_vars = _measure(cut, parse, variables)
        except Exception:
            cut = cut[:i]
            continue
        op = TAIL_OP.match(code[len(cut):])
        if op and m["문장"]:
            m["조합"] = min(m["문장"], m["조합"] + 1)
            m[{">>": "seq", "|": "seq", "&": "par", "??": "fb"}[op.group(1)]] += 1
            m["최대단계"] = max(m["최대단계"], 2)
        return m, out_vars
    return None, variables


UNASSIGNED_RE = re.compile(r"앞에서 할당되지 않았습니다")


def _pair_trajectory(events, corpus=None):
    """한 주행의 궤적 사건(event_seq 순) → {"IBL", "실패", "fn", "중첩", "shas"}.

    ibl.started 는 execute_ibl 한 번(조종실이 부른 호출 수와 같다 — nested 도 모델의 호출), ibl.finished 는
    직전에 열린 started 에 짝지어 success 를 귀속한다(스택). fn_count는 원문에 쓴 fn 머리 수다.
    구판 actions는 한글을 누락했으므로 코퍼스로 재계수한다. 원문도 없으면 미측정(None).
    shas = started 순서의 코드 해시(코퍼스에서 원문을 찾는 열쇠)."""
    from ibl_scanner import source_heads
    out = {"IBL": 0, "실패": 0, "fn": 0, "fn미측정": 0, "중첩": 0, "shas": [], "calls": []}
    stack = []
    for kind, data in events:
        try:
            d = json.loads(data or "{}")
        except Exception:
            d = {}
        if kind == "ibl.started":
            out["IBL"] += 1
            if d.get("nested"):
                out["중첩"] += 1
            fn_count = d.get("fn_count")
            if not isinstance(fn_count, int) or isinstance(fn_count, bool) or fn_count < 0:
                code = (corpus or {}).get(d.get("code_sha256"))
                if code is not None:
                    fn_count = sum(n == "fn" for n, _ in source_heads(code))
                elif d.get("code_chars") == 0:
                    fn_count = 0
                else:
                    fn_count = 0
                    out["fn미측정"] += 1
            out["fn"] += fn_count
            out["shas"].append(d.get("code_sha256") or "")
            out["calls"].append(d)
            stack.append(d)
        elif kind == "ibl.finished":
            if stack:
                stack.pop()
            if d.get("success") is False:
                out["실패"] += 1
    if out["fn미측정"]:
        out["fn"] = None
    return out


def _scan(log, parse, trunc_re=None, traj=None, corpus=None):
    """에피소드 로그 한 건 (+ 궤적·코퍼스) → 도구·조합 계수.

    traj = _pair_trajectory 의 결과(없으면 None = 궤적 이전 주행 → 로그 방언 폴백).
    corpus = {sha: code} — 호출마다 코퍼스 우선, 누락된 호출만 로그로 복원한다.
    """
    acc = {"IBL": 0, "Bash": 0, "기타도구": 0, "파싱실패": 0, "절단": 0, "절단불가": 0, "문법오류": 0,
           "문맥불명": 0, "회수": 0, "실패": None, "fn": None, "fn미측정": 0, "중첩": 0,
           "문장": 0, "조합": 0, "seq": 0, "par": 0, "fb": 0, "블록": 0, "each": 0, "최대단계": 0}
    counts, log_codes, tool_lines, rchars, rchars_lower = _collect(log, trunc_re)
    acc.update(counts)
    acc.update({k: 0 for k in CALL_KINDS})
    acc["코드미기록"] = 0
    acc["_결과문자"] = rchars
    acc["_결과문자하한"] = rchars_lower
    acc["_로그IBL"] = counts["IBL"]
    acc["_궤적"] = traj is not None
    if traj is not None:
        # 궤적이 1차 소스 — 로그 계수는 대조용으로만 남긴다(어긋나면 상태에 신고)
        acc["IBL"] = traj["IBL"]
        acc["실패"] = traj["실패"]
        acc["fn"] = traj["fn"]
        acc["fn미측정"] = traj.get("fn미측정", 0)
        acc["중첩"] = traj["중첩"]
    calls = _select_calls(log_codes, trunc_re, traj, corpus)
    sources = {c["source"] for c in calls}
    acc["_코드소스"] = next(iter(sources)) if len(sources) == 1 else "mixed"
    variables = {}                     # 턴 변수 문맥 — 실행 순서대로 앞 호출의 할당을 잇는다
    incomplete_context = False
    for call in calls:
        acc[call["kind"]] += 1
        code, cut = call["code"], call["cut"]
        if code is None:
            acc["코드미기록"] += 1
            incomplete_context = True
            if call["source"] == "log":
                acc["파싱실패"] += 1
            continue
        if not code.strip() or parse is None:
            continue
        incomplete_context = incomplete_context or cut
        try:
            got, variables = (_measure_prefix(code, parse, variables) if cut
                              else _measure(code, parse, variables))
        except Exception as e:
            got = None
            if UNASSIGNED_RE.search(str(e)) and (incomplete_context or call["source"] == "log"):
                # 로그는 잘리므로 앞 호출의 할당이 문맥에서 빠졌을 수 있다 — 미할당은 문법오류가 아니라 문맥 부족.
                acc["문맥불명"] += 1
                continue
        if got is None:
            # 세 사건을 한 칸에 뭉치면 셋 다 안 보인다:
            #   절단불가 = 잘린 자리에 완결된 문장이 없다 (관측 한계)
            #   문법오류 = 온전한 코드가 파서를 통과 못 한다 = 그 주행에서 에이전트가
            #              실제로 잘못 쓴 IBL 이다 (로그 문제가 아니라 관측된 사실 — 그
            #              호출은 실행도 실패했다). 턴 변수 문맥을 주입한 뒤의 판정이다.
            acc["절단불가" if cut else "문법오류"] += 1
            continue
        if cut:
            acc["절단"] += 1          # 이 주행의 조합·단계는 하한이다
        for k, v in got.items():
            acc[k] = max(acc[k], v) if k == "최대단계" else acc[k] + v
    acc["_tool_lines"] = tool_lines
    # 코드를 못 본 IBL 호출 — in-process 디듀프(30초 창) 또는 IBL_DEBUG 이전 구판 로그, 코퍼스 이전 궤적.
    # 계수는 맞고 조합 지표에서만 빠진 몫이라 0 으로 뭉개지 않고 따로 신고한다.
    unobserved = max(0, acc["IBL"] - len(calls))
    acc["코드미기록"] += unobserved
    acc["종류미상"] += unobserved
    return acc


def _load_trajectory(conn, ids):
    """선택된 주행들의 궤적 → {episode_id: _pair_trajectory(...)} 와 코퍼스 {sha: code}.
    표가 없으면(옛 DB·시험 DB) 빈 값 — 로그 방언 폴백."""
    if not ids:
        return {}, {}
    try:
        q = ",".join("?" * len(ids))
        rows = conn.execute(
            f"SELECT episode_id, kind, data FROM trajectory_event "
            f"WHERE episode_id IN ({q}) AND kind IN ('ibl.started', 'ibl.finished') "
            f"ORDER BY episode_id, event_seq", list(ids)).fetchall()
    except sqlite3.Error:
        return {}, {}
    by_ep = {}
    for r in rows:
        by_ep.setdefault(r[0], []).append((r[1], r[2]))
    traj = {ep: _pair_trajectory(ev) for ep, ev in by_ep.items()}
    shas = sorted({h for t in traj.values() for h in t["shas"] if h})
    corpus = {}
    try:
        for i in range(0, len(shas), 500):
            chunk = shas[i:i + 500]
            q = ",".join("?" * len(chunk))
            for h, code in conn.execute(
                    f"SELECT code_sha256, code FROM ibl_code_corpus WHERE code_sha256 IN ({q})", chunk):
                corpus[h] = code
    except sqlite3.Error:
        corpus = {}
    return {ep: _pair_trajectory(ev, corpus) for ep, ev in by_ep.items()}, corpus


def _pct(a, b):
    return round(a * 100 / b, 1) if b else None


def main():
    try:
        args = json.loads(sys.stdin.read() or "{}")
    except Exception:
        args = {}
    if not isinstance(args, dict):
        args = {}

    if not DB.exists():
        print(json.dumps({"items": [], "success": False,
                          "message": f"주행기록 DB 가 없습니다: {DB}"}, ensure_ascii=False))
        return

    parse, trunc_re = _load_backend()
    ids = args.get("ids")
    last = int(args.get("last") or 10)
    where, params = [], []
    if not args.get("include_test"):
        where.append("COALESCE(e.source, 'usage') <> 'test'")
    if args.get("agent"):
        where.append("e.agent LIKE ?")
        params.append(f"%{args['agent']}%")
    if ids:
        if not isinstance(ids, list):
            ids = [ids]
        where.append("e.id IN (%s)" % ",".join("?" * len(ids)))
        params.extend([int(i) for i in ids])
        limit = len(ids)
    else:
        limit = last

    sql = f"""SELECT e.id, e.started_at, e.agent, e.user_message, e.log, e.total_ms,
                     s.hippocampus_score, s.unconscious_decision,
                     s.execution_rounds, s.evaluation_result
              FROM episode_log e LEFT JOIN episode_summary s ON s.episode_id = e.id
              {'WHERE ' + ' AND '.join(where) if where else ''}
              ORDER BY e.id DESC LIMIT ?"""
    conn = sqlite3.connect(str(DB), timeout=10)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(sql, params + [limit]).fetchall()
    traj_by_ep, corpus = _load_trajectory(conn, [r["id"] for r in rows])
    conn.close()

    items, skipped, unparsed, nocode, lowered, uncut, bad_ibl, polls = [], 0, 0, 0, 0, 0, 0, 0
    no_ctx, no_traj, disagree = 0, 0, 0
    for r in rows:
        a = _scan(r["log"], parse, trunc_re, traj=traj_by_ep.get(r["id"]), corpus=corpus)
        tools = a["IBL"] + a["Bash"] + a["기타도구"]
        # 합계는 상태 표시와 따로 센다 — 한 주행이 절단과 파싱실패를 함께 가질 수 있고,
        # 상태 칸은 그중 하나만 보여주므로 여기서 누락되면 메시지가 조용히 적게 신고한다.
        unparsed += a["파싱실패"]
        lowered += a["절단"]
        uncut += a["절단불가"]
        bad_ibl += a["문법오류"]
        polls += a["회수"]
        nocode += a["코드미기록"]
        no_ctx += a["문맥불명"]
        if not a["_궤적"]:
            no_traj += 1
        elif a["_로그IBL"] != a["IBL"]:
            disagree += 1
        if a["_tool_lines"] == 0 and a["IBL"] == 0:
            _log = r["log"] or ""
            if not _log.strip():
                state = "로그없음"
            elif "[Episode ORPHAN]" in _log:
                state = "끊김"          # 종료 기록 없이 끊긴 턴 — 셀 것이 없다
            elif READABLE.search(_log):
                state = "도구없음"      # 읽히는 방언인데 도구 줄이 없다 = 진짜 안 썼다
            else:
                state = "형식밖"        # 모르는 방언 — 0 은 관측이 아니라 무지다
                skipped += 1
        elif parse is None:
            state = "파서없음"
        elif a["파싱실패"]:
            state = f"파싱실패 {a['파싱실패']}"
        elif a["문법오류"]:
            state = f"문법오류 {a['문법오류']}"   # 에이전트가 보낸 IBL 이 실제로 깨졌다
        elif a["절단불가"]:
            state = f"절단불가 {a['절단불가']}"  # 잘린 자리에 완결된 문장이 없다
        elif a["절단"]:
            state = f"절단하한 {a['절단']}"   # 조합·단계는 '실제 이상은 아닌 값'
        elif a["코드미기록"]:
            state = f"코드미기록 {a['코드미기록']}"
        elif a["문맥불명"]:
            state = f"문맥불명 {a['문맥불명']}"   # 잘린 로그라 변수 문맥이 불완전 — 문법오류로 신고하지 않는다
        elif a["종류미상"]:
            state = f"호출종류미상 {a['종류미상']}"
        elif a["회수"]:
            state = f"회수폴링 {a['회수']}"   # 결함이 아니라 '기다린 왕복' — 칸이 비면 ok
        elif not a["_궤적"]:
            state = "궤적없음"             # 궤적 이전 주행 — 계수는 로그 방언(잘림·쪼개짐 가능)
        elif a["_로그IBL"] != a["IBL"]:
            state = f"로그계수 {a['_로그IBL']}≠궤적 {a['IBL']}"   # 계기끼리 어긋남 — 로그 쪽이 못 센 것
        else:
            state = "ok"
        ts = (r["started_at"] or "")[5:16].replace("T", " ")
        items.append({
            "ep": r["id"], "시각": ts, "에이전트": r["agent"],
            "요청": (r["user_message"] or "")[:60].replace("\n", " "),
            "해마": round(r["hippocampus_score"], 3) if r["hippocampus_score"] is not None else None,
            "분류": r["unconscious_decision"], "평가": r["evaluation_result"],
            "라운드": r["execution_rounds"],
            "총초": round(r["total_ms"] / 1000) if r["total_ms"] else None,
            "IBL": a["IBL"], "실패": a["실패"], "fn": a["fn"],
            "fn미측정": a["fn미측정"],
            **{k: a[k] for k in CALL_KINDS},
            "Bash": a["Bash"], "기타도구": a["기타도구"],
            "IBL비중": _pct(a["IBL"], tools),
            # 모델이 도구 결과로 읽은 문자수(천 단위) — 절단 표식의 숨긴 글자수까지 복원한
            # 정확값(옛 '...' 행만 하한). None = in-process 방언이라 결과 줄이 없음(0 아님).
            "결과천자": (round(a["_결과문자"] / 1000, 1) if a["_결과문자"] is not None else None),
            "결과천자하한": a["_결과문자하한"] or None,
            "문장": a["문장"], "조합": a["조합"], "조합률": _pct(a["조합"], a["문장"]),
            "최대단계": a["최대단계"] or None,
            "seq": a["seq"], "par": a["par"], "fb": a["fb"], "블록": a["블록"], "each": a["each"],
            "상태": state,
        })

    if (args.get("mode") or "episodes") == "totals":
        groups = {}
        for it in items:
            g = groups.setdefault(it["에이전트"] or "?", {"에이전트": it["에이전트"], "주행": 0})
            g["주행"] += 1
            for k in ("IBL", "실패", "fn", *CALL_KINDS, "Bash", "기타도구", "문장", "조합", "seq", "par", "fb", "블록",
                      "each", "결과천자"):
                if k == "fn" and (it[k] is None or (k in g and g[k] is None)):
                    g[k] = None
                else:
                    g[k] = round(g.get(k, 0) + (it[k] or 0), 1)
            g["fn미측정"] = g.get("fn미측정", 0) + it["fn미측정"]
            g["최대단계"] = max(g.get("최대단계") or 0, it["최대단계"] or 0)
        for g in groups.values():
            g["IBL비중"] = _pct(g["IBL"], g["IBL"] + g["Bash"] + g["기타도구"])
            g["조합률"] = _pct(g["조합"], g["문장"])
        items = sorted(groups.values(), key=lambda x: -x["주행"])

    rlow = sum(1 for it in items if it.get("결과천자하한"))
    msg = f"주행 {len(rows)}건 집계"
    if any(it.get("fn미측정") for it in items):
        msg += " · fn미측정: 구판 호출 목록에서 한글 이름이 누락됐고 원문도 없어 fn=null(0 아님)"
    if rlow:
        msg += (f" · 결과천자 {rlow}건은 옛 절단 행(숨긴 글자수 미기록)이라 **하한**입니다 "
                "— 현행 표식 행(2026-08-22 이후)의 정확값과 나란히 비교하지 말 것")
    if parse is None:
        msg += " · ★IBL 파서를 못 불러 조합 지표는 비어 있습니다(도구 계수만 유효)"
    if skipped:
        msg += (f" · {skipped}건은 두 로그 방언(tool_use·화살표) 중 어느 것도 없어 도구 계수가 "
                "0입니다(안 쓴 게 아니라 못 읽은 것)")
    if nocode:
        msg += (f" · IBL 호출 {nocode}건은 코드 원문이 로그에 없어(30초 디듀프 또는 구판 로그) "
                "조합 지표에서만 빠졌습니다 — 도구 계수는 온전합니다")
    if lowered:
        msg += (f" · IBL 호출 {lowered}건은 로그가 잘려 보이는 앞부분만으로 하한 집계했습니다 "
                "— 잘린 자리는 조합을 숨길 수는 있어도 만들 수는 없으니 조합·단계는 '실제 이상은 "
                "아닌 값' 입니다(같은 이유로 조합률은 여전히 낮게 나올 수 있습니다)")
    if uncut:
        msg += (f" · IBL 호출 {uncut}건은 잘린 자리에 완결된 문장이 하나도 없어 조합 지표에서 "
                "빠졌습니다(도구 계수는 온전 — 대부분 2026-08-22 이전 300자 상한 시절 행)")
    if polls:
        msg += (f" · IBL 호출 {polls}건은 코드 없는 **회수 폴링**(execute_ibl{{recover}})이었습니다 "
                "— 문장이 아니므로 조합 지표에서 뺐습니다(문법오류 아님). 이 수는 그 주행이 "
                "결과를 기다리며 쓴 모델 왕복 수입니다 — 회수에 wait 초를 주면 한 번으로 줄어듭니다")
    if bad_ibl:
        msg += (f" · IBL 호출 {bad_ibl}건은 코드 자체가 문법 오류였습니다(턴 변수 문맥을 주입한 뒤의 판정) "
                "— 로그 문제가 아니라 그 주행에서 실제로 깨진 문장을 보냈다는 관측입니다")
    if no_ctx:
        msg += (f" · IBL 호출 {no_ctx}건은 앞 호출의 `$변수` 를 쓰는데 코드 소스가 잘린 로그라 문맥이 불완전합니다 "
                "— 문법오류로 세지 않았습니다(문맥불명)")
    if no_traj:
        msg += (f" · {no_traj}건은 궤적(trajectory_event)이 없는 옛 주행이라 IBL 계수를 로그 방언에서 셌습니다 "
                "— 실패·fn 칸은 비어 있습니다")
    if disagree:
        msg += (f" · {disagree}건은 로그 방언의 IBL 계수가 궤적과 어긋납니다(상태 칸) — 궤적이 정본이고, "
                "로그 쪽은 여러 문장 code 를 개행째 실은 옛 로거의 줄 쪼개짐입니다(2026-09-07 수리 이전 행)")
    if unparsed:
        msg += (f" · ★IBL 호출 {unparsed}건은 절단 표식도 없이 로그 줄을 못 읽었습니다 "
                "— 로그 형식이 바뀌었다는 신호일 수 있습니다")
    print(json.dumps({"items": items, "message": msg}, ensure_ascii=False))


if __name__ == "__main__":
    main()
