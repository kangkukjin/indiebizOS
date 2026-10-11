"""Shared HTML reading regions, using declared semantics rather than site names."""
from bs4 import BeautifulSoup

# Standard landmarks first; common publishing/editor body declarations second.
# No URL, event title, or user preference determines a reading region.
BODY_SELECTORS = (
    'main, [role="main"]', 'article, [itemprop="articleBody"]',
    '.entry-content, .post-content, .article-body, .article-content, .ck-content, .se-main-container',
)
UI_SELECTORS = ('nav, footer, aside, script, style, noscript, iframe, button, input, select, textarea, svg, '
                '[role="navigation"], [role="banner"], [role="contentinfo"], '
                '[hidden], [aria-hidden="true"]')
NOISE = {'advert', 'advertisement', 'ads', 'sidebar', 'social-share',
         'share-buttons', 'sharing-buttons', 'cookie-banner', 'cookie-consent',
         'newsletter-signup', 'related-posts', 'related-articles', 'comments',
         'comment-list', 'comment-form', 'sidenav', 'sidenavigation',
         'side-navigation', 'site-navigation', 'site-nav', 'searchoverlay', 'search-overlay'}


# A declared region holding only a filter menu or search frame is not the body:
# under THIN_CHARS of text while the page carries THIN_RATIO times more (and at
# least THIN_PAGE_CHARS). Measured on text only, never on site or class names.
THIN_CHARS, THIN_RATIO, THIN_PAGE_CHARS = 400, 5, 1000


def _text_len(nodes):
    return sum(len(' '.join(node.get_text(' ').split())) for node in nodes)


def _regions(soup):
    """(nodes, selector, declared selectors skipped as too thin)."""
    body = soup.find('body') or soup
    body_len, skipped = None, []
    for selector in BODY_SELECTORS:
        nodes = soup.select(selector)
        chosen = {id(node) for node in nodes}
        nodes = [node for node in nodes if not any(id(p) in chosen for p in node.parents)]
        if not nodes:
            continue
        declared = _text_len(nodes)
        if declared < THIN_CHARS:
            if body_len is None:
                body_len = _text_len([body])
            if body_len >= max(THIN_PAGE_CHARS, declared * THIN_RATIO):
                skipped.append(selector)
                continue
        return nodes, selector, skipped
    return [body], 'body', skipped


def regions(soup):
    """All non-nested declared bodies; never silently select only the first article."""
    nodes, selector, _ = _regions(soup)
    return nodes, selector


def clean(soup):
    matched = [node for node in soup.select(UI_SELECTORS) if node.attrs is not None]
    for node in matched:
        if node.name != 'form' and node.attrs is not None:
            node.decompose()
    # A form is a container, not evidence that its prose is UI. Remove actual
    # controls above and unwrap the container without a text-length cutoff.
    for node in list(soup.find_all('form')):
        if node.attrs is not None:
            node.unwrap()
    for node in list(soup.find_all(True)):
        if node.attrs is None:
            continue
        labels = [*node.get('class', []), node.get('id', '')]
        if any(str(label).lower() in NOISE for label in labels):
            node.decompose()


def reading_container(soup):
    clean(soup)
    nodes, _ = regions(soup)
    if len(nodes) == 1:
        return nodes[0]
    fragment = BeautifulSoup('<div></div>', 'html.parser')
    container = fragment.div
    for node in nodes:
        container.append(node.extract())
    return container


def selection(html):
    soup = BeautifulSoup(html, 'html.parser')
    clean(soup)
    nodes, selector, skipped = _regions(soup)
    out = {'selector': selector, 'regions': len(nodes),
           'scope': 'body_fallback' if selector == 'body' else 'declared_content',
           'note': '선택한 본문 영역입니다. HTML 전체는 source_ref에 보존됩니다.'}
    if skipped:
        out['skipped_thin'] = skipped
        out['note'] = '본문 선언 영역에 글이 거의 없어(메뉴·검색 틀) 더 넓은 영역을 읽었습니다. HTML 전체는 source_ref에 보존됩니다.'
    return out
