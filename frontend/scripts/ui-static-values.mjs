import ts from 'typescript';

/** Resolve only finite, source-owned values at display sinks. Unknown data is never translated.
 * Bindings are lexical, including map callbacks; ids/keys/values are never rewritten.
 */
export function staticValues(ast) {
  const host = {getSourceFile: name => name === ast.fileName ? ast : undefined,
    getDefaultLibFileName: () => '', writeFile() {}, getCurrentDirectory: () => '',
    getDirectories: () => [], fileExists: name => name === ast.fileName,
    readFile: () => undefined, getCanonicalFileName: name => name,
    useCaseSensitiveFileNames: () => true, getNewLine: () => '\n'};
  const checker = ts.createProgram([ast.fileName], {noLib:true, allowJs:true}, host).getTypeChecker();
  const all = (parts) => parts.some(p => !p) ? undefined : parts.flat();
  const key = n => ts.isIdentifier(n) || ts.isStringLiteral(n) || ts.isNumericLiteral(n) ? n.text : undefined;
  function pick(nodes, keys, seen) {
    if (!nodes) return;
    return all(nodes.map(n => {
      if (ts.isObjectLiteralExpression(n)) {
        if (n.properties.some(ts.isSpreadAssignment)) return;
        const props = n.properties.filter(p => ts.isPropertyAssignment(p) || ts.isShorthandPropertyAssignment(p));
        const selected = keys ? keys.map(k => props.find(p => key(p.name) === k)) : props;
        if (!selected.length || selected.some(p => !p)) return;
        return all(selected.map(p => resolve(p.initializer || p.name, new Set(seen))));
      }
      if (ts.isArrayLiteralExpression(n)) {
        if (n.elements.some(ts.isSpreadElement)) return;
        const selected = keys ? keys.map(k => n.elements[Number(k)]) : [...n.elements];
        if (selected.some(p => !p)) return;
        return all(selected.map(p => resolve(p, new Set(seen))));
      }
    }));
  }
  function binding(decl, seen) {
    if (ts.isVariableDeclaration(decl)) {
      // Mutable bindings may contain user/API data by the time they are displayed.
      if (!(decl.parent.flags & ts.NodeFlags.Const)) return;
      return resolve(decl.initializer, seen);
    }
    if (ts.isParameter(decl)) {
      const fn = decl.parent, call = fn.parent;
      if (!ts.isCallExpression(call) || !ts.isPropertyAccessExpression(call.expression) || !['map','flatMap','forEach','filter','find'].includes(call.expression.name.text) || fn.parameters[0] !== decl) return;
      return pick(resolve(call.expression.expression, seen), undefined, seen);
    }
    if (ts.isBindingElement(decl)) {
      const pattern = decl.parent, owner = pattern.parent;
      const base = binding(owner, seen);
      return pick(base, [ts.isArrayBindingPattern(pattern) ? String(pattern.elements.indexOf(decl)) : key(decl.propertyName || decl.name)], seen);
    }
  }
  function resolve(n, seen = new Set()) {
    if (!n || seen.has(n)) return;
    seen.add(n);
    if (ts.isStringLiteral(n) || ts.isNoSubstitutionTemplateLiteral(n) || ts.isNumericLiteral(n) || ts.isObjectLiteralExpression(n) || ts.isArrayLiteralExpression(n)) return [n];
    if (ts.isParenthesizedExpression(n) || ts.isAsExpression(n) || ts.isSatisfiesExpression(n) || ts.isNonNullExpression(n)) return resolve(n.expression, seen);
    if (ts.isIdentifier(n)) {
      const decl = checker.getSymbolAtLocation(n)?.valueDeclaration;
      return decl && binding(decl, seen);
    }
    if (ts.isCallExpression(n)) {
      const method = ts.isPropertyAccessExpression(n.expression) ? n.expression.name.text : '';
      const receiver = ts.isPropertyAccessExpression(n.expression) ? n.expression.expression : undefined;
      if (['filter','slice'].includes(method)) return resolve(receiver, seen);
      if (['find','at'].includes(method)) return pick(resolve(receiver, seen), undefined, seen);
      if (['map','flatMap'].includes(method)) {
        const fn = n.arguments[0];
        if (!fn || !ts.isArrowFunction(fn) && !ts.isFunctionExpression(fn)) return;
        const body = ts.isBlock(fn.body) ? fn.body.statements.find(ts.isReturnStatement)?.expression : fn.body;
        const results = resolve(body, seen);
        if (!results) return;
        const elements = method === 'flatMap' ? all(results.map(r => ts.isArrayLiteralExpression(r) ? [...r.elements] : [r])) : results;
        return elements && [ts.factory.createArrayLiteralExpression(elements)];
      }
      if (receiver?.getText(ast) === 'Object' && ['keys','values'].includes(method)) {
        const objects = resolve(n.arguments[0], seen);
        if (!objects?.every(ts.isObjectLiteralExpression)) return;
        if (method === 'values') return [ts.factory.createArrayLiteralExpression(pick(objects, undefined, seen) || [])];
        const names = objects.flatMap(o => o.properties.map(p => key(p.name)));
        if (names.some(k => k === undefined)) return;
        return [ts.factory.createArrayLiteralExpression(names.map(k => ts.factory.createStringLiteral(k)))];
      }
    }
    if (ts.isPropertyAccessExpression(n)) return pick(resolve(n.expression, seen), [n.name.text], seen);
    if (ts.isElementAccessExpression(n)) {
      const index = resolve(n.argumentExpression, new Set(seen));
      const keys = index?.every(v => ts.isStringLiteral(v) || ts.isNumericLiteral(v)) ? index.map(v => v.text) : undefined;
      return pick(resolve(n.expression, seen), keys, seen);
    }
    if (ts.isBinaryExpression(n) && [ts.SyntaxKind.QuestionQuestionToken, ts.SyntaxKind.BarBarToken].includes(n.operatorToken.kind)) return all([resolve(n.left, new Set(seen)), resolve(n.right, new Set(seen))]);
    if (ts.isConditionalExpression(n)) return all([resolve(n.whenTrue, new Set(seen)), resolve(n.whenFalse, new Set(seen))]);
  }
  return node => {
    const nodes = resolve(node);
    if (!nodes?.length || nodes.some(n => !ts.isStringLiteral(n) && !ts.isNoSubstitutionTemplateLiteral(n))) return;
    return [...new Set(nodes.map(n => n.text))];
  };
}
