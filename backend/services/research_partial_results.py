"""Display already-read public source excerpts, independently of final approval."""
import hashlib
import ipaddress
import json
from urllib.parse import urlsplit


def collect(store, tid, run, cancelled=lambda: False):
    from research_library import ResearchLibrary
    from research_capture import clean_url
    from logging_utils import mask_secrets
    lib = ResearchLibrary(store, thread=tid)
    with store.connect() as db:
        store.check_epoch(db)
        if store.thread(tid, db)['active_run'] != run or cancelled():
            return []
        accesses = db.execute('SELECT version_id,revision,locator,quote FROM research_access '
                              'WHERE run_id=? ORDER BY rowid', (run,)).fetchall()
        previous = {}
        for row in db.execute("SELECT payload FROM research_events WHERE thread_id=? AND run_id=? "
                              "AND kind='partial_result' ORDER BY sequence", (tid, run)):
            event = json.loads(row['payload'])
            previous[event['id']] = event
    results = {}
    for access in accesses:
        if cancelled():
            return []
        try:
            version = lib.version(access['version_id'])
            url = clean_url(version['origin'])
            parsed = urlsplit(url)
            host = parsed.hostname or ''
            if (parsed.scheme not in {'https', 'http'} or not host or host == 'localhost'
                    or host.endswith(('.local', '.localhost'))):
                continue  # Draft files and locally captured artifacts stay private.
            try:
                if not ipaddress.ip_address(host).is_global:
                    continue
            except ValueError:
                pass
            paragraphs, revision = lib.paragraphs(version['id'])
            quote = access['quote']
            original = dict(paragraphs).get(access['locator'], '')
            valid = (not version['excluded'] and revision == access['revision']
                     and bool(quote.strip()) and quote in original)
            key = hashlib.sha256(f"{run}:{version['source_id']}:{access['locator']}".encode()).hexdigest()
            results[key] = {'type': 'partial_result', 'id': key, 'state': 'observed' if valid else 'withdrawn',
                'title': mask_secrets(version['title']), 'source': url, 'version': version['id'],
                'extraction_revision': access['revision'], 'locator': access['locator'],
                'content': mask_secrets(quote[:1800]) if valid else '',
                'truncated': len(quote) > 1800, 'scope': 'read_excerpt; source_claim_not_verified',
                'run_id': run}
        except (ValueError, KeyError, OSError):
            continue
    for key, event in previous.items():
        if key not in results:
            results[key] = {**event, 'state': 'withdrawn', 'content': ''}
    return [] if cancelled() else list(results.values())
