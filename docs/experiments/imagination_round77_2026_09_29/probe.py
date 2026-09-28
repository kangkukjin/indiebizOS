"""77회차: 강의·연구 자료 업무 (훈련 턴 · 무수정).

축 = 행동 기준 미조합 메뉴의 강의·연구 어휘(self:lecture·material·notebook, sense:researcher·book·entity·devdocs·paper,
table:structure·judge)를 table:dedup·union·merge·join·select·sort·each·document 와 조합.
도메인: 사용자(AI 주제 물리학박사·뇌과학 연구자·AI 저서 3권·AI 강의) — 이번 주 강의 주제 최근 논문 요약 표,
특정 연구자의 최근 논문·동명이인 분리, 책 서지 조회(정보나루·nl·google), 강의 재료·노트북에서 관련 메모 찾기,
개념 정의를 여러 원천에서 모아 비교, 참고문헌 목록 정리·인용 중복 제거, 주차별 주제와 자료 연결, 원천 실패 폴백.

모든 요청 edition 2·project_id 컨텐츠·origin training·agent_id IT77_probe·task_id IT77_task.
★사용자 강의·노트북·자료함은 읽기만. 쓰기는 IT77_ 스크래치(없으면 check 만), 끝에 삭제.
★외부 API(논문·도서·위키데이터·국회도서관)는 읽기 조회만, 같은 조회 반복 금지(과제 안 변수 재사용·reuse).
★유료 AI(notebook ask·table:structure·table:judge)는 최소 — 각 1회 이하, 행 5 이하.
★발신 0.
사용: .venv/bin/python probe.py baseline | run [tNN ...] | after | raw '<code>' [--check] | desc node:action ...
"""
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from datetime import datetime

HERE = Path(__file__).resolve().parent
BASE = Path('/Users/kangkukjin/Desktop/AI/indiebizOS')
AGENT = {'agent_id': 'IT77_probe', 'task_id': 'IT77_task'}
LOG = []
PULSE = BASE / 'data/world_pulse.db'
SINCE = BASE / 'data/table_since.db'


def post(route, payload=None, method='POST'):
    args = ['curl', '-sS', '--max-time', '280', '-X', method, f'http://127.0.0.1:8765/{route}',
            '-H', 'Content-Type: application/json']
    if payload is not None:
        args += ['--data-binary', '@-']
    proc = subprocess.run(args, input=json.dumps(payload) if payload is not None else None,
                          text=True, capture_output=True, check=True)
    return json.loads(proc.stdout)


def ex(code, **extra):
    payload = dict(code='#!ibl edition=2\n' + code, edition=2, project_id='컨텐츠', origin='training',
                   **AGENT, **extra)
    response = post('ibl/execute', payload)
    slim = {k: v for k, v in response.items() if k not in ('evidence', 'source_map', 'recordings', 'value_wire')}
    LOG.append({'request': payload, 'response': slim})
    return response


def codes(r):
    return [i.get('code') for i in r.get('issues') or []]


def err(r):
    e = r.get('error')
    if isinstance(e, dict):
        return json.dumps({k: e.get(k) for k in ('code', 'message', 'hint')}, ensure_ascii=False)[:600]
    if e:
        return str(e)[:600]
    return json.dumps([{k: i.get(k) for k in ('code', 'message')} for i in r.get('issues') or []],
                      ensure_ascii=False)[:600]


def val(r):
    return r.get('value')


def js(x, n=400):
    return json.dumps(x, ensure_ascii=False, default=str)[:n]


def q(db, sql, args=()):
    con = sqlite3.connect(str(db), timeout=10)
    try:
        return con.execute(sql, args).fetchall()
    finally:
        con.close()


def ok_or_err(r, n=500):
    return js(val(r), n) if r.get('success') else f"FAIL {err(r)}"


# ───────────────────────── 과제 ─────────────────────────
# 이번 주 강의(「인공지능이 할 수 있는 것, 할 수 없는 것」) 주제 = LLM 추론의 한계.

def t01():
    """[강의] 이번 주 강의 주제(LLM 추론의 한계) 최근 논문 5편을 찾아 제목·연도·인용수·링크·초록 첫 문장 표로."""
    r = ex("""
$p = [sense:paper]{query:"large language model reasoning limitations", source:"openalex", year_from:2025, sort_by:"cited", limit:5}
$rows = $p.items >> [table:compute]{set:($x)=> {연도: split($x.meta, " · ")[1], 초록첫문장: split(get($x,"summary",""), ". ")[0]}}
return {n:len($p.items), keys:keys($p), total:get($p,"total",null), truncated:get($p,"truncated",null), cols:keys($p.items[0]), rows:($rows >> [table:select]{columns:["title","meta","연도","url","초록첫문장"]})}
""")
    v = val(r) or {}
    return bool(r.get('success') and v.get('n') == 5), ok_or_err(r, 2500)


def t02():
    """[강의] arXiv 에서 같은 주제 최신 프리프린트 5편(최근순) — 날짜 순 정렬."""
    r = ex("""
$a = [sense:paper]{query:"LLM reasoning limitations", source:"arxiv", sort_by:"recent", year_from:2026, limit:5}
$rows = $a.items >> [table:compute]{set:($x)=> {날짜: split($x.meta, " · ")[-1]}} >> [table:sort]{by:"날짜", descending:true}
return {n:len($a.items), keys:keys($a), rows:($rows >> [table:select]{columns:["title","날짜","url"]})}
""")
    v = val(r) or {}
    return bool(r.get('success') and v.get('n')), ok_or_err(r, 2000)


def t03():
    """[연구자] 서울대 장병탁 교수의 최근 국내 논문 — 동명이인은 소속으로 가르고, 국회도서관 논문에서 그 이름이 저자인 것만 연도 역순 5편."""
    r = ex("""
$who = [sense:researcher]{op:"find", name:"장병탁", org:"서울대", limit:10}
$p = [sense:paper]{source:"nanet", query:"장병탁", limit:15}
$mine = $p.items >> [table:filter]{where:($x)=> contains($x.meta, "장병탁")} >> [table:compute]{set:($x)=> {연도: split($x.meta, " · ")[-1]}} >> [table:sort]{by:"연도", descending:true} >> [table:take]{n:5}
return {who:($who.items >> [table:select]{columns:["name","org","birth_year","position","lodID"]}), papers:len($p.items), total:get($p,"total",null), truncated:get($p,"truncated",null), mine:($mine >> [table:select]{columns:["title","meta","연도"]})}
""")
    v = val(r) or {}
    return bool(r.get('success') and v.get('who')), ok_or_err(r, 2500)


def t04():
    """[연구자] 흔한 이름(김민수) 연구자 — 동명이인 수를 소속별로 세고, 서울대 소속만 공저자망으로 교차 확인."""
    r = ex("""
$all = [sense:researcher]{op:"find", name:"김민수", limit:30}
$g = $all.items >> [table:groupby]{by:"org", agg:{명:["count"]}}
$by = $g.items >> [table:sort]{by:"명", descending:true} >> [table:take]{n:5}
$co = [sense:researcher]{op:"coauthor", name:"김민수", limit:10}
return {people:len($all.items), top_orgs:$by, co_n:len($co.items), co:($co.items >> [table:select]{columns:["name","org","lodID"]} >> [table:take]{n:5})}
""")
    v = val(r) or {}
    return bool(r.get('success') and v.get('people')), ok_or_err(r, 2000)


def t05():
    """[책] 강의 참고문헌용 — 『특이점이 온다』 서지를 정보나루·국립중앙도서관·구글북스 세 곳에서 모아 출판사·연도·ISBN 한 표로(원천 칸 표시)."""
    r = ex("""
$a = [sense:book]{title:"특이점이 온다", rows:5}
$b = [sense:book]{title:"특이점이 온다", source:"nl"}
$c = [sense:book]{query:"특이점이 온다 커즈와일", source:"google"}
$na = $a.items >> [table:take]{n:3} >> [table:compute]{set:($x)=> {원천:"정보나루", 연도:get($x,"publication_year",null), 출판사:get($x,"publisher",null), isbn:get($x,"isbn13",null)}}
$nb = $b.items >> [table:take]{n:3} >> [table:compute]{set:($x)=> {원천:"nl", 연도:get($x,"publication_year",null), 출판사:get($x,"publisher",null), isbn:get($x,"isbn13",null)}}
$nc = $c.items >> [table:take]{n:3} >> [table:compute]{set:($x)=> {원천:"google", 연도:get($x,"publication_year",null), 출판사:get($x,"publisher",null), isbn:get($x,"isbn13",null)}}
$u = [table:union]{inputs:[$na, $nb, $nc]}
return {counts:[len($a.items), len($b.items), len($c.items)], cols:[keys($a.items[0]), keys($b.items[0]), keys($c.items[0])], nl_meta:$b.items[0].meta, rows:($u.items >> [table:select]{columns:["원천","title","출판사","연도","isbn"]})}
""")
    v = val(r) or {}
    return bool(r.get('success') and v.get('rows')), ok_or_err(r, 3500)


def t06():
    """[책] 2025년판 『특이점이 온다』(ISBN 9791173320873) 대출 통계 — 누적 대출과 대출자 연령대 상위 3, 함께 빌린 책 3권."""
    r = ex("""
$d = [sense:book]{isbn:"9791173320873", detail:true}
$u = get($d, "usage", {})
return {keys:keys($d), book_keys:keys(get($d,"book",{})), total:get(get(get($d,"book",{}),"loan_stats",{}),"total",null), usage_keys:keys($u), co_loan:(get($u,"co_loan",[]) >> [table:take]{n:3}), items_n:len(get($d,"items",[]))}
""")
    v = val(r) or {}
    return bool(r.get('success') and v.get('total') is not None), ok_or_err(r, 2500)


def t07():
    """[강의자료] 내 강의들의 재료(원고)에서 '하네스'가 나오는 문단만 찾아 강의 제목·파일·문단 앞부분으로."""
    r = ex("""
$l = [self:lecture]{op:"list"}
$hits = $l.lectures >> [table:each]{mode:"flat_map"} {
  $lec = $it
  $m = [self:material]{op:"list", lecture_id:$lec.lecture_id}
  return $m.items >> [table:each]{mode:"flat_map"} {
    $doc = [self:read]{path:$it.path}
    return $doc.blocks >> [table:filter]{where:($b)=> contains(get($b,"text",""), "하네스")} >> [table:take]{n:2} >> [table:compute]{set:($b)=> {강의:$lec.title, 파일:$it.filename, 앞부분:get($b,"text","")[0:80]}}
  }
}
return {list_item_cols:keys($l.items[0]), n:len($hits), rows:($hits >> [table:select]{columns:["강의","파일","앞부분"]} >> [table:take]{n:6})}
""")
    v = val(r) or {}
    return bool(r.get('success') and v.get('n')), ok_or_err(r, 2500)


def t08():
    """[노트북] 'AI 동향' 노트북에서 '에이전트 메모리' 관련 발췌 5개(LLM 0) — 소스·위치·인용 한 표."""
    r = ex("""
$s = [self:notebook]{op:"search", name:"AI 동향", query:"에이전트 메모리", top_k:5}
return {keys:keys($s), n:len($s.items), cols:keys($s.items[0]), rows:($s.items >> [table:take]{n:5})}
""")
    v = val(r) or {}
    return bool(r.get('success') and v.get('n')), ok_or_err(r, 3000)


def t09():
    """[노트북] '카파시 강의' 노트북에 근거 고정 질문 — LLM 을 운영체제에 비유한 대목이 무엇인지, 인용과 함께(유료 1회)."""
    r = ex("""
$a = [self:notebook]{op:"ask", name:"카파시 강의", query:"LLM을 운영체제에 비유한 대목은 무엇이고 어떤 근거를 드는가?"}
return {keys:keys($a), mode:get($a,"mode",null), not_in:get($a,"not_in_sources",null), answer:get($a,"answer","")[0:300], cites:(get($a,"citations",[]) >> [table:take]{n:3}), items_n:len(get($a,"items",[]))}
""")
    v = val(r) or {}
    return bool(r.get('success') and v.get('cites')), ok_or_err(r, 2500)


def t10():
    """[개념] '환각(hallucination)' 정의를 위키데이터(뇌과학·AI 두 뜻)·논문(openalex)·도서(구글북스)에서 모아 원천별 한 줄 정의 비교표."""
    r = ex(reuse={'run_id': 'a5669155dd0d447eb69c8f25817f3d8c'}, code="""
$e0 = [sense:entity]{op:"resolve", query:"hallucination", lang:"en", limit:7}
# 첫 시도 contains($x.summary,"AI") 는 casefold 라 'pAInting by John D. Graham'(Q23946118)을 골랐다 → split 로 대소문자 구분
$ai = $e0.items >> [table:filter]{where:($x)=> len(split($x.summary, "AI")) > 1}
$neuro = $e0.items >> [table:filter]{where:($x)=> contains($x.summary, "perception")}
$p = [sense:paper]{query:"hallucination in large language models survey definition", limit:2}
$b = [sense:book]{query:"AI hallucination large language models", source:"google"}
$rows = [
  {원천:"wikidata(AI)", 이름:$ai[0].qid, 정의:$ai[0].summary, 근거:$ai[0].url},
  {원천:"wikidata(뇌과학)", 이름:$neuro[0].qid, 정의:$neuro[0].summary, 근거:$neuro[0].url},
  {원천:"openalex", 이름:$p.items[0].title, 정의:split(get($p.items[0],"summary",""), ". ")[0], 근거:$p.items[0].url},
  {원천:"google_books", 이름:$b.items[0].title, 정의:get($b.items[0],"description","")[0:160], 근거:get($b.items[0],"infoLink",null)}
]
return {counts:[len($e0.items), len($p.items), len($b.items)], rows:$rows}
""")
    v = val(r) or {}
    return bool(r.get('success') and v.get('rows')), ok_or_err(r, 3000)

def t11():
    """[참고문헌] 'in-context learning' 참고문헌을 openalex·arxiv·semantic scholar 에서 모아 제목 중복 빼고 저자·연도·링크 목록 마크다운(IT77_ 스크래치)으로."""
    r = ex("""
$o = [sense:paper]{query:"in-context learning transformers", source:"openalex", limit:5}
$a = [sense:paper]{query:"in-context learning transformers", source:"arxiv", limit:5}
$s = [sense:paper]{query:"in-context learning transformers", source:"semantic", limit:5} ?? {items:[], failed:true}
$u = [table:union]{inputs:[$o.items >> [table:compute]{set:($x)=> {원천:"openalex"}}, $a.items >> [table:compute]{set:($x)=> {원천:"arxiv"}}, $s.items >> [table:compute]{set:($x)=> {원천:"semantic"}}]}
$d = $u.items >> [table:dedup]{by:"title"}
$doc = $d.items >> [table:select]{columns:["title","meta","url","원천"]} >> [table:document]{format:"markdown", title:"in-context learning 참고문헌", filename:"IT77_참고문헌"}
return {counts:[len($o.items), len($a.items), len($s.items)], semantic_failed:get($s,"failed",false), union:len($u.items), dedup:len($d.items), doc_keys:keys($doc), path:get($doc,"path",null), md_head:get($doc,"markdown","")[0:400]}
""")
    v = val(r) or {}
    return bool(r.get('success') and v.get('path')), ok_or_err(r, 2500)


def t12():
    """[인용] 강의 슬라이드 두 판에서 모은 인용 목록의 중복 제거 — 대소문자·끝 마침표·부제 표기만 다른 같은 논문을 한 줄로(외부 호출 0)."""
    r = ex("""
$refs = [
  {title:"Attention Is All You Need", year:2017, doi:"10.48550/arXiv.1706.03762"},
  {title:"Attention is all you need.", year:2017, doi:"10.48550/ARXIV.1706.03762"},
  {title:"  attention is all you need ", year:"2017", doi:null},
  {title:"Language Models are Few-Shot Learners", year:2020, doi:"10.48550/arXiv.2005.14165"},
  {title:"Language models are few-shot learners (GPT-3)", year:2020, doi:"10.48550/arXiv.2005.14165"}
]
$by_title = $refs >> [table:dedup]{by:"title"}
$by_doi = $refs >> [table:dedup]{by:"doi"}
$by_pair = $refs >> [table:dedup]{by:["title","year"]}
return {by_title:len($by_title.items), by_doi:len($by_doi.items), by_pair:len($by_pair.items), doi_rows:($by_doi.items >> [table:select]{columns:["title","doi"]})}
""")
    v = val(r) or {}
    return bool(r.get('success')), ok_or_err(r, 2000)


def t13():
    """[강의계획] 4주 강의 계획의 주차별 주제마다 'AI 동향' 노트북에서 관련 발췌 2개씩 붙여 주차·주제·자료(소스·위치) 표(LLM 0)."""
    r = ex("""
$plan = [
  {주차:1, 주제:"에이전트와 도구 사용"},
  {주차:2, 주제:"AI 반도체와 추론 비용"},
  {주차:3, 주제:"오픈소스 모델과 규제"},
  {주차:4, 주제:"에이전트 보안과 권한"}
]
$linked = $plan >> [table:each]{mode:"flat_map"} {
  $w = $it
  $s = [self:notebook]{op:"search", name:"AI 동향", query:$w.주제, top_k:2}
  return $s.items >> [table:compute]{set:($x)=> {주차:$w.주차, 주제:$w.주제, 자료:$x.title, 위치:split($x.meta, " · ")[0]}}
}
return {n:len($linked), rows:($linked >> [table:select]{columns:["주차","주제","자료","위치"]})}
""")
    v = val(r) or {}
    return bool(r.get('success') and v.get('n') == 8), ok_or_err(r, 2500)


def t14():
    """[폴백] Semantic Scholar 로 먼저 찾고, 막히면 OpenAlex 로 — 어느 원천으로 답했는지와 앞 원천이 실패한 이유를 함께."""
    r = ex("""
$why = null
[try] {
  $p = [sense:paper]{query:"predictive coding neural networks", source:"semantic", year_from:2024, limit:3}
  $src = "semantic"
} [catch] {
  $why = {code:$error.code, message:$error.message}
  $p = [sense:paper]{query:"predictive coding neural networks", source:"openalex", year_from:2024, limit:3}
  $src = "openalex"
}
return {source:$src, why:$why, n:len($p.items), titles:($p.items >> [table:select]{columns:["title","meta"]})}
""")
    v = val(r) or {}
    return bool(r.get('success') and v.get('n')), ok_or_err(r, 2000)


def t15():
    """[실습] 강의 실습용 — Hugging Face transformers 의 pipeline 사용법 공식 문서를 찾아 앞부분만(라이브러리 ID 는 resolve 결과에서)."""
    r = ex("""
$lib = [sense:devdocs]{op:"resolve", library_name:"transformers"}
$first = $lib.items[0]
# 첫 시도 get($first,"id"/"library_id") → null(TYPE 거절). resolve 행은 title 이 빈 문자열이고 ID 는 meta 문자열에만 있다.
$doc = [sense:devdocs]{op:"search", library_id:$first.meta, query:"pipeline text generation quickstart"}
return {lib_cols:keys($first), raw_lib_cols:keys($lib.libraries[0]), lib:($lib.items >> [table:take]{n:3}), doc_keys:keys($doc), n:len(get($doc,"items",[])), head:(get($doc,"items",[]) >> [table:take]{n:2})}
""")
    v = val(r) or {}
    return bool(r.get('success') and v.get('n')), ok_or_err(r, 2500)


def t16():
    """[강의노트] 이번 주 주제 논문(T01 과 같은 조회 — reuse) 상위 3편 초록을 강의 노트 문서 IR 로 구조화(유료 1회) → 마크다운(IT77_ 스크래치)."""
    r = ex(reuse={'run_id': '20cfa31004324b8788baf3529b3474fe'}, code="""
$p = [sense:paper]{query:"large language model reasoning limitations", source:"openalex", year_from:2025, sort_by:"cited", limit:5}
$picked = $p.items >> [table:filter]{where:($x)=> len(split($x.title, "LLM")) > 1 or contains($x.title, "language model") or contains($x.title, "reasoning")} >> [table:take]{n:3}
$parts = $picked >> [table:each]{ return f"## ${$it.title}\\n${$it.meta}\\n${get($it,'summary','')[0:600]}" }
$src = join("\\n\\n", $parts)
$ir = [table:structure]{content:$src, instruction:"대학 교양 강의용 노트: 논문별 핵심 주장 1줄·근거 1줄·한계 1줄을 표로, 끝에 토론 질문 2개"}
$doc = $ir >> [table:document]{format:"markdown", filename:"IT77_강의노트"}
$types = get($ir,"blocks",[]) >> [table:each]{ return $it.type }
return {picked:len($picked), ir_keys:keys($ir), blocks:len(get($ir,"blocks",[])), block_types:unique($types), path:get($doc,"path",null), md_head:get($doc,"markdown","")[0:500]}
""")
    v = val(r) or {}
    return bool(r.get('success') and v.get('path')), ok_or_err(r, 2500)


def t17():
    """[선별] arXiv 최신 프리프린트 5편(T02 와 같은 조회 — reuse) 중 인지과학·뇌과학과 연결되는 것 판정(judge 5행, 유료 1회)."""
    r = ex(reuse={'run_id': '4f57bee3742a4053a8c7841714c50ab3'}, code="""
$a = [sense:paper]{query:"LLM reasoning limitations", source:"arxiv", sort_by:"recent", year_from:2026, limit:5}
$j = $a.items >> [table:select]{columns:["title","summary"]} >> [table:judge]{instruction:"이 논문이 인지과학·뇌과학(인간 인지, 신경 메커니즘)과 직접 연결되는가", as:"뇌"}
return {n:len($j.items), cols:keys($j.items[0]), rows:($j.items >> [table:select]{columns:["title","뇌_result_value","뇌_result_status"]})}
""")
    v = val(r) or {}
    return bool(r.get('success') and v.get('n') == 5), ok_or_err(r, 2500)


def t18():
    """[슬라이드] 최신 강의(88장)에서 슬라이드 스펙을 읽어 '환각'(0장 — 디스크 grep 대조)·'뇌'·'기억'이 나오는 슬라이드 번호·제목과 스펙의 한국어 문구, 발표자 노트가 빈 슬라이드 수."""
    r = ex("""
$l = [self:lecture]{op:"load", lecture_id:"aie-daehan-jalmotdoen-eoneodeul"}
$dir = $l.lecture_dir
$hits = $l.items >> [table:each]{mode:"flat_map"} {
  $spec = [self:read]{path:f"${$dir}/${$it.spec_file}"}
  $t = $spec.text
  [if: contains($t, "환각") or contains($t, "뇌") or contains($t, "기억")] { return [{순번:$it.순번, 제목:$it.제목, spec_top:keys($spec.data), 문구:get($spec.data,"korean_texts",null)}] } [else] { return [] }
}
$empty_notes = $l.items >> [table:filter]{where:($s)=> len(strip(text(get($s,"speaker_note","")))) == 0}
return {slides:len($l.items), hits:$hits, empty_notes:len($empty_notes)}
""")
    v = val(r) or {}
    return bool(r.get('success') and v.get('slides') == 88), ok_or_err(r, 2500)


def t19():
    """[학위논문] 국내 '뇌과학 인공지능' 학위논문 — 건수를 말하지 않고 그냥 찾기(기본값) vs 5건 명시, 최근 연도순."""
    a = ex("""
$d = [sense:paper]{source:"nanet", query:"뇌과학 인공지능", type:"학위논문"}
return {n:len($d.items), total:get($d,"total",null), truncated:get($d,"truncated",null), tr:get($d,"truncations",null)}
""")
    b = ex("""
$d = [sense:paper]{source:"nanet", query:"뇌과학 인공지능", type:"학위논문", limit:5}
$rows = $d.items >> [table:compute]{set:($x)=> {연도: split($x.meta, " · ")[-1]}} >> [table:sort]{by:"연도", descending:true}
return {n:len($d.items), total:get($d,"total",null), tr:get($d,"truncations",null), rows:($rows >> [table:select]{columns:["title","연도"]})}
""")
    da = a.get('diagnostic') or {}
    return bool(b.get('success')), f"default: success={a.get('success')} code={da.get('code')} src_complete={a.get('source_complete')} {ok_or_err(a,500)} | limit5: {ok_or_err(b, 1200)}"


def t20():
    """[노트북 점검] 강의 준비 전 'AI 동향' 노트북 — 원본이 바뀌었거나 사라진 소스, 색인 안 끝난 소스 수와 지도(카드 한 줄) 앞 3개(LLM 0)."""
    r = ex("""
$s = [self:notebook]{op:"sources", name:"AI 동향"}
$stale = $s.items >> [table:filter]{where:($x)=> has($x,"stale") and $x.stale != null and $x.stale != false}
$notready = $s.items >> [table:filter]{where:($x)=> not contains($x.meta, "ready")}
# items 에는 stale·status 칸이 없다(meta 문자열 '⚠️modified'·'ready' 에만) → 위 filter 는 구조적으로 항상 0. 원 행(.sources)으로 대조:
$raw_stale = $s.sources >> [table:filter]{where:($x)=> has($x,"stale")}
$meta_stale = $s.items >> [table:filter]{where:($x)=> contains($x.meta, "⚠")}
$m = [self:notebook]{op:"map", name:"AI 동향"}
return {sources:len($s.items), src_cols:keys($s.items[0]), raw_src_keys:keys($s.sources[0]), stale:len($stale), raw_stale:len($raw_stale), raw_stale_rows:($raw_stale >> [table:select]{columns:["id","title","stale","path"]}), meta_stale:len($meta_stale), notready:len($notready), map_keys:keys($m), map_head:(get($m,"items",[]) >> [table:take]{n:3})}
""")
    v = val(r) or {}
    return bool(r.get('success') and v.get('sources')), ok_or_err(r, 2500)


def t21():
    """[연도 범위] 사용자가 '2024년부터 2025년까지' 라고 말한 걸 그대로 문자열로 — openalex 연도 범위 + 결과 연도 확인(몸이 맞추는지)."""
    r = ex("""
$p = [sense:paper]{query:"free energy principle active inference", source:"openalex", year_from:"2024", year_to:"2025", limit:5}
$years = $p.items >> [table:each]{ return split($it.meta, " · ")[-2] }
return {n:len($p.items), metas:($p.items >> [table:select]{columns:["meta"]})}
""")
    v = val(r) or {}
    return bool(r.get('success') and v.get('n')), ok_or_err(r, 1800)


def t22():
    """[저자] 뇌과학자 김대식(KAIST)의 국내 저서를 정보나루에서 저자로 찾아 제목 중복 빼고 최근 출간순."""
    r = ex("""
$b = [sense:book]{author:"김대식", rows:30}
$mine = $b.items >> [table:filter]{where:($x)=> contains($x.authors, "김대식")} >> [table:dedup]{by:"bookname"}
$rows = $mine.items >> [table:sort]{by:"publication_year", descending:true} >> [table:take]{n:8}
return {n:len($b.items), total:get($b,"total",null), truncated:get($b,"truncated",null), mine:len($mine.items), rows:($rows >> [table:select]{columns:["bookname","publisher","publication_year","loan_count"]})}
""")
    v = val(r) or {}
    return bool(r.get('success') and v.get('mine')), ok_or_err(r, 2200)


T23_CODE = """
$c = [self:lecture]{op:"create", title:"IT77_스크래치 에이전트 보안", audience:"훈련 스크래치"}
$id = $c.lecture_id
$out = null
[try] {
  $s = [self:notebook]{op:"search", name:"AI 동향", query:"에이전트 권한 승인", top_k:3}
  $lines = $s.items >> [table:each]{ return f"- ${$it.title} (${split($it.meta, ' · ')[0]}): ${$it.summary[0:120]}" }
  $memo = "# 에이전트 보안 메모\\n" + join("\\n", $lines)
  $add = [self:material]{op:"add", lecture_id:$id, text:$memo, filename:"IT77_memo.md"}
  $m = [self:material]{op:"list", lecture_id:$id}
  $out = {id:$id, create_keys:keys($c), add_keys:keys($add), added:get($add,"material",null), listed:($m.items >> [table:select]{columns:["filename","type","size_bytes","exists"]})}
} [finally] {
  $del = [self:lecture]{op:"delete", lecture_id:$id, confirm:true}
}
return {out:$out, deleted:$del}
"""


def t23():
    """[자료함] 다음 강의(스크래치 IT77_ 강의)를 만들고, 노트북 발췌 3개를 메모 한 장으로 재료함에 넣고, 재료 목록 확인 — 끝나면 finally 로 강의 삭제."""
    ck = ex(T23_CODE, check=True)
    if ck.get('status') == 'invalid':
        return False, f"check invalid {err(ck)}"
    r = ex(T23_CODE)
    v = val(r) or {}
    return bool(r.get('success') and (v.get('out') or {}).get('listed')), ok_or_err(r, 2500)


def t24():
    """[check] 코퍼스 강의·연구 용례를 판본 2 check 로 — 4013 '$it.path'·4005 '$it.title'(문자 그대로 치환), 4759 옛 filter {field,op,value}, arXiv 다운로드(쓰기)·arxiv 에 year_from."""
    a = ex("""
$m = [self:material]{op:"list", lecture_id:"ai-sahoeyi-jayulsingyeonggye"}
return $m.items >> [table:take]{n:2} >> [table:each] { [self:read]{path:'$it.path'} }
""", check=True)
    b = ex("""
return [self:notebook]{op:"list"} >> [table:each] { [self:notebook]{op:'sources', name:'$it.title'} }
""", check=True)
    c = ex("""
return [sense:researcher]{op:"find", name:"홍길동"} >> [table:filter]{where: {field: "org", op: "contains", value: "서울대"}}
""", check=True)
    d = ex("""
return [sense:paper]{op:"download", source:"arxiv", arxiv_id:"1706.03762"}
""", check=True)
    e = ex("""
return [sense:paper]{source:"arxiv", query:"predictive coding", year_from:2025, sort_by:"recent", open_access:true}
""", check=True)
    def st(x):
        w = [i.get('code') for i in (x.get('warnings') or x.get('precheck_warnings') or [])]
        return f"{x.get('status')} issues={codes(x)} warn={w} effects={x.get('effects') or (x.get('plan') or {}).get('effects')}"
    return (a.get('status') != 'invalid'), f"4013={st(a)} | 4005={st(b)} | 4759={st(c)} {err(c)[:200]} | download={st(d)} | arxiv_year={st(e)}"


def t00():
    """(탐색) 원천 모양 확인 — 과제 아님."""
    return True, 'noop'


TASKS = []


def _collect():
    global TASKS
    TASKS = [globals()[n] for n in sorted(globals()) if n.startswith('t') and n[1:].isdigit() and n != 't00']


def run():
    _collect()
    only = [a for a in sys.argv[2:] if a.startswith('t')]
    path = HERE / 'before.json'
    store = json.loads(path.read_text()) if path.exists() else {'rows': [], 'log': []}
    rows = {r['task']: r for r in store['rows']}
    for task in TASKS:
        if only and task.__name__ not in only:
            continue
        LOG.clear()
        started = datetime.now().isoformat(timespec='seconds')
        try:
            ok, detail = task()
        except Exception as exc:  # 탐침의 실패도 기록한다
            ok, detail = False, f'probe error: {type(exc).__name__}: {exc}'
        rows[task.__name__] = {'task': task.__name__, 'intent': task.__doc__, 'ok': bool(ok), 'detail': detail,
                               'at': started}
        store['log'] = [e for e in store['log'] if e.get('task') != task.__name__]
        store['log'].extend({'task': task.__name__, **e} for e in LOG)
        print(('PASS' if ok else 'FAIL'), task.__name__, detail[:1500], flush=True)
    store['rows'] = [rows[k] for k in sorted(rows)]
    store['passed'] = sum(r['ok'] for r in store['rows'])
    store['total'] = len(store['rows'])
    path.write_text(json.dumps(store, ensure_ascii=False, indent=1))
    print(f"{store['passed']}/{store['total']}")


def desc():
    r = post('ibl/execute', dict(code='', edition=2, describe=sys.argv[2:], project_id='컨텐츠', origin='training', **AGENT))
    print(json.dumps(r, ensure_ascii=False, indent=1, default=str)[:20000])


def raw():
    extra = {}
    if '--check' in sys.argv:
        extra['check'] = True
    r = ex(sys.argv[2], **extra)
    print(json.dumps({k: v for k, v in r.items() if k not in ('evidence', 'source_map', 'recordings', 'value_wire')},
                     ensure_ascii=False, indent=1, default=str)[:12000])


def snapshot():
    notes = post('notifications?limit=100', method='GET')
    return {
        'at': datetime.now().isoformat(timespec='seconds'),
        'notifications': [{k: n.get(k) for k in ('id', 'type', 'title', 'created_at')} for n in notes['notifications']],
        'action_health_max_id': q(PULSE, 'select max(id) from action_health')[0][0],
        'notify_log_max_id': q(PULSE, 'select max(id) from notify_log')[0][0],
        'since_streams': q(SINCE, 'select count(distinct stream), count(*) from since_seen')[0],
    }


def baseline():
    (HERE / 'baseline.json').write_text(json.dumps({'baseline': snapshot()}, ensure_ascii=False, indent=1))
    print('baseline saved')


def after():
    base = json.loads((HERE / 'baseline.json').read_text())
    b = base['baseline']
    a = snapshot()
    diff = {
        'notifications_added': [n for n in a['notifications'] if n['id'] not in {x['id'] for x in b['notifications']}],
        'action_health_by_source': q(PULSE, 'select source, coalesce(channel,""), count(*) from action_health where id > ? group by 1, 2',
                                     (b['action_health_max_id'],)),
        'action_health_training_by_action': q(PULSE, "select node||':'||action, count(*), sum(success) from action_health where id > ? and source='training' group by 1 order by 2 desc",
                                              (b['action_health_max_id'],)),
        'notify_log_new': q(PULSE, 'select id, title, emitter, source from notify_log where id > ?', (b['notify_log_max_id'],)),
        'since_streams': a['since_streams'],
    }
    base['after'] = {'snapshot': {k: a[k] for k in ('at', 'action_health_max_id', 'notify_log_max_id')}, 'diff': diff}
    (HERE / 'baseline.json').write_text(json.dumps(base, ensure_ascii=False, indent=1))
    print(json.dumps(diff, ensure_ascii=False, indent=1, default=str)[:6000])


if __name__ == '__main__':
    {'baseline': baseline, 'run': run, 'after': after, 'raw': raw, 'desc': desc}[sys.argv[1]]()
