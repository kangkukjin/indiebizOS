/**
 * BinNote (빈노트) — 워드/파워포인트처럼 넓은 편집 캔버스를 주는 문서 앱.
 *
 * 프로젝트 에이전트 대화창의 입력창은 작다. 빈노트는 그 반대 —
 * 화면 대부분을 빈 캔버스로 내주고 사용자가 마음껏 글을 쓴다.
 *   · 큰 텍스트 캔버스 (자동 로컬 임시저장으로 실수 방지)
 *   · 파일로 저장 / 불러오기 / 다른 이름으로 (projects/앱모드/outputs/binnote/**)
 *   · 폴더 트리 — 폴더를 만들고, 열고 닫으며 이동. 저장은 "지금 있는 폴더(cwd)"에.
 *     (헤더의 폴더칩이 저장 위치를 늘 보여줘 "어디 저장됐지?" 를 없앤다.)
 *   · 이름 필터 — 폴더 정리에 의존하지 않고도 노트를 즉석에서 좁혀 찾는다(폴더의 보완).
 *   · 하단 AI 대화창 — 현재 글을 통째로 맥락으로 넘겨 "개선해줘",
 *     "다른 형식(pdf·docx)으로 저장해줘" 같은 지시를 시스템 AI에게.
 *
 * 앱 모드 안의 인라인 계기(el) — 신문·길찾기처럼 메인 창 안에서 열리고 상단 '‹ 뒤로'로 나간다
 * (별도 창 아님 — 갇힘 방지). 저장·불러오기·폴더조작은 IBL [self:write/read/list/delete/mkdir], AI는 /system-ai/chat.
 *
 * 폴더 생성: [self:mkdir] 로 빈 폴더를 만든다(중간 경로 자동 생성·멱등).
 * 목록에서 점(.)으로 시작하는 항목은 감춘다(과거 .keep 잔여 등).
 */
import { useState, useEffect, useRef, useCallback } from 'react';
import { FileText, Save, FolderOpen, FolderPlus, Folder, ChevronRight, FilePlus2, Send, Sparkles, X, Trash2, ArrowDownToLine } from 'lucide-react';
// 앱 모드 계기 공용 헬퍼 — project_id:'앱모드' 내장 IBL 호출 + 시스템 AI 동기 대화.
import { iblExecuteApp, askSystemAI } from '../lib/instrument';

// 저장 루트(상대). 앱모드 컨텍스트에서 projects/앱모드/outputs/binnote/ 로 해소된다.
const NOTE_DIR = 'outputs/binnote';
const DRAFT_KEY = 'binnote.draft';
const NAME_KEY = 'binnote.name';
const CWD_KEY = 'binnote.cwd';   // 현재 폴더(루트 기준 하위 경로, '' = 루트)

// 목록 한 항목(폴더 또는 노트).
interface Entry { name: string; meta: string; isDir: boolean }
interface ChatMsg { role: 'user' | 'ai'; text: string }

// 파일명 정리 — 확장자 없으면 .md, 위험문자 제거.
function normalizeName(raw: string): string {
  let n = raw.trim().replace(/[\\/:*?"<>|]/g, '').slice(0, 80);
  if (!n) n = '제목없음';
  if (!/\.(md|txt)$/i.test(n)) n += '.md';
  return n;
}
// 폴더명 정리 — 위험문자·슬래시 제거.
function normalizeFolder(raw: string): string {
  return raw.trim().replace(/[\\/:*?"<>|]/g, '').slice(0, 60);
}

export function BinNote() {
  const [name, setName] = useState<string>(() => localStorage.getItem(NAME_KEY) || '제목없음.md');
  const [content, setContent] = useState<string>(() => localStorage.getItem(DRAFT_KEY) || '');
  const [cwd, setCwd] = useState<string>(() => localStorage.getItem(CWD_KEY) || '');
  const [dirty, setDirty] = useState(false);
  const [status, setStatus] = useState<string>('');

  // 폴더 브라우저(불러오기/이동) 모달
  const [listOpen, setListOpen] = useState(false);
  const [entries, setEntries] = useState<Entry[]>([]);
  const [filter, setFilter] = useState('');

  // AI 대화창
  const [chat, setChat] = useState<ChatMsg[]>([]);
  const [aiInput, setAiInput] = useState('');
  const [aiBusy, setAiBusy] = useState(false);
  const chatEndRef = useRef<HTMLDivElement | null>(null);

  // 자동 임시저장 — 창을 잘못 닫아도 작업이 날아가지 않게.
  useEffect(() => { localStorage.setItem(DRAFT_KEY, content); }, [content]);
  useEffect(() => { localStorage.setItem(NAME_KEY, name); }, [name]);
  useEffect(() => { localStorage.setItem(CWD_KEY, cwd); }, [cwd]);
  useEffect(() => { chatEndRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [chat, aiBusy]);

  const flashStatus = (msg: string) => { setStatus(msg); window.setTimeout(() => setStatus(''), 3000); };

  // cwd(하위경로) → 실제 디렉토리 경로. 루트면 NOTE_DIR 그대로 (기존 평면 노트 회귀 없음).
  const dirOf = (sub: string) => (sub ? `${NOTE_DIR}/${sub}` : NOTE_DIR);
  const label = (sub: string) => (sub ? `빈노트 / ${sub.replace(/\//g, ' / ')}` : '빈노트');

  // ── 폴더 열람(이동) ───────────────────────────────────
  // 브라우저의 현재 폴더 = 작업 폴더(cwd). 여기로 저장되고, 여기서 불러온다.
  const browse = useCallback(async (sub: string) => {
    setCwd(sub);
    setFilter('');
    try {
      const r = await iblExecuteApp(`[self:list]{path: ${JSON.stringify(dirOf(sub))}}`);
      const items = (r as { items?: Array<{ title?: string; meta?: string }> })?.items ?? [];
      const es: Entry[] = items
        .map((it) => {
          const raw = it.title ?? '';
          const meta = it.meta ?? '';
          const isDir = raw.endsWith('/') || meta.startsWith('디렉');
          return { name: raw.replace(/\/$/, ''), meta, isDir };
        })
        // 숨김 플레이스홀더(.keep 등) 감추고, 폴더 + 노트(.md/.txt)만 보인다.
        .filter((e) => !e.name.startsWith('.'))
        .filter((e) => e.isDir || /\.(md|txt)$/i.test(e.name))
        // 폴더 먼저, 그 안에서 이름순.
        .sort((a, b) => (a.isDir === b.isDir ? a.name.localeCompare(b.name) : a.isDir ? -1 : 1));
      setEntries(es);
    } catch {
      // 폴더가 아직 없거나(에러) 비었으면 빈 목록. 저장 시 자동 생성되므로 무해.
      setEntries([]);
    }
  }, []);

  const openList = useCallback(() => { setListOpen(true); browse(cwd); }, [cwd, browse]);

  // ── 새 폴더 ──────────────────────────────────────────
  const makeFolder = useCallback(async () => {
    const raw = window.prompt('새 폴더 이름 (현재 폴더 안에 생성됩니다)');
    if (raw == null) return;
    const fn = normalizeFolder(raw);
    if (!fn) return;
    const sub = cwd ? `${cwd}/${fn}` : fn;
    setStatus('폴더 만드는 중…');
    await iblExecuteApp(`[self:mkdir]{path: ${JSON.stringify(dirOf(sub))}}`);
    flashStatus(`폴더 생성 · ${fn}`);
    browse(cwd);
  }, [cwd, browse]);

  // ── 저장 (현재 폴더 cwd 에) ───────────────────────────
  const save = useCallback(async (saveAs = false) => {
    let fname = name;
    if (saveAs) {
      const input = window.prompt(`'${label(cwd)}' 에 저장할 파일명`, name);
      if (!input) return;
      fname = normalizeName(input);
      setName(fname);
    } else {
      fname = normalizeName(name);
      if (fname !== name) setName(fname);
    }
    setStatus('저장 중…');
    try {
      const r = await iblExecuteApp(
        `[self:write]{path: ${JSON.stringify(`${dirOf(cwd)}/${fname}`)}, content: ${JSON.stringify(content)}}`
      );
      if (r && typeof r === 'object' && (r as { success?: boolean }).success) {
        setDirty(false);
        flashStatus(`저장됨 · ${cwd ? cwd + '/' : ''}${fname}`);
      } else {
        flashStatus('저장 실패');
      }
    } catch {
      flashStatus('저장 실패 (연결 확인)');
    }
  }, [name, content, cwd]);

  // ── 불러오기 / 삭제 (현재 폴더 기준) ──────────────────
  const loadNote = useCallback(async (fileName: string) => {
    if (dirty && !window.confirm('저장하지 않은 변경이 있습니다. 계속 불러올까요?')) return;
    try {
      const r = await iblExecuteApp(`[self:read]{path: ${JSON.stringify(`${dirOf(cwd)}/${fileName}`)}}`);
      // read 는 {result: "text"} 또는 {text: "..."} 또는 문자열 로 온다.
      let text = '';
      if (typeof r === 'string') text = r;
      else if (r && typeof r === 'object') {
        const o = r as { result?: unknown; text?: unknown };
        text = String(o.result ?? o.text ?? '');
      }
      setName(fileName);
      setContent(text);
      setDirty(false);
      setListOpen(false);
      flashStatus(`불러옴 · ${cwd ? cwd + '/' : ''}${fileName}`);
    } catch {
      flashStatus('불러오기 실패');
    }
  }, [dirty, cwd]);

  const delEntry = useCallback(async (e: Entry, ev: React.MouseEvent) => {
    ev.stopPropagation();
    const msg = e.isDir
      ? `폴더 '${e.name}' 와(과) 그 안의 모든 노트를 삭제할까요?`
      : `'${e.name}' 을(를) 삭제할까요?`;
    if (!window.confirm(msg)) return;
    await iblExecuteApp(`[self:delete]{path: ${JSON.stringify(`${dirOf(cwd)}/${e.name}`)}}`);
    browse(cwd);
  }, [cwd, browse]);

  const newNote = useCallback(() => {
    if (dirty && !window.confirm('저장하지 않은 변경이 있습니다. 새 문서를 시작할까요?')) return;
    setName('제목없음.md');
    setContent('');
    setDirty(false);
    // cwd 는 유지 — 방금까지 있던 폴더에서 계속 작업.
  }, [dirty]);

  // ── AI 대화 (현재 글을 맥락으로 시스템 AI에게) ──────────
  const askAI = useCallback(async () => {
    const instruction = aiInput.trim();
    if (!instruction || aiBusy) return;
    setChat((c) => [...c, { role: 'user', text: instruction }]);
    setAiInput('');
    setAiBusy(true);
    const saveDir = cwd ? `${NOTE_DIR}/${cwd}` : NOTE_DIR;
    const message =
      `아래는 사용자가 '빈노트' 편집기에서 작성 중인 문서입니다.\n` +
      `문서 파일명: ${name}\n\n----- 문서 시작 -----\n${content || '(빈 문서)'}\n----- 문서 끝 -----\n\n` +
      `사용자 요청: ${instruction}\n\n` +
      `글을 고쳐 달라는 요청이면, 설명 없이 개선된 전체 본문만 답하세요(그대로 캔버스에 반영됩니다). ` +
      `다른 형식(pdf·docx·html 등)으로 저장하라는 요청이면 ${saveDir}/ 아래에 저장하고 저장 경로를 알려주세요.`;
    try {
      const reply = (await askSystemAI(message)) || '(응답 없음)';
      setChat((c) => [...c, { role: 'ai', text: reply }]);
    } catch {
      setChat((c) => [...c, { role: 'ai', text: '⚠️ AI 응답을 받지 못했습니다. 백엔드 연결을 확인하세요.' }]);
    } finally {
      setAiBusy(false);
    }
  }, [aiInput, aiBusy, name, content, cwd]);

  const applyToCanvas = useCallback((text: string) => {
    if (dirty && !window.confirm('현재 캔버스 내용을 AI 결과로 교체할까요?')) return;
    setContent(text);
    setDirty(true);
    flashStatus('AI 결과를 캔버스에 반영했습니다');
  }, [dirty]);

  // Esc: 브라우저 모달이 열려 있으면 닫는다. (앱 모드 나가기는 상단 '‹ 뒤로' BackBar가 담당)
  useEffect(() => {
    if (!listOpen) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setListOpen(false); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [listOpen]);

  const segs = cwd ? cwd.split('/') : [];
  const shown = entries.filter((e) => e.name.toLowerCase().includes(filter.toLowerCase()));

  return (
    <div className="h-full w-full flex flex-col bg-[#F5F1EB] text-stone-800">
      {/* 상단 툴바 */}
      <header className="flex items-center gap-2 px-4 py-2.5 border-b border-stone-200 bg-white/70 backdrop-blur">
        <FileText size={18} className="text-amber-600 shrink-0" />
        <input
          value={name}
          onChange={(e) => { setName(e.target.value); setDirty(true); }}
          className="min-w-0 flex-1 max-w-xs px-2 py-1 rounded-md bg-transparent text-base font-semibold outline-none hover:bg-stone-100 focus:bg-stone-100"
        />
        {/* 폴더칩 — 저장이 어디로 가는지 늘 보인다. 클릭하면 폴더 브라우저. */}
        <button
          onClick={openList}
          title="폴더 이동 / 불러오기"
          className="flex items-center gap-1.5 px-2 py-1 rounded-lg text-xs text-stone-500 hover:bg-stone-100 max-w-[220px]"
        >
          <Folder size={13} className="text-amber-600 shrink-0" />
          <span className="truncate">{label(cwd)}</span>
        </button>
        {dirty && <span className="text-xs text-amber-600 shrink-0">● 저장 안 됨</span>}
        <div className="flex-1" />
        <button onClick={newNote} className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-sm text-stone-600 hover:bg-stone-100">
          <FilePlus2 size={15} /> 새 문서
        </button>
        <button onClick={openList} className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-sm text-stone-600 hover:bg-stone-100">
          <FolderOpen size={15} /> 열기
        </button>
        <button onClick={() => save(true)} className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-sm text-stone-600 hover:bg-stone-100">
          다른 이름으로
        </button>
        <button onClick={() => save(false)} className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-sm font-semibold text-white bg-amber-600 hover:bg-amber-700">
          <Save size={15} /> 저장
        </button>
      </header>

      {status && <div className="px-4 py-1 text-xs text-stone-500 bg-amber-50 border-b border-amber-100">{status}</div>}

      {/* 편집 캔버스 */}
      <div className="flex-1 min-h-0 overflow-auto px-6 py-6 flex justify-center">
        <textarea
          value={content}
          onChange={(e) => { setContent(e.target.value); setDirty(true); }}
          placeholder="여기에 자유롭게 글을 쓰세요…"
          spellCheck={false}
          className="w-full max-w-4xl min-h-full resize-none bg-white rounded-xl shadow-sm border border-stone-200 px-10 py-9 text-[15px] leading-8 outline-none focus:border-amber-300"
          style={{ fontFamily: "'Noto Serif KR', serif" }}
        />
      </div>

      {/* 하단 AI 대화창 */}
      <section className="border-t border-stone-200 bg-white/80 backdrop-blur">
        {chat.length > 0 && (
          <div className="max-h-52 overflow-auto px-4 py-3 space-y-2.5">
            {chat.map((m, i) => (
              <div key={i} className={m.role === 'user' ? 'flex justify-end' : 'flex justify-start'}>
                <div className={
                  'max-w-[80%] rounded-2xl px-3.5 py-2 text-sm whitespace-pre-wrap leading-relaxed ' +
                  (m.role === 'user' ? 'bg-amber-600 text-white' : 'bg-stone-100 text-stone-800')
                }>
                  {m.text}
                  {m.role === 'ai' && m.text.length > 40 && !m.text.startsWith('⚠️') && (
                    <button
                      onClick={() => applyToCanvas(m.text)}
                      className="mt-2 flex items-center gap-1 text-xs font-semibold text-amber-700 hover:underline"
                    >
                      <ArrowDownToLine size={13} /> 캔버스에 반영
                    </button>
                  )}
                </div>
              </div>
            ))}
            {aiBusy && (
              <div className="flex justify-start">
                <div className="rounded-2xl px-3.5 py-2 text-sm bg-stone-100 text-stone-400">AI가 생각 중…</div>
              </div>
            )}
            <div ref={chatEndRef} />
          </div>
        )}
        <div className="flex items-end gap-2 px-4 py-3">
          <Sparkles size={18} className="text-amber-600 shrink-0 mb-2" />
          <textarea
            value={aiInput}
            onChange={(e) => setAiInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); askAI(); } }}
            placeholder="이 글에 대해 AI에게 시키기 — 예: 더 간결하게 고쳐줘 / PDF로 저장해줘  (Enter 전송, Shift+Enter 줄바꿈)"
            rows={1}
            className="flex-1 resize-none max-h-28 px-3 py-2 rounded-xl border border-stone-200 text-sm outline-none focus:border-amber-300 bg-white"
          />
          <button
            onClick={askAI}
            disabled={aiBusy || !aiInput.trim()}
            className="flex items-center gap-1 px-3.5 py-2 rounded-xl text-sm font-semibold text-white bg-amber-600 hover:bg-amber-700 disabled:opacity-40"
          >
            <Send size={15} /> 보내기
          </button>
        </div>
      </section>

      {/* 폴더 브라우저 모달 (불러오기 / 이동 / 새 폴더) */}
      {listOpen && (
        <div className="absolute inset-0 bg-black/30 flex items-center justify-center z-20" onClick={() => setListOpen(false)}>
          <div className="bg-white rounded-2xl shadow-xl w-[560px] max-h-[74vh] flex flex-col overflow-hidden" onClick={(e) => e.stopPropagation()}>
            {/* 헤더: 브레드크럼(열고 닫기) + 새 폴더 + 닫기 */}
            <div className="flex items-center gap-2 px-5 py-3.5 border-b border-stone-200">
              <div className="flex items-center gap-0.5 text-sm min-w-0 flex-1 flex-wrap">
                <button onClick={() => browse('')} className="font-semibold hover:text-amber-700 shrink-0">빈노트</button>
                {segs.map((s, i) => (
                  <span key={i} className="flex items-center gap-0.5 min-w-0">
                    <ChevronRight size={13} className="text-stone-300 shrink-0" />
                    <button
                      onClick={() => browse(segs.slice(0, i + 1).join('/'))}
                      className="hover:text-amber-700 truncate max-w-[140px]"
                    >
                      {s}
                    </button>
                  </span>
                ))}
              </div>
              <button onClick={makeFolder} className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs font-medium text-amber-700 hover:bg-amber-50 shrink-0">
                <FolderPlus size={15} /> 새 폴더
              </button>
              <button onClick={() => setListOpen(false)} className="text-stone-400 hover:text-stone-700 shrink-0"><X size={18} /></button>
            </div>

            {/* 이름 필터 — 폴더 정리에 기대지 않고도 즉석에서 좁혀 찾기 */}
            <div className="px-4 pt-3">
              <input
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
                placeholder="이 폴더에서 이름으로 찾기…"
                className="w-full px-3 py-1.5 rounded-lg border border-stone-200 text-sm outline-none focus:border-amber-300"
              />
            </div>

            <div className="flex-1 overflow-auto p-3">
              {shown.length === 0 ? (
                <div className="text-center text-sm text-stone-400 py-10">
                  {filter ? '일치하는 항목이 없습니다.' : "이 폴더가 비어 있습니다. '새 폴더'로 폴더를 만들거나, 글을 써서 저장하세요."}
                </div>
              ) : (
                shown.map((e) => (
                  <div
                    key={(e.isDir ? 'd:' : 'f:') + e.name}
                    onClick={() => (e.isDir ? browse(cwd ? `${cwd}/${e.name}` : e.name) : loadNote(e.name))}
                    className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-amber-50 text-left group cursor-pointer"
                  >
                    {e.isDir
                      ? <Folder size={16} className="text-amber-500 shrink-0" />
                      : <FileText size={16} className="text-amber-600 shrink-0" />}
                    <div className="min-w-0 flex-1">
                      <div className="text-sm font-medium truncate">{e.name}</div>
                      <div className="text-xs text-stone-400">{e.meta}</div>
                    </div>
                    <span onClick={(ev) => delEntry(e, ev)} className="opacity-0 group-hover:opacity-100 text-stone-300 hover:text-rose-500 p-1">
                      <Trash2 size={15} />
                    </span>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
