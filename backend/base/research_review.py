"""제출 판본과 인용 위치의 공통 계약. 원문 읽기와 의미 승인은 별도로 둔다."""
import json
import re
from pathlib import Path

MARKER = re.compile(r'\[자료:([^:\]]+):([^\]]+)\]')
PATH = re.compile(r"(?<![\w:])((?:/|outputs/)[^\n`\"'<>]*?\.(?:md|txt|html|json|csv|tsv))(?=[\s)`\"'<>]|$)")


def submission_paths(text, root):
    paths = set()
    root = Path(root).resolve()
    for value in PATH.findall(text or ''):
        path = Path(value)
        path = (root / path).resolve() if not path.is_absolute() else path.resolve()
        if path.is_relative_to(root):
            paths.add(str(path))
    return paths


def review_text(response, artifacts):
    return '\n\n'.join([response, *(f"<research_artifact path={a['path']!r} sha256={a['hash']!r}>\n"
                                    + a['text'] + '\n</research_artifact>' for a in artifacts)]) if artifacts else response


def claims(text, *, path='response', digest=None):
    """같은 표지가 여러 주장에 쓰인 경우도 별도 위치로 보존한다. 중요도는 추정하지 않는다."""
    return [{'citation': m[0], 'path': path, 'hash': digest, 'offset': m.start(),
             'context_start': max(0, m.start() - 350), 'context_end': min(len(text), m.end() + 100),
             'claim_context': text[max(0, m.start() - 350):m.end() + 100]}
            for m in MARKER.finditer(text)]


def allocate(lengths, budget=16000, cap=2400):
    """등장 순서 대신 항목별 동등 몫을 먼저 확보하고 짧은 항목의 잔액을 재분배한다."""
    result = {key: 0 for key in lengths}
    pending = sorted(lengths)
    while pending and budget:
        share = max(1, budget // len(pending))
        for key in pending:
            n = min(share, budget, min(cap, lengths[key]) - result[key])
            result[key] += n
            budget -= n
        pending = [key for key in pending if result[key] < min(cap, lengths[key])]
    return result


def passage(full, limit, context):
    """동일 글자 예산 안에서 주장과 겹치는 원문 주변을 선택한다. 발췌 범위는 명시한다."""
    if limit <= 0:
        return '', 0
    if len(full) <= limit:
        return full, 0
    from recall_relevance import terms
    wanted = terms(context)
    # 문단별 어휘 일치만 사용한다. 의미적 지지 또는 중요도의 판정으로 취급하지 않는다.
    starts = [0] + [m.end() for m in re.finditer(r'\n', full)]
    # 짧은 후보 구간을 고른 뒤 주변을 붙인다. 긴 창의 끝에 있던 핵심 문장을
    # 앞쪽 여백을 붙이는 과정에서 잃지 않도록 후보 자체가 창 안에 남게 한다.
    width = min(limit, 600)  # clamp-ok: 내부 검색 창; 반환 발췌의 누락은 호출자가 truncated로 신고
    starts = sorted(set(starts) | set(range(0, len(full), max(1, width // 2))))
    scored = [(len(wanted & terms(full[pos:pos + width])), -pos) for pos in starts]
    start = -max(scored)[1] if limit and wanted else 0
    margin = min(150, max(0, limit - width))  # clamp-ok: 검색 창 앞 여백; 반환 범위와 누락은 별도 신고
    start = max(0, min(start - margin, len(full) - limit))
    return full[start:start + limit], start


def passages(full, limit, contexts, anchors=()):
    """읽은 한 원문 안의 명시 인용·주장별 창을 같은 예산으로 배분한다.

    반환 좌표는 합성 문자열이 아닌 입력 원문의 Unicode 좌표다. 선택은 의미
    판정이 아니다. 여러 주장의 같은 창은 공유하고 멀리 떨어진 창은 보존한다.
    """
    if limit <= 0 or not full:
        return []
    if len(full) <= limit:
        return [(0, len(full))]
    targets = []
    for quote in dict.fromkeys(anchors):
        start = full.find(quote) if quote else -1
        if start >= 0:
            targets.append((start, start + len(quote)))
    for context in dict.fromkeys(contexts):
        shown, start = passage(full, min(limit, 600), context)  # clamp-ok: 내부 탐색 창; 실제 발췌 누락은 호출자가 truncated로 신고
        if not any(left <= start < right or start <= left < start + len(shown)
                   for left, right in targets):
            targets.append((start, start + len(shown)))
    targets = targets or [(0, min(limit, len(full)))]
    return range_windows(len(full), limit, targets)


def range_windows(total, limit, targets):
    """Allocate exact ordered ranges around previously selected source anchors."""
    quotas = allocate({str(i): total for i in range(len(targets))}, budget=limit, cap=limit)
    ranges = []
    for i, (left, right) in enumerate(targets):
        size = quotas[str(i)]
        if size:
            start = max(0, min(left - max(0, size - (right - left)) // 2, total - size))
            ranges.append((start, start + size))
    merged = []
    for left, right in sorted(ranges):
        if merged and left <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(right, merged[-1][1]))
        else:
            merged.append((left, right))
    return merged


def citation_uses(feedback, occurrences, sources):
    """Validate AI-selected uses against supplied source identities, not marker semantics."""
    if not occurrences:
        return [], []
    match = re.search(r'(?m)^CITATION_USES:\s*(\[.*\])\s*$', feedback or '')
    try:
        rows = json.loads(match[1]) if match else None
        if not isinstance(rows, list) or len(rows) != len(occurrences):
            raise ValueError('모든 인용 후보의 CITATION_USES가 필요합니다')
        if {r['index'] for r in rows} != set(range(len(occurrences))):
            raise ValueError('인용 후보 위치가 누락되거나 중복됐습니다')
        available = {r['citation'] for r in sources}
        invalid = []
        for row in rows:
            if type(row['index']) is not int or row.get('use') not in {'source', 'example', 'unverified'}:
                raise ValueError('인용 사용 형식이 유효하지 않습니다')
            if row['use'] == 'source' and occurrences[row['index']]['citation'] not in available:
                invalid.append(occurrences[row['index']])
        return rows, invalid
    except (TypeError, KeyError, ValueError) as exc:
        raise ValueError('인용 사용 응답 형식 오류: ' + str(exc)) from exc


def saved_citations(review, uses):
    """Project confirmed source uses from the same prepared inputs for storage."""
    selected = {review['claims'][r['index']]['citation'] for r in uses if r['use'] == 'source'}
    return [{'version_id': row['version_ref'], 'locator': row['locator'],
             'extraction_revision': receipt['extraction_revision'], 'quote': receipt['quote']}
            for row in review.get('valid', []) if row['citation'] in selected
            for receipt in row.get('receipts', [])]
