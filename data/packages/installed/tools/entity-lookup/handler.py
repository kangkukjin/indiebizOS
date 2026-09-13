"""Wikidata 개체 식별. 학술 검색과 독립적으로 선택·공유하는 묶음."""
import os
import re
import json
import requests

_CONTACT = os.environ.get("INDIEBIZ_CONTACT_EMAIL", "").strip()

# ─── Wikidata 개체 해소(entity resolution) — 지식 그래프 ────────────────
# www.wikidata.org/w/api.php — wbsearchentities(검색)·wbgetentities(상세).
# 무API키(공개), 순수 requests(맥·폰 공통). Wikimedia는 서술적 User-Agent 요구.
_WD_API = "https://www.wikidata.org/w/api.php"
_WD_HEADERS = {"User-Agent": "IndieBizOS/1.0 (entity resolution" + (f"; contact {_CONTACT}" if _CONTACT else "") + ")"}


def _wd_get(params: dict) -> dict:
    """Wikidata Action API GET (format=json 고정)."""
    r = requests.get(_WD_API, params={**params, "format": "json"},
                     headers=_WD_HEADERS, timeout=20)
    r.raise_for_status()
    return r.json()


def _wd_search(query: str, lang: str, limit: int) -> list:
    """wbsearchentities — lang 라벨 없으면 en 폴백."""
    data = _wd_get({"action": "wbsearchentities", "search": query,
                    "language": lang, "uselang": lang, "type": "item", "limit": limit})
    hits = data.get("search") or []
    if not hits and lang != "en":
        data = _wd_get({"action": "wbsearchentities", "search": query,
                        "language": "en", "uselang": "en", "type": "item", "limit": limit})
        hits = data.get("search") or []
    return hits


def _wd_labels(ids: list, lang: str) -> dict:
    """P-id/Q-id 라벨 배치 해소 (wbgetentities props=labels, 50개씩)."""
    out, ids = {}, [i for i in dict.fromkeys(ids) if i]
    for i in range(0, len(ids), 50):
        chunk = ids[i:i + 50]
        try:
            d = _wd_get({"action": "wbgetentities", "ids": "|".join(chunk),
                         "props": "labels", "languages": f"{lang}|en"})
        except Exception:
            continue
        for k, v in (d.get("entities") or {}).items():
            labs = v.get("labels") or {}
            out[k] = (labs.get(lang) or labs.get("en") or {}).get("value") or k
    return out


def _wd_snak_value(snak: dict, label_map: dict):
    """mainsnak → 사람이 읽는 값 문자열 (개체는 라벨 해소, 시간·수량 포맷)."""
    if snak.get("snaktype") != "value":
        return None
    dv = snak.get("datavalue") or {}
    t, v = dv.get("type"), dv.get("value")
    if t == "wikibase-entityid":
        return label_map.get(v.get("id"), v.get("id"))
    if t == "string":
        return v
    if t == "monolingualtext":
        return (v or {}).get("text")
    if t == "time":
        tv = (v or {}).get("time") or ""    # 예: +1946-08-04T00:00:00Z
        m = re.match(r"[+-](\d+)-(\d\d)-(\d\d)", tv)
        if m:
            y, mo, d = m.groups()
            if mo == "00":
                return y
            if d == "00":
                return f"{y}-{mo}"
            return f"{y}-{mo}-{d}"
        return tv
    if t == "quantity":
        return ((v or {}).get("amount") or "").lstrip("+")
    if t == "globecoordinate":
        return f"{(v or {}).get('latitude')}, {(v or {}).get('longitude')}"
    return None


def _wikidata_resolve(tool_input: dict) -> str:
    """개체 후보 검색 — 동명이인/동음이의를 QID·설명으로 분리."""
    query = tool_input.get("query") or tool_input.get("q") or tool_input.get("name")
    if not query:
        return {"success": False, "error": "검색어(query)가 필요합니다. 예: [sense:entity]{query: \"이순신\"}", "items": []}
    lang = (tool_input.get("lang") or "ko").strip()
    limit = int(tool_input.get("limit") or tool_input.get("max_results") or 7)
    try:
        hits = _wd_search(query, lang, limit)
    except Exception as e:
        return {"success": False, "error": f"Wikidata 검색 오류: {e}", "items": []}
    if not hits:
        return {"items": [], "message": f"'{query}'에 해당하는 Wikidata 개체를 찾지 못했습니다."}
    lines = [f"Wikidata 개체 후보 '{query}' — {len(hits)}건 (QID로 동명이인/동음이의 해소):"]
    records = []
    for h in hits:
        qid = h.get("id")
        label = h.get("label") or query
        desc = h.get("description") or ""
        lines.append(f"- {label} ({qid})" + (f" — {desc}" if desc else ""))
        records.append({  # 레코드 통화 — 개체 후보를 QID·설명으로 식별
            "title": label,
            "meta": " · ".join(x for x in [qid, desc] if x),
            "summary": desc,
            "url": f"https://www.wikidata.org/wiki/{qid}",
            "qid": qid,
        })
    lines.append("→ QID를 [sense:entity]{op:\"detail\", id:\"<QID>\"}에 넣어 구조화된 사실 조회.")
    return {"success": True, "message": "\n".join(lines), "items": records, "count": len(records)}


def _wikidata_detail(tool_input: dict) -> str:
    """QID(또는 query) → 구조화된 속성·사실 (P-속성명: 값, records 통화)."""
    lang = (tool_input.get("lang") or "ko").strip()
    qid = tool_input.get("id") or tool_input.get("qid")
    if not qid:
        query = tool_input.get("query") or tool_input.get("q") or tool_input.get("name")
        if not query:
            return {"success": False, "error": "id(QID) 또는 query가 필요합니다. 예: [sense:entity]{op:\"detail\", id:\"Q42\"}", "items": []}
        try:
            hits = _wd_search(query, lang, 1)
        except Exception as e:
            return {"success": False, "error": f"Wikidata 조회 오류: {e}", "items": []}
        if not hits:
            return {"items": [], "message": f"'{query}'에 해당하는 Wikidata 개체를 찾지 못했습니다."}
        qid = hits[0].get("id")
    qid = str(qid).strip().upper()
    if not re.match(r"^Q\d+$", qid):
        return {"success": False, "error": f"올바른 QID가 아닙니다: {qid} (예: Q42). 이름으로 찾으려면 op:resolve 사용.", "items": []}
    try:
        data = _wd_get({"action": "wbgetentities", "ids": qid,
                        "props": "labels|descriptions|claims", "languages": f"{lang}|en"})
    except Exception as e:
        return {"success": False, "error": f"Wikidata 상세 오류: {e}", "items": []}
    ent = (data.get("entities") or {}).get(qid)
    if not ent or ent.get("missing") is not None and "missing" in ent:
        return {"items": [], "message": f"{qid} 개체 정보가 없습니다."}

    def _pick(obj):    # labels/descriptions dict → lang→en 폴백
        d = obj or {}
        for L in (lang, "en"):
            if d.get(L):
                return d[L].get("value")
        return None

    label = _pick(ent.get("labels")) or qid
    desc = _pick(ent.get("descriptions")) or ""
    claims = ent.get("claims") or {}
    prop_ids = list(claims.keys())
    truncated = len(prop_ids) > 30
    prop_ids = prop_ids[:30]
    # 라벨 해소 대상(속성 P-id + 값이 개체인 Q-id) 수집 → 한 번에 배치 조회
    value_qids = []
    for pid in prop_ids:
        for st in (claims[pid] or [])[:3]:
            dv = (((st.get("mainsnak") or {}).get("datavalue")) or {}).get("value")
            if isinstance(dv, dict) and dv.get("entity-type") == "item" and dv.get("id"):
                value_qids.append(dv["id"])
    label_map = _wd_labels(prop_ids + value_qids, lang)
    lines = [f"[{label}] ({qid})" + (f" — {desc}" if desc else ""),
             f"https://www.wikidata.org/wiki/{qid}", ""]
    records = []
    for pid in prop_ids:
        plabel = label_map.get(pid, pid)
        vals = []
        for st in (claims[pid] or [])[:3]:
            val = _wd_snak_value(st.get("mainsnak") or {}, label_map)
            if val:
                vals.append(str(val))
        if not vals:
            continue
        valstr = ", ".join(vals)
        lines.append(f"- {plabel}: {valstr}")
        records.append({  # 레코드 통화 — 사실 1건 = 속성:값
            "title": plabel,
            "meta": pid,
            "summary": valstr,
            "url": None,
        })
    if truncated:
        lines.append(f"… (속성 {len(claims)}개 중 30개만 표시)")
    return {"success": True, "message": "\n".join(lines), "items": records,
            "count": len(records), "qid": qid, "label": label}


def _entity_source_err(tool_input: dict):
    """[sense:entity] 공용 source 게이트 — 지원 밖 source 면 에러 dict, 아니면 None."""
    source = (tool_input.get("source") or "wikidata").strip().lower()
    if source not in ("wikidata", "wd", "wikimedia"):
        return {"success": False, "error": f"현재 source는 wikidata만 지원합니다 (요청: {source})."}
    return None


def _entity_resolve(tool_input: dict, context) -> str:
    """[sense:entity]{op:resolve} — 개체 후보 검색 (Wikidata)."""
    return _entity_source_err(tool_input) or _wikidata_resolve(tool_input)


def _entity_detail(tool_input: dict, context) -> str:
    """[sense:entity]{op:detail} — QID → 구조화된 사실 (Wikidata)."""
    return _entity_source_err(tool_input) or _wikidata_detail(tool_input)


_OP_DISPATCHERS = {"entity_op": {"resolve": _entity_resolve, "detail": _entity_detail}}
_OP_DEFAULTS = {"entity_op": "resolve"}


def execute(tool_input: dict, context):
    tool_name = context.tool_name
    if tool_name in _OP_DISPATCHERS:
        op = (tool_input.get("op") or _OP_DEFAULTS.get(tool_name, "")).strip()
        fn = _OP_DISPATCHERS[tool_name].get(op)
        if fn is None:
            return {"success": False, "error": f"알 수 없는 op '{op}'. 사용: {'|'.join(_OP_DISPATCHERS[tool_name])}"}
        return fn(tool_input, context)
    return json.dumps({"success": False, "error": f"Unknown tool: {tool_name}"}, ensure_ascii=False)
