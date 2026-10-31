"""공통 수명 조회·명시 검증/수리. 기존 self:script와 정기 유지보수가 같은 입구를 쓴다."""
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import sqlite3

import yaml

import capability_history as ledger
from capability_inventory import collect, executions
from runtime_utils import get_base_path


def _locations(root=None):
    if root is not None:
        return Path(root), ledger.storage_path(root)
    return get_base_path(), ledger.storage_path()


def _days(at):
    if not at:
        return None
    value = datetime.fromisoformat(at)
    if value.tzinfo is None:
        return None  # 옛 로컬 시각의 시간대를 추측하지 않는다.
    return (datetime.now(timezone.utc) - value).days


def sync(root=None):
    root, path = _locations(root)
    inventory = collect(root)  # 파손·읽기 실패면 원장을 건드리지 않는다.
    at = ledger.observe(inventory, path)
    return {'observed_at': at, 'count': len(inventory)}


def operate(args, root=None):
    import principal
    if not principal.is_owner():
        return {'success': False, 'error': '소유자만 구성요소 수명 원장을 조회·기록할 수 있습니다.'}
    if not isinstance(args, dict):
        return {'success': False, 'error': 'args는 객체여야 합니다.'}
    root, path = _locations(root)
    op = args.get('op', 'list')
    if op not in {'list', 'history', 'sync', 'verify', 'repair'}:
        return {'success': False, 'error': 'op: list/history/sync/verify/repair'}
    try:
        inventory = collect(root)
        observed = {'observed_at': ledger.observe(inventory, path), 'inventory_count': len(inventory)}
        key = args.get('key')
        if op in {'verify', 'repair', 'history'} and not key:
            raise ValueError('목록의 key를 지정하세요.')
        if op in {'verify', 'repair'}:
            ledger.record(key, 'verified' if op == 'verify' else 'repaired', args.get('expected_revision'),
                          scope=args.get('scope', ''), outcome=args.get('outcome', ''),
                          evidence=args.get('evidence', ''), reason=args.get('reason', ''), path=path)
        if op == 'history':
            return {'success': True, **ledger.history(key, after=args.get('after', 0),
                                                     limit=args.get('limit', 50), path=path)}
        items = ledger.rows(path)
        runs, telemetry_errors = executions(root)
        for item in items:
            if item['key'] in runs:
                item['last_execution'] = runs[item['key']]
            item['days_since_verification'] = _days(item['last_verified_at'])
            item['days_since_implementation_change'] = _days(item['implementation_changed_at'])
        if key:
            items = [row for row in items if row['key'] == key]
        if args.get('kind'):
            items = [row for row in items if row['kind'] == args['kind']]
        if args.get('status'):
            items = [row for row in items if row['verification_status'] == args['status']]
        total = len(items)
        after, limit = args.get('after', 0), args.get('limit', 50)
        if type(after) is not int or after < 0 or type(limit) is not int or limit < 1:
            raise ValueError('after는 0 이상, limit은 양의 정수여야 합니다.')
        selected = items[after:after + limit]
        return {'success': True, **observed, 'items': selected, 'count': len(selected), 'total': total,
                'summary': dict(Counter(row['verification_status'] for row in items)),
                'next_cursor': after + limit if after + limit < total else None,
                'telemetry_errors': telemetry_errors,
                'verification_meaning': 'current는 명시한 범위·근거가 현재 로컬 revision에 대응한다는 뜻; 전체 기능 보증 아님',
                'revision_limits': '환경변수·외부 API·원격 몸·설치된 라이브러리 바이너리·실행 중 프로세스는 지문 밖'}
    except (ValueError, TypeError, OSError, sqlite3.Error, yaml.YAMLError) as exc:
        return {'success': False, 'error': str(exc)}


def run_age_check():
    """기존 유지보수 주기에 편승. 실행·검증·수리·은퇴를 자동 수행하지 않는다."""
    root, path = _locations()
    with ledger.connection(path) as conn:
        last = conn.execute('SELECT MAX(last_observed_at) FROM components').fetchone()[0]
    if last and (datetime.now(timezone.utc) - datetime.fromisoformat(last)).total_seconds() < 86400:
        return {'skipped': True, 'reason': 'daily cadence'}
    return {'success': True, 'observed_at': ledger.observe(collect(root), path)}
