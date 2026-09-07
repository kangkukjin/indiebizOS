"""ibl_name_search.py — 이름 채널 검색: 이름 붙은 용례 부분집합 안에서 원점수로 잰다 (2026-09-06).

ibl_usage_db.IBLUsageDB.search_aliased 의 몸체(1500줄 관문으로 분리). 왜 따로인가는 함수 docstring 에.
"""
from __future__ import annotations

import logging
from typing import Dict, List

from datetime import datetime
from typing import Optional

from ibl_usage_db import UsageExample

logger = logging.getLogger(__name__)

#: 이름 채널의 시맨틱 비중 — 원장 기본 alpha(1.0=시맨틱 100%)를 쓰면 어휘 항이 0 이 된다(09-06 실측: 관문배터리돌리기 0.11).
NAME_ALPHA = 0.7


def search_aliased(db, query: str, top_k: int = 5, alpha: float = None,
               allowed_nodes: set = None) -> List["UsageExample"]:
    """이름 채널 검색(2026-09-06) — 이름 붙은 것들 **안에서** 원점수로 잰다.

    옛 길(search_hybrid 의 aliased_only 사후 필터)의 두 결함: ① 점수가 코퍼스 전체의 최고점으로 정규화돼
    이름의 0.2 는 '낱말 최고점 대비' 였고(문턱 0.45 와 자가 다름) ② 후보가 코퍼스 상위 200 뿐이라 그 밖의
    이름은 아예 안 보였다. 실측(09-06): 딱 맞는 이름이 있는 자연 요청 2/2 에 이름 0건.
    여기서는 이름 행 전부를 후보로 두고, 시맨틱은 L2 정규화 벡터의 내적(= 코사인, 절대 자), 어휘 항은 질의 토큰의
    포함 비율(coverage)로 alpha 로 합친다. 렌트 모드(폰)는 _search_rented 가 이미 원점수(코사인)다."""
    if alpha is None:
        alpha = NAME_ALPHA          # 원장 기본(시맨틱 100%)을 따르지 않는다 — 이름은 낱말(coverage)이 반을 맡는다
    with db._get_connection() as conn:
        rows = conn.execute(
            """SELECT id, intent, ibl_code, nodes, category, difficulty, source, success_count, fail_count,
                      avg_ms, avg_tokens, COALESCE(topic,'') AS topic, COALESCE(alias,'') AS alias,
                      signature, COALESCE(returns,'') AS returns
               FROM ibl_examples WHERE COALESCE(alias,'') != ''""").fetchall()
    metas = {int(r["id"]): dict(r) for r in rows}
    if not metas:
        return []
    ids = list(metas)
    ph = ",".join("?" * len(ids))
    sem: Dict[int, float] = {}
    if db.is_semantic_available() and alpha > 0:
        qe = db._generate_embedding(query)
        vconn = db._get_vec_connection() if qe is not None else None
        if vconn is not None:
            try:
                import numpy as np
                db._ensure_vec_table(vconn)
                q = np.frombuffer(qe, dtype="float32")
                for r in vconn.execute(f"SELECT rowid, embedding FROM ibl_examples_vec WHERE rowid IN ({ph})", ids):
                    v = np.frombuffer(r[1], dtype="float32")
                    if v.shape == q.shape:
                        sem[int(r[0])] = float(max(0.0, float(np.dot(q, v))))
            except Exception as e:
                logger.error(f"[IBL Usage DB] 이름 채널 시맨틱 실패: {e}")
            finally:
                vconn.close()
    # 어휘 항(2026-09-06): 질의 토큰이 이름·뜻·본문에 든 비율(coverage). BM25 는 쓰지 않는다 — 이름은 한국어 복합어
    # 한 토큰("관문배터리돌리기")이라 FTS MATCH 가 부분어("관문")를 못 잡고, 최고점 정규화는 토큰 하나 겹친 무관한
    # 이름도 1.0 으로 만들었다(09-06 실측). 시맨틱(코사인)이 뜻을, coverage 가 낱말을 맡는다.
    lex: Dict[int, float] = {}
    try:
        from korean_utils import tokenize_korean
        tokens = [t for t in tokenize_korean(query) if len(t) >= 2]
    except Exception:
        tokens = [t for t in query.split() if len(t) >= 2]
    if tokens:
        for i in ids:
            m = metas[i]
            text = f"{m.get('alias', '')} {m.get('intent', '')} {m.get('ibl_code', '')}"
            # 어간 근사: "돌려줘"→"돌려", "찾아서"→"찾아" — 마지막 한 글자를 뗀 꼴도 포함으로 본다
            hit = sum(1 for t in tokens if t in text or (len(t) >= 3 and t[:-1] in text))
            if hit:
                lex[i] = hit / len(tokens)
    scored = []
    for i in ids:
        if sem:
            sc = alpha * sem.get(i, 0.0) + (1 - alpha) * lex.get(i, 0.0)
        else:
            sc = lex.get(i, 0.0) * 0.8       # 시맨틱 없이 낱말만 맞은 것은 그 자체로 확답이 아니다
        if sc > 0:
            scored.append((i, sc))
    scored.sort(key=lambda t: t[1], reverse=True)
    results: List[UsageExample] = []
    for i, sc in scored:
        meta = metas[i]
        if allowed_nodes:
            ex_nodes = set(meta["nodes"].split(",")) if meta.get("nodes") else set()
            if ex_nodes and not ex_nodes.intersection(allowed_nodes):
                continue
        total = meta["success_count"] + meta["fail_count"]
        success_rate = (meta["success_count"] / total) if total else -1.0
        results.append(UsageExample(
            id=meta["id"], intent=meta["intent"], ibl_code=meta["ibl_code"], nodes=meta["nodes"],
            category=meta["category"], difficulty=meta["difficulty"], score=round(float(sc), 4),
            source=meta["source"], success_rate=round(success_rate, 2) if total else -1.0,
            avg_ms=round(float(meta["avg_ms"]), 0) if (meta["avg_ms"] or -1) >= 0 else -1.0,
            avg_tokens=round(float(meta["avg_tokens"]), 0) if (meta["avg_tokens"] or -1) >= 0 else -1.0,
            topic=meta["topic"] or "", alias=meta["alias"] or "", signature=meta.get("signature"),
            returns=meta.get("returns") or ""))
        if len(results) >= top_k:
            break
    return results


def update_intent(db, example_id: int, intent: str) -> bool:
    """용례의 intent(이름이면 '함수의 뜻')를 바꾸고 벡터·FTS 색인을 다시 세운다(2026-09-06 뜻 백필)."""
    intent = (intent or "").strip()
    if not example_id or not intent:
        return False
    with db._get_connection() as conn:
        row = conn.execute("SELECT ibl_code, COALESCE(alias,'') AS alias FROM ibl_examples WHERE id = ?",
                           (example_id,)).fetchone()
        if not row:
            return False
        conn.execute("UPDATE ibl_examples SET intent = ?, updated_at = ? WHERE id = ?",
                     (intent, datetime.now().isoformat(), example_id))
        conn.commit()
    alias = row["alias"]
    db._index_single(example_id, (f"{alias} {intent}" if alias else intent), row["ibl_code"])
    return True


def alias_of_code(db, ibl_code: str) -> str:
    """ibl_code 정확 일치 용례의 이름(alias) — 없으면 "". 회상 top-1 이 *부를 수 있는* 함수인지 묻는 자리
    (2026-09-05 이름 호출 학습 루프: 증류 게이트·귀속이 '베꼈나/불렀나'를 가른다)."""
    if not ibl_code:
        return ""
    with db._get_connection() as conn:
        row = conn.execute(
            "SELECT COALESCE(alias,'') FROM ibl_examples WHERE ibl_code = ? AND COALESCE(alias,'') != '' "
            "ORDER BY updated_at DESC LIMIT 1", (ibl_code,)).fetchone()
    return (row[0] or "").strip() if row else ""

def aliased_examples(db, limit: int = 500) -> List[tuple]:
    """이름 있는 용례 (alias, ibl_code) — 실행 관문의 모양 대조(fn_recognizer)가 읽는다(2026-09-06)."""
    with db._get_connection() as conn:
        rows = conn.execute("SELECT alias, ibl_code FROM ibl_examples WHERE COALESCE(alias,'') != '' "
                            "ORDER BY updated_at DESC LIMIT ?", (limit,)).fetchall()
    return [(r[0], r[1]) for r in rows]

def phrase_aliases(db, limit: int = 12) -> List[str]:
    with db._get_connection() as conn:
        rows = conn.execute("SELECT alias FROM ibl_examples WHERE COALESCE(alias,'') != '' "
                            "ORDER BY (success_count + fail_count) DESC, created_at DESC LIMIT ?", (limit,)).fetchall()
    return [r[0] for r in rows]


def find_phrase_by_alias(db, name: str) -> Optional[Dict]:
    """이름으로 관용구 하나 — `[fn:이름]` 해소의 셋째 길(프로그램 정의 → 저장 워크플로 → 관용구). 없으면 None."""
    if not name:
        return None
    with db._get_connection() as conn:
        # 2026-09-05: 카테고리 무관 — 이름이 붙은 용례(관용구·다문장 프로그램)는 무엇이든 부를 수 있다(자동 작명과 한 벌)
        row = conn.execute(
            "SELECT id, intent, ibl_code, COALESCE(topic,'') AS topic, COALESCE(alias,'') AS alias, category, "
            "COALESCE(returns,'') AS returns, signature, "
            # 실행 이력·우회 횟수도 준다(2026-09-07) — 증류의 덮어쓰기 판정이 '돈 적 있는가'를 여기서 묻는다
            "COALESCE(success_count,0) AS success_count, COALESCE(fail_count,0) AS fail_count, "
            "COALESCE(bypass_count,0) AS bypass_count "
            "FROM ibl_examples WHERE alias = ? ORDER BY updated_at DESC LIMIT 1",
            (name.strip(),)).fetchone()
    return dict(row) if row else None


def replace_example(db, example_id: int, *, intent: str, ibl_code: str, nodes: str = "",
                    topic: str = "", alias: str = "", returns: str = "") -> int:
    """돈 적 없는 이름의 **본문을 덮는다** — 새 이름(이름2)을 만들지 않는다(2026-09-07 사용자 판정).

    왜: 증류에는 갱신 경로가 없었다. `unique_fn_name` 은 같은 이름·다른 골격을 만나면 `이름2` 를 새로 만들고
    `add_example` 은 삽입뿐이라, 가이드가 개정되면 낡은 정의가 이름을 붙든 채 원장에 남았다. 실행자는 매 호
    expand 로 열어 "낡았다" 고 판단하고 손으로 다시 짓는다 — 우회할수록 실행 0 이 유지되고, 실행 0 이라
    아무도 갱신하지 않는다(09-07 유튜브팁 보고서 실측: `유튜브팁보고서작성` 09-04 생성, ✓0/✗0, 본문은
    검색 2갈래·심사 없음인데 가이드 §2-0 은 09-05·09-06 개정으로 5갈래·심사 한 칸). **한 번도 돈 적 없는
    정의는 지킬 가치가 없다** — 부른 적도 성공한 적도 없는 글자일 뿐이다. 실행 이력이 있으면 이 길로 오지 않는다.

    성공/실패 카운트는 건드리지 않는다(0 인 채로 남는다 — 새 본문도 아직 안 돌았다). 우회 횟수는 0 으로
    되돌린다: 거부당한 것은 옛 본문이고, 새 본문은 아직 거부당한 적이 없다.
    """
    if not example_id or not (ibl_code or "").strip():
        return 0
    from ibl_usage_db import _norm_topic, _signature_of, _syntax_reason, _tree_refresh
    why = _syntax_reason(ibl_code)
    if why:
        logger.warning(f"[IBL Usage DB] 파싱 불가 본문 덮어쓰기 거부(입구 구문-게이트): {why} / {ibl_code[:100]}")
        return 0
    now = datetime.now().isoformat()
    with db._get_connection() as conn:
        old = conn.execute("SELECT COALESCE(topic,'') AS topic FROM ibl_examples WHERE id = ?",
                           (example_id,)).fetchone()
        if not old:
            return 0
        conn.execute(
            "UPDATE ibl_examples SET intent = ?, ibl_code = ?, nodes = ?, topic = ?, alias = ?, returns = ?, "
            "signature = ?, bypass_count = 0, updated_at = ? WHERE id = ?",
            (intent, ibl_code, nodes, _norm_topic(topic), (alias or "").strip(), (returns or "").strip(),
             _signature_of(ibl_code), now, example_id))
        conn.commit()
    db._index_single(example_id, (f"{alias} {intent}" if alias else intent), ibl_code)
    _tree_refresh(topic, old["topic"])
    return int(example_id)


def record_bypass(db, alias: str) -> int:
    """이 이름의 프로그램을 **부르지 않고 손으로 친** 실행 하나를 원장에 적는다 — 반환: 누계(못 찾으면 0).

    2026-09-07: 우회는 지금까지 아무 흔적도 남기지 않았다(✓0/✗0). 그래서 낡은 정의는 '실행 0' 으로만 보였고,
    그건 '아직 안 써 본 새 정의' 와 글자가 같다 — 표면이 둘을 구별하지 못하니 정리도 증류도 집을 수 없었다.
    실패로 세지 않는다: 정의가 실패한 게 아니라 거부당한 것이다(`no-counter-watch` 의 카운터가 아니라 사건 기록 —
    이 수는 표면이 '거부 N회' 로 말하고, 증류의 덮어쓰기가 지운다)."""
    alias = (alias or "").strip()
    if not alias:
        return 0
    with db._get_connection() as conn:
        cur = conn.execute(
            "UPDATE ibl_examples SET bypass_count = COALESCE(bypass_count,0) + 1 WHERE alias = ?", (alias,))
        conn.commit()
        if not cur.rowcount:
            return 0
        row = conn.execute("SELECT COALESCE(bypass_count,0) FROM ibl_examples WHERE alias = ?", (alias,)).fetchone()
    return int(row[0]) if row else 0
