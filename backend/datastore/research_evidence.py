"""연구 질문이 인용하는 불변 자료와 읽기 영수증 검증. 의미적 지지는 판정하지 않는다."""
import hashlib
import json


def evidence_key(ref):
    value = [ref['version_ref'], ref['extraction_revision'], ref['locator'], ref['quote']]
    return hashlib.sha256(json.dumps(value, ensure_ascii=False).encode()).hexdigest()


def validate_reference(store, db, tid, value, *, run=None, retained=None):
    """새 AI 인용은 현재 실행의 읽기 증거가 필요하다. 기존 연결은 원래 영수증을 유지한다."""
    if not isinstance(value, dict) or set(value) - {
        'version_ref', 'extraction_revision', 'locator', 'quote', 'evidence_id', 'observed_in',
    }:
        raise ValueError('근거는 version_ref, extraction_revision, locator, quote로 지정하세요')
    ref = {key: value.get(key) for key in ('version_ref', 'extraction_revision', 'locator', 'quote')}
    if (any(not isinstance(ref[k], str) or not ref[k] for k in ('version_ref', 'locator', 'quote'))
            or len(ref['quote']) > 4000 or len(ref['locator']) > 1000
            or type(ref['extraction_revision']) is not int or ref['extraction_revision'] < 1):
        raise ValueError('근거 판본·위치·비어 있지 않은 원문 인용이 필요합니다')
    row = db.execute('SELECT e.blob FROM research_extractions e WHERE e.version_id=? AND e.revision=? '
                     'AND EXISTS (SELECT 1 FROM research_captures c WHERE c.version_id=e.version_id AND c.thread_id=?)',
                     (ref['version_ref'], ref['extraction_revision'], tid)).fetchone()
    if not row:
        raise ValueError('이 대화에 보존된 자료의 추출 판본만 인용할 수 있습니다')
    paragraphs = json.loads(store.blob(row['blob']))
    if not any(loc == ref['locator'] and ref['quote'] in text for loc, text in paragraphs):
        raise ValueError(
            f"인용이 지정한 원문 위치와 일치하지 않습니다: version_ref={ref['version_ref']}, "
            f"extraction_revision={ref['extraction_revision']}, locator={ref['locator']}. "
            "self:notebook read로 이 추출 판본을 읽고 반환된 위치·원문으로 수정하세요. "
            "문단 번호를 추측하여 재시도하지 마세요.")
    key = evidence_key(ref)
    previous = (retained or {}).get(key)
    observed = list(previous.get('observed_in', [])) if previous else []
    if run and not previous:
        rows = db.execute('SELECT quote FROM research_access WHERE run_id=? AND version_id=? AND revision=? AND locator=?',
                          (run, ref['version_ref'], ref['extraction_revision'], ref['locator'])).fetchall()
        if not any(ref['quote'] in row['quote'] for row in rows):
            raise ValueError(
                f"새 근거는 현재 실행에서 해당 자료 구간을 읽은 뒤 연결하세요: "
                f"version_ref={ref['version_ref']}, extraction_revision={ref['extraction_revision']}, "
                f"locator={ref['locator']}. 원문 일치는 확인됐지만 이 위치의 읽기 증명이 없습니다. "
                "self:notebook read로 해당 구간을 읽은 뒤 같은 근거를 저장하세요.")
        observed.append({'run_id': run})
    return {**ref, 'evidence_id': key, 'observed_in': observed}
