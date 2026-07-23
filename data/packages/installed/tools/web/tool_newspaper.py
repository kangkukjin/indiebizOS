# -*- coding: utf-8 -*-
"""tool_newspaper.py — 신문 발행(결정론적 IBL 파이프의 도구화)

[engines:newspaper] 핸들러. 옛 engines:newspaper(수집+조립+브라우저 열기 박제)와 다른 개념:
현행 '판(edition) 3파일' 모델(newspaper_guide.md 정본)을 **한 액션**으로 결정화한 것.

배경: 발행 로직이 데스크탑 계기(NewspaperInstrument.tsx) React 코드에만 살아서, 원격/폰
신문앱 '새 신문 발행' 버튼은 시스템 AI 자연어 위임([others:delegate]{scope:system})으로
우회했고, 시스템 AI가 레시피를 안 따르면 조용히 무시됐다. 이 도구가 그 레시피를 어휘로
내려 어느 표면에서 눌러도 같은 결정론 경로가 돈다(위임 소멸).

흐름(가이드 '현행 발행 레시피' 그대로):
  1. 서버 설정(제호·키워드) 로드 — projects/앱모드/outputs/newspaper_config.json
     (키워드의 단일 소스. 데스크탑 계기도 이 파일을 읽고 쓴다 — localStorage 이전.)
  2. search_gnews 배치 팬아웃 1회 — {queries, headlines:true, curate:7}
     (RSS 병렬 + 경량 AI 편집장 일괄 편성 + 가디언 합류. handler.py 기존 배치 경로 재사용.)
  3. 판 조립 → 3파일 + 아카이브(전부 앱모드 outputs/, 데스크탑 계기와 같은 계약):
     newspaper_current.json(데스크탑 카드 그리드) / .md(폰·원격 뷰어) / .html(폰 공유)
     + newspaper_archive/newspaper_<YYYY-MM-DD>.json(발아 대조)

주의: HTML 마스트헤드의 날씨·코스피 줄은 생략(데스크탑 계기 발행만 포함 — 크로스 패키지
호출 없이 결정론 유지, 장식은 본질 아님).
"""

import json
import re
from datetime import datetime
from pathlib import Path

# handler.py 가 backend 를 sys.path 에 올려둔 뒤 load_module 로 로드한다.
from runtime_utils import get_base_path

APP_PROJECT = "앱모드"          # 판 파일이 사는 시스템 프로젝트 (가이드 정본)
CONFIG_FILE = "newspaper_config.json"
SECTION_SIZE = 7                # 섹션당 기사 수 — 계기 SECTION_SIZE 와 일치(가이드)
HOT_QUERY = "오늘의 핫토픽"      # handler 배치 경로가 헤드라인 섹션에 붙이는 query 태그
HOT_LABEL = "🔥 오늘의 핫토픽"   # 판에 저장되는 섹션 이름(데스크탑 hotLabel 파리티)

# 기본 설정 — 데스크탑 계기 EDITIONS 의 default 판과 동일(가이드 '계기 기본 키워드 12개')
DEFAULT_CONFIG = {
    "default": {
        "title": "청주 데일리",
        "keywords": ["청주", "AI", "문화", "드라마", "영화", "만화", "세종",
                     "경제", "주식", "부동산", "AI 에이전트", "중국 경제"],
    },
    "hn": {
        "title": "Hacker News 데일리",
        "keywords": ["AI", "LLM", "startup", "programming", "security", "open source"],
    },
}


def _outputs_dir() -> Path:
    return get_base_path() / "projects" / APP_PROJECT / "outputs"


def _load_config() -> dict:
    """서버 설정 로드. 없으면 기본값을 파일로 결정화(데스크탑·원격이 이후 편집 가능)."""
    path = _outputs_dir() / CONFIG_FILE
    try:
        cfg = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(cfg, dict) and cfg:
            return cfg
    except Exception:
        pass
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(DEFAULT_CONFIG, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass
    return dict(DEFAULT_CONFIG)


def _parse_keywords(raw) -> list:
    if isinstance(raw, list):
        return [str(k).strip() for k in raw if str(k).strip()]
    if isinstance(raw, str):
        return [k.strip() for k in re.split(r"[,\n]", raw) if k.strip()]
    return []


def _today_label() -> str:
    d = datetime.now()
    wd = ["월", "화", "수", "목", "금", "토", "일"][d.weekday()]
    return f"{d.year}년 {d.month}월 {d.day}일 ({wd})"


# ── HTML 판 (데스크탑 buildNewspaperHtml 포팅 — 마스트헤드 날씨·지수 줄만 생략) ──

def _esc(s) -> str:
    return (str(s or "")
            .replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


_HTML_CSS = """
  :root { color-scheme:light; --paper:#fbf9f3; --ink:#1b1b1b; --muted:#6b675e; --rule:#1b1b1b; --hair:#cfc9ba; --accent:#7a1f1f; }
  * { box-sizing:border-box; }
  body { margin:0; background:#e9e4d8; color:var(--ink); line-height:1.6;
    font-family:'Noto Serif KR',Georgia,'Times New Roman',serif; -webkit-font-smoothing:antialiased; }
  .paper { max-width:1060px; margin:28px auto; background:var(--paper); padding:44px 52px 60px;
    box-shadow:0 2px 24px rgba(0,0,0,.14); border:1px solid #d8d2c4; }
  .dateline { display:flex; justify-content:space-between; align-items:center;
    font-family:-apple-system,BlinkMacSystemFont,'Noto Sans KR',sans-serif;
    font-size:.72rem; letter-spacing:.14em; text-transform:uppercase; color:var(--muted);
    border-bottom:1px solid var(--hair); padding-bottom:8px; }
  .nameplate { text-align:center; font-weight:900; letter-spacing:-.02em; color:#111;
    font-size:clamp(2.6rem,7vw,4.4rem); line-height:1; margin:.28em 0 .14em; }
  .strip { text-align:center; font-family:-apple-system,BlinkMacSystemFont,'Noto Sans KR',sans-serif;
    font-size:.82rem; letter-spacing:.03em; color:var(--muted);
    border-top:3px double var(--rule); border-bottom:3px double var(--rule); padding:8px 0; margin-top:4px; }
  .sec { margin-top:34px; }
  .rubric { display:flex; align-items:center; gap:16px; margin:0 0 18px; color:var(--accent);
    font-family:-apple-system,BlinkMacSystemFont,'Noto Sans KR',sans-serif;
    font-size:.9rem; font-weight:800; letter-spacing:.16em; text-transform:uppercase; }
  .rubric::before, .rubric::after { content:''; flex:1; border-top:1.5px solid var(--rule); }
  .rubric span { white-space:nowrap; }
  .cols { columns:300px 3; column-gap:30px; }
  .art { break-inside:avoid; margin:0 0 20px; padding-bottom:16px; border-bottom:1px solid var(--hair); }
  .art h3 { font-size:1.05rem; font-weight:700; line-height:1.35; margin:0 0 6px; }
  .art h3 a { color:var(--ink); text-decoration:none; }
  .art h3 a:hover { text-decoration:underline; }
  .art .meta { font-family:-apple-system,BlinkMacSystemFont,'Noto Sans KR',sans-serif;
    font-size:.68rem; letter-spacing:.06em; text-transform:uppercase; color:var(--muted); margin-bottom:6px; }
  .art p { font-size:.92rem; color:#33322e; margin:0; text-align:justify; hyphens:auto; }
  .lead { border-bottom:2px solid var(--rule); padding-bottom:20px; margin-bottom:22px; }
  .lead h3 { font-size:1.9rem; font-weight:900; line-height:1.18; letter-spacing:-.01em; }
  .lead p { font-size:1.02rem; color:#26251f; }
  .lead p::first-letter { float:left; font-size:3.1em; line-height:.72; font-weight:900; padding:.02em .1em 0 0; color:var(--accent); }
  .empty { color:var(--muted); font-style:italic; }
  footer { margin-top:52px; border-top:1px solid var(--hair); padding-top:18px; text-align:center; color:var(--muted);
    font-family:-apple-system,BlinkMacSystemFont,'Noto Sans KR',sans-serif; font-size:.72rem; letter-spacing:.1em; }
  @media (max-width:600px) {
    .paper { padding:26px 20px 40px; margin:0; border:none; }
    .cols { columns:1; }
    .lead h3 { font-size:1.5rem; }
  }
  @media print {
    body { background:#fff; }
    .paper { box-shadow:none; border:none; margin:0; max-width:none; padding:0; }
    .art h3 a { color:#000; }
    @page { margin:15mm; }
  }
"""


def _article_html(it: dict, lead: bool = False) -> str:
    head = (f'<a href="{_esc(it.get("url"))}" target="_blank" rel="noopener">{_esc(it.get("title"))}</a>'
            if it.get("url") else _esc(it.get("title")))
    meta = f'<div class="meta">{_esc(it.get("meta"))}</div>' if it.get("meta") else ""
    summary = f'<p>{_esc(it.get("summary"))}</p>' if it.get("summary") else ""
    return f'<article class="art{" lead" if lead else ""}"><h3>{head}</h3>{meta}{summary}</article>'


def _section_html(sec: dict, first: bool) -> str:
    items = sec.get("items") or []
    rubric = f'<h2 class="rubric"><span>{_esc(sec.get("keyword"))}</span></h2>'
    if not items:
        return f'<section class="sec">{rubric}<div class="empty">관련 뉴스가 없습니다.</div></section>'
    if first:
        lead, rest = items[0], items[1:]
        cols = f'<div class="cols">{"".join(_article_html(it) for it in rest)}</div>' if rest else ""
        body = _article_html(lead, lead=True) + cols
    else:
        body = f'<div class="cols">{"".join(_article_html(it) for it in items)}</div>'
    return f'<section class="sec">{rubric}{body}</section>'


def _build_html(title: str, date_label: str, sections: list) -> str:
    sections_html = "\n".join(_section_html(sec, i == 0) for i, sec in enumerate(sections))
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{_esc(title)} — {_esc(date_label)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com"/>
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin/>
<link href="https://fonts.googleapis.com/css2?family=Noto+Serif+KR:wght@400;700;900&display=swap" rel="stylesheet"/>
<style>{_HTML_CSS}</style></head>
<body><main class="paper">
  <div class="dateline"><span>IndieBiz OS</span><span>나만의 신문</span></div>
  <h1 class="nameplate">{_esc(title)}</h1>
  <div class="strip">{_esc(date_label)}</div>
  {sections_html}
  <footer>IndieBiz OS · 나만의 신문 · 자동 편집 지면</footer>
</main></body></html>"""


def _build_markdown(title: str, date_label: str, sections: list) -> str:
    """폰/원격 뷰어([self:read]{blocks:true})용 마크다운 판."""
    lines = [f"# {title}", "", date_label, ""]
    for sec in sections:
        lines.append(f"## {sec.get('keyword')}")
        lines.append("")
        for it in (sec.get("items") or []):
            t = str(it.get("title") or "").strip()
            url = str(it.get("url") or "").strip()
            head = f"[{t}]({url})" if url else t
            lines.append(f"**{head}**")
            if it.get("meta"):
                lines.append(str(it["meta"]))
            if it.get("summary"):
                lines.append(str(it["summary"]))
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


STATE_FILE = "newspaper_publish_state.json"   # 백그라운드 발행 진행 상태(뷰어·상태 버튼이 읽음)
STALE_BUILDING_SEC = 300                       # building 이 5분 넘게 남아 있으면 죽은 발행으로 간주


def _read_state(out: Path) -> dict:
    try:
        return json.loads((out / STATE_FILE).read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_state(out: Path, state: dict):
    try:
        out.mkdir(parents=True, exist_ok=True)
        (out / STATE_FILE).write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def publish_newspaper(tool_input: dict, gnews_batch) -> dict:
    """발행 진입점 — 기본 **백그라운드**(family-news create 선례: 발행 ~1분이 폰 @hub 포워드
    read timeout(30s)·LTE 푸시 대기(20s)를 넘겨, 동기로 두면 폰·원격 버튼이 타임아웃으로
    오판한다). 즉시 반환하고 데몬 스레드가 발행, 진행 상태는 STATE_FILE 로 확인.
    wait:true 면 동기 발행(테스트·블로킹 호출용)."""
    out = _outputs_dir()
    if tool_input.get("wait") in (True, "true", "True", 1, "1"):
        return _publish_sync(tool_input, gnews_batch)

    # 이미 발행 중이면 중복 기동 방지 (죽은 building 은 STALE 초과 시 무시)
    state = _read_state(out)
    if state.get("status") == "building":
        try:
            started = datetime.fromisoformat(state.get("started_at", ""))
            if (datetime.now() - started).total_seconds() < STALE_BUILDING_SEC:
                return {"success": True, "queued": True,
                        "message": f"이미 발행 중입니다 ({state.get('started_at', '')[:19]} 시작) — 잠시 후 신문 탭에서 확인하세요."}
        except Exception:
            pass

    _write_state(out, {"status": "building", "started_at": datetime.now().isoformat()})

    import threading

    def _bg():
        try:
            result = _publish_sync(tool_input, gnews_batch)
            _write_state(out, {
                "status": "done" if result.get("success") else "error",
                "started_at": datetime.now().isoformat(),
                "finished_at": datetime.now().isoformat(),
                "message": result.get("message") or result.get("error", ""),
            })
        except Exception as e:
            _write_state(out, {"status": "error", "finished_at": datetime.now().isoformat(),
                               "message": f"발행 실패: {e}"})

    threading.Thread(target=_bg, daemon=True).start()
    return {"success": True, "queued": True,
            "message": "신문 발행을 시작했습니다 — 약 1분 뒤 신문 탭을 다시 열면 새 판이 보입니다. (발행 상태 버튼으로 진행 확인)"}


def _publish_sync(tool_input: dict, gnews_batch) -> dict:
    """발행 본체(동기). gnews_batch = handler 의 search_gnews 배치 경로를 부르는 콜러블
    (tool_input dict → JSON 문자열). 반환은 dict(핸들러가 format_json)."""
    cfg = _load_config().get("default") or DEFAULT_CONFIG["default"]
    keywords = _parse_keywords(tool_input.get("keywords")) or _parse_keywords(cfg.get("keywords")) \
        or DEFAULT_CONFIG["default"]["keywords"]
    title = str(tool_input.get("title") or cfg.get("title") or DEFAULT_CONFIG["default"]["title"]).strip()
    sources = str(tool_input.get("sources") or "gnews,guardian")

    # 1. 취재+편성 — 배치 팬아웃 1회(RSS 병렬 + 편집장 일괄 curate + 가디언 합류)
    raw = gnews_batch({"queries": keywords, "headlines": True,
                       "curate": SECTION_SIZE, "sources": sources})
    res = json.loads(raw) if isinstance(raw, str) else (raw or {})
    if not res.get("success"):
        return {"success": False, "error": f"뉴스 수집 실패: {res.get('error', '알 수 없는 오류')}"}

    # 2. query 태그 → 섹션 (핫토픽 맨 앞, 이후 키워드 순서 보존 — 데스크탑 판과 동일 구조)
    by_q = {}
    for it in (res.get("items") or []):
        by_q.setdefault(it.get("query"), []).append(it)
    sections = []
    if by_q.get(HOT_QUERY):
        sections.append({"keyword": HOT_LABEL, "items": by_q[HOT_QUERY]})
    for kw in keywords:
        sections.append({"keyword": kw, "items": by_q.get(kw, [])})

    date_label = _today_label()
    issued_at = datetime.now().isoformat()
    edition = {"title": title, "keywords": keywords, "sections": sections,
               "dateLabel": date_label, "issuedAt": issued_at}
    if isinstance(res.get("perspective"), bool):
        edition["perspective"] = res["perspective"]

    # 3. 판 3파일 + 아카이브 (JSON 은 필수 — 실패 시 발행 실패. MD/HTML 은 best-effort, 데스크탑과 동일)
    out = _outputs_dir()
    out.mkdir(parents=True, exist_ok=True)
    content = json.dumps(edition, ensure_ascii=False)
    (out / "newspaper_current.json").write_text(content, encoding="utf-8")
    files = ["newspaper_current.json"]
    warn = []
    try:
        day = issued_at[:10]
        (out / "newspaper_archive").mkdir(parents=True, exist_ok=True)
        (out / "newspaper_archive" / f"newspaper_{day}.json").write_text(content, encoding="utf-8")
        files.append(f"newspaper_archive/newspaper_{day}.json")
    except Exception:
        warn.append("archive")
    try:
        (out / "newspaper_current.md").write_text(_build_markdown(title, date_label, sections), encoding="utf-8")
        files.append("newspaper_current.md")
    except Exception:
        warn.append("md")
    try:
        (out / "newspaper_current.html").write_text(_build_html(title, date_label, sections), encoding="utf-8")
        files.append("newspaper_current.html")
    except Exception:
        warn.append("html")

    total = sum(len(s["items"]) for s in sections)
    result = {
        "success": True,
        "message": f"『{title}』 발행 완료 — 섹션 {len(sections)}·기사 {total}건 ({date_label})",
        "title": title, "dateLabel": date_label,
        "sections": [{"keyword": s["keyword"], "count": len(s["items"])} for s in sections],
        "total_items": total, "files": files,
    }
    if isinstance(res.get("perspective"), bool):
        result["perspective"] = res["perspective"]
    if warn:
        result["warning"] = f"부분 실패(발행은 유지): {', '.join(warn)}"
    return result
