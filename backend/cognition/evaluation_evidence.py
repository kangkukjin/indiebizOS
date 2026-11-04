"""Immutable receipt candidates and structured evaluation displays; no library access."""
def freeze_receipts(citations, store, cancelled=lambda: False):
    """Replace bodies by authenticated masked TurnStore references before checkpointing."""
    for citation in citations.get('valid', []):
        for receipt in citation.get('receipts', []):
            if cancelled():
                raise ValueError('검수 원문 고정 중 사용자 취소')
            ref = store.evidence(receipt.pop('quote'))
            receipt['evidence_ref'] = {k: ref[k] for k in ('id', 'chars', 'integrity')}
        # Anchors select windows; store them masked with the same evidence boundary.
        for link in citation.get('question_links', []):
            if 'quote' in link:
                ref = store.evidence(link.pop('quote'))
                link['anchor_ref'] = ref['id']


def receipt_sections(citations, store):
    from evaluation_input import record
    rows = []
    for citation in citations.get('valid', []):
        for receipt in citation.get('receipts', []):
            ref = receipt['evidence_ref']
            page = store.read_evidence(ref['id'], 0, None)
            if page.get('integrity') != 'verified' or page['chars'] != ref['chars']:
                raise ValueError('검수 읽기 영수증의 불변 원문을 확인할 수 없습니다')
            row = record(page['text'], subject=citation['citation'], role='citation',
                         source_ref=ref['id'], revision=ref['id'])
            row['receipt'] = {k: citation[k] for k in ('version_ref', 'locator')}
            row['receipt'].update({k: receipt[k] for k in ('access_id', 'extraction_revision')})
            row['contexts'] = [c['claim_context'] for c in citation.get('occurrences', [])]
            row['anchors'] = [store.read_evidence(link['anchor_ref'], 0, None)['text']
                              for link in citation.get('question_links', [])
                              if link.get('extraction_revision') == receipt['extraction_revision']
                              and link.get('anchor_ref')]
            rows.append(row)
    return rows


def structured_sections(key, data):
    """JSON records are atomic: an omitted object never becomes invalid sliced JSON."""
    from evaluation_input import record, dumps
    if key == 'research_claims':
        documents = {}
        for claim in data:
            identity = (claim['path'], claim.get('hash'))
            doc = documents.setdefault(identity, {'path': identity[0], 'hash': identity[1], 'claims': []})
            doc['claims'].append({k: v for k, v in claim.items() if k not in ('path', 'hash')})
        items = list(documents.values())
    elif key == 'research_citations' and isinstance(data, dict):
        items = [{k: v for k, v in data.items() if k != 'valid'}, *data.get('valid', [])]
    else:
        items = data if isinstance(data, list) else [data]
    return [{**record(dumps(item), subject=f'{key}[{i}]'), 'structured': item,
             'structure_kind': key} for i, item in enumerate(items)]


def structure_display(row, displayed):
    """Elide claim prose only when its exact range is present in a delivered document."""
    data = row['structured']
    if row.get('structure_kind') != 'research_claims':
        return data
    claims = []
    for claim in data['claims']:
        text = claim.get('claim_context')
        start, end = claim.get('context_start'), claim.get('context_end')
        matches = [r for r in displayed if r['subject'] == data['path'] and r['role'] == 'submission']
        proven = (isinstance(start, int) and isinstance(end, int) and any(
            r['start'] <= start < end <= r['start'] + len(r['text'])
            and r['text'][start-r['start']:end-r['start']] == text for r in matches))
        claims.append({k: v for k, v in claim.items() if not proven or k != 'claim_context'})
    return {**data, 'claims': claims}
