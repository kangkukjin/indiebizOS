"""포식 근거의 공통 해소·연결·제한된 현재성 대조. 네트워크/모델 호출 없음."""
import copy
import fnmatch
import hashlib
import json
import os
import stat
import time
import uuid

from distill_receipts import fingerprint
from source_observation import file_state, now

# 호출 전체에 공유. 실제 10k 항목/64MiB fixture로 검증한다.
CHECK_LIMITS = {'seconds': 2.0, 'entries': 10000, 'bytes': 64 * 1024 * 1024}


def provenance(value):
    if isinstance(value, str):
        value = json.loads(value or '{}')
    if not isinstance(value or {}, dict):
        raise ValueError('provenance must be an object')
    return copy.deepcopy(value or {})


def claim_digest(row):
    from forage_doc import _claim_key, _norm
    return fingerprint([_claim_key(row.get('claim')), _norm(row['locus']), row['kind'],
                        row.get('prior_class', 'structural'), bool(row.get('generalizes'))])


def bind(row, prov=None):
    p = provenance(row.get('provenance') if prov is None else prov)
    p.setdefault('claim_ref', uuid.uuid4().hex)
    p.setdefault('claim_digest', claim_digest(row))
    p.setdefault('evidence', {'schema_version': 1, 'items': [], 'link_state': 'legacy'})
    if p['claim_digest'] != claim_digest(row):
        p['evidence']['link_state'] = 'reconfirmation_required'
    return p


def resolve_input(value, locus):
    """직접 note는 영수증/job 참조만 채택한다. 입력 판본·해시는 신뢰하지 않는다."""
    p = provenance(value)
    refs = p.pop('observation_refs', [])
    if not isinstance(refs, list):
        raise ValueError('observation_refs must be a list')
    p.pop('evidence', None)
    p.pop('claim_ref', None)
    p.pop('claim_digest', None)
    items = []
    from source_observation import resolve, identity
    for ref in refs:
        if not isinstance(ref, dict):
            raise ValueError('invalid_observation_ref')
        if ref.get('receipt_id'):
            items.append(resolve(ref['receipt_id'], locus=locus))
        elif ref.get('job_key') and type(ref.get('observation_id')) is int:
            import distill_ledger
            record = distill_ledger.read(ref['job_key'])
            owner, body = identity()
            if (not record or record['payload'].get('principal') != owner
                    or record['payload'].get('body_id') != body):
                raise ValueError('unknown_or_foreign_job')
            observations = (((record.get('prepared') or {}).get('sections') or {}).get('forage') or {}).get('observations', [])
            observation = next((r for r in observations if r['id'] == ref['observation_id']), None)
            if not observation:
                raise ValueError('unknown_observation_id')
            for e in observation.get('source_evidence', []):
                items.append(resolve(e['observation_ref']['receipt_id'], locus=locus))
            if not observation.get('source_evidence'):
                raise ValueError('unversioned_observation')
        else:
            raise ValueError('invalid_observation_ref')
    p['evidence'] = {'schema_version': 1, 'items': items,
                     'link_state': 'observed' if items else ('tool_result_only' if p.get('job_key') and p.get('observed') else 'user_declaration')}
    return p


def merge(old, new):
    a, b = provenance(old), provenance(new)
    for key in ('claim_ref', 'claim_digest'):
        if key not in a and key in b:
            a[key] = b[key]
    ae, be = a.get('evidence', {}), b.get('evidence', {})
    items = ae.get('items', []) + be.get('items', [])
    unique = {fingerprint(e): e for e in items}
    a['evidence'] = {'schema_version': 1, 'items': list(unique.values()),
                     'link_state': ae.get('link_state') or be.get('link_state', 'legacy')}
    # Semantic edits require an explicit new confirmation, not merely fresh bytes.
    if be.get('items') and ae.get('link_state') != 'reconfirmation_required':
        a['evidence']['link_state'] = 'observed'
    return a


class BudgetExceeded(Exception):
    pass


class Checker:
    def __init__(self, mode='metadata', limits=None):
        if mode not in {'metadata', 'content'}:
            raise ValueError('evidence_check must be metadata or content')
        self.mode = mode
        self.limits = {**CHECK_LIMITS, **(limits or {})}
        self.started = time.monotonic()
        self.bytes = self.entries = 0
        self.cache = {}
        self.observed = {}
        self.checked_at = now()

    def spend(self, *, size=0, entries=0):
        if (time.monotonic() - self.started >= self.limits['seconds']
                or self.bytes + size > self.limits['bytes']
                or self.entries + entries > self.limits['entries']):
            raise BudgetExceeded()
        self.bytes += size
        self.entries += entries

    def listing(self, path, scope):
        depth = scope.get('depth', 1)
        if type(depth) is not int or not 1 <= depth <= 64:
            raise ValueError('unsupported_listing_depth')
        entries, states = [], {}
        def walk(folder, level):
            self.spend()
            states[folder] = file_state(folder)
            with os.scandir(folder) as scan:
                for entry in scan:
                    self.spend(entries=1)
                    rel = os.path.relpath(entry.path, path)
                    if any(fnmatch.fnmatchcase(rel, p) for p in scope.get('exclusions', [])):
                        continue
                    mode = entry.stat(follow_symlinks=False).st_mode
                    kind = 'symlink' if stat.S_ISLNK(mode) else ('directory' if stat.S_ISDIR(mode) else 'file')
                    if not scope.get('pattern') or fnmatch.fnmatchcase(entry.name, scope['pattern']):
                        entries.append([rel, kind])
                    if kind == 'directory' and level < depth:
                        walk(entry.path, level + 1)
        walk(path, 1)
        if any(file_state(p) != s for p, s in states.items()):
            return None
        return fingerprint(sorted(entries))

    def file_hash(self, path, evidence):
        scope = evidence['scope']
        method = evidence['version']['method']
        digest = hashlib.sha256()
        if method == 'sha256_utf8_lines' and scope.get('selector', {}).get('start') == scope.get('selector', {}).get('end'):
            return digest.hexdigest()
        with open(path, 'rb') as stream:
            if method == 'sha256_bytes':
                while True:
                    self.spend()
                    chunk = stream.read(min(65536, max(1, self.limits['bytes'] - self.bytes + 1)))
                    if not chunk:
                        break
                    self.spend(size=len(chunk))
                    digest.update(chunk)
            elif method == 'sha256_utf8_lines' and scope.get('selector'):
                selector = scope['selector']
                # TextIOWrapper preserves the producer's CR/LF/CRLF semantics. Every
                # buffered read spends the shared byte/time budget, including read-ahead.
                import io
                checker = self
                class BoundedReader(io.RawIOBase):
                    def readable(self):
                        return True

                    def readinto(self, target):
                        checker.spend()
                        chunk = stream.read(min(len(target), max(1, checker.limits['bytes'] - checker.bytes + 1)))
                        checker.spend(size=len(chunk))
                        target[:len(chunk)] = chunk
                        return len(chunk)
                with io.TextIOWrapper(io.BufferedReader(BoundedReader()), encoding='utf-8', newline='') as lines:
                    for index, line in enumerate(lines):
                        if selector['start'] <= index < selector['end']:
                            digest.update(line.encode('utf-8'))
                        if index + 1 >= selector['end']:
                            break
            else:
                raise ValueError('unsupported_selector')
        return digest.hexdigest()

    def check(self, e):
        key = fingerprint([e.get('source'), e.get('scope'), e.get('version'), e.get('stable')])
        if key in self.cache:
            return dict(self.cache[key])
        result = {'state': 'unknown', 'method': self.mode, 'reason': 'unlinked'}
        try:
            self.spend()
            source, version = e.get('source', {}), e.get('version', {})
            path = source.get('address', '')
            if e.get('link_state') != 'observed' or not version.get('sha256'):
                result['reason'] = 'legacy_or_declaration'
            elif not e.get('stable'):
                result['reason'] = 'unstable_observation'
            elif source.get('kind') not in {'file', 'directory'} or not os.path.isabs(path):
                result['reason'] = 'unsupported_source'
            else:
                from source_observation import identity, device_identity
                from forage_memory import _mounted
                if (source.get('body') != identity()[1]
                        or source.get('device_id') != device_identity()):
                    result['reason'] = 'different_body'
                elif not _mounted(path):
                    result['reason'] = 'offline_volume'
                else:
                    before = file_state(path)
                    self.spend()
                    if source['kind'] == 'directory' and not e.get('scope', {}).get('complete'):
                        result['reason'] = 'incomplete_listing'
                    elif self.mode == 'metadata':
                        old = version.get('metadata', {})
                        # Metadata differences expose change; equality never proves byte/list equality.
                        changed = before != old
                        result.update(state='changed' if changed else 'unknown',
                                      reason='metadata_changed' if changed else 'content_not_checked')
                    else:
                        observation_key = fingerprint([source, e['scope'], version['method']])
                        if observation_key not in self.observed:
                            digest = (self.listing(path, e['scope']) if source['kind'] == 'directory'
                                      else self.file_hash(path, e))
                            self.observed[observation_key] = (digest, before, file_state(path))
                        digest, before, after = self.observed[observation_key]
                        self.spend()
                        if digest is None or after != before:
                            result['reason'] = 'unstable_check'
                        else:
                            changed = digest != version['sha256'] or before['target'] != version.get('metadata', {}).get('target', before['target'])
                            result.update(state='changed' if changed else 'unchanged',
                                          method=version['method'], reason='version_changed' if changed else 'version_equal')
        except FileNotFoundError:
            # Only ENOENT on an available volume is a confirmed absence.
            result.update(state='missing', reason='not_found')
        except PermissionError:
            result['reason'] = 'permission'
        except BudgetExceeded:
            result['reason'] = 'budget_exhausted'
        except OSError as exc:
            result['reason'] = 'io_error:' + str(exc.errno)
        except (ValueError, KeyError, TypeError):
            result['reason'] = 'unsupported_evidence'
        self.cache[key] = result
        return dict(result)

    def status(self, row):
        p = bind(row)
        evidence = p['evidence']
        outcomes = [{**self.check(e), 'source': e.get('source'),
                     'observation_ref': e.get('observation_ref'), 'scope': e.get('scope')}
                    for e in evidence.get('items', [])]
        if evidence.get('link_state') != 'observed' or not outcomes:
            outcomes.append({'state': 'unknown', 'method': 'none', 'reason': evidence.get('link_state', 'legacy')})
        states = {r['state'] for r in outcomes}
        state = next(s for s in ('changed', 'missing', 'unknown', 'unchanged') if s in states)
        return {'state': state, 'checked_at': self.checked_at, 'comparison': self.mode,
                'checked': sum(r['state'] != 'unknown' for r in outcomes),
                'unchecked': sum(r['state'] == 'unknown' for r in outcomes),
                'outcomes': outcomes, 'receipt_availability': 'not_checked',
                'claim_ref': p['claim_ref']}


def annotate(rows, checker):
    import forage_doc
    for row in rows:
        status = checker.status(row)
        row['evidence_status'] = status
        row['evidence_doc'] = forage_doc.doc_path_for(row['body'], row['locus'], create_default=False)
        if status['state'] == 'changed':
            row['freshness'] = 'stale'
        elif status['state'] == 'missing':
            row['freshness'] = 'missing'
        elif provenance(row.get('provenance')).get('evidence', {}).get('items'):
            row['freshness'] = ''
