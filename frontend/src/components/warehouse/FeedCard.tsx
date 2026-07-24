/**
 * FeedCard — 이웃 탭 피드의 카드 1장 = "이웃의 발화 1건"(창고×둘러보기 회차×종류).
 * 트위터 문법 복원: 저자·시간은 카드 헤더에 한 번만, 파일들은 본문에서 이미지=썸네일
 * 그리드 / 그 외=이름 칩 그리드로 조밀하게. 좋아요·리트윗은 칩 hover 에만 나타난다 —
 * 파일마다 버튼 4개짜리 행이 만들던 소음 제거. "외 N개"는 인앱 파인더(NeighborBrowser)로.
 */
import { useState } from 'react';
import { MessageCircle, Heart, Repeat2, Folder, Star } from 'lucide-react';
import { fmtBytes, fileIcon, openNeighborFile, IMG_EXT, fmtWhen } from './shared';
import type { WfCard, WfFeedItem } from './shared';

interface ActionProps {
  onLike: (f: WfFeedItem) => void;
  onRetweet: (f: WfFeedItem) => void;
}

/** 칩·타일 hover 시 우상단에 뜨는 좋아요·리트윗 — 클릭이 칩의 열기와 안 겹치게 전파 차단. */
export function ChipActions({ f, onLike, onRetweet }: { f: WfFeedItem } & ActionProps) {
  return (
    <div className="absolute right-1 top-1 hidden group-hover/chip:flex items-center gap-0.5 rounded-md bg-white/95 border border-stone-200 shadow-sm px-0.5">
      <button
        className="p-1 text-stone-400 hover:text-rose-500"
        title="좋아요 — 카운트는 이 파일의 창고 주인에게 쌓입니다"
        onClick={(e) => { e.stopPropagation(); onLike(f); }}
      >
        <Heart className="w-3.5 h-3.5" />
      </button>
      <button
        className="p-1 text-stone-400 hover:text-[#D97706]"
        title="리트윗 — 내 창고에 소개(링크=추천 / 복사=소장·재서빙)"
        onClick={(e) => { e.stopPropagation(); onRetweet(f); }}
      >
        <Repeat2 className="w-3.5 h-3.5" />
      </button>
    </div>
  );
}

/** 이미지 파일 = 정사각 썸네일 타일(트위터 미디어 그리드). 회원 레벨 파일처럼 브라우저가
    직접 못 받는 이미지는 onError 로 아이콘 타일로 강등 — 레이아웃은 안 흔들린다. */
function ThumbTile({ f, onLike, onRetweet }: { f: WfFeedItem } & ActionProps) {
  const [fail, setFail] = useState(false);
  const name = f.path.split('/').pop() || f.path;
  const Icon = fileIcon(name);
  return (
    <div
      className="group/chip relative aspect-square rounded-lg overflow-hidden border border-stone-200 bg-stone-100 cursor-pointer"
      title={`${f.path}\n${fmtBytes(f.bytes || 0)} · ${(f.mtime || '').replace('T', ' ')}`}
      onClick={() => openNeighborFile(f.url)}
    >
      {fail ? (
        <div className="w-full h-full flex flex-col items-center justify-center gap-1 p-1">
          <Icon className="w-8 h-8 text-stone-400" strokeWidth={1.2} />
          <span className="text-[10px] text-stone-500 text-center break-all line-clamp-2">{name}</span>
        </div>
      ) : (
        <img src={f.url} loading="lazy" className="w-full h-full object-cover" onError={() => setFail(true)} />
      )}
      {!fail && (
        <div className="absolute inset-x-0 bottom-0 px-1.5 py-0.5 bg-gradient-to-t from-black/55 to-transparent opacity-0 group-hover/chip:opacity-100">
          <span className="text-[10px] text-white break-all line-clamp-1">{name}</span>
        </div>
      )}
      {(f.likes || 0) > 0 && (
        <span className="absolute left-1 top-1 px-1 rounded bg-white/85 text-[10px] text-rose-500">♥{f.likes}</span>
      )}
      <ChipActions f={f} onLike={onLike} onRetweet={onRetweet} />
    </div>
  );
}

/** 이미지 아닌 파일 = 아이콘+이름 칩 — 한 행이 아니라 한 칸이라 카드에 수십 개도 가볍다. */
function FileChip({ f, onLike, onRetweet }: { f: WfFeedItem } & ActionProps) {
  const name = f.path.split('/').pop() || f.path;
  const Icon = fileIcon(name);
  return (
    <div
      className="group/chip relative flex items-center gap-1.5 pl-2 pr-1.5 py-1.5 rounded-lg bg-stone-50 border border-stone-200 hover:border-[#D97706]/40 cursor-pointer min-w-0"
      title={`${f.path}\n${fmtBytes(f.bytes || 0)} · ${(f.mtime || '').replace('T', ' ')}`}
      onClick={() => openNeighborFile(f.url)}
    >
      <Icon className="w-4 h-4 text-stone-400 shrink-0" />
      <span className="flex-1 min-w-0 text-xs text-stone-700 truncate group-hover/chip:text-[#B45309]">{name}</span>
      {(f.likes || 0) > 0 && <span className="text-[10px] text-rose-400 shrink-0">♥{f.likes}</span>}
      <ChipActions f={f} onLike={onLike} onRetweet={onRetweet} />
    </div>
  );
}

const KIND_BADGE: Record<string, [string, string]> = {
  new: ['새 파일', 'bg-amber-100 text-[#B45309]'],
  changed: ['갱신', 'bg-stone-100 text-stone-500'],
  seed: ['첫 둘러보기', 'bg-sky-50 text-sky-600'],
};

export function FeedCard({ c, score, onScore, onLike, onRetweet, onOpenBrowser, onDm }: {
  c: WfCard;
  /** 이 창고에 내가 준 창고점수(0~3) — 칩 줄 은퇴 후 카드가 점수의 집 */
  score: number;
  onScore: (whUrl: string, score: number) => void;
  onOpenBrowser: (whUrl: string, path?: string) => void;
  /** 이 이웃에게 nostr DM — 메신저 창을 그 이웃의 대화로 딥링크 */
  onDm: (whUrl: string) => void;
} & ActionProps) {
  const imgs = c.items.filter((f) => IMG_EXT.test(f.path));
  const rest = c.items.filter((f) => !IMG_EXT.test(f.path));
  const folders = c.folders || [];
  const [label, cls] = KIND_BADGE[c.kind || ''] || [c.kind || '', 'bg-stone-100 text-stone-500'];
  // 폴더 안 파일은 folders 가 대표하므로, "외 N개"는 루트 파일의 넘침만 말한다.
  const more = (c.count || 0) - c.items.length - folders.reduce((s, d) => s + d.count, 0);
  return (
    <li className="rounded-xl bg-white border border-stone-200 p-3 space-y-2">
      <div className="flex items-center gap-2 min-w-0">
        {/* 창고점수(0~3) — 클릭 순환. 내 평가 축이라 상대에겐 안 보인다 */}
        <button
          className="flex items-center gap-0.5 shrink-0"
          title={`창고점수 ${score} — 누르면 0→1→2→3 순환 (내 평가, 상대에겐 안 보여요)`}
          onClick={() => onScore(c.wh_url, (score + 1) % 4)}
        >
          <Star className={`w-4 h-4 ${score > 0 ? 'text-[#D97706] fill-current' : 'text-stone-300 hover:text-[#D97706]'}`} />
          {score > 0 && <span className="text-[11px] font-semibold text-[#D97706]">{score}</span>}
        </button>
        {/* 창고 제목 우선 — 이웃 이름이 npub 주소일 때도 사람이 읽는 이름이 앞선다 */}
        <button
          className="text-sm font-medium text-stone-800 hover:text-[#D97706] hover:underline truncate"
          title={`이 창고를 앱 안에서 둘러보기\n${c.neighbor_name}`}
          onClick={() => onOpenBrowser(c.wh_url)}
        >
          {c.neighbor_title || c.neighbor_name}
        </button>
        <span className={`px-1.5 rounded text-[11px] shrink-0 ${cls}`}>{label} {c.count}개</span>
        <span className="text-[11px] text-stone-400 shrink-0">{fmtBytes(c.bytes || 0)}</span>
        <div className="flex-1" />
        <span className="text-[11px] text-stone-400 shrink-0">{fmtWhen(c.seen_at)}</span>
        {/* 창고 열람은 이름 클릭이 이미 하므로, 끝자리는 대화(DM)로 잇는 문 */}
        <button
          className="p-1.5 rounded-lg text-stone-400 hover:text-[#D97706] hover:bg-amber-50 shrink-0"
          title="이 이웃에게 DM — 메신저로 대화"
          onClick={() => onDm(c.wh_url)}
        >
          <MessageCircle className="w-4 h-4" />
        </button>
      </div>
      {/* 폴더 = 이름만 — 안의 파일 수백 장이 카드를 먹지 않는다. 클릭=파인더가 그 폴더로. */}
      {folders.length > 0 && (
        <div className="grid grid-cols-[repeat(auto-fill,minmax(180px,1fr))] gap-1.5">
          {folders.map((d) => (
            <div
              key={`d:${d.name}`}
              className="flex items-center gap-1.5 pl-2 pr-1.5 py-1.5 rounded-lg bg-amber-50/60 border border-stone-200 hover:border-[#D97706]/40 cursor-pointer min-w-0"
              title={`${d.name}\n${d.count}개 · ${fmtBytes(d.bytes)} — 눌러서 폴더 열기`}
              onClick={() => onOpenBrowser(c.wh_url, d.name)}
            >
              <Folder className="w-4 h-4 text-[#F59E0B] shrink-0" />
              <span className="flex-1 min-w-0 text-xs text-stone-700 truncate">{d.name}</span>
              <span className="text-[10px] text-stone-400 shrink-0">{d.count}</span>
            </div>
          ))}
        </div>
      )}
      {imgs.length > 0 && (
        <div className="grid grid-cols-[repeat(auto-fill,minmax(96px,1fr))] gap-1.5">
          {imgs.map((f) => (
            <ThumbTile key={`${f.id ?? f.path}`} f={f} onLike={onLike} onRetweet={onRetweet} />
          ))}
        </div>
      )}
      {rest.length > 0 && (
        <div className="grid grid-cols-[repeat(auto-fill,minmax(180px,1fr))] gap-1.5">
          {rest.map((f) => (
            <FileChip key={`${f.id ?? f.path}`} f={f} onLike={onLike} onRetweet={onRetweet} />
          ))}
        </div>
      )}
      {more > 0 && (
        <button
          className="text-[11px] text-stone-400 hover:text-[#D97706] hover:underline"
          onClick={() => onOpenBrowser(c.wh_url)}
        >
          외 {more}개 — 창고 전체 보기
        </button>
      )}
    </li>
  );
}
