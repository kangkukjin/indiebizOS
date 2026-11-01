"""다섯 근거 기록과 판본 결속을 강제하는 격리 후보. 의미의 참은 보증하지 않는다."""
import copy
import hashlib
import json
import re

PRINCIPLES = ('purpose', 'progress', 'method', 'execution', 'bounds')


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':')).encode()).hexdigest()


def parse_json(raw):
    if not isinstance(raw, str):
        raise ValueError('응답은 JSON 문자열이어야 한다')
    return json.loads(re.sub(r'^```(?:json)?\s*|\s*```$', '', raw.strip()))


def field_value(candidate, path):
    if not isinstance(path, str) or not path:
        raise ValueError('근거 필드가 없다')
    value = candidate
    for part in path.strip('/').split('/'):
        if isinstance(value, list):
            if not part.isdigit():
                raise ValueError('목록 필드의 인덱스가 없다')
            value = value[int(part)]
        elif isinstance(value, dict):
            value = value[part]
        else:
            raise ValueError('근거 필드를 찾을 수 없다')
    if not isinstance(value, str):
        raise ValueError('근거는 문자열 필드에 결속되어야 한다')
    return value


def validate_checks(result, candidate, user_texts):
    if not isinstance(result, dict) or set(result) != {'checks'}:
        raise ValueError('checks 객체가 필요하다')
    rows = result['checks']
    if not isinstance(rows, list) or len(rows) != len(PRINCIPLES):
        raise ValueError('다섯 항목이 모두 필요하다')
    if any(not isinstance(row, dict) for row in rows):
        raise ValueError('각 점검은 객체여야 한다')
    if tuple(row.get('principle') for row in rows) != PRINCIPLES:
        raise ValueError('항목 누락·중복·순서 오류')
    for row in rows:
        if row.get('status') not in {'pass', 'fail', 'uncertain'}:
            raise ValueError('지원하지 않는 판정')
        user_quote = row.get('user_quote')
        if not isinstance(user_quote, str) or not user_quote.strip() or not any(
                user_quote in text for text in user_texts if text):
            raise ValueError('사용자 원문 인용이 일치하지 않는다')
        evidence = row.get('evidence')
        if not isinstance(evidence, list) or not 1 <= len(evidence) <= 3:
            raise ValueError('계획 근거1~3개가 필요하다')
        for item in evidence:
            if not isinstance(item, dict):
                raise ValueError('근거는 객체여야 한다')
            quote = item.get('quote')
            if not isinstance(quote, str) or not quote.strip():
                raise ValueError('계획 인용이 비어 있다')
            if quote not in field_value(candidate, item.get('field')):
                raise ValueError('계획 인용이 해당 필드와 일치하지 않는다')
        if not isinstance(row.get('reason'), str) or not row['reason'].strip():
            raise ValueError('짧은 판정 근거가 필요하다')
        if not isinstance(row.get('repair'), str):
            raise ValueError('수정 사항 필드가 필요하다')
        if row['status'] != 'pass' and not row['repair'].strip():
            raise ValueError('미통과 항목의 최소 수정이 필요하다')
    return copy.deepcopy(rows)


def releasable(candidate, audit):
    return (isinstance(audit, dict) and audit.get('candidate_sha256') == digest(candidate)
            and tuple(row.get('principle') for row in audit.get('checks', [])) == PRINCIPLES
            and all(row.get('status') == 'pass' for row in audit['checks']))


def run(candidate, user_texts, review, repair, validate_candidate, record):
    """최대 최초점검→한 번 수정→전항목 재점검. 미통과/형식오류에 실행용 전달 없음."""
    current = copy.deepcopy(candidate)
    audits = []
    revisions = []
    for revision in range(2):
        try:
            validate_candidate(current)
            raw = review(copy.deepcopy(current), revision)
            checks = validate_checks(parse_json(raw), current, user_texts)
            audit = {'revision': revision, 'candidate_sha256': digest(current), 'checks': checks}
            audits.append(audit)
            record('audit', audit)
        except Exception as exc:
            result = {'status': 'invalid', 'release_allowed': False, 'candidate': current,
                      'audits': audits, 'revisions': revisions, 'error': str(exc)}
            record('outcome', result)
            return result
        if releasable(current, audit):
            result = {'status': 'passed', 'release_allowed': True, 'candidate': current,
                      'audits': audits, 'revisions': revisions}
            record('outcome', result)
            return result
        if revision == 1:
            break
        try:
            updated = repair(copy.deepcopy(current), copy.deepcopy(audit))
            validate_candidate(updated)
            change = {'from_sha256': digest(current), 'to_sha256': digest(updated)}
            revisions.append(change)
            record('revision', change)
            current = copy.deepcopy(updated)
        except Exception as exc:
            result = {'status': 'repair_failed', 'release_allowed': False, 'candidate': current,
                      'audits': audits, 'revisions': revisions, 'error': str(exc)}
            record('outcome', result)
            return result
    result = {'status': 'not_passed', 'release_allowed': False, 'candidate': current,
              'audits': audits, 'revisions': revisions}
    record('outcome', result)
    return result
