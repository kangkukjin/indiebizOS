"""AI 팁 가이드 1회 IBL 실행 실험: 입력 고정·프로그램 작성·HTTP 실행 계측.

보고서 내용과 원장 델타는 Python이 만들지 않는다. 생성된 program.ibl이 실행한다.
사용: PYTHONPATH=backend .venv/bin/python scripts/experiment_ai_tips_onepass.py prepare|check|run
"""
import boot_paths  # noqa: F401

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import shutil
import sqlite3
import time
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs/experiments/ai_tips_onepass_2026_09_08"
SOURCE = ROOT / "outputs/ai_tips_reports"
DATE = "2026-09-08"
TOPIC = "디버깅"
CUTOFF = (dt.date.fromisoformat(DATE) - dt.timedelta(days=180)).isoformat()
TASK = "ai-tips-onepass-20260908-v1"


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def action(name, **params):
    return f"[{name}]" + (json.dumps(params, ensure_ascii=False) if params else "")


def program():
    covered = str(OUT / "_covered_videos.json")
    tips = str(OUT / "db/tips.json")
    report = str(OUT / f"ai_tips_report_{DATE}_{TOPIC}.md")
    html = str(OUT / f"AI 팁 보고서 {DATE} {TOPIC}.html")
    lines = []

    def assign(var, expr):
        lines.append(f"${var} = {expr};")

    def checkpoint(var, name):
        assign("저장_" + name, f"${var} >> " + action(
            "self:write", path=str(OUT / f"{name}.json"), format="json"))

    assign("기존영상", action("self:ledger", path=covered, target="covered",
                              fields=["id", "verdict"]))
    assign("최근주제", action("self:ledger", path=covered, target="recent_topics"))
    assign("기존팁", action("self:ledger", path=tips, fields=["tip", "date"],
                            where={"topic": TOPIC}))
    queries = [
        ("한국어", "클로드 코드 디버깅 오류 수정"),
        ("영어", "AI coding debugging workflow"),
        ("워크플로", "Claude Code debug failing tests"),
        ("회의론", "AI coding debugging limitations"),
        ("행위", "에러 로그 AI 버그 재현"),
    ]
    branches = []
    for branch, query in queries:
        branches.append("(" + action("sense:search_youtube", query=query, count=12)
                        + " >> " + action("table:compute", set={"branch": repr(branch)}) + ")")
    assign("검색", " & ".join(branches) + " >> [table:union] >> "
           + action("table:dedup", by="video_id"))
    checkpoint("검색", "01_search")
    assign("신규", "$검색 >> " + action("table:filter", where={
        "field": "video_id", "op": "not_in", "value": "${기존영상.items.*.id}"}))
    assign("조회", "$신규 >> " + action("table:each", limit=60, parallel=4,
        on_error="keep", keep=["branch"],
        do=action("sense:video", op="info", video_id="$it.video_id")))
    fields = ["video_id", "title", "uploader", "duration", "view_count", "upload_date", "url", "branch"]
    row = {k: "${it." + k + "?}" for k in fields}
    row["info_error"] = "${it._error?}"
    assign("정보", "$조회 >> " + action("table:each", limit=60,
        do=action("table:take", items=[row], n=1)))
    checkpoint("정보", "02_info")
    assign("최신", "$정보 >> " + action("table:filter", where=[
        {"field": "info_error", "op": "eq", "value": ""},
        {"field": "upload_date", "op": "gte", "value": CUTOFF},
        {"field": "upload_date", "op": "lte", "value": DATE}]))
    assign("심사", "$최신 >> " + action("table:ai",
        instruction=("모든 입력 행과 원 필드를 유지하고 selected(불리언), reason(한국어 한 문장), "
            "language(ko/en)만 추가하라. 디버깅의 실제 재현·로그·테스트 실패·수정 검증에 "
            "쓸 조작 지식이 있을 영상을 정확히 4편 선정하라(후보가 4편 미만이면 전부). "
            "한국어와 영어 층을 섞고, branch 회의론의 관련 영상이 있으면 최소 1편 넣는다. "
            "같은 채널 중복보다 관점 다양성, 뉴스·홍보·단순 시연보다 구체적 튜토리얼 우선. "
            "duration은 초이며 3600초 이상은 최대 1편. source metadata를 수정하지 말라."),
        criteria="입력 행 수·video_id 보존. selected는 불리언, reason과 language가 모든 행에 있다. "
                 "selected true는 4편(입력이 4편 미만이면 전부), 3600초 이상 최대 1편."))
    checkpoint("심사", "03_selection")
    assign("선정", "$심사 >> " + action("table:filter", where={"selected": True})
           + " >> " + action("table:take", n=4))

    transcript_path = str(OUT / "transcripts/${it.video_id}.json")
    do = "$자막 = " + action("sense:video", op="transcript", video_id="$it.video_id", language="$it.language")
    do += " ?? " + action("sense:video", op="transcript", video_id="$it.video_id", language="en") + "; "
    do += "$자막보존 = $자막 >> " + action("self:write", path=transcript_path, format="json") + "; "
    do += "$자막 >> " + action("self:struct", grounded=True,
        known="${기존팁.items.*.tip}", schema="tip(한국어 실행형 팁 제목·동사로 끝남), timestamp(MM:SS)",
        instruction="디버깅·재현·로그·테스트·검증 관련 실제 조작 팁만 최대 8개. 덕담·홍보 제외. "
                    "제목과 타임스탬프만. 근거 _quote는 원문 철자 그대로 8~12단어 안의 앵커.",
        criteria="행마다 tip와 _quote가 있다. 실행 가능한 디버깅 팁이며 최대 8행. "
                 "timestamp는 원문 시간 또는 null이며 꾸민 시각을 넣지 않는다.")
    assign("팁후보", "$선정 >> " + action("table:each", limit=4, parallel=4,
        on_error="continue", keep=["video_id", "title", "uploader", "url", "language"], do=do))
    checkpoint("팁후보", "04_tip_candidates")
    assign("절제", "$팁후보 >> " + action("table:ai",
        instruction="입력의 모든 행과 원 필드는 유지하고 selected 불리언과 dedup_note 한 문장만 추가. "
            "영상당 2~5개, 전체 8~15개(가능하면 12개)의 가장 실행 가능한 팁을 선정하라. "
            "영상 균형·서로 다른 디버깅 단계·반대 관점을 살리고 같은 행동의 재탕은 제거. "
            "이미 수집한 오늘 주제 팁과 대조: ${기존팁.items}. 재탕이면 selected false와 수집 날짜. "
            "유효한 후보가 적으면 수를 채우려고 만들지 말라.",
        criteria="모든 입력 행과 tip·video_id 보존, selected 불리언과 dedup_note 존재. "
                 "선정은 영상당 2~5행, 전체 8~15행. 원문 밖 팁을 추가하지 않는다."))
    checkpoint("절제", "05_tip_selection")
    assign("선정팁", "$절제 >> " + action("table:filter", where={"selected": True})
        + " >> " + action("table:take", n=15))
    assign("정독영상", "$선정 >> " + action("table:filter", where={
        "field": "video_id", "op": "in", "value": "${선정팁.items.*.video_id}"}))
    do = "$이영상팁 = " + action("table:filter", items="${선정팁.items}",
        where={"field": "video_id", "op": "eq", "value": "$it.video_id"}) + "; "
    do += action("self:struct", file=transcript_path, grounded=True,
        known="${기존팁.items.*.tip}",
        schema="tip(주어진 제목 그대로), how(구체적 단계·설정·명령·프롬프트; 원문에 없으면 빈 문자열), "
               "tools(문자열), hype(과장 간극 한국어 한 줄; 없으면 빈 문자열), timestamp(MM:SS)",
        instruction="다음 제목들에 대해서만 각 1행: ${이영상팁.items.*.tip}. "
            "how는 한국어로 원문에서 설명한 방법만 쓴다. 원문에 없는 명령·수치·단계는 보완하지 않는다. "
            "고유명사 철자가 불확실하면 (자막 표기·철자 불확실)을 붙인다. _quote 원문 앵커 필수.",
        criteria="요청한 tip 제목 각각 1행, 새 제목 추가 금지. 모든 행에 how/tools/hype/_quote. "
                 "원문에서 말한 실행 방법만 담고 timestamp는 원문 시간 또는 null.")
    assign("상세", "$정독영상 >> " + action("table:each", limit=4, parallel=4,
        on_error="continue", keep=["video_id", "title", "uploader", "url"], do=do))
    checkpoint("상세", "06_details")
    # 요청한 제목과 원본 영상 식별자로 inner join: 추출기의 추가 제목은 DB에 못 들어간다.
    assign("확정", action("table:join", left="$상세", right="$선정팁", on=["video_id", "tip"]))
    assign("팁수", "$확정 >> " + action("table:groupby", by="video_id", agg={"tip_count": ["count"]}))
    assign("완료영상", action("table:join", left="$정독영상", right="$팁수", on="video_id"))
    assign("편집", "$확정 >> " + action("table:ai",
        instruction="입력 모든 행·사실·방법·출처를 그대로 보존하고 implication(한 줄)과 "
            "try_candidate(불리언, true 최대 3개)만 추가하라. 사용자는 Claude Code·IndieBiz OS를 "
            "쓰는 고급 사용자이며 하네스의 실행 오류·AI 호출·시간·토큰을 줄이고 싶다. "
            "implication은 이미 하는 것/이식 후보/해당 없음 중 하나로 시작. "
            "실제 구현을 확인하지 못했으므로 이미 하는 것이라고 단정하지 말고, 구체적인 적용 "
            "제안은 원문 사실과 분리해 '이식 후보:'로 적는다. 시도 후보는 오늘 호 안에서만 끝난다.",
        criteria="입력 행수 및 모든 원 필드 보존. implication이 모든 행에 있다. "
                 "try_candidate는 모든 행에서 불리언이며 true는 최대 3행."))
    checkpoint("편집", "07_edited")
    assign("검법팁수", "$편집 >> " + action("table:reduce", init=0, step="acc + 1"))
    assign("검법편수", "$완료영상 >> " + action("table:reduce", init=0, step="acc + 1"))
    assign("불균형", "$팁수 >> " + action("table:filter", where="tip_count < 2 or tip_count > 5"))
    guard_start = len(lines)

    # 원장 델타는 확인한 전체 행에서 파생한다. 정보 조회 실패는 최신으로 취급하지 않는다.
    do = "$건수 = " + action("table:filter", items="${팁수.items}",
        where={"field": "video_id", "op": "eq", "value": "$it.video_id"})
    do += " >> " + action("table:reduce", init=0, step="acc + tip_count") + "; "
    record = {"id": "$it.video_id", "title": "$it.title", "channel": "$it.uploader",
              "date": DATE, "upload_date": "$it.upload_date", "topic": TOPIC,
              "n": "$건수.value", "info_error": "$it.info_error"}
    do += action("table:take", items=[record], n=1) + " >> " + action("table:compute", set={
        "verdict": "'tips_' + str(n) if n > 0 else ('not_selected' if info_error else ('too_old' if upload_date < '" + CUTOFF + "' else 'not_selected'))",
        "note": "'영상 정보 조회 실패; 최신성 미확인' if info_error else ('자막에서 팁 추출' if n > 0 else '선정·정독·팁 확정 제외; 실험 단계 파일 참조')"})
    do += " >> " + action("table:select", columns=["id", "title", "channel", "date", "upload_date", "topic", "verdict", "note"])
    assign("원장델타", "$정보 >> " + action("table:each", limit=60, do=do))
    checkpoint("원장델타", "08_ledger_delta")
    assign("평탄팁", "$편집 >> " + action("table:compute", set={
        "topic": repr(TOPIC), "channel": "uploader", "date": repr(DATE), "report": repr(Path(report).name)})
        + " >> " + action("table:select", columns=["tip", "how", "topic", "video_id", "title", "channel", "url", "date", "report", "try_candidate"]))
    checkpoint("평탄팁", "09_tips_flat")
    assign("중첩", action("self:script", op="run", id="팁행source중첩", args={
        "src": str(OUT / "09_tips_flat.json"), "out": str(OUT / "10_tips_nested.json")}))
    assign("원장갱신", action("self:ledger", op="upsert", path=covered, target="covered", key="id",
        items_file=str(OUT / "08_ledger_delta.json")))
    assign("주제갱신", action("self:ledger", op="append", path=covered, target="recent_topics",
        item={"date": DATE, "topic": TOPIC}, max_items=10))
    assign("팁갱신", action("self:ledger", op="append", path=tips,
        items_file=str(OUT / "10_tips_nested.json")))
    assign("M", action("self:ledger", path=tips, fields=["tip"])
        + " >> " + action("table:reduce", init=0, step="acc + 1"))
    assign("K", action("self:ledger", path=covered, target="covered", fields=["id"],
        where={"field": "verdict", "op": "startswith", "value": "tips_"})
        + " >> " + action("table:reduce", init=0, step="acc + 1"))
    assign("T", action("self:ledger", path=covered, target="covered", fields=["id"])
        + " >> " + action("table:reduce", init=0, step="acc + 1"))
    for var, source in [("N", "완료영상"), ("검사수", "정보"), ("최신수", "최신"), ("오늘팁수", "편집")]:
        assign(var, f"${source} >> " + action("table:reduce", init=0, step="acc + 1"))
    assign("보고재료", "$편집 >> " + action("table:select", columns=[
        "tip", "how", "tools", "hype", "timestamp", "_quote", "video_id", "title", "uploader", "url", "implication", "try_candidate"]))
    instruction = (
        f"유튜브 AI 팁 보고서 완성본을 한국어 Markdown으로 쓴다. H1 정확히 '# 유튜브 AI 팁 보고서 — {DATE} — {TOPIC}'. "
        "머리줄 정확히 '> 오늘의 영상 ${N.value}편 · 누적: 팁 ${M.value}개 / 다룬 영상 ${K.value}편(후보 등재 ${T.value}편)'. "
        "## 한눈에 (TL;DR): 최강 신호 2~3개, 서로 다른 영상이 같은 결론/반대 결론이면 명시하되 억지 교차 확인 금지. "
        "## 오늘의 팁: 입력 모든 ${오늘팁수.value}개를 tip 제목 그대로 ### 번호. 제목으로 배치하고 "
        "각각 - **방법**: how의 구체적 단계·설정을 빠짐없이, - **출처**: [title](url) — uploader · timestamp, "
        "- **보정**: hype(없으면 생략), - **우리 시스템 함의**: implication 순서. "
        "원문에 없는 단계·명령·도구·수치는 추가하지 말고 how가 비면 영상 확인 필요라고 적는다. "
        "timestamp가 null이면 '시각 미확인'으로 표시. 불확실한 고유명사는 자막 표기·철자 불확실이라고 표시한다. "
        "## 시도 후보: try_candidate true인 것만 최대 3개. 그날 호의 제안으로만 쓰고 재촉·부채 금지. "
        "## 오늘의 영상: 아래 실제 영상 목록 각각 [title](url) — uploader · view_count회 · duration초 · "
        "upload_date · 팁 밀도·과장에 대한 한줄평. 영상 목록: ${완료영상.items}. "
        "## 지켜볼 점 / 내일 주제 후보: 디버깅 관점의 남은 논점과 최근 주제에 없는 후보 2개. "
        "최근 주제: ${최근주제.items}. "
        "## 이 호의 한계: 자막만 읽었고 실효는 테스트하지 않았음, 날짜 확인 ${검사수.value}편 중 "
        "180일 통과 ${최신수.value}편, 팁 확정에 기여한 정독 ${N.value}편. "
        "원장 복사본에서 실행한 실험판이며 누적 수는 그 복사본 기준임을 명시. "
        "_quote는 기계 검증용 근거이므로 장문 인용을 싣지 말라. 본문 전체를 코드펜스로 감싸지 말라.")
    assign("보고서", "$보고재료 >> " + action("table:brief", instruction=instruction,
        criteria="지정한 H1·머리줄과 6개 섹션을 갖춘 한국어 보고서. 입력 팁을 모두 다루고 "
            "각 팁에 방법·정확한 출처 URL·시각 또는 시각 미확인·우리 시스템 함의가 있다. "
            "입력 밖 방법·명령·수치를 추가하지 않으며 시도 후보 최대 3개. 실효 미검증·실험판을 명시."))
    assign("md", "$보고서 >> " + action("self:write", path=report))
    assign("html", action("self:script", op="run", id="보고서HTML", args={
        "src": report, "dst": html, "subtitle": "IBL 한 번 실행 실험판 · 자막 기반 · 실효 미검증",
        "theme": "card", "drop_lines": ["우리 시스템 함의"]}))
    assign("return", action("table:take", n=1, items=[{
        "report": report, "html": html, "videos": "$N.value", "tips": "$오늘팁수.value",
        "checked": "$검사수.value", "fresh": "$최신수.value", "M": "$M.value", "K": "$K.value", "T": "$T.value"}]))
    tail = lines[guard_start:]
    failure = action("self:ledger", op="append", path=str(OUT / "_scan_log.json"),
        item={"date": DATE, "reason": "팁 수 8~15·영상 수 2~4·영상당 2~5 검법 미충족. 단계 파일 참조.",
              "retry": "실험 결과로 보고하고 원인 확인"}, max_items=60)
    failure += "; $return = " + action("table:take", n=1, items=[{
        "status": "quality_gate_failed", "tips": "$검법팁수.value", "videos": "$검법편수.value"}]) + ";"
    return "\n\n".join(lines[:guard_start]) + "\n\n" + (
        "[if: $검법팁수.value >= 8 and $검법팁수.value <= 15 and "
        "$검법편수.value >= 2 and $검법편수.value <= 4 and empty($불균형.items)]{\n"
        + "\n\n".join(tail) + "\n} [else]{\n" + failure + "\n}\n")


def prepare():
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "db").mkdir(exist_ok=True)
    (OUT / "transcripts").mkdir(exist_ok=True)
    for name in ["_covered_videos.json", "db/tips.json"]:
        if (OUT / name).exists():
            raise SystemExit(f"기존 실험 입력을 덮어쓰지 않습니다: {OUT / name}")
        shutil.copy2(SOURCE / name, OUT / name)
    dump(OUT / "manifest.json", {
        "prepared_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "date": DATE, "cutoff": CUTOFF, "topic": TOPIC, "task_id": TASK,
        "scope": "실제 검색·자막·AI; 원장 복사본; HTML 로컬 실험판. 배포·알림 제외.",
        "inputs": {name: hashlib.sha256((SOURCE / name).read_bytes()).hexdigest()
                   for name in ["_covered_videos.json", "db/tips.json"]},
        "guide_sha256": hashlib.sha256((ROOT / "data/guides/youtube_ai_tips_report.md").read_bytes()).hexdigest(),
    })
    (OUT / "program.ibl").write_text(program(), encoding="utf-8")
    print(OUT)


def call(check=False, recovery=False, finish=False):
    code = (OUT / ("finish.ibl" if finish else "recovery.ibl" if recovery else "program.ibl")).read_text(encoding="utf-8")
    payload = {"code": code, "project_path": str(ROOT), "task_id": TASK + ("-check" if check else ""),
               "parent_run_id": "experiment-ai-tips-20260908", "check": check, "origin": "user"}
    if not check:
        payload["ticket"] = "a170202609080003" if finish else "a170202609080002" if recovery else "a170202609080001"
    if recovery:
        payload["resume"] = {"vars_ref": json.loads((OUT / "run_result.json").read_text())["resume_vars"]["vars_ref"]}
    label = "preflight" if check else "finish" if finish else "recovery" if recovery else "run"
    dump(OUT / f"{label}_request.json", payload)
    started = dt.datetime.now(dt.timezone.utc).isoformat()
    t0 = time.monotonic()
    req = urllib.request.Request("http://127.0.0.1:8765/ibl/execute",
        data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=3600) as response:
            result = json.load(response)
    except Exception as exc:
        result = {"transport_error": repr(exc)}
    elapsed = time.monotonic() - t0
    dump(OUT / f"{label}_result.json", result)
    dump(OUT / f"{label}_timing.json", {"started_at": started,
        "finished_at": dt.datetime.now(dt.timezone.utc).isoformat(), "wall_seconds": elapsed,
        "code_chars": len(code), "code_sha256": hashlib.sha256(code.encode()).hexdigest()})
    print(json.dumps({"elapsed": elapsed, "result": result}, ensure_ascii=False)[:18000], flush=True)


def prepare_recovery():
    original = (OUT / "program.ibl").read_text()
    # 같은 시간·텍스트를 IBL의 결정론 fold로 보존. 모델 재추출이나 자막 재요청 없음.
    time_line = ("acc + '[' + str(int(start // 60)) + ':' + "
                 "('0' if int(start % 60) < 10 else '') + str(int(start % 60)) + '] ' + text + '\\n'")
    do = action("self:read", path=str(OUT / "transcripts/${it.video_id}.json"))
    do += " >> " + action("table:reduce", init="", step=time_line)
    do += " >> " + action("self:write", path=str(OUT / "transcripts/${it.video_id}.txt"))
    prefix = "$자막본문복원 = $정독영상 >> " + action("table:each", limit=4, parallel=4, do=do) + ";\n\n"
    tail = "$상세 = " + original.split("$상세 = ", 1)[1]
    tail = tail.replace("${it.video_id}.json", "${it.video_id}.txt")
    tail = tail.replace("원장 복사본에서 실행한 실험판이며", "선정된 영상 4편은 실제로 모두 영어다. "
        "branch는 검색어 갈래일 뿐 실제 언어·회의론 성격을 보증하지 않는다. "
        "한국어권의 관련 최신 자료와 실질적인 회의론 관점은 확보하지 못했다고 한계에 명시하라. "
        "원장 복사본에서 실행한 실험판이며")
    (OUT / "recovery.ibl").write_text(prefix + tail)


def prepare_finish():
    from ibl_parser import _extract_bracket_raw
    edited = json.loads((OUT / "07_edited.json").read_text())["items"]
    counts = {}
    for row in edited:
        counts[row["video_id"]] = counts.get(row["video_id"], 0) + 1
    if not (8 <= len(edited) <= 15 and 2 <= len(counts) <= 4 and all(2 <= n <= 5 for n in counts.values())):
        raise SystemExit("산출물 검법 미충족: 저장 분기를 실행하지 않습니다.")
    code = (OUT / "recovery.ibl").read_text()
    start = code.index("[if: $검법팁수.value")
    body, _ = _extract_bracket_raw(code, code.index("]{", start) + 1, "{", "}")
    prefix = []
    for var, file in [("편집", "07_edited.json"), ("정보", "02_info.json"), ("심사", "03_selection.json")]:
        prefix.append(f"${var} = " + action("self:read", path=str(OUT / file)) + ";")
    prefix.append("$최근주제 = " + action("self:ledger", path=str(OUT / "_covered_videos.json"), target="recent_topics") + ";")
    prefix.append("$팁수 = $편집 >> " + action("table:groupby", by="video_id", agg={"tip_count": ["count"]}) + ";")
    prefix.append("$정독영상 = $심사 >> " + action("table:filter", where={"selected": True}) + ";")
    prefix.append("$완료영상 = " + action("table:join", left="$정독영상", right="$팁수", on="video_id") + ";")
    (OUT / "finish.ibl").write_text("\n".join(prefix) + "\n" + body + "\n")


def audit():
    """모델 본문·비공개 추론을 복제하지 않고 사건·산출물의 계수만 저장한다."""
    conn = sqlite3.connect(f"file:{ROOT / 'data/world_pulse.db'}?mode=ro", uri=True)
    events = [(seq, ts, kind, json.loads(data or "{}")) for seq, ts, kind, data in conn.execute(
        "SELECT event_seq,ts,kind,data FROM trajectory_event WHERE task_id=? ORDER BY event_seq", (TASK,))]
    conn.close()
    usage = [dict(d, event_seq=seq, ts=ts) for seq, ts, kind, d in events if kind == "model.usage"]
    by_role = {}
    for u in usage:
        r = by_role.setdefault(u.get("role", "unknown"), {"calls": 0})
        r["calls"] += 1
        for k in ("input", "output", "cache_read", "cache_create", "reasoning", "latency_ms"):
            if k in u:
                r[k] = r.get(k, 0) + u[k]
    counts = {k: sum(u.get(k, 0) for u in usage) for k in
              ("input", "output", "cache_read", "cache_create", "reasoning")}
    stages = {}
    for file in sorted(OUT.glob("[0-9]*.json")):
        obj = json.loads(file.read_text())
        stages[file.stem] = obj.get("items", []) if isinstance(obj, dict) else obj
    result = {"task_id": TASK, "ibl_invocations": sum(k == "ibl.started" for _, _, k, _ in events),
        "completed_model_calls": len(usage), "tokens": counts, "by_role": by_role, "usage": usage,
        "response_ids": len({d.get("response_id") for _, _, k, d in events if k == "model.response_snapshot"}),
        "models": sorted({d.get("model") for _, _, k, d in events if k == "model.round" and d.get("model")}),
        "stage_counts": {k: len(v) for k, v in stages.items()},
        "timing": json.loads((OUT / "run_timing.json").read_text()) if (OUT / "run_timing.json").exists() else None}
    timings = {name: json.loads((OUT / f"{name}_timing.json").read_text())
               for name in ("run", "recovery", "finish", "qualityfix")
               if (OUT / f"{name}_timing.json").exists()}
    result["timings"] = timings
    result["execution_wall_seconds_sum"] = sum(t["wall_seconds"] for t in timings.values())
    if timings:
        result["elapsed_including_repairs_seconds"] = (
            max(dt.datetime.fromisoformat(t["finished_at"]) for t in timings.values())
            - min(dt.datetime.fromisoformat(t["started_at"]) for t in timings.values())).total_seconds()
    manifest = json.loads((OUT / "manifest.json").read_text())
    result["production_ledgers_unchanged"] = all(
        hashlib.sha256((SOURCE / n).read_bytes()).hexdigest() == h for n, h in manifest["inputs"].items())
    selected = [r for r in stages.get("03_selection", []) if r.get("selected") is True]
    result["selected_videos"] = [{k: r.get(k) for k in
        ("video_id", "title", "uploader", "upload_date", "duration", "language", "branch", "reason")} for r in selected]
    details = stages.get("06_details", [])
    evidence = []
    for r in details:
        file = OUT / "transcripts" / (str(r.get("video_id")) + ".json")
        segs = json.loads(file.read_text()).get("items", []) if file.exists() else []
        text = " ".join(str(s.get("text", "")) for s in segs)
        quote = r.get("_quote") or ""
        normalized = lambda s: re.sub(r"\s+", " ", s).strip()
        evidence.append({"video_id": r.get("video_id"), "tip": r.get("tip"),
            "timestamp": r.get("timestamp"), "timestamp_error": r.get("_timestamp_error"),
            "quote_present_in_saved_transcript": bool(quote) and normalized(quote) in normalized(text),
            "how_nonempty": bool(str(r.get("how") or "").strip())})
    result["evidence_checks"] = evidence
    report = OUT / f"ai_tips_report_{DATE}_{TOPIC}.md"
    html = OUT / f"AI 팁 보고서 {DATE} {TOPIC}.html"
    if report.exists():
        md = report.read_text()
        ledger = json.loads((OUT / "_covered_videos.json").read_text())["covered"]
        tips = json.loads((OUT / "db/tips.json").read_text())
        k = sum(str(r.get("verdict", "")).startswith("tips_") for r in ledger)
        n = len({r["video_id"] for r in stages.get("07_edited", [])})
        expected = f"> 오늘의 영상 {n}편 · 누적: 팁 {len(tips)}개 / 다룬 영상 {k}편(후보 등재 {len(ledger)}편)"
        body = html.read_text() if html.exists() else ""
        info_ids = {r["video_id"] for r in stages.get("02_info", [])}
        delta_ids = {r["id"] for r in stages.get("08_ledger_delta", [])}
        result["artifact_checks"] = {
            "report_chars": len(md), "tip_headings": len(re.findall(r"^### \d+\.", md, re.M)),
            "implication_lines": sum("우리 시스템 함의" in l for l in md.splitlines()),
            "header_matches_updated_ledgers": expected in md,
            "info_ids_equal_ledger_delta_ids": info_ids == delta_ids,
            "html_exists": html.exists(), "html_links": len(re.findall(r"<a\s[^>]*href=", body)),
            "html_contains_private_implications": "우리 시스템 함의" in body,
            "sections": re.findall(r"^## (.+)$", md, re.M),
            "M": len(tips), "K": k, "T": len(ledger),
        }
    dump(OUT / "audit.json", result)
    print(json.dumps({k: v for k, v in result.items() if k not in ("usage", "selected_videos", "evidence_checks")},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["prepare", "build", "check", "run", "audit", "recover", "finish"])
    mode = parser.parse_args().mode
    if mode == "prepare":
        prepare()
    elif mode == "build":
        (OUT / "program.ibl").write_text(program(), encoding="utf-8")
    elif mode == "audit":
        audit()
    elif mode == "recover":
        prepare_recovery()
        call(recovery=True)
    elif mode == "finish":
        prepare_finish()
        call(finish=True)
    else:
        call(check=mode == "check")
