"""
memory_consolidation.py - 심층메모리 정리 패스 (consolidate-memory 이식)

쓰기 시점 중복제거(_distill_deep_memory의 SAME/UPDATE/REPLACE/NEW)의
배치/오프라인 짝이다. 쓰기 경로는 "방금 들어온 한 조각"만 보지만,
정리 패스는 축적된 전체를 보고 모순·근접중복·노화·카테고리 드리프트를 청소한다.

설계:
- 심층메모리는 에이전트별로 격리된 memory_*.db 다 → 격리 유지한 채 DB별 팬아웃
- 기계 단계(가지치기/클러스터 탐지/카테고리 정규화)는 memory_db가 담당 (무LLM, 싸다)
- 의미 병합 판단만 경량 AI에 위임 (클러스터당 1회) — 근접중복 후보 중
  '진짜 동일한 사실'만 골라 병합, 다른 사실은 분리 유지
- self-check(6h)에 합류하되 내부 카덴스 게이트(24h/DB)로 자기 페이싱

self-check가 정적 IBL 검증을 합류시킨 패턴과 동일하게 면역 순찰의 일부다.
"""
import json
import sys
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from runtime_utils import get_base_path, parse_first_json

CADENCE_HOURS = 24      # DB당 정리 최소 간격
MIN_ROWS_FOR_CLUSTER = 8   # 이 미만이면 클러스터 병합 스킵 (가지치기만)
MAX_CLUSTERS_PER_DB = 12   # 한 사이클에서 LLM 병합할 클러스터 상한 (비용 가드)
BOCHUNG_COMPACT_MIN = 4    # [보충] 줄이 이 이상인 단일 레코드 = 압축 후보(자석 비대)
COMPACT_LEN_FLOOR = 800    # 또는 content 길이가 이 이상이면 후보
MAX_COMPACT_PER_DB = 8     # 한 사이클 단일레코드 압축 LLM 호출 상한 (비용 가드)

# ── 반증 패스 (stage 4) — 낡음=사용 빈도가 아니라 '사실이 더는 참이 아님'.
#    경로 주장은 실존 검사로 직접 반증(AI 0·결정론). LRU 가 못 잡는 '자주 회상되는
#    틀린 사실'을 잡는다. URL 은 네트워크 소음(일시 장애·봇차단)이 있어 보고만.
FALSIFY_CADENCE_HOURS = 168     # 주 1회/DB
MAX_FALSIFY_ACTIONS_PER_DB = 10 # 한 사이클 자동 수리(삭제·절단) 상한
FALSIFY_HEAD_DELETE_LEN = 220   # 머리 조각이 이보다 길면 삭제 대신 보고(혼합 기억 보호)
MAX_URL_CHECKS_PER_DB = 20      # 한 사이클 URL 응답 검사 상한
URL_TIMEOUT_SEC = 6

# ── 원거리 모순 스캔 (stage 5) — 쓰기 시점 판정·클러스터 병합은 임베딩이 가까운
#    쌍만 본다. 표현이 달라 멀어진 모순은 전체를 한눈에 보는 배치 판정 1회로 잡는다.
#    모순이 실제로 문제가 되는 카테고리(의사결정·사용자선호)만 — 작업기록은 시점이
#    다르면 둘 다 참이라 제외.
CONTRA_CADENCE_HOURS = 168      # 주 1회/DB
CONTRA_CATEGORIES = ("의사결정", "사용자선호")
MAX_CONTRA_ROWS = 60            # 배치 목록 상한 (초과 시 최신 우선)
MAX_CONTRA_DELETES_PER_DB = 6   # 한 사이클 자동 삭제 상한


def _memory_db():
    """memory 패키지의 memory_db 모듈 로드 (sys.path 주입)."""
    mem_pkg = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..",
        "data", "packages", "installed", "tools", "memory"
    )
    if mem_pkg not in sys.path:
        sys.path.insert(0, mem_pkg)
    import memory_db
    return memory_db


def _discover_memory_dbs() -> List[str]:
    """존재하는 모든 심층메모리 DB 경로 수집 (시스템 AI + 프로젝트 에이전트)."""
    base = get_base_path()
    dbs: List[str] = []
    sysdb = base / "data" / "system_ai_state" / "memory_system_ai.db"
    if sysdb.exists():
        dbs.append(str(sysdb))
    projects = base / "projects"
    if projects.exists():
        for p in sorted(projects.glob("*/memory_*.db")):
            dbs.append(str(p))
    return dbs


def _is_dirty(db_path: str, force: bool = False) -> bool:
    """정리 대상인지 — force거나 마지막 정리 후 CADENCE_HOURS 경과."""
    if force:
        return True
    mdb = _memory_db()
    last = mdb.get_meta(db_path, "last_consolidated")
    if not last:
        return True
    try:
        last_dt = datetime.fromisoformat(last)
    except Exception:
        return True
    return datetime.now() - last_dt >= timedelta(hours=CADENCE_HOURS)


def _merge_cluster_llm(items: List[Dict], today: str) -> List[Dict]:
    """근접중복 클러스터를 경량 AI로 판정 → 병합 지시 리스트 반환.

    items: [{id, category, keywords, content, created_at}, ...]
    반환: [{"keep_id", "drop_ids", "content", "keywords", "category"}, ...]
          병합할 그룹만 포함. 서로 다른 사실은 언급하지 않음(= 그대로 둠).
    """
    from consciousness_agent import oneshot_ai_call

    listing = "\n".join(
        f'- id={it["id"]} (생성 {str(it.get("created_at",""))[:10]}, '
        f'분류 {it.get("category") or "미분류"}): {(it.get("content") or "")[:300]}'
        for it in items
    )
    prompt = f"""아래는 의미가 비슷해 보여 묶인 기억 후보들이다. 오늘 날짜는 {today}.

{listing}

이들 중 '정확히 같은 사실'을 가리키는 것끼리만 병합하라.
- 비슷하지만 다른 사실(예: 사용자 본인 주소 vs 자녀 주소, 다른 시점의 다른 작업)은 병합하지 말 것.
- 병합 시 가장 최신·구체적인 정보로 모순을 정정하고, 낡은/틀린 내용은 버려라(append 금지, 정규 병합본을 새로 써라).
- "다음 주", "어제" 같은 상대 시간은 오늘({today}) 기준 절대 날짜로 바꿔라.
- 키워드는 합집합으로 중복 제거. 분류는 사용자선호|사용자정보|작업기록|의사결정|중요날짜|기타 중 하나.

JSON으로만 응답:
{{"merges": [{{"keep_id": <남길 id>, "drop_ids": [<삭제할 id들>], "content": "<정규 병합본>", "keywords": "k1,k2", "category": "<분류>"}}]}}
병합할 그룹이 없으면 {{"merges": []}}."""

    resp = oneshot_ai_call(
        prompt=prompt,
        system_prompt="기억 병합 판정기. 같은 사실만 병합. JSON으로만 응답.",
        role="background",
    )
    if not resp:
        return []
    cleaned = resp.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        return []
    merges = data.get("merges", []) if isinstance(data, dict) else []
    valid_ids = {it["id"] for it in items}
    out = []
    for m in merges:
        keep = m.get("keep_id")
        drops = [d for d in m.get("drop_ids", []) if d in valid_ids and d != keep]
        content = (m.get("content") or "").strip()
        if keep not in valid_ids or not drops or not content:
            continue
        out.append({
            "keep_id": keep,
            "drop_ids": drops,
            "content": content,
            "keywords": (m.get("keywords") or "").strip(),
            "category": (m.get("category") or "").strip(),
        })
    return out


def _compact_record_llm(item: Dict, today: str) -> Optional[Dict]:
    """[보충]으로 비대해진 *단일* 레코드를 경량 AI로 간결 재작성.

    근접중복 '병합'(별개 레코드 2+)과 달리, 이건 *한 레코드*가 증류 UPDATE 로 [보충] 누적돼
    부푼 것을 푼다 — 자주 회상돼 used_at 최신이라 LRU 가지치기에도 안 걸리는 '회상 자석'을
    줄이는 사각지대 패스. 구별되는 사실은 보존하고 중복·옛 정보만 버린다.
    반환 {content, keywords} 또는 None(실패/압축 효과 없음 → 스킵)."""
    from consciousness_agent import oneshot_ai_call

    content = item.get("content", "") or ""
    prompt = f"""아래는 같은 주제로 여러 번 [보충]되며 비대해진 하나의 기억이다. 오늘 날짜는 {today}.
이를 *간결한 하나의 기억*으로 다시 써라.
- 서로 구별되는 사실은 모두 보존한다(정보 손실 금지).
- 중복·이미 더 최신 정보로 대체된 내용만 버린다.
- "[보충]" 표식은 없애고 자연스러운 문장으로 합쳐라.
- "어제"·"다음 주" 같은 상대 시간은 오늘({today}) 기준 절대 날짜로 바꿔라.
- keywords 는 핵심만 추려 새로 만든다(나열 과다 금지).

기억:
{content}

JSON으로만 응답: {{"content": "<압축본>", "keywords": "k1,k2,..."}}"""
    resp = oneshot_ai_call(
        prompt=prompt,
        system_prompt="기억 압축기. 구별되는 사실은 보존하고 중복만 제거. JSON으로만 응답.",
        role="background",
    )
    if not resp:
        return None
    cleaned = resp.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    new_content = (data.get("content") or "").strip()
    new_keywords = (data.get("keywords") or "").strip()
    # 안전: 비었거나 압축 효과 없으면(원본 이상) 스킵 — 정보손실/무의미 갱신 방지
    if not new_content or len(new_content) >= len(content):
        return None
    return {"content": new_content, "keywords": new_keywords}


def _cadence_due(mdb, db_path: str, key: str, hours: int, force: bool) -> bool:
    """스테이지별 카덴스 게이트 (_is_dirty 의 일반형 — meta 키·간격 매개변수화)."""
    if force:
        return True
    last = mdb.get_meta(db_path, key)
    if not last:
        return True
    try:
        return datetime.now() - datetime.fromisoformat(last) >= timedelta(hours=hours)
    except Exception:
        return True


def _is_fs_claim(tok: str) -> bool:
    """파일시스템 주장인가 — 첫 마디가 실존 루트 디렉토리인 절대경로만.

    API 라우트(/api/quotes)·게시판 경로(/b/…)·분수 표기(…16곳/12파일)·루트상대
    표기(/outputs/…)는 슬래시로 시작해도 파일시스템 주장이 아니다(시운전 오탐 실측).
    """
    parts = tok.strip("/").split("/")
    return bool(parts and parts[0] and os.path.isdir("/" + parts[0]))


def _path_alive(tok: str) -> bool:
    """경로 주장 생존 검사.

    관용 둘(시운전 오탐 실측): ①한글 조사가 붙은 토큰("…png이며")은 조사를 떼고도
    본다. ②공백 든 경로가 절단된 토큰("…/집필/하네스란"←"하네스란 무엇인가?")은
    디렉토리가 살아있고 basename 이 그 안 항목의 접두이면 생존으로 친다.
    """
    import re
    for cand in {tok, re.sub(r"[가-힣]+$", "", tok)}:
        if not cand:
            continue
        if os.path.exists(cand):
            return True
        base_dir, base_name = os.path.split(cand.rstrip("/"))
        if base_name and os.path.isdir(base_dir):
            try:
                if any(entry.startswith(base_name)
                       for entry in os.listdir(base_dir)):
                    return True
            except Exception:
                pass
    return False


def _url_dead(url: str) -> bool:
    """정의된 죽음만 True — 404/410/NXDOMAIN. 403·429·타임아웃 등 소음은 불확정(생존 취급)."""
    import socket
    import urllib.request
    import urllib.error
    ua = {"User-Agent": "Mozilla/5.0"}
    try:
        urllib.request.urlopen(
            urllib.request.Request(url, method="HEAD", headers=ua),
            timeout=URL_TIMEOUT_SEC)
        return False
    except urllib.error.HTTPError as e:
        if e.code in (404, 410):
            return True
        if e.code == 405:  # HEAD 미지원 → GET 재시도
            try:
                urllib.request.urlopen(
                    urllib.request.Request(url, headers=ua), timeout=URL_TIMEOUT_SEC)
                return False
            except urllib.error.HTTPError as e2:
                return e2.code in (404, 410)
            except Exception:
                return False
        return False
    except urllib.error.URLError as e:
        return isinstance(getattr(e, "reason", None), socket.gaierror)  # NXDOMAIN
    except Exception:
        return False


def _falsify_pass(mdb, db_path: str, force: bool = False) -> Dict:
    """stage 4 — 반증 패스 (AI 0, 주 1회/DB).

    낡음의 본질은 '안 쓰임'(LRU)이 아니라 '더는 참이 아님'이다. 세계의 명사=반증
    가능한 데이터(헌법)이므로 실제로 반증한다: 경로 주장은 실존 검사(결정론 → 자동
    수리 — 죽은 경로가 머리 조각이고 짧으면(경로 지배 한줄) 행 삭제, 보충에 있으면
    그 보충만 절단, 머리가 길면(혼합 기억) 보고만). URL 주장은 소음이 있어 정의된
    죽음(404/410/NXDOMAIN)만 보고한다 — 자동 삭제 없음."""
    if not _cadence_due(mdb, db_path, "last_falsified", FALSIFY_CADENCE_HOURS, force):
        return {}
    stats = {"falsify_deleted": 0, "falsify_trimmed": 0,
             "falsify_reported": 0, "url_dead": 0}
    url_budget = MAX_URL_CHECKS_PER_DB
    name = os.path.basename(db_path)
    for rec in mdb.list_all(db_path):
        content = rec.get("content") or ""
        # 1) 경로 주장 반증 (결정론 → 자동 수리, 상한 가드)
        dead = [p for p in mdb.extract_path_claims(content)
                if not p.startswith("/Volumes")
                and _is_fs_claim(p) and not _path_alive(p)]
        acted = stats["falsify_deleted"] + stats["falsify_trimmed"]
        if dead and acted < MAX_FALSIFY_ACTIONS_PER_DB:
            segs = content.split("\n[보충] ")
            head_dead = any(p in segs[0] for p in dead)
            if head_dead and len(content) <= FALSIFY_HEAD_DELETE_LEN:
                mdb.delete_at(db_path, rec["id"])
                stats["falsify_deleted"] += 1
                print(f"[반증] {name}#{rec['id']} 삭제 — 죽은 경로 {dead[0]} "
                      f"| \"{content[:60]}\"")
                continue
            if head_dead:
                stats["falsify_reported"] += 1
                print(f"[반증] {name}#{rec['id']} 보고만 — 혼합 기억 머리에 "
                      f"죽은 경로 {dead[0]}")
            keep = [segs[0]] + [s for s in segs[1:]
                                if not any(p in s for p in dead)]
            if len(keep) < len(segs):
                mdb.apply_merge(db_path, rec["id"], "\n[보충] ".join(keep),
                                rec.get("keywords") or "",
                                rec.get("category") or "", [])
                stats["falsify_trimmed"] += 1
                print(f"[반증] {name}#{rec['id']} 보충절단 — 죽은 경로 {dead[0]}")
        # 2) URL 주장 검사 (소음 → 보고만, 상한 가드)
        if url_budget > 0:
            for url in mdb.extract_url_claims(content)[:3]:
                if url_budget <= 0:
                    break
                url_budget -= 1
                if _url_dead(url):
                    stats["url_dead"] += 1
                    print(f"[반증] {name}#{rec['id']} URL 죽음(보고만): {url}")
    mdb.set_meta(db_path, "last_falsified", datetime.now().isoformat())
    return stats


def _contradiction_scan(mdb, db_path: str, today: str, force: bool = False) -> Dict:
    """stage 5 — 원거리 모순 스캔 (주 1회/DB, 배치 LLM 1회).

    쓰기 시점 판정과 클러스터 병합은 임베딩이 가까운 쌍만 본다 — 표현이 달라
    멀어진 모순은 영영 안 만난다. 그래서 모순이 실제로 문제가 되는 카테고리
    (의사결정·사용자선호)를 통째로 한 판에 놓고 양립 불가 쌍만 골라 낡은 쪽을
    지운다. 무판정이 오판보다 낫다는 규칙 + 사이클당 삭제 상한이 가드."""
    if not _cadence_due(mdb, db_path, "last_contra_scan", CONTRA_CADENCE_HOURS, force):
        return {}
    rows = [r for r in mdb.list_all(db_path)
            if (r.get("category") or "").strip() in CONTRA_CATEGORIES]
    if len(rows) < 2:
        mdb.set_meta(db_path, "last_contra_scan", datetime.now().isoformat())
        return {}
    rows = sorted(rows, key=lambda r: str(r.get("created_at") or ""))[-MAX_CONTRA_ROWS:]

    from consciousness_agent import oneshot_ai_call
    listing = "\n".join(
        f'- id={r["id"]} ({str(r.get("created_at", ""))[:10]}, {r.get("category")}): '
        f'{(r.get("content") or "")[:240]}'
        for r in rows)
    prompt = f"""아래는 한 에이전트의 의사결정·사용자선호 기억 전체다. 오늘은 {today}.
서로 **모순**인 쌍만 골라라. 모순 = 양립 불가(하나가 참이면 다른 하나는 거짓).
- 다른 시점의 다른 작업·다른 대상·단순 유사·보완 관계는 모순이 아니다 → 내지 마라.
- 모순이면 어느 쪽이 낡았는지 판정하라: 보통 더 최신이거나 더 구체적인 쪽이 우세.
- 확실하지 않으면 내지 마라(무판정이 오판보다 낫다).

{listing}

JSON으로만 응답:
{{"contradictions": [{{"obsolete_id": <낡은 쪽 id>, "kept_id": <우세한 쪽 id>, "reason": "<한 문장>"}}]}}
모순이 없으면 {{"contradictions": []}}."""
    resp = oneshot_ai_call(
        prompt=prompt,
        system_prompt="기억 모순 판정기. 양립 불가 쌍만. JSON으로만 응답.",
        role="background",
    )
    stats = {"contra_rows": len(rows), "contra_deleted": 0}
    if not resp:
        # LLM 무응답(키 부재·장애) = 스캔 미수행 — 카덴스를 소진하지 않아야
        # 다음 사이클이 재시도한다(무응답이 일주일 침묵으로 굳는 것 방지).
        print(f"[모순] {os.path.basename(db_path)} 판정 불가(LLM 무응답) — "
              f"카덴스 미소진, 다음 사이클 재시도")
        return stats
    data = parse_first_json(resp)
    items = data.get("contradictions", []) if isinstance(data, dict) else []
    valid = {r["id"] for r in rows}
    by_id = {r["id"]: r for r in rows}
    for c in items[:MAX_CONTRA_DELETES_PER_DB]:
        if not isinstance(c, dict):
            continue
        o, k = c.get("obsolete_id"), c.get("kept_id")
        if o not in valid or k not in valid or o == k:
            continue
        mdb.delete_at(db_path, o)
        stats["contra_deleted"] += 1
        print(f"[모순] {os.path.basename(db_path)}#{o} 삭제 (vs #{k}): "
              f"{(c.get('reason') or '')[:80]} "
              f"| \"{(by_id[o].get('content') or '')[:60]}\"")
    mdb.set_meta(db_path, "last_contra_scan", datetime.now().isoformat())
    return stats


def consolidate_one(db_path: str, force: bool = False) -> Dict:
    """단일 DB 정리 — 카테고리 정규화 → 근접중복 병합 → [보충] 비대 압축 → LRU 가지치기
    → (주 1회) 반증 패스 → (주 1회) 원거리 모순 스캔."""
    mdb = _memory_db()
    if not _is_dirty(db_path, force):
        return {"db": db_path, "skipped": "cadence"}

    total = mdb.count_at(db_path)
    today = datetime.now().date().isoformat()
    stats = {"db": os.path.basename(db_path), "rows": total,
             "normalized": 0, "clusters": 0, "merged": 0,
             "dropped": 0, "compacted": 0, "pruned": 0}

    # 1) 카테고리 정규화 (빈칸 제외, 쓰레기 값만)
    stats["normalized"] = mdb.normalize_all_categories(db_path)

    # 2) 근접중복 클러스터 병합 (LLM 판정) — 충분한 행이 있을 때만
    if total >= MIN_ROWS_FOR_CLUSTER:
        clusters = mdb.find_duplicate_clusters(db_path)
        stats["clusters"] = len(clusters)
        for cluster in clusters[:MAX_CLUSTERS_PER_DB]:
            items = [mdb.get_by_id(db_path, cid) for cid in cluster]
            items = [it for it in items if it]
            if len(items) < 2:
                continue
            try:
                merges = _merge_cluster_llm(items, today)
            except Exception as e:
                print(f"[정리] 병합 판정 실패 (스킵): {e}")
                continue
            for mg in merges:
                mdb.apply_merge(
                    db_path, mg["keep_id"], mg["content"],
                    mg["keywords"], mg["category"], mg["drop_ids"],
                )
                stats["merged"] += 1
                stats["dropped"] += len(mg["drop_ids"])

    # 2.5) [보충] 비대 단일 레코드 압축 (클러스터 병합 사각지대 = '회상 자석')
    for rec in mdb.list_all(db_path):
        if stats["compacted"] >= MAX_COMPACT_PER_DB:
            break
        content = rec.get("content") or ""
        if content.count("[보충]") < BOCHUNG_COMPACT_MIN and len(content) < COMPACT_LEN_FLOOR:
            continue
        try:
            new = _compact_record_llm(rec, today)
        except Exception as e:
            print(f"[정리] 압축 판정 실패 (스킵): {e}")
            continue
        if not new:
            continue
        # apply_merge 를 drop_ids=[] 로 = 단일 레코드 content/keywords 갱신 + 재임베딩.
        # used_at 미변경이라 자석은 유지하되 *크기만* 줄인다(키워드 표면·내용 압축).
        mdb.apply_merge(db_path, rec["id"], new["content"],
                        new["keywords"] or (rec.get("keywords") or ""),
                        rec.get("category") or "", [])
        stats["compacted"] += 1

    # 3) 상한 초과 시 LRU 가지치기 (보호 카테고리 제외)
    stats["pruned"] = mdb.prune_lru(db_path)

    # 4) 반증 패스 — 반증 가능한 주장 재검증 (AI 0, 주 1회/DB 자체 카덴스)
    try:
        stats.update(_falsify_pass(mdb, db_path, force=force))
    except Exception as e:
        print(f"[반증] 패스 실패 (스킵) {os.path.basename(db_path)}: {e}")

    # 5) 원거리 모순 스캔 — 의사결정·선호 배치 판정 (주 1회/DB 자체 카덴스)
    try:
        stats.update(_contradiction_scan(mdb, db_path, today, force=force))
    except Exception as e:
        print(f"[모순] 스캔 실패 (스킵) {os.path.basename(db_path)}: {e}")

    mdb.set_meta(db_path, "last_consolidated", datetime.now().isoformat())
    return stats


def run_memory_consolidation(force: bool = False) -> Dict:
    """전체 심층메모리 DB 팬아웃 정리 (self-check 카덴스에 합류).

    내부적으로 DB별 24h 카덴스 게이트가 있어, 6h마다 호출돼도 각 DB는
    하루 한 번만 실제로 정리된다. dirty하지 않은 DB는 즉시 스킵(싸다)."""
    dbs = _discover_memory_dbs()
    results = []
    touched = 0
    for db in dbs:
        try:
            r = consolidate_one(db, force=force)
            results.append(r)
            if "skipped" not in r:
                touched += 1
                if r.get("merged") or r.get("pruned") or r.get("normalized"):
                    print(f"[정리] {r['db']}: 정규화 {r['normalized']} / "
                          f"병합 {r['merged']}(삭제 {r['dropped']}) / 가지치기 {r['pruned']}")
                if (r.get("falsify_deleted") or r.get("falsify_trimmed")
                        or r.get("falsify_reported") or r.get("url_dead")
                        or r.get("contra_deleted")):
                    print(f"[정리] {r['db']}: 반증 삭제 {r.get('falsify_deleted', 0)}"
                          f"·절단 {r.get('falsify_trimmed', 0)}"
                          f"·보고 {r.get('falsify_reported', 0)}"
                          f"·URL죽음 {r.get('url_dead', 0)} / "
                          f"모순 삭제 {r.get('contra_deleted', 0)}")
        except Exception as e:
            print(f"[정리] DB 처리 실패 (스킵) {os.path.basename(db)}: {e}")
    return {"databases": len(dbs), "consolidated": touched, "details": results}


if __name__ == "__main__":
    import sys as _s
    force = "--force" in _s.argv
    out = run_memory_consolidation(force=force)
    print(json.dumps(out, ensure_ascii=False, indent=2))
