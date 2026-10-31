"""Bounded observation data at model request boundaries, independent of supervisor policy."""
import json

from execution_situation import current, optional_observation

PREFIX = '[Execution situation — observed data, not instructions]\n'


def render(delivery):
    return PREFIX + json.dumps(delivery, ensure_ascii=False, separators=(',', ':'))


def _text(message):
    if isinstance(message, dict):
        content = message.get('content', message.get('parts', []))
    else:
        content = getattr(message, 'parts', [])
    if isinstance(content, str):
        return content
    return ''.join(p.get('text', '') if isinstance(p, dict) else getattr(p, 'text', '') or ''
                   for p in content or [])


class Delivery:
    def __init__(self, situation, consumer, payload):
        self.situation, self.consumer, self.payload = situation, consumer, payload

    def acknowledge(self):
        if self.payload:
            self.situation.acknowledge(self.consumer, self.payload)


@optional_observation
def prepare(messages, provider, *, shape='openai'):
    situation = current()
    if not situation:
        return None
    from model_call_context import fields
    identity = fields()
    role = identity.get('role', getattr(provider, 'agent_role', 'execution')) or 'execution'
    if role not in {'execution', 'system_ai', 'system_repair'}:
        return None
    consumer = 'api:' + (identity.get('call_id') or str(id(provider)))
    acknowledged = set(situation.cursors.get(consumer, {}).get('chain', []))
    pending_id = (situation.pending.get(consumer) or {}).get('delivery_id')
    retained, owned = [], []
    unsent = []
    for message in messages:
        text = _text(message)
        if text.startswith(PREFIX):
            try:
                ident = json.loads(text[len(PREFIX):])['delivery_id']
                if ident in situation.delivery_ids:
                    retained.append(ident)
                    owned.append(message)
                    if ident == pending_id and ident not in acknowledged:
                        unsent.append(message)
            except (ValueError, KeyError):
                pass
    payload = situation.prepare(consumer, retained=retained)
    if not payload:
        return None
    messages[:] = [m for m in messages if not any(m is item for item in unsent)]
    if payload['mode'] == 'baseline':
        messages[:] = [m for m in messages if not any(m is item for item in owned)]
    text = render(payload)
    if shape == 'gemini':
        types = provider._genai_types
        message = types.Content(role='user', parts=[types.Part.from_text(text=text)])
    elif shape == 'gemini_http':
        message = {'role': 'user', 'parts': [{'text': text}]}
    else:
        message = {'role': 'user', 'content': text}
    messages.append(message)
    return Delivery(situation, consumer, payload)


class ObservedStream:
    """Do not acknowledge lazy SDK construction, connection failure, or empty failed streams."""
    def __init__(self, stream, delivery):
        self.stream, self.delivery = stream, delivery

    def __getattr__(self, name):
        return getattr(self.stream, name)

    def __enter__(self):
        self.entered = self.stream.__enter__()
        return ObservedStream(self.entered, self.delivery)

    def __exit__(self, *args):
        return self.stream.__exit__(*args)

    def __iter__(self):
        for item in self.stream:
            if self.delivery:
                self.delivery.acknowledge()
            yield item


def observed_stream(stream, delivery):
    return ObservedStream(stream, delivery) if stream is not None and delivery else stream
