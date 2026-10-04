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
  // Called only at explicitly declared system-metadata sinks, never arbitrary content.
  const systemMessages = Object.entries(catalog.messages).filter(([, m]) => m.context === 'system:metadata' || m.context === 'system:status');
  // Match complete source-owned status templates, never substitute inside diagnostic values.
  const statusTemplates = systemMessages.filter(([, m]) => m.context === 'system:status' && /\{\d+\}/.test(m.source)).sort((a, b) => b[1].source.length - a[1].source.length).map(([id, m]) => {
    const slots = [];
    const pattern = m.source.split(/(\{\d+\})/).map(part => {
      if (/^\{\d+\}$/.test(part)) { slots.push(Number(part.slice(1, -1))); return '([\\s\\S]*?)'; }
      return part.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    }).join('');
    return { id, slots, pattern: new RegExp('^' + pattern + '$') };
  });
  const systemIds = new Map(systemMessages.map(([id, m]) => [m.source, id]));
  const fragments = [...systemIds.keys()].filter(s => s.length > 4).sort((a,b) => b.length - a.length);
  function system(value, allowFragments = false) {
    if (typeof value !== 'string' || locale === 'ko') return value;
    if (systemIds.has(value)) return text(systemIds.get(value));
    if (value.length <= 10000) for (const template of statusTemplates) {
      const match = template.pattern.exec(value);
      if (match) {
        const values = [];
        template.slots.forEach((slot, index) => { values[slot] = match[index + 1]; });
        return text(template.id, values);
      }
    }
    if (!allowFragments) return value;
    // Server-owned descriptions can concatenate source sentences; unmatched text stays literal.
    let output = '', cursor = 0;
    while (cursor < value.length) {
      const fragment = fragments.find(s => value.startsWith(s, cursor));
      if (fragment) { output += text(systemIds.get(fragment)); cursor += fragment.length; }
      else output += value[cursor++];
    }
    return output;
  }
  function instrument(raw) {
    const spec = catalog.instruments?.[raw?.id];
    if (!spec || spec.name !== raw.name || locale === 'ko') return raw;
    const copy = structuredClone(raw);
    for (const field of spec.fields) {
      let node = copy;
      for (const key of field.path.slice(0, -1)) node = node?.[key];
      const key = field.path.at(-1);
      // The id, path AND unchanged source must agree. Overrides remain literal.
      if (node && node[key] === field.source) node[key] = system(field.source);
    }
    return copy;
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
  return { text, system, instrument, languages, getLocale: () => locale, setLocale,
    subscribe(fn) { listeners.add(fn); return () => listeners.delete(fn); } };
}

/** Only compiler-marked elements are visited; never inspect/translate arbitrary DOM text. */
export function mountRemote(ui, doc = document) {
  const attributes = ['title', 'placeholder', 'aria-label', 'alt'];
  const selector = ['[data-ui-text]', '[data-ui-system]', ...attributes.map(a => `[data-ui-${a}]`)].join(',');
  function update(root) {
    const nodes = [...(root.querySelectorAll?.(selector) || [])];
    if (root.matches?.(selector)) nodes.unshift(root);
    for (const node of nodes) {
      if (node.closest('[translate="no"], [data-ui-skip]')) continue;
      const systemSource = node.getAttribute('data-ui-system');
      if (systemSource !== null) {
        const value = (node.getAttribute('data-ui-prefix') || '') + ui.system(systemSource, node.hasAttribute('data-ui-fragments'));
        if (node.textContent !== value) node.textContent = value;
      }
      const id = node.getAttribute('data-ui-text');
      if (id) { const value = ui.text(id); if (node.textContent !== value) node.textContent = value; }
      for (const attr of attributes) {
        const message = node.getAttribute(`data-ui-${attr}`);
        if (message) { const value = ui.text(message); if (node.getAttribute(attr) !== value) node.setAttribute(attr, value); }
      }
    }
  }
  // Serialized into the remote bundle: keep the picker and its scoped styles together.
  const pickerStyle = doc.createElement('style');
  pickerStyle.textContent = `
.ui-language-picker{position:relative;display:inline-flex;align-items:center;flex-shrink:0;color:var(--dim,#8A7B6C)}
.top .ui-language-picker{margin-left:8px}
.login-box .ui-language-picker{display:flex;width:max-content;margin:14px auto 0}
.ui-language-picker .ui-language{appearance:none;-webkit-appearance:none;box-sizing:border-box;cursor:pointer;height:26px;max-width:140px;border:1px solid var(--line,#E5DFD5);border-radius:999px;background:var(--bg3,#EAE4DA);color:inherit;font-family:inherit;font-size:11px;font-weight:600;line-height:1.5;letter-spacing:-.01em;padding:0 25px 0 29px;transition:background .15s,border-color .15s,color .15s}
.ui-language-picker .ui-language:hover{border-color:var(--acc,#D97706);color:var(--acc2,#B45309)}
.ui-language-picker .ui-language:active{background:var(--line,#E5DFD5);border-color:var(--acc,#D97706);color:var(--acc2,#B45309)}
.ui-language-picker .ui-language:focus-visible{outline:2px solid var(--acc,#D97706);outline-offset:2px}
.ui-language-picker svg{position:absolute;pointer-events:none;width:13px;height:13px;left:10px}
.ui-language-picker .ui-language-chevron{width:11px;height:11px;left:auto;right:9px}
.ui-language-picker option{background:var(--bg2,#FFFFFF);color:var(--txt,#4A4035)}
`;
  doc.head.append(pickerStyle);
  function picker(parent) {
    if (!parent) return;
    const wrapper = doc.createElement('div');
    wrapper.className = 'ui-language-picker';
    function icon(path, className = '') {
      const svg = doc.createElementNS('http://www.w3.org/2000/svg', 'svg');
      for (const [key, value] of Object.entries({viewBox:'0 0 24 24',fill:'none',stroke:'currentColor','stroke-width':'2','stroke-linecap':'round','stroke-linejoin':'round','aria-hidden':'true',focusable:'false',class:className})) svg.setAttribute(key, value);
      const shape = doc.createElementNS('http://www.w3.org/2000/svg', 'path');
      shape.setAttribute('d', path); svg.append(shape);
      return svg;
    }
    wrapper.append(icon('m5 8 6 6m-7 0 6-6 2-3M2 5h12M7 2h1m14 20-5-11-5 11m2-4h6'));
    const select = doc.createElement('select');
    select.setAttribute('aria-label', 'Language / 언어');
    select.className = 'ui-language';
    for (const [value, label] of Object.entries(ui.languages)) {
      const option = doc.createElement('option'); option.value = value; option.textContent = label; select.append(option);
    }
    select.value = ui.getLocale(); select.addEventListener('change', () => ui.setLocale(select.value));
    wrapper.append(select, icon('M6 9l6 6 6-6', 'ui-language-chevron'));
    parent.append(wrapper);
    ui.subscribe(() => { select.value = ui.getLocale(); });
  }
  picker(doc.querySelector('.login-box')); picker(doc.querySelector('.top'));
  update(doc);
  const observer = new MutationObserver(records => {
    for (const record of records) {
      if (record.type === 'attributes') update(record.target);
      else for (const node of record.addedNodes) if (node.nodeType === 1) update(node);
    }
  });
  observer.observe(doc.body, { childList: true, subtree: true, attributes: true,
    attributeFilter: ['data-ui-system', 'data-ui-prefix', 'data-ui-fragments', 'data-ui-text', ...attributes.map(a => `data-ui-${a}`)] });
  ui.subscribe(() => update(doc));
  return () => observer.disconnect();
}
