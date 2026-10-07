/* 격자 엔진 — 브라우저 안 Univer 를 `engine` 뷰(kind=sheet)의 기본 편집 엔진으로 묶는 얇은 껍질.
 * docs/SPREADSHEET_APP_ON_IBL_PLAN_2026_10_07.md §2·§4. Univer 의 자체 도구줄·머리·꼬리는 숨기고
 * 우리 엑셀 얼굴(ExcelFrame)이 Facade 로 명령한다. 파일 I/O 는 grid.v1 통화(grid-schema.ts)로만 — 이 파일 밖에서는
 * Univer 타입이 새지 않는다. */
import { createUniver, LocaleType, mergeLocales, type FUniver, type ICellData, type IRange, type IStyleData } from '@univerjs/presets';
import type { FWorkbook, FWorksheet, FRange } from '@univerjs/preset-sheets-core';
import { greenTheme } from '@univerjs/themes';
import { UniverSheetsCorePreset, FormulaDataModel, SetHorizontalTextAlignCommand, SetVerticalTextAlignCommand } from '@univerjs/preset-sheets-core';
import coreKo from '@univerjs/preset-sheets-core/locales/ko-KR';
import { UniverSheetsFilterPreset } from '@univerjs/preset-sheets-filter';
import filterKo from '@univerjs/preset-sheets-filter/locales/ko-KR';
import { UniverSheetsSortPreset } from '@univerjs/preset-sheets-sort';
import sortKo from '@univerjs/preset-sheets-sort/locales/ko-KR';
import { UniverSheetsFindReplacePreset, OpenFindDialogOperation, OpenReplaceDialogOperation } from '@univerjs/preset-sheets-find-replace';
import findKo from '@univerjs/preset-sheets-find-replace/locales/ko-KR';
import '@univerjs/preset-sheets-core/lib/index.css';
import '@univerjs/preset-sheets-filter/lib/index.css';
import '@univerjs/preset-sheets-sort/lib/index.css';
import '@univerjs/preset-sheets-find-replace/lib/index.css';
import { type GridCell, type GridSheet, type GridWorkbook, a1, gridValue, parseRange, rangeA1, toUniver } from './grid-schema';

export type Selection = { sheet: string; range: string; rows: number; cols: number; r1: number; c1: number; r2: number; c2: number };
export type CellInfo = { address: string; formula: string; display: string; style: Partial<IStyleData> | null };
export type Stats = { count: number; numbers: number; sum: number; avg: number };
export type SheetTab = { id: string; name: string; active: boolean; hidden: boolean };
type Listener = () => void;

const SILENT_MUTATIONS = /set-zoom-ratio|set-scroll|set-selections|set-worksheet-active|set-frozen/;
const DEFAULT_COL_W = 73, DEFAULT_ROW_H = 20;

export class GridEngine {
  private api: FUniver;
  private wb: FWorkbook | null = null;
  private disposers: Array<{ dispose: () => void }> = [];
  private changeListeners = new Set<Listener>();
  private selectionListeners = new Set<Listener>();
  private sheetListeners = new Set<Listener>();
  private highlight: { dispose: () => void } | null = null;
  readonly unitId = 'wb-' + Math.random().toString(36).slice(2, 10);

  constructor(container: HTMLElement) {
    const { univerAPI } = createUniver({
      locale: LocaleType.KO_KR,
      locales: { [LocaleType.KO_KR]: mergeLocales(coreKo, filterKo, sortKo, findKo) },
      theme: greenTheme,
      presets: [
        UniverSheetsCorePreset({ container, header: false, toolbar: false, footer: false, formulaBar: false, contextMenu: true }),
        UniverSheetsFilterPreset(), UniverSheetsSortPreset(), UniverSheetsFindReplacePreset(),
      ],
    });
    this.api = univerAPI;
  }

  /* ── 수명 ── */
  load(grid: GridWorkbook) {
    this.unload();
    const wb = this.api.createWorkbook(toUniver(grid, this.unitId));
    this.wb = wb;
    this.disposers.push(wb.onCommandExecuted((cmd) => {
      if (cmd.type === 2 && !SILENT_MUTATIONS.test(cmd.id)) this.changeListeners.forEach((l) => l());  // 2 = MUTATION
      if (/set-worksheet-active|insert-sheet|remove-sheet|set-worksheet-name|set-worksheet-order|set-worksheet-hide/.test(cmd.id)) this.sheetListeners.forEach((l) => l());
    }));
    this.disposers.push(wb.onSelectionChange(() => this.selectionListeners.forEach((l) => l())));
    this.sheetListeners.forEach((l) => l());
    this.selectionListeners.forEach((l) => l());
  }
  unload() {
    this.highlight?.dispose(); this.highlight = null;
    this.disposers.forEach((d) => d.dispose()); this.disposers = [];
    if (this.wb) { this.api.disposeUnit(this.wb.getId()); this.wb = null; }
  }
  dispose() { this.unload(); try { this.api.dispose(); } catch { /* 이미 내려간 엔진 */ } }
  get loaded() { return !!this.wb; }
  onChange(l: Listener) { this.changeListeners.add(l); return () => { this.changeListeners.delete(l); }; }
  onSelection(l: Listener) { this.selectionListeners.add(l); return () => { this.selectionListeners.delete(l); }; }
  onSheets(l: Listener) { this.sheetListeners.add(l); return () => { this.sheetListeners.delete(l); }; }

  /* ── 편집 중인 셀 확정(IME·수식 입력줄) — 포획·저장 전에 부른다 ── */
  async settle() { if (this.wb?.isCellEditing()) await this.wb.endEditingAsync(true); }

  /* ── 내보내기: grid.v1 ── */
  private arrayRanges(sheetId: string): Map<string, IRange> {
    // 배열 수식(FILTER·SORT…)의 스필 범위 — 주인 셀만 수식으로, 나머지는 값 없이 둔다(다시 열면 다시 스필).
    const out = new Map<string, IRange>();
    try {
      const injector = (this.api as unknown as { _injector: { get: (k: unknown) => unknown } })._injector;
      const model = injector.get(FormulaDataModel) as { getArrayFormulaRange: () => Record<string, Record<string, Record<string, Record<string, IRange>>>> };
      const sheet = model.getArrayFormulaRange()?.[this.unitId]?.[sheetId];
      if (sheet) for (const [r, cols] of Object.entries(sheet)) for (const [c, range] of Object.entries(cols)) out.set(`${r}:${c}`, range);
    } catch { /* 모델에 닿지 못하면 스필 없이 */ }
    return out;
  }
  export(): GridWorkbook {
    const wb = this.wb; if (!wb) throw new Error('열린 통합문서가 없습니다');
    const styles = wb.getWorkbook().getStyles();
    const sheets: GridSheet[] = wb.getSheets().map((ws) => {
      const core = ws.getSheet();
      const used = ws.getDataRange();
      const r0 = used.getRow(), c0 = used.getColumn(), rows = used.getHeight(), cols = used.getWidth();
      const cells: Record<string, GridCell> = {};
      const spills = this.arrayRanges(ws.getSheetId());
      const covered = new Set<string>();
      for (const [key, range] of spills) {
        for (let r = range.startRow; r <= range.endRow; r++) for (let c = range.startColumn; c <= range.endColumn; c++) if (`${r}:${c}` !== key) covered.add(`${r}:${c}`);
      }
      if (rows > 0 && cols > 0 && !used.isBlank()) {
        const datas = used.getCellDatas(), formulas = used.getFormulas();
        for (let i = 0; i < rows; i++) for (let j = 0; j < cols; j++) {
          const r = r0 + i, c = c0 + j;
          const d: ICellData | null = datas[i]?.[j] ?? null;
          const f = formulas[i]?.[j] || '';
          const s = d?.s ? (typeof d.s === 'string' ? styles.get(d.s) : d.s) : null;
          const entry: GridCell = {};
          if (f) {
            entry.f = f;
            const spill = spills.get(`${r}:${c}`);
            if (spill) entry.ref = rangeA1(spill.startRow, spill.startColumn, spill.endRow, spill.endColumn);
            const v = gridValue(d); if (v.v !== undefined) entry.v = v.v;  // 격자가 계산한 값 → 파일의 캐시
          } else if (!covered.has(`${r}:${c}`)) {
            Object.assign(entry, gridValue(d));
          }
          if (s && Object.keys(s).length) entry.s = s as Partial<IStyleData>;
          if (entry.f || entry.v !== undefined || entry.s) cells[a1(r, c)] = entry;
        }
      }
      const colsOut: GridSheet['cols'] = {};
      const maxC = Math.max(cols + c0, 1);
      for (let c = 0; c < Math.min(core.getColumnCount(), maxC + 30); c++) {
        const w = ws.getColumnWidth(c), hidden = !core.getColVisible(c);
        if (Math.round(w) !== DEFAULT_COL_W || hidden) colsOut[String(c)] = { ...(Math.round(w) !== DEFAULT_COL_W ? { w: Math.round(w) } : {}), ...(hidden ? { hidden: true } : {}) };
      }
      const rowsOut: GridSheet['rows'] = {};
      const maxR = Math.max(rows + r0, 1);
      for (let r = 0; r < Math.min(core.getRowCount(), maxR + 30); r++) {
        const h = ws.getRowHeight(r), hidden = !core.getRowVisible(r) && !core.getRowFiltered(r);
        if (Math.round(h) !== DEFAULT_ROW_H || hidden) rowsOut[String(r)] = { ...(Math.round(h) !== DEFAULT_ROW_H ? { h: Math.round(h) } : {}), ...(hidden ? { hidden: true } : {}) };
      }
      const fr = ws.getFreeze();
      return {
        name: ws.getSheetName(), hidden: ws.isSheetHidden(), tab_color: ws.getTabColor() || null, gridlines: !ws.hasHiddenGridLines(),
        freeze: { rows: Math.max(0, fr.ySplit || 0), cols: Math.max(0, fr.xSplit || 0) },
        cols: colsOut, rows: rowsOut,
        merges: ws.getMergedRanges().map((m) => { const r = m.getRange(); return rangeA1(r.startRow, r.startColumn, r.endRow, r.endColumn); }),
        cells,
      };
    });
    return { version: 1, sheets };
  }

  /* ── `[self:workspace]` 스냅샷 계약의 engine_state(플러그인 state() 와 같은 꼴) ── */
  engineState(): string {
    const wb = this.wb; if (!wb) throw new Error('열린 통합문서가 없습니다');
    return JSON.stringify(wb.getSheets().map((ws) => {
      const used = ws.getDataRange();
      const blank = used.isBlank();
      return { name: ws.getSheetName(), address: blank ? 'A1' : used.getA1Notation(),
        values: blank ? [[null]] : used.getRawValues(), formulas: blank ? [['']] : used.getFormulas(),
        format: blank ? [['General']] : used.getCellDatas().map((row) => row.map((d) => {
          const s = d?.s ? (typeof d.s === 'string' ? wb.getWorkbook().getStyles().get(d.s) : d.s) : null;
          return (s as IStyleData | null)?.n?.pattern || 'General';
        })) };
    }));
  }

  /* ── 선택·셀 정보 ── */
  sheet(): FWorksheet | null { return this.wb?.getActiveSheet() ?? null; }
  range(): FRange | null { return this.wb?.getActiveRange() ?? null; }
  selection(): Selection | null {
    const ws = this.sheet(), r = this.range(); if (!ws || !r) return null;
    const g = r.getRange();
    return { sheet: ws.getSheetName(), range: rangeA1(g.startRow, g.startColumn, g.endRow, g.endColumn), rows: r.getHeight(), cols: r.getWidth(),
      r1: g.startRow, c1: g.startColumn, r2: g.endRow, c2: g.endColumn };
  }
  activeCell(): CellInfo | null {
    const ws = this.sheet(); const cell = this.wb?.getActiveCell() ?? ws?.getActiveCell(); if (!ws || !cell) return null;
    const g = cell.getRange(); const one = ws.getRange(g.startRow, g.startColumn);
    const f = one.getFormula();
    const raw = one.getRawValue();
    return { address: a1(g.startRow, g.startColumn), formula: f || (raw == null ? '' : String(raw)), display: one.getDisplayValue(), style: one.getCellStyleData() };
  }
  stats(): Stats {
    const r = this.range(); if (!r || r.getHeight() * r.getWidth() > 200000) return { count: 0, numbers: 0, sum: 0, avg: 0 };
    let count = 0, numbers = 0, sum = 0;
    for (const row of r.getRawValues()) for (const v of row) {
      if (v === null || v === undefined || v === '') continue;
      count++;
      if (typeof v === 'number') { numbers++; sum += v; }
    }
    return { count, numbers, sum, avg: numbers ? sum / numbers : 0 };
  }
  values(sel: Selection, cap = 10000): (string | number | boolean | null)[][] {
    const ws = this.wb?.getSheetByName(sel.sheet); if (!ws) return [];
    if (sel.rows * sel.cols > cap) throw new Error(`선택 범위가 ${cap.toLocaleString()}셀을 넘습니다 — 더 좁게 고르세요`);
    return ws.getRange(sel.r1, sel.c1, sel.rows, sel.cols).getRawValues().map((row) => row.map((v) => (v === undefined ? null : v)));
  }
  /* AI 에게 보이는 셀: 수식이 있으면 수식, 아니면 값 — 제안도 같은 표현으로 돌아오므로 "바뀌지 않은 셀"을 정확히 가른다. */
  cellsForAI(sel: Selection, cap = 10000): (string | number | boolean | null)[][] {
    const ws = this.wb?.getSheetByName(sel.sheet); if (!ws) return [];
    if (sel.rows * sel.cols > cap) throw new Error(`선택 범위가 ${cap.toLocaleString()}셀을 넘습니다 — 더 좁게 고르세요`);
    const r = ws.getRange(sel.r1, sel.c1, sel.rows, sel.cols);
    const values = r.getRawValues(), formulas = r.getFormulas();
    return values.map((row, i) => row.map((v, j) => formulas[i]?.[j] || (v === undefined ? null : v)));
  }
  /* 바뀐 셀만 한 명령으로(실행 취소 한 번). 희소 행렬의 키는 절대 행·열. */
  applyCells(sel: Selection, cells: { row: number; col: number; value: string | number | boolean | null }[]) {
    const ws = this.wb?.getSheetByName(sel.sheet); if (!ws) throw new Error('시트를 찾지 못했습니다: ' + sel.sheet);
    if (!cells.length) return;
    const matrix: Record<number, Record<number, ICellData>> = {};
    for (const c of cells) {
      const v = c.value;
      (matrix[c.row] ||= {})[c.col] = typeof v === 'string' && v.startsWith('=') ? { f: v } : v === null ? { v: null, f: null } : { v, f: null };
    }
    ws.getRange(sel.r1, sel.c1, sel.rows, sel.cols).setValues(matrix);
  }
  usedSelection(): Selection | null {
    const ws = this.sheet(); if (!ws) return null;
    const u = ws.getDataRange(); if (u.isBlank()) return null;
    const g = u.getRange();
    return { sheet: ws.getSheetName(), range: rangeA1(g.startRow, g.startColumn, g.endRow, g.endColumn), rows: u.getHeight(), cols: u.getWidth(), r1: g.startRow, c1: g.startColumn, r2: g.endRow, c2: g.endColumn };
  }
  goTo(address: string) {
    const ws = this.sheet(); const p = parseRange(address); if (!ws || !p) return false;
    ws.getRange(p.r1, p.c1, p.r2 - p.r1 + 1, p.c2 - p.c1 + 1).activate();
    ws.scrollToCell(p.r1, p.c1);
    return true;
  }

  /* ── 값·수식 쓰기(사람의 편집과 같은 길 — 실행 취소 가능) ── */
  setCell(text: string) {
    const ws = this.sheet(); const cell = this.wb?.getActiveCell(); if (!ws || !cell) return;
    const g = cell.getRange(); const one = ws.getRange(g.startRow, g.startColumn);
    if (text.startsWith('=')) one.setFormula(text); else if (text === '') one.clearContent(); else one.setValue(numberOrText(text));
  }
  setValues(sel: Selection, values: (string | number | boolean | null)[][], asFormulas = false) {
    const ws = this.wb?.getSheetByName(sel.sheet); if (!ws) throw new Error('시트를 찾지 못했습니다: ' + sel.sheet);
    const target = ws.getRange(sel.r1, sel.c1, values.length, values[0]?.length || 1);
    if (asFormulas) target.setFormulas(values.map((row) => row.map((v) => String(v ?? ''))));
    else target.setValues(values.map((row) => row.map((v): ICellData => (typeof v === 'string' && v.startsWith('=') ? { f: v } : v === null ? { v: null } : { v }))));
  }
  /* 제안 미리보기 강조 — 바뀌는 셀들을 노랗게. 반영·닫기 때 거둔다. */
  highlightCells(sel: Selection, addresses: string[]) {
    this.highlight?.dispose(); this.highlight = null;
    const ws = this.wb?.getSheetByName(sel.sheet); if (!ws || !addresses.length) return;
    const ranges = addresses.map((addr) => ws.getRange(addr));
    this.highlight = ws.highlightRanges(ranges, { fill: 'rgba(255, 213, 79, 0.35)', stroke: '#e0a800', strokeWidth: 1 });
  }
  clearHighlight() { this.highlight?.dispose(); this.highlight = null; }

  /* ── 리본 명령(활성 범위에) ── */
  private with(fn: (r: FRange, ws: FWorksheet, wb: FWorkbook) => void) { const r = this.range(), ws = this.sheet(); if (r && ws && this.wb) fn(r, ws, this.wb); }
  private styleOf(): Partial<IStyleData> { return this.activeCell()?.style || {}; }
  toggleBold() { this.with((r) => r.setFontWeight(this.styleOf().bl ? 'normal' : 'bold')); }
  toggleItalic() { this.with((r) => r.setFontStyle(this.styleOf().it ? 'normal' : 'italic')); }
  toggleUnderline() { this.with((r) => r.setFontLine(this.styleOf().ul?.s ? 'none' : 'underline')); }
  toggleStrike() { this.with((r) => r.setFontLine(this.styleOf().st?.s ? 'none' : 'line-through')); }
  fontFamily(name: string) { this.with((r) => r.setFontFamily(name)); }
  fontSize(size: number) { this.with((r) => r.setFontSize(size)); }
  fontColor(color: string | null) { this.with((r) => r.setFontColor(color)); }
  fillColor(color: string | null) { this.with((r) => r.setBackgroundColor(color || 'transparent')); }
  border(kind: 'all' | 'outside' | 'none' | 'bottom' | 'top' | 'left' | 'right', color = '#000000') {
    const T = this.api.Enum.BorderType, S = this.api.Enum.BorderStyleTypes;
    const map = { all: T.ALL, outside: T.OUTSIDE, none: T.ALL, bottom: T.BOTTOM, top: T.TOP, left: T.LEFT, right: T.RIGHT } as const;
    this.with((r) => r.setBorder(map[kind], kind === 'none' ? S.NONE : S.THIN, color));
  }
  // 가로 맞춤은 Facade 가 right 를 모른다 → 같은 명령(선택 범위에 적용, 실행 취소 가능)을 직접 부른다. HorizontalAlign: 1 left·2 center·3 right
  align(h: 'left' | 'center' | 'right') { if (this.wb) void this.api.executeCommand(SetHorizontalTextAlignCommand.id, { value: { left: 1, center: 2, right: 3 }[h] }); }
  valign(v: 'top' | 'middle' | 'bottom') { if (this.wb) void this.api.executeCommand(SetVerticalTextAlignCommand.id, { value: { top: 1, middle: 2, bottom: 3 }[v] }); }
  toggleWrap() { this.with((r) => r.setWrap(this.styleOf().tb === 3 ? false : true)); }
  toggleMerge() { this.with((r) => (r.isMerged() || r.isPartOfMerge() ? r.breakApart() : r.merge())); }
  numberFormat(pattern: string) { this.with((r) => r.setNumberFormat(pattern)); }
  adjustDecimals(delta: 1 | -1) {
    const cur = this.styleOf().n?.pattern || 'General';
    const m = /^(.*?0)(?:\.(0+))?(.*)$/.exec(cur === 'General' ? '0' : cur);
    const dec = m?.[2]?.length ?? 0;
    const next = Math.max(0, dec + delta);
    const base = m ? m[1] + (next ? '.' + '0'.repeat(next) : '') + m[3] : (next ? '0.' + '0'.repeat(next) : '0');
    this.numberFormat(base);
  }
  insertRows(count = 1) { this.with((r, ws) => ws.insertRowsBefore(r.getRow(), count)); }
  deleteRows() { this.with((r, ws) => ws.deleteRows(r.getRow(), r.getHeight())); }
  insertCols(count = 1) { this.with((r, ws) => ws.insertColumnsBefore(r.getColumn(), count)); }
  deleteCols() { this.with((r, ws) => ws.deleteColumns(r.getColumn(), r.getWidth())); }
  clearContents() { this.with((r) => r.clearContent()); }
  clearFormats() { this.with((r) => r.clearFormat()); }
  autoSum() {
    this.with((r, ws) => {
      const g = r.getRange();
      if (r.getHeight() > 1 || r.getWidth() > 1) {  // 범위를 골랐으면 바로 아래 줄에 열별 합계
        for (let c = g.startColumn; c <= g.endColumn; c++) ws.getRange(g.endRow + 1, c).setFormula(`=SUM(${rangeA1(g.startRow, c, g.endRow, c)})`);
        return;
      }
      let top = g.startRow - 1;  // 위로 숫자가 이어지는 구간
      while (top >= 0 && typeof ws.getRange(top, g.startColumn).getRawValue() === 'number') top--;
      top++;
      if (top < g.startRow) { ws.getRange(g.startRow, g.startColumn).setFormula(`=SUM(${rangeA1(top, g.startColumn, g.startRow - 1, g.startColumn)})`); return; }
      let left = g.startColumn - 1;
      while (left >= 0 && typeof ws.getRange(g.startRow, left).getRawValue() === 'number') left--;
      left++;
      if (left < g.startColumn) ws.getRange(g.startRow, g.startColumn).setFormula(`=SUM(${rangeA1(g.startRow, left, g.startRow, g.startColumn - 1)})`);
    });
  }
  sort(ascending: boolean) {
    this.with((r, ws) => {
      const multi = r.getHeight() > 1 || r.getWidth() > 1;
      const target = multi ? r : ws.getDataRange();
      const col = r.getColumn() - target.getColumn();
      (target as unknown as { sort: (s: { column: number; ascending: boolean }) => void }).sort({ column: Math.max(0, col), ascending });
    });
  }
  toggleFilter() {
    this.with((r, ws) => {
      const w = ws as unknown as { getFilter: () => { remove: () => void } | null; getDataRange: () => FRange };
      const existing = w.getFilter();
      if (existing) { existing.remove(); return; }
      const multi = r.getHeight() > 1 || r.getWidth() > 1;
      ((multi ? r : w.getDataRange()) as unknown as { createFilter: () => unknown }).createFilter();
    });
  }
  hasFilter(): boolean { const ws = this.sheet() as unknown as { getFilter?: () => unknown } | null; return !!ws?.getFilter?.(); }
  freezeAtSelection() { this.with((r, ws) => { const g = r.getRange(); ws.setFreeze({ xSplit: g.startColumn, ySplit: g.startRow, startRow: g.startRow, startColumn: g.startColumn }); }); }
  freezeTopRow() { this.sheet()?.setFrozenRows(1); }
  freezeFirstCol() { this.sheet()?.setFrozenColumns(1); }
  unfreeze() { this.sheet()?.cancelFreeze(); }
  frozen(): boolean { const f = this.sheet()?.getFreeze(); return !!f && ((f.xSplit || 0) > 0 || (f.ySplit || 0) > 0); }
  toggleGridlines() { const ws = this.sheet(); if (ws) ws.setHiddenGridlines(!ws.hasHiddenGridLines()); }
  gridlines(): boolean { return !this.sheet()?.hasHiddenGridLines(); }
  zoom(ratio: number) { this.sheet()?.zoom(Math.min(4, Math.max(0.25, ratio))); }
  zoomLevel(): number { return this.sheet()?.getZoom() ?? 1; }
  undo() { void this.api.undo(); }
  redo() { void this.api.redo(); }
  copy() { void this.api.copy(); }
  paste() { void this.api.paste(); }
  find() { void this.api.executeCommand(OpenFindDialogOperation.id); }
  replace() { void this.api.executeCommand(OpenReplaceDialogOperation.id); }
  autoFitColumns() { this.with((r, ws) => ws.autoResizeColumns(r.getColumn(), r.getWidth())); }
  autoFitRows() { this.with((r, ws) => ws.autoResizeRows(r.getRow(), r.getHeight())); }

  /* ── 시트 탭 ── */
  tabs(): SheetTab[] {
    const wb = this.wb; if (!wb) return [];
    const active = wb.getActiveSheet().getSheetId();
    return wb.getSheets().map((ws) => ({ id: ws.getSheetId(), name: ws.getSheetName(), active: ws.getSheetId() === active, hidden: ws.isSheetHidden() }));
  }
  activate(id: string) { const ws = this.wb?.getSheetBySheetId(id); if (ws) this.wb?.setActiveSheet(ws); }
  addSheet() {
    const wb = this.wb; if (!wb) return;
    const names = new Set(wb.getSheets().map((s) => s.getSheetName()));
    let n = wb.getNumSheets() + 1; while (names.has(`Sheet${n}`)) n++;
    const ws = wb.insertSheet(`Sheet${n}`); wb.setActiveSheet(ws);
  }
  renameSheet(id: string, name: string) { const ws = this.wb?.getSheetBySheetId(id); if (ws && name.trim()) ws.setName(name.trim().slice(0, 31)); }
  deleteSheet(id: string) { const wb = this.wb; if (!wb || wb.getNumSheets() < 2) return; const ws = wb.getSheetBySheetId(id); if (ws) wb.deleteSheet(ws); }
  duplicateSheet(id: string) { const ws = this.wb?.getSheetBySheetId(id); if (ws) this.wb?.duplicateSheet(ws); }
}

function numberOrText(text: string): string | number | boolean {
  const t = text.trim();
  if (/^-?\d+(\.\d+)?$/.test(t) && !/^0\d/.test(t)) return Number(t);
  if (/^(true|false)$/i.test(t)) return t.toLowerCase() === 'true';
  return text;
}
