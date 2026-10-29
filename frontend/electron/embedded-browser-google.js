// Fixed Google result capture. No supplied script, cookies, forms or account menus.
export function captureGoogleResults() {
  const url = location.origin + location.pathname;
  if (location.hostname === 'consent.google.com') return { url, html: '' };
  if (location.hostname !== 'www.google.com') throw new Error('UNEXPECTED_PAGE');
  if (location.pathname.startsWith('/sorry') || document.querySelector('#captcha-form,.g-recaptcha,iframe[src*="recaptcha"]')) {
    return { url, html: '<div id="captcha-form"></div>' };
  }
  if (location.pathname !== '/search') throw new Error('UNEXPECTED_PAGE');
  const attributes = new Set(['id', 'class', 'href', 'hidden', 'aria-hidden', 'data-text-ad', 'data-agch', 'data-sncf']);
  const root = document.querySelector('#rso') || document.querySelector('#search');
  const parts = [];
  for (const element of [root, document.querySelector('#topstuff')].filter(Boolean)) {
    if (getComputedStyle(element).display === 'none' || getComputedStyle(element).visibility === 'hidden') continue;
    const copy = element.cloneNode(true);
    const originals = [element, ...element.querySelectorAll('*')];
    const copies = [copy, ...copy.querySelectorAll('*')];
    originals.forEach((el, i) => {
      const clone = copies[i];
      if (el.matches('script,style,noscript,input,textarea,select,iframe,[contenteditable]') ||
          getComputedStyle(el).display === 'none' || getComputedStyle(el).visibility === 'hidden') {
        clone.remove(); return;
      }
      for (const attr of [...clone.attributes]) if (!attributes.has(attr.name)) clone.removeAttribute(attr.name);
    });
    parts.push(copy.outerHTML);
  }
  const html = parts.join('');
  if (new TextEncoder().encode(html).length > 400000) throw new Error('RESULTS_TOO_LARGE');
  return { url, html, query: new URL(location.href).searchParams.get('q') };
}
