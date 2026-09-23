#!/usr/bin/env python3
"""유튜브 AI 팁 보고서 — 평탄 팁 행(tip/how/vid/title/uploader/url)을
tips.json 스키마(source 중첩)로 변환한다. 기존 보고서의 저장 스키마 변환을
이 스크립트가 맡는다. 현재 IBL compute 콜백도 Record를 만들 수 있다. 출력은 [self:ledger]{op:'append', items_file:...} 로 적재.

인자는 stdin JSON: {src, out, topic, date, report, try_match}
  try_match — '||' 로 구분한 부분문자열 목록. 팁 제목에 포함되면 try_candidate=true.
"""
import json
import sys

a = json.loads(sys.stdin.read() or '{}')
for k in ('src', 'out', 'topic', 'date', 'report'):
    if not a.get(k):
        print(json.dumps({'error': f'인자 누락: {k}'}, ensure_ascii=False))
        sys.exit(2)

keys = [k.strip() for k in a.get('try_match', '').split('||') if k.strip()]
rows = json.load(open(a['src'], encoding='utf-8'))['items']
out = []
for r in rows:
    out.append({
        'tip': r['tip'],
        'how': r.get('how', ''),
        'topic': a['topic'],
        'source': {
            'video_id': r.get('vid') or r.get('video_id'),
            'title': r.get('title', ''),
            'channel': r.get('uploader') or r.get('channel', ''),
            'url': r.get('url', ''),
        },
        'date': a['date'],
        'report': a['report'],
        'try_candidate': any(k in r['tip'] for k in keys),
    })
json.dump({'items': out, 'count': len(out)}, open(a['out'], 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
print(json.dumps({'count': len(out), 'try_candidates': sum(1 for o in out if o['try_candidate']), 'out': a['out']}, ensure_ascii=False))
