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
  · 로그는 상한이 있어 잘린다(현행 표식 episode_logger.TRUNC_MARK_RE, 2026-08-22 이전 행은
    꼬리 '...'). 잘린 코드는 버리지 않고 **보이는 앞부분만으로 하한 집계**한다 — 잘린 자리는
    조합을 숨길 수는 있어도 만들 수는 없으므로 앞부분 지표는 과대보고가 불가능하다.
    앞부분 뒤에 조합 연산자가 보이면('… >> [잘림') 그 문장은 조합 확정이라 한 칸 올려 센다.
    상태=절단하한 N 으로 신고하니, 그 주행의 조합·단계는 '실제 이상은 아닌 값' 으로 읽어라.
    앞부분조차 못 읽으면 그때만 파싱실패.
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
# 잘린 코드의 절단면에 남은 조합 연산자 — 뒷단은 몰라도 '조합했다' 는 확정이다.
TAIL_OP = re.compile(r"^\s*(>>|\?\?|&|\|)")
# 잘린 JSON 에서 code 값의 시작점 — 뒤따르는 키(files 등)가 잘려도 코드는 온전할 수 있다.
CODE_KEY = re.compile(r'"code"\s*:\s*"')
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


def _measure_prefix(code, parse):
    """잘린 코드 → 파싱되는 가장 긴 앞부분의 지표(하한). 못 읽으면 None.

    하한이 안전한 이유: 잘린 자리는 조합을 숨길 수는 있어도 만들 수는 없다.
    앞부분 뒤에 조합 연산자가 보이면(예 '… >> [잘림') 그 문장이 조합이라는 건
    관측된 사실이므로 한 칸 올려 센다 — 몇 단계였는지는 여전히 모른다.
    """
    cut = code
    while cut:
        i = cut.rfind("}")
        if i < 0:
            return None
        cut = cut[:i + 1]
        try:
            m = _measure(cut, parse)
        except Exception:
            cut = cut[:i]
            continue
        op = TAIL_OP.match(code[len(cut):])
        if op and m["문장"]:
            m["조합"] = min(m["문장"], m["조합"] + 1)
            m[{">>": "seq", "|": "seq", "&": "par", "??": "fb"}[op.group(1)]] += 1
            m["최대단계"] = max(m["최대단계"], 2)
        return m
    return None


def _scan(log, parse, trunc_re=None):
    """에피소드 로그 한 건 → 도구·조합 계수."""
    acc = {"IBL": 0, "Bash": 0, "기타도구": 0, "파싱실패": 0, "절단": 0, "절단불가": 0, "문법오류": 0,
           "문장": 0, "조합": 0, "seq": 0, "par": 0, "fb": 0, "블록": 0, "each": 0, "최대단계": 0}
    counts, codes, tool_lines = _collect(log)
    acc.update(counts)
    for kind, raw in codes:
        if parse is None:
            break
        try:
            code, cut = _code_of(kind, raw, trunc_re)
        except Exception:
            acc["파싱실패"] += 1        # 로그 줄 자체를 못 읽었다 = 형식 변화 신호
            continue
        try:
            got = _measure_prefix(code, parse) if cut else _measure(code, parse)
        except Exception:
            got = None
        if got is None:
            # 세 사건을 한 칸에 뭉치면 셋 다 안 보인다:
            #   절단불가 = 잘린 자리에 완결된 문장이 없다 (관측 한계)
            #   문법오류 = 온전한 코드가 파서를 통과 못 한다 = 그 주행에서 에이전트가
            #              실제로 잘못 쓴 IBL 이다 (로그 문제가 아니라 관측된 사실 — 그
            #              호출은 실행도 실패했다)
            acc["절단불가" if cut else "문법오류"] += 1
            continue
        if cut:
            acc["절단"] += 1          # 이 주행의 조합·단계는 하한이다
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

    items, skipped, unparsed, nocode, lowered, uncut, bad_ibl = [], 0, 0, 0, 0, 0, 0
    for r in rows:
        a = _scan(r["log"], parse, trunc_re)
        tools = a["IBL"] + a["Bash"] + a["기타도구"]
        # 합계는 상태 표시와 따로 센다 — 한 주행이 절단과 파싱실패를 함께 가질 수 있고,
        # 상태 칸은 그중 하나만 보여주므로 여기서 누락되면 메시지가 조용히 적게 신고한다.
        unparsed += a["파싱실패"]
        lowered += a["절단"]
        uncut += a["절단불가"]
        bad_ibl += a["문법오류"]
        nocode += a["코드미기록"]
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
        elif a["문법오류"]:
            state = f"문법오류 {a['문법오류']}"   # 에이전트가 보낸 IBL 이 실제로 깨졌다
        elif a["절단불가"]:
            state = f"절단불가 {a['절단불가']}"  # 잘린 자리에 완결된 문장이 없다
        elif a["절단"]:
            state = f"절단하한 {a['절단']}"   # 조합·단계는 '실제 이상은 아닌 값'
        elif a["코드미기록"]:
            state = f"코드미기록 {a['코드미기록']}"
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
    if lowered:
        msg += (f" · IBL 호출 {lowered}건은 로그가 잘려 보이는 앞부분만으로 하한 집계했습니다 "
                "— 잘린 자리는 조합을 숨길 수는 있어도 만들 수는 없으니 조합·단계는 '실제 이상은 "
                "아닌 값' 입니다(같은 이유로 조합률은 여전히 낮게 나올 수 있습니다)")
    if uncut:
        msg += (f" · IBL 호출 {uncut}건은 잘린 자리에 완결된 문장이 하나도 없어 조합 지표에서 "
                "빠졌습니다(도구 계수는 온전 — 대부분 2026-08-22 이전 300자 상한 시절 행)")
    if bad_ibl:
        msg += (f" · IBL 호출 {bad_ibl}건은 코드 자체가 문법 오류였습니다 "
                "— 로그 문제가 아니라 그 주행에서 실제로 깨진 문장을 보냈다는 관측입니다")
    if unparsed:
        msg += (f" · ★IBL 호출 {unparsed}건은 절단 표식도 없이 로그 줄을 못 읽었습니다 "
                "— 로그 형식이 바뀌었다는 신호일 수 있습니다")
    print(json.dumps({"items": items, "message": msg}, ensure_ascii=False))


if __name__ == "__main__":
    main()
