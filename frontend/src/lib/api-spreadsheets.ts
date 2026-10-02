import { BACKEND_ORIGIN } from './backend-origin';
export { sessionArgs } from './api-documents';
export type { Session, Document } from './api-documents';
import type { Session, Document } from './api-documents';
export type SheetDetail = {document:Document;session:Session|null;capabilities:{edit_native:boolean;reason:string};workbook:{sheets?:{sheet_id:string;name:string}[]}};
export type SheetSnapshot = {id:string;session_revision:number;calc_status:string;unsaved:boolean};
export async function sheetRequest<T>(path:string,method='GET',body?:unknown):Promise<T> {
  const response=await fetch(`${BACKEND_ORIGIN}/spreadsheets${path}`,{method,credentials:'include',headers:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});
  const value=await response.json();
  if(!response.ok)throw new Error(typeof value.detail==='string'?value.detail:`스프레드시트 요청 실패 (${response.status})`);
  return value as T;
}
export function sheetCommand<T>(id:string,op:string,args:Record<string,unknown>={}):Promise<T> {
  return sheetRequest<T>(`/${encodeURIComponent(id)}/${op}`,'POST',{args});
}
