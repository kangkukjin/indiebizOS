"""Bounded, producer-owned pre-execution diagnostics in the existing turn journal."""
import json
import time

from execution_situation import current, optional_observation


@optional_observation
def publish(report, subject=None, *, situation=None):
    situation = situation or current()
    if situation is None:
        return
    from logging_utils import mask_secret_data
    report = mask_secret_data(report)
    subject = subject or {'kind': 'command', 'source_hash': report['source_hash'],
                          'runtime': report.get('runtime_fingerprint')}
    ref = situation.evidence(report)
    inline = {k: report[k] for k in ('status', 'executed', 'language', 'phase', 'total', 'coverage', 'exit_code') if k in report}
    inline['items'] = []
    for item in report.get('items', [])[:8]:
        small = {k: item[k] for k in ('code', 'severity', 'location', 'message') if k in item}
        if isinstance(small.get('message'), str):
            small['message'] = small['message'].encode()[:240].decode(errors='ignore')
        if isinstance(small.get('location'), dict):
            small['location'] = {k: small['location'][k] for k in ('line', 'column', 'encoding', 'offset_encoding')
                                 if k in small['location']}
        inline['items'].append(small)
        if len(json.dumps(inline, ensure_ascii=False).encode()) > 850:
            inline['items'].pop()
            break
    inline['omitted'] = max(0, report.get('total', len(report.get('items', []))) - len(inline['items']))
    situation.observe(subject, 'diagnostics', inline,
                      source='shell_execution' if report.get('phase') == 'execution' else 'preflight', source_ref=ref,
                      subject_revision=report['source_hash'], observed_at=time.time())


def execution_result(preflight, exit_code, output, *, subject=None, situation=None, executed=True):
    """Actual exit feedback, including cmd. Never claims unsupported syntax was checked."""
    report = {**preflight, 'phase': 'execution', 'executed': executed,
              'status': 'succeeded' if exit_code == 0 else 'failed', 'exit_code': exit_code,
              'items': [], 'total': 0}
    if exit_code != 0:
        report['items'] = [{'code': 'SHELL_EXIT_NONZERO', 'severity': 'error',
                            'message': f'exit {exit_code}: {output[-2000:]}'}]
        report['total'] = 1
    publish(report, subject, situation=situation)
    return report


def blocked(report):
    return report['status'] in ('invalid', 'failed')


def rejection(report):
    return {'success': False, 'executed': False, 'error': '실행 전 검사에서 거절했습니다',
            'preflight': report}
