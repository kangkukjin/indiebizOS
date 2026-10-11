"""Close only this rehearsal's local fixture tabs, using its recorded owners."""
import boot_paths  # noqa: F401
import asyncio
import importlib.util
import json
import re
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[5]
OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-12_60회차'


async def main():
    spec = importlib.util.spec_from_file_location('browser60_cleanup', ROOT /
        'data/packages/installed/tools/browser-action/browser_embedded.py')
    driver = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(driver)
    owners = set(json.loads((OUT / 'owners.json').read_text()))
    for path in (OUT / 'runs').glob('*.json'):
        owners.update(re.findall(r'"session_owner",\s*\[\s*"scalar",\s*"([0-9a-f]{64})"', path.read_text()))
    endpoint = driver.connection()
    if not endpoint:
        raise RuntimeError('Live bridge unavailable; no cleanup performed')
    closed = []
    for owner in owners:
        result = await driver.request({'op': 'tab', 'mode': 'list'}, owner, endpoint)
        for tab in result.get('tabs', []):
            parsed = urlparse(tab.get('url', ''))
            if parsed.hostname != '127.0.0.1' or parsed.port != 8874:
                continue
            receipt = await driver.request({'op': 'tab', 'mode': 'close', 'tab_id': tab['tab_id']}, owner, endpoint)
            if not receipt.get('success'):
                raise RuntimeError('Fixture tab did not close: ' + str(receipt.get('error_code')))
            closed.append(tab['tab_id'])
    evidence = {'owners_checked': len(owners), 'closed_fixture_tabs': closed}
    (OUT / 'cleanup.json').write_text(json.dumps(evidence, indent=2))
    print(json.dumps(evidence))


if __name__ == '__main__':
    asyncio.run(main())
