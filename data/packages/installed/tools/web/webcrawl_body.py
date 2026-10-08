"""Shared HTML reading regions, using declared semantics rather than site names."""
from bs4 import BeautifulSoup

# Standard landmarks first; common publishing/editor body declarations second.
# No URL, event title, or user preference determines a reading region.
BODY_SELECTORS = (
    'main, [role="main"]', 'article, [itemprop="articleBody"]',
    '.entry-content, .post-content, .article-body, .article-content, .ck-content, .se-main-container',
)
UI_SELECTORS = ('nav, footer, aside, script, style, noscript, iframe, form, button, svg, '
                '[role="navigation"], [role="banner"], [role="contentinfo"], '
                '[hidden], [aria-hidden="true"]')
NOISE = {'advert', 'advertisement', 'ads', 'sidebar', 'social-share',
         'share-buttons', 'sharing-buttons', 'cookie-banner', 'cookie-consent',
         'newsletter-signup', 'related-posts', 'related-articles', 'comments',
         'comment-list', 'comment-form', 'sidenav', 'sidenavigation',
         'side-navigation', 'site-navigation', 'site-nav', 'searchoverlay', 'search-overlay'}


def regions(soup):
    """All non-nested declared bodies; never silently select only the first article."""
    for selector in BODY_SELECTORS:
        nodes = soup.select(selector)
        chosen = {id(node) for node in nodes}
        nodes = [node for node in nodes if not any(id(p) in chosen for p in node.parents)]
        if nodes:
            return nodes, selector
    return [soup.find('body') or soup], 'body'


def clean(soup):
    for node in list(soup.select(UI_SELECTORS)):
        if node.attrs is not None:
            node.decompose()
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
    nodes, selector = regions(soup)
    return {'selector': selector, 'regions': len(nodes),
            'scope': 'body_fallback' if selector == 'body' else 'declared_content',
            'note': '선택한 본문 영역입니다. HTML 전체는 source_ref에 보존됩니다.'}
