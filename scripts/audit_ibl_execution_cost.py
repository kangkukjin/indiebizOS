#!/usr/bin/env python3
"""실제 에피소드와 Claude JSONL을 대조한다. 모델 호출·원장 수정·본문 출력 없음.

--episode와 --session을 같은 순서로 반복한다. 출력 토큰에는 추론이 포함되어 있으므로
둘을 더하지 않는다. 응답 시각은 완료된 블록 수신 시각이며 순수 추론/서버 대기는 분리 불가다.
"""
import argparse
import hashlib
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def audit(db, episode, session):
    raw = Path(session).read_bytes()
    messages = {}
    block_count = 0
    for line in raw.decode('utf-8').splitlines():
        event = json.loads(line)
        if event.get('type') != 'assistant':
            continue
        block_count += 1
        msg = event['message']
        if not msg.get('id'):
            raise ValueError('응답 ID가 없어 실제 응답 수를 검증할 수 없습니다')
        dst = messages.setdefault(msg['id'], {
            'response_id': msg['id'], 'model': msg.get('model'), 'effort': event.get('effort'),
            'first_block_at': event['timestamp'], 'last_block_at': event['timestamp'],
            'usage': {}, 'fragments': [], 'tool_argument_chars': 0, 'text_chars': 0,
        })
        dst['last_block_at'] = event['timestamp']
        dst['fragments'].append([b['type'] for b in msg.get('content', [])])
        usage = msg.get('usage', {})
        for key in ('input_tokens', 'output_tokens', 'cache_read_input_tokens', 'cache_creation_input_tokens'):
            if usage.get(key) is not None:
                dst['usage'][key] = max(dst['usage'].get(key, 0), usage[key])
        thinking = usage.get('output_tokens_details', {}).get('thinking_tokens')
        if thinking is not None:
            dst['usage']['thinking_tokens'] = max(dst['usage'].get('thinking_tokens', 0), thinking)
        for b in msg.get('content', []):
            if b['type'] == 'tool_use':
                dst['tool_argument_chars'] += len(json.dumps(b.get('input'), ensure_ascii=False))
            elif b['type'] == 'text':
                dst['text_chars'] += len(b.get('text', ''))
    responses = list(messages.values())
    # 추론 필드 부재는 0으로 바꾸지 않는다. 최신 최종 text-only 응답은 명시 0을 제공한다.
    thinking_known = all('thinking_tokens' in r['usage'] for r in responses)
    output = sum(r['usage'].get('output_tokens', 0) for r in responses)
    thinking = sum(r['usage']['thinking_tokens'] for r in responses) if thinking_known else None
    ep = db.execute('select started_at,ended_at,total_ms,run_id from episode_log where id=?', (episode,)).fetchone()
    if ep is None:
        raise ValueError(f'episode {episode} 없음')
    events = [(seq, ts, kind, json.loads(data)) for seq, ts, kind, data in db.execute(
        'select event_seq,ts,kind,data from trajectory_event where episode_id=? order by event_seq', (episode,))]
    calls = []
    pending = []
    for seq, ts, kind, data in events:
        if kind == 'ibl.started':
            pending.append((seq, ts))
        elif kind == 'ibl.finished':
            start_seq, start = pending.pop()
            calls.append({'event_seq': start_seq, 'started_at': start, 'ended_at': ts,
                          'elapsed_ms': data['elapsed_ms'], 'success': data.get('success')})
    # 동시 구간이 있으면 시간을 이중 계산하지 않고 진단을 중단한다.
    intervals = sorted((c['started_at'], c['ended_at']) for c in calls)
    if pending or any(b[0] < a[1] for a, b in zip(intervals, intervals[1:])):
        raise ValueError('미종료/중첩 구간: IBL 시간 합계 불가')
    ibl_ms = sum(c['elapsed_ms'] for c in calls)
    execution = [d for _, _, k, d in events if k == 'model.usage' and d.get('role') == 'execution']
    if len(execution) != 1 or execution[0].get('output') != output:
        raise ValueError('주 모델 원장 총계와 세션 응답 합계가 다릅니다')
    return {'episode_id': episode, 'session_sha256': hashlib.sha256(raw).hexdigest(),
            'started_at': ep[0], 'ended_at': ep[1], 'total_ms': ep[2],
            'ibl_calls': len(calls), 'ibl_elapsed_ms': ibl_ms, 'outside_ibl_ms': ep[2] - ibl_ms,
            'execution_latency_ms': execution[0]['latency_ms'],
            'assistant_events': block_count, 'unique_responses': len(responses),
            'output_tokens': output, 'thinking_tokens': thinking,
            'nonthinking_output_tokens': output - thinking if thinking is not None else None,
            'calls': calls, 'responses': responses}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--episode', action='append', type=int, required=True)
    parser.add_argument('--session', action='append', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if len(args.episode) != len(args.session):
        parser.error('episode/session의 수가 같아야 합니다')
    db = sqlite3.connect(f'file:{ROOT / "data/world_pulse.db"}?mode=ro', uri=True)
    try:
        result = {'schema': 1, 'episodes': [audit(db, ep, path) for ep, path in zip(args.episode, args.session)]}
    finally:
        db.close()
    with args.out.open('x', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write('\n')
    for ep in result['episodes']:
        print({k: v for k, v in ep.items() if k not in ('calls', 'responses', 'session_sha256')})


if __name__ == '__main__':
    main()
