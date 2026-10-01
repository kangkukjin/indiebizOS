/** Shared, offline UI translation runtime. Catalogs contain source-code UI only. */
export function createUI(catalog, host = globalThis) {
  const key = 'indiebiz.ui.locale';
  const listeners = new Set();
  const languages = catalog.languages || { ko: '한국어', en: 'English' };
  let locale = 'ko';
  try { const saved = host.localStorage?.getItem(key); if (saved in languages) locale = saved; } catch {}
  const signature = text => [...text.matchAll(/\{\d+\}/g)].map(m => m[0]).sort().join('|');
  function text(id, values = []) {
    const message = catalog.messages[id];
    if (!message) return id;
    let value = message.translations?.[locale] ?? message.source;
    if (signature(value) !== signature(message.source)) value = message.source;
    // A function replacement keeps $&, $1 and markup in user values literal.
    return value.replace(/\{(\d+)\}/g, (_, i) => String(values[Number(i)] ?? `{${i}}`));
  }
  function announce() {
    if (host.document) host.document.documentElement.lang = locale;
    listeners.forEach(fn => fn());
  }
  function setLocale(next) {
    if (!(next in languages)) return;
    locale = next;
    try { host.localStorage?.setItem(key, next); } catch {}
    announce();
  }
  host.addEventListener?.('storage', event => {
    if (event.key === key) { locale = event.newValue in languages ? event.newValue : 'ko'; announce(); }
  });
  if (host.document) host.document.documentElement.lang = locale;
  return { text, languages, getLocale: () => locale, setLocale,
    subscribe(fn) { listeners.add(fn); return () => listeners.delete(fn); } };
}

/** Only compiler-marked elements are visited; never inspect/translate arbitrary DOM text. */
export function mountRemote(ui, doc = document) {
  const attributes = ['title', 'placeholder', 'aria-label', 'alt'];
  const selector = ['[data-ui-text]', ...attributes.map(a => `[data-ui-${a}]`)].join(',');
  function update(root) {
    const nodes = [...(root.querySelectorAll?.(selector) || [])];
    if (root.matches?.(selector)) nodes.unshift(root);
    for (const node of nodes) {
      if (node.closest('[translate="no"], [data-ui-skip]')) continue;
      const id = node.getAttribute('data-ui-text');
      if (id) { const value = ui.text(id); if (node.textContent !== value) node.textContent = value; }
      for (const attr of attributes) {
        const message = node.getAttribute(`data-ui-${attr}`);
        if (message) { const value = ui.text(message); if (node.getAttribute(attr) !== value) node.setAttribute(attr, value); }
      }
    }
  }
  function picker(parent) {
    if (!parent) return;
    const select = doc.createElement('select');
    select.setAttribute('aria-label', 'Language / 언어');
    select.className = 'ui-language';
    select.style.cssText = 'font:inherit;padding:4px;border-radius:6px;max-width:120px;background:#fff;color:#333';
    for (const [value, label] of Object.entries(ui.languages)) {
      const option = doc.createElement('option'); option.value = value; option.textContent = label; select.append(option);
    }
    select.value = ui.getLocale(); select.addEventListener('change', () => ui.setLocale(select.value));
    parent.append(select);
    ui.subscribe(() => { select.value = ui.getLocale(); });
  }
  picker(doc.querySelector('.login-box')); picker(doc.querySelector('.top'));
  update(doc);
  const observer = new MutationObserver(records => {
    for (const record of records) for (const node of record.addedNodes) if (node.nodeType === 1) update(node);
  });
  observer.observe(doc.body, { childList: true, subtree: true });
  ui.subscribe(() => update(doc));
  return () => observer.disconnect();
}
