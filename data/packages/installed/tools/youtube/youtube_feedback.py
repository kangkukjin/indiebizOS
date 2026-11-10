"""Playback-owned readback, attached before releasing the shared player lock."""
from functools import wraps
import uuid

from operation_effects import make


def operation(op, state):
    def decorate(fn):
        @wraps(fn)
        def run(*args, **kwargs):
            s = state()
            with s['_player_lock']:
                previous = s['_player_process']
                result = fn(*args, **kwargs)
                # 시작한 재생의 ID 를 결과에 싣는다 — 뒤의 제어가 '그 재생'을 가리킬 수 있게(stop 의 playback_id).
                started = getattr(s['_player_process'], 'playback_id', None)
                if started and op != 'stop' and result.get('success') is not False and not result.get('queued'):
                    result.setdefault('playback_id', started)
                try:
                    result['observation'] = observe(op, result, s, previous)
                except Exception as exc:
                    result['observation'] = make(
                        driver='youtube_player', implementation=__file__,
                        resource={'kind': 'playback', 'id': None}, scope='player_state',
                        requested={'operation': op}, actual={},
                        checks=[{'name': 'readback', 'matched': None}],
                        status='unknown', reason='readback_failed: ' + str(exc)[:240])
                return result
        return run
    return decorate


def observe(op, result, s, previous):
    phone = s['_phone']
    process = s['_player_process']
    requested_video = result.get('video_id') or (result.get('now_playing') or {}).get('video_id')
    queue_length = len(s['_player_queue'])
    actual = {'video_id': s['_player_video_id'], 'title': s['_player_title'],
              'queue_length': queue_length}
    requested = {'operation': op, 'video_id': requested_video}
    scope, resource_id = 'player_state', getattr(process or previous, 'playback_id', None)
    reason = None
    status = None
    if result.get('stale'):
        # 가리킨 재생이 현재가 아니다: 아무것도 바꾸지 않았고, 그 사실을 관측으로 남긴다.
        native = phone.stream_status() if phone.is_phone() else {}
        return make(driver='youtube_player', implementation=s['__file__'],
                    resource={'kind': 'playback', 'id': result.get('expected_playback_id')}, scope='player_state',
                    requested={'operation': op, 'playback_id': result.get('expected_playback_id'), 'playing': False},
                    actual={**actual, **native},
                    checks=[{'name': 'expected_playback_is_current', 'matched': False}],
                    reason='playback_replaced_or_ended')
    if result.get('queued'):
        position = result.get('queue_position')
        entry = s['_player_queue'][position - 1] if type(position) is int and 0 < position <= queue_length else {}
        resource_id = entry.setdefault('entry_id', uuid.uuid4().hex) if entry else None
        actual.update(queued_video_id=entry.get('video_id'), queue_position=position)
        scope = 'queue_membership'
        checks = [{'name': 'requested_entry_enqueued', 'matched': bool(entry) and entry.get('video_id') == requested_video}]
    elif result.get('play_in_client') or result.get('control') == 'external' or s['_player_mode'] == 'video':
        scope = 'client_handoff' if result.get('play_in_client') else 'external_player'
        actual.update(opened=result.get('opened'), playing=None)
        checks = [{'name': 'playback_state', 'matched': None}]
        status, reason = 'unsupported', 'playback_owned_by_external_client'
    elif phone.is_phone():
        native = phone.stream_status()
        actual.update(native)
        if op == 'stop' or op == 'skip' and process is None:
            requested['playing'] = False
            replaced = bool(previous and native.get('playback_id') not in (None, '', previous.playback_id))
            match = None if replaced or native.get('error') else native.get('playing') is False
            checks = [{'name': 'player_stopped', 'matched': match}]
            if replaced:
                reason = 'playback_ownership_changed'
        else:
            requested['playing'] = True
            same = bool(process and native.get('playback_id') == process.playback_id)
            match = (None if not same or native.get('error') else
                     native.get('playing') is True and s['_player_video_id'] == requested_video)
            checks = [{'name': 'requested_track_playing', 'matched': match}]
            if not same:
                reason = 'playback_ownership_changed'
    else:
        scope = 'process_state'
        alive = process is not None and process.poll() is None
        actual.update(process_running=alive)
        resource_id = str(getattr(process or previous, 'pid', '')) or None
        expected = op != 'stop' and not (op == 'skip' and process is None)
        checks = [{'name': 'owned_process_running' if expected else 'player_processes_stopped',
                   'matched': (alive and s['_player_video_id'] == requested_video) if expected else
                              not alive and not s['is_process_running_by_marker'](s['YOUTUBE_MARKER'])}]
        reason = 'process_state_does_not_prove_audio_output'
    if result.get('success') is False:
        status, reason = 'unknown', result.get('error') or result.get('message') or 'operation_failed'
    return make(driver='youtube_player', implementation=s['__file__'],
                resource={'kind': 'queue_entry' if scope == 'queue_membership' else 'playback', 'id': resource_id},
                scope=scope, requested=requested, actual=actual, checks=checks,
                status=status, reason=reason)
