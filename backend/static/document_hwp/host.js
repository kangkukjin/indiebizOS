// 본 제품은 한컴의 HWP 문서 파일(.hwp) 공개 문서를 참고하여 개발하였습니다.
// The HTTP host also supports Electron's file: parent (the SDK itself cannot).
import { createStudio } from './sdk/index.js';
const channel = new URLSearchParams(location.search).get('channel');
let parentOrigin, studio, composing = false;
const send = value => parent.postMessage({ channel, ...value }, parentOrigin === 'null' ? '*' : parentOrigin);
const same = (a, b) => a.documentEpoch === b.documentEpoch && a.changeSeq === b.changeSeq && a.documentSha256 === b.documentSha256;
const ready = createStudio('#editor', { studioUrl: new URL('./index.html', location.href).href, plugins: ['hwpctrl'] }).then(value => {
  studio = value;
  const doc = studio.element.contentDocument;
  // Document identity belongs to the workspace. Keep formatting/table menus.
  doc.querySelectorAll('[data-cmd="file:open"], [data-cmd="file:new-doc"], [data-cmd="file:save-as"]').forEach(el => el.remove());
  doc.addEventListener('compositionstart', () => { composing = true; }, true);
  doc.addEventListener('compositionend', () => { composing = false; }, true);
  doc.addEventListener('keydown', event => {
    if (!(event.ctrlKey || event.metaKey)) return;
    if (['s', 'o', 'n'].includes(event.key.toLowerCase())) {
      event.preventDefault(); event.stopImmediatePropagation();
      if (event.key.toLowerCase() === 's') send({ event: 'save' });
    }
  }, true);
  const style = doc.createElement('style');
  style.textContent = '#recent-files-section,[data-cmd="file:open-recent"]{display:none!important}';
  doc.head.appendChild(style);
  doc.addEventListener('click', event => {
    if (event.target.closest?.('[data-cmd="file:open-recent"], [data-cmd="file:open"], [data-cmd="file:new-doc"]')) {
      event.preventDefault(); event.stopImmediatePropagation(); return;
    }
    if (event.target.closest?.('[data-cmd="file:save"]')) {
      event.preventDefault(); event.stopImmediatePropagation(); send({ event: 'save' });
    }
  }, true);
  doc.addEventListener('drop', event => {
    if (event.dataTransfer?.files.length) { event.preventDefault(); event.stopImmediatePropagation(); }
  }, true);
  return studio;
});
ready.catch(error => { document.getElementById('error').textContent = String(error); });
let chain = Promise.resolve();
window.addEventListener('message', event => {
  if (event.source !== parent || event.data?.channel !== channel || !event.data.id) return;
  if (parentOrigin === undefined) parentOrigin = event.origin;
  if (event.origin !== parentOrigin) return;
  const { id, op, args } = event.data;
  chain = chain.catch(() => {}).then(async () => {
    try {
      await ready;
      let result;
      if (op === 'load') {
        result = await studio.loadFile(args.data, args.filename);
      } else if (op === 'state') {
        result = await studio.getDocumentState();
      } else if (op === 'export') {
        if (composing) throw new Error('한글 입력 조합이 끝난 뒤 저장하세요');
        const before = await studio.getDocumentState();
        const data = args.format === 'hwpx' ? await studio.exportHwpx() : await studio.exportHwp();
        const after = await studio.getDocumentState();
        if (!same(before, after)) throw new Error('저장 중 편집이 계속되었습니다. 다시 저장하세요');
        result = { data, state: after };
      } else if (op === 'ack') {
        const state = await studio.getDocumentState();
        if (!same(state, args.state)) throw new Error('새 편집 내용이 남아 있습니다');
        result = await studio.notifySaved();
      } else {
        throw new Error('지원하지 않는 편집기 요청입니다');
      }
      send({ id, result });
    } catch (error) { send({ id, error: String(error) }); }
  });
});
