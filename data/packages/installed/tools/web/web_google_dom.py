"""Google rendered results parser. Unknown layouts/blocks are never successful zero hits."""
import re
from urllib.parse import parse_qs, urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup


def destination(href):
    try:
        url = urljoin('https://www.google.com', href or '')
        parsed = urlsplit(url)
        if parsed.scheme not in ('http', 'https') or parsed.username or parsed.password:
            return None
        # Google also renders opaque /goto links. Preserve the observed redirect URL;
        # displayed breadcrumbs are not sufficient evidence to invent a destination.
        if parsed.hostname == 'www.google.com' and parsed.path in ('/url', '/goto'):
            params = parse_qs(parsed.query)
            target = (params.get('q') or params.get('url') or [''])[0]
            if target.startswith(('https://', 'http://')):
                url, parsed = target, urlsplit(target)
            elif parsed.path == '/goto' and params.get('url'):
                return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parsed.query, ''))
        if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
            return None
        if parsed.hostname == 'google.com' or parsed.hostname.endswith('.google.com'):
            return None
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parsed.query, ''))
    except ValueError:
        return None


def parse_results(html, url, limit=5):
    soup = BeautifulSoup(html, 'html.parser')
    host = urlsplit(url).hostname or ''
    if host == 'consent.google.com':
        return failure('CONSENT_REQUIRED', 'Google 동의 화면입니다. 자동으로 동의하지 않았습니다.')
    if (urlsplit(url).path.startswith('/sorry') or soup.select_one('#captcha-form, .g-recaptcha') or
            soup.select_one('iframe[src*="recaptcha"]')):
        return failure('CAPTCHA_REQUIRED', 'Google이 자동 검색 확인을 요구했습니다. 다른 검색 소스를 사용하거나 브라우저에서 확인하세요.')
    if host != 'www.google.com' or urlsplit(url).path != '/search':
        return failure('UNEXPECTED_PAGE', 'Google 검색 결과 페이지에 도달하지 못했습니다.')
    root = soup.select_one('#rso') or soup.select_one('#search')
    items, seen = [], set()
    if root:
        for heading in root.select('h3'):
            ancestors = list(heading.parents)
            if any(e.get('id') in {'tads', 'tadsb', 'bottomads'} or e.has_attr('data-text-ad') or
                   e.get('aria-hidden') == 'true' or e.has_attr('hidden') for e in ancestors):
                continue
            anchor = heading.find_parent('a', href=True)
            if not anchor:
                continue
            href = anchor.get('href', '')
            # Direct advertiser URLs can occur in sponsored cards; exclude marked ad containers too.
            if '/aclk?' in href or anchor.has_attr('data-agch'):
                continue
            target = destination(href)
            title = heading.get_text(' ', strip=True)
            if not target or target in seen or not title:
                continue
            summary = ''
            for parent in anchor.parents:
                if parent is root or parent.name in ('body', 'html'):
                    break
                if len(parent.select('h3')) > 1:
                    break  # Never attach a neighboring result's snippet.
                snippet = parent.select_one('.VwiC3b, .IsZvec, [data-sncf="1"]')
                if snippet:
                    summary = snippet.get_text(' ', strip=True)
                    break
            seen.add(target)
            items.append({'title': title, 'url': target, 'summary': summary[:1500],
                          'meta': 'Google', 'rank': len(items) + 1,
                          **({'url_kind': 'google_redirect'} if urlsplit(target).hostname == 'www.google.com' else {})})
            if len(items) >= limit:
                break
    if items:
        return {'success': True, 'items': items, 'count': len(items)}
    # Check only Google's no-results region, not query text or snippets containing these words.
    empty = soup.select_one('#topstuff')
    text = empty.get_text(' ', strip=True) if empty else ''
    if re.search(r'did not match any documents|No results found|검색어와 일치하는 문서가 없습니다|검색결과가 없습니다', text, re.I):
        return {'success': True, 'items': [], 'count': 0, 'message': 'Google이 검색 결과 없음으로 표시했습니다.'}
    return failure('RESULTS_UNRECOGNIZED', '검색 결과를 해석하지 못했습니다. 로딩·화면 구조를 확인하거나 다른 검색 소스를 사용하세요.')


def failure(code, message):
    return {'success': False, 'items': [], 'count': 0, 'error_code': code, 'error': message}
