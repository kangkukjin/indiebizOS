"""Accessibility UI primitive. One dispatch, bounded read-only observation; never replay."""
import json
import time


def run(args, bridge=None, verifier=None, sleep=time.sleep):
    if bridge is None:
        from indiebiz_android import call
        bridge = call
    action = args['op']
    if action == 'ui_snapshot':
        try:
            before = bridge('snapshot')
        except Exception as error:
            return {'success': False, 'driver_status': 'failed', 'error': str(error),
                    'execution_phase': 'before_dispatch'}
        if before.get('ui_contract') != 1:
            return {'success': False, 'driver_status': 'failed',
                    'error': 'UI_DRIVER_UPDATE_REQUIRED: 폰 APK를 업데이트하고 접근성 서비스를 켜세요.'}
        return {'success': True, 'screen': before}
    # The service reads and validates the current snapshot under its dispatch lock.
    # Its returned before evidence replaces the redundant Python preflight snapshot.
    try:
        reply = bridge('uiControl', json.dumps(args, ensure_ascii=False))['control']
        if not isinstance(reply, dict) or type(reply.get('success')) is not bool:
            raise ValueError('INVALID_UI_REPLY: 조작 결과를 확인하지 못했습니다.')
    except Exception as error:
        unsupported = 'unsupported_device_call: uiControl' in str(error)
        return {'success': False, 'driver_status': 'failed' if unsupported else 'unknown',
                'execution_phase': 'before_dispatch' if unsupported else 'dispatch_unknown',
                'error': ('UI_DRIVER_UPDATE_REQUIRED: 폰 APK를 업데이트하세요. 조작은 실행되지 않았습니다.'
                          if unsupported else str(error))}
    value = {**reply, 'success': reply.get('success') is True}
    if not value['success']:
        value['driver_status'] = 'unknown' if reply.get('dispatched') else 'failed'
        value['error'] = reply.get('error') or '접근성 서비스 상태를 확인하세요.'
        return value
    for attempt in range(8):
        try:
            value['screen'] = bridge('snapshot')
            if verifier(value):
                return value
            if action in {'tap', 'back'} and not args.get('expect'):
                return value  # Dispatch + observation only, no invented UI postcondition.
        except Exception as error:
            value['observation_error'] = str(error)
        if attempt < 7:
            sleep(0.25)
    return {**value, 'success': False, 'driver_status': 'unknown',
            'error': 'POSTCONDITION_UNCONFIRMED: 동작 후 화면 조건을 확인하지 못했습니다. 다시 실행하지 말고 화면만 읽으세요.'}
