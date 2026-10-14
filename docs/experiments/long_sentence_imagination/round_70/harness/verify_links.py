"""Check the AI follow-up changed only Markdown links and preserved both JSON files."""
import hashlib
import json
import re
from prepare import HERE, OUT

before = OUT / 'ai-repaired-base'
after = OUT / 'ai-repaired-links'
hashes = {}
for name in ('collected.json', 'decisions.json'):
    original, repaired = (before / name).read_bytes(), (after / name).read_bytes()
    assert original == repaired, name
    hashes[name] = hashlib.sha256(repaired).hexdigest()
original = (before / 'newsletter.md').read_text()
repaired = (after / 'newsletter.md').read_text()
links = re.findall(r'\[([^\]]+)\]\(([^)]+)\)', repaired)
decisions = json.loads((after / 'decisions.json').read_text())['decisions']
urls = [source['url'] for row in decisions for source in row['sources']]
assert sorted(url for _, url in links) == sorted(urls) and len(urls) == 54
assert re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'\1', repaired) == original
result = {'passed': True, 'links': len(links), 'json_sha256': hashes,
          'other_markdown_unchanged': True}
(HERE / 'evidence/verify-links-only.json').write_text(json.dumps(result, indent=2))
print(json.dumps(result))
