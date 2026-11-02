"""Input transport limits are independent of model context; no prompt contents in metrics."""
import json
import math

from model_context import input_budget


class InputTooLarge(ValueError):
    kind = 'input_too_large'

    def __init__(self, details):
        self.details = details
        super().__init__('평가 입력 예산 초과: ' + json.dumps(details, ensure_ascii=False))


def failure_kind(error):
    """Only call on a provider failure, never on model prose."""
    text = str(error).lower()
    if any(s in text for s in ('input_too_large', '평가 입력 예산 초과', 'context_length_exceeded', 'request too large', 'input is too long')):
        return 'input_too_large'
    if any(s in text for s in ('timeout', 'timed out', 'deadline', '타임아웃', '마감')):
        return 'deadline'
    if any(s in text for s in ('unauthorized', 'authentication', 'invalid api key', '401')):
        return 'authentication'
    if any(s in text for s in ('cancelled', 'canceled', '사용자 취소')):
        return 'cancelled'
    return 'transport'


def limits(provider):
    return {'input_tokens': input_budget(provider),
            'transport': getattr(provider, 'request_limits', {}) or {},
            'estimate': 'max(text_chars/2, utf8_bytes/3); image reserve 8192 tokens/image'}


def measure(text, images=None):
    encoded = text.encode('utf-8')
    token_text = getattr(text, 'token_text', text)
    return {'chars': len(text), 'bytes': len(encoded),
            'estimated_tokens': math.ceil(max(len(token_text) / 2, len(token_text.encode('utf-8')) / 3)) + 8192 * len(images or [])}


def check(provider, text, *, images=None, reserve=0, model=True):
    measured = measure(text, images)
    policy = limits(provider)
    exceeded = {}
    for unit in ('chars', 'bytes'):
        maximum = policy['transport'].get(unit)
        used = measured[unit] + reserve
        if maximum and used > maximum:
            exceeded[unit] = {'used': used, 'limit': maximum, 'excess': used - maximum}
    if model and measured['estimated_tokens'] + reserve > policy['input_tokens']:
        used = measured['estimated_tokens'] + reserve
        exceeded['estimated_tokens'] = {'used': used, 'limit': policy['input_tokens'],
                                        'excess': used - policy['input_tokens']}
    if exceeded:
        raise InputTooLarge({'exceeded': exceeded, 'limits': policy, 'measured': measured})
    return {**measured, 'limits': policy}


def serialized(provider, message, images=None):
    """Plan with the selected adapter's wrapper. Native image bytes travel separately."""
    builder = getattr(provider, '_build_prompt_with_history', None)
    if callable(builder):
        text = builder(message, [])
        # Codex embeds system in stdin; other CLI adapters send it separately.
        if not getattr(provider, 'system_in_stdin', False):
            text = (provider.system_prompt or '') + '\n' + text
        return text
    return payload_text({'model': getattr(provider, 'model', None), 'system': provider.system_prompt,
                       'messages': [{'role': 'user', 'content': message}],
                       'images': images or [], 'tools': []})


class RequestText(str):
    def __new__(cls, wire, token_text):
        obj = super().__new__(cls, wire)
        obj.token_text = token_text
        return obj


def payload_text(payload, *, ensure_ascii=False):
    """Account for binary transport separately from text token estimation."""
    import base64
    def plain(value):
        if hasattr(value, 'model_dump'):
            return plain(value.model_dump(exclude_none=True))
        if isinstance(value, bytes):
            return base64.b64encode(value).decode('ascii')
        if isinstance(value, dict):
            return {k: plain(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [plain(v) for v in value]
        return value
    def text_only(value):
        if isinstance(value, dict):
            if value.get('type') in {'image', 'image_url'}:
                return '[image]'
            return {k: ('[image]' if k in {'base64', 'inline_data', 'inlineData'} else text_only(v))
                    for k, v in value.items()}
        if isinstance(value, list):
            return [text_only(v) for v in value]
        return value
    obj = plain(payload)
    return RequestText(json.dumps(obj, ensure_ascii=ensure_ascii, default=str),
                       json.dumps(text_only(obj), ensure_ascii=False, default=str))


def check_payload(provider, payload, *, ensure_ascii=False):
    """Last API assembly gate; ordinary execution context policy is unchanged."""
    if not getattr(provider, '_evaluation_budget', False):
        return
    try:
        return check(provider, payload_text(payload, ensure_ascii=ensure_ascii), images=getattr(provider, '_evaluation_images', None))
    except InputTooLarge as exc:
        provider.last_failure_kind, provider.last_failure_details = exc.kind, exc.details
        raise
