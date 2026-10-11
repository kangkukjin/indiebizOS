"""Independent checks from synthetic inputs and preserved official raw articles."""
import collections
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
ROOT = HERE.parents[3]
OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-11_54회차'


def lines(value):
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, list):
        return [s for v in value for s in lines(v)]
    return []


def seq(value):
    return value if isinstance(value, list) else [value] if isinstance(value, dict) else []


def raw_articles():
    articles, dates = {}, {}
    for path in (HERE / 'evidence').glob('law_*.json'):
        raw = json.loads(path.read_text())
        info = raw['기본정보']
        name = info['법령명_한글']
        date = info['시행일자']
        dates[name] = f'{date[:4]}-{date[4:6]}-{date[6:]}'
        for a in raw['조문']:
            no = '제' + str(a['조문번호']) + '조'
            if a.get('조문가지번호'):
                no += '의' + str(a['조문가지번호'])
            text = lines(a.get('조문내용'))
            for h in seq(a.get('항')):
                text += lines(h.get('항내용'))
                for item in seq(h.get('호')):
                    text += lines(item.get('호내용'))
                    for m in seq(item.get('목')):
                        text += lines(m.get('목내용'))
            articles[(name, no)] = '\n'.join(text)
    return articles, dates


def verify(who, mode, suffix=''):
    folder = OUT / who / mode
    inp = json.loads((folder / 'input.json').read_text())['cases']
    p = folder / 'out/report.json'
    doc = json.loads(p.read_text())
    rows = doc['cases']
    articles, dates = raw_articles()
    errors = collections.defaultdict(list)
    expected_priority = []
    if [r['id'] for r in rows] != [r['id'] for r in inp]:
        errors['1_ids'].append('id/order mismatch')
    for source, row in zip(inp, rows):
        key = (source['law'], source['no'])
        expected = 'unverified_law' if source['law'] not in dates else 'verified' if key in articles else 'unverified_article'
        status = row['citation_status']
        normalized = {'확인': 'verified', '미확인(법령 없음)': 'unverified_law', '미확인(조 없음)': 'unverified_article'}.get(status, status)
        if status.startswith('미확인: 법령 없음'):
            normalized = 'unverified_law'
        elif status.startswith('미확인: 조 없음'):
            normalized = 'unverified_article'
        if normalized != expected:
            errors['2_citations'].append([row['id'], status, expected])
        if expected == 'verified' and (row['article_text'] != articles[key] or not row['url'] or not row['article_date']):
            errors['3_original'].append(row['id'])
        missing = [d for d in source['required_documents'] if d not in source['documents']]
        if row['missing_documents'] != missing:
            errors['4_documents'].append(row['id'])
        historical = source['law'] not in dates or source['event_date'] < dates[source['law']]
        actual = row['historical_review']
        if isinstance(actual, dict):
            actual = actual.get('status')
        if isinstance(actual, str):
            actual = actual in ('과거 판본 확인 필요', '확인 필요')
        if actual != historical:
            errors['5_history'].append([row['id'],row['historical_review'],historical])
        if expected != 'verified' or missing:
            expected_priority.append(row['id'])
    if doc['priority_ids'] != expected_priority:
        errors['6_priority'].append({'strict_order': False, 'same_members': set(doc['priority_ids']) == set(expected_priority)})
    for item in doc['supplements']:
        status = item.get('status', '')
        if status in ('retrieved', '확보'):
            text = item.get('text') or ''.join(a.get('text','') for a in item.get('articles',[]))
            url = item.get('url') or item.get('source',{}).get('url')
            if not text or not url:
                errors['7_supplements'].append(item['key'])
            if item['key'] == 'term' and text == 'counterforce':
                # Preserved source_10 explicitly identifies this entry as a bilingual dictionary.
                errors['7_supplements'].append('translation reported as a definition')
    md = (folder / 'out/report.md').read_text()
    if not md or any(r['id'] not in md for r in rows) or re.search(r'OC=[^&\s"\'\\<]+', p.read_text()+md):
        errors['8_artifacts'].append('missing ids/body or OC')
    result = {'who':who,'mode':mode,'count':len(rows),'passed':8-len(errors),'total':8,'errors':dict(errors),
              'supplements':[{k:v for k,v in s.items() if k in ('key','status')} for s in doc['supplements']]}
    (HERE/'evidence'/f'verify_{who}_{mode}{suffix}.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps(result,ensure_ascii=False))


if __name__ == '__main__':
    verify(*sys.argv[1:])
