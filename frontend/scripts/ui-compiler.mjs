import ts from 'typescript';
import { createHash } from 'node:crypto';

export const korean = text => /[가-힣]/.test(text);
export const messageId = (context, source) => createHash('sha256').update(context + '\0' + source).digest('hex').slice(0, 20);
export function collector() {
  const messages = {};
  return { messages, add(context, source) {
    const id = messageId(context, source);
    messages[id] = { source, context };
    return id;
  } };
}
function apply(source, edits) {
  for (const { start, end, text } of edits.sort((a, b) => b.start - a.start)) source = source.slice(0, start) + text + source.slice(end);
  return source;
}
const json = JSON.stringify;
const attrs = new Set(['title', 'placeholder', 'aria-label', 'alt']);
const noText = new Set(['script', 'style', 'code', 'pre', 'textarea']);
function jsxText(text) {
  const lines = text.replace(/\r/g, '').split('\n');
  return lines.map((line, i) => {
    line = line.replace(/\t/g, ' ');
    if (i) line = line.replace(/^ +/, '');
    if (i < lines.length - 1) line = line.replace(/ +$/, '');
    return line;
  }).filter(Boolean).join(' ');
}
export function compileReact(source, file, catalog) {
  const ast = ts.createSourceFile(file, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const edits = [];
  let used = false;
  const edit = (node, text) => edits.push({ start: node.getStart(ast), end: node.end, text });
  function expression(node, context) {
    if (!node) return;
    if ((ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) && korean(node.text)) {
      edit(node, `<__UiText id=${json(catalog.add(context, node.text))} />`); used = true;
    } else if (ts.isTemplateExpression(node) && korean(node.getText(ast))) {
      let text = node.head.text;
      const values = [];
      for (const span of node.templateSpans) { text += `{${values.length}}` + span.literal.text; values.push(span.expression.getText(ast)); }
      if (korean(text)) { edit(node, `<__UiText id=${json(catalog.add(context, text))} values={[${values.join(',')}]} />`); used = true; }
    } else if (ts.isConditionalExpression(node)) {
      expression(node.whenTrue, context); expression(node.whenFalse, context);
    } else if (ts.isBinaryExpression(node) && [ts.SyntaxKind.AmpersandAmpersandToken, ts.SyntaxKind.BarBarToken, ts.SyntaxKind.QuestionQuestionToken].includes(node.operatorToken.kind)) {
      expression(node.right, context);
    } else if (ts.isParenthesizedExpression(node)) expression(node.expression, context);
  }
  function walk(node, blocked = false) {
    if (ts.isCallExpression(node) && node.expression.getText(ast) === 'uiMessage' && node.arguments.length === 2 && node.arguments.every(ts.isStringLiteral)) {
      edit(node, json(catalog.add(node.arguments[0].text, node.arguments[1].text))); return;
    }
    if (ts.isJsxElement(node) || ts.isJsxSelfClosingElement(node)) {
      const opening = ts.isJsxElement(node) ? node.openingElement : node;
      const tag = opening.tagName.getText(ast);
      const excluded = opening.attributes.properties.some(a => ts.isJsxAttribute(a) &&
        (a.name.getText(ast) === 'data-ui-skip' || a.name.getText(ast) === 'translate' && a.initializer?.text === 'no'));
      const skip = blocked || excluded;
      const messages = {};
      if (!skip && /^[a-z]/.test(tag)) {
        for (const attr of opening.attributes.properties) {
          if (!ts.isJsxAttribute(attr)) continue;
          const name = attr.name.getText(ast);
          if (attrs.has(name) && attr.initializer && ts.isStringLiteral(attr.initializer) && korean(attr.initializer.text)) {
            messages[name] = catalog.add(`${file}:${tag}@${name}`, attr.initializer.text);
          }
        }
      }
      if (Object.keys(messages).length) {
        edit(opening.tagName, `__UiElement as=${json(tag)} uiAttrs={${json(messages)}}`);
        if (ts.isJsxElement(node)) edit(node.closingElement.tagName, '__UiElement');
        used = true;
      }
      if (ts.isJsxElement(node)) {
        for (const child of node.children) {
          if (!skip && !noText.has(tag) && ts.isJsxText(child)) {
            const text = decodeHTML(jsxText(child.text));
            if (korean(text)) { edits.push({ start: child.pos, end: child.end, text: `<__UiText id=${json(catalog.add(`${file}:${tag}`, text))} />` }); used = true; }
          } else if (!skip && !noText.has(tag) && ts.isJsxExpression(child)) {
            expression(child.expression, `${file}:${tag}`);
            // Visit JSX nested in conditional branches, but not its literal expressions twice.
            function nested(n) { if (ts.isJsxElement(n) || ts.isJsxSelfClosingElement(n)) walk(n, skip); else ts.forEachChild(n, nested); }
            if (child.expression) nested(child.expression);
          } else if (!ts.isJsxText(child)) walk(child, skip || noText.has(tag));
        }
      }
      return;
    }
    ts.forEachChild(node, n => walk(n, blocked));
  }
  walk(ast);
  const output = apply(source, edits);
  return used ? `import { UiText as __UiText, UiElement as __UiElement } from '/src/i18n/ui';\n${output}` : output;
}

// Only source-code HTML text/attributes are annotated. No runtime data enters this compiler.
export function compileHTML(html, context, catalog) {
  const stack = [];
  const voids = new Set(['area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr']);
  return html.replace(/<!--[\s\S]*?-->|<[^>]*>|[^<]+/g, token => {
    if (token.startsWith('<!--')) return token;
    if (token.startsWith('<')) {
      const tag = token.match(/^<\/?([\w-]+)/)?.[1]?.toLowerCase();
      if (!tag) return token;
      if (token.startsWith('</')) { const index = stack.map(e => e.tag).lastIndexOf(tag); if (index >= 0) stack.splice(index); return token; }
      const excluded = !!stack.at(-1)?.blocked || /\btranslate\s*=\s*["']no["']|\bdata-ui-skip\b/i.test(token);
      const blocked = excluded || noText.has(tag) || /class=["'][^"']*\babout-code\b/.test(token);
      if (!voids.has(tag) && !token.endsWith('/>')) stack.push({tag, blocked});
      if (excluded) return token;
      return token.replace(/\b(title|placeholder|aria-label|alt)=("[^"]*"|'[^']*')/g, (full, attr, quoted) => {
        const value = quoted.slice(1, -1);
        if (!korean(value)) return full;
        return `${full} data-ui-${attr}="${catalog.add(`${context}@${attr}`, decodeHTML(value))}"`;
      });
    }
    if (stack.at(-1)?.blocked || !korean(token)) return token;
    const id = catalog.add(`${context}:text`, decodeHTML(token));
    // option/title cannot contain spans: handled by a post-pass on complete source elements.
    if (['option','title'].includes(stack.at(-1)?.tag)) return `__UI_OPTION_${id}__${token}`;
    return `<span data-ui-text="${id}">${token}</span>`;
  }).replace(/<(option|title)([^>]*)>__UI_OPTION_([a-f0-9]+)__([^<]*)<\/\1>/g,
    (_,tag,attributes,id,value) => `<${tag}${attributes} data-ui-text="${id}">${value}</${tag}>`);
}
function decodeHTML(text) {
  return text.replace(/&(amp|lt|gt|quot|apos|nbsp);/g, (_, name) => ({ amp: '&', lt: '<', gt: '>', quot: '"', apos: "'", nbsp: '\u00a0' })[name])
    .replace(/&#(x[\da-f]+|\d+);/gi, (_, number) => String.fromCodePoint(number[0].toLowerCase() === 'x' ? parseInt(number.slice(1), 16) : Number(number)));
}
export function compileRemoteJS(source, catalog) {
  const ast = ts.createSourceFile('remote.js', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.JS);
  const edits = [];
  function walk(node) {
    if (ts.isCallExpression(node) && node.expression.getText(ast) === 'esc' && ['nm', 'ds'].includes(node.arguments[0]?.getText(ast))) {
      let owner = node.parent;
      while (owner && !ts.isFunctionDeclaration(owner)) owner = owner.parent;
      if (owner?.name?.text === 'apCard') { edits.push({start:node.getStart(ast),end:node.end,text:`window.__uiContent(${node.arguments[0].getText(ast)})`}); return; }
    }
    if (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) {
      const value = node.text;
      if (!korean(value)) return;
      const parent = node.parent;
      if (ts.isCallExpression(parent)) {
        const name = parent.expression.getText(ast), index = parent.arguments.indexOf(node);
        if ((name === 'apCard' && [1,2].includes(index)) || (['alert','prompt','confirm'].includes(name) && index === 0)) {
          const id = catalog.add(`remote:call:${name}:${index}`,value);
          edits.push({start:node.getStart(ast),end:node.end,text:name === 'apCard' ? `{ui:${json(id)}}` : `window.__ui.text(${json(id)})`}); return;
        }
      }
      if (/<[a-z][\s\S]*>/i.test(value)) {
        if (/<(?:pre|code|textarea)\b|\bdata-ui-skip\b|\btranslate=["']no["']/i.test(value)) return;
        // Only fully bounded text in HTML fragments; never translate concatenated data or HTML attribute fragments.
        const bounded = value.replace(/(<(?:h[1-6]|button|span|label|p|div)\b[^>]*>)([^<>]*[가-힣][^<>]*)$/gi, (_,tag,text) => `${tag}<span data-ui-text="${catalog.add('remote:dynamic',decodeHTML(text))}">${text}</span>`);
        const next = bounded.replace(/(>)([^<>]*[가-힣][^<>]*)(<)/g, (all, left, text, right) => {
          if (/[{}]|\bfunction\b/.test(text)) return all;
          return `${left}<span data-ui-text="${catalog.add('remote:dynamic', decodeHTML(text))}">${text}</span>${right}`;
        }).replace(/\b(title|placeholder|aria-label|alt)=("[^"]*"|'[^']*')/g, (full, attr, quoted) => korean(quoted) ? `${full} data-ui-${attr}="${catalog.add(`remote:dynamic@${attr}`, decodeHTML(quoted.slice(1, -1)))}"` : full);
        if (next !== value) edits.push({ start: node.getStart(ast), end: node.end, text: json(next) });
      } else if (ts.isBinaryExpression(node.parent) && node.parent.right === node && node.parent.operatorToken.kind === ts.SyntaxKind.EqualsToken && ts.isPropertyAccessExpression(node.parent.left) && node.parent.left.name.text === 'textContent') {
        // span marker is removed naturally if later code replaces the parent's content with runtime data.
        const target = node.parent.left.expression.getText(ast);
        const id = catalog.add('remote:status', value);
        edits.push({ start: node.parent.getStart(ast), end: node.parent.end, text: `window.__uiSetText(${target},${json(id)})` });
      }
      return;
    }
    ts.forEachChild(node, walk);
  }
  walk(ast);
  return apply(source, edits);
}
