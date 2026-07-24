/**
 * warehouse/shared — 공유창고 창의 세 패널(내 창고·이웃·이웃찾기)이 함께 쓰는
 * 타입·포맷터·아이콘 매핑. WarehouseView 가 1500줄 규칙에 걸려 분리(2026-07-20).
 */
import type { DragEvent as ReactDragEvent } from 'react';
import { File as FileIcon, FileText, Film, Music, Archive } from 'lucide-react';

export const API = 'http://127.0.0.1:8765';

export interface WhFile { name: string; bytes: number; path: string; mtime: string }
export interface WhData {
  title: string; public_url: string; level: number;
  levels: Record<string, number>; files: WhFile[];
  /** 창고 안 모든 폴더(상대경로) — 빈 폴더도 뷰에 보이게 목록이 따로 온다 */
  dirs?: string[];
  level_labels: Record<string, string>;
  root_path?: string; folder_path?: string;
}
export interface TrashItem {
  name: string; level: number; is_dir: boolean;
  count: number; bytes: number; mtime: string;
}
export interface WfNeighbor {
  contact_id: number; neighbor_id: number; name: string; info_level: number;
  /* 즐겨찾기 점수(0~3) — 내가 이 창고에 주는 평가. 접근 레벨(준/받은)과 독립인 내 쪽 축. */
  warehouse_url: string; warehouse_memo: string; score?: number;
  last_poll: string | null; ok: number | null; error: string | null;
  file_count: number | null; title: string; has_restricted: boolean;
  adapter?: string; adapter_label?: string;
  /* 회원 로그인 — 내가 그 창고에 가입한 계정으로 폴링하면 내 레벨의 매니페스트를 받는다 */
  login_user?: string; login_ok?: number | null; login_error?: string;
  viewer_level?: number | null;
}
export interface WfFeedItem {
  id?: number; wh_url: string; path: string; mtime: string; bytes: number;
  url: string; kind?: string; seen_at: string; likes?: number;
  /* 피드·검색 행에는 API 가 붙여주고, 인앱 브라우저(browse)의 스냅샷 행에는 없다 */
  neighbor_name?: string; neighbor_home?: string;
  /* 폴더 단위로 접힌 줄 — 한 폴링에서 같은 폴더에 GROUP_MIN 이상 들어왔을 때.
     원장은 파일 단위 그대로고 여기 표현만 접힌다(warehouse_feed._group_feed). */
  group?: boolean; folder?: string; count?: number; items?: WfFeedItem[];
}

/** 피드 카드(cards=1) — 카드 1장 = 이웃의 발화 1건(창고×둘러보기 회차×종류).
    items=루트 파일만(CARD_ITEMS_CAP 까지), 폴더 안 파일은 folders 로 이름만 접힌다
    (열람은 인앱 파인더). 전체 개수는 count 가 사실대로 말한다. */
export interface WfCard {
  card: true; wh_url: string; seen_at: string; kind: string;
  count: number; bytes: number; mtime: string; items: WfFeedItem[];
  folders?: WfBrowseDir[];
  neighbor_name: string; neighbor_home: string;
  /** 창고 제목(매니페스트 title) — 이웃 이름이 npub 주소일 때 카드가 이걸 앞세운다 */
  neighbor_title?: string;
}

/** 인앱 브라우저(browse)의 하위 폴더 한 줄 — 스냅샷에서 집계 파생. */
export interface WfBrowseDir { name: string; count: number; bytes: number; mtime: string }

/** "2026-07-21T07:55:21" → "07-21 07:55" — 피드 카드의 시간 표기. */
export function fmtWhen(s: string): string {
  return (s || '').slice(5, 16).replace('T', ' ');
}

export const IMG_EXT = /\.(jpe?g|png|gif|webp)$/i;

/* 창고 안 드래그 = 이 MIME 로 옮길 항목의 상대경로(JSON 배열)를 싣는다. 바깥에서
   끌어온 파일 투입(dataTransfer.files)과 구별하는 표식 — 없으면 둘이 같은 drop
   핸들러에서 엉킨다. */
export const WH_DRAG = 'application/x-indiebiz-warehouse-path';

export function fmtBytes(n: number): string {
  if (n < 1024) return `${n}B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)}KB`;
  if (n < 1024 * 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)}MB`;
  return `${(n / 1024 / 1024 / 1024).toFixed(2)}GB`;
}

export function fileIcon(name: string) {
  const ext = name.split('.').pop()?.toLowerCase() || '';
  if (/^(mp4|mov|avi|mkv|webm)$/.test(ext)) return Film;
  if (/^(mp3|m4a|wav|flac|ogg)$/.test(ext)) return Music;
  if (/^(zip|tar|gz|7z|rar)$/.test(ext)) return Archive;
  if (/^(md|txt|pdf|doc|docx|hwp|xlsx|csv)$/.test(ext)) return FileText;
  return FileIcon;
}

export function openExternalUrl(url: string) {
  const el = (window as any).electron;
  if (el?.openExternal) el.openExternal(url);
  else window.open(url, '_blank', 'noopener');
}

/** 이웃 창고 방문은 내부(포식) 브라우저로 — 창틀이 내 것이어야 파일 링크 우클릭 리트윗이 산다.
    Launcher 가 'indiebiz:open-forage-url' 을 받아 브라우저 오버레이를 그 URL 로 연다. */
export function openWarehouseInBrowser(url: string) {
  window.dispatchEvent(new CustomEvent('indiebiz:open-forage-url', { detail: url }));
}

/** 이웃 창고의 *파일*도 포식 브라우저로 — 내 로그인 쿠키(pk, persist:forage 세션)가 거기 산다.
    기본 브라우저로 열면 익명(레벨 0)이라 회원 레벨 파일이 404("no such file")가 된다:
    폴러는 저장된 자격으로 내 레벨 스냅샷을 받으므로, 여는 쪽도 같은 신원이어야 한다. */
export function openNeighborFile(url: string) {
  const el = (window as any).electron;
  if (el) openWarehouseInBrowser(url);
  else window.open(url, '_blank', 'noopener');
}

/** 이웃 창고 파일을 창 밖(파인더·바탕화면)으로 끌어 저장 — dragstart 에서 부른다.
    HTML5 드래그는 브라우저 밖으로 파일을 못 내보내므로 preventDefault 로 접고,
    메인 프로세스가 파일을 (포식 세션 쿠키로 — 회원 레벨 파일도) 내려받아 네이티브
    OS 드래그로 전환한다. 받는 동안 버튼을 놓으면 cancel — 받은 캐시는 남아
    큰 파일도 두 번째 끌기는 즉시. 비 Electron(웹)에선 아무것도 안 한다. */
export function dragOutNeighborFile(e: ReactDragEvent, f: Pick<WfFeedItem, 'url' | 'path' | 'mtime'>) {
  const el = (window as any).electron;
  if (!el?.warehouseDragOut) return;
  e.preventDefault();
  el.warehouseDragOut({
    url: f.url,
    name: f.path.split('/').pop() || f.path,
    mtime: f.mtime || '',
  });
  window.addEventListener('mouseup', () => el.warehouseDragCancel?.(), { once: true });
}
