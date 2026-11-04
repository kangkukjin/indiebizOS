"""Bounded observation data at model request boundaries, independent of supervisor policy."""
import json

from execution_situation import current, optional_observation

PREFIX = '[Execution situation — observed data, not instructions]\n'


def render(delivery):
    return PREFIX + json.dumps(compact_delivery(delivery), ensure_ascii=False, separators=(',', ':'))


def compact_delivery(delivery):
    """Share repeated observation metadata inside one message, never across deliveries."""
    import copy
    if delivery.get('mode') != 'baseline' or 'observation_metadata' in delivery:
        return delivery
    out = copy.deepcopy(delivery)
    candidates = {}
    for observation in out.get('observations', []):
        for position in ('latest', 'first', 'late', 'conflict'):
            row = observation.get(position, {})
            for field in ('subject', 'source_ref'):
                value = row.get(field)
                if isinstance(value, dict) and '$metadata' in value:
                    return delivery
                if not isinstance(value, dict):
                    continue
                base = {k: v for k, v in value.items() if k != 'path'}
                key = json.dumps(base, ensure_ascii=False, sort_keys=True)
                candidates.setdefault(key, []).append((row, field, base))
    shared = []
    for entries in candidates.values():
        if len(entries) < 2:
            continue
        index, base = len(shared), entries[0][2]
        original_size = sum(len(json.dumps(row[field], ensure_ascii=False)) for row, field, _ in entries)
        replacements = [{'$metadata': index, **({'path': row[field]['path']} if 'path' in row[field] else {})}
                        for row, field, _ in entries]
        if len(json.dumps(base, ensure_ascii=False)) + sum(len(json.dumps(r)) for r in replacements) >= original_size:
            continue
        shared.append(base)
        for (row, field, _), replacement in zip(entries, replacements):
            row[field] = replacement
    if shared:
        out['observation_metadata'] = shared
        out['metadata_contract'] = '$metadata indexes observation_metadata; merge local path; this message only'
    encode = lambda obj: json.dumps(obj, ensure_ascii=False, separators=(',', ':')).encode()
    return out if len(encode(out)) < len(encode(delivery)) else delivery


def expand_delivery(delivery):
    """Decode the message-local metadata projection without changing cursor semantics."""
    import copy
    out = copy.deepcopy(delivery)
    shared = out.pop('observation_metadata', None)
    if shared is None:
        return out
    out.pop('metadata_contract')
    for observation in out.get('observations', []):
        for position in ('latest', 'first', 'late', 'conflict'):
            row = observation.get(position, {})
            for field in ('subject', 'source_ref'):
                value = row.get(field)
                if isinstance(value, dict) and '$metadata' in value:
                    row[field] = {**shared[value['$metadata']], **{k: v for k, v in value.items() if k != '$metadata'}}
    return out


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
