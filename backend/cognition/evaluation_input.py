"""One evaluation budget, immutable evidence, explicit selection and bounded recovery."""
import hashlib
import json
import re
import time

from model_request_budget import InputTooLarge, check, serialized
from research_review import allocate


def dumps(value):
    return json.dumps(value, ensure_ascii=False, default=str)


def record(text, *, subject, role='support', source_ref=None, revision=None,
           criterion_ids=(), start=0, total=None):
    return {'text': text, 'subject': subject, 'role': role, 'source_ref': source_ref,
            'revision': revision or hashlib.sha256(text.encode()).hexdigest(),
            'criterion_ids': list(criterion_ids), 'start': start,
            'total': len(text) if total is None else total}


class EvaluationPrompt(str):
    """String-compatible until the actual oneshot provider has been selected."""
    def __new__(cls, required, sections, context=''):
        obj = super().__new__(cls, required + '\n\n' + '\n\n'.join(
            f"## {r['subject']}\n{r['text']}" for r in sections))
        obj.required, obj.sections, obj.context = required, sections, context
        obj.metrics = None
        return obj

    def prepare_request(self, provider, images=None):
        started = time.monotonic()
        # Distinct source revisions/roles are not merged just because text/path matches.
        rows, seen = [], set()
        for row in self.sections:
            key = (row['source_ref'], row['revision'], row['role'], row['start'], row['text'])
            if key in seen:
                previous = next(r for r in rows if (r['source_ref'], r['revision'], r['role'], r['start'], r['text']) == key)
                previous['criterion_ids'] = sorted(set(previous['criterion_ids']) | set(row['criterion_ids']))
                if row['subject'] not in previous['subjects']:
                    previous['subjects'].append(row['subject'])
                continue
            seen.add(key)
            rows.append({**row, 'subjects': [row['subject']]})
        lengths = {str(i): len(r['text']) for i, r in enumerate(rows)}

        anchors = {}
        from recall_relevance import terms
        wanted = terms(self.context)

        def render(budget):
            # Requested passages, then explicit submissions, then other evidence.
            # A collected source must not displace the artifact being evaluated.
            recovered = {str(i): len(r['text']) for i, r in enumerate(rows) if r['role'] == 'recovered'}
            sizes = allocate(recovered, budget, cap=budget) if recovered else {}
            preferred = {str(i): len(r['text']) for i, r in enumerate(rows) if r['role'] == 'submission'}
            sizes.update(allocate(preferred, budget - sum(sizes.values()), cap=budget) if preferred else {})
            left = budget - sum(sizes.values())
            rest = allocate({k: n - sizes.get(k, 0) for k, n in lengths.items()}, left, cap=budget)
            sizes = {k: sizes.get(k, 0) + rest.get(k, 0) for k in lengths}
            shown, manifest = [], []
            for i, row in enumerate(rows):
                size = sizes[str(i)]
                if not size or size >= len(row['text']):
                    text, offset = row['text'][:size], 0
                else:
                    key = row['revision']
                    if key not in anchors:
                        # Score fixed source windows once, not a Korean tokenizer
                        # per overlapping newline on every budget-search attempt.
                        width = min(600, size)
                        positions = range(0, len(row['text']), max(1, width // 2))
                        best = max(positions, key=lambda pos: sum(
                            term in row['text'][pos:pos + width] for term in wanted)) if wanted else 0
                        anchors[key] = best
                    offset = max(0, min(anchors[key] - max(0, (size - 600) // 2), len(row['text']) - size))
                    text = row['text'][offset:offset + size]
                begin = row['start'] + offset
                full = begin == 0 and len(text) == row['total']
                meta = {k: row[k] for k in ('subject', 'subjects', 'role', 'source_ref', 'revision', 'criterion_ids')}
                meta.update(range={'unit': 'unicode_chars', 'start': begin, 'end': begin + len(text),
                                   'total': row['total']}, completeness='complete' if full else 'partial' if text else 'omitted')
                manifest.append({**meta, 'original_chars': len(row['text']), 'shown_chars': len(text)})
                shown.append(dumps(meta) + '\n' + text)
            prompt = self.required + ('\n\n## 선택된 증거 (manifest는 열람 증명이 아님)\n' + '\n\n'.join(shown) if rows else '')
            return prompt, manifest

        # Required contracts and even omission metadata must fit, or do not call.
        minimal, _ = render(0)
        check(provider, serialized(provider, minimal, images), images=images, reserve=8192)
        low, high = 0, sum(lengths.values())
        prompt, manifest = render(high)
        try:
            metrics = check(provider, serialized(provider, prompt, images), images=images, reserve=8192)
        except InputTooLarge:
            # All checks include wrappers, JSON escaping and omission records.
            while low < high:
                mid = (low + high + 1) // 2
                candidate, selection = render(mid)
                try:
                    check(provider, serialized(provider, candidate, images), images=images, reserve=8192)
                    low = mid
                except InputTooLarge:
                    high = mid - 1
            prompt, manifest = render(low)
            metrics = check(provider, serialized(provider, prompt, images), images=images, reserve=8192)
        self.metrics = {**metrics, 'sections': manifest, 'selected': sum(r['shown_chars'] > 0 for r in manifest),
                        'omitted': sum(r['completeness'] != 'complete' for r in manifest),
                        'prepare_s': round(time.monotonic() - started, 6)}
        from episode_logger import record_trajectory_event
        record_trajectory_event('evaluation.input_budget', self.metrics)
        incomplete = [r for r in manifest if r['role'] == 'recovered' and r['shown_chars'] < r['original_chars']]
        if incomplete:
            raise InputTooLarge({'reason': '회수 요청 구간을 평가 입력에 전부 전달할 수 없습니다',
                                 'references': [r['source_ref'] for r in incomplete]})
        return prompt


def context_sections(context):
    """Keep authority/status/criteria intact; evidence is selectable, not authority."""
    try:
        value = json.loads(context)
    except (TypeError, ValueError):
        return context, []
    if not isinstance(value, dict):
        return context, []
    optional = {'evidence_index', 'assertion_evidence', 'research_citations', 'research_claims',
                'recovered_evidence', 'workspace_evidence'}
    required, sections = {}, []
    for key, data in value.items():
        if key not in optional:
            required[key] = data
            continue
        for i, item in enumerate(data if isinstance(data, list) else [data]):
            sections.append(record(dumps(item), subject=f'{key}[{i}]',
                                   role='recovered' if key == 'recovered_evidence' else 'support'))
    return dumps(required), sections


def evidence_references(packet):
    """One projection for presentation and validation; never overwrite conflicting versions."""
    refs = {}

    def add(key, revision, total, subject, criteria=()):
        if not isinstance(key, str) or not key:
            return
        item = {'evidence_id': key, 'revision': revision, 'total': total,
                'unit': 'unicode_chars', 'subjects': [subject], 'criterion_ids': list(criteria),
                'availability': 'not_read', 'ambiguous': False}
        prior = refs.get(key)
        if prior:
            prior['ambiguous'] |= (prior['revision'] != revision or
                                   prior['total'] is not None and total is not None and prior['total'] != total)
            if prior['total'] is None:
                prior['total'] = total
            prior['subjects'] = list(dict.fromkeys([*prior['subjects'], subject]))
            prior['criterion_ids'] = sorted(set(prior['criterion_ids']) | set(criteria))
        else:
            refs[key] = item

    for row in [*packet.get('attachments', []), *packet.get('selection_sources', [])]:
        add(row.get('source_ref'), row.get('revision'), row.get('total'),
            row.get('subject', 'selected_section'), row.get('criterion_ids', []))
    for index, call in enumerate(packet.get('context', {}).get('evidence_index', [])):
        for field in ('input', 'result'):
            ref = call.get(field) or {}
            add(ref.get('id'), ref.get('id'), ref.get('chars'), f'evidence_index[{index}].{field}')
    for row in packet.get('context', {}).get('workspace_evidence', []):
        ref = row.get('evidence_ref') or {}
        add(ref.get('id'), ref.get('id'), ref.get('chars'),
            'workspace_check:' + str(row.get('id', '')), row.get('criterion_ids', []))
    for row in refs.values():
        row['recoverable'] = bool(not row['ambiguous'] and re.fullmatch(r'[0-9a-f]{64}', row['evidence_id'])
                                  and row['revision'] == row['evidence_id'])
    return list(refs.values())


def evidence_requests(feedback, packet):
    """Classify protocol errors separately from missing evidence; normalize only immutable IDs."""
    result = {'status': 'absent', 'requests': [], 'errors': [], 'normalizations': []}
    matches = re.findall(r'(?m)^EVIDENCE_REQUESTS:[ \t]*(.*)$', feedback)
    if not matches:
        return result
    result['status'] = 'invalid'
    try:
        if len(matches) != 1:
            raise ValueError('요청 선언은 하나여야 합니다')
        rows = json.loads(matches[0])
        if not isinstance(rows, list) or not 1 <= len(rows) <= 16:
            raise ValueError('요청은 1~16개 배열이어야 합니다')
    except ValueError as exc:
        result['errors'].append({'code': 'format', 'reason': str(exc)})
        return result
    allowed = {r['evidence_id']: r for r in evidence_references(packet)}
    criteria = {r['id'] for r in packet['context']['criteria_contract']['criteria']}
    for index, row in enumerate(rows):
        error = None
        ref = allowed.get(row.get('evidence_id')) if isinstance(row, dict) and isinstance(row.get('evidence_id'), str) else None
        if not isinstance(row, dict):
            error = 'format'
        elif not ref or not ref['recoverable']:
            error = 'reference_conflict' if ref and ref['ambiguous'] else 'reference'
        elif not isinstance(row.get('criterion_id'), str) or row['criterion_id'] not in criteria:
            error = 'criterion'
        elif 'revision' in row and row['revision'] != ref['revision']:
            error = 'revision'
        elif (type(row.get('start')) is not int or type(row.get('end')) is not int
              or not 0 <= row['start'] < row['end']
              or ref['total'] is not None and row['end'] > ref['total']):
            error = 'range'
        if error:
            result['errors'].append({'index': index, 'code': error})
            continue
        normalized = {k: row[k] for k in ('criterion_id', 'evidence_id', 'start', 'end')}
        normalized['revision'] = ref['revision']
        result['requests'].append(normalized)
        if 'revision' not in row:
            result['normalizations'].append({'index': index, 'field': 'revision',
                                              'value': ref['revision'], 'reason': 'immutable_turn_evidence'})
    if not result['errors']:
        result['status'] = 'normalized' if result['normalizations'] else 'valid'
    return result


def new_evidence_requests(requests, attachments):
    """Subtract already recovered ranges; identity includes the immutable revision.

    Only recovered text is guaranteed to have survived selection. Original
    attachments and reference manifests are not proof of delivery to the model.
    """
    covered = {}
    for row in attachments:
        if row.get('role') == 'recovered':
            key = (row.get('source_ref'), row.get('revision'))
            start = row.get('start', 0)
            covered.setdefault(key, []).append((start, start + len(row['text'])))
    pending = []
    for request in requests:
        key = (request['evidence_id'], request['revision'])
        ranges = [(request['start'], request['end'])]
        for left, right in sorted(covered.get(key, [])):
            ranges = [(a, b) for start, end in ranges
                      for a, b in ((start, min(end, left)), (max(start, right), end)) if a < b]
        for start, end in ranges:
            pending.append({**request, 'start': start, 'end': end})
            covered.setdefault(key, []).append((start, end))
    return pending


def recover(controller, requests):
    """Read only authenticated masked evidence from this turn, preserving revisions."""
    rows = []
    for request in requests:
        if controller.cancelled():
            raise ValueError('증거 회수 중 사용자 취소')
        page = controller.store.read_evidence(request['evidence_id'], 0, None)
        text = page['text']
        if (page.get('integrity') != 'verified' or request['end'] > len(text)
                or page['id'] != request['revision']):
            raise ValueError('증거 만료·판본·범위 불일치')
        start, end = request['start'], request['end']
        rows.append(record(text[start:end], subject=request['evidence_id'], role='recovered',
                           source_ref=request['evidence_id'], revision=request['revision'],
                           criterion_ids=[request['criterion_id']], start=start, total=len(text)))
    return rows
