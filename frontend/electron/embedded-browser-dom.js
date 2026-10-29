import { captureGoogleResults } from './embedded-browser-google.js';
// Fixed, isolated-world page program. Never execute model-provided JavaScript.
export function pageOperation(op, args = {}) {
  const fail = (code) => { throw new Error(code); };
  const state = globalThis.__indiebizBrowser ??= {
    document: crypto.randomUUID(), refs: new Map(), seq: 0, texts: new Map(),
  };
  const visible = el => !!el?.isConnected && !!el.getClientRects().length &&
    getComputedStyle(el).visibility !== 'hidden' && !el.closest('[hidden],[aria-hidden="true"]');
  const sensitive = el => el.matches('input[type="password"],input[autocomplete="one-time-code"]') ||
    /otp|verification.?code|auth.?code/i.test(`${el.name} ${el.id} ${el.autocomplete}`);
  const name = el => (el.getAttribute('aria-label') || el.labels?.[0]?.innerText ||
    el.getAttribute('placeholder') || el.innerText || el.getAttribute('title') || '').trim().slice(0, 160);
  const role = el => el.getAttribute('role') || ({ A: 'link', BUTTON: 'button', SELECT: 'combobox',
    TEXTAREA: 'textbox', SUMMARY: 'button', INPUT: el.type === 'checkbox' ? 'checkbox' : 'textbox' })[el.tagName] || el.tagName.toLowerCase();
  const url = value => { try { const u = new URL(value, location.href); u.search = ''; u.hash = ''; u.username = ''; u.password = ''; return u.href; } catch { return ''; } };
  const ref = el => {
    const id = `${state.document.slice(0, 8)}-e${++state.seq}`;
    state.refs.set(id, { el, name: name(el), role: role(el) });
    return id;
  };
  const resolve = key => {
    const entry = state.refs.get(key);
    if (!entry || !visible(entry.el) || entry.name !== name(entry.el) || entry.role !== role(entry.el)) fail('STALE_REF');
    return entry.el;
  };
  if (args.document_id && args.document_id !== state.document) fail('STALE_DOCUMENT');
  const base = { document_id: state.document, url: url(location.href), title: document.title.slice(0, 250) };
  if (op === 'snapshot') {
    state.refs.clear();
    const all = [...document.querySelectorAll('a[href],button,input:not([type="hidden"]),textarea,select,summary,[role],[contenteditable="true"]')].filter(visible);
    const elements = all.slice(0, 200).map(el => ({ ref: ref(el), role: role(el), name: name(el),
      disabled: !!el.disabled, ...(el.tagName === 'A' ? { href: url(el.href) } : {}),
      ...(sensitive(el) ? { sensitive: true } : {}), ...(el.type === 'checkbox' ? { checked: el.checked } : {}) }));
    return { ...base, elements, total: all.length, truncated: all.length > elements.length,
      snapshot: elements.map(e => `[${e.ref}] ${e.role} ${e.name}${e.sensitive ? ' [protected]' : ''}`).join('\n') };
  }
  if (op === 'content') {
    const integer = (value, fallback) => {
      if (value == null) return fallback;
      if (!Number.isInteger(value) || value < 0) fail('INVALID_CONTENT_RANGE');
      return value;
    };
    const offset = integer(args.offset, 0);
    const requested = integer(args.limit, 12000);
    if (!requested) fail('INVALID_CONTENT_RANGE');
    const limit = Math.min(20000, Math.max(500, requested));
    const explicit = args.limit != null && requested === limit;
    let cursor = args.cursor;
    let saved = cursor ? state.texts.get(cursor) : null;
    if (cursor && !saved) fail('STALE_CURSOR');
    if (!saved) {
      // Scope is the rendered document, or the explicitly observed element.
      // An article/form is structure, not proof that its siblings are irrelevant.
      const root = args.ref ? resolve(args.ref) : document.body;
      if (!root) fail('CONTENT_NOT_READY');
      const excluded = 'script,style,noscript,textarea,input,select,[contenteditable]:not([contenteditable="false"])';
      const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT);
      const parts = []; let units = 0; let captureTruncated = false; let previousBlock;
      const append = value => {
        const remaining = 500000 - units;
        if (value.length > remaining) { captureTruncated = true; value = value.slice(0, remaining); }
        parts.push(value); units += value.length;
      };
      let node;
      while ((node = walker.nextNode())) {
        const el = node.nodeType === Node.ELEMENT_NODE ? node : node.parentElement;
        if (!el || el.closest(excluded) || el.closest('[hidden],[aria-hidden="true"]')) continue;
        if (node.nodeType === Node.ELEMENT_NODE) {
          if (el.tagName === 'BR' && visible(el)) append('\n');
          if (captureTruncated) break;
          continue;
        }
        // Ranges also work for visible text inside display:contents containers.
        const range = document.createRange(); range.selectNodeContents(node);
        const style = getComputedStyle(el);
        if (!range.getClientRects().length || ['hidden', 'collapse'].includes(style.visibility)) continue;
        let block = el;
        while (block !== root && block.parentElement &&
               ['inline', 'contents', 'inline-block', 'inline-flex', 'inline-grid'].includes(getComputedStyle(block).display)) block = block.parentElement;
        const value = /^(pre|break-spaces)/.test(style.whiteSpace) ? node.textContent : node.textContent.replace(/[\t\n\r\f ]+/g, ' ');
        if (!value) continue;
        if (previousBlock && previousBlock !== block) append('\n');
        append(value); previousBlock = block;
        if (captureTruncated) break;
      }
      let text = parts.join('').replace(/[ \t]*\n[ \t]*/g, '\n').trim();
      // Never serialize half a surrogate pair at the hard extraction boundary.
      if (captureTruncated && /[\uD800-\uDBFF]$/.test(text)) text = text.slice(0, -1);
      const links = [...(root.matches('a[href]') ? [root] : []), ...root.querySelectorAll('a[href]')]
        .filter(el => visible(el) && !el.closest(excluded));
      saved = { ...base, points: Array.from(text), captureTruncated,
        captured_at: new Date().toISOString(), links_total: links.length,
        links: links.slice(0, 80).map(el => ({ text: name(el), url: url(el.href) })) };
      cursor = crypto.randomUUID();
      state.texts.clear(); state.texts.set(cursor, saved);
    }
    const { points, captureTruncated, ...metadata } = saved;
    const content = points.slice(offset, offset + limit).join('');
    const next = offset + limit < points.length ? offset + limit : null;
    const linksOmitted = saved.links_total - saved.links.length;
    const truncations = [];
    if (next !== null) truncations.push({ scope: explicit ? 'selection' : 'source',
      reason: 'limit', limit, retained: Math.min(limit, Math.max(0, points.length - offset)), unit: 'characters' });
    if (captureTruncated) truncations.push({ scope: 'source', reason: 'capture_limit', limit: 500000, retained: points.length });
    if (linksOmitted) truncations.push({ scope: 'source', reason: 'links_limit', limit: 80, retained: saved.links.length, total: saved.links_total });
    return { ...metadata, content, cursor, offset, next_offset: next,
      truncated: truncations.length > 0, truncations, capture_truncated: captureTruncated,
      source_complete: !truncations.some(t => t.scope === 'source'), total_chars: points.length,
      scope: 'rendered_dom', links_omitted: linksOmitted,
      coverage_limits: ['unloaded_or_collapsed_content', 'images_and_canvas', 'other_frames', 'form_values'] };
  }
  if (op === 'auth_probe') {
    const fields = [...document.querySelectorAll('input')].filter(visible);
    const password = fields.find(el => el.type === 'password');
    const user = fields.find(el => el.autocomplete === 'username' || el.type === 'email') ||
      (password ? fields.find(el => ['text', 'email'].includes(el.type) && !sensitive(el)) : null);
    const otp = fields.some(el => sensitive(el) && el.type !== 'password') ||
      [...document.querySelectorAll('iframe')].some(el => visible(el) && /captcha|challenge/i.test(`${el.src} ${el.title}`));
    return { ...base, origin: location.origin, password_ref: password ? ref(password) : null,
      username_ref: user ? ref(user) : null, user_action_required: otp,
      state: otp ? 'user_action_required' : password || user ? 'login_required' : 'unknown' };
  }
  if (op === 'auth_fill') {
    if (location.origin !== args.origin) fail('AUTH_ORIGIN_MISMATCH');
    const password = args.password_ref ? resolve(args.password_ref) : null;
    const user = args.username_ref ? resolve(args.username_ref) : null;
    const submit = args.submit_ref ? resolve(args.submit_ref) : null;
    if (!password && !user) fail('LOGIN_FIELDS_REQUIRED');
    if (password && !password.matches('input[type="password"]')) fail('AUTH_FIELD_MISMATCH');
    if (user && (!user.matches('input') || sensitive(user))) fail('AUTH_FIELD_MISMATCH');
    for (const el of [password, user, submit].filter(Boolean)) {
      const form = el.form;
      if (form && new URL(form.action || location.href, location.href).origin !== location.origin) fail('AUTH_FORM_ORIGIN_MISMATCH');
      if (el.getAttribute('formaction') && new URL(el.formAction, location.href).origin !== location.origin) fail('AUTH_FORM_ORIGIN_MISMATCH');
    }
    const fill = (el, value) => {
      if (!el) return;
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(el, value);
      el.dispatchEvent(new Event('input', { bubbles: true }));
      el.dispatchEvent(new Event('change', { bubbles: true }));
    };
    fill(user, args.username); fill(password, args.password);
    if (submit) submit.click();
    return { ...base, filled: true, submitted: !!submit, state: 'unknown', verification: 'check_destination' };
  }
  if (op === 'wait') {
    const found = args.ref ? visible(resolve(args.ref)) : args.text ? document.body?.innerText.includes(args.text) : document.readyState === 'complete';
    return { ...base, matched: !!found };
  }
  if (op === 'scroll') {
    scrollBy(0, args.direction === 'up' ? -innerHeight * .8 : innerHeight * .8);
    return base;
  }
  const el = resolve(args.ref);
  if (el.disabled) fail('ELEMENT_DISABLED');
  if (op === 'click') el.click();
  else if (op === 'type') {
    if (sensitive(el)) fail('USE_AUTH_FOR_PROTECTED_INPUT');
    if (!el.matches('input,textarea')) fail('UNSUPPORTED_INPUT');
    const proto = el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, String(args.text ?? ''));
    el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true }));
    if (args.submit) el.form?.requestSubmit();
  } else if (op === 'check') {
    if (!el.matches('input[type="checkbox"],input[type="radio"]')) fail('UNSUPPORTED_INPUT');
    if (el.checked !== (args.checked !== false)) el.click();
  } else if (op === 'select') {
    if (el.tagName !== 'SELECT') fail('UNSUPPORTED_INPUT');
    const option = [...el.options].find(o => args.label != null ? o.text === args.label : o.value === args.value);
    if (!option) fail('OPTION_NOT_FOUND');
    el.value = option.value; el.dispatchEvent(new Event('change', { bubbles: true }));
  } else if (op === 'focus') {
    if (sensitive(el)) fail('USE_AUTH_FOR_PROTECTED_INPUT');
    el.focus();
  } else fail('UNSUPPORTED_OPERATION');
  return { ...base, verification: 'interaction_only' };
}

export function expression(op, args) {
  if (op === 'google_results') return `(${captureGoogleResults.toString()})()`;
  return `(${pageOperation.toString()})(${JSON.stringify(op)},${JSON.stringify(args)})`;
}
