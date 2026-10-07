/* 격자 통화 grid.v1 (backend/services/spreadsheet_grid.py 와 같은 꼴) ↔ Univer 워크북 데이터.
 * docs/SPREADSHEET_APP_ON_IBL_PLAN_2026_10_07.md §4. 스타일은 Univer IStyleData 의 부분집합을 그대로 들고 다닌다 —
 * 백엔드 변환기가 openpyxl 서식으로 옮긴다. 셀 주소는 A1, 행·열 치수의 키는 0-기반 인덱스. */
import type { ICellData, IStyleData, IWorkbookData, IWorksheetData } from '@univerjs/presets';
import { LocaleType } from '@univerjs/presets';

export type GridCell = { v?: string | number | boolean | null; t?: 'n' | 's' | 'b' | 'e'; f?: string; ref?: string; s?: Partial<IStyleData> | null };
export type GridSheet = {
  name: string; hidden?: boolean; tab_color?: string | null; gridlines?: boolean;
  freeze?: { rows: number; cols: number };
  cols?: Record<string, { w?: number; hidden?: boolean }>;
  rows?: Record<string, { h?: number; hidden?: boolean }>;
  merges?: string[];
  cells: Record<string, GridCell>;
};
export type GridWorkbook = { version: 1; date_system?: '1900' | '1904'; sheets: GridSheet[] };

export const colLetter = (index0: number): string => {
  let n = index0 + 1, s = '';
  while (n > 0) { const r = (n - 1) % 26; s = String.fromCharCode(65 + r) + s; n = Math.floor((n - 1) / 26); }
  return s;
};
export const colIndex = (letters: string): number => {
  let n = 0;
  for (const ch of letters) n = n * 26 + ch.charCodeAt(0) - 64;
  return n - 1;
};
export const a1 = (row0: number, col0: number) => `${colLetter(col0)}${row0 + 1}`;
export function parseA1(addr: string): { row: number; col: number } | null {
  const m = /^\$?([A-Z]{1,3})\$?([0-9]+)$/.exec(addr.trim().toUpperCase());
  return m ? { row: Number(m[2]) - 1, col: colIndex(m[1]) } : null;
}
export function parseRange(addr: string): { r1: number; c1: number; r2: number; c2: number } | null {
  const [a, b] = addr.split(':');
  const p = parseA1(a), q = b ? parseA1(b) : p;
  if (!p || !q) return null;
  return { r1: Math.min(p.row, q.row), c1: Math.min(p.col, q.col), r2: Math.max(p.row, q.row), c2: Math.max(p.col, q.col) };
}
export const rangeA1 = (r1: number, c1: number, r2: number, c2: number) => (r1 === r2 && c1 === c2 ? a1(r1, c1) : `${a1(r1, c1)}:${a1(r2, c2)}`);

const DEFAULT_ROWS = 1000, DEFAULT_COLS = 26;

/* grid.v1 → Univer IWorkbookData. 시트 id 는 이름 기반으로 안정화(같은 이름 = 같은 id). */
export function toUniver(grid: GridWorkbook, unitId: string): IWorkbookData {
  const sheets: Record<string, Partial<IWorksheetData>> = {};
  const order: string[] = [];
  grid.sheets.forEach((sheet, i) => {
    const id = `s${i}`;
    order.push(id);
    const cellData: Record<number, Record<number, ICellData>> = {};
    let maxR = 0, maxC = 0;
    for (const [addr, c] of Object.entries(sheet.cells || {})) {
      const p = parseA1(addr); if (!p) continue;
      maxR = Math.max(maxR, p.row); maxC = Math.max(maxC, p.col);
      const cell: ICellData = {};
      if (c.f) cell.f = c.f;
      else if (c.v !== undefined && c.v !== null) {
        if (c.t === 'b') { cell.v = c.v ? 1 : 0; cell.t = 3; }
        else if (c.t === 'n') { cell.v = Number(c.v); cell.t = 2; }
        else { cell.v = String(c.v); cell.t = c.t === 's' && /^[-+=@0-9.']/.test(String(c.v)) ? 4 : 1; }
      }
      if (c.s) cell.s = c.s as IStyleData;
      (cellData[p.row] ||= {})[p.col] = cell;
    }
    const mergeData = (sheet.merges || []).map(parseRange).filter((m): m is NonNullable<typeof m> => !!m)
      .map((m) => ({ startRow: m.r1, endRow: m.r2, startColumn: m.c1, endColumn: m.c2 }));
    const columnData: Record<number, { w?: number; hd?: number }> = {};
    for (const [k, e] of Object.entries(sheet.cols || {})) columnData[Number(k)] = { ...(e.w ? { w: e.w } : {}), ...(e.hidden ? { hd: 1 } : {}) };
    const rowData: Record<number, { h?: number; hd?: number }> = {};
    for (const [k, e] of Object.entries(sheet.rows || {})) rowData[Number(k)] = { ...(e.h ? { h: e.h } : {}), ...(e.hidden ? { hd: 1 } : {}) };
    const fr = sheet.freeze || { rows: 0, cols: 0 };
    sheets[id] = {
      id, name: sheet.name, hidden: sheet.hidden ? 1 : 0, tabColor: sheet.tab_color || '',
      rowCount: Math.max(DEFAULT_ROWS, maxR + 200), columnCount: Math.max(DEFAULT_COLS, maxC + 10),
      cellData, mergeData, columnData, rowData, showGridlines: sheet.gridlines === false ? 0 : 1,
      freeze: { xSplit: fr.cols, ySplit: fr.rows, startRow: fr.rows, startColumn: fr.cols },
      defaultColumnWidth: 73, defaultRowHeight: 20,
    };
  });
  return { id: unitId, name: unitId, appVersion: '1', locale: LocaleType.KO_KR, styles: {}, sheetOrder: order, sheets,
    dateSystem: grid.date_system === '1904' ? 1904 : 1900 } as unknown as IWorkbookData;
}

/* 값 타입 판정(Univer 셀 → grid.v1). */
export function gridValue(cell: ICellData | null | undefined): Pick<GridCell, 'v' | 't'> {
  if (!cell || cell.v === undefined || cell.v === null || cell.v === '') return {};
  if (cell.t === 3) return { v: !!cell.v, t: 'b' };
  if (typeof cell.v === 'number') return { v: cell.v, t: 'n' };
  const s = String(cell.v);
  if (/^#[A-Z0-9/!?]+$/.test(s)) return { v: s, t: 'e' };
  return { v: s, t: 's' };
}
