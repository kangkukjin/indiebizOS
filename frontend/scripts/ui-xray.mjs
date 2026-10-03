import ts from 'typescript';
import { korean, compileHTML } from './ui-compiler.mjs';
import { staticValues } from './ui-static-values.mjs';

/** X-Ray is an explicitly owned UI source. Keys/comparisons and runtime values stay literal. */
export function compileXray(html, catalog) {
  const textCall = (source, escape = false) => {
    const id = catalog.add('xray:ui', source);
    const call = `window.__ui.text(${JSON.stringify(id)})`;
    return escape ? `escHtml(${call})` : call;
  };
  function fragment(value, expressions = []) {
    const slots = /__XR_SLOT_(\d+)__/g;
    const parts = [];
    const append = (text, translate = false) => {
      let start = 0;
      for (const match of text.matchAll(slots)) {
        literal(text.slice(start, match.index), translate);
        parts.push(`(${expressions[Number(match[1])]})`);
        start = match.index + match[0].length;
      }
      literal(text.slice(start), translate);
    };
    const literal = (text, translate) => {
      if (!text) return;
      parts.push(translate && korean(text) ? textCall(text, true) : JSON.stringify(text));
    };
    const blocked = [];
    for (const match of value.matchAll(/<!--[\s\S]*?-->|<[^>]*>|[^<]+|</g)) {
      const token = match[0];
      if (token.startsWith('<!--')) { append(token); continue; }
      if (token.startsWith('<')) {
        const tag = token.match(/^<\/?([\w-]+)/)?.[1]?.toLowerCase();
        if (token.startsWith('</')) {
          if (blocked.at(-1) === tag) blocked.pop();
        } else if (['style', 'script', 'pre', 'code', 'textarea'].includes(tag)) blocked.push(tag);
        // Only display attributes; event handlers and API identifiers are untouched.
        let start = 0;
        for (const attr of token.matchAll(/\b(?:title|placeholder|aria-label|alt)=("[^"]*"|'[^']*')/g)) {
          const offset = attr.index + attr[0].indexOf('=') + 2;
          append(token.slice(start, offset));
          append(attr[1].slice(1, -1), !blocked.length);
          start = offset + attr[1].length - 2;
        }
        append(token.slice(start));
      } else append(token, !blocked.length);
    }
    return ['""', ...parts].join(' + ');
  }
  function script(source) {
    const ast = ts.createSourceFile('xray.js', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.JS);
    const finite = staticValues(ast);
    function display(node) {
      const values = finite(node);
      if (!values?.some(korean) || values.some(value => /<\/?[a-z]/i.test(value))) return render(node);
      const choices = Object.fromEntries(values.filter(korean).map(value => [value, catalog.add('xray:ui', value)]));
      return `((value)=>{const choices=${JSON.stringify(choices)};return Object.hasOwn(choices,value)?escHtml(window.__ui.text(choices[value])):value;})(${node.getText(ast)})`;
    }
    function render(node) {
      if (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) {
        if (!korean(node.text)) return node.getText(ast);
        const parent = node.parent;
        const isKey = ts.isPropertyAssignment(parent) ||
          (ts.isElementAccessExpression(parent) && parent.argumentExpression === node) ||
          (ts.isBinaryExpression(parent) && [ts.SyntaxKind.EqualsEqualsEqualsToken, ts.SyntaxKind.ExclamationEqualsEqualsToken, ts.SyntaxKind.EqualsEqualsToken, ts.SyntaxKind.ExclamationEqualsToken].includes(parent.operatorToken.kind));
        let owner = parent;
        while (owner && !ts.isFunctionLike(owner)) owner = owner.parent;
        // Top-level dictionaries retain source values; explicit system display translates them.
        if (!owner) {
          if (!(ts.isPropertyAssignment(parent) && parent.name === node)) catalog.add('system:metadata', node.text);
          return node.getText(ast);
        }
        if (isKey) return node.getText(ast);
        return /<\/?[a-z]/i.test(node.text) ? fragment(node.text) : textCall(node.text);
      }
      if (ts.isTemplateExpression(node)) {
        const expressions = node.templateSpans.map(span => display(span.expression));
        let value = node.head.text;
        node.templateSpans.forEach((span, i) => { value += `__XR_SLOT_${i}__` + span.literal.text; });
        return '(' + fragment(value, expressions) + ')';
      }
      const edits = [];
      ts.forEachChild(node, child => {
        const original = child.getText(ast), next = render(child);
        if (next !== original) edits.push({start: child.getStart(ast), end: child.end, next});
      });
      let result = source.slice(node.getStart(ast), node.end);
      for (const edit of edits.reverse()) {
        const start = node.getStart(ast);
        result = result.slice(0, edit.start - start) + edit.next + result.slice(edit.end - start);
      }
      return result;
    }
    return render(ast);
  }
  const scripts = [];
  const shell = html.replace(/(<script\b[^>]*>)([\s\S]*?)(<\/script>)/gi, (_, open, body, close) => {
    scripts.push(open + script(body) + close);
    return `<!--XR_SCRIPT_${scripts.length - 1}-->`;
  });
  return compileHTML(shell, 'xray:shell', catalog).replace(/<!--XR_SCRIPT_(\d+)-->/g, (_, i) => scripts[Number(i)]);
}
