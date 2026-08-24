#!/usr/bin/env python3
"""에피소드통계 — 주행기록(episode_log/episode_summary)을 items 통화로 집계.

why: 조종실은 IBL 만 쓰는 표면인데, 자기가 감독한 주행의 기록을 읽을 어휘가 없었다
     (data/ibl_nodes_src 전체에 episode 0건). 데이터는 X-Ray·주행기록계(사람용 웹)에만
     열려 있어서, "에피소드 분석해줘" 가 [self:memory] 로 오번역돼 조용히 틀린 답을 냈다.
     집계 관습(무엇을 세나)은 자주 바뀌므로 어휘가 아니라 등록 스크립트로 얼린다
     — 반-어휘-증식(설계원칙 5), [self:script] 가이드의 '어휘 신설 압력의 배출구'.

args (stdin JSON):
  last         최근 N 에피소드 (기본 10)
  ids          [1781, 1765] — 특정 주행만 (주면 last 무시)
  agent        에이전트 이름 부분일치 필터
  include_test true 면 시험 주행(source='test')도 포함 (기본 false)
  mode         "episodes"(기본, 주행 한 줄씩) | "totals"(에이전트별 합계)

산출: {"items": [...], "message": "..."}

★숫자의 뜻 (이 스크립트가 무엇을 세는지 — 안 읽으면 오독한다):
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
  · 도구 줄이 0일 때는 상태로 갈라 적는다 — 도구없음(읽히는 방언인데 안 씀=사실) /
    끊김(Episode ORPHAN) / 로그없음 / 형식밖(모르는 방언 = 0 은 관측이 아니라 무지).
  · IBL 조합 판정은 정규식이 아니라 실제 파서(ibl_parser.parse)로 한다. 파서를 못 부르면
    조합 칸을 비우고 상태에 적는다 — 열등한 숫자를 조용히 내지 않는다.
  · 조합 = 한 문장이 2단계 이상이거나 병렬(&)·폴백(??)·블록을 품은 것.
  · 로그는 상한이 있어 잘린다. 잘린 자리의 도구 인자는 JSON 이 깨지므로 파싱실패로 센다.
"""
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
# 여러 문장 IBL 코드는 줄바꿈째 찍히므로 뒤따르는 줄을 이어붙인다. 다른 로그 줄과
# 겹치지 않는 모양만 인정 — 화살표는 '[숫자', 프로바이더 태그는 대문자로 시작한다.
IBL_CONT = re.compile(
    r"^\s*(\[[a-z_]+:[a-z_]+\]|\$\w|\[(?:if|else|case|try|catch|finally|repeat|goal|on_error)\b)")
# 로그가 '읽을 수 있는 방언'인지의 표지 — 도구 줄이 0일 때 '안 썼다'와 '못 읽었다'를
# 가르는 유일한 근거. 라운드 줄(in-process 에이전트 루프)·ClaudeCode 줄·IBL_DEBUG 중
# 하나라도 있으면 이 스크립트가 읽는 방언이므로 도구 0 은 사실이다.
READABLE = re.compile(r"^\[[^\]]+\] 라운드 \d+|^\[ClaudeCode/|^\[IBL_DEBUG\] code=", re.M)
BLOCK_KEYS = ("_condition", "_try", "_repeat", "_case", "_goal")


def _load_backend():
    """실제 IBL 파서 + 절단 표식(단일 진실). 없으면 None — 숨기지 않고 상태로 신고한다."""
    be = str(REPO / "backend")
    if be not in sys.path:
        sys.path.insert(0, be)
    try:
        import boot_paths  # noqa: F401
        from ibl_parser import parse
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


def _measure(code, parse):
    """IBL 코드 한 덩이 → 조합 지표. 파싱 실패는 None 이 아니라 예외로 알린다."""
    steps = parse(code)
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
    return m


def _collect(log):
    """에피소드 로그 → (도구 계수, 관측된 IBL 코드 [(종류, 원문)], 도구 줄 수).

    두 방언을 한 번에 읽는다(위 '숫자의 뜻' 참조). 계수는 tool_use/화살표에서만 세고,
    [IBL_DEBUG] 는 코드 원문 공급만 한다 — 디듀프 때문에 계수로 쓰면 적게 나온다.
    """
    counts = {"IBL": 0, "Bash": 0, "기타도구": 0}
    codes, tool_lines = [], 0
    lines = (log or "").split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        i += 1
        mt = TOOL_LINE.match(line)          # ① 아웃오브프로세스(claude_code)
        if mt:
            tool_lines += 1
            tool, raw = mt.group(1), mt.group(2) or ""
            if tool == IBL_TOOL:
                counts["IBL"] += 1
                codes.append(("json", raw))
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
            codes.append(("raw", code))
            continue
        ma = ARROW_LINE.match(line)         # ③ in-process 도구 계수의 정본
        if ma:
            tool_lines += 1
            marker = ma.group(1)
            if marker == "tool:run_command":
                counts["Bash"] += 1
            elif marker.startswith("tool:"):
                counts["기타도구"] += 1
            else:                            # [node:action] = execute_ibl 한 번
                counts["IBL"] += 1
            continue
    return counts, codes, tool_lines


def _scan(log, parse, trunc_re=None):
    """에피소드 로그 한 건 → 도구·조합 계수."""
    acc = {"IBL": 0, "Bash": 0, "기타도구": 0, "파싱실패": 0,
           "문장": 0, "조합": 0, "seq": 0, "par": 0, "fb": 0, "블록": 0, "each": 0, "최대단계": 0}
    counts, codes, tool_lines = _collect(log)
    acc.update(counts)
    for kind, raw in codes:
        if parse is None:
            break
        if trunc_re is not None and trunc_re.search(raw):
            acc["파싱실패"] += 1        # 잘린 코드는 앞부분만 파싱돼 조합을 낮게 속인다
            continue
        try:
            code = json.loads(raw).get("code") if kind == "json" else raw
            got = _measure(code or "", parse)
        except Exception:
            acc["파싱실패"] += 1
            continue
        for k, v in got.items():
            acc[k] = max(acc[k], v) if k == "최대단계" else acc[k] + v
    acc["_tool_lines"] = tool_lines
    # 코드를 못 본 IBL 호출 — in-process 디듀프(30초 창) 또는 IBL_DEBUG 이전 구판 로그.
    # 계수는 맞고 조합 지표에서만 빠진 몫이라 0 으로 뭉개지 않고 따로 신고한다.
    acc["코드미기록"] = max(0, acc["IBL"] - len(codes))
    return acc


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
    conn.close()

    items, skipped, unparsed, nocode = [], 0, 0, 0
    for r in rows:
        a = _scan(r["log"], parse, trunc_re)
        tools = a["IBL"] + a["Bash"] + a["기타도구"]
        if a["_tool_lines"] == 0:
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
            unparsed += a["파싱실패"]
        elif a["코드미기록"]:
            state = f"코드미기록 {a['코드미기록']}"
            nocode += a["코드미기록"]
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
            "IBL": a["IBL"], "Bash": a["Bash"], "기타도구": a["기타도구"],
            "IBL비중": _pct(a["IBL"], tools),
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
            for k in ("IBL", "Bash", "기타도구", "문장", "조합", "seq", "par", "fb", "블록", "each"):
                g[k] = g.get(k, 0) + (it[k] or 0)
            g["최대단계"] = max(g.get("최대단계") or 0, it["최대단계"] or 0)
        for g in groups.values():
            g["IBL비중"] = _pct(g["IBL"], g["IBL"] + g["Bash"] + g["기타도구"])
            g["조합률"] = _pct(g["조합"], g["문장"])
        items = sorted(groups.values(), key=lambda x: -x["주행"])

    msg = f"주행 {len(rows)}건 집계"
    if parse is None:
        msg += " · ★IBL 파서를 못 불러 조합 지표는 비어 있습니다(도구 계수만 유효)"
    if skipped:
        msg += (f" · {skipped}건은 두 로그 방언(tool_use·화살표) 중 어느 것도 없어 도구 계수가 "
                "0입니다(안 쓴 게 아니라 못 읽은 것)")
    if nocode:
        msg += (f" · IBL 호출 {nocode}건은 코드 원문이 로그에 없어(30초 디듀프 또는 구판 로그) "
                "조합 지표에서만 빠졌습니다 — 도구 계수는 온전합니다")
    if unparsed:
        msg += (f" · IBL 호출 {unparsed}건은 로그 줄이 잘려 인자 JSON 이 깨졌습니다 "
                "— 조합 지표에서 빠졌고, 잘리는 건 대개 긴(=조합된) 문장이라 조합률이 낮게 나옵니다")
    print(json.dumps({"items": items, "message": msg}, ensure_ascii=False))


if __name__ == "__main__":
    main()
