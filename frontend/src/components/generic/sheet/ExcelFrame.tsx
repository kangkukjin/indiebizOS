/* 엑셀 얼굴 — 제목줄·리본 탭·리본·수식줄·격자 자리·시트 탭·상태줄 + 오른쪽 AI 작업창 + 파일 탭(백스테이지).
 * docs/SPREADSHEET_APP_ON_IBL_PLAN_2026_10_07.md §1. 명령은 전부 GridEngine(Facade)로 — 안 되는 버튼은 그리지 않는다.
 * 선언에는 레이아웃 키가 없다: 이 얼굴은 시트 엔진이 맡는다. */
import { useEffect, useRef, useState, type ReactNode } from 'react';
import type { GridEngine } from './grid-engine';
import './excel.css';

export type FrameProps = {
  engine: GridEngine | null;
  tick: number;                       // 선택·변경·시트 바뀔 때마다 증가 — 얼굴이 엔진 상태를 다시 읽는다
  hostRef: (el: HTMLDivElement | null) => void;
  title: string; dirty: boolean; status: string; busy: boolean; overlay?: string | null;
  onSave: () => void;
  backstage: (close: () => void) => ReactNode;   // 파일 탭 내용(계기 모드 탭·엔진 도구) — 엔진 바인딩이 준다
  pane: ReactNode | null;                        // AI 작업창 내용(ai_dock 선언이 있을 때)
  paneOpen: boolean; onPane: (open: boolean) => void;
};

const TABS = ['홈', '삽입', '수식', '데이터', '보기'] as const;
type Tab = typeof TABS[number];
const FONTS = ['맑은 고딕', 'Apple SD Gothic Neo', '나눔고딕', 'Arial', 'Calibri', 'Times New Roman', 'Courier New'];
const SIZES = [8, 9, 10, 11, 12, 14, 16, 18, 20, 24, 28, 36];
const FORMATS: [string, string][] = [['General', '일반'], ['0', '숫자'], ['#,##0', '천 단위'], ['#,##0.00', '소수 둘'], ['₩#,##0', '통화(₩)'],
  ['_(₩* #,##0_);_(₩* (#,##0);_(₩* "-"_);_(@_)', '회계'], ['0%', '백분율'], ['0.00%', '백분율(소수)'], ['yyyy-mm-dd', '날짜'], ['yyyy-mm-dd hh:mm', '날짜·시간'], ['hh:mm', '시간'], ['@', '텍스트']];

export function ExcelFrame(p: FrameProps) {
  const { engine } = p;
  const [tab, setTab] = useState<Tab>('홈');
  const [file, setFile] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [nameBox, setNameBox] = useState('');
  const [formula, setFormula] = useState('');
  const [editingFormula, setEditingFormula] = useState(false);
  const [renaming, setRenaming] = useState<{ id: string; name: string } | null>(null);
  const formulaRef = useRef<HTMLInputElement>(null);
  const sel = engine?.loaded ? engine.selection() : null;
  const cell = engine?.loaded ? engine.activeCell() : null;
  const stats = engine?.loaded ? engine.stats() : null;
  const tabs = engine?.loaded ? engine.tabs() : [];
  const style = cell?.style || {};
  useEffect(() => { if (!editingFormula) { setNameBox(sel ? sel.range : ''); setFormula(cell ? cell.formula : ''); } }, [p.tick, editingFormula]); // eslint-disable-line react-hooks/exhaustive-deps
  const act = (fn: (e: GridEngine) => void) => () => { if (engine?.loaded) fn(engine); };
  const B = ({ on, title, children, do: fn, disabled }: { on?: boolean; title: string; children: ReactNode; do: (e: GridEngine) => void; disabled?: boolean }) => (
    <button type="button" className={`xl-btn${on ? ' on' : ''}`} title={title} aria-label={title} aria-pressed={on} disabled={disabled || !engine?.loaded} onMouseDown={(e) => e.preventDefault()} onClick={act(fn)}>{children}</button>
  );
  const Big = ({ title, ico, label, do: fn }: { title: string; ico: string; label: string; do: (e: GridEngine) => void }) => (
    <button type="button" className="xl-big" title={title} aria-label={title} disabled={!engine?.loaded} onMouseDown={(e) => e.preventDefault()} onClick={act(fn)}><span className="xl-ico">{ico}</span><span>{label}</span></button>
  );
  const Group = ({ label, children }: { label: string; children: ReactNode }) => <div className="xl-group"><div className="xl-body">{children}</div><div className="xl-label">{label}</div></div>;
  const Color = ({ title, glyph, color, do: fn }: { title: string; glyph: string; color: string; do: (e: GridEngine, c: string | null) => void }) => {
    const id = useRef('c' + Math.random().toString(36).slice(2, 8));
    return (
      <span className="xl-row">
        <button type="button" className="xl-btn" title={title} aria-label={title} disabled={!engine?.loaded} onMouseDown={(e) => e.preventDefault()}
          onClick={() => document.getElementById(id.current)?.click()}><span className="xl-colorbtn">{glyph}<i className="xl-swatch" style={{ background: color }} /></span></button>
        <input id={id.current} type="color" aria-label={title + ' 고르기'} defaultValue={color} onChange={(e) => engine && fn(engine, e.target.value)} />
        <button type="button" className="xl-btn" title={title + ' 없음'} aria-label={title + ' 없음'} disabled={!engine?.loaded} onMouseDown={(e) => e.preventDefault()} onClick={() => engine && fn(engine, null)}>✕</button>
      </span>
    );
  };
  const commitFormula = () => { if (engine?.loaded) engine.setCell(formula); setEditingFormula(false); };
  const sumWith = (fn: string) => act((e) => {
    const s = e.selection(); if (!s) return;
    if (fn === 'SUM') { e.autoSum(); return; }
    const cur = e.activeCell(); if (!cur) return;
    e.setCell(`=${fn}(${s.rows > 1 || s.cols > 1 ? s.range : ''}`);
  });
  return (
    <div className="xl" data-testid="excel-frame" onKeyDown={(e) => { if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 's') { e.preventDefault(); p.onSave(); } }}>
      <div className="xl-title">
        <span className="xl-save"><i className={p.dirty ? 'dirty' : ''} />{p.dirty ? '초안' : '저장됨'}</span>
        <span className="xl-name" title={p.title}>{p.title} — 스프레드시트</span>
        <span className="xl-status" role="status">{p.status}</span>
        <button type="button" title="실행 취소 (Ctrl+Z)" aria-label="실행 취소" onClick={act((e) => e.undo())}>↶</button>
        <button type="button" title="다시 실행 (Ctrl+Y)" aria-label="다시 실행" onClick={act((e) => e.redo())}>↷</button>
        <button type="button" disabled={p.busy} onClick={p.onSave} title="원본 저장 (Ctrl+S)">저장</button>
      </div>

      <div className="xl-tabs" role="tablist">
        <button type="button" role="tab" className={`xl-tab file${file ? ' on' : ''}`} aria-selected={file} onClick={() => setFile((v) => !v)}>파일</button>
        {TABS.map((t) => <button key={t} type="button" role="tab" className={`xl-tab${tab === t && !collapsed ? ' on' : ''}`} aria-selected={tab === t}
          onClick={() => { if (tab === t) setCollapsed((v) => !v); else { setTab(t); setCollapsed(false); } }}>{t}</button>)}
        <span className="xl-spacer" />
        {p.pane !== null && <button type="button" className={`xl-ai${p.paneOpen ? ' on' : ''}`} aria-pressed={p.paneOpen} onClick={() => p.onPane(!p.paneOpen)}>✦ AI</button>}
      </div>

      <div className={`xl-ribbon${collapsed ? ' collapsed' : ''}`} role="toolbar" aria-label={tab + ' 리본'}>
        {tab === '홈' && <>
          <Group label="클립보드"><Big title="붙여넣기" ico="📋" label="붙여넣기" do={(e) => e.paste()} /><div className="xl-col"><B title="복사" do={(e) => e.copy()}>⧉ 복사</B><B title="내용 지우기" do={(e) => e.clearContents()}>◌ 지우기</B><B title="서식 지우기" do={(e) => e.clearFormats()}>🖌 서식 지우기</B></div></Group>
          <Group label="글꼴">
            <div className="xl-col">
              <div className="xl-row">
                <select className="xl-sel" aria-label="글꼴" style={{ width: 130 }} value={style.ff || ''} disabled={!engine?.loaded} onChange={(e) => engine?.fontFamily(e.target.value)}>
                  <option value="">기본 글꼴</option>{FONTS.map((f) => <option key={f} value={f}>{f}</option>)}</select>
                <select className="xl-sel" aria-label="글꼴 크기" style={{ width: 52 }} value={style.fs || 11} disabled={!engine?.loaded} onChange={(e) => engine?.fontSize(Number(e.target.value))}>
                  {SIZES.map((s) => <option key={s} value={s}>{s}</option>)}</select>
              </div>
              <div className="xl-row">
                <B title="굵게" on={!!style.bl} do={(e) => e.toggleBold()}><b>가</b></B>
                <B title="기울임꼴" on={!!style.it} do={(e) => e.toggleItalic()}><i>가</i></B>
                <B title="밑줄" on={!!style.ul?.s} do={(e) => e.toggleUnderline()}><u>가</u></B>
                <B title="취소선" on={!!style.st?.s} do={(e) => e.toggleStrike()}><s>가</s></B>
                <select className="xl-sel" aria-label="테두리" value="" disabled={!engine?.loaded} onChange={(e) => { const v = e.target.value as 'all' | 'outside' | 'bottom' | 'top' | 'left' | 'right' | 'none'; if (v) engine?.border(v); e.target.value = ''; }}>
                  <option value="">⊞ 테두리</option><option value="all">모든 테두리</option><option value="outside">바깥쪽 테두리</option><option value="bottom">아래쪽</option><option value="top">위쪽</option><option value="left">왼쪽</option><option value="right">오른쪽</option><option value="none">테두리 없음</option></select>
                <Color title="채우기 색" glyph="◆" color={style.bg?.rgb || '#ffff00'} do={(e, c) => e.fillColor(c)} />
                <Color title="글꼴 색" glyph="가" color={style.cl?.rgb || '#c00000'} do={(e, c) => e.fontColor(c)} />
              </div>
            </div>
          </Group>
          <Group label="맞춤">
            <div className="xl-col">
              <div className="xl-row"><B title="위쪽 맞춤" on={style.vt === 1} do={(e) => e.valign('top')}>⤒</B><B title="가운데 맞춤(세로)" on={style.vt === 2} do={(e) => e.valign('middle')}>⇅</B><B title="아래쪽 맞춤" on={style.vt === 3} do={(e) => e.valign('bottom')}>⤓</B><B title="자동 줄 바꿈" on={style.tb === 3} do={(e) => e.toggleWrap()}>↵ 자동 줄 바꿈</B></div>
              <div className="xl-row"><B title="왼쪽 맞춤" on={style.ht === 1} do={(e) => e.align('left')}>≡</B><B title="가운데 맞춤" on={style.ht === 2} do={(e) => e.align('center')}>☰</B><B title="오른쪽 맞춤" on={style.ht === 3} do={(e) => e.align('right')}>≡</B><B title="병합하고 가운데 맞춤 / 병합 해제" do={(e) => { e.toggleMerge(); e.align('center'); }}>⊟ 병합하고 가운데 맞춤</B></div>
            </div>
          </Group>
          <Group label="표시 형식">
            <div className="xl-col">
              <select className="xl-sel" aria-label="표시 형식" style={{ width: 130 }} value={FORMATS.some(([k]) => k === (style.n?.pattern || 'General')) ? (style.n?.pattern || 'General') : '__custom'} disabled={!engine?.loaded}
                onChange={(e) => { if (e.target.value !== '__custom') engine?.numberFormat(e.target.value); }}>
                {FORMATS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}<option value="__custom">사용자 지정</option></select>
              <div className="xl-row"><B title="통화 형식" do={(e) => e.numberFormat('₩#,##0')}>₩</B><B title="백분율" do={(e) => e.numberFormat('0%')}>%</B><B title="쉼표 스타일" do={(e) => e.numberFormat('#,##0')}>,</B><B title="자릿수 늘림" do={(e) => e.adjustDecimals(1)}>.0<sup>+</sup></B><B title="자릿수 줄임" do={(e) => e.adjustDecimals(-1)}>.00<sup>−</sup></B></div>
            </div>
          </Group>
          <Group label="셀">
            <div className="xl-col"><B title="위에 행 삽입" do={(e) => e.insertRows(Math.max(1, e.selection()?.rows || 1))}>⊕ 행 삽입</B><B title="선택한 행 삭제" do={(e) => e.deleteRows()}>⊖ 행 삭제</B></div>
            <div className="xl-col"><B title="왼쪽에 열 삽입" do={(e) => e.insertCols(Math.max(1, e.selection()?.cols || 1))}>⊕ 열 삽입</B><B title="선택한 열 삭제" do={(e) => e.deleteCols()}>⊖ 열 삭제</B></div>
            <div className="xl-col"><B title="열 너비 자동 맞춤" do={(e) => e.autoFitColumns()}>⇔ 열 자동 맞춤</B><B title="행 높이 자동 맞춤" do={(e) => e.autoFitRows()}>⇕ 행 자동 맞춤</B></div>
          </Group>
          <Group label="편집">
            <div className="xl-col"><B title="자동 합계" do={(e) => e.autoSum()}>Σ 자동 합계</B><B title="찾기 (Ctrl+F)" do={(e) => e.find()}>🔍 찾기</B><B title="바꾸기 (Ctrl+H)" do={(e) => e.replace()}>⇄ 바꾸기</B></div>
            <div className="xl-col"><B title="오름차순 정렬" do={(e) => e.sort(true)}>↑ 정렬</B><B title="내림차순 정렬" do={(e) => e.sort(false)}>↓ 정렬</B><B title="필터 켜기/끄기" on={engine?.loaded ? engine.hasFilter() : false} do={(e) => e.toggleFilter()}>▽ 필터</B></div>
          </Group>
        </>}
        {tab === '삽입' && <>
          <Group label="셀"><Big title="위에 행 삽입" ico="⊕" label="행 삽입" do={(e) => e.insertRows(Math.max(1, e.selection()?.rows || 1))} /><Big title="왼쪽에 열 삽입" ico="⊕" label="열 삽입" do={(e) => e.insertCols(Math.max(1, e.selection()?.cols || 1))} /></Group>
          <Group label="시트"><Big title="새 시트" ico="▦" label="새 시트" do={(e) => e.addSheet()} /><Big title="현재 시트 복제" ico="⧉" label="시트 복제" do={(e) => { const t = e.tabs().find((x) => x.active); if (t) e.duplicateSheet(t.id); }} /></Group>
          <Group label="수식"><Big title="자동 합계" ico="Σ" label="자동 합계" do={(e) => e.autoSum()} /></Group>
        </>}
        {tab === '수식' && <>
          <Group label="함수 라이브러리">
            <Big title="자동 합계" ico="Σ" label="자동 합계" do={(e) => e.autoSum()} />
            {['AVERAGE', 'COUNT', 'MAX', 'MIN'].map((fn) => <button key={fn} type="button" className="xl-big" disabled={!engine?.loaded} onMouseDown={(e) => e.preventDefault()} onClick={sumWith(fn)} title={`${fn} 수식 시작`}><span className="xl-ico">ƒ</span><span>{fn}</span></button>)}
          </Group>
          <Group label="수식 입력"><div className="xl-col"><B title="수식 입력줄로 이동" do={() => { setEditingFormula(true); setTimeout(() => formulaRef.current?.focus(), 0); }}><i>fx</i> 함수 삽입</B><B title="찾기" do={(e) => e.find()}>🔍 찾기</B></div></Group>
        </>}
        {tab === '데이터' && <>
          <Group label="정렬 및 필터"><Big title="오름차순 정렬" ico="↑" label="오름차순" do={(e) => e.sort(true)} /><Big title="내림차순 정렬" ico="↓" label="내림차순" do={(e) => e.sort(false)} /><Big title="필터 켜기/끄기" ico="▽" label="필터" do={(e) => e.toggleFilter()} /></Group>
          <Group label="데이터 도구"><Big title="텍스트 나누기(쉼표·탭 기준)" ico="⫼" label="텍스트 나누기" do={(e) => e.range()?.splitTextToColumns(true)} /></Group>
        </>}
        {tab === '보기' && <>
          <Group label="창">
            <div className="xl-col"><B title="선택 위치에서 틀 고정" do={(e) => e.freezeAtSelection()}>▣ 틀 고정</B><B title="첫 행 고정" do={(e) => e.freezeTopRow()}>첫 행 고정</B></div>
            <div className="xl-col"><B title="첫 열 고정" do={(e) => e.freezeFirstCol()}>첫 열 고정</B><B title="틀 고정 취소" disabled={!(engine?.loaded && engine.frozen())} do={(e) => e.unfreeze()}>틀 고정 취소</B></div>
          </Group>
          <Group label="표시"><B title="눈금선 표시" on={engine?.loaded ? engine.gridlines() : true} do={(e) => e.toggleGridlines()}>▦ 눈금선</B></Group>
          <Group label="확대/축소"><Big title="100%" ico="1:1" label="100%" do={(e) => e.zoom(1)} /><Big title="확대" ico="+" label="확대" do={(e) => e.zoom(e.zoomLevel() + 0.1)} /><Big title="축소" ico="−" label="축소" do={(e) => e.zoom(e.zoomLevel() - 0.1)} /></Group>
        </>}
      </div>

      <div className="xl-fbar">
        <input className="xl-namebox" aria-label="이름 상자" value={nameBox} onChange={(e) => setNameBox(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') { engine?.goTo(nameBox); (e.target as HTMLInputElement).blur(); } }} />
        <span className="xl-fx">
          <button type="button" title="취소" aria-label="입력 취소" onClick={() => { setEditingFormula(false); setFormula(cell?.formula || ''); }}>✗</button>
          <button type="button" title="입력" aria-label="입력 확정" onClick={commitFormula}>✓</button>
          <button type="button" title="함수 삽입" aria-label="함수 삽입" onClick={() => { setEditingFormula(true); setFormula((f) => f || '='); formulaRef.current?.focus(); }}><i>fx</i></button>
        </span>
        <input ref={formulaRef} className="xl-formula" aria-label="수식 입력줄" value={formula} placeholder={cell ? '' : '셀을 고르세요'}
          onFocus={() => setEditingFormula(true)} onChange={(e) => setFormula(e.target.value)}
          onBlur={() => setEditingFormula(false)}
          onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); commitFormula(); (e.target as HTMLInputElement).blur(); } if (e.key === 'Escape') { setEditingFormula(false); setFormula(cell?.formula || ''); (e.target as HTMLInputElement).blur(); } }} />
      </div>

      <div className={`xl-main${p.paneOpen && p.pane ? ' with-pane' : ''}`}>
        <div className="xl-grid">
          <div ref={p.hostRef} />
          {p.overlay && <div className="xl-overlay">{p.overlay}</div>}
        </div>
        {p.paneOpen && p.pane && <aside className="xl-pane" aria-label="AI 작업창"><div className="xl-pane-hd"><span>✦ AI</span><button type="button" aria-label="AI 작업창 닫기" onClick={() => p.onPane(false)}>✕</button></div>{p.pane}</aside>}
        {file && <div className="xl-backstage" role="dialog" aria-label="파일">{p.backstage(() => setFile(false))}</div>}
      </div>

      <div className="xl-sheets" role="tablist" aria-label="시트 탭">
        <span className="xl-nav">◂ ▸</span>
        {tabs.map((t) => renaming?.id === t.id
          ? <input key={t.id} autoFocus aria-label="시트 이름" value={renaming.name} onChange={(e) => setRenaming({ id: t.id, name: e.target.value })}
              onBlur={() => { engine?.renameSheet(t.id, renaming.name); setRenaming(null); }}
              onKeyDown={(e) => { if (e.key === 'Enter') { engine?.renameSheet(t.id, renaming.name); setRenaming(null); } if (e.key === 'Escape') setRenaming(null); }} />
          : <button key={t.id} type="button" role="tab" className={`xl-st${t.active ? ' on' : ''}${t.hidden ? ' hidden' : ''}`} aria-selected={t.active}
              onClick={() => engine?.activate(t.id)} onDoubleClick={() => setRenaming({ id: t.id, name: t.name })}
              onContextMenu={(e) => { e.preventDefault(); if (tabs.length > 1 && window.confirm(`시트 "${t.name}" 을(를) 삭제할까요?`)) engine?.deleteSheet(t.id); }}
              title="두 번 눌러 이름 바꾸기 · 오른쪽 클릭으로 삭제">{t.name}</button>)}
        <button type="button" className="xl-add" title="새 시트" aria-label="새 시트" disabled={!engine?.loaded} onClick={act((e) => e.addSheet())}>+</button>
      </div>
      <div className="xl-status-bar">
        <span>{p.busy ? '작업 중…' : '준비'}</span><span className="xl-sp" />
        {stats && stats.numbers > 0 && <><span>평균: {fmt(stats.avg)}</span><span>개수: {stats.count.toLocaleString()}</span><span>합계: {fmt(stats.sum)}</span></>}
        {stats && stats.numbers === 0 && stats.count > 1 && <span>개수: {stats.count.toLocaleString()}</span>}
        <span className="xl-zoom"><button type="button" aria-label="축소" onClick={act((e) => e.zoom(e.zoomLevel() - 0.1))}>−</button>
          <input type="range" min={25} max={400} step={5} aria-label="확대/축소" value={Math.round((engine?.loaded ? engine.zoomLevel() : 1) * 100)} onChange={(e) => engine?.zoom(Number(e.target.value) / 100)} />
          <button type="button" aria-label="확대" onClick={act((e) => e.zoom(e.zoomLevel() + 0.1))}>+</button> {Math.round((engine?.loaded ? engine.zoomLevel() : 1) * 100)}%</span>
      </div>
    </div>
  );
}

const fmt = (n: number) => (Number.isInteger(n) ? n.toLocaleString() : n.toLocaleString(undefined, { maximumFractionDigits: 2 }));
